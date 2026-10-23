"""Explicit current-host CPU runtime capture through a canonical effect intent.

Open never constructs this adapter's filesystem capabilities from retained roots.
The injected resolver supplies current trusted local configuration only. Captured
binaries remain an ignored local cache; portable metadata declares exact bytes.
"""
import copy
from datetime import datetime
import hashlib
import os

import agent_api
from model_definitions import reference
from project_material import decode_records as material_records
from project_session import operation_records, REQUEST_KEY, _digest as operation_digest
from runtime_snapshots import RuntimeSnapshots, DEFAULT_RESERVE, MAX_FILES, MAX_BYTES, MAX_MANIFEST
from workbench import WorkbenchError, timestamp

OPERATIONS = frozenset(('runtime.capture_intent', 'runtime.capture', 'runtime.abandon'))
RESULT_FIELDS = frozenset(('format','project_id','manifest_sha256','file_count','total_bytes',
                           'actor_id','observed_at','request_key'))


def _fail(message, code='invalid', status=400):
    raise WorkbenchError(message, code, status)


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        _fail('Runtime capture requires an exact SHA256.')


def _id(value):
    if type(value) is not str or len(value) != 32 or any(c not in '0123456789abcdef' for c in value):
        _fail('Runtime capture requires a project or actor UUID.')


def _key(value):
    if type(value) is not str or not REQUEST_KEY.fullmatch(value):
        _fail('Invalid runtime capture request key.')


def _intent_key(key):
    return 'runtime-intent.' + hashlib.sha256(key.encode('utf-8')).hexdigest()


def _body(config_request, expected_inventory_sha256, reserve_bytes):
    _sha(expected_inventory_sha256)
    if type(reserve_bytes) is not int or not 0 <= reserve_bytes <= 2**63-1:
        _fail('Runtime capture reserve must be a nonnegative integer.')
    try:
        if type(config_request) is not dict or len(agent_api.encoded(config_request)) > 65536:
            raise ValueError()
    except (agent_api.AgentAPIError, TypeError, ValueError, RecursionError, UnicodeError):
        _fail('Runtime capture requires a bounded current-local configuration request.')
    return dict(configuration=copy.deepcopy(config_request), expected_inventory_sha256=expected_inventory_sha256,
                reserve_bytes=reserve_bytes)


def _intent_input(body):
    """Use the canonical intent owner's exact request identity for local custody."""
    return operation_digest(dict(operation='runtime.capture_intent',
        target=body['expected_inventory_sha256'], body=body))


def _summary(project_id, observed, actor_id, key, *, runtime_ref=None):
    value = dict(format='project_runtime_capture_intent_v1' if runtime_ref is None else 'project_runtime_capture_v1',
        project_id=project_id,manifest_sha256=observed['inventory_sha256'],file_count=observed['file_count'],
        total_bytes=observed['total_bytes'],actor_id=actor_id,observed_at=timestamp(),request_key=key)
    if runtime_ref is not None: value['runtime_ref'] = copy.deepcopy(runtime_ref)
    return value


def validate_operation_result(operation, result, records=None):
    """Validate inert capture facts; no retained path becomes a local binding."""
    if operation not in OPERATIONS: return False
    try:
        if operation == 'runtime.abandon':
            fields = {'format','project_id','capture_key','input_sha256','manifest_sha256',
                      'actor_id','reason','observed_checkpoint','observed_at'}
            if type(result) is not dict or set(result) != fields or result['format'] != 'project_runtime_capture_abandon_v1':
                _fail('Invalid runtime abandonment observation.')
            _id(result['project_id']); _id(result['actor_id']); _key(result['capture_key'])
            for field in ('input_sha256','manifest_sha256','observed_checkpoint'): _sha(result[field])
            if type(result['reason']) is not str or not result['reason'].strip() or len(result['reason']) > 1000:
                _fail('Runtime abandonment requires the retained owner reason.')
            if type(result['observed_at']) is not str or datetime.fromisoformat(result['observed_at']).utcoffset() is None:
                _fail('Runtime abandonment requires an offset timestamp.')
            if records is not None:
                intents = [r['document'] for r in records if r['family']=='project_operation'
                           and r['document']['operation']=='runtime.capture_intent'
                           and r['document']['request_key']==_intent_key(result['capture_key'])
                           and r['document']['input_sha256']==result['input_sha256']
                           and r['document']['result'].get('project_id')==result['project_id']
                           and r['document']['result'].get('manifest_sha256')==result['manifest_sha256']]
                if len(intents) != 1: _fail('Runtime abandonment has no exact original capture intent.')
                if any(r['family']=='project_operation'
                       and r['document']['operation']=='runtime.capture'
                       and r['document']['request_key']==result['capture_key']
                       and r['document']['result'].get('project_id')==result['project_id']
                       for r in records):
                    _fail('Completed runtime capture cannot be abandoned.')
            return True
        complete = operation == 'runtime.capture'
        fields = RESULT_FIELDS | ({'runtime_ref'} if complete else set())
        if type(result) is not dict or set(result) != fields:
            _fail('Invalid runtime capture observation fields.')
        expected_format = 'project_runtime_capture_v1' if complete else 'project_runtime_capture_intent_v1'
        if result['format'] != expected_format: _fail('Unsupported runtime capture observation.')
        _id(result['project_id']); _id(result['actor_id']); _sha(result['manifest_sha256']); _key(result['request_key'])
        if (type(result['file_count']) is not int or not 1 <= result['file_count'] <= MAX_FILES or
                type(result['total_bytes']) is not int or not 0 <= result['total_bytes'] <= MAX_BYTES):
            _fail('Runtime capture observation exceeds the owner inventory bounds.')
        instant = result['observed_at']
        if type(instant) is not str or len(instant) > 80 or datetime.fromisoformat(instant).utcoffset() is None:
            _fail('Runtime capture observation requires an offset timestamp.')
        if not complete: return True
        ref = reference(result['runtime_ref'], 'runtime', result['project_id'])
        if records is None: return True
        doc = material_records(records).get(('runtime_material', result['project_id']+'.'+ref['sha256']))
        descriptor = None if doc is None else doc['value']['descriptor']
        if (doc is None or doc['value']['ref'] != ref or descriptor is None or
                descriptor['profile'] != 'captured_cpu_python_v1' or
                any(descriptor[field] != result[field] for field in ('manifest_sha256','file_count','total_bytes'))):
            _fail('Runtime capture observation differs from its exact retained material.')
        declarations = {r['id']:r['document'] for r in records if r['family']=='project_artifact'}
        for edge in doc['artifacts']:
            if declarations.get(edge['blob']['sha256']) != dict(format='project_artifact_v1', **edge['blob']):
                _fail('Runtime capture lacks its complete exact artifact declarations.')
        intents = [r['document']['result'] for r in records if r['family']=='project_operation'
                   and r['document']['operation']=='runtime.capture_intent'
                   and r['document']['request_key']==_intent_key(result['request_key'])]
        matching = [intent for intent in intents if all(intent.get(field)==result[field]
                    for field in ('project_id','manifest_sha256','file_count','total_bytes','request_key'))]
        if len(matching) != 1: _fail('Runtime capture lacks its unique durable publication intent.')
        validate_operation_result('runtime.capture_intent', matching[0])
        return True
    except WorkbenchError: raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        _fail('Malformed runtime capture observation.')


class ProjectRuntime:
    def __init__(self, projection, *, resolve_configuration):
        if not callable(resolve_configuration):
            raise TypeError('An explicit current-local runtime configuration resolver is required.')
        self.projection = projection
        self.session, self.db, self.access = projection.session, projection.db, projection.access
        self.execution, self.materials = projection.execution, projection.materials
        self.resolve_configuration = resolve_configuration
        self.owner = RuntimeSnapshots(self.db, self.execution.runtime_access, self.db.path)

    def _authorize(self, action):
        return self.access.require('admin', action, owner_only=True)

    def inspect(self, config_request):
        """Read an explicitly selected current source; never provision or execute."""
        with self.access.lock, self.session.lock, self.db.lock:
            self._authorize('runtime_snapshots.inspect'); self.session.check()
            _body(config_request, '0'*64, 0)
            with self.execution.runtime_inspection():
                return self.owner.inspect(self.resolve_configuration(copy.deepcopy(config_request)))

    def status(self, key):
        """Read historical outcome only; captured does not claim local readiness."""
        _key(key)
        with self.access.lock, self.session.lock, self.db.lock:
            self.access.require('inspect', 'runtime.capture_status'); self.session.check()
            receipts = operation_records(self.session.snapshot['records'])
            intent = receipts.get(_intent_key(key)); complete = receipts.get(key)
            if intent is not None and intent['operation'] != 'runtime.capture_intent': intent = None
            if complete is not None and complete['operation'] != 'runtime.capture': complete = None
            abandoned = next((r['result'] for r in receipts.values() if r['operation']=='runtime.abandon'
                              and r['result']['capture_key']==key), None)
            if abandoned is not None:
                return dict(state='abandoned',intent=copy.deepcopy(intent['result']) if intent else None,
                            result=None,abandonment=copy.deepcopy(abandoned))
            return dict(state='captured' if complete else 'intent_recorded' if intent else 'absent',
                        intent=copy.deepcopy(intent['result']) if intent else None,
                        result=copy.deepcopy(complete['result']) if complete else None)

    def recover_capture(self, config_request, expected_inventory_sha256, expected_checkpoint, key, *, reserve_bytes=DEFAULT_RESERVE):
        """Explicitly restore one original local copy before its exact retry."""
        body = _body(config_request, expected_inventory_sha256, reserve_bytes)
        body_sha = _intent_input(body)
        self._authorize('runtime_snapshots.create')
        self.execution.prepare_runtime_reconciliation(key, body_sha, expected_inventory_sha256, expected_checkpoint)
        return self.capture(config_request, expected_inventory_sha256, self.session.snapshot['checkpoint'], key,
                            reserve_bytes=reserve_bytes)

    def abandon(self, capture_key, reason, expected_checkpoint, key):
        """Preserve partial bytes and acknowledge one stopped local copy."""
        _key(capture_key); _key(key); _sha(expected_checkpoint)
        if key == capture_key or type(reason) is not str or not reason.strip() or len(reason) > 1000:
            _fail('Use a separate abandonment key and a retained reason.')
        actor = self._authorize('runtime.capture_abandon')
        body = dict(capture_key=capture_key, reason=reason, actor_id=actor.actor_id)
        marker = self.execution.runtime_pending(capture_key)
        if marker is None:
            # Pure receipt replay cannot clear a local writer or run anything.
            def forbidden(): _fail('No original local runtime copy exists to abandon.', 'unavailable', 409)
            return self.session.mutate('runtime.abandon', capture_key, body, expected_checkpoint, key,
                                       forbidden, lambda *args: forbidden(), scope='admin')
        with self.execution.runtime_reconciliation(capture_key, marker['input_sha256'],
                marker['manifest_sha256'], expected_checkpoint) as guard:
            receipts = operation_records(self.session.snapshot['records'])
            intent = receipts.get(_intent_key(capture_key))
            if (intent is None or intent['operation']!='runtime.capture_intent'
                    or intent['input_sha256']!=marker['input_sha256']
                    or intent['result']['project_id']!=self.session.project_id
                    or intent['result']['manifest_sha256']!=marker['manifest_sha256']):
                _fail('Runtime intent differs from its exact original local writer.', 'conflict', 409)
            if capture_key in receipts:
                _fail('Capture completed; reconcile its acknowledgement with the exact capture request.', 'conflict', 409)
            observed = self.session.snapshot['checkpoint']
            def invoke():
                current = self._authorize('runtime.capture_abandon')
                if current.actor_id != actor.actor_id: _fail('Runtime abandonment caller changed.', 'conflict', 409)
                return dict(format='project_runtime_capture_abandon_v1',project_id=self.session.project_id,
                    capture_key=capture_key,input_sha256=marker['input_sha256'],manifest_sha256=marker['manifest_sha256'],
                    actor_id=actor.actor_id,reason=reason,observed_checkpoint=observed,observed_at=timestamp())
            result = self.session.mutate('runtime.abandon', capture_key, body, observed, key, invoke,
                                         lambda value,before:dict(records=[],result=value),scope='admin')
            guard.confirmed()
            return result

    def _barrier(self, descriptor):
        # Native creation fsyncs all staged files before its atomic rename. This
        # explicit barrier also closes a previous parent-fsync unknown outcome.
        from runtime_snapshots import sync_directory
        root = self.owner.path / descriptor['manifest_sha256']
        if descriptor['root'] != str(root): _fail('Current runtime binding differs.', 'stale', 409)
        for directory in (root, self.owner.path, self.owner.path.parent): sync_directory(directory)

    def _replay(self, key, body, expected_checkpoint):
        def forbidden(): _fail('Runtime replay has no canonical receipt.', 'unavailable', 409)
        return self.session.mutate('runtime.capture', body['expected_inventory_sha256'], body,
            expected_checkpoint, key, forbidden, lambda *args: forbidden(), scope='admin')

    def capture(self, config_request, expected_inventory_sha256, expected_checkpoint, key, *, reserve_bytes=DEFAULT_RESERVE):
        """Explicitly capture bytes after durable intent and current quiescence.

        The resolver is trusted current-host configuration authority. It must not
        derive source directories from canonical descriptors or historical roots.
        """
        _key(key); _sha(expected_checkpoint)
        body = _body(config_request, expected_inventory_sha256, reserve_bytes)
        body_sha = _intent_input(body)
        intent = None
        with self.access.lock, self.session.lock, self.db.lock:
            actor = self._authorize('runtime_snapshots.create'); self.session.check()
            receipts = operation_records(self.session.snapshot['records'])
            if any(r['operation']=='runtime.abandon' and r['result']['capture_key']==key for r in receipts.values()):
                _fail('This capture was abandoned; use a fresh key for a new measurement.', 'conflict', 409)
            if (_intent_key(key) in receipts and key not in receipts
                    and self.execution.runtime_pending(key) is None):
                _fail('This incomplete capture intent is inert history; use a fresh key for a new capture.', 'unavailable', 409)
            try:
                with self.execution.runtime_effect(key, body_sha, expected_inventory_sha256) as guard:
                    receipts = operation_records(self.session.snapshot['records'])
                    if key in receipts:
                        result = self._replay(key, body, expected_checkpoint)
                        descriptor = self.owner.get(expected_inventory_sha256)
                        from pipeline import digest
                        if digest(descriptor) != result['runtime_ref']['sha256']:
                            _fail('Acknowledged runtime belongs to a different local binding; capture with a new key.', 'unavailable', 409)
                        guard.publication_started()
                        self._barrier(descriptor); guard.confirmed()
                        return result
                    config = None
                    if _intent_key(key) in receipts:
                        def invalid(): _fail('Runtime intent replay is unavailable.', 'unavailable', 409)
                        intent = self.session.mutate('runtime.capture_intent', expected_inventory_sha256, body,
                            expected_checkpoint, _intent_key(key), invalid, lambda *args: invalid(), scope='admin')
                    else:
                        if expected_checkpoint != self.session.snapshot['checkpoint']:
                            _fail('Expected project checkpoint changed.', 'stale_project', 409)
                        config = self.resolve_configuration(copy.deepcopy(config_request))
                        observed = self.owner.inspect(config)
                        if observed['inventory_sha256'] != expected_inventory_sha256:
                            _fail('Runtime inventory changed after inspection.', 'stale', 409)
                        intent = self.session.mutate('runtime.capture_intent', expected_inventory_sha256, body,
                            expected_checkpoint, _intent_key(key),
                            lambda:_summary(self.session.snapshot['project_id'], observed, actor.actor_id, key),
                            lambda result,before:dict(records=[],result=result), scope='admin')
                    guard.publication_started()
                    if os.path.lexists(self.owner.path / expected_inventory_sha256):
                        descriptor = self.owner.get(expected_inventory_sha256)
                    else:
                        if config is None: config = self.resolve_configuration(copy.deepcopy(config_request))
                        descriptor = self.owner.create(config, expected_inventory_sha256, quiesced=True, reserve_bytes=reserve_bytes)
                    self._barrier(descriptor)
                    from recipe_process import read_regular, decode
                    from pipeline import digest
                    from pathlib import Path
                    raw = read_regular(Path(descriptor['root'])/'manifest.json', MAX_MANIFEST)
                    runtime_ref = dict(kind='runtime',catalog_id=self.session.snapshot['project_id'],
                                       id=digest(descriptor),sha256=digest(descriptor))
                    value = dict(ref=runtime_ref,descriptor=descriptor,environment=None,manifest=decode(raw))
                    observed = dict(inventory_sha256=descriptor['manifest_sha256'],file_count=descriptor['file_count'],total_bytes=descriptor['total_bytes'])
                    def capture(result, before):
                        record = self.materials.capture_runtime(value, raw)
                        return dict(records=[*self.materials.declarations(record),record],result=result)
                    result = self.session.mutate('runtime.capture', expected_inventory_sha256, body,
                        self.session.snapshot['checkpoint'], key,
                        lambda:_summary(self.session.snapshot['project_id'], observed, actor.actor_id, key, runtime_ref=runtime_ref), capture, scope='admin')
                    guard.confirmed()
                    return result
            except BaseException as error:
                if isinstance(error, (OSError, RuntimeError)):
                    failure = WorkbenchError('Runtime capture outcome requires explicit same-key reconciliation.',
                                             'outcome_unknown' if intent else 'unavailable', 503)
                else: failure = error
                if intent is not None and not hasattr(failure, 'receipt'):
                    snapshot = self.session.snapshot
                    failure.receipt = dict(committed=True,selected=True,project_id=snapshot['project_id'],
                                           checkpoint=snapshot['checkpoint'],request_key=key)
                if failure is error: raise
                raise failure from error
