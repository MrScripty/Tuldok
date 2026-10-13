"""Explicit, non-destructive SQLite-to-PostgreSQL catalog migration.

Recognized SQLite v0 schemas are pinned to released Tuldok source, not inferred
from arbitrary SQL. The original catalog and complete raw backup stay untouched.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import uuid

from backup_metadata import (StorageTransferError, ORDERS, canonical, copy_tree, digest,
    file_hash, populate_catalog, read_catalog, separate_paths, summaries,
    sync_directory, table_state, tree_manifest, write_json)

LEGACY_VERSION = 0
FORMAT_VERSION = 1
# Source schema authority: Tuldok 1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c.
# Earlier owners use subsets of these tables; Workbench's only kind evolution
# was image/text -> image/text/sequence -> image/text/sequence/mesh.
LEGACY_DDL = {
    'caption_proposals': 'CREATE TABLE caption_proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL)',
    'generation_entries': 'CREATE TABLE generation_entries (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(job_id, ordinal))',
    'generation_jobs': 'CREATE TABLE generation_jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)',
    'grounded_jobs': 'CREATE TABLE grounded_jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)',
    'samples': 'CREATE TABLE samples (\n            id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,\n            width INTEGER NOT NULL, height INTEGER NOT NULL,\n            book_id TEXT NOT NULL, session_id TEXT NOT NULL, split TEXT NOT NULL,\n            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,\n            revision INTEGER NOT NULL DEFAULT 1, annotation TEXT)',
    'saved_searches': 'CREATE TABLE saved_searches (\n    id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,\n    criteria_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'saved_selections': 'CREATE TABLE saved_selections (\n                id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,\n                members_json TEXT NOT NULL, member_count INTEGER NOT NULL,\n                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'text_classification_proposals': 'CREATE TABLE text_classification_proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL)',
    'workbench_deleted_sources': 'CREATE TABLE workbench_deleted_sources (\n                id TEXT PRIMARY KEY, book_id TEXT NOT NULL, session_id TEXT NOT NULL,\n                split TEXT NOT NULL)',
    'workbench_history': 'CREATE TABLE workbench_history (\n                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,\n                PRIMARY KEY(id, revision))',
    'workbench_mesh_assets': 'CREATE TABLE workbench_mesh_assets (\n            id TEXT PRIMARY KEY, bundle BLOB NOT NULL, metadata_json TEXT NOT NULL,\n            bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))',
    'workbench_preference_history': 'CREATE TABLE workbench_preference_history (\n                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,\n                PRIMARY KEY(id,revision))',
    'workbench_preferences': 'CREATE TABLE workbench_preferences (\n                id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, revision INTEGER NOT NULL,\n                data TEXT NOT NULL)',
    'workbench_records': 'CREATE TABLE "workbench_records" (\n                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN (\'image\',\'text\',\'sequence\',\'mesh\')),\n                name TEXT, text TEXT, original_text TEXT,\n                content_hash TEXT NOT NULL, pixel_hash TEXT,\n                groups_json TEXT NOT NULL, parents_json TEXT NOT NULL,\n                provenance_json TEXT NOT NULL, task TEXT NOT NULL,\n                annotation_json TEXT, review TEXT NOT NULL,\n                revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'workbench_response_history': 'CREATE TABLE workbench_response_history (\n                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,\n                PRIMARY KEY(id,revision))',
    'workbench_responses': 'CREATE TABLE workbench_responses (\n                id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, revision INTEGER NOT NULL,\n                completion TEXT NOT NULL, review TEXT NOT NULL, provenance_json TEXT NOT NULL,\n                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
    'workbench_rights_notes': 'CREATE TABLE workbench_rights_notes (\n                id TEXT PRIMARY KEY, note TEXT NOT NULL, revision INTEGER NOT NULL)',
    'workbench_sequence_assets': 'CREATE TABLE workbench_sequence_assets (\n            id TEXT PRIMARY KEY, bundle BLOB NOT NULL, metadata_json TEXT NOT NULL,\n            bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))',
    'workbench_target_proposals': 'CREATE TABLE workbench_target_proposals (id TEXT PRIMARY KEY, evidence TEXT NOT NULL)',
}
LEGACY_INDEXES = {
    'workbench_content': 'CREATE INDEX workbench_content ON workbench_records(content_hash)',
    'workbench_preference_prompt': 'CREATE INDEX workbench_preference_prompt ON workbench_preferences(prompt_id)',
    'workbench_response_prompt': 'CREATE INDEX workbench_response_prompt ON workbench_responses(prompt_id)',
}
SQLITE_FILES = {'dataset.sqlite3', 'dataset.sqlite3-wal', 'dataset.sqlite3-shm', 'dataset.sqlite3-journal'}
MIGRATION_RECEIPT = '.migration-receipt.json'
RESERVED_FILES = {'.tuldok.json', MIGRATION_RECEIPT, '.restore-receipt.json', '.metadata-init.lock', '.tuldok-initializing.json', '.tuldok.json.tmp'}


def normalized_sql(statement):
    return re.sub(r'\s+', '', statement.replace('"workbench_records"', 'workbench_records', 1))


def known_schema(db):
    """Reject unknown schema before reading values or allocating a destination."""
    if db.execute('PRAGMA user_version').fetchone()[0] != LEGACY_VERSION:
        raise StorageTransferError('Unsupported SQLite user_version; expected legacy version 0.')
    if db.execute('PRAGMA application_id').fetchone()[0] != 0:
        raise StorageTransferError('Unsupported SQLite application_id.')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise StorageTransferError('SQLite integrity check failed.')
    objects = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master').fetchall()
    tables = {}
    expected = sqlite3.connect(':memory:')
    try:
        for ddl in LEGACY_DDL.values():
            expected.execute(ddl)
        for kind, name, owner, statement in objects:
            if kind == 'index' and statement is None:
                continue  # Constraints are checked in exact table DDL below.
            if kind == 'index' and name in LEGACY_INDEXES and normalized_sql(statement) == normalized_sql(LEGACY_INDEXES[name]):
                continue
            if kind != 'table' or name not in LEGACY_DDL:
                raise StorageTransferError('Unsupported SQLite schema object: ' + name)
            accepted = [LEGACY_DDL[name]]
            if name == 'workbench_records':
                accepted.extend(LEGACY_DDL[name].replace("'image','text','sequence','mesh'", value)
                                for value in ("'image','text'", "'image','text','sequence'"))
            if normalized_sql(statement) not in [normalized_sql(value) for value in accepted]:
                raise StorageTransferError('Unsupported SQLite table constraints: ' + name)
            columns = db.execute('PRAGMA table_info("' + name + '")').fetchall()
            if columns != expected.execute('PRAGMA table_info("' + name + '")').fetchall():
                raise StorageTransferError('Unsupported SQLite columns: ' + name)
            tables[name] = columns
        if 'samples' not in tables:
            raise StorageTransferError('Legacy catalog has no recognized samples table.')
        return tables
    finally:
        expected.close()


def read_legacy(path):
    """Read only a disposable copy: SQLite may need WAL/SHM recovery files."""
    with tempfile.TemporaryDirectory(prefix='tuldok-legacy-preflight-') as temporary:
        working = Path(temporary) / 'catalog'
        working.mkdir()
        for name in SQLITE_FILES:
            source = Path(path) / name
            if source.exists():
                shutil.copyfile(source, working / name)
        database = working / 'dataset.sqlite3'
        db = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            schemas = known_schema(db)
            result = {}
            for table, columns in schemas.items():
                rows = []
                for row in db.execute('SELECT rowid,* FROM "' + table + '" ORDER BY rowid'):
                    rowid, *values = row
                    for column, value in zip(columns, values):
                        _, name, dtype, required, _, primary = column
                        if value is None:
                            if required or primary:
                                raise StorageTransferError('Unsupported NULL in ' + table + '.' + name)
                            continue
                        expected = {'TEXT': str, 'INTEGER': int, 'BLOB': bytes}[dtype]
                        if type(value) is not expected:
                            raise StorageTransferError('Unsupported SQLite storage type in ' + table + '.' + name)
                        if isinstance(value, str) and '\x00' in value:
                            raise StorageTransferError('NUL text cannot be represented losslessly by PostgreSQL text: ' + table + '.' + name)
                        if isinstance(value, int) and not -(2 ** 31) <= value < 2 ** 31:
                            raise StorageTransferError('Unsupported integer range in ' + table + '.' + name)
                    if table in ORDERS:
                        values.append(rowid)
                    rows.append(values)
                names = [column[1] for column in columns]
                if table in ORDERS:
                    names.append(ORDERS[table])
                result[table] = table_state(names, rows)
            return result
        finally:
            db.close()


def legacy_backup(source, backup):
    """Raw complete snapshot, with no SQLite connection to the source or backup."""
    before = tree_manifest(source)
    if 'dataset.sqlite3' not in before or before['dataset.sqlite3']['kind'] != 'file':
        raise StorageTransferError('Source has no ordinary dataset.sqlite3 file.')
    if RESERVED_FILES.intersection(before):
        raise StorageTransferError('Source already has PostgreSQL or transfer metadata.')
    if backup.exists():
        receipt = json.loads((backup / 'backup-receipt.json').read_bytes())
        if (receipt.get('format_version') != FORMAT_VERSION or receipt.get('kind') != 'sqlite-legacy'
                or receipt.get('sqlite_user_version') != LEGACY_VERSION
                or receipt.get('source_sha256') != digest(receipt.get('files'))):
            raise StorageTransferError('Unsupported legacy backup receipt.')
        if receipt['files'] != before or tree_manifest(backup / 'catalog') != before:
            raise StorageTransferError('Source or backup changed since the initial snapshot; refusing retry.')
        return receipt
    backup.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=backup.name + '.partial-', dir=backup.parent))
    try:
        copy_tree(source, temporary / 'catalog', before)
        if before != tree_manifest(source) or before != tree_manifest(temporary / 'catalog'):
            raise StorageTransferError('Source changed during backup. Stop all source writers first.')
        receipt = {'kind': 'sqlite-legacy', 'format_version': FORMAT_VERSION,
                   'sqlite_user_version': LEGACY_VERSION, 'dataset_id': uuid.uuid4().hex,
                   'files': before, 'source_sha256': digest(before)}
        write_json(temporary / 'backup-receipt.json', receipt)
        os.rename(temporary, backup)
        sync_directory(backup.parent)
        return receipt
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def migrate_sqlite(source, destination, backup, *, dsn=None, quiesced=False):
    """Preserve one stopped catalog; retry only its proven unchanged snapshot."""
    from metadata import Metadata, SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS
    if not quiesced:
        raise StorageTransferError('Stop all app/artifact writers and explicitly pass quiesced=True / --quiesced.')
    source, destination, backup = separate_paths(source, destination, backup)
    receipt = legacy_backup(source, backup)
    tables = read_legacy(backup / 'catalog')
    identity = receipt['dataset_id']
    if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity):
        raise StorageTransferError('Invalid legacy backup dataset identity.')
    files = {name: entry for name, entry in receipt['files'].items() if name not in SQLITE_FILES}
    state = {'kind': 'sqlite-migration', 'format_version': FORMAT_VERSION,
             'source_sha256': receipt['source_sha256'], 'dataset_id': identity,
             'schema_version': SCHEMA_VERSION, 'tables': summaries(tables), 'files': files}
    staging = destination.with_name(destination.name + '.migrating-' + identity)
    # A retained transfer receipt still owns its exact version and import.
    # Continuing it preserves that version until an explicit upgrade; a completed,
    # upgraded destination reconciles only unchanged rows/files and empty new tables.
    owned = destination if destination.exists() else staging
    if owned.exists():
        saved = json.loads((owned / MIGRATION_RECEIPT).read_bytes())
        version = saved.get('schema_version')
        if type(version) is not int or version not in SUPPORTED_SCHEMA_VERSIONS:
            raise StorageTransferError('Unsupported SQLite migration destination version.')
        state['schema_version'] = version
    if destination.exists():
        if json.loads((destination / MIGRATION_RECEIPT).read_bytes()) != state:
            raise StorageTransferError('Destination exists with a different migration receipt.')
        metadata = Metadata(destination, dsn=dsn, create=False, dataset_id=identity, schema_version=None)
        try:
            with metadata.lock, metadata.transaction():
                if metadata.schema_version < state['schema_version']:
                    raise StorageTransferError('Migrated catalog version contradicts its receipt.')
                current = read_catalog(metadata)
                for name, table in current.items():
                    if (name in tables and summaries({name: table}) != summaries({name: tables[name]})) or (name not in tables and table['count']):
                        raise StorageTransferError('Migrated catalog changed; refusing to overwrite later writes.')
                if tree_manifest(destination, ('.tuldok.json', '.metadata-init.lock', '.tuldok-initializing.json', '.tuldok.json.tmp', MIGRATION_RECEIPT)) != files:
                    raise StorageTransferError('Migrated artifacts changed; refusing to overwrite later writes.')
            return state
        finally:
            metadata.close()
    if staging.exists():
        if json.loads((staging / MIGRATION_RECEIPT).read_bytes()) != state:
            raise StorageTransferError('Staging directory belongs to a different migration.')
    else:
        staging.mkdir(parents=True, mode=0o700)
        write_json(staging / MIGRATION_RECEIPT, state)
    existing = tree_manifest(staging, ('.tuldok.json', '.metadata-init.lock', '.tuldok-initializing.json', '.tuldok.json.tmp', MIGRATION_RECEIPT))
    if any(name not in files or files[name] != value for name, value in existing.items()):
        raise StorageTransferError('Migration staging contains unexpected artifact bytes.')
    copy_tree(backup / 'catalog', staging, files)
    existed = (staging / '.tuldok.json').exists()
    metadata = Metadata(staging, dsn=dsn, create=not existed, dataset_id=identity,
                        schema_version=state['schema_version'])
    try:
        with metadata.lock, metadata.transaction():
            current = read_catalog(metadata)
            # An earlier import either committed every table or rolled back all.
            merged = {name: tables.get(name, table_state(current[name]['columns'], [])) for name in metadata.tables}
            if any(table['count'] for table in current.values()):
                if summaries(current) != summaries(merged):
                    raise StorageTransferError('Staged PostgreSQL catalog differs from the retained snapshot.')
            else:
                populate_catalog(metadata, merged)
            if summaries(read_catalog(metadata)) != summaries(merged):
                raise StorageTransferError('SQLite/PostgreSQL row/hash reconciliation failed.')
        if tree_manifest(staging, ('.tuldok.json', '.metadata-init.lock', '.tuldok-initializing.json', '.tuldok.json.tmp', MIGRATION_RECEIPT)) != files:
            raise StorageTransferError('SQLite/PostgreSQL artifact/hash reconciliation failed.')
        if tree_manifest(source) != receipt['files']:
            raise StorageTransferError('Legacy source changed before publication; destination remains staged.')
        os.rename(staging, destination)
        sync_directory(destination.parent)
        return state
    finally:
        metadata.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('destination')
    parser.add_argument('--backup', required=True)
    parser.add_argument('--quiesced', action='store_true')
    args = parser.parse_args()
    try:
        result = migrate_sqlite(args.source, args.destination, args.backup, quiesced=args.quiesced)
    except (StorageTransferError, OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
