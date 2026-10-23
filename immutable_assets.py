"""Bounded immutable asset storage; Dataset transaction owns record publication."""
from access import authorized
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
import os
import uuid

from workbench import WorkbenchError, encode, strings, text_value, timestamp

MAX_SELECTED_ASSET_BYTES = 40 * 1024 * 1024


def validate_project_metadata_fields(value, fields, maximum):
    """Common transport checks; selected asset owners supply native semantics."""
    if type(value) is not dict or set(value) != set(fields) | {'bundle_bytes'}:
        raise WorkbenchError('Unexpected retained immutable metadata fields.')
    if type(value['bundle_bytes']) is not int or not 0 < value['bundle_bytes'] <= maximum:
        raise WorkbenchError('Invalid retained immutable byte count.')
    if strings(value['protected_groups'],'Immutable groups') != value['protected_groups'] or len(value['protected_groups']) != 2:
        raise WorkbenchError('Invalid retained immutable protected groups.')
    text_value(value['scope'],'Immutable source scope',1000)


def validate_project_bounds(value):
    if type(value) is not dict or set(value) != {'min','max'}:
        raise WorkbenchError('Invalid retained spatial bounds.')
    if any(type(value[k]) is not list or len(value[k]) != 3 or any(type(n) not in (int,float) or not math.isfinite(n) for n in value[k]) for k in ('min','max')):
        raise WorkbenchError('Spatial bounds require finite XYZ.')
    if any(a>b for a,b in zip(value['min'],value['max'])):
        raise WorkbenchError('Spatial bounds are reversed.')


def check_selection(records):
    total = sum(row[row['kind']]['bundle_bytes'] for row in records
                if row['kind'] in ('sequence', 'mesh', 'pointcloud', 'volume') and row.get(row['kind']))
    total += sum(row['audio']['source_bytes'] for row in records if row['kind'] == 'audio')
    total += sum(row['field_sequence']['source_bytes'] for row in records if row['kind'] == 'field_sequence')
    if total > MAX_SELECTED_ASSET_BYTES:
        raise WorkbenchError('Selected immutable assets exceed the synchronous 40 MiB bound.')


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def publish_file(db, folder, filename, raw):
    """Publish one trusted local asset path with its metadata transaction.

    Callers supply a server-owned unique folder and fixed filename. Successful
    savepoints transfer rollback custody to the outer transaction; an uncertain
    commit retains bytes for catalog reconciliation. This never extracts paths.
    """
    from metadata import CommitOutcomeUnknown
    created = False
    path = folder / filename
    def discard():
        if created and folder.exists():
            path.unlink(missing_ok=True)
            folder.rmdir()
    try:
        with (nullcontext(db) if db.in_transaction else db.transaction()):
            folder.parent.mkdir(exist_ok=True)
            folder.mkdir()
            created = True
            db.on_rollback(discard)
            with path.open('xb') as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            _sync_directory(folder)
            _sync_directory(folder.parent)
            _sync_directory(folder.parent.parent)
            yield path
    except CommitOutcomeUnknown:
        raise
    except BaseException:
        discard()
        raise


def migrate_records(db):
    """PostgreSQL schema evolution belongs to the versioned metadata owner."""
    db.validate_schema()


class ImmutableAssets:
    """Concrete facades select trusted table/task policy, adapters own file meaning."""
    def __init__(self, workbench, *, kind, task, maximum, default_name):
        self.access = workbench.access
        if kind not in ('sequence', 'mesh', 'pointcloud', 'volume'):
            raise ValueError('Unsupported immutable asset owner.')
        self.workbench, self.kind, self.task = workbench, kind, task
        self.maximum, self.default_name = maximum, default_name
        self.table = 'workbench_' + kind + '_assets'

    @authorized('edit', 'immutable_assets.admit')
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
            self.access.audit('immutable_assets.admit', record_id, {'revision': record['revision'], 'source_sha256': digest})
            return record

    @authorized('inspect', 'immutable_assets.check_selection')
    def check_selection(self, records):
        check_selection(records)

    @authorized('inspect', 'immutable_assets.metadata')
    def metadata(self, record_id):
        source = getattr(self.workbench.dataset, 'project_sources', {}).get(record_id)
        if source is not None and source['kind'] == self.kind:
            return dict(source['metadata'])
        row = self.workbench.db.execute(f'SELECT metadata_json,bundle_bytes FROM {self.table} WHERE id=%s', (record_id,)).fetchone()
        return None if row is None else dict(json.loads(row[0]), bundle_bytes=row[1])

    @authorized('inspect', 'immutable_assets.asset', target=lambda record: record.get('id') if isinstance(record, dict) else None)
    def asset(self, record):
        resolver = getattr(self.workbench.dataset, 'project_asset', None)
        if resolver is not None and record['id'] in self.workbench.dataset.project_sources:
            bundle = resolver(record['id'], self.kind)
            if not 0 < len(bundle) <= self.maximum or hashlib.sha256(bundle).hexdigest() != record['content_hash']:
                raise WorkbenchError('Project asset identity differs.', 'invalid', 409)
            return bundle, 'application/zip'
        row = self.workbench.db.execute(f'SELECT bundle,bundle_bytes FROM {self.table} WHERE id=%s', (record['id'],)).fetchone()
        if row is None:
            raise WorkbenchError(f'{self.kind.title()} source unavailable.', 'unavailable', 404)
        bundle, size = row
        if not 0 < len(bundle) <= self.maximum or len(bundle) != size or hashlib.sha256(bundle).hexdigest() != record['content_hash']:
            raise WorkbenchError(f'{self.kind.title()} bytes changed outside Tuldok.', 'conflict', 409)
        return bundle, 'application/zip'
