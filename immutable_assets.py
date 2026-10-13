"""Bounded immutable asset storage; Dataset transaction owns record publication."""
import hashlib
import json
import uuid

from workbench import WorkbenchError, encode, strings, text_value, timestamp

MAX_SELECTED_ASSET_BYTES = 40 * 1024 * 1024


def check_selection(records):
    total = sum(row[row['kind']]['bundle_bytes'] for row in records
                if row['kind'] in ('sequence', 'mesh', 'pointcloud', 'volume') and row.get(row['kind']))
    total += sum(row['audio']['source_bytes'] for row in records if row['kind'] == 'audio')
    if total > MAX_SELECTED_ASSET_BYTES:
        raise WorkbenchError('Selected immutable assets exceed the synchronous 40 MiB bound.')


def migrate_records(db):
    """PostgreSQL schema evolution belongs to the versioned metadata owner."""
    db.validate_schema()


class ImmutableAssets:
    """Concrete facades select trusted table/task policy, adapters own file meaning."""
    def __init__(self, workbench, *, kind, task, maximum, default_name):
        if kind not in ('sequence', 'mesh', 'pointcloud', 'volume'):
            raise ValueError('Unsupported immutable asset owner.')
        self.workbench, self.kind, self.task = workbench, kind, task
        self.maximum, self.default_name = maximum, default_name
        self.table = 'workbench_' + kind + '_assets'

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
        with w.lock, w.db.transaction():
            w._sync_images()
            for parent in parents:
                w._get(parent)
            if w.db.execute('SELECT 1 FROM workbench_records WHERE kind=%s AND content_hash=%s', (self.kind, digest)).fetchone():
                raise WorkbenchError(f'This complete {self.kind} bundle already exists.', 'conflict', 409)
            w.db.execute(f'INSERT INTO {self.table} VALUES (%s,%s,%s,%s)', (record_id, bundle, metadata, len(bundle)))
            w.db.execute('INSERT INTO workbench_records VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (record_id, self.kind, name, None, None, digest, None, encode(groups), encode(parents),
                          origin, self.task, None, 'draft', 1, created, created))
            record = w._get(record_id)
            w._history(record)
            return record

    def check_selection(self, records):
        check_selection(records)

    def metadata(self, record_id):
        row = self.workbench.db.execute(f'SELECT metadata_json,bundle_bytes FROM {self.table} WHERE id=%s', (record_id,)).fetchone()
        return None if row is None else dict(json.loads(row[0]), bundle_bytes=row[1])

    def asset(self, record):
        row = self.workbench.db.execute(f'SELECT bundle,bundle_bytes FROM {self.table} WHERE id=%s', (record['id'],)).fetchone()
        if row is None:
            raise WorkbenchError(f'{self.kind.title()} source unavailable.', 'unavailable', 404)
        bundle, size = row
        if not 0 < len(bundle) <= self.maximum or len(bundle) != size or hashlib.sha256(bundle).hexdigest() != record['content_hash']:
            raise WorkbenchError(f'{self.kind.title()} bytes changed outside Tuldok.', 'conflict', 409)
        return bundle, 'application/zip'
