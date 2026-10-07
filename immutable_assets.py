"""Bounded immutable asset storage; Dataset transaction owns record publication."""
import hashlib
import json
import uuid

from workbench import WorkbenchError, encode, strings, text_value, timestamp

MAX_SELECTED_ASSET_BYTES = 40 * 1024 * 1024


def check_selection(records):
    total = sum(row[row['kind']]['bundle_bytes'] for row in records
                if row['kind'] in ('sequence', 'mesh') and row.get(row['kind']))
    if total > MAX_SELECTED_ASSET_BYTES:
        raise WorkbenchError('Selected immutable assets exceed the synchronous 40 MiB bound.')


def migrate_records(db):
    """Admit known retained schemas only; preserve values/indexes in a savepoint."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workbench_records'").fetchone()[0]
    constraints = ("CHECK(kind IN ('image','text'))", "CHECK(kind IN ('image','text','sequence'))",
                   "CHECK(kind IN ('image','text','sequence','mesh'))")
    found = [value for value in constraints if value in sql]
    expected = ['id', 'kind', 'name', 'text', 'original_text', 'content_hash', 'pixel_hash', 'groups_json',
                'parents_json', 'provenance_json', 'task', 'annotation_json', 'review', 'revision', 'created_at', 'updated_at']
    if len(found) != 1 or [row[1] for row in db.execute('PRAGMA table_info(workbench_records)')] != expected:
        raise WorkbenchError('Unsupported Workbench schema or columns for immutable asset migration.')
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='workbench_records'").fetchone():
        raise WorkbenchError('Unsupported Workbench triggers for immutable asset migration.')
    if found[0] == constraints[-1]:
        return
    indexes = [row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='workbench_records' AND sql IS NOT NULL")]
    db.execute('SAVEPOINT immutable_schema')
    try:
        db.execute(sql.replace('workbench_records', 'workbench_records_immutable', 1).replace(found[0], constraints[-1]))
        db.execute('INSERT INTO workbench_records_immutable SELECT * FROM workbench_records')
        db.execute('DROP TABLE workbench_records')
        db.execute('ALTER TABLE workbench_records_immutable RENAME TO workbench_records')
        for statement in indexes:
            db.execute(statement)
        db.execute('RELEASE immutable_schema')
    except BaseException:
        db.execute('ROLLBACK TO immutable_schema')
        db.execute('RELEASE immutable_schema')
        raise


class ImmutableAssets:
    """Concrete facades select trusted table/task policy, adapters own file meaning."""
    def __init__(self, workbench, *, kind, task, maximum, default_name):
        if kind not in ('sequence', 'mesh'):
            raise ValueError('Unsupported immutable asset owner.')
        self.workbench, self.kind, self.task = workbench, kind, task
        self.maximum, self.default_name = maximum, default_name
        self.table = 'workbench_' + kind + '_assets'
        workbench.db.execute(f'''CREATE TABLE IF NOT EXISTS {self.table} (
            id TEXT PRIMARY KEY, bundle BLOB NOT NULL, metadata_json TEXT NOT NULL,
            bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))''')

    def admit(self, prepared, body, origin):
        w = self.workbench
        name = text_value(body.get('name', self.default_name), 'Name')
        rights = text_value(body.get('rights', 'unknown'), 'Rights / permission note', 1000)
        groups = strings(body.get('groups', []), 'Protected groups', maximum=28)
        parents = strings(body.get('parents', []), 'Parent IDs')
        groups = list(dict.fromkeys(groups + prepared['metadata']['protected_groups']))
        bundle = prepared['bundle']
        if not 0 < len(bundle) <= self.maximum:
            raise WorkbenchError(f'{self.kind.title()} bundle exceeds the bounded asset limit.')
        digest = hashlib.sha256(bundle).hexdigest()
        metadata = encode(prepared['metadata'])
        origin = encode(dict(origin, rights=rights))
        record_id, created = uuid.uuid4().hex, timestamp()
        with w.lock, w.db:
            w._sync_images()
            for parent in parents:
                w._get(parent)
            if w.db.execute('SELECT 1 FROM workbench_records WHERE kind=? AND content_hash=?', (self.kind, digest)).fetchone():
                raise WorkbenchError(f'This complete {self.kind} bundle already exists.', 'conflict', 409)
            w.db.execute(f'INSERT INTO {self.table} VALUES (?,?,?,?)', (record_id, bundle, metadata, len(bundle)))
            w.db.execute('INSERT INTO workbench_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (record_id, self.kind, name, None, None, digest, None, encode(groups), encode(parents),
                          origin, self.task, None, 'draft', 1, created, created))
            record = w._get(record_id)
            w._history(record)
            return record

    def check_selection(self, records):
        check_selection(records)

    def metadata(self, record_id):
        row = self.workbench.db.execute(f'SELECT metadata_json,bundle_bytes FROM {self.table} WHERE id=?', (record_id,)).fetchone()
        return None if row is None else dict(json.loads(row[0]), bundle_bytes=row[1])

    def asset(self, record):
        row = self.workbench.db.execute(f'SELECT bundle,bundle_bytes FROM {self.table} WHERE id=?', (record['id'],)).fetchone()
        if row is None:
            raise WorkbenchError(f'{self.kind.title()} source unavailable.', 'unavailable', 404)
        bundle, size = row
        if not 0 < len(bundle) <= self.maximum or len(bundle) != size or hashlib.sha256(bundle).hexdigest() != record['content_hash']:
            raise WorkbenchError(f'{self.kind.title()} bytes changed outside Tuldok.', 'conflict', 409)
        return bundle, 'application/zip'
