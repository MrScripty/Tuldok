"""Small consumer workflows over the negotiated local AgentClient.

Import is standard-library-only. Each WorkflowClient exclusively owns its
AgentClient while a workflow runs; callers must not share it concurrently.
Execution, disclosure, comparison and grants remain server-owned.
"""
import copy
from contextlib import nullcontext
import hashlib
import math
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time

from agent_api import (AgentAPIError, AgentClient, encoded, validate_arguments,
                       verify_artifact, verify_publication_artifact)

MAX_ITEMS = 20
MAX_COLLECTION_BYTES = 512 * 1024 * 1024
TERMINAL = frozenset(('completed', 'failed', 'cancelled', 'interrupted', 'unknown'))
SUBMISSIONS = frozenset(('runs.submit_external', 'studies.admit'))
COMPARISONS = frozenset(('runs.compare_model_evidence', 'runs.compare_publication_evidence'))


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise AgentAPIError('Invalid workflow document fields.')


def _digest(value):
    try:
        return hashlib.sha256(encoded(value)).hexdigest()
    except (TypeError, ValueError, RecursionError):
        raise AgentAPIError('Invalid bounded workflow JSON.') from None


def _error(error):
    return {'code': error.code, 'error': str(error), 'status': error.status}


def _invoke(client, operation, arguments):
    envelope = client.call(operation, arguments)
    if envelope['status'] >= 400:
        error = envelope['result']
        raise AgentAPIError(error['error'], error.get('code', 'http_error'), envelope['status'])
    return envelope['result']


def _manifest(catalog_id, operation, arguments, kind):
    result = {'format': kind, 'catalog_id': catalog_id, 'operation': operation,
              'arguments': copy.deepcopy(arguments)}
    return dict(result, sha256=_digest(result))


def _check_manifest(value, catalog_id, kind, operations):
    _closed(value, ('format', 'catalog_id', 'operation', 'arguments', 'sha256'))
    body = {key: child for key, child in value.items() if key != 'sha256'}
    if (value['format'] != kind or value['catalog_id'] != catalog_id
            or type(value['operation']) is not str or value['operation'] not in operations or _digest(body) != value['sha256']):
        raise AgentAPIError('Workflow manifest identity differs.', 'conflict', 409)
    version = 2 if value['operation'] == 'runs.compare_model_evidence' else None
    if version is None:
        validate_arguments(value['operation'], value['arguments'])
    else:
        validate_arguments(value['operation'], value['arguments'], version)
    if value['operation'] in SUBMISSIONS and 'approval_id' not in value['arguments']:
        raise AgentAPIError('Select an existing owner approval_id for the reviewed material.')
    return copy.deepcopy(value)


def download(client, run_id, name, expected_sha256, destination, *, result_ref=None,
             chunk_bytes=8*1024*1024, cancelled=None, expected_bytes=None):
    """Verify whole bytes, fsync and atomically link a new private file.

    Incomplete segments are disposable, including cancellation. A future explicit
    collection resumes this item at zero rather than trusting a partial prefix.
    """
    destination = Path(destination)
    if os.path.lexists(destination):
        raise AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409)
    fd, provisional = tempfile.mkstemp(prefix='.tuldok-download-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            def consume(raw):
                if cancelled is not None and cancelled.is_set():
                    raise AgentAPIError('Collection stopped; compute cancellation was not requested.', 'stopped', 409)
                handle.write(raw)
                if expected_bytes is not None and handle.tell() > expected_bytes:
                    raise AgentAPIError('Artifact exceeds selected inventory bytes.', 'artifact_mismatch', 409)
            receipt = (verify_artifact(client, run_id, name, expected_sha256, consume=consume, chunk_bytes=chunk_bytes)
                       if result_ref is None else verify_publication_artifact(client, result_ref, name,
                           expected_sha256, consume=consume, chunk_bytes=chunk_bytes))
            if expected_bytes is not None and receipt['bytes'] != expected_bytes:
                raise AgentAPIError('Artifact size differs from selected inventory.', 'artifact_mismatch', 409)
            if cancelled is not None and cancelled.is_set():
                raise AgentAPIError('Collection stopped; compute cancellation was not requested.', 'stopped', 409)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(provisional, destination, follow_symlinks=False)
        return dict(receipt, run_id=run_id, name=name, output=str(destination))
    except FileExistsError:
        raise AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409) from None
    finally:
        os.unlink(provisional)


def _verified_local(path, item):
    """Reopen resumed success without following links; never trust a receipt alone."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size != item['bytes']
                or before.st_uid != os.getuid() or before.st_mode & 0o077):
            raise AgentAPIError('Resumed artifact is not a private exact regular file.', 'artifact_mismatch', 409)
        checksum = hashlib.sha256()
        remaining = item['bytes']
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw:
                break
            checksum.update(raw)
            remaining -= len(raw)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        if ((current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)
                or remaining or checksum.hexdigest() != item['sha256']
                or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                   (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise AgentAPIError('Resumed artifact differs from its exact whole hash.', 'artifact_mismatch', 409)
    finally:
        os.close(fd)


class WorkflowClient:
    """Explicit, serial consumer of one privately configured AgentClient."""
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_config(cls, path):
        return cls(AgentClient.from_config(path))

    def submission_manifest(self, graph_id, revision, *, approval_id, request_key):
        """Read selected preflight; export existing grant + exact reviewed material."""
        prepared = _invoke(self.client, 'graphs.preflight_external', {'graph_id': graph_id, 'revision': revision})
        if (prepared['material']['catalog_id'] != self.client.catalog_id
                or prepared['graph_revision'] != revision
                or hashlib.sha256(json.dumps(prepared['material'], sort_keys=True, separators=(',', ':'),
                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest() != prepared['material_sha256']):
            raise AgentAPIError('Selected preflight material differs.', 'conflict', 409)
        args = {'graph_id': graph_id, 'graph_revision': revision,
                'expected_digest': prepared['material_sha256'], 'approval_id': approval_id, 'request_key': request_key}
        validate_arguments('runs.submit_external', args)
        return _manifest(self.client.catalog_id, 'runs.submit_external', args, 'workflow_submission_manifest_v1')

    def trial_submission_manifest(self, trial_id, *, approval_id, request_key, parent_run_id=None):
        trial = _invoke(self.client, 'studies.trial', {'trial_id': trial_id})
        study = _invoke(self.client, 'studies.get', {'study_id': trial['study_id']})['study']
        if (trial['id'] != trial_id or trial['material']['catalog_id'] != self.client.catalog_id
                or study['id'] != trial['study_id']):
            raise AgentAPIError('Selected Trial belongs to another identity.', 'conflict', 409)
        args = {'study_id': trial['study_id'], 'revision': study['revision'],
                'admission_epoch': study['admission_epoch'], 'trial_id': trial_id,
                'approval_id': approval_id, 'request_key': request_key}
        if parent_run_id is not None:
            args['parent_run_id'] = parent_run_id
        validate_arguments('studies.admit', args)
        return _manifest(self.client.catalog_id, 'studies.admit', args, 'workflow_submission_manifest_v1')

    def submit(self, manifest):
        """One dispatch. Unknown delivery returns the same manifest for explicit reconciliation."""
        manifest = _check_manifest(manifest, self.client.catalog_id, 'workflow_submission_manifest_v1', SUBMISSIONS)
        operation, arguments = manifest['operation'], manifest['arguments']
        selected = self.client.selected_contracts()
        if operation not in selected:
            raise AgentAPIError('Submission has no compatible available contract.', 'operation_unsupported', 409)
        validate_arguments(operation, arguments, selected[operation])
        receipt = {'format': 'workflow_submission_receipt_v1', 'manifest': manifest}
        try:
            envelope = self.client.call(operation, arguments)
        except AgentAPIError as error:
            return dict(receipt, state='unknown', error=_error(error))
        if envelope['status'] >= 500 or envelope['result'].get('code') == 'commit_unknown':
            error = envelope['result']
            return dict(receipt, state='unknown', error={'code': error.get('code', 'http_error'),
                'error': error['error'], 'status': envelope['status']})
        if envelope['status'] >= 400:
            return dict(receipt, state='refused', envelope=envelope)
        try:
            if operation == 'runs.submit_external':
                run = envelope['result']
                if (run['request_key'] != arguments['request_key'] or run['dataset_id'] != self.client.catalog_id
                        or run['graph']['id'] != arguments['graph_id']
                        or run['graph_revision'] != arguments['graph_revision']
                        or run['material_sha256'] != arguments['expected_digest']
                        or run['approval_id'] != arguments['approval_id']):
                    raise ValueError()
            else:
                reservation = envelope['result']['reservation']
                if (any(reservation[key] != arguments[key] for key in
                        ('study_id', 'trial_id', 'request_key', 'admission_epoch'))
                        or reservation['run_id'] != envelope['result']['run']['id']):
                    raise ValueError()
        except (KeyError, TypeError, ValueError):
            return dict(receipt, state='unknown', error={'code': 'transport', 'status': 502,
                'error': 'Submission acknowledgement differs from its exact requested identity.'})
        return dict(receipt, state='acknowledged', envelope=envelope)

    def reconcile(self, unknown):
        if type(unknown) is not dict or set(unknown) not in (
                {'format', 'manifest', 'state', 'error'}, {'format', 'manifest', 'state', 'error', 'reconciliation'}):
            raise AgentAPIError('Reconcile requires the exact unknown submission receipt.')
        if unknown['format'] != 'workflow_submission_receipt_v1' or unknown['state'] != 'unknown':
            raise AgentAPIError('Reconcile requires the exact unknown submission receipt.')
        # Validate before the try: a changed manifest is an invalid local request,
        # not another observation of the original uncertain admission.
        _check_manifest(unknown['manifest'], self.client.catalog_id, 'workflow_submission_manifest_v1', SUBMISSIONS)
        try:
            current = self.submit(unknown['manifest'])
        except AgentAPIError as error:
            current = {'state': 'unknown', 'error': _error(error)}
        if current['state'] == 'acknowledged':
            return current
        # Later revocation/refusal cannot establish that an earlier unknown
        # mutation had no effect. Preserve its original uncertainty and identity.
        observation = {key: value for key, value in current.items() if key in ('state', 'error', 'envelope')}
        return dict(copy.deepcopy(unknown), reconciliation=observation)

    def monitor(self, run_id, *, timeout=60, cancelled=None, interval=.25, max_interval=5):
        """Bound read-only polling, bootstrap and blocking reads with one deadline."""
        for value in (timeout, interval, max_interval):
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise AgentAPIError('Monitoring requires finite positive budgets.')
        if interval > max_interval or timeout > 86400 or max_interval > 60:
            raise AgentAPIError('Monitoring budgets exceed the supported bounds.')
        stop = cancelled if cancelled is not None else threading.Event()
        deadline, delay, reads, latest = time.monotonic() + timeout, interval, 0, None
        def outcome(state):
            return {'state': state, 'run': latest, 'reads': reads, 'compute_cancel_requested': False}
        try:
            with self.client.read_budget(deadline, stop):
                validate_arguments('runs.get', {'run_id': run_id})
                while True:
                    if stop.is_set():
                        return outcome('stopped')
                    if time.monotonic() >= deadline:
                        return outcome('deadline')
                    latest = _invoke(self.client, 'runs.get', {'run_id': run_id})
                    reads += 1
                    if latest['id'] != run_id:
                        raise AgentAPIError('Monitor returned a different Run.', 'transport', 502)
                    if latest['state'] in TERMINAL:
                        return outcome('terminal')
                    # The selected Run contract has no Retry-After field. Server
                    # errors remain typed; capped delay is only for valid reads.
                    stop.wait(min(delay, max(0, deadline-time.monotonic())))
                    delay = min(max_interval, delay * 2)
        except AgentAPIError as error:
            if error.code in ('deadline', 'stopped'):
                return outcome(error.code)
            raise

    def cancel(self, run_id):
        run = _invoke(self.client, 'runs.cancel', {'run_id': run_id})
        if run['id'] != run_id:
            raise AgentAPIError('Cancellation returned a different Run.', 'transport', 502)
        drained = run.get('custody_phase') == 'drained'
        before_start = run['state'] == 'cancelled' and run.get('custody_phase') == 'prepared'
        return {'state': 'drained' if drained else 'cancelled_before_start' if before_start else 'requested',
                'drained': drained, 'run': run}

    def _result(self, source):
        if set(source) == {'run_id'}:
            value = _invoke(self.client, 'runs.get', source)
            if value['id'] != source['run_id'] or value.get('dataset_id') != self.client.catalog_id:
                raise AgentAPIError('Collection Run identity differs.', 'conflict', 409)
        elif set(source) == {'ref'}:
            value = _invoke(self.client, 'runs.publication_result', source)
            if value['result_ref'] != source['ref'] or value['catalog_id'] != self.client.catalog_id:
                raise AgentAPIError('Collection publication identity differs.', 'conflict', 409)
        else:
            raise AgentAPIError('Select one exact Run or publication Ref.')
        return value

    def _inventory(self, source):
        return self._artifact_inventory(self._result(source), source)

    @staticmethod
    def _artifact_inventory(value, source):
        try:
            artifacts = value['artifacts']
            if type(artifacts) is not list or len(artifacts) > 96:
                raise ValueError()
            inventory = []
            for item in artifacts:
                validate_arguments('runs.artifact_chunk', {
                    'run_id': source.get('run_id', source.get('ref', {}).get('run_id')),
                    'name': item['name'], 'expected_sha256': item['sha256'], 'offset': 0, 'max_bytes': 1})
                if type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_COLLECTION_BYTES:
                    raise ValueError()
                inventory.append({key: item[key] for key in ('name', 'sha256', 'bytes')})
            if len({item['name'] for item in inventory}) != len(inventory):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AgentAPIError):
            raise AgentAPIError('Selected artifact inventory is malformed or exceeds its bounds.', 'transport', 502) from None
        return sorted(inventory, key=lambda item: item['name'])

    def collection_manifest(self, *, names, run_id=None, result_ref=None):
        if (run_id is None) == (result_ref is None):
            raise AgentAPIError('Select one exact Run or publication Ref.')
        if (type(names) is not list or not 1 <= len(names) <= MAX_ITEMS
                or any(type(name) is not str for name in names) or len(set(names)) != len(names)):
            raise AgentAPIError('Select between 1 and 20 unique artifact names.')
        source = {'run_id': run_id} if result_ref is None else {'ref': copy.deepcopy(result_ref)}
        inventory = self._inventory(source)
        items = [item for item in inventory if item['name'] in names]
        if len(items) != len(names) or sum(item['bytes'] for item in items) > MAX_COLLECTION_BYTES:
            raise AgentAPIError('Selected artifacts are missing or exceed the aggregate collection bound.')
        body = {'format': 'workflow_collection_manifest_v1', 'catalog_id': self.client.catalog_id,
                'source': source, 'inventory_sha256': _digest(inventory), 'items': items}
        return dict(body, sha256=_digest(body))

    def _validate_collection(self, manifest):
        _closed(manifest, ('format', 'catalog_id', 'source', 'inventory_sha256', 'items', 'sha256'))
        if (manifest['format'] != 'workflow_collection_manifest_v1' or manifest['catalog_id'] != self.client.catalog_id
                or manifest['sha256'] != _digest({k: v for k, v in manifest.items() if k != 'sha256'})
                or type(manifest['source']) is not dict or type(manifest['items']) is not list
                or not 1 <= len(manifest['items']) <= MAX_ITEMS):
            raise AgentAPIError('Invalid collection manifest.')
        source = manifest['source']
        if set(source) == {'run_id'}:
            operation = 'runs.artifact_chunk'
        elif set(source) == {'ref'}:
            operation = 'runs.publication_artifact_chunk'
        else:
            raise AgentAPIError('Select one exact Run or publication Ref.')
        inventory_hash = manifest['inventory_sha256']
        if (type(inventory_hash) is not str or len(inventory_hash) != 64
                or any(char not in '0123456789abcdef' for char in inventory_hash)):
            raise AgentAPIError('Invalid collection inventory identity.')
        names = []
        for item in manifest['items']:
            _closed(item, ('name', 'sha256', 'bytes'))
            if type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_COLLECTION_BYTES:
                raise AgentAPIError('Invalid collection item byte bound.')
            validate_arguments(operation, dict(source, name=item['name'], expected_sha256=item['sha256'],
                offset=0, max_bytes=1))
            if 'ref' in source and source['ref']['catalog_id'] != self.client.catalog_id:
                raise AgentAPIError('Collection publication belongs to another catalog.', 'conflict', 409)
            names.append(item['name'])
        if len(set(names)) != len(names) or sum(item['bytes'] for item in manifest['items']) > MAX_COLLECTION_BYTES:
            raise AgentAPIError('Collection exceeds unique item or aggregate bounds.')
        return copy.deepcopy(manifest)

    def _check_collection(self, manifest):
        # Fresh transitive disclosure and exact inventory, including on resume.
        inventory = self._inventory(manifest['source'])
        if (_digest(inventory) != manifest['inventory_sha256']
                or any(item not in inventory for item in manifest['items'])):
            raise AgentAPIError('Selected inventory changed; explicit new selection required.', 'stale', 409)
        return copy.deepcopy(manifest)

    def collect(self, manifest, directory, *, resume=None, cancelled=None, chunk_bytes=8*1024*1024):
        """Sequential exact collection. Failure stops dispatch; explicit resume is required."""
        if cancelled is not None and not isinstance(cancelled, threading.Event):
            raise AgentAPIError('Collection cancellation must be a threading.Event.')
        if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 8*1024*1024:
            raise AgentAPIError('Invalid bounded collection segment size.')
        manifest = self._validate_collection(manifest)
        # No batch operation exists in the installed registry. Do not probe an
        # invented route or fall back in response to an operation failure.
        previous = {}
        if resume is not None:
            _closed(resume, ('format', 'manifest', 'state', 'items'))
            if (resume['format'] != 'workflow_collection_receipt_v1' or resume['manifest'] != manifest
                    or type(resume['items']) is not list or len(resume['items']) != len(manifest['items'])):
                raise AgentAPIError('Resume receipt differs from the exact collection manifest.', 'conflict', 409)
            for selected, result in zip(manifest['items'], resume['items']):
                if (type(result) is not dict or result.get('name') != selected['name']
                        or result.get('state') not in ('verified', 'refused', 'outstanding')):
                    raise AgentAPIError('Invalid resume item.')
                previous[result['name']] = result
        def stopped():
            return {'format': 'workflow_collection_receipt_v1', 'manifest': manifest, 'state': 'stopped',
                    'items': [copy.deepcopy(previous.get(item['name'], {'name': item['name'], 'state': 'outstanding'}))
                              for item in manifest['items']]}
        if cancelled is not None and cancelled.is_set():
            return stopped()
        try:
            budget = self.client.read_budget(None, cancelled) if cancelled is not None else nullcontext()
            with budget:
                self._check_collection(manifest)
                directory = Path(directory)
                if not directory.is_dir() or directory.is_symlink():
                    raise AgentAPIError('Collection destination must be an existing regular directory.')
                results, halted = [], False
                for item in manifest['items']:
                    name = item['name']
                    destination = directory / name
                    if halted or (cancelled is not None and cancelled.is_set()):
                        results.append(copy.deepcopy(previous.get(name, {'name': name, 'state': 'outstanding'})))
                        halted = True
                        continue
                    try:
                        if previous.get(name, {}).get('state') == 'verified':
                            # Reauthorize this artifact even when no local write is needed.
                            source = manifest['source']
                            operation = 'runs.publication_artifact_chunk' if 'ref' in source else 'runs.artifact_chunk'
                            _invoke(self.client, operation, dict(source, name=name, expected_sha256=item['sha256'], offset=0, max_bytes=1))
                            _verified_local(destination, item)
                            receipt = {'run_id': source.get('run_id', source.get('ref', {}).get('run_id')),
                                       'name': name, 'output': str(destination), 'sha256': item['sha256'],
                                       'bytes': item['bytes'], 'verification': 'whole_sha256_verified'}
                            if 'ref' in source:
                                receipt['result_ref'] = copy.deepcopy(source['ref'])
                        else:
                            source = manifest['source']
                            receipt = download(self.client, source.get('run_id', source.get('ref', {}).get('run_id')),
                                name, item['sha256'], destination, result_ref=source.get('ref'), chunk_bytes=chunk_bytes,
                                cancelled=cancelled, expected_bytes=item['bytes'])
                        results.append({'name': name, 'state': 'verified', 'receipt': receipt})
                    except (AgentAPIError, OSError) as error:
                        if isinstance(error, OSError):
                            error = AgentAPIError('Local collection file operation failed.', 'unavailable', 503)
                        results.append({'name': name, 'state': 'outstanding' if error.code == 'stopped' else 'refused', 'error': _error(error)})
                        halted = True
                state = ('complete' if all(item['state'] == 'verified' for item in results) else
                         'stopped' if cancelled is not None and cancelled.is_set() else 'partial')
                return {'format': 'workflow_collection_receipt_v1', 'manifest': manifest, 'state': state, 'items': results}

        except AgentAPIError as error:
            if error.code == 'stopped':
                return stopped()
            raise

    def comparison_manifest(self, run_id, other_run_id, *, checkpoint_sha256, other_checkpoint_sha256,
                            metric_id, mode='paired', result_ref=None, other_result_ref=None):
        """Read exact evidence selectors; delegate all compatibility and numerical work."""
        if (result_ref is None) != (other_result_ref is None):
            raise AgentAPIError('Mixed ordinary/recovered comparison is unsupported.', 'unsupported', 409)
        selections = []
        for selected_run, checkpoint, ref in ((run_id, checkpoint_sha256, result_ref),
                                             (other_run_id, other_checkpoint_sha256, other_result_ref)):
            source = {'run_id': selected_run} if ref is None else {'ref': ref}
            value = self._result(source)
            self._artifact_inventory(value, source)
            args = {'run_id': selected_run, 'checkpoint_sha256': checkpoint} if ref is None else {
                'ref': ref, 'selectors': {'checkpoint_sha256': checkpoint}}
            evidence = _invoke(self.client, 'runs.model_evidence' if ref is None else 'runs.publication_model_evidence', args)
            if ref is not None:
                if ref['run_id'] != selected_run:
                    raise AgentAPIError('Comparison Run differs from publication Ref.', 'conflict', 409)
                evidence = evidence['evidence']
            if evidence.get('state') != 'verified':
                raise AgentAPIError(evidence.get('reason', 'Selected evidence is unavailable.'), 'unsupported', 409)
            try:
                evaluation = next(item['sha256'] for item in value['artifacts'] if item['name'] == 'model-evidence.json')
                definition = evidence['metric_definition_hashes'][metric_id]
            except (KeyError, StopIteration):
                raise AgentAPIError('Selected evaluation or metric definition is unavailable.', 'unsupported', 409) from None
            selections.append((checkpoint, evaluation, definition))
        args = {'run_id': run_id, 'other_run_id': other_run_id, 'metric_id': metric_id, 'mode': mode}
        for prefix, values in zip(('', 'other_'), selections):
            args.update({prefix + key: value for key, value in zip(
                ('checkpoint_sha256', 'evaluation_sha256', 'metric_definition_sha256'), values)})
        operation = 'runs.compare_model_evidence'
        if result_ref is not None:
            args = {'ref': result_ref, 'other_ref': other_result_ref,
                    'selection': {k: v for k, v in args.items() if k not in ('run_id', 'other_run_id')}}
            operation = 'runs.compare_publication_evidence'
        result = _manifest(self.client.catalog_id, operation, args, 'workflow_comparison_manifest_v1')
        return _check_manifest(result, self.client.catalog_id, 'workflow_comparison_manifest_v1', COMPARISONS)

    def compare(self, manifest):
        manifest = _check_manifest(manifest, self.client.catalog_id, 'workflow_comparison_manifest_v1', COMPARISONS)
        operation = manifest['operation']
        selected = self.client.selected_contracts()
        if operation not in selected or (operation == 'runs.compare_model_evidence' and selected[operation] < 2):
            raise AgentAPIError('Exact comparison has no compatible available contract.', 'operation_unsupported', 409)
        return self.client.call(operation, manifest['arguments'])
