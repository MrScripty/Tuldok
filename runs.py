"""Durable admission, one local worker, and verified immutable result custody."""
from access import authorized
import base64
import copy
from contextlib import contextmanager
import io
import tempfile
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import stat
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
from metadata import CommitOutcomeUnknown
from workbench import WorkbenchError, encode, timestamp, text_value
from pipeline import closed, digest, execution_digest, identifier, adapter_for_graph, adapter_identity_for_graph, source_content_hash, training_environment, model_aware_graph, model_contract

ACTIVE = ('queued', 'running', 'cancelling')
TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted', 'unknown')
PAYLOADS = {'metrics.json', 'test-metrics.json', 'predictions-validation.json',
            'predictions-test.json', 'checkpoint.pt'}
TEST_FILES = {'test-metrics.json', 'predictions-test.json'}
REQUEST_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$')
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_SEGMENT_BYTES = 8 * 1024 * 1024
_DOWNLOAD_PERMIT = threading.BoundedSemaphore(1)


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
        self.access = dataset.access
        self.db, self.lock = dataset.db, dataset.lock
        self.path = dataset.path / 'workspace-runs'
        self.path.mkdir(exist_ok=True)
        self._wake, self._stop = threading.Event(), threading.Event()
        self._thread = None
        self._thread_lock = threading.Lock()
        self._blocked = False
        self._external_blocked = False
        self._confirmed_external = set()
        self._closed = False
        from run_capacity import Capacity
        self._capacity = Capacity.configured()
        with self.lock:
            self.runtime_owner = self.db.claim_runtime('workspace_runs')
            if self.runtime_owner:
                self._recover()

    def _study_attempt_metadata(self, trial, limit=5):
        """Bounded saved status for experiment overviews, without byte verification.

        Full retained execution/context and artifact inspection stays in _load/get.
        This projection proves catalog and reservation identities only; callers
        must label outcomes as saved metadata and link to the full Run inspector.
        """
        from model_definitions import retained_json, natural, text
        natural(limit, 'Attempt overview limit', 1, 5)
        count = self.db.execute('SELECT count(*) FROM model_attempt_reservations WHERE trial_id=%s',
                                (trial['id'],)).fetchone()[0]
        natural(count, 'Attempt count')
        rows = self.db.execute('SELECT r.id,r.study_id,r.actor_id,r.request_sha256,r.trial_id,r.run_id,'
            'r.document AS reservation,w.request_key AS run_key,w.request_sha256 AS run_sha,w.document AS run_document '
            'FROM model_attempt_reservations r LEFT JOIN workspace_runs w ON w.id=r.run_id WHERE r.trial_id=%s '
            "ORDER BY w.document::jsonb->>'created_at' DESC,w.id DESC LIMIT %s", (trial['id'],limit)).fetchall()
        result = []
        for row in rows:
            reservation = retained_json(row['reservation'])
            run = retained_json(row['run_document'], 8*1024**2) if row['run_document'] is not None else None
            if (type(reservation) is not dict or not isinstance(run,dict) or run.get('schema_version') != 1 or run.get('mode') != 'real' or
                    run.get('id') != row['run_id'] or run.get('dataset_id') != self.db.dataset_id or
                    run.get('actor_id') != row['actor_id'] or run.get('request_sha256') != row['request_sha256'] or
                    run.get('request_sha256') != row['run_sha'] or run.get('request_key') != row['run_key'] or
                    run.get('state') not in (*ACTIVE,*TERMINAL) or row['study_id'] != trial['study_id'] or
                    any(reservation.get(key) != row[key] for key in ('id','study_id','actor_id','request_sha256','trial_id','run_id')) or
                    reservation.get('material_sha256') != trial['material']['sha256'] or
                    run.get('parent_run_id') != reservation.get('parent_run_id')):
                raise WorkbenchError('Saved attempt overview identity differs.', 'unavailable', 409)
            parent = run.get('parent_run_id')
            if parent is not None: identifier(parent, 'Retry parent Run')
            text(run.get('created_at'), 'Run creation time', 80)
            if run.get('finished_at') is not None: text(run['finished_at'], 'Run finish time', 80)
            saved_metrics = run.get('metrics')
            if saved_metrics is not None and type(saved_metrics) is not dict:
                raise WorkbenchError('Saved validation summary is malformed.', 'unavailable', 409)
            metrics = (saved_metrics or {}).get('validation', {})
            if type(metrics) is not dict:
                raise WorkbenchError('Saved validation summary is malformed.', 'unavailable', 409)
            summary = {key:metrics[key] for key in ('accuracy','loss','macro_f1','balanced_accuracy')
                       if type(metrics.get(key)) in (int,float) and math.isfinite(metrics[key])}
            result.append({'id':run['id'],'state':run['state'],'parent_run_id':parent,
                'created_at':run['created_at'],'finished_at':run.get('finished_at'),'validation':summary})
        return count,result

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
                    or (not self._external(run) and run['adapter'] != adapter_identity_for_graph(run['graph']))):
                raise ValueError('Invalid retained run identity.')
            if self._external(run):
                import recipe_contract
                import recipe_process
                # Absolute execution paths are historical evidence, not restore
                # destinations. Never rewrite a spec bound by a custody receipt.
                declared = run['spec']['cwd']
                if (type(declared) is not str or not Path(declared).is_absolute()
                        or '..' in Path(declared).parts or str(Path(declared)) != declared
                        or Path(declared).name != '.external-' + run['id']
                        or Path(declared).parent.name != 'workspace-runs'):
                    raise ValueError('Invalid retained external staging location.')
                admitted_context=self._extension_context(run) if self._extension(run) else None
                recipe_contract.validate_spec(run['material'], run['spec'], declared,context=admitted_context)
                if (run['graph'].get('recipe') != 'external_recipe'
                        or run['material']['catalog_id'] != self.db.dataset_id
                        or digest(run['material']) != run['material_sha256']
                        or run['material']['graph_execution_sha256'] != run['graph_sha256']
                        or run['outputs'] != run['material']['recipe']['outputs']
                        or run['spec']['attempt_id'] != run['id']
                        or run['spec']['request_sha256'] != run['request_sha256']
                        or run['custody_phase'] not in ('prepared', 'barrier_ready', 'go_intent', 'drained')):
                    raise ValueError('Invalid external execution identity.')
                identity = run.get('custody_identity')
                if identity is not None and (identity.get('attempt_id') != run['id']
                        or identity.get('request_sha256') != run['request_sha256']
                        or identity.get('spec_sha256') != hashlib.sha256(recipe_process.encoded(run['spec'])).hexdigest()):
                    raise ValueError('Invalid external custodian identity.')
                association=self.db.execute('SELECT t.material_sha256,r.actor_id,r.request_sha256 FROM model_attempt_reservations r '
                                            'JOIN model_trials t ON t.id=r.trial_id WHERE r.run_id=%s',
                                            (run['id'],)).fetchone()
                # A retained Study association owns this requirement: removing
                # the JSON marker must not downgrade its Run to legacy custody.
                if association is not None or 'approval_material_sha256' in run:
                    approved=run.get('approval_material_sha256')
                    if type(approved) is not str or not re.fullmatch('[a-f0-9]{64}',approved):
                        raise ValueError('Invalid composed approval identity.')
                    grant=self.db.execute('SELECT g.material_sha256,g.consumer_actor_id,g.catalog_id,'
                                          'c.run_id,c.admission_id,c.request_sha256 FROM access_execution_grants g '
                                          'JOIN access_execution_consumptions c ON c.grant_id=g.id WHERE g.id=%s',
                                          (run['approval_id'],)).fetchone()
                    if (grant is None or grant['material_sha256']!=approved or grant['consumer_actor_id']!=run['actor_id'] or
                            grant['catalog_id']!=self.db.dataset_id or grant['run_id']!=run['id'] or
                            grant['admission_id']!=run['admission_id'] or grant['request_sha256']!=run['request_sha256']):
                        raise ValueError('Composed approval differs from its retained consumption.')
                    if (association is None or association['material_sha256']!=approved or association['actor_id']!=run['actor_id'] or
                            association['request_sha256']!=run['request_sha256']):
                        raise ValueError('Composed approval differs from its retained study association.')
                    self._approved_composition(approved,run['graph'],run['material_sha256'])
            elif 'execution_kind' in run:
                raise ValueError('Unknown execution kind.')
            if model_aware_graph(run['graph']):
                owner = model_contract(run['graph'])
                context=run['evidence_context']
                if (context['adapter_sha256']!=run['runtime']['adapter_definition_sha256']
                        or context['model_definition']!=owner.model_definition(run['parameters'])
                        or context['profile']!=owner.profile(self.db.dataset_id,context['model_sha256'],run['parameters'],
                            sum(row['split']=='validation' for row in run['source_records']))):
                    raise ValueError('Retained classifier evidence context differs.')
                association=self.db.execute('SELECT r.study_id,r.trial_id,r.actor_id,r.request_sha256,t.material_sha256 '
                    'FROM model_attempt_reservations r JOIN model_trials t ON t.id=r.trial_id WHERE r.run_id=%s',(run_id,)).fetchone()
                if association is not None:
                    if (run.get('actor_id')!=association['actor_id'] or run.get('approval_material_sha256')!=association['material_sha256']
                            or context['material_sha256']!=association['material_sha256'] or run['request_sha256']!=association['request_sha256']):
                        raise ValueError('Built-in Study association differs from its authoritative receipt.')
                    self._approved_composition(association['material_sha256'],run['graph'],run['graph_sha256'])
                elif run.get('approval_material_sha256') is not None:
                    raise ValueError('Unexpected built-in Study marker.')
            return run
        except (ValueError, KeyError, TypeError):
            raise WorkbenchError('Stored run envelope is invalid; refusing to guess execution state.', 'unavailable', 409) from None

    def _in_states(self, states):
        """Route queue candidates by saved state; fully validate every selection.

        Terminal history is still validated by explicit reads and startup recovery.
        Coordination must not reopen its immutable source closures on every poll.
        """
        with self.lock:
            rows = self.db.execute(
                "SELECT id FROM workspace_runs WHERE document::jsonb->>'state' = ANY(%s)",
                (list(states),)).fetchall()
            return [self._load(row[0]) for row in rows]

    def _save(self, run):
        self.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (encode(run), run['id']))
        action = 'runs.reconcile' if self.access.identity().get('mode') == 'system' else 'runs.update'
        evidence = {'state': run['state'], 'request_sha256': run['request_sha256'], 'graph_sha256': run['graph_sha256']}
        if self._external(run):
            evidence.update(material_sha256=run['material_sha256'], approval_id=run['approval_id'],
                            custody_phase=run['custody_phase'], receipt_sha256=run.get('custody_receipt_sha256'))
        else:
            evidence['release_sha256'] = run['release_sha256']
        self.access.audit(action, run['id'], evidence)

    @staticmethod
    def _external(run):
        return run.get('execution_kind') == 'external_recipe'

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
                if self._external(run):
                    state = self._external_recovery_state(run)
                    self._external_blocked |= state == 'unknown'
                    self._event(run, state, 'External descendant cessation is unconfirmed; external execution remains fenced for this host boot.' if state == 'unknown' else
                                'Application restarted; this external attempt was not replayed. Review and approve a new attempt.')
                    self._save(run)
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
        if self._external(run):
            from candidate_packages import authorize_transitive_inputs
            authorize_transitive_inputs(self,run)
            keys = ('schema_version', 'mode', 'id', 'dataset_id', 'request_key', 'state', 'created_at',
                    'started_at', 'finished_at', 'graph', 'graph_revision', 'graph_sha256', 'parameters',
                    'attempt', 'parent_run_id', 'events', 'error', 'progress', 'node_attempts',
                    'quality_claim', 'execution_kind', 'result_kind', 'material', 'material_sha256',
                    'approval_id', 'actor_id', 'custody_phase')
            result = {key: copy.deepcopy(run[key]) for key in keys}
            if 'execution_resources' in run:
                result['execution_resources'] = copy.deepcopy(run['execution_resources'])
            if 'approval_material_sha256' in run:result['approval_material_sha256']=run['approval_material_sha256']
            association=self.db.execute('SELECT study_id,trial_id FROM model_attempt_reservations WHERE run_id=%s',(run['id'],)).fetchone()
            if association is not None:result['study_membership']=dict(association)
            result['artifacts'] = [dict(item, locked=False,
                url=f"/api/workspace/runs/{run['id']}/artifacts/{item['name']}") for item in run['artifacts']]
            return result
        hidden = {'source_records', 'release_path', 'worker', 'python', 'request_sha256', 'graph_document_sha256',
                  'worker_command', 'supervisor', 'process_phase', 'admission_id', 'evidence_context'}
        result = {key: copy.deepcopy(value) for key, value in run.items() if key not in hidden}
        association=self.db.execute('SELECT study_id,trial_id FROM model_attempt_reservations WHERE run_id=%s',(run['id'],)).fetchone()
        if association is not None or run['graph'].get('recipe')==image_training.MODEL_RECIPE:
            result['study_membership']=dict(association) if association is not None else None
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

    @authorized('inspect', 'runs.list')
    def list(self):
        with self.lock:
            rows = [self._load(row[0]) for row in self.db.execute('SELECT id FROM workspace_runs')]
        result = []
        for run in sorted(rows, key=lambda item: (item['created_at'], item['id']), reverse=True):
            public = self._public(run)
            if run['state'] == 'completed':
                try:
                    status = self._inspect_published(run)
                    if status:
                        public['artifact_status'] = status
                except WorkbenchError as error:
                    public['metrics'] = None
                    public.pop('validation_summary', None)
                    public['artifact_status'] = {'status': 'unavailable', 'message': str(error)}
            result.append(public)
        return result

    @authorized('inspect', 'runs.get')
    def get(self, run_id):
        with self.lock:
            run = self._load(run_id)
        public = self._public(run)
        if run['state'] == 'completed':
            status = self._inspect_published(run)
            if status:
                public['artifact_status'] = status
        return public

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

    @authorized('approve-execution', 'runs.approve_external', owner_only=True)
    def approve_external(self, body):
        closed(body, ('graph_id', 'graph_revision', 'expected_digest', 'consumer_actor_id'), ('ttl_seconds',))
        preflight = self.pipelines.preflight_external(body['graph_id'], body['graph_revision'])
        if preflight['material_sha256'] != body['expected_digest']:
            raise WorkbenchError('Execution material changed. Review the current preflight before approving.', 'stale', 409)
        return self.access.grant_execution(body['expected_digest'], body['consumer_actor_id'], body.get('ttl_seconds', 600))

    def _external_receipt(self, key, request_hash, actor_id):
        row = self.db.execute('SELECT id,request_sha256 FROM workspace_runs WHERE request_key=%s', (key,)).fetchone()
        if row is None:
            return None
        run = self._load(row['id'])
        if (not self._external(run) or row['request_sha256'] != request_hash or run['actor_id'] != actor_id):
            raise WorkbenchError('This submission key belongs to a different actor or request.', 'conflict', 409)
        return self._public(run)

    @authorized('inspect', 'runs.submit_external')
    def submit_external(self, body, *, _graph_guard=None):
        """The sole agent execution exception consumes an exact owner grant."""
        context = self.access.require_external_submission()
        closed(body, ('request_key', 'graph_id', 'graph_revision', 'expected_digest'), ('approval_id',))
        key, request_hash = self._request(body, tuple(body))
        with self.lock:
            receipt = self._external_receipt(key, request_hash, context.actor_id)
        if receipt:
            return self._reconcile_receipt(receipt)
        if _graph_guard is not None:
            _graph_guard(self.pipelines.get(body['graph_id']))
        self._available()
        if self._external_blocked:
            raise WorkbenchError('External descendant cessation is unknown for this host boot.', 'unavailable', 409)
        run_id = uuid.uuid4().hex
        staging = self.path / ('.external-' + run_id)
        try:
            captured = self.pipelines.capture_external(body['graph_id'], body['graph_revision'], body['expected_digest'], staging)
            with self.lock, self.db.transaction():
                self.db.on_rollback(lambda: shutil.rmtree(staging, ignore_errors=True))
                receipt = self._external_receipt(key, request_hash, context.actor_id)
                if receipt:
                    self.db.on_commit(lambda: shutil.rmtree(staging, ignore_errors=True))
                else:
                    run = self._admit_external_prepared(body, captured, run_id, staging,
                                                        wake_on_commit=False)
        except CommitOutcomeUnknown:
            # Neither delete captured files nor dispatch after ambiguous admission.
            raise
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if receipt:
            return self._reconcile_receipt(receipt)
        self._wake_external(run_id)
        return self._public(run)

    def _wake_external(self, run_id):
        with self.lock:
            self._confirmed_external.add(run_id)
        self._start()

    def _approved_composition(self,sha,graph,execution_material_sha256):
        from model_definitions import retained_json
        row=self.db.execute('SELECT document FROM workspace_recipe_materials WHERE sha256=%s',(sha,)).fetchone()
        if row is None:raise WorkbenchError('Approved composed material is unavailable.','unavailable',409)
        value=retained_json(row[0]);closed(value,('ref','material'));material=value['material']
        if (digest(material)!=sha or value['ref']!={'kind':'recipe_material','catalog_id':self.db.dataset_id,'id':sha,'sha256':sha} or
                material.get('format')!='recipe_material_v1' or material.get('catalog_id')!=self.db.dataset_id or
                material.get('recipe_id')!=graph['id'] or material.get('recipe_revision')!=graph['revision'] or
                material.get('executable_sha256')!=execution_material_sha256):
            raise WorkbenchError('Approved composed material differs from execution.','unavailable',409)
        return value

    @staticmethod
    def _extension(run):
        material=run.get('material')
        recipe=material.get('recipe') if type(material) is dict else None
        import recipe_contract
        return run.get('execution_kind')=='external_recipe' and recipe_contract.is_evidence(recipe)

    def _extension_context(self,run, *, with_captured_inputs=False):
        """Rederive the exact admitted context; never authorize from its copy."""
        import extension_evidence
        composition=self._approved_composition(run.get('approval_material_sha256'),run['graph'],run['material_sha256'])
        retained=self.pipelines._retained_extension_static(composition,with_captured_inputs=with_captured_inputs)
        static,captured=retained if with_captured_inputs else (retained,None)
        context=extension_evidence.validate_context(run.get('extension_context'),run,composition,static)
        return (context,captured) if with_captured_inputs else context

    def _verify_extension(self,directory,run):
        import extension_evidence
        context,captured=self._extension_context(run,with_captured_inputs=True)
        return extension_evidence.verify(directory,run,context,captured=captured)

    @authorized('inspect', 'runs.lookup_external_receipt')
    def lookup_external_receipt(self, request_key, request_hash):
        """Current-actor receipt read; this operation never wakes queued work."""
        if (type(request_key) is not str or not REQUEST_KEY.fullmatch(request_key) or
                type(request_hash) is not str or not re.fullmatch('[a-f0-9]{64}', request_hash)):
            raise WorkbenchError('Receipt lookup requires an exact key and SHA256.')
        context = self.access._context()
        with self.lock:
            return self._external_receipt(request_key, request_hash, context.actor_id)

    def _admit_external_prepared(self, body, captured, run_id, staging, *,
                                 check_current=True, request_hash=None, parent=None,
                                 wake_on_commit=True, approval_material_sha256=None):
        """Runs-owned insert inside an existing outer transaction; never wake early."""
        if not self.db.in_transaction:
            raise RuntimeError('Prepared admission requires an owned outer transaction.')
        context = self.access.require_external_submission()
        self._available()
        if self._external_blocked:
            raise WorkbenchError('External descendant cessation is unknown.', 'unavailable', 409)
        key, original_hash = self._request(body, tuple(body))
        request_hash = original_hash if request_hash is None else request_hash
        approved_sha = body['expected_digest'] if approval_material_sha256 is None else approval_material_sha256
        if type(approved_sha) is not str or not re.fullmatch('[a-f0-9]{64}',approved_sha):
            raise WorkbenchError('Exact approved material SHA256 is required.')
        graph = captured['graph']
        if approval_material_sha256 is not None:self._approved_composition(approved_sha,graph,captured['material_sha256'])
        spec = dict(captured['spec'], attempt_id=run_id, request_sha256=request_hash)
        import recipe_contract
        if (digest(captured['material']) != body['expected_digest'] or
                captured['material_sha256'] != body['expected_digest'] or
                captured['material']['graph_execution_sha256'] != execution_digest(graph)):
            raise WorkbenchError('Prepared execution identity differs.', 'stale', 409)
        self.db.on_rollback(lambda: shutil.rmtree(staging, ignore_errors=True))
        claim = self._capacity.claim({'material': captured['material']})
        if claim[2] > len(self._capacity.cores):
            raise WorkbenchError('Recipe CPU reservation exceeds this supervisor CPU pool.', 'unsupported', 409)
        extension_context=None
        if recipe_contract.is_evidence(captured['material']['recipe']):
            if approval_material_sha256 is None:
                raise WorkbenchError('Model evidence requires the complete Study composition grant.','unsupported',409)
            import extension_evidence
            composition=self._approved_composition(approved_sha,graph,captured['material_sha256'])
            static=self.pipelines._retained_extension_static(composition)
            extension_context=extension_evidence.context(static,composition['ref'],run_id,request_hash)
            path=staging/extension_evidence.CONTEXT_PATH
            with path.open('xb') as output:
                output.write(extension_evidence.canonical(extension_context));output.flush()
                os.fchmod(output.fileno(),0o400);os.fsync(output.fileno())
            _sync(path.parent);_sync(staging)
            spec=dict(recipe_contract.spec_for_material(captured['material'],staging,context=extension_context),
                      attempt_id=run_id,request_sha256=request_hash)
        recipe_contract.validate_spec(captured['material'], spec, str(staging),context=extension_context)
        # Captured/validated resource policy owns this bound. Check
        # after both reconciliation opportunities, before consuming
        # approval or persisting admission; failure uses normal cleanup.
        if spec.get('resource_profile') == 'captured_cpu_large_outputs_v1':
            required_bytes = 2 * spec['max_output_bytes'] + 1024**3
            try:
                available_bytes = shutil.disk_usage(self.path).free
            except OSError as error:
                raise WorkbenchError('Execution storage capacity is unavailable.', 'unavailable', 409) from error
            if available_bytes < required_bytes:
                raise WorkbenchError('Insufficient storage for declared outputs, publication copy and reserve.', 'unavailable', 409)
        if check_current and self.pipelines._get(graph['id']) != graph:
            raise WorkbenchError('Graph changed during capture.', 'stale', 409)
        if len(self._in_states(ACTIVE)) >= 8:
            raise WorkbenchError('The local queue is full (8 attempts).', 'unavailable', 409)
        grant_id = body.get('approval_id')
        if grant_id is None:
            grant_id = self.access.grant_execution(approved_sha, context.actor_id)['id']
        admission_id = self.access._consume_external_run(grant_id, approved_sha, run_id, request_hash)
        run = {'schema_version': 1, 'mode': 'real', 'execution_kind': 'external_recipe',
               'result_kind': 'external_recipe', 'id': run_id, 'dataset_id': self.db.dataset_id,
               'request_key': key, 'request_sha256': request_hash, 'actor_id': context.actor_id,
               'admission_id': admission_id, 'approval_id': grant_id,
               'state': 'queued', 'created_at': timestamp(), 'started_at': None, 'finished_at': None,
               'graph': graph, 'graph_revision': graph['revision'], 'graph_sha256': execution_digest(graph),
               'graph_document_sha256': digest(graph), 'material': captured['material'],
               'material_sha256': captured['material_sha256'], 'spec': spec,
               'outputs': captured['outputs'], 'parameters': next(node['parameters'] for node in graph['nodes'] if node['type'] == 'execute'),
               'attempt': parent['attempt']+1 if parent else 1, 'parent_run_id': parent['id'] if parent else None, 'events': [], 'artifacts': [], 'metrics': None,
               'error': None, 'worker': None, 'custody_phase': 'prepared', 'custody_identity': None,
               'custody_receipt_sha256': None, 'quality_claim': False,
               'progress': {'stage': 'queued', 'completed': None, 'total': None},
               'node_attempts': [{'node_id': node['id'], 'type': node['type'], 'state': 'pending'} for node in graph['nodes']]}
        if extension_context is not None:run['extension_context']=extension_context
        if approval_material_sha256 is not None:
            run['approval_material_sha256']=approved_sha
        self._event(run, 'queued', 'Exact owner-approved external recipe admitted.')
        self.db.execute('INSERT INTO workspace_runs(id,request_key,request_sha256,document) VALUES(%s,%s,%s,%s)',
                        (run_id, key, request_hash, encode(run)))
        self.access.audit('runs.admit_external', run_id, {'material_sha256': run['material_sha256'],
                          'approved_material_sha256':approved_sha,'approval_id': grant_id, 'request_sha256': request_hash})
        if wake_on_commit:
            self.db.on_commit(lambda: self._wake_external(run_id))
        return run

    def _external_directory(self, run):
        return self.path / ('.external-' + run['id'])

    def _external_drain_receipt(self, run):
        import recipe_process
        identity = run.get('custody_identity')
        if not identity:
            return None
        try:
            receipt = recipe_process.load_receipt(self._external_directory(run) / 'custody' / 'receipt.json', identity)
            return receipt if receipt['drained'] else None
        except (OSError, ValueError, KeyError):
            return None

    def _external_recovery_state(self, run):
        if run['custody_phase'] in ('prepared', 'barrier_ready'):
            return 'interrupted'
        if self._external_drain_receipt(run):
            return 'interrupted'
        helper = (run.get('custody_identity') or {}).get('helper')
        if helper:
            try:
                if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != helper['boot_id']:
                    return 'interrupted'
            except (OSError, KeyError):
                pass
        return 'unknown'

    @staticmethod
    def _read_regular(path, limit):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise WorkbenchError('Output is not a bounded regular file.', 'invalid', 409)
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(raw) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise WorkbenchError('Output changed while it was captured.', 'stale', 409)
            return raw

    @staticmethod
    def _progress_json(raw):
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('Duplicate diagnostic field.')
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite diagnostic.')))

    @staticmethod
    def _progress_text(value, limit, empty=False):
        return (type(value) is str and (empty or bool(value.strip())) and len(value) <= limit
                and not any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value))

    @classmethod
    def _progress_event(cls, raw):
        for line in reversed(raw.splitlines(keepends=True)):
            if len(line) > 4096 or not line.endswith(b'\n'):
                continue
            try:
                value = cls._progress_json(line)
                if type(value) is not dict or set(value) != {'format', 'stage', 'completed', 'total', 'metrics'}:
                    continue
                if value['format'] != 'tuldok_progress_v1' or type(value['stage']) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value['stage']):
                    continue
                if not (type(value['completed']) is int and type(value['total']) is int
                        and 0 <= value['completed'] <= value['total'] <= 1000000):
                    continue
                metrics = value['metrics']
                if type(metrics) is not dict or len(metrics) > 8 or any(
                        not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', name)
                        or type(number) not in (int, float) or not math.isfinite(number)
                        for name, number in metrics.items()):
                    continue
                return value
            except (ValueError, TypeError, OverflowError, RecursionError):
                continue
        return None

    @staticmethod
    def _diagnostic_directory(path):
        """Resolve every owned-directory component without following symlinks."""
        descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in Path(path).absolute().parts[1:]:
                following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = following
            if os.fstat(descriptor).st_uid != os.getuid():
                raise ValueError('Diagnostic directory owner differs.')
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    @staticmethod
    def _diagnostic_read(directory, name, limit, *, tail=False):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_size > limit:
                raise ValueError('Invalid diagnostic file.')
            start = max(0, before.st_size - 8192) if tail else 0
            raw = os.pread(descriptor, before.st_size - start, start)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if ((before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
                    or len(raw) != before.st_size - start or after.st_size < before.st_size
                    or after.st_size > limit or (not tail and
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns))):
                raise ValueError('Diagnostic changed during observation.')
            return raw, start, before.st_size
        finally:
            os.close(descriptor)

    def _external_result_summary(self, run):
        if run['state'] != 'completed':
            return None
        rules = [rule for rule in run['outputs'] if rule['role'] == 'result_summary']
        if not rules:
            return None
        try:
            if len(rules) != 1 or rules[0]['max_bytes'] > 65536:
                raise ValueError('Invalid result summary declaration.')
            inventory = (self._external_inventory(run) if self._large_outputs(run)
                         else self._verify_external_artifacts(run))
            item = next(item for item in inventory if item['name'] == rules[0]['path'] and item['role'] == 'result_summary')
            raw = self._external_bytes(run, item)
            if len(raw) > 65536:
                raise ValueError('Result summary is too large.')
            value = self._progress_json(raw)
            if type(value) is not dict or not {'format','title','metrics','scope'} <= set(value) or set(value) - {'format','title','metrics','scope','checkpoint'}:
                raise ValueError('Invalid result summary fields.')
            if value['format'] != 'tuldok_result_summary_v1' or not self._progress_text(value['title'], 120):
                raise ValueError('Invalid result summary title.')
            if type(value['metrics']) is not list or len(value['metrics']) > 24:
                raise ValueError('Invalid metrics.')
            names = set()
            for metric in value['metrics']:
                if (type(metric) is not dict or set(metric) != {'name','value','unit'}
                        or not self._progress_text(metric['name'], 64) or metric['name'] in names
                        or not self._progress_text(metric['unit'], 24, empty=True)
                        or type(metric['value']) not in (int, float) or not math.isfinite(metric['value'])):
                    raise ValueError('Invalid metric.')
                names.add(metric['name'])
            if type(value['scope']) is not list or len(value['scope']) > 8 or not all(self._progress_text(label, 160) for label in value['scope']):
                raise ValueError('Invalid scope.')
            if 'checkpoint' in value and not any(item['name'] == value['checkpoint'] and item['role'] == 'checkpoint' for item in inventory):
                raise ValueError('Checkpoint is not a verified declared output.')
            if 'checkpoint' in value:
                checkpoint = next(entry for entry in inventory if entry['name'] == value['checkpoint'])
                directory = self._diagnostic_directory(self.path / run['id'])
                try:
                    self._copy_verified(directory, checkpoint['name'], checkpoint)
                finally:
                    os.close(directory)
            return {'status':'hash_verified','artifact_name':item['name'], 'sha256':item['sha256'], 'summary':value}
        except (OSError, ValueError, TypeError, KeyError, StopIteration, OverflowError, RecursionError):
            return {'status':'unavailable'}

    @authorized('inspect', 'runs.external_progress')
    def external_progress(self, run_id):
        import recipe_process
        with self.lock:
            run = self._load(run_id)
        if not self._external(run):
            raise WorkbenchError('Progress diagnostics require an external Run.', 'unsupported', 400)
        from candidate_packages import authorize_transitive_inputs
        authorize_transitive_inputs(self,run)
        result = {'schema_version':1, 'run_id':run['id'], 'state':run['state'],
                  'custody_phase':run['custody_phase'], 'evidence':'unavailable',
                  'streams':{'stdout':None,'stderr':None}, 'progress':None,
                  'result':self._external_result_summary(run)}
        directory = None
        try:
            directory = self._diagnostic_directory(self._external_directory(run) / 'custody')
            terminal = run['state'] in TERMINAL and run['state'] != 'unknown'
            receipt = None
            if terminal:
                raw, _, _ = self._diagnostic_read(directory, 'receipt.json', 16384)
                receipt = recipe_process.validate_receipt(raw, run['custody_identity'])
                if not receipt['drained']:
                    raise ValueError('Diagnostic custody has not drained.')
                if run['state'] == 'completed':
                    published = self._read_regular(self.path / run['id'] / 'custody-receipt.json', 16384)
                    if hashlib.sha256(published).hexdigest() != run['custody_receipt_sha256'] or self._progress_json(published) != receipt:
                        raise ValueError('Published custody differs.')
            for name in ('stdout','stderr'):
                raw, start, size = self._diagnostic_read(directory, name+'.log', recipe_process.STREAM_LIMIT, tail=not terminal)
                if receipt and (len(raw) != receipt['streams'][name]['bytes'] or hashlib.sha256(raw).hexdigest() != receipt['streams'][name]['sha256']):
                    raise ValueError('Stream receipt differs.')
                if terminal:
                    start = max(0, len(raw)-8192)
                    raw = raw[start:]
                if name == 'stdout':
                    complete = raw.split(b'\n', 1)[1] if start and b'\n' in raw else b'' if start else raw
                    result['progress'] = self._progress_event(complete)
                text = raw.decode('utf-8', errors='replace')
                text = ''.join(c if c in '\n\t' or (ord(c) >= 32 and not 127 <= ord(c) <= 159) else '\ufffd' for c in text)
                result['streams'][name] = {'available_bytes':size,'start_byte':start,'text':text,'truncated':start > 0}
            result['evidence'] = 'custody_verified' if receipt else 'live_unverified'
        except FileNotFoundError:
            result['evidence'] = 'pending' if run['state'] == 'queued' or run['custody_phase'] == 'prepared' and run['state'] in ACTIVE else 'unavailable'
            result['streams'] = {'stdout':None,'stderr':None}
            result['progress'] = None
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            result['streams'] = {'stdout':None,'stderr':None}
            result['progress'] = None
        finally:
            if directory is not None:
                os.close(directory)
        if len(json.dumps(result).encode()) > 192 * 1024:
            raise WorkbenchError('Progress response exceeds its encoded bound.', 'unavailable', 409)
        return result

    def _publish_external(self, run, receipt):
        import recipe_contract
        source = Path(run['spec']['output_dir'])
        checked = recipe_contract.verify_outputs(source, run['outputs'], run['spec']['max_output_bytes'])
        destination = self.path / run['id']
        destination.mkdir(mode=0o700)
        artifacts = []
        total = 0
        source_descriptor = self._diagnostic_directory(source)
        try:
            if shutil.disk_usage(self.path).free < sum(item['bytes'] for item in checked) + 512*1024*1024:
                raise WorkbenchError('Insufficient space for artifact publication.', 'unavailable', 409)
            for item in checked:
                total += item['bytes']
                if total > run['spec']['max_output_bytes']:
                    raise WorkbenchError('Recipe outputs exceed their admitted bound.', 'invalid', 409)
                try:
                    with (destination / item['path']).open('xb') as output:
                        self._copy_verified(source_descriptor, item['path'], item, output)
                        output.flush()
                        os.fsync(output.fileno())
                except (OSError, ValueError) as error:
                    raise WorkbenchError('Recipe output changed or could not be published.', 'unavailable', 409) from error
                artifacts.append({'name':item['path'],'role':item['role'],'bytes':item['bytes'],
                                  'sha256':item['sha256'],'media_type':item.get('media_type','application/octet-stream')})
        finally:
            os.close(source_descriptor)
        if self._extension(run):
            import extension_evidence
            from candidate_packages import authorize_material_inputs
            authorize_material_inputs(self,run['material'])
            self._verify_extension(destination,dict(run,artifacts=artifacts))
        receipt_raw = encode(receipt).encode()
        manifest = {'schema_version': 1, 'run_id': run['id'], 'material_sha256': run['material_sha256'],
                    'request_sha256': run['request_sha256'], 'custody_receipt_sha256': hashlib.sha256(receipt_raw).hexdigest(),
                    'artifacts': artifacts}
        for name, raw in (('custody-receipt.json', receipt_raw), ('artifact-manifest.json', encode(manifest).encode())):
            with (destination / name).open('xb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
        _sync(destination)
        _sync(self.path)
        return artifacts, manifest['custody_receipt_sha256']

    def _execute_external(self, run_id):
        import recipe_process
        import recipe_contract
        handle = None
        run = None
        receipt = None
        try:
            with self.lock, self.db.transaction():
                run = self._load(run_id)
                self.access.require_job('runs', run_id, run['admission_id'], run['request_sha256'])
                if run['state'] != 'queued' or self._blocked or self._external_blocked or self._stop.is_set():
                    return
                if run['spec']['cwd'] != str(self._external_directory(run)):
                    raise WorkbenchError('Restored execution paths cannot be dispatched. Approve a new attempt.', 'stale', 409)
                self._event(run, 'running', 'Starting the approved custodian; recipe waits behind its launch barrier.')
                run['started_at'] = timestamp()
                self._save(run)
            if recipe_contract.recipe_host_identity(run['material']['recipe']) != run['material']['host_files']:
                raise WorkbenchError('Recipe host changed after approval. Reopen and review a new attempt.', 'stale', 409)
            handle = recipe_process.launch(run['spec'], self._external_directory(run) / 'custody')
            preparation_seconds = recipe_process.preparation_seconds(run['spec'])
            ready_deadline = time.monotonic() + preparation_seconds + 2
            custody_deadline = ready_deadline
            cancel_deadline = None
            terminal = False
            while not terminal:
                for event in handle.poll():
                    if event['type'] == 'ready':
                        with self.lock, self.db.transaction():
                            run = self._load(run_id)
                            run['custody_identity'] = copy.deepcopy(handle.expected_identity)
                            run['worker'] = copy.deepcopy(handle.expected_identity['helper'])
                            run['custody_phase'] = 'barrier_ready'
                            self._save(run)
                        with self.lock, self.db.transaction():
                            run = self._load(run_id)
                            if run['state'] == 'cancelling' or self._stop.is_set() or self._blocked or self._external_blocked:
                                handle.cancel('cancelled')
                                continue
                            run['custody_phase'] = 'go_intent'
                            run['progress']['stage'] = 'execute'
                            self._save(run)
                        # No GO is sent when either transaction acknowledgement is unknown.
                        handle.go(handle.expected_identity['helper'])
                        # Runtime inventory is verified cancellably after GO,
                        # before child wall time starts, under its own bound.
                        recheck_seconds = recipe_process.verification_seconds(run['spec'])
                        custody_deadline = (time.monotonic() + recheck_seconds + run['spec']['wall_seconds']
                                            + recipe_process.CLEANUP_SECONDS + 5)
                    elif event['type'] == 'verifying':
                        with self.lock, self.db.transaction():
                            run = self._load(run_id)
                            run['progress']['stage'] = 'verify_runtime'
                            self._save(run)
                    elif event['type'] == 'started':
                        with self.lock, self.db.transaction():
                            run = self._load(run_id)
                            run['progress']['stage'] = 'execute'
                            self._save(run)
                    elif event['type'] in ('terminal', 'lost'):
                        terminal = True
                if terminal:
                    break
                if self._stop.is_set():
                    handle.cancel('cancelled')
                    cancel_deadline = cancel_deadline or time.monotonic() + 12
                with self.lock:
                    current = self._load(run_id)
                    if current['state'] == 'cancelling':
                        handle.cancel('cancelled')
                        cancel_deadline = cancel_deadline or time.monotonic() + 12
                if handle.ready is None and time.monotonic() > ready_deadline:
                    handle.cancel('cancelled')
                if time.monotonic() > min(custody_deadline, cancel_deadline or custody_deadline):
                    raise WorkbenchError('Custodian deadline elapsed without confirmed drainage.', 'unknown', 409)
                time.sleep(.03)
            with self.lock:
                run = self._load(run_id)
            receipt = self._external_drain_receipt(run)
            if receipt is None:
                raise WorkbenchError('External descendant drainage could not be established.', 'unknown', 409)
            with self.lock, self.db.transaction():
                run = self._load(run_id)
                run['custody_phase'] = 'drained'
                cancelled = run['state'] == 'cancelling' or self._stop.is_set() or receipt['outcome'] == 'cancelled'
                if not cancelled and receipt['outcome'] == 'completed':
                    artifacts, receipt_hash = self._publish_external(run, receipt)
                    run['artifacts'], run['custody_receipt_sha256'] = artifacts, receipt_hash
                    self._event(run, 'completed', 'All descendants drained; declared outputs verified and retained.')
                    for node in run['node_attempts']:
                        node['state'] = 'completed'
                else:
                    self._event(run, 'cancelled' if cancelled else 'failed', 'External process drained without successful publication.')
                self._save(run)
        finally:
            if handle is not None:
                # Independent of database availability. EOF asks the pinned helper
                # to stop and drain; missing evidence remains unknown on reopen.
                handle.close_control()

    def _external_inventory(self, run):
        import recipe_process
        import recipe_contract
        from candidate_packages import authorize_transitive_inputs
        authorize_transitive_inputs(self,run)
        directory = self.path / run['id']
        descriptor = None
        try:
            descriptor = self._diagnostic_directory(directory)
            if run['state'] != 'completed':
                raise ValueError('Only completed Runs publish artifacts.')
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError('Invalid artifact directory.')
            definition = recipe_contract.decode_definition(encode(run['material']['recipe']).encode())
            allowed = {item['path']: item for item in definition['outputs']}
            seen, total = set(), 0
            for item in run['artifacts']:
                if (set(item) != {'name', 'role', 'bytes', 'sha256', 'media_type'}
                        or item['name'] not in allowed or item['name'] in seen):
                    raise ValueError('Invalid artifact inventory.')
                rule = allowed[item['name']]
                if (item['role'] != rule['role'] or type(item['bytes']) is not int
                        or not 0 <= item['bytes'] <= rule['max_bytes']
                        or item['media_type'] != 'application/octet-stream'
                        or not isinstance(item['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', item['sha256'])):
                    raise ValueError('Artifact differs from its approved contract.')
                seen.add(item['name'])
                total += item['bytes']
            if (any(rule['required'] and name not in seen for name, rule in allowed.items())
                    or total > definition['resources']['max_output_bytes']):
                raise ValueError('Incomplete or excessive artifact inventory.')
            receipt_raw, _, _ = self._diagnostic_read(descriptor, 'custody-receipt.json', 16384)
            if hashlib.sha256(receipt_raw).hexdigest() != run['custody_receipt_sha256']:
                raise ValueError('Custody receipt changed.')
            receipt = recipe_process.validate_receipt(receipt_raw, run['custody_identity'])
            if not receipt['drained'] or receipt['outcome'] != 'completed':
                raise ValueError('Custody did not complete.')
            manifest_raw, _, _ = self._diagnostic_read(descriptor, 'artifact-manifest.json', 65536)
            manifest = self._progress_json(manifest_raw)
            expected = {'schema_version': 1, 'run_id': run['id'], 'material_sha256': run['material_sha256'],
                        'request_sha256': run['request_sha256'], 'custody_receipt_sha256': run['custody_receipt_sha256'],
                        'artifacts': run['artifacts']}
            if manifest != expected:
                raise ValueError('Artifact manifest changed.')
            if set(os.listdir(descriptor)) != {item['name'] for item in run['artifacts']} | {'artifact-manifest.json','custody-receipt.json'}:
                raise ValueError('Published directory inventory differs.')
            for item in run['artifacts']:
                info = os.stat(item['name'], dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != item['bytes']:
                    raise ValueError('Artifact inventory changed.')
            if self._extension(run):
                import extension_evidence
                # All download/segment/capture/summary accessors share this
                # structural gate and current transitive input authorization.
                for item in run['artifacts']:self._copy_verified(descriptor,item['name'],item)
                self._verify_extension(directory,run)
            return run['artifacts']
        except (OSError, ValueError, KeyError, TypeError, RecursionError) as error:
            raise WorkbenchError('Retained external result cannot be verified.', 'unavailable', 409) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _verify_external_artifacts(self, run):
        inventory = self._external_inventory(run)
        directory = None
        try:
            directory = self._diagnostic_directory(self.path / run['id'])
            for item in inventory:
                self._copy_verified(directory, item['name'], item)
            return inventory
        except (OSError, ValueError) as error:
            raise WorkbenchError('Retained external result cannot be verified.', 'unavailable', 409) from error
        finally:
            if directory is not None:
                os.close(directory)

    @staticmethod
    def _large_outputs(run):
        return (run.get('execution_kind') == 'external_recipe' and
                run['material']['recipe']['resources'].get('profile') == 'captured_cpu_large_outputs_v1')

    def _inspect_published(self, run):
        if self._external(run) and self._large_outputs(run):
            self._external_inventory(run)
            return {'status':'receipt_verified', 'payloads':'not_checked'}
        self._verified_artifacts(run)
        return None

    @staticmethod
    def _copy_verified(directory, name, item, output=None):
        """Hash one exact regular payload, optionally copying with bounded memory."""
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or before.st_uid != os.getuid() or before.st_size != item['bytes']):
                raise ValueError('Artifact is not the declared regular file.')
            total = 0
            measured = hashlib.sha256()
            while True:
                raw = os.read(fd, min(65536, item['bytes'] - total + 1))
                if not raw:
                    break
                total += len(raw)
                if total > item['bytes']:
                    raise ValueError('Artifact grew during verification.')
                measured.update(raw)
                if output is not None:
                    if output.write(raw) != len(raw):
                        raise OSError('Artifact copy made incomplete progress.')
            after = os.fstat(fd)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (total != item['bytes'] or measured.hexdigest() != item['sha256']
                    or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) !=
                       (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                    or (before.st_dev,before.st_ino) != (current.st_dev,current.st_ino)):
                raise ValueError('Artifact changed during verification.')
        finally:
            os.close(fd)

    def _selected_external(self, run, name, *, max_bytes=None):
        inventory = self._external_inventory(run)
        item = next((item for item in inventory if item['name'] == name), None)
        if item is None:
            raise WorkbenchError('Unknown external artifact.', 'unavailable', 404)
        if max_bytes is not None and item['bytes'] > max_bytes:
            raise WorkbenchError('Artifact exceeds the declared input byte bound.', 'invalid', 409)
        if not self._large_outputs(run):
            self._verify_external_artifacts(run)
        return item

    def _external_bytes(self, run, item):
        directory = None
        try:
            directory = self._diagnostic_directory(self.path / run['id'])
            output = io.BytesIO()
            self._copy_verified(directory, item['name'], item, output)
            return output.getvalue()
        except (OSError, ValueError) as error:
            raise WorkbenchError('Selected artifact cannot be verified.', 'unavailable', 409) from error
        finally:
            if directory is not None:
                os.close(directory)

    @authorized('inspect', 'runs.input_candidates')
    def input_candidates(self):
        with self.lock:
            rows = self.db.execute('SELECT id FROM workspace_runs ORDER BY id').fetchall()
            completed = []
            for row in rows:
                run = self._load(row[0])
                if self._external(run) and run['state'] == 'completed':
                    completed.append(run)
            completed = sorted(completed, key=lambda run:(run['created_at'],run['id']), reverse=True)[:100]
        result = []
        for run in completed:
            entry = {'run_id':run['id'], 'state':'completed', 'status':'receipt_verified', 'reason':None, 'artifacts':[]}
            try:
                inventory = self._external_inventory(run)
                entry['artifacts'] = [{'artifact_name':item['name'],'role':item['role'],'bytes':item['bytes'],
                                       'sha256':item['sha256'],'status':'receipt_verified'}
                                      for item in inventory if item['bytes'] <= 40*1024*1024]
            except WorkbenchError:
                entry.update(status='unavailable', reason='Completed artifact inventory cannot be verified.')
            result.append(entry)
        return {'runs':result}

    @authorized('inspect', 'runs.open_artifact')
    def open_artifact(self, run_id, name):
        return self._open_artifact(run_id, name)

    @contextmanager
    def _open_artifact(self, run_id, name):
        # Recheck at context entry: callers cannot retain an unentered context
        # and use it after their credential has been revoked or unbound.
        self.access.require('inspect', 'runs.open_artifact', run_id)
        with self.lock:
            run = self._load(run_id)
        if not self._external(run):
            raw, media_type = self.artifact(run_id, name)
            with io.BytesIO(raw) as stream:
                yield stream, {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'media_type':media_type}
            return
        item = self._selected_external(run, name)
        if not _DOWNLOAD_PERMIT.acquire(blocking=False):
            raise WorkbenchError('Another artifact download is in progress.', 'unavailable', 503)
        directory = None
        try:
            if shutil.disk_usage(self.path).free < item['bytes'] + 512*1024*1024:
                raise WorkbenchError('Insufficient free space for a verified download.', 'unavailable', 409)
            directory = self._diagnostic_directory(self.path / run['id'])
            with tempfile.TemporaryFile(dir=self.path, mode='w+b') as stream:
                try:
                    self._copy_verified(directory, name, item, stream)
                    stream.flush()
                    stream.seek(0)
                except (OSError, ValueError) as error:
                    raise WorkbenchError('Selected artifact cannot be verified.', 'unavailable', 409) from error
                yield stream, {key:item[key] for key in ('bytes','sha256','media_type')}
        except OSError as error:
            raise WorkbenchError('Verified download storage is unavailable.', 'unavailable', 409) from error
        finally:
            if directory is not None:
                os.close(directory)
            _DOWNLOAD_PERMIT.release()

    @authorized('execute', 'runs.submit', owner_only=True)
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
            if self._external(receipt):
                with self.lock:
                    self._confirmed_external.add(receipt['id'])
            self._start()
        return receipt

    def _admit(self, key, request_hash, graph, validation, release, parent=None, *, run_id=None, composition=None):
        queued = len(self._in_states(ACTIVE))
        if queued >= 8:
            raise WorkbenchError('The local queue is full (8 attempts). Wait or cancel a queued attempt.', 'unavailable', 409)
        run_id = run_id or uuid.uuid4().hex
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
        if model_aware_graph(graph):
            owner = model_contract(graph)
            model_sha = composition['ref']['sha256'] if composition else None
            definition = owner.model_definition(parameters)
            model_identity = composition['material']['model']['sha256'] if composition else digest(definition)
            run['evidence_context'] = {'model_sha256':model_identity,
                'material_sha256':model_sha or digest({'graph':graph,'runtime':validation['runtime'],'release':release['sha256']}),
                'adapter_sha256':validation['runtime']['adapter_definition_sha256'],
                'model_definition':definition,
                'profile':owner.profile(self.db.dataset_id,model_identity,parameters,
                    sum(row['split']=='validation' for row in release['manifest']['records']))}
            run['evidence_context']['metric_definitions']=owner.metric_definitions(run['evidence_context'],release['manifest'])
            if composition:
                run.update(actor_id=self.access._context().actor_id, approval_material_sha256=model_sha)
        if self._validation_run(run):
            run.update(result_kind='release_validation', validation_summary=copy.deepcopy(release['validation_summary']))
        recipe = graph.get('recipe', 'image_classification')
        effects = {'pipeline.inspect_release': [release['id']], 'dataset_releases.locate': [release['id']],
                   'pipeline.probe': [recipe], 'pipeline.probe_native': [recipe],
                   'pipeline.definition_identity': [recipe], 'pipeline.exposures': [None],
                   'runs.update': [run_id]}
        run['admission_id'] = self.access.admit_job('runs', run_id, request_hash, effects)
        self.access.audit('runs.admit', run_id, {'request_sha256': request_hash,
                         'graph_sha256': run['graph_sha256'], 'release_sha256': run['release_sha256']})
        self._event(run, 'queued', 'Frozen integrity attempt admitted.' if self._validation_run(run) else
                    'Real CPU attempt admitted. Training starts from scratch; no model download.')
        self.db.execute('INSERT INTO workspace_runs(id,request_key,request_sha256,document) VALUES(%s,%s,%s,%s)',
                        (run_id, key, request_hash, encode(run)))
        return run

    @authorized('execute', 'runs.retry', owner_only=True)
    def retry(self, run_id, body):
        closed(body, ('request_key',))
        key, request_hash = self._request(dict(body, parent_run_id=run_id), ('request_key', 'parent_run_id'))
        with self.lock:
            receipt = self._receipt(key, request_hash)
            if not receipt:
                parent = self._load(run_id)
        if receipt:
            return self._reconcile_receipt(receipt)
        if self._external(parent):
            raise WorkbenchError('External retries require a fresh material preflight and execution approval.', 'unsupported', 409)
        self._available()
        if parent['state'] not in ('failed', 'cancelled', 'interrupted'):
            raise WorkbenchError('Only failed, cancelled or interrupted attempts can restart; unknown work requires reconciliation.', 'conflict', 409)
        validation = self.pipelines.validate_graph(parent['graph'])
        if not validation['valid']:
            first = validation['errors'][0]
            raise WorkbenchError(first['message'], first['code'], 409)
        release = self.pipelines.inspect_release(parent['release_id'], private=True, recipe=parent['graph'].get('recipe', 'image_classification'))
        with self.lock, self.db.transaction():
            receipt = self._receipt(key, request_hash)
            if not receipt:
                run = self._admit(key, request_hash, parent['graph'], validation, release, parent)
        if receipt:
            return self._reconcile_receipt(receipt)
        self._start()
        return self._public(run)

    @authorized('cancel', 'runs.cancel')
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
            if self._closed or self._stop.is_set():
                return
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name='workspace-runs', daemon=True)
                self._thread.start()
        self._wake.set()

    def _loop(self):
        from concurrent.futures import ThreadPoolExecutor
        from run_capacity import available_memory, MAX_ATTEMPTS
        # Only this coordinator owns futures/reservations. Each attempt retains
        # its existing independent process custodian and exact job context.
        with ThreadPoolExecutor(max_workers=MAX_ATTEMPTS, thread_name_prefix='workspace-attempt') as executor:
            active = {}
            try:
                while not self._stop.is_set():
                    for run_id, (future, _, _) in list(active.items()):
                        if future.done():
                            future.result()
                            del active[run_id]
                    with self.lock:
                        blocked = self._blocked or self._external_blocked or not self.runtime_owner
                    if blocked:
                        self._wake.wait(.25)
                        self._wake.clear()
                        continue
                    with self.lock:
                        queued = self._in_states(('queued',))
                        queued = sorted((run for run in queued if run['state'] == 'queued' and run['id'] not in active
                                         and (not self._external(run) or run['id'] in self._confirmed_external)),
                                        key=lambda run: (run['created_at'], run['id']))
                    try:
                        headroom = available_memory()
                    except (OSError, ValueError, KeyError, StopIteration):
                        headroom = 0
                    for run in queued:
                        claim = self._capacity.claim(run)
                        with self.lock:
                            blocked = self._blocked or self._external_blocked
                        if self._stop.is_set() or blocked:
                            break
                        if self._capacity.admits(claim, [item[1] for item in active.values()], headroom):
                            used = {cpu for _, _, cpus in active.values() for cpu in cpus}
                            cpus = tuple(cpu for cpu in self._capacity.cores if cpu not in used)[:claim[2]]
                            active[run['id']] = (executor.submit(self._run_attempt, run, cpus, claim), claim, cpus)
                    # With no pending work only admission/stop can change the queue.
                    # Queued resource waits still retry when headroom changes.
                    self._wake.wait(.05 if active else .25 if queued else None)
                    self._wake.clear()
            finally:
                # On coordinator/storage failure, active attempts observe stop
                # and drain before executor shutdown releases ownership.
                self._stop.set()

    def _run_attempt(self, admitted, cpus, claim):
        affinity = os.sched_getaffinity(0)
        try:
            # Linux affinity belongs to this executor thread. Children inherit it;
            # other attempts and the HTTP/coordinator threads remain independent.
            os.sched_setaffinity(0, cpus)
            with self.access._job('runs', admitted['id'], admitted.get('admission_id'), admitted['request_sha256']):
                with self.lock, self.db.transaction():
                    current = self._load(admitted['id'])
                    # Executor submission is provisional. This transaction is
                    # the dispatch decision shared with sibling unknown fences.
                    if current['state'] != 'queued' or self._blocked or self._external_blocked or self._stop.is_set():
                        return
                    current['execution_resources'] = {'device': claim[0], 'memory_reservation_bytes': claim[1],
                        'cpu_affinity': list(cpus), 'host_memory_reserve_bytes': self._capacity.reserve_bytes}
                    self._save(current)
                self._execute(admitted['id'])
        except Exception:
            try:
                with self.access._reconcile(), self.lock, self.db.transaction():
                    run = self._load(admitted['id'])
                    if run['state'] in ACTIVE:
                        run['error'] = {'code': 'failed', 'message': 'Run supervisor could not complete this attempt.'}
                        state = self._external_recovery_state(run) if self._external(run) else 'failed'
                        self._external_blocked |= state == 'unknown' and self._external(run)
                        self._event(run, state, run['error']['message'])
                        self._save(run)
            except psycopg.Error:
                self._stop.set()
        finally:
            os.sched_setaffinity(0, affinity)
            self._wake.set()

    def _execute(self, run_id):
        with self.lock:
            selected = self._load(run_id)
        if self._external(selected):
            return self._execute_external(run_id)
        process = owner = None
        with self.lock, self.db.transaction():
            run = self._load(run_id)
            self.access.require_job('runs', run_id, run.get('admission_id'), run['request_sha256'])
            if run['state'] != 'queued' or self._blocked or self._external_blocked or self._stop.is_set():
                return
            self._event(run, 'running', 'Verifying frozen release and adapter before starting the CPU worker.')
            run['started_at'] = timestamp()
            run['progress']['stage'] = 'validate'
            self._save(run)
        try:
            if self._validation_run(run):
                self._execute_validation(run)
                return
            release = self.pipelines.inspect_release(run['release_id'], private=True, recipe=run['graph'].get('recipe', 'image_classification'))
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
            if run['graph'].get('recipe') == image_training.MODEL_RECIPE:
                job.update(schema_version=2,evidence_context=run['evidence_context'])
            elif model_aware_graph(run['graph']):
                from one_fit_evidence import job_for_run
                job.update(job_for_run(run, output), parent_pid=os.getpid(), release_path=release['path'])
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
                if self._blocked or self._external_blocked:
                    self._event(current, 'interrupted', 'Sibling custody became unknown before worker creation.')
                    self._save(current)
                    return
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
            if model_aware_graph(run['graph']):
                # Only the owned pinned CPU subprocess may load retained state.
                process.stdout.close()
                command = [run['python'], str(worker_path), '--verify-evidence', str(job_path)]
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                           start_new_session=True, env=training_environment())
                owner = process_identity(process.pid)
                if owner is None:
                    process.wait(timeout=10)
                    raise WorkbenchError('Checkpoint verifier exited before custody was recorded.', 'failed', 409)
                with self.lock,self.db.transaction():
                    current=self._load(run_id);current['worker']=owner;current['worker_command']=command;self._save(current)
                until=time.monotonic()+90
                while process.poll() is None:
                    with self.lock: current=self._load(run_id)
                    if current['state']=='cancelling' or self._stop.is_set():
                        self._drain(process,owner);self._finish(run_id,'cancelled','Checkpoint verification cancelled; no outputs published.');return
                    if time.monotonic()>until:
                        self._drain(process,owner);raise WorkbenchError('Checkpoint verifier exceeded its90-second bound.','failed',409)
                    self._wake.wait(.1);self._wake.clear()
                process.wait()
                try:os.killpg(process.pid,0)
                except ProcessLookupError:pass
                else:raise WorkbenchError('Checkpoint verifier cessation is unknown.','unknown',409)
                if process.returncode:
                    raise WorkbenchError('Retained checkpoints failed independent fixed-probe reconstruction.','failed',409)
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
                    try:
                        with self.lock:
                            self._blocked = True
                            with self.db.transaction():
                                current = self._load(run_id)
                                current['error'] = {'code': 'unknown', 'message': 'Worker cessation could not be confirmed.'}
                                self._event(current, 'unknown', current['error']['message'])
                                self._save(current)
                    except BaseException:
                        # CatalogLock acquisition can itself fail after storage
                        # loss. Stop dispatch even when no durable fence is possible.
                        self._stop.set()
                        raise
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
        runtime = self.pipelines.probe(run['graph']['recipe'])
        if runtime != run['runtime']:
            raise WorkbenchError('Integrity definition changed after admission.', 'stale', 409)
        release = self.pipelines.inspect_release(run['release_id'], private=True, recipe=run['graph'].get('recipe', 'image_classification'))
        if release['validation_summary'] != run['validation_summary']:
            raise WorkbenchError('Frozen integrity evidence changed after admission.', 'stale', 409)
        # Validate the definition again after reading, before publishing its result.
        if self.pipelines.probe(run['graph']['recipe']) != runtime:
            raise WorkbenchError('Integrity definition changed during execution.', 'stale', 409)
        stage = self.path / ('.staging-' + run_id)
        stage.mkdir(mode=0o700)
        output = stage / 'output'
        output.mkdir(mode=0o700)
        release_validation.write_report(output, self._identity(run), release['validation_summary'], run['graph']['recipe'])
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
            self._event(current, 'completed', 'Verified frozen integrity report published; no training ran.')
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
        if run['graph'].get('recipe') == image_training.MODEL_RECIPE:
            import model_evidence
            return model_evidence.payload_names(run['parameters']['epochs'])
        if model_aware_graph(run['graph']):
            from one_fit_evidence import payload_names
            return payload_names()
        return PAYLOADS if adapter_for_graph(run['graph']) is image_training else PAYLOADS - {'checkpoint.pt'} | {'model.json'}

    def _reference_keys(self, run):
        adapter = adapter_for_graph(run['graph'])
        return adapter.REFERENCE_KEYS if adapter is not image_training else (
            'id', 'revision', 'source_revision', 'source_sha256', 'asset_sha256', 'exported_pixel_sha256')

    def _verify_directory(self, run, directory):
        if self._validation_run(run):
            return release_validation.verify_directory(directory, self._identity(run), run['validation_summary'], run['graph']['recipe'])
        if directory.is_symlink() or not directory.is_dir():
            raise WorkbenchError('Published artifact directory is unavailable.', 'unavailable', 409)
        payload_names = self._payloads(run)
        one_fit = model_aware_graph(run['graph']) and adapter_for_graph(run['graph']) is not image_training
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
            if len(artifacts) != len(payload_names) or {item['name'] for item in artifacts} != payload_names:
                raise ValueError('Artifact inventory mismatch.')
            payloads = {}
            for item in artifacts:
                closed(item, ('name', 'sha256', 'bytes', 'media_type', 'split'))
                expected_split = 'test' if item['name'] in TEST_FILES else 'validation' if item['name'] in ('metrics.json', 'predictions-validation.json') or item['name'].startswith('probes-epoch-') else None
                if one_fit and item['name'] in ('probe.json', 'probe-inputs.json', 'probes-fit-0001.json', 'observations.json'):
                    expected_split = 'validation'
                expected_media = 'application/json' if item['name'].endswith('.json') else 'application/octet-stream'
                if item['split'] != expected_split or item['media_type'] != expected_media:
                    raise ValueError('Artifact media type or split differs from its declared role.')
                contents = (directory / item['name']).read_bytes()
                if type(item['bytes']) is not int or len(contents) != item['bytes'] or hashlib.sha256(contents).hexdigest() != item['sha256']:
                    raise ValueError('Artifact hash mismatch.')
                if item['name'].endswith('.json') and item['name'] in PAYLOADS - {'checkpoint.pt'} | {'model.json'}:
                    payload = image_training._json(contents,'Training artifact')
                    if payload['schema_version'] != 1 or payload['source_identity'] != self._identity(run) or payload['adapter'] != run['adapter']:
                        raise ValueError('Artifact source identity mismatch.')
                    payloads[item['name']] = payload
            metrics = payloads['metrics.json']
            closed(metrics, ('schema_version', 'source_identity', 'adapter', 'parameters', 'transform', 'class_vocabulary',
                             'class_to_idx', 'validation', 'runtime', *(['clocks'] if one_fit else ['history', 'best_epoch'])))
            self._vocabulary(run, metrics)
            if any(metrics['runtime'].get(key) != value for key, value in run['runtime']['runtime'].items()):
                raise ValueError('Executed runtime differs from the admission fingerprint.')
            if metrics['parameters'] != run['parameters'] or metrics['transform'] != (image_training.transform_for_parameters(run['parameters']) if run['graph'].get('recipe') == image_training.MODEL_RECIPE else adapter_for_graph(run['graph']).TRANSFORM):
                raise ValueError('Default metrics are inconsistent or disclose test results.')
            if adapter_for_graph(run['graph']) is not image_training:
                adapter = adapter_for_graph(run['graph'])
                model = adapter.validate_model(payloads['model.json'])
                self._vocabulary(run, model)
                if model['parameters'] != run['parameters'] or model['transform'] != adapter.TRANSFORM:
                    raise ValueError('JSON model differs from the admitted recipe.')
            self._metric(metrics['validation'], 'validation', run)
            if not one_fit:
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
            if run['graph'].get('recipe') == image_training.MODEL_RECIPE:
                import model_evidence
                model_evidence.verify(directory,run,metrics)
            elif one_fit:
                import one_fit_evidence
                one_fit_evidence.verify(directory,run,metrics)
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
        if self._external(run):
            return self._verify_external_artifacts(run)
        artifacts, metrics = self._verify_directory(run, self.path / run['id'])
        if artifacts != run['artifacts'] or metrics != run['metrics']:
            raise WorkbenchError('Published artifacts differ from the admitted result receipt.', 'unavailable', 409)
        return artifacts

    @authorized('inspect', 'runs.capture_artifact')
    def capture_artifact(self, run_id, name, expected_sha256, *, max_bytes=MAX_ARTIFACT_BYTES):
        """Capture a completed external artifact with server-derived custody evidence."""
        import recipe_process
        if type(expected_sha256) is not str or not re.fullmatch('[a-f0-9]{64}', expected_sha256):
            raise WorkbenchError('Supply the expected artifact SHA256.')
        with self.lock:
            run = self._load(run_id)
        if not self._external(run):
            if run.get('graph', {}).get('recipe') != 'image_classification_model_v2':
                raise WorkbenchError('Capture requires a qualified classifier evidence or external Run.', 'unsupported', 400)
            if type(max_bytes) is not int or not 0 < max_bytes <= MAX_ARTIFACT_BYTES:
                raise WorkbenchError('Invalid artifact input byte bound.')
            if name == 'release.zip':
                raise WorkbenchError('Mixed private/protected releases are not model evidence inputs.', 'unsupported', 409)
            artifacts = self._verified_artifacts(run)
            item = next((item for item in artifacts if item['name'] == name), None)
            if item is None or item['bytes'] > max_bytes:
                raise WorkbenchError('Classifier artifact is unavailable or exceeds its capture bound.', 'unavailable', 409)
            if item['sha256'] != expected_sha256:
                raise WorkbenchError('Artifact differs from expected SHA256.', 'conflict', 409)
            raw, _media_type = self.artifact(run_id, name)
            manifest_raw = self._read_regular(self.path / run_id / 'artifact-manifest.json', 65536)
            context = run['evidence_context']
            source = {'schema_version': 2, 'kind': 'builtin_classifier_publication_v1',
                'catalog_id': run['dataset_id'], 'run_id': run_id, 'request_sha256': run['request_sha256'],
                'material_sha256': context['material_sha256'], 'graph_sha256': run['graph_sha256'],
                'release_sha256': run['release_sha256'], 'adapter_sha256': context['adapter_sha256'],
                'artifact_name': name, 'artifact_role': 'model_evidence', 'artifact_bytes': len(raw),
                'measured_sha256': hashlib.sha256(raw).hexdigest(),
                'artifact_manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
                'artifact_manifest_base64': base64.b64encode(manifest_raw).decode('ascii'),
                'population': 'test' if name in TEST_FILES else 'validation' if item.get('split') == 'validation' else 'train'}
            try:
                recipe_process.validate_artifact_source(source, expected_sha256, len(raw))
            except recipe_process.ProcessError as error:
                raise WorkbenchError('Classifier publication source differs.', 'unavailable', 409) from error
            return raw, source
        if type(max_bytes) is not int or not 0 < max_bytes <= MAX_ARTIFACT_BYTES:
            raise WorkbenchError('Invalid artifact input byte bound.')
        item = self._selected_external(run, name, max_bytes=max_bytes)
        if item['sha256'] != expected_sha256:
            raise WorkbenchError('Artifact differs from the expected SHA256.', 'conflict', 409)
        raw = self._external_bytes(run, item)
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise WorkbenchError('Artifact changed during capture.', 'conflict', 409)
        receipt_raw = self._read_regular(self.path / run_id / 'custody-receipt.json', 16384)
        if hashlib.sha256(receipt_raw).hexdigest() != run['custody_receipt_sha256']:
            raise WorkbenchError('Custody receipt changed during capture.', 'conflict', 409)
        try:
            receipt = recipe_process.validate_receipt(receipt_raw, run['custody_identity'])
        except recipe_process.ProcessError as error:
            raise WorkbenchError('Retained custody receipt cannot be verified.', 'unavailable', 409) from error
        if not receipt['drained'] or receipt['outcome'] != 'completed':
            raise WorkbenchError('Run custody did not complete.', 'unavailable', 409)
        source = {'schema_version': 1, 'catalog_id': run['dataset_id'],
                  'run_id': run['id'], 'attempt_id': run['spec']['attempt_id'],
                  'request_sha256': run['request_sha256'], 'material_sha256': run['material_sha256'],
                  'artifact_name': item['name'], 'artifact_role': item['role'],
                  'artifact_bytes': item['bytes'], 'measured_sha256': item['sha256'],
                  'custody_receipt_sha256': run['custody_receipt_sha256'],
                  'custody_identity': copy.deepcopy(run['custody_identity']),
                  'custody_receipt_base64': base64.b64encode(receipt_raw).decode('ascii')}
        return raw, source

    @authorized('inspect', 'runs.artifact_segment')
    def artifact_segment(self, run_id, name, body):
        """Read a bounded segment; only the client can verify the whole digest.

        Every call rechecks credentials. External Runs use retained custody;
        qualified built-ins verify their complete published evidence inventory.
        The returned segment still requires client-side whole-hash verification.
        """
        closed(body, ('expected_sha256', 'offset', 'max_bytes'))
        expected = body['expected_sha256']
        offset, maximum = body['offset'], body['max_bytes']
        if type(expected) is not str or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise WorkbenchError('Supply the expected whole-artifact SHA256.')
        if type(offset) is not int or offset < 0:
            raise WorkbenchError('Artifact segment offset must be a nonnegative integer.')
        if type(maximum) is not int or not 1 <= maximum <= MAX_ARTIFACT_SEGMENT_BYTES:
            raise WorkbenchError('Artifact segment max_bytes must be 1 through 8 MiB.')
        if type(name) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', name):
            raise WorkbenchError('Artifact segment requires a declared flat output name.')
        with self.lock:
            run = self._load(run_id)
        if self._external(run):
            inventory = self._external_inventory(run)
        else:
            adapter = adapter_for_graph(run['graph'])
            if run['graph'].get('recipe') != getattr(adapter, 'MODEL_RECIPE', None):
                raise WorkbenchError('Artifact segments require a qualified model-evidence or external Run.', 'unsupported', 400)
            if name in TEST_FILES and not run['exposure_events']:
                raise WorkbenchError('Record an explicit test-set exposure before opening test results.', 'conflict', 409)
            inventory = self._verified_artifacts(run)
        item = next((item for item in inventory if item['name'] == name), None)
        if item is None:
            raise WorkbenchError('Unknown published artifact.', 'unavailable', 404)
        if item['sha256'] != expected:
            raise WorkbenchError('Artifact differs from the expected whole SHA256.', 'conflict', 409)
        if offset > item['bytes']:
            raise WorkbenchError('Artifact segment offset exceeds the artifact length.')
        directory = descriptor = None
        try:
            directory = self._diagnostic_directory(self.path / run_id)
            directory_identity = os.fstat(directory)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or before.st_nlink != 1 or before.st_size != item['bytes']):
                raise ValueError('Artifact segment source differs from declared inventory.')
            count = min(maximum, item['bytes'] - offset)
            raw = os.pread(descriptor, count, offset)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')
            if (len(raw) != count or any(getattr(before, key) != getattr(after, key) for key in keys)
                    or any(getattr(after, key) != getattr(current, key) for key in keys)):
                raise ValueError('Artifact changed during segment read.')
            current_directory = self._diagnostic_directory(self.path / run_id)
            try:
                current_identity = os.fstat(current_directory)
                if (directory_identity.st_dev, directory_identity.st_ino) != (current_identity.st_dev, current_identity.st_ino):
                    raise ValueError('Artifact directory changed during segment read.')
            finally:
                os.close(current_directory)
        except (OSError, ValueError) as error:
            raise WorkbenchError('Artifact segment is unavailable or changed during read.', 'unavailable', 409) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory is not None:
                os.close(directory)
        next_offset = offset + len(raw)
        return {'run_id':run_id, 'name':name, 'expected_sha256':expected,
                'total_bytes':item['bytes'], 'media_type':item['media_type'],
                'offset':offset, 'bytes':len(raw), 'next_offset':next_offset,
                'eof':next_offset == item['bytes'],
                'segment_sha256':hashlib.sha256(raw).hexdigest(),
                'data_base64':base64.b64encode(raw).decode('ascii'),
                'verification':'segment_read_whole_hash_unverified'}

    @authorized('inspect', 'runs.artifact')
    def artifact(self, run_id, name):
        with self.lock:
            run = self._load(run_id)
        if self._external(run):
            item = self._selected_external(run, name, max_bytes=MAX_ARTIFACT_BYTES)
            raw = self._external_bytes(run, item)
            if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise WorkbenchError('Artifact changed during read.', 'unavailable', 409)
            return raw, item['media_type']
        if name not in self._payloads(run) | {'artifact-manifest.json', 'release.zip'}:
            raise WorkbenchError('Unknown artifact for this recipe.', 'unavailable', 404)
        if name == 'release.zip':
            release = self.pipelines.inspect_release(run['release_id'], private=True, recipe=run['graph'].get('recipe', 'image_classification'))
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

    @authorized('expose-holdout', 'runs.expose_test')
    def expose_test(self, run_id, body):
        closed(body, ('reason',))
        reason = text_value(body['reason'], 'Exposure reason', 500)
        with self.lock:
            run = self._load(run_id)
        if self._external(run):
            raise WorkbenchError('External recipes have no classification test exposure operation.', 'unsupported', 409)
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
            self.access.audit('runs.expose_test', run_id, {'event_id': event_id, 'release_sha256': run['release_sha256'], 'reason': reason})
            run['exposure_events'].append({'id': event_id, 'created_at': at, 'reason': reason})
            self._save(run)
        return {'id': event_id, 'run_id': run_id, 'release_id': run['release_id'], 'created_at': at, 'reason': reason,
                'test_exposure': {'exposed': True, 'event_count': len(run['exposure_events'])}}

    @authorized('inspect', 'runs.predictions')
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

    @authorized('inspect', 'runs.model_evidence')
    def model_evidence(self, run_id, body=None, *, contract_version=None):
        body={} if body is None else body
        with self.lock:run=self._load(run_id)
        if contract_version is not None and (type(contract_version) is not int or contract_version not in (1,2)):
            raise WorkbenchError('Unsupported model evidence query contract.','unsupported',409)
        if self._extension(run):
            self._external_inventory(run)
            if contract_version==1:
                closed(body,(),('checkpoint_sha256',))
                return {'state':'unsupported','reason':'Scientific field evidence requires its explicit selected query contract.'}
            import extension_evidence
            return extension_evidence.query(self._verify_extension(self.path/run_id,run),body)
        if contract_version==2:
            closed(body,(),('checkpoint_sha256','split'))
            if body.get('split','validation')!='validation':
                raise WorkbenchError('Model evidence only supports validation queries.','unsupported',409)
            body={key:value for key,value in body.items() if key!='split'}
        closed(body,(),('checkpoint_sha256',))
        selected=body.get('checkpoint_sha256')
        if selected is not None and (type(selected) is not str or not re.fullmatch('[a-f0-9]{64}',selected)):
            raise WorkbenchError('Checkpoint selection requires its descriptor SHA256.')
        with self.lock:run=self._load(run_id)
        if not model_aware_graph(run['graph']):
            return {'state':'unsupported','reason':'This retained adapter did not capture model_evidence_v1.'}
        self._verified_artifacts(run)
        import model_evidence
        if adapter_for_graph(run['graph']) is image_training:
            evaluator = model_evidence
        else:
            import one_fit_evidence as evaluator
        result,descriptors,predictions=evaluator.verify(self.path/run_id,run,run['metrics'])
        result.update(checkpoint=None,predictions=None,metric_definition_hashes={item['id']:model_evidence.digest(item) for item in result['metric_definitions']})
        if selected is not None:
            entries=result['checkpoint_index']['entries']
            match=[i for i,item in enumerate(entries) if item['checkpoint']['sha256']==selected]
            if not match:raise WorkbenchError('Checkpoint does not belong to this Run.','not_found',404)
            result.update(checkpoint=descriptors[match[0]],predictions=predictions[match[0]])
        return result

    @authorized('inspect', 'runs.compare_model_evidence')
    def compare_model_evidence(self, run_id, other_run_id, body=None):
        import model_evidence
        identifier(other_run_id,'Comparison Run ID')
        evidence=[self.model_evidence(item) for item in (run_id,other_run_id)]
        if body is not None:
            closed(body,('checkpoint_sha256','other_checkpoint_sha256','evaluation_sha256','other_evaluation_sha256',
                         'metric_id','metric_definition_sha256','other_metric_definition_sha256','mode'))
            if body['mode'] not in ('paired','side_by_side'):
                raise WorkbenchError('Choose paired or side_by_side comparison mode.')
            text_value(body['metric_id'],'Metric ID',64)
            for key,value in body.items():
                if key.endswith('sha256') and (type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value)):
                    raise WorkbenchError('Comparison identities require exact SHA256 values.')
            if any(value['state']!='verified' for value in evidence):
                raise WorkbenchError('Exact comparison requires verified checkpoint evidence.','unsupported',409)
            with self.lock:
                for index,selected_id in enumerate((run_id,other_run_id)):
                    selected_run=self._load(selected_id)
                    item=next((artifact for artifact in selected_run['artifacts'] if artifact['name']=='model-evidence.json'),None)
                    expected=body[('other_' if index else '')+'evaluation_sha256']
                    if item is None or item['sha256']!=expected:
                        raise WorkbenchError('Exact comparison evaluation snapshot differs.','stale',409)
            try:return model_evidence.compare_evidence(evidence,[run_id,other_run_id],body)
            except (ValueError,KeyError,TypeError) as error:
                raise WorkbenchError('Exact comparison refused: '+str(error)[:200],'invalid',409) from None
        reasons=[];metrics=[]
        if any(item['state']!='verified' for item in evidence):
            reasons.append('Both Runs require verified model_evidence_v1.')
        else:
            left,right=evidence
            if left['manifest']['task']['sha256']!=right['manifest']['task']['sha256']:
                reasons.append('Task semantics differ.')
            if left['model_definition']['preprocessing_policy']!=right['model_definition']['preprocessing_policy']:
                reasons.append('Preprocessing policies differ.')
            if left['model_definition']['output_policy']!=right['model_definition']['output_policy']:
                reasons.append('Output policies differ.')
            if sorted((model_evidence.canonical(item['frozen_reference']) for item in left['probe']['members'])) != sorted(
                    model_evidence.canonical(item['frozen_reference']) for item in right['probe']['members']):
                reasons.append('Frozen validation membership differs.')
            with self.lock:
                runs=[self._load(item) for item in (run_id,other_run_id)]
            if runs[0]['metrics']['class_vocabulary']!=runs[1]['metrics']['class_vocabulary']:
                reasons.append('Frozen class vocabulary or order differs.')
            if left['metric_definitions']!=right['metric_definitions']:
                reasons.append('Metric semantics or validation population differ.')
            if not reasons:
                for definition in left['metric_definitions']:
                    metrics.append({'metric_id':definition['id'],'values':[run['metrics']['validation'][definition['id']] for run in runs],
                                    'direction':definition['direction'],'units':definition['units']})
        return {'state':'incompatible' if reasons else 'compatible','run_ids':[run_id,other_run_id],
                'reasons':reasons,'metrics':metrics}


    def close(self):
        with self._thread_lock:
            self._closed = True
            self._stop.set()
            self._wake.set()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=60)
            if thread.is_alive():
                raise RuntimeError('Training supervisor did not drain; metadata must remain open.')
        if self.runtime_owner:
            try:
                with self.lock, self.db.transaction():
                    for run in self._in_states(('queued',)):
                        if run['state'] == 'queued':
                            self._event(run, 'cancelled', 'Application closed before this queued attempt started.')
                            self._save(run)
            except psycopg.Error:
                # Drain local resources independently of database availability.
                # No successful durable transition is claimed after a lost write.
                pass
