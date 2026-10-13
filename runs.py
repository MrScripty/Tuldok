"""Durable admission, one local worker, and verified immutable result custody."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

import image_training
import text_training
import audio_training
import release_validation
import psycopg
from workbench import WorkbenchError, encode, timestamp, text_value
from pipeline import closed, digest, execution_digest, identifier, adapter_for_graph, source_content_hash, training_environment

ACTIVE = ('queued', 'running', 'cancelling')
TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted', 'unknown')
PAYLOADS = {'metrics.json', 'test-metrics.json', 'predictions-validation.json',
            'predictions-test.json', 'checkpoint.pt'}
TEST_FILES = {'test-metrics.json', 'predictions-test.json'}
REQUEST_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$')
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def process_identity(pid):
    """Linux start ticks plus boot ID distinguish an owned PID from PID reuse."""
    try:
        stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if stat[0] == 'Z':
            return None
        return {'pid': pid, 'start_ticks': stat[19],
                'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError):
        return None


def process_status(owner):
    """A failed observation is unknown; only absence or changed identity is ceased."""
    if (not isinstance(owner, dict) or set(owner) != {'pid', 'start_ticks', 'boot_id'}
            or type(owner['pid']) is not int or owner['pid'] < 1):
        return 'unknown'
    try:
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if boot != owner['boot_id']:
            return 'ceased'
        parts = Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(')', 1)[1].split()
        return 'ceased' if parts[0] == 'Z' or parts[19] != owner['start_ticks'] else 'alive'
    except FileNotFoundError:
        return 'ceased'
    except (OSError, IndexError):
        return 'unknown'


def _sync(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Runs:
    def __init__(self, dataset, pipelines):
        self.dataset, self.pipelines = dataset, pipelines
        self.db, self.lock = dataset.db, dataset.lock
        self.path = dataset.path / 'workspace-runs'
        self.path.mkdir(exist_ok=True)
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread = None
        self._thread_lock = threading.Lock()
        self._blocked = False
        self._closed = False
        with self.lock:
            self.runtime_owner = self.db.claim_runtime('workspace_runs')
            if self.runtime_owner:
                self._recover()

    def _load(self, run_id):
        identifier(run_id, 'Run ID')
        row = self.db.execute('SELECT request_key,request_sha256,document FROM workspace_runs WHERE id=%s', (run_id,)).fetchone()
        if row is None:
            raise WorkbenchError('Run not found.', 'unavailable', 404)
        try:
            run = json.loads(row['document'])
            if (run['schema_version'] != 1 or run['id'] != run_id or run['dataset_id'] != self.db.dataset_id
                    or run['mode'] != 'real' or run['state'] not in (*ACTIVE, *TERMINAL)
                    or run['request_key'] != row['request_key'] or run['request_sha256'] != row['request_sha256']
                    or digest(run['graph']) != run['graph_document_sha256']
                    or execution_digest(run['graph']) != run['graph_sha256']
                    or run['adapter'] != adapter_for_graph(run['graph']).ADAPTER):
                raise ValueError('Invalid retained run identity.')
            return run
        except (ValueError, KeyError, TypeError):
            raise WorkbenchError('Stored run envelope is invalid; refusing to guess execution state.', 'unavailable', 409) from None

    def _save(self, run):
        self.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (encode(run), run['id']))

    def _event(self, run, state, message):
        run['state'] = state
        run['events'].append({'at': timestamp(), 'state': state, 'message': message})
        if state in TERMINAL:
            run['finished_at'] = timestamp()
            run['progress'] = {'stage': state, 'completed': None, 'total': None}

    def _recover(self):
        """Never restart durable work or signal a remembered PID on startup."""
        with self.db.transaction():
            for row in self.db.execute('SELECT id FROM workspace_runs'):
                run = self._load(row[0])
                if run['state'] not in (*ACTIVE, 'unknown'):
                    continue
                worker = run.get('worker')
                if run['process_phase'] == 'not_started':
                    state = 'interrupted'
                elif worker:
                    state = 'interrupted' if process_status(worker) == 'ceased' else 'unknown'
                else:
                    state = self._reconcile_start(run)
                self._blocked |= state == 'unknown'
                self._event(run, state, 'Worker cessation is unconfirmed. Stop the prior application, then reopen this catalog to reconcile its exact local process.' if state == 'unknown' else
                            'Application restarted; this attempt was not replayed. Restart training explicitly.')
                self._save(run)

    def _reconcile_start(self, run):
        """Resolve only this closed worker's spawn/PID-receipt crash window."""
        if process_status(run.get('supervisor')) != 'ceased':
            return 'unknown'
        command = run.get('worker_command')
        if (not isinstance(command, list) or len(command) != 4 or not all(isinstance(value, str) for value in command)
                or command[2] != '--job' or not command[1].endswith(f"/.staging-{run['id']}/{Path(adapter_for_graph(run['graph']).__file__).name}")
                or Path(command[3]) != Path(command[1]).with_name('job.json')):
            return 'unknown'
        try:
            for path in Path('/proc').iterdir():
                if not path.name.isdigit():
                    continue
                try:
                    if path.stat().st_uid != os.getuid():
                        continue
                    argv = (path / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
                    if argv[1:] == [value.encode() for value in command[1:]]:
                        return 'unknown'
                except FileNotFoundError:
                    continue
                except OSError:
                    return 'unknown'
        except OSError:
            return 'unknown'
        # The qualified adapter checks parent death before Torch and uses no
        # child workers; a dead supervisor cannot create a later matching worker.
        return 'interrupted'

    def _public(self, run):
        hidden = {'source_records', 'release_path', 'worker', 'python', 'request_sha256', 'graph_document_sha256',
                  'worker_command', 'supervisor', 'process_phase'}
        result = {key: copy.deepcopy(value) for key, value in run.items() if key not in hidden}
        result['test_exposure'] = {'exposed': bool(run['exposure_events']), 'event_count': len(run['exposure_events'])}
        result['current_test_exposure'] = ({'exposed': False, 'events': []} if self._validation_run(run)
                                           else self.pipelines.exposures(run['source_records']))
        result.pop('exposure_events', None)
        result['artifacts'] = [dict(item, locked=item['name'] in TEST_FILES and not result['test_exposure']['exposed'],
                                    url=f"/api/workspace/runs/{run['id']}/artifacts/{item['name']}")
                               for item in run['artifacts']]
        result['input_artifacts'] = [{'name': 'release.zip', 'sha256': run['release_sha256'], 'bytes': run['release_bytes'],
                                      'media_type': 'application/zip', 'stage': 'validate/export',
                                      'url': f"/api/workspace/runs/{run['id']}/artifacts/release.zip"}]
        return result

    def list(self):
        with self.lock:
            rows = [self._load(row[0]) for row in self.db.execute('SELECT id FROM workspace_runs')]
        result = []
        for run in sorted(rows, key=lambda item: (item['created_at'], item['id']), reverse=True):
            public = self._public(run)
            if run['state'] == 'completed':
                try:
                    self._verified_artifacts(run)
                except WorkbenchError as error:
                    public['metrics'] = None
                    public.pop('validation_summary', None)
                    public['artifact_status'] = {'status': 'unavailable', 'message': str(error)}
            result.append(public)
        return result

    def get(self, run_id):
        with self.lock:
            run = self._load(run_id)
        if run['state'] == 'completed':
            # A retained completed envelope never certifies missing or altered files.
            self._verified_artifacts(run)
        return self._public(run)

    def _request(self, body, required):
        closed(body, required)
        key = body['request_key']
        if not isinstance(key, str) or not REQUEST_KEY.fullmatch(key):
            raise WorkbenchError('Submission key must be 8–128 letters, digits or . _ : - characters.')
        try:
            return key, digest(body)
        except (ValueError, TypeError):
            raise WorkbenchError('Submission must be finite JSON.') from None

    def _receipt(self, key, request_hash):
        row = self.db.execute('SELECT id,request_sha256 FROM workspace_runs WHERE request_key=%s', (key,)).fetchone()
        if row:
            if row['request_sha256'] != request_hash:
                raise WorkbenchError('This submission key already belongs to a different request.', 'conflict', 409)
            return self._public(self._load(row['id']))
        return None

    def _available(self):
        if self._closed or not self.runtime_owner:
            raise WorkbenchError('Another application owns this catalog’s training supervisor.', 'unavailable', 409)
        if self._blocked:
            raise WorkbenchError('A prior worker has unconfirmed cessation. Close the old application before reopening this catalog.', 'unavailable', 409)
        if sys.platform != 'linux':
            raise WorkbenchError('The qualified CPU worker lifecycle currently requires Linux.', 'unsupported', 400)

    def submit(self, body):
        key, request_hash = self._request(body, ('request_key', 'graph_id', 'graph_revision', 'validation_token'))
        with self.lock:
            receipt = self._receipt(key, request_hash)
        if receipt:
            return self._reconcile_receipt(receipt)
        self._available()
        graph, validation, release = self.pipelines.snapshot(body['graph_id'], body['graph_revision'], body['validation_token'])
        with self.lock, self.db.transaction():
            receipt = self._receipt(key, request_hash)
            if not receipt:
                if self.pipelines._get(graph['id']) != graph:
                    raise WorkbenchError('Graph changed during submission.', 'stale', 409)
                run = self._admit(key, request_hash, graph, validation, release)
        if receipt:
            return self._reconcile_receipt(receipt)
        self._start()
        return self._public(run)

    def _reconcile_receipt(self, receipt):
        # A committed admission whose response/commit acknowledgment was lost
        # still needs its existing queue observed. This never admits a second run.
        if receipt['state'] == 'queued' and self.runtime_owner and not self._blocked and not self._closed and not self._stop.is_set():
            self._start()
        return receipt

    def _admit(self, key, request_hash, graph, validation, release, parent=None):
        queued = sum(self._load(row[0])['state'] in ACTIVE for row in self.db.execute('SELECT id FROM workspace_runs'))
        if queued >= 8:
            raise WorkbenchError('The local queue is full (8 attempts). Wait or cancel a queued attempt.', 'unavailable', 409)
        run_id = uuid.uuid4().hex
        parameters = next((node['parameters'] for node in graph['nodes'] if node['type'] == 'train'), {})
        run = {'schema_version': 1, 'mode': 'real', 'id': run_id, 'dataset_id': self.db.dataset_id,
               'request_key': key, 'request_sha256': request_hash, 'state': 'queued',
               'created_at': timestamp(), 'started_at': None, 'finished_at': None,
               'graph': copy.deepcopy(graph), 'graph_revision': graph['revision'],
               'graph_sha256': execution_digest(graph), 'graph_document_sha256': digest(graph),
               'release_id': release['id'], 'release_sha256': release['sha256'], 'release_path': release['path'],
               'release_bytes': Path(release['path']).stat().st_size,
               'source_records': copy.deepcopy(release['manifest']['records']),
               'prior_test_exposure': release['prior_test_exposure'],
               'adapter': validation['runtime']['adapter'], 'runtime': validation['runtime'],
               'parameters': copy.deepcopy(parameters), 'python': os.environ.get('TULDOK_TRAINING_PYTHON') or sys.executable,
               'attempt': parent['attempt'] + 1 if parent else 1, 'parent_run_id': parent['id'] if parent else None,
               'events': [], 'artifacts': [], 'metrics': None, 'error': None, 'worker': None,
               'process_phase': 'not_started', 'supervisor': None, 'worker_command': None,
               'exposure_events': [], 'quality_claim': False,
               'progress': {'stage': 'queued', 'completed': None, 'total': None},
               'node_attempts': [{'node_id': node['id'], 'type': node['type'], 'state': 'pending'} for node in graph['nodes']]}
        if self._validation_run(run):
            run.update(result_kind='release_validation', validation_summary=copy.deepcopy(release['validation_summary']))
        self._event(run, 'queued', 'Frozen mesh integrity attempt admitted.' if self._validation_run(run) else
                    'Real CPU attempt admitted. Training starts from scratch; no model download.')
        self.db.execute('INSERT INTO workspace_runs(id,request_key,request_sha256,document) VALUES(%s,%s,%s,%s)',
                        (run_id, key, request_hash, encode(run)))
        return run

    def retry(self, run_id, body):
        closed(body, ('request_key',))
        key, request_hash = self._request(dict(body, parent_run_id=run_id), ('request_key', 'parent_run_id'))
        with self.lock:
            receipt = self._receipt(key, request_hash)
            if not receipt:
                parent = self._load(run_id)
        if receipt:
            return self._reconcile_receipt(receipt)
        self._available()
        if parent['state'] not in ('failed', 'cancelled', 'interrupted'):
            raise WorkbenchError('Only failed, cancelled or interrupted attempts can restart; unknown work requires reconciliation.', 'conflict', 409)
        validation = self.pipelines.validate_graph(parent['graph'])
        if not validation['valid']:
            first = validation['errors'][0]
            raise WorkbenchError(first['message'], first['code'], 409)
        release = self.pipelines.inspect_release(parent['release_id'], private=True)
        with self.lock, self.db.transaction():
            receipt = self._receipt(key, request_hash)
            if not receipt:
                run = self._admit(key, request_hash, parent['graph'], validation, release, parent)
        if receipt:
            return self._reconcile_receipt(receipt)
        self._start()
        return self._public(run)

    def cancel(self, run_id):
        with self.lock, self.db.transaction():
            run = self._load(run_id)
            if run['state'] == 'queued':
                self._event(run, 'cancelled', 'Queued attempt cancelled before process creation.')
            elif run['state'] == 'running':
                self._event(run, 'cancelling', 'Cancellation requested; waiting for confirmed process-group cessation.')
            self._save(run)
        self._wake.set()
        return self._public(run)

    def _start(self):
        with self._thread_lock:
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name='workspace-runs', daemon=True)
                self._thread.start()
        self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            if self._blocked or not self.runtime_owner:
                self._wake.wait(.25)
                self._wake.clear()
                continue
            try:
                with self.lock:
                    queued = [self._load(row[0]) for row in self.db.execute('SELECT id FROM workspace_runs')]
                    queued = sorted((run for run in queued if run['state'] == 'queued'), key=lambda run: (run['created_at'], run['id']))
            except psycopg.Error:
                self._stop.set()
                return
            if not queued:
                self._wake.wait(.25)
                self._wake.clear()
                continue
            try:
                self._execute(queued[0]['id'])
            except Exception as error:
                try:
                    with self.lock, self.db.transaction():
                        run = self._load(queued[0]['id'])
                        if run['state'] in ACTIVE:
                            run['error'] = {'code': 'failed', 'message': 'Run supervisor could not complete this attempt.'}
                            self._event(run, 'failed', run['error']['message'])
                            self._save(run)
                except psycopg.Error:
                    # _execute's finally owns child drainage even when persistence
                    # disappears. The retained active row reconciles on reopening.
                    self._stop.set()
                    return

    def _execute(self, run_id):
        process = owner = None
        with self.lock, self.db.transaction():
            run = self._load(run_id)
            if run['state'] != 'queued':
                return
            self._event(run, 'running', 'Verifying frozen release and adapter before starting the CPU worker.')
            run['started_at'] = timestamp()
            run['progress']['stage'] = 'validate'
            self._save(run)
        try:
            if self._validation_run(run):
                self._execute_validation(run)
                return
            release = self.pipelines.inspect_release(run['release_id'], private=True)
            runtime = self.pipelines.probe(run['graph'].get('recipe', 'image_classification'))
            if not runtime['available'] or runtime != run['runtime']:
                raise WorkbenchError('Training runtime changed after admission.', 'stale', 409)
            stage = self.path / ('.staging-' + run_id)
            stage.mkdir(mode=0o700)
            output = stage / 'output'
            output.mkdir(mode=0o700)
            job = {'schema_version': 1, 'dataset_id': run['dataset_id'], 'run_id': run_id,
                   'graph_sha256': run['graph_sha256'], 'release_id': run['release_id'],
                   'release_sha256': run['release_sha256'], 'release_path': release['path'],
                   'output_dir': str(output), 'parameters': run['parameters'], 'parent_pid': os.getpid()}
            job_path = stage / 'job.json'
            job_path.write_text(encode(job))
            definition_files = run['runtime']['definition_files']
            if digest(definition_files) != run['runtime']['adapter_definition_sha256']:
                raise WorkbenchError('Pinned adapter definition is inconsistent.', 'stale', 409)
            for name, expected_hash in definition_files.items():
                if name not in self.pipelines.definition_identity(run['graph'].get('recipe', 'image_classification'))['definition_files']:
                    raise WorkbenchError('Unsupported adapter source dependency.', 'unsupported', 409)
                contents = (self.pipelines.source_path / name).read_bytes()
                if hashlib.sha256(contents).hexdigest() != expected_hash:
                    raise WorkbenchError('Adapter source changed before process creation.', 'stale', 409)
                (stage / name).write_bytes(contents)
            worker_path = stage / Path(adapter_for_graph(run['graph']).__file__).name
            command = [run['python'], str(worker_path), '--job', str(job_path)]
            with self.lock, self.db.transaction():
                current = self._load(run_id)
                current['execution_test_exposure'] = self.pipelines.exposures(current['source_records'])
                self._save(current)
                if current['state'] == 'cancelling' or self._stop.is_set():
                    self._event(current, 'cancelled', 'Cancelled before worker process creation.')
                    self._save(current)
                    return
                current['process_phase'] = 'starting'
                current['supervisor'] = process_identity(os.getpid())
                current['worker_command'] = command
                self._save(current)
            process = subprocess.Popen(command,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True,
                                       env=training_environment())
            os.set_blocking(process.stdout.fileno(), False)
            progress = {'buffer': b'', 'bytes': 0, 'epoch': 0}
            owner = process_identity(process.pid)
            if owner is None:
                process.wait(timeout=10)
                raise WorkbenchError('CPU worker exited before lifecycle ownership was recorded.', 'failed', 409)
            with self.lock, self.db.transaction():
                current = self._load(run_id)
                current['worker'] = owner
                current['process_phase'] = 'started'
                current['progress']['stage'] = 'train'
                for node in current['node_attempts']:
                    node['state'] = 'completed' if node['type'] in ('release', 'validate') else 'running' if node['type'] == 'train' else 'pending'
                self._save(current)
            started = time.monotonic()
            cancelled = False
            try:
                while process.poll() is None:
                    self._read_progress(process, run, progress)
                    with self.lock:
                        current = self._load(run_id)
                    if current['state'] == 'cancelling' or self._stop.is_set():
                        cancelled = True
                        self._drain(process, owner)
                        break
                    if time.monotonic() - started > 600:
                        self._drain(process, owner)
                        raise WorkbenchError('CPU worker exceeded its ten-minute bound.', 'failed', 409)
                    self._wake.wait(.1)
                    self._wake.clear()
                process.wait()
                self._read_progress(process, run, progress)
                try:
                    os.killpg(process.pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise WorkbenchError('Worker group cessation is unconfirmed.', 'unknown', 409)
            finally:
                if process.poll() is None:
                    self._drain(process, owner)
            with self.lock:
                current = self._load(run_id)
            if cancelled or current['state'] == 'cancelling':
                self._finish(run_id, 'cancelled', 'Worker process group drained; no results were published.')
                return
            if process.returncode != 0:
                raise WorkbenchError(f'CPU trainer exited with status {process.returncode}; no results were published.', 'failed', 409)
            artifacts, metrics = self._verify_directory(run, output)
            for path in output.iterdir():
                with path.open('rb') as handle:
                    os.fsync(handle.fileno())
            _sync(output)
            with self.lock, self.db.transaction():
                current = self._load(run_id)
                if current['state'] == 'cancelling' or self._stop.is_set():
                    self._event(current, 'cancelled', 'Cancelled before artifact publication; worker group drained.')
                    self._save(current)
                    return
                destination = self.path / run_id
                os.rename(output, destination)
                _sync(self.path)
                current['artifacts'] = artifacts
                current['metrics'] = metrics
                for node in current['node_attempts']:
                    node['state'] = 'completed'
                self._event(current, 'completed', 'Verified real CPU outputs published. Test results remain behind explicit exposure.')
                self._save(current)
        except WorkbenchError as error:
            self._finish(run_id, 'unknown' if error.code == 'unknown' else 'failed', str(error), error.code)
        except (OSError, ValueError, subprocess.SubprocessError):
            self._finish(run_id, 'failed', 'Local worker or artifact publication failed; this attempt was not replayed.')
        finally:
            if process is not None and process.poll() is None:
                try:
                    self._drain(process, owner)
                except (WorkbenchError, OSError, subprocess.SubprocessError):
                    self._blocked = True
                    with self.lock, self.db.transaction():
                        current = self._load(run_id)
                        current['error'] = {'code': 'unknown', 'message': 'Worker cessation could not be confirmed.'}
                        self._event(current, 'unknown', current['error']['message'])
                        self._save(current)
            if process is not None and process.stdout is not None:
                process.stdout.close()

    @staticmethod
    def _validation_run(run):
        return adapter_for_graph(run['graph']) is release_validation

    def _execute_validation(self, run):
        """Bounded local reader, owned by the sole supervisor; never spawns children.

        process_phase remains not_started: after application death no independent
        worker can survive. Restart therefore interrupts rather than replays it.
        Cancellation can arrive during native parsing and is observed before any
        publication; the existing close() join keeps metadata alive until drain.
        """
        run_id = run['id']
        with self.lock:
            current = self._load(run_id)
        if current['state'] == 'cancelling' or self._stop.is_set():
            self._finish(run_id, 'cancelled', 'Cancelled before frozen integrity validation.')
            return
        with self.lock, self.db.transaction():
            current = self._load(run_id)
            for node in current['node_attempts']:
                node['state'] = 'completed' if node['type'] == 'release' else 'running' if node['type'] == 'validate' else 'pending'
            self._save(current)
        runtime = self.pipelines.probe(release_validation.RECIPE)
        if runtime != run['runtime']:
            raise WorkbenchError('Integrity definition changed after admission.', 'stale', 409)
        release = self.pipelines.inspect_release(run['release_id'], private=True)
        if release['validation_summary'] != run['validation_summary']:
            raise WorkbenchError('Frozen mesh evidence changed after admission.', 'stale', 409)
        # Validate the definition again after reading, before publishing its result.
        if self.pipelines.probe(release_validation.RECIPE) != runtime:
            raise WorkbenchError('Integrity definition changed during execution.', 'stale', 409)
        stage = self.path / ('.staging-' + run_id)
        stage.mkdir(mode=0o700)
        output = stage / 'output'
        output.mkdir(mode=0o700)
        release_validation.write_report(output, self._identity(run), release['validation_summary'])
        artifacts, metrics = self._verify_directory(run, output)
        for path in output.iterdir():
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
        _sync(output)
        with self.lock, self.db.transaction():
            current = self._load(run_id)
            if current['state'] == 'cancelling' or self._stop.is_set():
                for node in current['node_attempts']:
                    if node['state'] == 'running':
                        node['state'] = 'cancelled'
                self._event(current, 'cancelled', 'Cancelled before integrity artifact publication.')
                self._save(current)
                return
            os.rename(output, self.path / run_id)
            _sync(self.path)
            current['artifacts'], current['metrics'] = artifacts, metrics
            for node in current['node_attempts']:
                node['state'] = 'completed'
            self._event(current, 'completed', 'Verified frozen mesh integrity report published; no training ran.')
            self._save(current)

    def _read_progress(self, process, run, progress):
        """Only bounded adapter events become logs; raw worker text is never served."""
        while True:
            try:
                chunk = os.read(process.stdout.fileno(), 8192)
            except BlockingIOError:
                return
            if not chunk:
                if progress['buffer']:
                    raise WorkbenchError('Worker progress ended with an incomplete event.', 'failed', 409)
                return
            progress['bytes'] += len(chunk)
            progress['buffer'] += chunk
            if progress['bytes'] > 65536:
                raise WorkbenchError('Worker progress exceeded the 64 KiB bound.', 'failed', 409)
            while b'\n' in progress['buffer']:
                line, progress['buffer'] = progress['buffer'].split(b'\n', 1)
                if len(line) > 8192:
                    raise WorkbenchError('Worker progress event is oversized.', 'failed', 409)
                try:
                    event = json.loads(line)
                    kind = event['event']
                    fields = ('schema_version', 'event', 'epoch', 'epochs', 'validation') if kind == 'epoch' else (
                        ('schema_version', 'event', 'outcome', 'message') if kind == 'failed' else ('schema_version', 'event', 'epochs'))
                    closed(event, fields)
                    if type(event['schema_version']) is not int or event['schema_version'] != 1 or kind not in ('started', 'epoch', 'completed', 'failed'):
                        raise ValueError('Unsupported progress event.')
                    if kind == 'failed':
                        if event['outcome'] not in ('invalid', 'unsupported', 'unavailable', 'failed') or not isinstance(event['message'], str) or len(event['message']) > 400:
                            raise ValueError('Malformed adapter failure.')
                        message = f"Adapter {event['outcome']}: {event['message']}"
                    else:
                        if type(event['epochs']) is not int or event['epochs'] != self._fit_count(run):
                            raise ValueError('Progress epoch total differs from admitted parameters.')
                        message = 'Local CPU worker started.' if kind == 'started' else 'CPU worker finished; verifying outputs before publication.'
                        if kind == 'epoch':
                            if type(event['epoch']) is not int or event['epoch'] != progress['epoch'] + 1 or event['epoch'] > event['epochs']:
                                raise ValueError('Worker epoch sequence is invalid.')
                            self._metric(event['validation'], 'validation', run)
                            progress['epoch'] = event['epoch']
                            message = f"Fit pass {event['epoch']} of {event['epochs']} completed; validation accuracy {event['validation']['accuracy']:.3f}."
                    with self.lock, self.db.transaction():
                        current = self._load(run['id'])
                        current['events'].append({'at': timestamp(), 'state': current['state'], 'message': message})
                        if len(current['events']) > 32:
                            raise ValueError('Worker emitted too many progress events.')
                        if kind == 'epoch':
                            current['progress'] = {'stage': 'train', 'completed': event['epoch'], 'total': event['epochs']}
                        self._save(current)
                except (ValueError, TypeError, KeyError) as error:
                    raise WorkbenchError('Invalid worker progress: ' + str(error)[:200], 'failed', 409) from None

    def _drain(self, process, owner):
        if process.poll() is not None:
            return
        if process_identity(process.pid) != owner:
            raise WorkbenchError('Owned worker identity changed; refusing to signal an unverified PID.', 'unknown', 409)
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if process_identity(process.pid) != owner:
                raise WorkbenchError('Worker identity cannot be confirmed for final cancellation.', 'unknown', 409)
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)

    def _finish(self, run_id, state, message, code='failed'):
        with self.lock, self.db.transaction():
            run = self._load(run_id)
            if run['state'] not in ACTIVE:
                return
            if state in ('failed', 'unknown'):
                run['error'] = {'code': code, 'message': message[:1000]}
            self._event(run, state, message[:1000])
            for node in run['node_attempts']:
                if node['state'] == 'running':
                    node['state'] = state
            self._save(run)
            if state == 'unknown':
                self._blocked = True

    def _identity(self, run):
        return {key: run[key] for key in ('dataset_id', 'graph_sha256', 'release_id', 'release_sha256')} | {'run_id': run['id']}

    def _fit_count(self, run):
        return run['parameters']['epochs'] if adapter_for_graph(run['graph']) is image_training else 1

    def _payloads(self, run):
        if self._validation_run(run):
            return release_validation.PAYLOADS
        return PAYLOADS if adapter_for_graph(run['graph']) is image_training else PAYLOADS - {'checkpoint.pt'} | {'model.json'}

    def _reference_keys(self, run):
        adapter = adapter_for_graph(run['graph'])
        return adapter.REFERENCE_KEYS if adapter is not image_training else (
            'id', 'revision', 'source_revision', 'source_sha256', 'asset_sha256', 'exported_pixel_sha256')

    def _verify_directory(self, run, directory):
        if self._validation_run(run):
            return release_validation.verify_directory(directory, self._identity(run), run['validation_summary'])
        if directory.is_symlink() or not directory.is_dir():
            raise WorkbenchError('Published artifact directory is unavailable.', 'unavailable', 409)
        payload_names = self._payloads(run)
        paths = list(directory.iterdir())
        if {path.name for path in paths} != payload_names | {'artifact-manifest.json'} or any(path.is_symlink() or not path.is_file() for path in paths):
            raise WorkbenchError('Artifact files do not match the closed result contract.', 'unavailable', 409)
        if sum(path.stat().st_size for path in paths) > MAX_ARTIFACT_BYTES:
            raise WorkbenchError('Artifacts exceed the 64 MiB result bound.', 'unavailable', 409)
        try:
            manifest_bytes = (directory / 'artifact-manifest.json').read_bytes()
            manifest = json.loads(manifest_bytes)
            closed(manifest, ('schema_version', 'source_identity', 'adapter', 'artifacts'))
            if manifest['schema_version'] != 1 or manifest['source_identity'] != self._identity(run) or manifest['adapter'] != run['adapter']:
                raise ValueError('Artifact identity mismatch.')
            artifacts = manifest['artifacts']
            if len(artifacts) != 5 or {item['name'] for item in artifacts} != payload_names:
                raise ValueError('Artifact inventory mismatch.')
            payloads = {}
            for item in artifacts:
                closed(item, ('name', 'sha256', 'bytes', 'media_type', 'split'))
                expected_split = 'test' if item['name'] in TEST_FILES else 'validation' if item['name'] in ('metrics.json', 'predictions-validation.json') else None
                expected_media = 'application/json' if item['name'].endswith('.json') else 'application/octet-stream'
                if item['split'] != expected_split or item['media_type'] != expected_media:
                    raise ValueError('Artifact media type or split differs from its declared role.')
                contents = (directory / item['name']).read_bytes()
                if type(item['bytes']) is not int or len(contents) != item['bytes'] or hashlib.sha256(contents).hexdigest() != item['sha256']:
                    raise ValueError('Artifact hash mismatch.')
                if item['name'].endswith('.json'):
                    payload = json.loads(contents)
                    if payload['schema_version'] != 1 or payload['source_identity'] != self._identity(run) or payload['adapter'] != run['adapter']:
                        raise ValueError('Artifact source identity mismatch.')
                    payloads[item['name']] = payload
            metrics = payloads['metrics.json']
            closed(metrics, ('schema_version', 'source_identity', 'adapter', 'parameters', 'transform', 'class_vocabulary',
                             'class_to_idx', 'validation', 'history', 'best_epoch', 'runtime'))
            self._vocabulary(run, metrics)
            if any(metrics['runtime'].get(key) != value for key, value in run['runtime']['runtime'].items()):
                raise ValueError('Executed runtime differs from the admission fingerprint.')
            if metrics['parameters'] != run['parameters'] or metrics['transform'] != adapter_for_graph(run['graph']).TRANSFORM:
                raise ValueError('Default metrics are inconsistent or disclose test results.')
            if adapter_for_graph(run['graph']) is not image_training:
                adapter = adapter_for_graph(run['graph'])
                model = adapter.validate_model(payloads['model.json'])
                self._vocabulary(run, model)
                if model['parameters'] != run['parameters'] or model['transform'] != adapter.TRANSFORM:
                    raise ValueError('JSON model differs from the admitted recipe.')
            self._metric(metrics['validation'], 'validation', run)
            if type(metrics['best_epoch']) is not int or not 1 <= metrics['best_epoch'] <= self._fit_count(run):
                raise ValueError('Selected checkpoint epoch is invalid.')
            if not isinstance(metrics['history'], list) or len(metrics['history']) != self._fit_count(run):
                raise ValueError('Training history does not contain the admitted epoch count.')
            for epoch, entry in enumerate(metrics['history'], 1):
                closed(entry, ('epoch', 'training_loss', 'validation'))
                if (type(entry['epoch']) is not int or entry['epoch'] != epoch or type(entry['training_loss']) not in (int, float)
                        or not 0 <= entry['training_loss'] <= 1e12 or not math.isfinite(entry['training_loss'])):
                    raise ValueError('Training history is invalid.')
                self._metric(entry['validation'], 'validation', run)
            closed(payloads['test-metrics.json'], ('schema_version', 'source_identity', 'adapter', 'split', 'metrics'))
            if payloads['test-metrics.json']['split'] != 'test':
                raise ValueError('Test metrics have the wrong split.')
            self._metric(payloads['test-metrics.json']['metrics'], 'test', run)
            for split in ('validation', 'test'):
                matrix = self._predictions(run, payloads[f'predictions-{split}.json'], split)
                expected_metric = metrics['validation'] if split == 'validation' else payloads['test-metrics.json']['metrics']
                if matrix != expected_metric['confusion_matrix']:
                    raise ValueError('Per-example predictions disagree with the reported confusion matrix.')
            inventory = copy.deepcopy(artifacts)
            inventory.append({'name': 'artifact-manifest.json', 'sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                              'bytes': len(manifest_bytes), 'media_type': 'application/json', 'split': None})
            return inventory, metrics
        except (ValueError, TypeError, KeyError, OSError) as error:
            raise WorkbenchError('Artifact verification failed: ' + str(error)[:300], 'unavailable', 409) from None

    @staticmethod
    def _source_label(row):
        return row['target_label'] if row['kind'] == 'audio' else row['annotation']['label']

    def _metric(self, value, split, run):
        closed(value, ('split', 'examples', 'loss', 'accuracy', 'macro_f1', 'confusion_matrix'))
        examples = sum(row['split'] == split for row in run['source_records'])
        if value['split'] != split or type(value['examples']) is not int or value['examples'] != examples:
            raise ValueError('Metric split or example count differs from the frozen release.')
        for key in ('loss', 'accuracy', 'macro_f1'):
            number = value[key]
            if type(number) not in (int, float) or not 0 <= number <= (1e12 if key == 'loss' else 1) or not math.isfinite(number):
                raise ValueError('Metric is not a finite result.')
        count = len({self._source_label(row) for row in run['source_records']})
        matrix = value['confusion_matrix']
        if (not isinstance(matrix, list) or len(matrix) != count or
                any(not isinstance(row, list) or len(row) != count or any(type(number) is not int or number < 0 for number in row) for row in matrix)
                or sum(map(sum, matrix)) != examples):
            raise ValueError('Confusion matrix shape or total differs from the frozen split.')
        if abs(sum(matrix[index][index] for index in range(count)) / examples - value['accuracy']) > 1e-9:
            raise ValueError('Accuracy disagrees with the confusion matrix.')

    def _vocabulary(self, run, payload):
        labels = sorted({self._source_label(row) for row in run['source_records']})
        if adapter_for_graph(run['graph']) is not image_training:
            vocabulary = [{'label': label, 'index': index} for index, label in enumerate(labels)]
            mapping = {item['label']: item['index'] for item in vocabulary}
        else:
            vocabulary = [{'label': label, 'folder': f'class_{index:06d}', 'index': index} for index, label in enumerate(labels)]
            mapping = {item['folder']: item['index'] for item in vocabulary}
        if payload['class_vocabulary'] != vocabulary or payload['class_to_idx'] != mapping:
            raise ValueError('Result vocabulary differs from the frozen release.')
        return vocabulary

    def _predictions(self, run, payload, split):
        closed(payload, ('schema_version', 'source_identity', 'adapter', 'split', 'class_vocabulary', 'class_to_idx', 'rows'))
        sources = {row['id']: row for row in run['source_records'] if row['split'] == split}
        rows = payload['rows']
        vocabulary = self._vocabulary(run, payload)
        matrix = [[0] * len(vocabulary) for _ in vocabulary]
        if payload['split'] != split or len(rows) != len(sources) or len({row['id'] for row in rows}) != len(rows):
            raise ValueError('Prediction cardinality differs from the frozen split.')
        for row in rows:
            closed(row, (*self._reference_keys(run), 'split', 'truth_label', 'truth_index', 'predicted_label', 'predicted_index', 'probabilities'))
            source = sources.get(row['id'])
            if any(type(row[key]) is not int or row[key] < 1 for key in ('revision', 'source_revision')):
                raise ValueError('Prediction revisions must be positive integers.')
            if adapter_for_graph(run['graph']) is audio_training and any(type(row[key]) is not int for key in ('sample_rate_hz', 'channels', 'channel', 'start_frame', 'end_frame')):
                raise ValueError('Audio prediction coordinates must be integer source frames and channels.')
            if source is None or any(row[key] != source['content_hash' if key == 'content_sha256' else key] for key in self._reference_keys(run)):
                raise ValueError('Prediction references a different frozen example.')
            if row['source_sha256'] != source.get('source_sha256') or row['truth_label'] != self._source_label(source) or row['split'] != split:
                raise ValueError('Prediction target or original source identity differs.')
            if any(type(row[key]) is not int or not 0 <= row[key] < len(vocabulary) for key in ('truth_index', 'predicted_index')):
                raise ValueError('Prediction class index is invalid.')
            if vocabulary[row['truth_index']]['label'] != row['truth_label'] or vocabulary[row['predicted_index']]['label'] != row['predicted_label']:
                raise ValueError('Prediction labels disagree with class vocabulary.')
            probabilities = row['probabilities']
            if (not isinstance(probabilities, list) or len(probabilities) != len(vocabulary) or
                    any(type(number) not in (int, float) or not 0 <= number <= 1 or not math.isfinite(number) for number in probabilities)
                    or abs(sum(probabilities) - 1) > .0001):
                raise ValueError('Prediction probabilities are invalid.')
            if probabilities.index(max(probabilities)) != row['predicted_index']:
                raise ValueError('Predicted class differs from the maximum probability.')
            matrix[row['truth_index']][row['predicted_index']] += 1
        return matrix

    def _verified_artifacts(self, run):
        if run['state'] != 'completed':
            raise WorkbenchError('This attempt has no published results.', 'unavailable', 409)
        artifacts, metrics = self._verify_directory(run, self.path / run['id'])
        if artifacts != run['artifacts'] or metrics != run['metrics']:
            raise WorkbenchError('Published artifacts differ from the admitted result receipt.', 'unavailable', 409)
        return artifacts

    def artifact(self, run_id, name):
        if name not in PAYLOADS | release_validation.PAYLOADS | {'model.json', 'artifact-manifest.json', 'release.zip'}:
            raise WorkbenchError('Unknown run artifact.', 'unavailable', 404)
        with self.lock:
            run = self._load(run_id)
        if name not in self._payloads(run) | {'artifact-manifest.json', 'release.zip'}:
            raise WorkbenchError('Unknown artifact for this recipe.', 'unavailable', 404)
        if name == 'release.zip':
            release = self.pipelines.inspect_release(run['release_id'], private=True)
            contents = Path(release['path']).read_bytes()
            if len(contents) != run['release_bytes'] or hashlib.sha256(contents).hexdigest() != run['release_sha256']:
                raise WorkbenchError('Frozen export changed during read.', 'unavailable', 409)
            return contents, 'application/zip'
        if name in TEST_FILES and not run['exposure_events']:
            raise WorkbenchError('Record an explicit test-set exposure before opening test results.', 'conflict', 409)
        artifacts = self._verified_artifacts(run)
        item = next(item for item in artifacts if item['name'] == name)
        contents = (self.path / run_id / name).read_bytes()
        if len(contents) != item['bytes'] or hashlib.sha256(contents).hexdigest() != item['sha256']:
            raise WorkbenchError('Artifact changed during read.', 'unavailable', 409)
        return contents, item['media_type']

    def expose_test(self, run_id, body):
        closed(body, ('reason',))
        reason = text_value(body['reason'], 'Exposure reason', 500)
        with self.lock:
            run = self._load(run_id)
        if self._validation_run(run):
            raise WorkbenchError('Integrity validation has no model test results to expose.', 'unsupported', 409)
        self._verified_artifacts(run)
        event_id, at = uuid.uuid4().hex, timestamp()
        with self.lock, self.db.transaction():
            run = self._load(run_id)
            for source in run['source_records']:
                if source['split'] == 'test':
                    self.db.execute('INSERT INTO workspace_exposures(id,record_id,source_hash,reason,run_id,release_id,created_at) '
                                    'VALUES(%s,%s,%s,%s,%s,%s,%s)',
                                    (uuid.uuid4().hex, source['id'], source_content_hash(source), reason, run_id, run['release_id'], at))
            run['exposure_events'].append({'id': event_id, 'created_at': at, 'reason': reason})
            self._save(run)
        return {'id': event_id, 'run_id': run_id, 'release_id': run['release_id'], 'created_at': at, 'reason': reason,
                'test_exposure': {'exposed': True, 'event_count': len(run['exposure_events'])}}

    def predictions(self, run_id, split='validation'):
        if split not in ('validation', 'test'):
            raise WorkbenchError('Choose validation or test predictions.')
        contents, _ = self.artifact(run_id, f'predictions-{split}.json')
        result = json.loads(contents)
        with self.lock:
            run = self._load(run_id)
        for row in result['rows']:
            row['frozen_reference'] = {key: row[key] for key in self._reference_keys(run)}
            try:
                current = self.dataset.workbench.get(row['id'])
                row['current_record'] = {key: current.get(key) for key in ('id', 'revision', 'source_revision', 'task', 'annotation', 'review', 'source_available')}
                row['current_record']['changed'] = current['revision'] != row['revision'] or current['source_revision'] != row['source_revision']
            except WorkbenchError:
                row['current_record'] = {'id': row['id'], 'status': 'unavailable'}
        return result

    def close(self):
        self._closed = True
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=60)
            if self._thread.is_alive():
                raise RuntimeError('Training supervisor did not drain; metadata must remain open.')
        if self.runtime_owner:
            try:
                with self.lock, self.db.transaction():
                    for row in self.db.execute('SELECT id FROM workspace_runs'):
                        run = self._load(row[0])
                        if run['state'] == 'queued':
                            self._event(run, 'cancelled', 'Application closed before this queued attempt started.')
                            self._save(run)
            except psycopg.Error:
                # Drain local resources independently of database availability.
                # No successful durable transition is claimed after a lost write.
                pass
