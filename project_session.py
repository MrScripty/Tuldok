"""Canonical publication shared by the fixed external-project domain owners.

The supplied validator composes those owners' closed codecs and reference
closure. This boundary owns transaction ordering and receipts, not domain policy.
"""
import copy
import hashlib
import re
import threading

import agent_api
from workbench import WorkbenchError


OPERATION_FAMILY = 'project_operation'
OPERATION_FORMAT = 'project_operation_v1'
REQUEST_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
OPERATION = re.compile(r'^[a-z][a-z0-9_.]{0,119}$')


class ProjectSessionError(WorkbenchError):
    pass


def _digest(value):
    return hashlib.sha256(agent_api.encoded(value)).hexdigest()


def operation_records(records):
    """Decode transport receipts; the composed owner validates result meaning."""
    result = {}
    for envelope in records:
        if envelope['family'] != OPERATION_FAMILY:
            continue
        value = envelope['document']
        if (type(value) is not dict or set(value) != {
                'format', 'operation', 'target', 'request_key', 'input_sha256', 'result'}
                or value['format'] != OPERATION_FORMAT
                or type(value['operation']) is not str or not OPERATION.fullmatch(value['operation'])
                or value['target'] is not None and (type(value['target']) is not str or len(value['target']) > 512)
                or type(value['request_key']) is not str or not REQUEST_KEY.fullmatch(value['request_key'])
                or type(value['input_sha256']) is not str or not SHA.fullmatch(value['input_sha256'])
                or envelope['id'] != hashlib.sha256(value['request_key'].encode('utf-8')).hexdigest()
                or value['request_key'] in result):
            raise ProjectSessionError('Invalid canonical project operation receipt.')
        # Enforce the public bounded-result transport independently of the
        # storage document bound. Never truncate a committed result on replay.
        if len(agent_api.encoded(value['result'])) > agent_api.RESPONSE_LIMIT:
            raise ProjectSessionError('Canonical operation result exceeds its transport bound.', 'too_large', 413)
        result[value['request_key']] = value
    return result


class ProjectSession:
    def __init__(self, store, db, access, artifacts, *, validate_records):
        if not callable(validate_records):
            raise TypeError('A complete owner-codec validator is required.')
        self.store, self.db, self.access, self.artifacts = store, db, access, artifacts
        self.lock = threading.RLock()
        self._validate = validate_records
        self.available = False
        self._snapshot = None
        self.adopt(store.snapshot())

    @property
    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self._snapshot)

    def _validated(self, records):
        operation_records(records)
        self._validate(records)

    def adopt(self, snapshot):
        """Bind a fully validated checkpoint after inert reconstruction/cutover.

        The caller owns SQL reconstruction. This method never repairs or writes
        canonical bytes, and is not authorization to trust an imported receipt.
        """
        with self.access.lock, self.lock, self.db.lock:
            self._validated(snapshot['records'])
            current = self.store.snapshot()
            if current != snapshot:
                raise ProjectSessionError('Project changed while binding its projection.', 'stale_project', 409)
            self._snapshot = copy.deepcopy(snapshot)
            self.available = True

    def check(self):
        """Check freshness while a caller holds host/session/projection guards."""
        if not self.available:
            raise ProjectSessionError('Reopen this project to reconstruct its projection.', 'projection_unavailable', 503)
        current = self.store.snapshot()
        if current['checkpoint'] != self._snapshot['checkpoint']:
            raise ProjectSessionError('Canonical project changed. Close and reopen it.', 'stale_project', 409)
        return current

    def mutate(self, operation, target, body, expected_checkpoint, key, invoke, capture, *, scope='edit'):
        """Invoke existing policy, capture fixed-owner upserts, publish, commit SQL.

        invoke() returns the owner's result. capture(result, before_records)
        returns {'records': upserts, 'result': original bounded domain result}.
        Wrappers check any stronger scope/owner/disclosure requirement before
        entering, including before replay. The supplied current scope belongs to
        the wrapper's existing policy (for example freeze rather than edit).
        """
        if (type(operation) is not str or not OPERATION.fullmatch(operation)
                or target is not None and (type(target) is not str or len(target) > 512)
                or type(key) is not str or not REQUEST_KEY.fullmatch(key)
                or type(expected_checkpoint) is not str or not SHA.fullmatch(expected_checkpoint)):
            raise ProjectSessionError('Invalid project mutation identity.')
        digest = _digest(dict(operation=operation, target=target, body=body))
        committed = None
        with self.access.lock, self.lock, self.db.lock:
            self.access.require(scope, operation, target)
            current = self.check()
            if self.db.in_transaction:
                raise ProjectSessionError('Project mutation must own its outer SQL transaction.', 'unavailable', 409)
            receipts = operation_records(current['records'])
            prior = receipts.get(key)
            if prior is not None:
                if prior['operation'] != operation or prior['input_sha256'] != digest or prior['target'] != target:
                    raise ProjectSessionError('Request key already has different input.', 'conflict', 409)
                # The current composed codec validates the exact historical
                # result too; receipt facts can never authorize execution.
                self._validated(current['records'])
                return copy.deepcopy(prior['result'])
            if self.store.reconcile(key, digest) is not None:
                raise ProjectSessionError('Request key belongs to another canonical operation.', 'conflict', 409)
            if expected_checkpoint != current['checkpoint']:
                raise ProjectSessionError('Expected project checkpoint changed.', 'stale_project', 409)
            try:
                with self.db.transaction():
                    result = invoke()
                    captured = capture(result, copy.deepcopy(current['records']))
                    if type(captured) is not dict or set(captured) != {'records', 'result'} or type(captured['records']) is not list:
                        raise ProjectSessionError('Invalid owned project capture.')
                    if len(agent_api.encoded(captured['result'])) > agent_api.RESPONSE_LIMIT:
                        raise ProjectSessionError('Project result exceeds its transport bound.', 'too_large', 413)
                    merged = {(item['family'], item['id']): copy.deepcopy(item) for item in current['records']}
                    seen = set()
                    for item in captured['records']:
                        if type(item) is not dict or set(item) != {'family', 'id', 'document'}:
                            raise ProjectSessionError('Invalid owned project envelope.')
                        identity = (item['family'], item['id'])
                        if identity in seen or item['family'] == OPERATION_FAMILY:
                            raise ProjectSessionError('Owned capture cannot replace a project operation receipt.')
                        seen.add(identity)
                        merged[identity] = copy.deepcopy(item)
                    document = dict(format=OPERATION_FORMAT, operation=operation, target=target,
                                    request_key=key, input_sha256=digest, result=copy.deepcopy(captured['result']))
                    identity = (OPERATION_FAMILY, hashlib.sha256(key.encode('utf-8')).hexdigest())
                    merged[identity] = dict(family=identity[0], id=identity[1], document=document)
                    records = [merged[identity] for identity in sorted(merged)]
                    self._validated(records)
                    # Unique payloads have already reached artifact custody;
                    # SQL callbacks can delete only disposable projection files.
                    committed = self.store.commit(records, current['checkpoint'], key, digest)
                self._snapshot = committed
                return copy.deepcopy(captured['result'])
            except BaseException as error:
                if committed is not None:
                    self._snapshot, self.available = committed, False
                    failure = ProjectSessionError('Canonical operation committed; reopen to reconstruct the projection.',
                                                  'projection_unavailable', 503)
                    failure.receipt = dict(committed=True, selected=True, project_id=committed['project_id'],
                                           checkpoint=committed['checkpoint'], request_key=key)
                    raise failure from error
                if getattr(error, 'code', None) in ('unknown', 'outcome_unknown'):
                    self.available = False
                raise
