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
OPERATION_FORMAT = 'project_operation_v2'
REQUEST_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
SHA = re.compile(r'^[a-f0-9]{64}$')
OPERATION = re.compile(r'^[a-z][a-z0-9_.]{0,119}$')


class ProjectSessionError(WorkbenchError):
    pass


def _digest(value):
    return hashlib.sha256(agent_api.encoded(value)).hexdigest()


def operation_documents(records):
    """Validate all historical receipts without collapsing independent keys."""
    result, seen = [], set()
    for envelope in records:
        if envelope['family'] != OPERATION_FAMILY:
            continue
        value = envelope['document']
        base = {'format', 'operation', 'target', 'request_key', 'input_sha256', 'result'}
        namespaced = type(value) is dict and value.get('format') == 'project_operation_v2'
        if (type(value) is not dict or set(value) != base | ({'project_id'} if namespaced else set())
                or value['format'] not in ('project_operation_v1', 'project_operation_v2')
                or type(value['operation']) is not str or not OPERATION.fullmatch(value['operation'])
                or value['target'] is not None and (type(value['target']) is not str or len(value['target']) > 512)
                or type(value['request_key']) is not str or not REQUEST_KEY.fullmatch(value['request_key'])
                or type(value['input_sha256']) is not str or not SHA.fullmatch(value['input_sha256'])):
            raise ProjectSessionError('Invalid canonical project operation receipt.')
        identity = hashlib.sha256(value['request_key'].encode('utf-8')).hexdigest()
        if namespaced:
            if type(value['project_id']) is not str or not re.fullmatch('[a-f0-9]{32}', value['project_id']):
                raise ProjectSessionError('Invalid project operation namespace.')
            identity = value['project_id'] + '.' + identity
        if envelope['id'] != identity or identity in seen:
            raise ProjectSessionError('Invalid or duplicate canonical project operation identity.')
        seen.add(identity)
        if len(agent_api.encoded(value['result'])) > agent_api.RESPONSE_LIMIT:
            raise ProjectSessionError('Canonical operation result exceeds its transport bound.', 'too_large', 413)
        result.append(copy.deepcopy(value))
    return result


def operation_records(records, *, project_id=None):
    """Current request keys are independent of exactly retained fork history."""
    operation_documents(records)
    from project_fork import active_records, decode_fork
    overlay = decode_fork(records, project_id=project_id)
    if project_id is None and overlay is not None:
        project_id = overlay['destination_project_id']
    result = {}
    for value in operation_documents(active_records(records, project_id=project_id)):
        if overlay is not None and value['format'] == 'project_operation_v1':
            raise ProjectSessionError('A fork must retain legacy operation receipts as archived historical facts.')
        if project_id is not None and value.get('project_id', project_id) != project_id:
            raise ProjectSessionError('Active project operation belongs to another namespace.')
        if value['request_key'] in result:
            raise ProjectSessionError('Duplicate active project operation request key.')
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
        self.project_id = store.snapshot()['project_id']
        self.extra_capture = None
        self.publication_intent = None
        self.runtime_access = None
        self._foreground_publication = False
        self._pending_observation = None
        self._recovery_records = None
        self._recovery_request = None
        self.adopt(store.snapshot())

    @property
    def foreground_publication(self):
        return self._foreground_publication

    @staticmethod
    def _merge(records, upserts):
        merged = {(item['family'], item['id']): copy.deepcopy(item) for item in records}
        seen = {}
        for item in upserts:
            if type(item) is not dict or set(item) != {'family', 'id', 'document'}:
                raise ProjectSessionError('Invalid owned project envelope.')
            identity = (item['family'], item['id'])
            if item['family'] == OPERATION_FAMILY:
                raise ProjectSessionError('Owned capture cannot replace a project operation receipt.')
            if identity in seen and seen[identity] != item:
                raise ProjectSessionError('Owned captures disagree about the same project record.')
            seen[identity] = item
            merged[identity] = copy.deepcopy(item)
        return merged

    def _publish_observation(self, records, key, digest, *, authorize):
        """Publish fixed background science while its owned SQL TX is open.

        This is a private trusted-owner seam, not a transport operation or an
        imported receipt capability. The callback verifies current local job
        custody/admission. SQL outcome selects or fences the resulting cache.
        """
        if (self.foreground_publication or not self.db.in_transaction
                or not self.db.lock.depth or self._pending_observation is not None):
            raise ProjectSessionError('Background publication requires its own outer project transaction.')
        if (type(records) is not list or type(key) is not str or not REQUEST_KEY.fullmatch(key)
                or type(digest) is not str or not SHA.fullmatch(digest) or not callable(authorize)):
            raise ProjectSessionError('Invalid background publication identity.')
        authorize()
        current = self.check()
        merged = self._merge(current['records'], records)
        candidate = [merged[identity] for identity in sorted(merged)]
        self._validated(candidate)
        if self.publication_intent is not None:
            self.publication_intent(copy.deepcopy(current), copy.deepcopy(candidate), key, digest)
        try:
            self._pending_observation = self.store.commit(candidate, current['checkpoint'], key, digest)
        except BaseException as error:
            if getattr(error, 'code', None) in ('unknown', 'outcome_unknown'):
                self.available = False
                self._recovery_records = copy.deepcopy(candidate)
                self._recovery_request = (key, digest)
            raise
        return copy.deepcopy(self._pending_observation)

    def _observation_outcome(self, outcome):
        if outcome not in ('committed', 'rolled_back', 'unknown'):
            raise ValueError('Invalid project SQL outcome.')
        pending, self._pending_observation = self._pending_observation, None
        if pending is not None:
            self._snapshot = pending
            if outcome != 'committed':
                self.available = False
        if outcome == 'unknown':
            self.available = False

    def reconcile_selection(self, snapshot):
        """Bind only this owner's selected or uncertain publication, never a checkout.

        The execution controller first proves local cessation. Callers retain
        all ordered guards until fixed inert reconstruction succeeds or fences.
        """
        with self.access.lock, self.lock, self.db.lock:
            known = snapshot == self._snapshot
            attempted = (self._recovery_records is not None
                         and snapshot['project_id'] == self._snapshot['project_id']
                         and snapshot['name'] == self._snapshot['name']
                         and snapshot['records'] == self._recovery_records
                         and self._recovery_request is not None
                         and self.store.reconcile(*self._recovery_request) is not None)
            if not known and not attempted:
                raise ProjectSessionError('Canonical selection differs from this local execution outcome.', 'stale_project', 409)
            self.adopt(snapshot)
            self._recovery_records = None
            self._recovery_request = None

    @property
    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self._snapshot)

    def _validated(self, records):
        operation_records(records, project_id=self.project_id)
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
        attempted_records = None
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
                self._foreground_publication = True
                with self.db.transaction():
                    result = invoke()
                    captured = capture(result, copy.deepcopy(current['records']))
                    if type(captured) is not dict or set(captured) != {'records', 'result'} or type(captured['records']) is not list:
                        raise ProjectSessionError('Invalid owned project capture.')
                    if len(agent_api.encoded(captured['result'])) > agent_api.RESPONSE_LIMIT:
                        raise ProjectSessionError('Project result exceeds its transport bound.', 'too_large', 413)
                    upserts = captured['records']
                    if self.extra_capture is not None:
                        extra = self.extra_capture(copy.deepcopy(current['records']))
                        if type(extra) is not list:
                            raise ProjectSessionError('Invalid fixed runtime capture.')
                        upserts = upserts + extra
                    merged = self._merge(current['records'], upserts)
                    document = dict(format=OPERATION_FORMAT, project_id=self.project_id, operation=operation, target=target,
                                    request_key=key, input_sha256=digest, result=copy.deepcopy(captured['result']))
                    identity = (OPERATION_FAMILY, self.project_id + '.' + hashlib.sha256(key.encode('utf-8')).hexdigest())
                    merged[identity] = dict(family=identity[0], id=identity[1], document=document)
                    records = [merged[identity] for identity in sorted(merged)]
                    self._validated(records)
                    # Unique payloads have already reached artifact custody;
                    # SQL callbacks can delete only disposable projection files.
                    attempted_records = records
                    if self.publication_intent is not None:
                        self.publication_intent(copy.deepcopy(current), copy.deepcopy(records), key, digest)
                    committed = self.store.commit(records, current['checkpoint'], key, digest)
                    # Outcome hooks see canonical selection before SQL outcome
                    # and before any deferred dispatch/wake can run.
                    self._pending_observation = committed
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
                    if attempted_records is not None:
                        self._recovery_records = copy.deepcopy(attempted_records)
                        self._recovery_request = (key, digest)
                raise
            finally:
                self._foreground_publication = False
                self._pending_observation = None
