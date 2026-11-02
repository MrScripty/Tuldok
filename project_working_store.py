"""Persistent PostgreSQL working copy of one external project folder.

The database holds the current record set of an opened project and is kept
across sessions. The external folder (`.tuldok/project.json` plus
content-addressed `records/`, tracked in Git) is an import source, read only
when its checkpoint changed since Tuldok last imported or saved it, and an
export target written only by save(). See docs/plans/database-working-store.md.

Records are kept exactly as their canonical bytes with their SHA256, so the
working copy has the same manifest, checkpoint digest and receipts as the file
format and save() writes byte-identical files. This store keeps no record state
in memory: inventory, receipts and bodies are read from PostgreSQL, so an outer
transaction rollback can never leave a stale in-process copy.

Interface parity with ProjectStore (summary, snapshot, commit, save,
reconcile, root_directory, verify_records, recover_checkpoint, close, path)
lets Session, owners, artifacts and custody use either store.
"""
from contextlib import contextmanager, nullcontext
import json
import os
import re
import threading
import uuid

import psycopg
from psycopg import sql

from metadata import _key, connection_info
from project_record_dedupe import CLOSURE_FAMILY, RUN_FAMILY, compact, expand, is_compact
from project_store import (FORMAT, MAX_RECORD_BYTES, MAX_RECORDS, MAX_TOTAL_BYTES, SUPPORTED_FORMATS,
                           ProjectStoreError, _RecordsDigest, _decode, _digest, _domain_format, _encode,
                           _fail, _identifier, _keys, _manifest_raw, _request, _sha, envelope_digest)

WORKING_ID = re.compile(r'^[a-f0-9]{32}$')
_TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.state (
           singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
           project_id text NOT NULL, name text NOT NULL, checkpoint text NOT NULL,
           receipts bytea NOT NULL, external_sha256 text, dirty boolean NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS {schema}.records (
           family text COLLATE "C" NOT NULL, id text COLLATE "C" NOT NULL,
           format text NOT NULL, bytes integer NOT NULL, sha256 text NOT NULL,
           raw bytea NOT NULL, PRIMARY KEY (family, id))''',
)
_MIGRATIONS = (
    # SHA256 of the canonical {family, id, document} envelope (see envelope_digest).
    'ALTER TABLE {schema}.records ADD COLUMN IF NOT EXISTS envelope_sha256 text',
    # Shared runtime closure referenced by a compact Run row (project_record_dedupe).
    'ALTER TABLE {schema}.records ADD COLUMN IF NOT EXISTS closure_id text',
)
_ORDER = sql.SQL('ORDER BY family COLLATE "C", id COLLATE "C"')


class WorkingProjectStore:
    """One exclusive owner of a project's database working copy."""

    def __init__(self, folder, working_id, *, dsn=None, canonical_digests=None):
        if type(working_id) is not str or not WORKING_ID.fullmatch(working_id):
            raise ValueError('Invalid working copy identity.')
        self._folder = folder
        self.working_id = working_id
        self.schema = 'working_' + working_id
        self._canonical_digests = canonical_digests
        self._mutex = threading.RLock()
        self._db = None
        self._closed = False
        try:
            self._own = psycopg.connect(connection_info(dsn), autocommit=True)
        except psycopg.Error:
            raise ProjectStoreError('Local PostgreSQL is unavailable.', 'unavailable', 503) from None
        try:
            # One Tuldok process owns a working copy at a time.
            if not self._own.execute('SELECT pg_try_advisory_lock(%s)', (_key(self.schema),)).fetchone()[0]:
                raise ProjectStoreError('This project is already open in another Tuldok session.', 'busy', 409)
            with self._own.transaction():
                self._own.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
                for statement in (*_TABLES, *_MIGRATIONS):
                    self._own.execute(sql.SQL(statement).format(schema=sql.Identifier(self.schema)))
        except BaseException:
            self._own.close()
            raise

    # ---- Connection: own until bound to the projection, then shared so
    # record commits are atomic with the projection's SQL writes.

    def bind(self, db):
        """Use the projection database's connection and transactions."""
        with self._locked():
            self._db = db

    @contextmanager
    def _locked(self):
        """Store ownership in one global order: projection lock, then this mutex.

        A bound projection connection is shared with Session/owner threads that
        hold the projection lock across their transactions, so store work never
        takes its own mutex first and then waits for that lock.
        """
        if self._db is not None:
            with self._catalog_lock(), self._mutex:
                yield
        else:
            with self._mutex:
                yield

    def _catalog_lock(self):
        # The projection may install a composite host -> session -> catalog
        # lock; the store is innermost, so it takes only the catalog lock.
        lock = self._db.lock
        return getattr(lock, 'projection', lock)

    def _joined(self):
        # Join the projection only inside its open transaction (Session.mutate,
        # background publication), so record and projection rows commit
        # atomically. Other commits use this store's own connection and never
        # fire the projection's commit hooks.
        return self._db is not None and self._db.in_transaction

    def _connection(self):
        return self._db.connection if self._joined() else self._own

    def _guard(self):
        # A bound projection connection is shared; its catalog lock serializes
        # every command and transaction on it across threads.
        return self._catalog_lock() if self._joined() else nullcontext()

    @contextmanager
    def _transaction(self):
        if self._joined():
            with self._catalog_lock(), self._db.transaction():
                yield
        else:
            with self._own.transaction():
                yield

    def _execute(self, statement, parameters=None):
        if self._closed:
            _fail('Project store is closed.', 'unavailable', 409)
        with self._guard():
            return self._connection().execute(statement, parameters)

    def _q(self, text):
        return sql.SQL(text).format(state=sql.Identifier(self.schema, 'state'),
                                    records=sql.Identifier(self.schema, 'records'), order=_ORDER)

    # ---- Open: attach, import or refuse.

    @classmethod
    def open(cls, folder, working_id, *, dsn=None, canonical_digests=None):
        """Attach the working copy, importing the folder only if it changed."""
        store = cls(folder, working_id, dsn=dsn, canonical_digests=canonical_digests)
        try:
            raw, manifest = folder.folder_checkpoint()
            external = _sha(raw)
            state = store._state(required=False)
            if state is not None and state['project_id'] != manifest['project_id']:
                _fail('This working copy belongs to a different project.', 'conflict', 409)
            if state is None or state['external_sha256'] != external:
                if state is not None and state['dirty']:
                    _fail('The external project changed while this workspace has unsaved changes. '
                          'Save over it or discard the working copy and import again.', 'conflict', 409)
                store._import(raw, manifest)
            return store
        except BaseException:
            store.close()
            raise

    def _state(self, *, required=True):
        row = self._execute(self._q('SELECT project_id, name, checkpoint, receipts, external_sha256, dirty FROM {state}')).fetchone()
        if row is None:
            if required:
                _fail('Project working copy is missing.', 'unavailable', 409)
            return None
        return dict(project_id=row[0], name=row[1], checkpoint=row[2], receipts=json.loads(bytes(row[3])),
                    external_sha256=row[4], dirty=row[5])

    def _import(self, raw, manifest):
        """Bring the working copy to the folder's checkpoint, reading only new revisions."""
        with self._locked(), self._transaction():
            existing = {(row[0], row[1]): row[2] for row in
                        self._execute(self._q('SELECT family, id, sha256 FROM {records}'))}
            wanted = {}
            proven = []
            known = self._canonical_digests
            for entry in manifest['inventory']:
                identity = (entry['family'], entry['id'])
                wanted[identity] = entry
                if existing.get(identity) == entry['sha256']:
                    continue
                body = self._folder.folder_record(entry)
                if known is not None and entry['sha256'] in known:
                    document = json.loads(body)
                else:
                    document = _decode(body)
                    proven.append(entry['sha256'])
                if type(document) is not dict or document.get('format') != entry['format']:
                    _fail('Domain document format disagrees with its inventory.')
                compact_run = is_compact(entry['family'], document)
                self._execute(self._q(
                    'INSERT INTO {records} (family, id, format, bytes, sha256, raw, envelope_sha256, closure_id) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) '
                    'ON CONFLICT (family, id) DO UPDATE SET format=EXCLUDED.format, bytes=EXCLUDED.bytes, '
                    'sha256=EXCLUDED.sha256, raw=EXCLUDED.raw, envelope_sha256=EXCLUDED.envelope_sha256, '
                    'closure_id=EXCLUDED.closure_id'),
                    (entry['family'], entry['id'], entry['format'], entry['bytes'], entry['sha256'], body,
                     # A compact Run's logical envelope digest is filled from its expansion.
                     None if compact_run or entry['family'] == CLOSURE_FAMILY else envelope_digest(entry['family'], entry['id'], body),
                     document['runtime_closure']['id'] if compact_run else None))
            for family, record_id in set(existing) - set(wanted):
                self._execute(self._q('DELETE FROM {records} WHERE family=%s AND id=%s'), (family, record_id))
            if self._records_digest() != manifest['receipts'][-1]['records_sha256']:
                _fail('Latest operation receipt disagrees with the current record set.')
            self._write_state(manifest, external_sha256=_sha(raw), dirty=False)
            if known is not None and proven:
                known.add_many(proven)

    def _write_state(self, manifest, *, external_sha256, dirty):
        receipts = _encode(manifest['receipts'])
        self._execute(self._q('DELETE FROM {state}'))
        self._execute(self._q('INSERT INTO {state} (project_id, name, checkpoint, receipts, external_sha256, dirty) '
                              'VALUES (%s,%s,%s,%s,%s,%s)'),
                      (manifest['project_id'], manifest['name'], manifest['checkpoint'], receipts,
                       external_sha256, dirty))

    def _rows(self, statement, parameters=None):
        """Stream (family, id, raw) rows through a server-side cursor.

        Bodies are fetched in small batches, never the whole record set at once.
        """
        if self._closed:
            _fail('Project store is closed.', 'unavailable', 409)
        with self._guard():
            connection = self._connection()
            idle = connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            with (connection.transaction() if idle else nullcontext()), \
                    connection.cursor(name='working_' + uuid.uuid4().hex) as cursor:
                cursor.itersize = 64
                cursor.execute(statement, parameters)
                for row in cursor:
                    yield row[0], row[1], bytes(row[2])

    def _records_digest(self, replacements=None, identities=None):
        """Streamed receipt digest over the stored (or a candidate) record set."""
        digest = _RecordsDigest()
        replacements = replacements or {}
        if identities is None:
            for family, record_id, raw in self._rows(self._q('SELECT family, id, raw FROM {records} {order}')):
                digest.add(family, record_id, raw)
            return digest.hexdigest()
        stored = self._rows(self._q('SELECT family, id, raw FROM {records} {order}'))
        pending = next(stored, None)
        for identity in identities:
            while pending is not None and (pending[0], pending[1]) < identity:
                pending = next(stored, None)
            if identity in replacements:
                digest.add(identity[0], identity[1], replacements[identity])
            elif pending is not None and (pending[0], pending[1]) == identity:
                digest.add(identity[0], identity[1], pending[2])
            else:
                _fail('Unchanged candidate record is missing from the working copy.')
        return digest.hexdigest()

    # ---- Logical documents: closures hidden, compact Runs expanded.

    def _closure(self, identity):
        cache = self.__dict__.setdefault('_closures', {})
        if identity not in cache:
            row = self._execute(self._q('SELECT raw FROM {records} WHERE family=%s AND id=%s'),
                                (CLOSURE_FAMILY, identity)).fetchone()
            if row is None:
                _fail('Compact Run references a missing runtime closure.')
            cache[identity] = json.loads(bytes(row[0]))
        return cache[identity]

    def _logical(self, family, raw):
        document = json.loads(raw)
        if is_compact(family, document):
            document = expand(document, self._closure(document['runtime_closure']['id']))
        return document

    # ---- Manifest identity, identical to the file format.

    def _inventory(self):
        return [(row[0], row[1], row[2], row[3], row[4]) for row in
                self._execute(self._q('SELECT family, id, format, bytes, sha256 FROM {records} {order}'))]

    @staticmethod
    def _manifest(state, inventory):
        manifest = dict(format=FORMAT, project_id=state['project_id'], name=state['name'],
                        roots=[dict(family=f, id=i) for f, i, _fmt, _b, _s in inventory],
                        inventory=[dict(family=f, id=i, format=fmt, namespace=state['project_id'],
                                        path=f'records/{f}/{i}/{sha}.json', bytes=size, sha256=sha)
                                   for f, i, fmt, size, sha in inventory],
                        receipts=state['receipts'])
        manifest['checkpoint'] = _sha(_encode(manifest))
        return manifest

    # ---- ProjectStore interface.

    @property
    def path(self):
        return self._folder.path

    @property
    def _root_fd(self):
        """The external folder's locked physical root (read-only)."""
        return self._folder._root_fd

    def summary(self):
        with self._locked():
            state = self._state()
            return {key: state[key] for key in ('project_id', 'name', 'checkpoint')}

    def dirty(self):
        """Whether the working copy has changes not yet saved to the folder."""
        with self._locked():
            return self._state()['dirty']

    def snapshot(self):
        """Complete independent record set (costly for large projects)."""
        with self._locked():
            state = self._state()
            records = [dict(family=f, id=i, document=self._logical(f, raw)) for f, i, raw in self._rows(
                self._q('SELECT family, id, raw FROM {records} WHERE family <> %s {order}'), (CLOSURE_FAMILY,))]
            return dict(project_id=state['project_id'], name=state['name'],
                        checkpoint=state['checkpoint'], records=records)

    def records(self, *families):
        """Independent decoded envelopes of the selected families, in record order."""
        if not families or any(type(family) is not str for family in families):
            raise TypeError('Select one or more record families by name.')
        with self._locked():
            selected = [family for family in families if family != CLOSURE_FAMILY]
            return [dict(family=f, id=i, document=self._logical(f, raw)) for f, i, raw in self._rows(
                self._q('SELECT family, id, raw FROM {records} WHERE family = ANY(%s) {order}'), (selected,))]

    def envelope_digests(self):
        """(family, id) -> canonical envelope SHA256 for every stored revision.

        Rows imported before this column existed are filled once from their
        stored canonical bytes.
        """
        with self._locked():
            missing = self._execute(self._q('SELECT count(*) FROM {records} WHERE envelope_sha256 IS NULL AND family <> %s'),
                                    (CLOSURE_FAMILY,)).fetchone()[0]
            if missing:
                with self._transaction():
                    # Logical envelopes: a compact Run hashes its exact expansion.
                    digests = [(envelope_digest(family, record_id, _encode(self._logical(family, raw))
                                                if family == RUN_FAMILY else raw), family, record_id)
                               for family, record_id, raw in self._rows(self._q(
                                   'SELECT family, id, raw FROM {records} WHERE envelope_sha256 IS NULL AND family <> %s {order}'),
                                   (CLOSURE_FAMILY,))]
                    with self._guard():
                        with self._connection().cursor() as cursor:
                            cursor.executemany(self._q('UPDATE {records} SET envelope_sha256=%s WHERE family=%s AND id=%s'),
                                               digests)
            return {(row[0], row[1]): row[2] for row in
                    self._execute(self._q('SELECT family, id, envelope_sha256 FROM {records} WHERE family <> %s'),
                                  (CLOSURE_FAMILY,))}

    def records_view(self, *families):
        """Every record identity in order; documents decoded only for selected families.

        Unselected envelopes carry document None. Fork and membership
        validators need every identity but only read their own families.
        """
        if not families or any(type(family) is not str for family in families):
            raise TypeError('Select one or more record families by name.')
        with self._locked():
            connection = self._connection()
            idle = connection.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
            result = []
            with (connection.transaction() if idle else nullcontext()), \
                    connection.cursor(name='working_' + uuid.uuid4().hex) as cursor:
                cursor.itersize = 256
                cursor.execute(self._q('SELECT family, id, CASE WHEN family = ANY(%s) THEN raw END '
                                       'FROM {records} WHERE family <> %s {order}'), (list(families), CLOSURE_FAMILY))
                rows = [(family, record_id, None if raw is None else bytes(raw)) for family, record_id, raw in cursor]
            for family, record_id, raw in rows:
                result.append(dict(family=family, id=record_id,
                                   document=None if raw is None else self._logical(family, raw)))
            return result

    def record(self, family, record_id):
        if family == CLOSURE_FAMILY:
            return None
        with self._locked():
            row = self._execute(self._q('SELECT raw FROM {records} WHERE family=%s AND id=%s'),
                                (family, record_id)).fetchone()
            return None if row is None else dict(family=family, id=record_id, document=self._logical(family, bytes(row[0])))

    def reconcile(self, request_key, request_sha256):
        _request(request_key, request_sha256)
        with self._locked():
            for receipt in self._state()['receipts']:
                if receipt['request_key'] == request_key:
                    if receipt['request_sha256'] != request_sha256:
                        _fail('Request key was already used with different input.', 'conflict', 409)
                    return self.snapshot()
            return None

    def commit(self, records, expected_checkpoint, request_key, request_sha256, *, changed=None):
        """Replace the complete current record set in the working copy.

        changed, when given, names every (family, id) whose document may differ
        from the stored revision; all other candidate records are the caller's
        unmodified copies of stored revisions (Session.mutate constructs them
        so). Without it every candidate is compared exactly with its revision.
        Returns the committed snapshot, sharing the caller's record list.
        """
        _request(request_key, request_sha256)
        _digest(expected_checkpoint, 'Expected checkpoint')
        if type(records) is not list or len(records) > MAX_RECORDS:
            _fail('Project records must be a bounded list.')
        with self._locked(), self._transaction():
            state = self._state()
            inventory = {(f, i): (fmt, size, sha) for f, i, fmt, size, sha in self._inventory()}
            candidates = {}
            for record in records:
                _keys(record, ('family', 'id', 'document'), 'Project record')
                family, identity, document = record['family'], record['id'], record['document']
                _identifier(family, 'Record family')
                if family not in SUPPORTED_FORMATS:
                    _fail('Unsupported project record family.', 'unsupported', 422)
                if family == CLOSURE_FAMILY:
                    _fail('Runtime closures are store-owned records.', 'unsupported', 422)
                _identifier(identity, 'Record ID')
                if (family, identity) in candidates:
                    _fail('Duplicate project record identity.')
                if type(document) is not dict:
                    _fail('Domain document must be an object.')
                _domain_format(document.get('format'), family)
                candidates[(family, identity)] = document
            replacements, entries, total = {}, {}, 0
            closure_rows = {row[1]: row[2] for row in self._execute(self._q(
                'SELECT family, id, closure_id FROM {records} WHERE closure_id IS NOT NULL'))}
            new_closures, row_closures, logical_raw, referenced = {}, {}, {}, set()
            for identity in sorted(candidates):
                document = candidates[identity]
                current = inventory.get(identity)
                if current is not None and changed is not None and identity not in changed \
                        and current[0] in (document['format'], 'project_run_history_v2'):
                    entries[identity] = current
                    total += current[1]
                    if identity[1] in closure_rows and identity[0] == RUN_FAMILY:
                        referenced.add(closure_rows[identity[1]])
                    continue
                physical = document
                if (identity[0] == RUN_FAMILY and changed is None and current is not None
                        and current[0] == document['format'] and _sha(_encode(document)) == current[2]):
                    # An unchanged uncompacted Run keeps its verified revision (as in
                    # ProjectStore); compact_run_closures migrates explicitly.
                    entries[identity] = current
                    total += current[1]
                    continue
                if identity[0] == RUN_FAMILY:
                    compacted = compact(document)
                    if compacted is not None:
                        physical, closure = compacted
                        closure_id = physical['runtime_closure']['id']
                        new_closures.setdefault(closure_id, closure)
                        referenced.add(closure_id)
                        row_closures[identity] = closure_id
                        logical_raw[identity] = _encode(document)
                raw = _encode(physical)
                if len(raw) > MAX_RECORD_BYTES:
                    _fail('Project records exceed the synchronous byte limit.')
                digest = _sha(raw)
                if current is None or current[2] != digest:
                    replacements[identity] = raw
                entries[identity] = (physical['format'], len(raw), digest)
                total += len(raw)
                if total > MAX_TOTAL_BYTES:
                    _fail('Project records exceed the synchronous byte limit.')
            # Exactly the closures referenced by stored compact Runs are kept.
            for closure_id in sorted(referenced):
                identity = (CLOSURE_FAMILY, closure_id)
                if identity in inventory:
                    entries[identity] = inventory[identity]
                    total += inventory[identity][1]
                    continue
                raw = _encode(new_closures[closure_id])
                replacements[identity] = raw
                entries[identity] = (new_closures[closure_id]['format'], len(raw), _sha(raw))
                total += len(raw)
            if total > MAX_TOTAL_BYTES:
                _fail('Project records exceed the synchronous byte limit.')
            records_digest = self._records_digest(replacements, sorted(entries))
            for receipt in state['receipts']:
                if receipt['request_key'] == request_key:
                    if receipt['request_sha256'] != request_sha256 or receipt['records_sha256'] != records_digest:
                        _fail('Request key was already used with different input.', 'conflict', 409)
                    return self.snapshot()
            if expected_checkpoint != state['checkpoint']:
                _fail('Expected project checkpoint is stale.', 'stale', 409)
            receipts = state['receipts'] + [dict(request_key=request_key, request_sha256=request_sha256,
                                                  records_sha256=records_digest)]
            manifest = self._manifest(dict(state, receipts=receipts),
                                      [(f, i, *entries[(f, i)]) for f, i in sorted(entries)])
            _manifest_raw(manifest)
            for (family, identity), raw in replacements.items():
                fmt, size, digest = entries[(family, identity)]
                key = (family, identity)
                envelope = (None if family == CLOSURE_FAMILY else
                            envelope_digest(family, identity, logical_raw.get(key, raw)))
                self._execute(self._q(
                    'INSERT INTO {records} (family, id, format, bytes, sha256, raw, envelope_sha256, closure_id) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) '
                    'ON CONFLICT (family, id) DO UPDATE SET format=EXCLUDED.format, bytes=EXCLUDED.bytes, '
                    'sha256=EXCLUDED.sha256, raw=EXCLUDED.raw, envelope_sha256=EXCLUDED.envelope_sha256, '
                    'closure_id=EXCLUDED.closure_id'),
                    (family, identity, fmt, size, digest, raw, envelope, row_closures.get(key)))
            for family, identity in set(inventory) - set(entries):
                self._execute(self._q('DELETE FROM {records} WHERE family=%s AND id=%s'), (family, identity))
            self._write_state(manifest, external_sha256=state['external_sha256'], dirty=True)
            if self._canonical_digests is not None and replacements:
                self._canonical_digests.add_many([_sha(raw) for raw in replacements.values()])
            return dict(project_id=state['project_id'], name=state['name'], checkpoint=manifest['checkpoint'],
                        records=[dict(family=f, id=i, document=candidates[(f, i)]) for f, i in sorted(candidates)])

    def compact_run_closures(self, request_key, request_sha256):
        """Format migration: store every compactable Run against a shared closure.

        The logical record set is unchanged (each compaction is checked to expand
        to the exact original bytes); only the physical records and checkpoint
        change. Returns (previous checkpoint, committed snapshot summary).
        """
        with self._locked():
            state = self._state()
            uncompacted = {(row[0], row[1]) for row in self._execute(self._q(
                "SELECT family, id FROM {records} WHERE family=%s AND format='project_run_history_v1'"), (RUN_FAMILY,))}
            snapshot = self.snapshot()
            committed = self.commit(snapshot['records'], state['checkpoint'], request_key, request_sha256,
                                    changed=uncompacted)
            return state['checkpoint'], {key: committed[key] for key in ('project_id', 'name', 'checkpoint')}

    def save(self, expected_checkpoint):
        """Export the working copy to the external folder (the only folder write)."""
        _digest(expected_checkpoint, 'Expected checkpoint')
        with self._locked():
            state = self._state()
            if expected_checkpoint != state['checkpoint']:
                _fail('Expected project checkpoint is stale.', 'stale', 409)
            try:
                external_raw, _external = self._folder.folder_checkpoint()
            except ProjectStoreError:
                external_raw = None
            if (state['external_sha256'] is not None and
                    (external_raw is None or _sha(external_raw) != state['external_sha256'])):
                _fail('The external project changed since Tuldok last imported or saved it.', 'conflict', 409)
            manifest = self._manifest(state, self._inventory())
            if manifest['checkpoint'] != state['checkpoint']:
                _fail('Working copy checkpoint disagrees with its records.', 'invalid', 409)
            raw = _manifest_raw(manifest)
            if state['external_sha256'] != _sha(raw):
                for entry in manifest['inventory']:
                    if not self._folder.folder_has_record(entry):
                        body = self._execute(self._q('SELECT raw FROM {records} WHERE family=%s AND id=%s'),
                                             (entry['family'], entry['id'])).fetchone()
                        body = bytes(body[0])
                        if len(body) != entry['bytes'] or _sha(body) != entry['sha256']:
                            _fail('Working copy record bytes are corrupt.', 'invalid', 409)
                        self._folder.folder_write_record(entry['family'], entry['id'], entry['sha256'], body)
                self._folder.folder_publish(raw, external_raw)
            with self._transaction():
                self._write_state(manifest, external_sha256=_sha(raw), dirty=False)
            return {key: state[key] for key in ('project_id', 'name', 'checkpoint')}

    def verify_records(self):
        """Re-check every stored revision's bytes against its SHA256 and length."""
        with self._locked():
            inventory = {(f, i): (size, sha) for f, i, _fmt, size, sha in self._inventory()}
            for family, record_id, raw in self._rows(self._q('SELECT family, id, raw FROM {records} {order}')):
                size, digest = inventory[(family, record_id)]
                if len(raw) != size or _sha(raw) != digest:
                    _fail('Canonical record bytes changed or are corrupt.', 'stale', 409)

    def recover_checkpoint(self):
        """Database commits are atomic; return the committed record set."""
        return self.snapshot()

    @contextmanager
    def root_directory(self, *, verify_after=False):
        """Borrow the external folder's physical root (payload artifacts live there)."""
        if type(verify_after) is not bool:
            _fail('Root read verification must be an explicit boolean.')
        with self._locked():
            before = self._state()['checkpoint']
            descriptor = os.dup(self._folder._root_fd)
            try:
                yield descriptor
                self._folder._binding()
                if verify_after and self._state()['checkpoint'] != before:
                    _fail('Project checkpoint changed during the bounded root read.', 'stale', 409)
            finally:
                os.close(descriptor)

    def close(self):
        # The projection (and its lock's connection) may already be closed.
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            try:
                self._folder.close()
            finally:
                self._own.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

