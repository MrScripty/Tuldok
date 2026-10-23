"""M1 text documents: canonical files own facts; Workbench owns text semantics.

Only import and annotation are admitted by this slice. Reconstruction never
constructs Dataset, Jobs, Runs, or imports Access tables. The document decoder is
the closed workbench_text_v1 persisted contract; new families require their owner.
"""
import copy
from datetime import datetime
import hashlib
import re
import threading
from types import SimpleNamespace
import unicodedata

from workbench import (Workbench, WorkbenchError, IDENTIFIER, MAX_TEXT, encode,
                       strings, text_value, timestamp, validate_annotation)


class ProjectTextError(WorkbenchError):
    pass


def _invalid(message):
    raise ProjectTextError(message, 'invalid', 400)


def _sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _shape(value, fields, name):
    if type(value) is not dict or set(value) != set(fields):
        _invalid('Invalid ' + name + ' fields.')


def _time(value):
    if type(value) is not str or len(value) > 64:
        _invalid('Invalid text timestamp.')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except (ValueError, OverflowError):
        _invalid('Invalid text timestamp.')


SNAPSHOT_FIELDS = set('id kind name text content_hash pixel_hash groups parents provenance task annotation review revision created_at updated_at width height source_revision source_sha256 book_id session_id source_split corner_annotation source_available source_lineage_known'.split())
IMMUTABLE_FIELDS = set('id kind name text content_hash pixel_hash parents provenance created_at width height source_revision source_sha256 book_id session_id source_split corner_annotation source_available source_lineage_known'.split())
AUDIT_ACTIONS = {'workbench.import_asset', 'workbench.save', 'workbench.approve_review'}
SHA256 = re.compile(r'^[a-f0-9]{64}$')
REQUEST_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


def _snapshot(value, identity, original):
    _shape(value, SNAPSHOT_FIELDS, 'text snapshot')
    if value['id'] != identity or value['kind'] != 'text':
        _invalid('Text snapshot identity mismatch.')
    if type(value['revision']) is not int or value['revision'] < 1:
        _invalid('Invalid text revision.')
    if type(value['source_revision']) is not int or value['source_revision'] != 1:
        _invalid('Invalid text source revision.')
    if any(value[key] is not None for key in ('pixel_hash', 'width', 'height', 'book_id', 'session_id', 'corner_annotation')):
        _invalid('Text snapshot contains non-text source fields.')
    if value['source_available'] is not True or value['source_lineage_known'] is not True or value['source_split'] != 'unassigned':
        _invalid('Invalid text source state.')
    if text_value(value['name'], 'Name') != value['name']:
        _invalid('Text name must retain canonical spelling.')
    normalized = unicodedata.normalize('NFC', original.replace('\r\n', '\n').replace('\r', '\n'))
    if value['text'] != normalized or value['content_hash'] != _sha(normalized) or value['source_sha256'] != _sha(original):
        _invalid('Text source, normalization or hash mismatch.')
    for key in ('groups', 'parents'):
        if strings(value[key], key) != value[key] or (key == 'groups' and not value[key]):
            _invalid('Invalid text ' + key + '.')
    if any(not IDENTIFIER.fullmatch(parent) for parent in value['parents']):
        _invalid('Invalid text parent identity.')
    origin = value['provenance']
    _shape(origin, {'method', 'rights', 'normalization'}, 'text provenance')
    if origin['method'] != 'import' or origin['normalization'] != 'NFC; LF newlines' or text_value(origin['rights'], 'Rights', 1000) != origin['rights']:
        _invalid('Unsupported text provenance.')
    if value['task'] not in ('text_classification', 'text_entities', 'text_corpus') or value['review'] not in ('draft', 'human_reviewed'):
        _invalid('Invalid text task or review.')
    if value['annotation'] is None:
        if value['revision'] != 1 or value['task'] != 'text_classification' or value['review'] != 'draft':
            _invalid('Missing text annotation after import.')
    elif validate_annotation(value['task'], value['annotation'], value) != value['annotation']:
        _invalid('Text annotation is not canonical.')
    if _time(value['updated_at']) < _time(value['created_at']):
        _invalid('Text update precedes creation.')


def decode_records(records):
    """Validate complete text closure before any SQL write; return an owned copy."""
    if type(records) is not list or len(records) > 100_000:
        _invalid('Project text records must be a bounded list.')
    documents, operations, hashes = {}, set(), set()
    for envelope in records:
        _shape(envelope, {'family', 'id', 'document'}, 'text envelope')
        if envelope['family'] != 'workbench_text':
            raise ProjectTextError('Unsupported project record family.', 'unsupported', 409)
        identity, document = envelope['id'], envelope['document']
        if type(identity) is not str or not IDENTIFIER.fullmatch(identity) or identity in documents:
            _invalid('Invalid or duplicate text identity.')
        if type(document) is not dict:
            _invalid('Text document must be an object.')
        if document.get('format') != 'workbench_text_v1':
            raise ProjectTextError('Unsupported text document format.', 'unsupported', 409)
        _shape(document, {'format', 'original_text', 'current', 'history', 'audit', 'operations'}, 'text document')
        original = document['original_text']
        text_value(original, 'Original text', MAX_TEXT)
        history = document['history']
        if type(history) is not list or not history:
            _invalid('Text history must contain every revision.')
        previous = None
        for revision, state in enumerate(history, 1):
            _snapshot(state, identity, original)
            if state['revision'] != revision:
                _invalid('Text history revisions must be contiguous.')
            if previous and (any(state[key] != previous[key] for key in IMMUTABLE_FIELDS) or _time(state['updated_at']) < _time(previous['updated_at'])):
                _invalid('Text history changes immutable source or reverses time.')
            previous = state
        _snapshot(document['current'], identity, original)
        if document['current'] != history[-1] or history[0]['annotation'] is not None:
            _invalid('Text current value or initial history is inconsistent.')
        if document['current']['content_hash'] in hashes:
            _invalid('Duplicate canonical text.')
        hashes.add(document['current']['content_hash'])
        audit, receipts = document['audit'], document['operations']
        if type(audit) is not list or type(receipts) is not list or len(audit) != len(history) or len(receipts) != len(history):
            _invalid('Every text revision requires its audit and operation facts.')
        for revision, (fact, receipt, state) in enumerate(zip(audit, receipts, history), 1):
            _shape(fact, {'action', 'target', 'details', 'result', 'actor_id', 'occurred_at'}, 'text audit')
            expected_action = 'workbench.import_asset' if revision == 1 else 'workbench.approve_review' if state['review'] == 'human_reviewed' else 'workbench.save'
            details = {'revision': revision, 'source_revision': 1, 'content_sha256': _sha(encode(state))}
            if revision > 1:
                details.update(before_revision=revision - 1, before_source_revision=1)
            _shape(fact['details'], details, 'text audit details')
            if any(type(fact['details'][key]) is not type(expected) for key, expected in details.items()):
                _invalid('Invalid text audit detail types.')
            if fact['action'] != expected_action or fact['target'] != identity or fact['details'] != details or fact['result'] != 'success':
                _invalid('Invalid text audit evidence.')
            if type(fact['actor_id']) is not str or not IDENTIFIER.fullmatch(fact['actor_id']):
                _invalid('Invalid historical text actor identity.')
            if _time(fact['occurred_at']) < _time(state['updated_at']):
                _invalid('Text audit precedes its mutation.')
            _shape(receipt, {'request_key', 'request_sha256', 'action', 'target', 'revision'}, 'text operation')
            key, digest = receipt['request_key'], receipt['request_sha256']
            if type(key) is not str or not REQUEST_KEY.fullmatch(key) or key in operations or type(digest) is not str or not SHA256.fullmatch(digest):
                _invalid('Invalid or duplicate text operation identity.')
            if receipt['target'] != identity or type(receipt['revision']) is not int or receipt['revision'] != revision or receipt['action'] != ('import_text' if revision == 1 else 'annotate'):
                _invalid('Text operation revision or target mismatch.')
            operations.add(key)
        documents[identity] = document
    # Parents are authored source lineage. They must exist, precede children,
    # and form a closed acyclic graph; no foreign family can supply authority.
    for identity, document in documents.items():
        current = document['current']
        for parent in current['parents']:
            if parent not in documents or _time(documents[parent]['current']['created_at']) > _time(current['created_at']):
                _invalid('Text parent reference is missing or newer than its child.')
    visiting, visited = set(), set()
    for identity in documents:
        stack = [(identity, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                visiting.remove(node)
                visited.add(node)
            elif node not in visited:
                if node in visiting:
                    _invalid('Text parent lineage contains a cycle.')
                visiting.add(node)
                stack.append((node, True))
                stack.extend((parent, False) for parent in documents[node]['current']['parents'])
    return copy.deepcopy(records)


class _HostAccess:
    """Current authorization stays at the installation; only inert facts travel."""
    def __init__(self, host):
        self.host, self.facts = host, None

    def require(self, *args, **kwargs):
        return self.host.require(*args, **kwargs)

    def denial(self, *args, **kwargs):
        return self.host.denial(*args, **kwargs)

    def audit(self, action, target=None, details=None, result='success'):
        if self.facts is None or action not in AUDIT_ACTIONS or result != 'success':
            raise ProjectTextError('This project operation is unavailable in M1.', 'unavailable', 409)
        context = self.host.require('edit', action, target)
        self.facts.append(dict(action=action, target=target, details=copy.deepcopy(details or {}),
                               result=result, actor_id=context.actor_id, occurred_at=timestamp()))


class ProjectText:
    def __init__(self, store, db, access):
        self.store, self.db, self.access = store, db, access
        self._lock = threading.RLock()
        self._authority = _HostAccess(access)
        inert = SimpleNamespace(db=db, lock=db.lock, path=db.path, access=self._authority)
        self._workbench = Workbench(inert)
        self._snapshot = None
        self.available = False

    @property
    def checkpoint(self):
        return self._snapshot['checkpoint'] if self._snapshot else None

    def _authorize(self, scope, action, target=None):
        self.access.require(scope, action, target)

    def _bound(self):
        if not self.available:
            raise ProjectTextError('Project projection requires reconstruction.', 'projection_unavailable', 503)
        current = self.store.snapshot()
        if current['checkpoint'] != self.checkpoint:
            raise ProjectTextError('Project changed outside this projection. Reload it.', 'stale_project', 409)
        return current

    def _tag(self, value, request_key=None):
        result = dict(value, project_id=self._snapshot['project_id'], checkpoint=self.checkpoint)
        if request_key is not None:
            result['request_key'] = request_key
        return result

    def restore(self, snapshot=None):
        """Replace only this disposable text projection after full validation."""
        with self._lock, self.db.lock:
            if self.db.in_transaction:
                raise ProjectTextError('Reconstruction must own its SQL transaction.', 'unavailable', 409)
            current = self.store.snapshot()
            if snapshot is not None and snapshot != current:
                raise ProjectTextError('Restore snapshot is stale.', 'stale_project', 409)
            records = decode_records(current['records'])
            self.available = False
            with self.db.transaction():
                if self.db.execute("SELECT 1 FROM workbench_records WHERE kind<>'text' LIMIT 1").fetchone() or self.db.execute('SELECT 1 FROM samples LIMIT 1').fetchone():
                    raise ProjectTextError('M1 requires an isolated text projection.', 'unavailable', 409)
                self.db.execute('DELETE FROM workbench_history')
                self.db.execute('DELETE FROM workbench_rights_notes')
                self.db.execute('DELETE FROM workbench_target_proposals')
                self.db.execute('DELETE FROM workbench_records')
                for envelope in records:
                    doc, row = envelope['document'], envelope['document']['current']
                    self.db.execute('''INSERT INTO workbench_records
                        (id,kind,name,text,original_text,content_hash,pixel_hash,groups_json,parents_json,provenance_json,task,annotation_json,review,revision,created_at,updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (row['id'], 'text', row['name'], row['text'], doc['original_text'], row['content_hash'], None,
                         encode(row['groups']), encode(row['parents']), encode(row['provenance']), row['task'],
                         encode(row['annotation']) if row['annotation'] is not None else None, row['review'], row['revision'], row['created_at'], row['updated_at']))
                    for state in doc['history']:
                        self._workbench._history(state)
                if self.store.snapshot()['checkpoint'] != current['checkpoint']:
                    raise ProjectTextError('Project changed during reconstruction.', 'stale_project', 409)
            self._snapshot, self.available = current, True
            return copy.deepcopy(current)

    def query(self, options=None):
        with self.access.lock, self._lock, self.db.lock:
            self._authorize('inspect', 'workbench.query')
            self._bound()
            result = self._workbench.query(options or {})
            self._bound()
            return self._tag(result)

    def records(self):
        """Full current values for the controller's bounded public projection.

        Canonical values come from one verified snapshot, avoiding pagination
        truncation and repeated full inventory reads for each individual row.
        """
        with self.access.lock, self._lock, self.db.lock:
            self._authorize('inspect', 'workbench.query')
            current = self._bound()
            return self._tag({'items': [envelope['document']['current'] for envelope in current['records']]})

    def get(self, record_id):
        with self.access.lock, self._lock, self.db.lock:
            self._authorize('inspect', 'workbench.get', record_id)
            self._bound()
            result = self._workbench.get(record_id)
            self._bound()
            return self._tag(result)

    def history(self, record_id):
        with self.access.lock, self._lock, self.db.lock:
            self._authorize('inspect', 'workbench.history', record_id)
            self._bound()
            result = self._workbench.history(record_id)
            self._bound()
            return [self._tag(state) for state in result]

    def import_text(self, body, expected_checkpoint, request_key):
        if type(body) is not dict or set(body) - {'kind', 'text', 'name', 'groups', 'parents', 'rights'} or body.get('kind', 'text') != 'text':
            raise ProjectTextError('Only text import is available in M1.', 'unavailable', 409)
        return self._mutate('import_text', None, body, expected_checkpoint, request_key)

    def annotate(self, record_id, body, expected_checkpoint, request_key):
        _shape(body, {'revision', 'source_revision', 'task', 'annotation', 'groups', 'review'}, 'annotation request')
        if body['task'] not in ('text_classification', 'text_entities', 'text_corpus') or body['review'] not in ('draft', 'human_reviewed'):
            raise ProjectTextError('This annotation operation is unavailable in M1.', 'unavailable', 409)
        return self._mutate('annotate', record_id, body, expected_checkpoint, request_key)

    def _mutate(self, action, record_id, body, expected_checkpoint, request_key):
        # Current owner permission cannot be revoked between authorization and
        # canonical publication. Match the controller's host-before-projection
        # lock order, including standalone callers of this domain adapter.
        with self.access.lock:
            return self._mutate_authorized(action, record_id, body, expected_checkpoint, request_key)

    def _mutate_authorized(self, action, record_id, body, expected_checkpoint, request_key):
        self._authorize('edit', 'workbench.import_asset' if action == 'import_text' else 'workbench.save', record_id)
        if type(request_key) is not str or not REQUEST_KEY.fullmatch(request_key):
            _invalid('Supply a bounded operation request key.')
        body = copy.deepcopy(body)
        try:
            digest = _sha(encode(dict(action=action, target=record_id, body=body)))
        except (ValueError, TypeError, UnicodeError):
            _invalid('Project mutation must contain valid finite JSON.')
        with self._lock, self.db.lock:
            if self.db.in_transaction:
                raise ProjectTextError('Project mutation must own its SQL transaction.', 'unavailable', 409)
            current = self._bound()
            replay = self.store.reconcile(request_key, digest)
            if replay is not None:
                for envelope in current['records']:
                    doc = envelope['document']
                    for receipt in doc['operations']:
                        if receipt['request_key'] == request_key and receipt['request_sha256'] == digest:
                            return self._tag(doc['history'][receipt['revision'] - 1], request_key)
                _invalid('Project operation receipt has no text result.')
            if expected_checkpoint != self.checkpoint:
                raise ProjectTextError('Expected project checkpoint changed.', 'conflict', 409)
            committed = None
            self._authority.facts = []
            try:
                with self.db.transaction():
                    result = (self._workbench.import_asset(dict(body, kind='text')) if action == 'import_text'
                              else self._workbench.save(record_id, body))
                    identity = result['id']
                    records = copy.deepcopy(current['records'])
                    envelope = next((item for item in records if item['id'] == identity), None)
                    if envelope is None:
                        original = self.db.execute('SELECT original_text FROM workbench_records WHERE id=%s', (identity,)).fetchone()[0]
                        envelope = dict(family='workbench_text', id=identity,
                                        document=dict(format='workbench_text_v1', original_text=original, current=None, history=[], audit=[], operations=[]))
                        records.append(envelope)
                    document = envelope['document']
                    document['current'] = result
                    document['history'].append(result)
                    document['audit'].extend(self._authority.facts)
                    document['operations'].append(dict(request_key=request_key, request_sha256=digest, action=action,
                                                       target=identity, revision=result['revision']))
                    records = decode_records(records)
                    # Canonical publication is inside the outer SQL transaction,
                    # so Workbench savepoints cannot acknowledge DB-only work.
                    committed = self.store.commit(records, self.checkpoint, request_key, digest)
                self._snapshot = committed
                return self._tag(result, request_key)
            except BaseException as error:
                if committed is not None:
                    self._snapshot, self.available = committed, False
                    failure = ProjectTextError('Canonical edit committed; reconstruct the unavailable SQL projection.', 'projection_unavailable', 503)
                    failure.committed, failure.project_id = True, committed['project_id']
                    failure.checkpoint, failure.request_key = committed['checkpoint'], request_key
                    failure.receipt = dict(committed=True, selected=True, project_id=committed['project_id'],
                                           checkpoint=committed['checkpoint'], request_key=request_key)
                    raise failure from error
                if getattr(error, 'code', None) in ('unknown', 'outcome_unknown'):
                    self.available = False
                raise
            finally:
                self._authority.facts = None
