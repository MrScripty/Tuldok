"""Real SQLite snapshots and PostgreSQL transfer, recovery and byte-preservation proof."""
from auth_helpers import bind_owner
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import psycopg
from psycopg import sql

from backup_metadata import (StorageTransferError, backup_catalog, digest, file_hash,
    read_catalog, read_sequences, restore_catalog, summaries, tree_manifest)
from metadata import Metadata, TABLES, TABLES_V1, WORKSPACE_TABLES, connection_info
from migrate_sqlite import (LEGACY_DDL, LEGACY_INDEXES, ORDERS, legacy_backup,
                             migrate_sqlite, read_legacy)

FIXTURE = Path(__file__).parent / 'fixtures' / 'sqlite_migration_workflow'


def fixture(path, *, all_tables=False, workflow=False):
    path.mkdir()
    db = sqlite3.connect(path / 'dataset.sqlite3')
    if workflow:
        db.executescript((FIXTURE / 'catalog.sql').read_bytes().decode('utf-8'))
        for directory in ('images', 'releases'):
            shutil.copytree(FIXTURE / directory, path / directory)
    else:
        for name, ddl in LEGACY_DDL.items():
            if all_tables or name == 'samples':
                db.execute(ddl)
        if all_tables:
            for ddl in LEGACY_INDEXES.values():
                db.execute(ddl)
            for table in LEGACY_DDL:
                columns = db.execute('PRAGMA table_info("' + table + '")').fetchall()
                for number in (41, 7):
                    values = []
                    for _, name, kind, required, _, primary in columns:
                        if kind == 'BLOB':
                            value = b'\x00\x00\xff\x80raw ZIP evidence\r\n' + bytes([number])
                        elif kind == 'INTEGER':
                            value = number
                        elif name == 'kind':
                            value = 'text'
                        elif name == 'id':
                            value = ('f' if number == 7 else 'a') * 30 + str(number).zfill(2)
                        elif name == 'sha256':
                            value = str(number) * 32
                        elif name.endswith('json') or name in ('data', 'snapshot', 'evidence', 'annotation'):
                            value = ' { "exact" : "e\\u0301\\r\\n", "escaped_nul": "\\u0000", "duplicate": 1, "duplicate":2 } '
                        else:
                            value = ' exact e\u0301\r\n😀\ufeff ' + name
                        values.append(value)
                    db.execute('INSERT INTO "' + table + '" (rowid,' + ','.join('"' + c[1] + '"' for c in columns) + ') VALUES (' + ','.join('?' for _ in range(len(values) + 1)) + ')', [number] + values)
        (path / 'images' / 'original').mkdir(parents=True)
        (path / 'images' / 'original' / 'image.png').write_bytes(b'original image fixture\x00\xff')
        (path / 'releases').mkdir()
        (path / 'releases' / 'frozen.zip').write_bytes(b'PK\x03\x04exact frozen ZIP bytes\x00\xff')
        (path / 'empty-directory').mkdir()
    db.commit(); db.close()


class LegacyPreflight(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_current_all_owners_preserve_exact_opaque_text_blobs_and_row_order(self):
        fixture(self.root / 'source', all_tables=True)
        before = tree_manifest(self.root / 'source')
        tables = read_legacy(self.root / 'source')
        self.assertEqual(set(tables), set(TABLES_V1))
        self.assertTrue(all(state['count'] == 2 for state in tables.values()))
        for table, column in ORDERS.items():
            self.assertEqual(sorted(row[-1] for row in tables[table]['rows']), [7, 41])
            self.assertEqual(tables[table]['columns'][-1], column)
        self.assertEqual(tree_manifest(self.root / 'source'), before)

    def test_supported_older_workbench_kind_constraints_and_owner_subsets(self):
        for index, kinds in enumerate(("'image','text'", "'image','text','sequence'")):
            path = self.root / str(index); fixture(path)
            db = sqlite3.connect(path / 'dataset.sqlite3')
            db.execute(LEGACY_DDL['workbench_records'].replace("'image','text','sequence','mesh'", kinds))
            db.execute(LEGACY_INDEXES['workbench_content']); db.commit(); db.close()
            self.assertEqual(set(read_legacy(path)), {'samples', 'workbench_records'})

    def test_reject_unknown_versions_objects_columns_constraints_and_storage_types(self):
        mutations = [
            ('version', 'PRAGMA user_version=1'),
            ('application', 'PRAGMA application_id=123'),
            ('unknown', 'CREATE TABLE unsupported(id TEXT)'),
            ('view', 'CREATE VIEW unknown_view AS SELECT * FROM samples'),
            ('trigger', 'CREATE TRIGGER changed AFTER INSERT ON samples BEGIN SELECT 1; END'),
            ('column', 'ALTER TABLE samples ADD COLUMN unsupported TEXT'),
            ('index', 'CREATE INDEX unexpected ON samples(filename)'),
            ('type', "INSERT INTO samples VALUES ('x','hash','name','not-int',1,'b','s','train','now','now',1,NULL)"),
            ('range', "INSERT INTO samples VALUES ('x','hash','name',2147483648,1,'b','s','train','now','now',1,NULL)"),
            ('nul', "INSERT INTO samples VALUES ('x','hash','name',1,1,'b','s','train','now','now',1,char(0))"),
            ('null', "INSERT INTO samples VALUES (NULL,'hash','name',1,1,'b','s','train','now','now',1,NULL)"),
        ]
        for label, statement in mutations:
            with self.subTest(label=label):
                path = self.root / label; fixture(path)
                db = sqlite3.connect(path / 'dataset.sqlite3'); db.execute(statement); db.commit(); db.close()
                before = tree_manifest(path)
                with patch('metadata.Metadata', side_effect=AssertionError('PostgreSQL must not be touched')):
                    with self.assertRaises(StorageTransferError):
                        migrate_sqlite(path, self.root / (label + '-dest'), self.root / (label + '-backup'), quiesced=True)
                self.assertEqual(tree_manifest(path), before)
                self.assertEqual(tree_manifest(self.root / (label + '-backup') / 'catalog'), before)
                self.assertFalse((self.root / (label + '-dest')).exists())
        path = self.root / 'constraint'; path.mkdir()
        db = sqlite3.connect(path / 'dataset.sqlite3')
        db.execute(LEGACY_DDL['samples'].replace('filename TEXT NOT NULL', 'filename TEXT NOT NULL CHECK(length(filename)>1)'))
        db.commit(); db.close()
        with self.assertRaisesRegex(StorageTransferError, 'constraints'):
            read_legacy(path)

    def test_requires_quiescence_separate_paths_and_regular_files(self):
        fixture(self.root / 'source')
        with self.assertRaisesRegex(StorageTransferError, 'Stop all'):
            migrate_sqlite(self.root / 'source', self.root / 'dest', self.root / 'backup')
        with self.assertRaisesRegex(StorageTransferError, 'separate'):
            migrate_sqlite(self.root / 'source', self.root / 'source' / 'dest', self.root / 'backup', quiesced=True)
        (self.root / 'source' / 'escape').symlink_to('/tmp')
        with self.assertRaisesRegex(StorageTransferError, 'symlink'):
            migrate_sqlite(self.root / 'source', self.root / 'dest', self.root / 'backup', quiesced=True)

    def test_corrupted_legacy_backup_receipt_hash_or_version_refuses_retry(self):
        fixture(self.root / 'source')
        receipt = legacy_backup(self.root / 'source', self.root / 'backup')
        for key, value in (('source_sha256', 'f' * 64), ('sqlite_user_version', 999)):
            broken = dict(receipt, **{key: value})
            (self.root / 'backup' / 'backup-receipt.json').write_text(json.dumps(broken))
            with self.assertRaisesRegex(StorageTransferError, 'receipt'):
                legacy_backup(self.root / 'source', self.root / 'backup')

    def test_raw_wal_backup_preserves_committed_rows_without_touching_source(self):
        fixture(self.root / 'source')
        db = sqlite3.connect(self.root / 'source' / 'dataset.sqlite3')
        self.addCleanup(db.close)
        db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA wal_autocheckpoint=0')
        db.execute("INSERT INTO samples VALUES ('x','hash','name',1,1,'b','s','train','now','now',1,NULL)"); db.commit()
        before = tree_manifest(self.root / 'source')
        receipt = legacy_backup(self.root / 'source', self.root / 'backup')
        self.assertIn('dataset.sqlite3-wal', receipt['files'])
        self.assertEqual(read_legacy(self.root / 'backup' / 'catalog')['samples']['count'], 1)
        self.assertEqual(tree_manifest(self.root / 'source'), before)
        self.assertEqual(tree_manifest(self.root / 'backup' / 'catalog'), before)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL TULDOK_DATABASE_URL')
class PostgreSQLTransfers(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.schemas = set()
        self.addCleanup(self.cleanup_schemas)

    def cleanup_schemas(self):
        for manifest in self.root.rglob('.tuldok.json'):
            self.schemas.add('catalog_' + json.loads(manifest.read_bytes())['dataset_id'])
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            for schema in self.schemas:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def migrate(self, **options):
        return migrate_sqlite(self.root / 'source', self.root / 'dest', self.root / 'backup', quiesced=True, **options)

    def test_all_owner_rows_exact_hashes_order_reopen_and_completed_retry(self):
        fixture(self.root / 'source', all_tables=True)
        before = tree_manifest(self.root / 'source')
        expected = read_legacy(self.root / 'source')
        receipt = self.migrate()
        metadata = Metadata(self.root / 'dest', create=False)
        try:
            actual = read_catalog(metadata)
            self.assertEqual(summaries({name: actual[name] for name in TABLES_V1}), summaries(expected))
            self.assertTrue(all(actual[name]['count'] == 0 for name in WORKSPACE_TABLES))
            for table, column in ORDERS.items():
                order = metadata.execute(sql.SQL('SELECT {} FROM {} ORDER BY {}').format(sql.Identifier(column), sql.Identifier(table), sql.Identifier(column))).fetchall()
                self.assertEqual([r[0] for r in order], [7, 41])
            self.assertEqual(metadata.execute("INSERT INTO generation_jobs(id,data) VALUES ('new','{}') RETURNING ordinal").fetchone()[0], 42)
            metadata.execute("DELETE FROM generation_jobs WHERE id='new'")
        finally:
            metadata.close()
        self.assertEqual(self.migrate(), receipt)
        self.assertEqual(tree_manifest(self.root / 'source'), before)
        self.assertEqual(tree_manifest(self.root / 'backup' / 'catalog'), before)
        for directory in ('images', 'releases'):
            self.assertEqual(tree_manifest(self.root / 'source' / directory), tree_manifest(self.root / 'dest' / directory))

    def test_historical_samples_only_is_upgraded_without_inventing_rows(self):
        fixture(self.root / 'source')
        self.migrate()
        metadata = Metadata(self.root / 'dest', create=False)
        try:
            tables = read_catalog(metadata)
            self.assertEqual(set(tables), set(TABLES))
            self.assertFalse(any(table['count'] for table in tables.values()))
        finally:
            metadata.close()

    def test_insert_failure_rolls_back_all_rows_and_retry_reuses_identity(self):
        fixture(self.root / 'source', all_tables=True)
        import migrate_sqlite as migration
        def failed(metadata, tables):
            metadata.execute("INSERT INTO generation_jobs(id,data) VALUES ('injected','{}')")
            raise OSError('injected history failure')
        with patch.object(migration, 'populate_catalog', failed), self.assertRaisesRegex(OSError, 'history'):
            self.migrate()
        self.assertFalse((self.root / 'dest').exists())
        staging = next(self.root.glob('dest.migrating-*'))
        metadata = Metadata(staging, create=False)
        try:
            identity = metadata.dataset_id
            self.assertFalse(any(table['count'] for table in read_catalog(metadata).values()))
        finally:
            metadata.close()
        self.assertEqual(self.migrate()['dataset_id'], identity)

    def test_lost_response_after_rows_commit_before_directory_publish_is_reconciled(self):
        fixture(self.root / 'source', all_tables=True)
        import migrate_sqlite as migration
        rename = migration.os.rename
        def fail_publish(source, target):
            if Path(target) == self.root / 'dest':
                raise OSError('injected publication failure')
            return rename(source, target)
        with patch.object(migration.os, 'rename', side_effect=fail_publish), self.assertRaisesRegex(OSError, 'publication'):
            self.migrate()
        staging = next(self.root.glob('dest.migrating-*'))
        metadata = Metadata(staging, create=False)
        try:
            self.assertEqual(sum(t['count'] for t in read_catalog(metadata).values()), 38)
            identity = metadata.dataset_id
        finally:
            metadata.close()
        self.assertEqual(self.migrate()['dataset_id'], identity)
        self.assertFalse(staging.exists())

    def test_changed_source_backup_destination_or_post_import_writes_refuse_retry(self):
        fixture(self.root / 'source', all_tables=True)
        self.migrate()
        source = self.root / 'source' / 'images' / 'original' / 'image.png'
        raw = source.read_bytes(); source.write_bytes(raw + b'changed')
        with self.assertRaisesRegex(StorageTransferError, 'changed'):
            self.migrate()
        source.write_bytes(raw)
        metadata = Metadata(self.root / 'dest', create=False)
        metadata.execute("UPDATE samples SET filename='later user edit'"); metadata.close()
        with self.assertRaisesRegex(StorageTransferError, 'later writes'):
            self.migrate()

    def test_archived_real_workflow_reopens_searches_selections_history_preferences_and_exports(self):
        fixture(self.root / 'source', workflow=True)
        expected = json.loads((FIXTURE / 'expected.json').read_bytes())
        self.migrate()
        from app import Dataset
        from workbench import WorkbenchError
        with patch('ai_http.request', side_effect=AssertionError('No provider replay')):
            dataset = Dataset(self.root / 'dest'); self.actor = bind_owner(self, dataset)
            try:
                row = expected['record']; workbench = dataset.workbench
                self.assertEqual(workbench.get(row['id']), row)
                self.assertEqual(workbench.history(row['id']), expected['history'])
                self.assertEqual(workbench._response(expected['left']['id']), expected['left'])
                self.assertEqual(workbench.preferences._get(expected['judgment']['id']), expected['judgment'])
                self.assertEqual(dataset.selections.load(expected['selection']['id'])['selection'], expected['selection'])
                self.assertEqual(dataset.searches.get(expected['search']['id']), expected['search'])
                self.assertEqual(workbench.query({'label': 'Exact class'})['total'], 1)
                release = dataset.releases.locate(expected['release']['id'])
                self.assertEqual(file_hash(release), file_hash(FIXTURE / 'releases' / release.name))
                edited = workbench.save(row['id'], dict(row, annotation={'label': 'New class'}, review='human_reviewed'))
                with self.assertRaises(WorkbenchError):
                    workbench.save(row['id'], dict(row, annotation={'label': 'Stale'}, review='human_reviewed'))
                self.assertEqual(edited['revision'], row['revision'] + 1)
                body = dict(items=[{k: edited[k] for k in ('id', 'revision', 'source_revision')}], ratios=dict(train=100,validation=0,test=0),seed=42)
                preview = dataset.releases.preview(body)
                self.assertTrue(preview['eligible'])
                new = dataset.releases.create(dict(body, preview_token=preview['preview_token']))
                self.assertNotEqual(new['id'], expected['release']['id'])
                self.assertEqual(file_hash(release), file_hash(FIXTURE / 'releases' / release.name))
            finally:
                dataset.close()
            dataset = Dataset(self.root / 'dest'); self.actor = bind_owner(self, dataset)
            try:
                self.assertEqual(dataset.workbench.get(row['id'])['revision'], row['revision'] + 1)
            finally:
                dataset.close()

    def test_import_refuses_foreign_identity_in_completed_or_staged_destination(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                base = self.root / str(interrupted); base.mkdir(); fixture(base / 'source')
                invoke = lambda: migrate_sqlite(base / 'source', base / 'dest', base / 'backup', quiesced=True)
                if interrupted:
                    with patch('migrate_sqlite.populate_catalog', side_effect=OSError('stop')), self.assertRaises(OSError):
                        invoke()
                    target = next(base.glob('dest.migrating-*'))
                else:
                    invoke(); target = base / 'dest'
                own_id = json.loads((target / '.tuldok.json').read_bytes())['dataset_id']
                self.schemas.add('catalog_' + own_id)
                foreign = Metadata(base / 'foreign')
                try:
                    (target / '.tuldok.json').write_bytes((base / 'foreign' / '.tuldok.json').read_bytes())
                    with self.assertRaisesRegex(ValueError, 'identity'):
                        invoke()
                    self.assertFalse(any(t['count'] for t in read_catalog(foreign).values()))
                finally:
                    foreign.close()

    def test_restore_refuses_foreign_identity_in_completed_or_staged_destination(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                base = self.root / str(interrupted); base.mkdir(); fixture(base / 'source')
                migrate_sqlite(base / 'source', base / 'dest', base / 'backup', quiesced=True)
                backup_catalog(base / 'dest', base / 'pg-backup', quiesced=True)
                original = Metadata(base / 'dest', create=False)
                self.schemas.add(original.schema)
                original.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(original.schema))); original.close()
                invoke = lambda: restore_catalog(base / 'pg-backup', base / 'restored')
                if interrupted:
                    with patch('backup_metadata.populate_catalog', side_effect=OSError('stop')), self.assertRaises(OSError):
                        invoke()
                    target = next(base.glob('restored.restore-*'))
                else:
                    invoke(); target = base / 'restored'
                foreign = Metadata(base / 'foreign')
                try:
                    (target / '.tuldok.json').write_bytes((base / 'foreign' / '.tuldok.json').read_bytes())
                    with self.assertRaisesRegex(ValueError, 'identity'):
                        invoke()
                    self.assertFalse(any(t['count'] for t in read_catalog(foreign).values()))
                finally:
                    foreign.close()

    def test_import_retries_interrupted_catalog_identity_publication(self):
        fixture(self.root / 'source', all_tables=True)
        with patch('metadata._publish_manifest', side_effect=OSError('injected manifest publication')), self.assertRaisesRegex(OSError, 'manifest'):
            self.migrate()
        staging = next(self.root.glob('dest.migrating-*'))
        pending = json.loads((staging / '.tuldok-initializing.json').read_bytes())
        self.assertFalse((staging / '.tuldok.json').exists())
        receipt = self.migrate()
        self.assertEqual(receipt['dataset_id'], pending['dataset_id'])
        self.assertFalse((self.root / 'dest' / '.tuldok-initializing.json').exists())

    def test_restore_retries_interrupted_catalog_identity_publication(self):
        fixture(self.root / 'source', all_tables=True)
        self.migrate()
        receipt = backup_catalog(self.root / 'dest', self.root / 'pg-backup', quiesced=True)
        metadata = Metadata(self.root / 'dest', create=False)
        metadata.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(metadata.schema)))
        metadata.close()
        with patch('metadata._publish_manifest', side_effect=OSError('injected manifest publication')), self.assertRaisesRegex(OSError, 'manifest'):
            restore_catalog(self.root / 'pg-backup', self.root / 'restored')
        self.assertEqual(restore_catalog(self.root / 'pg-backup', self.root / 'restored')['dataset_id'], receipt['dataset_id'])
        # A restored catalog is itself backupable and restorable; earlier receipts remain ordinary files.
        second = backup_catalog(self.root / 'restored', self.root / 'pg-backup2', quiesced=True)
        metadata = Metadata(self.root / 'restored', create=False)
        metadata.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(metadata.schema)))
        metadata.close()
        self.assertEqual(restore_catalog(self.root / 'pg-backup2', self.root / 'restored2')['dataset_id'], second['dataset_id'])

    def test_actual_cli_restore_into_independent_database_keeps_original_catalog_unchanged(self):
        with psycopg.connect(connection_info(), autocommit=True) as admin:
            if not admin.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()[0]:
                self.skipTest('Independent database fixture requires CREATEDB; application role does not.')
            database = 'tuldok_restore_' + uuid.uuid4().hex
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        try:
            fixture(self.root / 'source', workflow=True)
            repository = Path(__file__).resolve().parents[1]
            def cli(module, arguments, environment=None):
                completed = subprocess.run([sys.executable, str(repository / module), *map(str, arguments)],
                                           env=environment, capture_output=True, text=True, timeout=90)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                return json.loads(completed.stdout)
            migration = cli('migrate_sqlite.py', [self.root / 'source', self.root / 'dest', '--backup', self.root / 'backup', '--quiesced'])
            backup = cli('backup_metadata.py', ['backup', self.root / 'dest', self.root / 'pg-backup', '--quiesced'])
            before = tree_manifest(self.root / 'pg-backup')
            original = Metadata(self.root / 'dest', create=False)
            try:
                original_rows = summaries(read_catalog(original))
                # Test setup reuses the connected provisioner's credential without
                # expanding its database-specific password-file entry or logging it.
                restored_dsn = psycopg.conninfo.make_conninfo(connection_info(), dbname=database,
                                                             password=original.connection.info.password)
                environment = dict(os.environ, TULDOK_DATABASE_URL=restored_dsn)
                restored = cli('backup_metadata.py', ['restore', self.root / 'pg-backup', self.root / 'restored'], environment)
                self.assertEqual(restored['dataset_id'], migration['dataset_id'])
                self.assertEqual(restored['dataset_id'], backup['dataset_id'])
                self.assertEqual(cli('backup_metadata.py', ['restore', self.root / 'pg-backup', self.root / 'restored'], environment), restored)
                from app import Dataset
                with patch.dict(os.environ, {'TULDOK_DATABASE_URL': restored_dsn}), patch('ai_http.request', side_effect=AssertionError('No provider replay')):
                    dataset = Dataset(self.root / 'restored'); self.actor = bind_owner(self, dataset)
                    try:
                        expected = json.loads((FIXTURE / 'expected.json').read_bytes())
                        self.assertEqual(dataset.workbench.get(expected['record']['id']), expected['record'])
                        self.assertTrue(dataset.selections.load(expected['selection']['id'])['current'])
                        frozen = dataset.releases.locate(expected['release']['id'])
                        self.assertEqual(file_hash(frozen), file_hash(FIXTURE / 'releases' / frozen.name))
                    finally:
                        dataset.close()
                self.assertEqual(summaries(read_catalog(original)), original_rows)
                self.assertEqual(tree_manifest(self.root / 'pg-backup'), before)
            finally:
                original.close()
        finally:
            with psycopg.connect(connection_info(), autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))

    def test_complete_backup_restore_preserves_identity_metadata_artifacts_and_retries(self):
        fixture(self.root / 'source', all_tables=True)
        self.migrate()
        before = tree_manifest(self.root / 'dest')
        metadata = Metadata(self.root / 'dest', create=False)
        metadata.execute("INSERT INTO generation_jobs(id,data) VALUES ('deleted','{}')")
        metadata.execute("DELETE FROM generation_jobs WHERE id='deleted'")
        sequences = read_sequences(metadata)
        metadata.close()
        receipt = backup_catalog(self.root / 'dest', self.root / 'pg-backup', quiesced=True)
        metadata = Metadata(self.root / 'dest', create=False)
        try:
            # Existing catalogs are not valid restore destinations, even with the same identity.
            with self.assertRaisesRegex(ValueError, 'exist'):
                restore_catalog(self.root / 'pg-backup', self.root / 'restored')
            metadata.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(metadata.schema)))
        finally:
            metadata.close()
        result = restore_catalog(self.root / 'pg-backup', self.root / 'restored')
        self.assertEqual(result['dataset_id'], receipt['dataset_id'])
        restored = Metadata(self.root / 'restored', create=False)
        try:
            self.assertEqual(summaries(read_catalog(restored)), receipt['tables'])
            self.assertEqual(read_sequences(restored), sequences)
        finally:
            restored.close()
        self.assertEqual(tree_manifest(self.root / 'restored', ('.restore-receipt-' + digest(receipt) + '.json',)), before)
        self.assertEqual(restore_catalog(self.root / 'pg-backup', self.root / 'restored'), result)
        self.assertEqual(tree_manifest(self.root / 'dest'), before)
        # Tampering any artifact makes the complete backup unusable, before writes.
        (self.root / 'pg-backup' / 'catalog' / 'releases' / 'frozen.zip').write_bytes(b'changed')
        with self.assertRaisesRegex(StorageTransferError, 'hash'):
            restore_catalog(self.root / 'pg-backup', self.root / 'other-restored')
