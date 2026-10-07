"""Immutable whole-sequence storage. Dataset's transaction owns publication."""
import hashlib
import uuid

from workbench import WorkbenchError, encode, strings, text_value, timestamp

MAX_SELECTED_SEQUENCE_BYTES = 40 * 1024 * 1024
MAX_BUNDLE_BYTES = 65536 + 2097152 + 1024


def migrate_records(db):
    """Replace only the known kind constraint, atomically; preserve indexes."""
    sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='workbench_records'").fetchone()[0]
    old = "CHECK(kind IN ('image','text'))"
    if "CHECK(kind IN ('image','text','sequence'))" in sql:
        return
    if old not in sql or db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='workbench_records'").fetchone():
        raise WorkbenchError('Unsupported Workbench schema or triggers for sequence migration.')
    indexes = [row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='workbench_records' AND sql IS NOT NULL")]
    expected = ['id', 'kind', 'name', 'text', 'original_text', 'content_hash', 'pixel_hash', 'groups_json',
                'parents_json', 'provenance_json', 'task', 'annotation_json', 'review', 'revision', 'created_at', 'updated_at']
    if [row[1] for row in db.execute('PRAGMA table_info(workbench_records)')] != expected:
        raise WorkbenchError('Unsupported Workbench columns for sequence migration.')
    db.execute('SAVEPOINT sequence_schema')
    try:
        db.execute(sql.replace('workbench_records', 'workbench_records_sequence', 1).replace(old, "CHECK(kind IN ('image','text','sequence'))"))
        db.execute('INSERT INTO workbench_records_sequence SELECT * FROM workbench_records')
        db.execute('DROP TABLE workbench_records')
        db.execute('ALTER TABLE workbench_records_sequence RENAME TO workbench_records')
        for statement in indexes:
            db.execute(statement)
        db.execute('RELEASE sequence_schema')
    except BaseException:
        db.execute('ROLLBACK TO sequence_schema')
        db.execute('RELEASE sequence_schema')
        raise


class SequenceAssets:
    def __init__(self, workbench):
        self.workbench = workbench
        workbench.db.execute('''CREATE TABLE IF NOT EXISTS workbench_sequence_assets (
            id TEXT PRIMARY KEY, bundle BLOB NOT NULL, metadata_json TEXT NOT NULL,
            bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))''')

    def admit(self, prepared, body):
        """Only a server-owned adapter provides prepared bytes and metadata."""
        w = self.workbench
        name = text_value(body.get('name', 'Rheon transport sequence'), 'Name')
        rights = text_value(body.get('rights', 'unknown'), 'Rights / permission note', 1000)
        groups = strings(body.get('groups', []), 'Protected groups', maximum=28)
        parents = strings(body.get('parents', []), 'Parent IDs')
        groups = list(dict.fromkeys(groups + prepared['metadata']['protected_groups']))
        bundle = prepared['bundle']
        if not 0 < len(bundle) <= MAX_BUNDLE_BYTES:
            raise WorkbenchError('Sequence bundle exceeds the bounded asset limit.')
        digest = hashlib.sha256(bundle).hexdigest()
        metadata = encode(prepared['metadata'])
        origin = encode({'method': 'simulation_import', 'rights': rights,
                         'adapter': prepared['metadata']['adapter'],
                         'run_sha256': prepared['metadata']['run_sha256'],
                         'frames_sha256': prepared['metadata']['manifest']['frames_sha256']})
        record_id, created = uuid.uuid4().hex, timestamp()
        with w.lock, w.db:
            w._sync_images()
            for parent in parents:
                w._get(parent)
            if w.db.execute("SELECT 1 FROM workbench_records WHERE kind='sequence' AND content_hash=?", (digest,)).fetchone():
                raise WorkbenchError('This complete sequence bundle already exists.', 'conflict', 409)
            w.db.execute('INSERT INTO workbench_sequence_assets VALUES (?,?,?,?)', (record_id, bundle, metadata, len(bundle)))
            w.db.execute('INSERT INTO workbench_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (record_id, 'sequence', name, None, None, digest, None, encode(groups), encode(parents),
                          origin, 'sequence_transport', None, 'draft', 1, created, created))
            record = w._get(record_id)
            w._history(record)
            return record

    def metadata(self, record_id):
        import json
        row = self.workbench.db.execute('SELECT metadata_json,bundle_bytes FROM workbench_sequence_assets WHERE id=?', (record_id,)).fetchone()
        if row is None:
            return None
        return dict(json.loads(row[0]), bundle_bytes=row[1])

    def asset(self, record):
        row = self.workbench.db.execute('SELECT bundle FROM workbench_sequence_assets WHERE id=?', (record['id'],)).fetchone()
        if row is None:
            raise WorkbenchError('Sequence source unavailable.', 'unavailable', 404)
        bundle = row[0]
        if not 0 < len(bundle) <= MAX_BUNDLE_BYTES or hashlib.sha256(bundle).hexdigest() != record['content_hash']:
            raise WorkbenchError('Sequence bytes changed outside Tuldok.', 'conflict', 409)
        return bundle, 'application/zip'

    def check_selection(self, records):
        total = sum(row['sequence']['bundle_bytes'] for row in records if row['kind'] == 'sequence' and row.get('sequence'))
        if total > MAX_SELECTED_SEQUENCE_BYTES:
            raise WorkbenchError('Selected sequence assets exceed the synchronous 40 MiB bound.')
