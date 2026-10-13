"""Real PostgreSQL version evolution and lossless retained backup contracts."""
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import psycopg
from psycopg import sql

from backup_metadata import (backup_catalog, populate_catalog, read_catalog,
                             read_sequences, restore_catalog, summaries,
                             table_state, tree_manifest)
from metadata import (CommitOutcomeUnknown, Metadata, SCHEMA_VERSION, StorageError,
                      TABLES_V1, TABLES_V2, WORKSPACE_TABLES, connection_info,
                      definition_hash)
from migrate_sqlite import migrate_sqlite, read_legacy
from upgrade_metadata import UPGRADES, upgrade_catalog

FIXTURE = Path(__file__).parent / 'fixtures' / 'sqlite_migration_workflow'


class WorkspaceSchemaContract(unittest.TestCase):
    def test_retained_v1_definition_is_exactly_the_qualified_19_table_contract(self):
        self.assertEqual(len(TABLES_V1), 19)
        self.assertEqual(definition_hash(1),
                         '859a04c5ee618faae689885bee79054d5e92098e746d058fd2bcb599da4c80db')
        self.assertEqual(SCHEMA_VERSION, 4)
        self.assertEqual(set(WORKSPACE_TABLES),
                         {'workspace_graphs', 'workspace_runs', 'workspace_exposures'})

    def test_retained_v2_definition_is_exactly_the_qualified_22_table_contract(self):
        self.assertEqual(len(TABLES_V2), 22)
        self.assertEqual(definition_hash(2),
                         'ac4d969f8794004dc11942d8fdb53181e453240c489ddf2605ea32606f911274')
        self.assertNotEqual(definition_hash(3), definition_hash(2))
        self.assertEqual([UPGRADES[version][0] for version in (1, 2)],
                         ['workspace-metadata-1-to-2', 'audio-metadata-2-to-3'])


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL TULDOK_DATABASE_URL')
class WorkspaceMetadata(unittest.TestCase):
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

    def catalog(self, name='catalog', version=1):
        metadata = Metadata(self.root / name, schema_version=version)
        self.schemas.add(metadata.schema)
        self.addCleanup(metadata.close)
        return metadata

    def historical_source(self):
        path = self.root / 'legacy'
        path.mkdir()
        connection = sqlite3.connect(path / 'dataset.sqlite3')
        connection.executescript((FIXTURE / 'catalog.sql').read_text())
        connection.close()
        for directory in ('images', 'releases'):
            shutil.copytree(FIXTURE / directory, path / directory)
        return path

    def historical_catalog(self, version=1):
        source = self.historical_source()
        metadata = self.catalog(version=version)
        tables = read_legacy(source)
        current = read_catalog(metadata)
        with metadata.transaction():
            populate_catalog(metadata, {name: tables.get(name, table_state(current[name]['columns'], []))
                                        for name in metadata.tables})
        for directory in ('images', 'releases'):
            shutil.copytree(source / directory, metadata.path / directory)
        return metadata

    def drop(self, metadata):
        metadata.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(metadata.schema)))
        metadata.close()

    def test_default_startup_refuses_v1_until_explicit_upgrade_preserving_history_identity_and_files(self):
        metadata = self.historical_catalog()
        identity = metadata.dataset_id
        rows = summaries(read_catalog(metadata))
        sequences = read_sequences(metadata)
        files = tree_manifest(metadata.path)
        metadata.close()
        with self.assertRaisesRegex(StorageError, 'explicit upgrade'):
            Metadata(self.root / 'catalog', create=False)
        with self.assertRaisesRegex(StorageError, 'Stop all'):
            upgrade_catalog(self.root / 'catalog')
        result = upgrade_catalog(self.root / 'catalog', quiesced=True)
        self.assertEqual(result['status'], 'upgraded')
        self.assertEqual(result['dataset_id'], identity)
        self.assertEqual(tree_manifest(self.root / 'catalog'), files)
        reopened = Metadata(self.root / 'catalog', create=False)
        self.addCleanup(reopened.close)
        current = read_catalog(reopened)
        self.assertEqual(summaries({name: current[name] for name in TABLES_V1}), rows)
        self.assertEqual(read_sequences(reopened), sequences)
        self.assertTrue(all(current[name]['count'] == 0 for name in WORKSPACE_TABLES))
        self.assertEqual(reopened.dataset_id, identity)
        self.assertEqual(reopened.schema_version, 4)
        from app import Dataset
        dataset = Dataset(self.root / 'catalog')
        try:
            expected = json.loads((FIXTURE / 'expected.json').read_bytes())
            row = expected['record']
            self.assertEqual(dataset.workbench.get(row['id']), row)
            self.assertEqual(dataset.workbench.history(row['id']), expected['history'])
            self.assertEqual(dataset.selections.load(expected['selection']['id'])['selection'], expected['selection'])
            self.assertEqual(dataset.searches.get(expected['search']['id']), expected['search'])
        finally:
            dataset.close()
        repeat = upgrade_catalog(self.root / 'catalog', quiesced=True)
        self.assertEqual(repeat, dict(result, status='already_current'))
        self.assertEqual(summaries(read_catalog(reopened)), summaries(current))

    def test_fresh_v3_persists_opaque_workspace_rows_and_enforces_unique_request_keys(self):
        metadata = self.catalog(version=3)
        self.assertEqual(len(read_catalog(metadata)), 22)
        self.workspace_rows(metadata)
        rows = summaries(read_catalog(metadata))
        with self.assertRaises(psycopg.errors.UniqueViolation), metadata.transaction():
            metadata.execute("INSERT INTO workspace_runs VALUES ('other','request-1','hash','{}')")
        metadata.close()
        reopened = Metadata(self.root / 'catalog', create=False, schema_version=3)
        self.addCleanup(reopened.close)
        self.assertEqual(summaries(read_catalog(reopened)), rows)

    def workspace_rows(self, metadata):
        # SQL preserves the opaque serialized domain evidence, including spacing,
        # duplicate keys and Unicode. Domain owners validate their documents.
        graph = ' { "nodes" : [], "exact" : "e\u0301\\r\\n", "key":1, "key":2 } '
        run = ' { "state" : "completed", "source" : "原本" } '
        with metadata.transaction():
            metadata.execute('INSERT INTO workspace_graphs VALUES (%s,%s,%s)', ('graph-1', 7, graph))
            metadata.execute('INSERT INTO workspace_runs VALUES (%s,%s,%s,%s)', ('run-1', 'request-1', 'a' * 64, run))
            metadata.execute('INSERT INTO workspace_exposures VALUES (%s,%s,%s,%s,%s,%s,%s)',
                             ('exposure-1', 'record-1', 'b' * 64, 'test_prediction_opened', 'run-1', 'release-1', '2026-10-11T00:00:00Z'))

    def audio_row(self, metadata, *, kind='audio'):
        # Authored opaque storage evidence, not an audio-domain validation oracle.
        provenance = ' { "source": "音声.wav", "duration_ms": 10, "hash": "original" } '
        annotation = ' { "segments": [{"start_ms":0,"end_ms":10,"text":"é"}] } '
        with metadata.transaction():
            metadata.execute('''INSERT INTO workbench_records
                (id,kind,name,content_hash,groups_json,parents_json,provenance_json,
                 task,annotation_json,review,revision,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                ('audio-1', kind, '音声.wav', 'c' * 64, '{}', '[]', provenance,
                 'audio_segments', annotation, 'reviewed', 2, 'created', 'updated'))
            metadata.execute('INSERT INTO workbench_history VALUES (%s,%s,%s)',
                             ('audio-1', 1, ' { "kind": "audio", "annotation": null } '))

    def test_v2_upgrade_preserves_populated_catalog_and_only_then_admits_audio(self):
        metadata = self.historical_catalog(version=2)
        self.workspace_rows(metadata)
        rows = summaries(read_catalog(metadata))
        sequences = read_sequences(metadata)
        files = tree_manifest(metadata.path)
        ledger = metadata.execute('SELECT * FROM catalog_version').fetchall()
        with self.assertRaisesRegex(StorageError, 'schema 2 requires an explicit upgrade'):
            Metadata(metadata.path, create=False)
        self.assertEqual(metadata.execute('SELECT * FROM catalog_version').fetchall(), ledger)
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.audio_row(metadata)
        with self.assertRaisesRegex(StorageError, 'Stop all'):
            upgrade_catalog(metadata.path)
        result = upgrade_catalog(metadata.path, quiesced=True)
        self.assertEqual(result['migration'], 'spatial-metadata-3-to-4')
        self.assertEqual(result['schema_version'], 4)
        current = Metadata(metadata.path, create=False)
        self.addCleanup(current.close)
        self.assertEqual(current.dataset_id, metadata.dataset_id)
        self.assertEqual(summaries({name: value for name, value in read_catalog(current).items() if name in rows}), rows)
        self.assertEqual(read_sequences(current), sequences)
        self.assertEqual(tree_manifest(current.path), files)
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.audio_row(current, kind='video')
        self.audio_row(current)
        after = summaries(read_catalog(current))
        self.assertEqual(upgrade_catalog(current.path, quiesced=True), dict(result, status='already_current'))
        self.assertEqual(summaries(read_catalog(current)), after)
        current.close()
        reopened = Metadata(metadata.path, create=False)
        self.addCleanup(reopened.close)
        self.assertEqual(summaries(read_catalog(reopened)), after)

    def test_audio_upgrade_failure_rolls_back_entire_v1_or_v2_chain(self):
        for version in (1, 2):
            for stage in ('constraint', 'proof', 'ledger'):
                with self.subTest(version=version, stage=stage):
                    metadata = self.catalog(f'rollback-{version}-{stage}', version)
                    rows = summaries(read_catalog(metadata))
                    signature = metadata._signature()
                    ledger = metadata.execute('SELECT * FROM catalog_version').fetchall()
                    execute = Metadata.execute
                    proof = Metadata.expected_signature

                    def fail(owner, statement, parameters=None):
                        if stage == 'constraint' and statement == UPGRADES[2][1][1]:
                            raise OSError('injected after old constraint removal')
                        if (stage == 'ledger' and isinstance(statement, str)
                                and statement.startswith('UPDATE catalog_version') and parameters[0] == 3):
                            raise OSError('injected before final ledger publication')
                        return execute(owner, statement, parameters)

                    def fail_proof(owner, target):
                        return 'wrong' if stage == 'proof' and target == 3 else proof(owner, target)

                    with patch.object(Metadata, 'execute', fail), patch.object(Metadata, 'expected_signature', fail_proof):
                        with self.assertRaises((StorageError, OSError)):
                            upgrade_catalog(metadata.path, quiesced=True)
                    self.assertEqual(metadata._signature(), signature)
                    self.assertEqual(metadata.execute('SELECT * FROM catalog_version').fetchall(), ledger)
                    self.assertEqual(summaries(read_catalog(metadata)), rows)
                    metadata.validate_schema()
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        self.audio_row(metadata)
                    self.assertEqual(upgrade_catalog(metadata.path, quiesced=True)['status'], 'upgraded')

    def test_resigned_audio_constraint_cannot_be_blessed_as_retained_v2(self):
        metadata = self.catalog(version=2)
        for statement in UPGRADES[2][1]:
            metadata.execute(statement)
        metadata.execute('UPDATE catalog_version SET catalog_sha256=%s', (metadata._signature(),))
        before = metadata._signature()
        ledger = metadata.execute('SELECT * FROM catalog_version').fetchall()
        with self.assertRaisesRegex(StorageError, 'known schema definition'):
            upgrade_catalog(metadata.path, quiesced=True)
        self.assertEqual(metadata._signature(), before)
        self.assertEqual(metadata.execute('SELECT * FROM catalog_version').fetchall(), ledger)

    def test_v3_backup_restores_audio_bytes_metadata_history_and_workspace_rows(self):
        metadata = self.historical_catalog(version=3)
        self.workspace_rows(metadata)
        self.audio_row(metadata)
        audio = metadata.path / 'audio'
        audio.mkdir()
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as handle:
            handle.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            handle.writeframes(b'\x00\x00' * 80)
        (audio / 'audio-1.wav').write_bytes(buffer.getvalue())
        rows = summaries(read_catalog(metadata))
        files = tree_manifest(metadata.path)
        backup = self.root / 'backup-v3'
        receipt = backup_catalog(metadata.path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], 3)
        self.assertEqual(len(receipt['tables']), 22)
        before = tree_manifest(backup)
        self.drop(metadata)
        restored = self.root / 'restored-v3'
        marker = restore_catalog(backup, restored)
        self.assertEqual(restore_catalog(backup, restored), marker)
        current = Metadata(restored, create=False, schema_version=3)
        self.addCleanup(current.close)
        self.assertEqual(summaries({name: value for name, value in read_catalog(current).items() if name in rows}), rows)
        restored_files = tree_manifest(restored)
        self.assertEqual({name: restored_files[name] for name in files}, files)
        self.assertEqual(tree_manifest(backup), before)
        current.execute("UPDATE workbench_records SET revision=3 WHERE id='audio-1'")
        with self.assertRaisesRegex(ValueError, 'later writes'):
            restore_catalog(backup, restored)

    def test_unknown_version_definition_and_structural_drift_are_refused_without_mutation(self):
        mutations = {
            'version': 'UPDATE catalog_version SET version=999',
            'definition': "UPDATE catalog_version SET definition_sha256='unknown'",
            'column': 'ALTER TABLE samples ADD COLUMN unowned TEXT',
            'index': 'CREATE INDEX unowned ON samples(filename)',
            'table': 'CREATE TABLE unowned(id TEXT)',
            'constraint': 'ALTER TABLE samples ADD CHECK(width > 0)',
        }
        for name, statement in mutations.items():
            with self.subTest(name=name):
                metadata = self.catalog(name)
                metadata.execute(statement)
                before = metadata._signature()
                ledger = metadata.execute('SELECT * FROM catalog_version').fetchall()
                with self.assertRaises(StorageError):
                    upgrade_catalog(metadata.path, quiesced=True)
                self.assertEqual(metadata._signature(), before)
                self.assertEqual(metadata.execute('SELECT * FROM catalog_version').fetchall(), ledger)
                self.assertIsNone(metadata.execute("SELECT to_regclass('workspace_graphs')").fetchone()[0])

    def test_resigning_a_mutated_schema_cannot_bless_it_as_a_known_source_or_destination(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                metadata = self.catalog('resigned-' + str(version), version)
                metadata.execute('ALTER TABLE samples ADD COLUMN unowned TEXT')
                metadata.execute('UPDATE catalog_version SET catalog_sha256=%s', (metadata._signature(),))
                before = metadata._signature()
                with self.assertRaisesRegex(StorageError, 'known schema definition'):
                    upgrade_catalog(metadata.path, quiesced=True)
                self.assertEqual(metadata._signature(), before)
                self.assertEqual(metadata.execute('SELECT version FROM catalog_version').fetchone()[0], version)

    def test_partial_ddl_failure_and_postcondition_failure_roll_back_everything(self):
        for stage in ('ddl', 'proof'):
            with self.subTest(stage=stage):
                metadata = self.catalog(stage)
                signature = metadata._signature()
                identity = metadata.dataset_id
                execute = Metadata.execute
                proof = Metadata.expected_signature

                def fail_ddl(owner, statement, parameters=None):
                    if stage == 'ddl' and statement == WORKSPACE_TABLES['workspace_runs']:
                        raise OSError('injected second table failure')
                    return execute(owner, statement, parameters)

                def fail_proof(owner, version):
                    return 'wrong' if stage == 'proof' and version == 2 else proof(owner, version)

                with patch.object(Metadata, 'execute', fail_ddl), patch.object(Metadata, 'expected_signature', fail_proof):
                    with self.assertRaises((StorageError, OSError)):
                        upgrade_catalog(metadata.path, quiesced=True)
                self.assertEqual(metadata._signature(), signature)
                metadata.validate_schema()
                self.assertEqual(metadata.dataset_id, identity)
                self.assertIsNone(metadata.execute("SELECT to_regclass('workspace_graphs')").fetchone()[0])
                self.assertEqual(upgrade_catalog(metadata.path, quiesced=True)['status'], 'upgraded')

    def test_lost_commit_acknowledgement_reopens_and_reconciles_known_v3(self):
        metadata = self.catalog()
        factory = Metadata.transaction

        @contextmanager
        def lost_acknowledgement(owner, *args, **kwargs):
            original = owner.connection.transaction

            @contextmanager
            def transaction(*inner_args, **inner_kwargs):
                with original(*inner_args, **inner_kwargs) as actual:
                    yield actual
                if not inner_kwargs.get('force_rollback'):
                    raise psycopg.OperationalError('injected lost commit acknowledgement')

            with patch.object(owner.connection, 'transaction', transaction):
                with factory(owner, *args, **kwargs) as current:
                    yield current

        with patch.object(Metadata, 'transaction', lost_acknowledgement):
            with self.assertRaises(CommitOutcomeUnknown):
                upgrade_catalog(metadata.path, quiesced=True)
        reopened = Metadata(metadata.path, create=False)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.schema_version, 4)
        self.assertEqual(upgrade_catalog(metadata.path, quiesced=True)['status'], 'already_current')

    def test_v1_backup_restores_exact_v1_and_can_explicitly_upgrade_with_backup_unchanged(self):
        metadata = self.historical_catalog()
        rows = summaries(read_catalog(metadata))
        identity = metadata.dataset_id
        backup = self.root / 'backup-v1'
        receipt = backup_catalog(metadata.path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], 1)
        self.assertEqual(set(receipt['tables']), set(TABLES_V1))
        before = tree_manifest(backup)
        self.drop(metadata)
        restored = self.root / 'restored'
        with patch('metadata._publish_manifest', side_effect=OSError('injected old-version manifest failure')):
            with self.assertRaisesRegex(OSError, 'manifest'):
                restore_catalog(backup, restored)
        result = restore_catalog(backup, restored)
        self.assertEqual(restore_catalog(backup, restored), result)
        with self.assertRaisesRegex(StorageError, 'explicit upgrade'):
            Metadata(restored, create=False)
        old = Metadata(restored, create=False, schema_version=1)
        self.assertEqual(summaries(read_catalog(old)), rows)
        old.close()
        self.assertEqual(upgrade_catalog(restored, quiesced=True)['dataset_id'], identity)
        self.assertEqual(tree_manifest(backup), before)
        # Exact restore retries refuse schema evolution and do not remove it.
        with self.assertRaises(StorageError):
            restore_catalog(backup, restored)

    def test_v2_backup_restore_preserves_graph_run_exposure_rows_and_rejects_later_writes(self):
        metadata = self.historical_catalog(version=2)
        path = metadata.path
        self.workspace_rows(metadata)
        artifacts = path / 'runs' / 'run-1'
        artifacts.mkdir(parents=True)
        (artifacts / 'test-evidence.bin').write_bytes(b'authored storage fixture\x00\xff\r\n')
        rows = summaries(read_catalog(metadata))
        backup = self.root / 'backup-v2'
        receipt = backup_catalog(path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], 2)
        self.assertTrue(all(receipt['tables'][name]['count'] == 1 for name in WORKSPACE_TABLES))
        before = tree_manifest(backup)
        self.drop(metadata)
        restored = self.root / 'restored'
        restore_catalog(backup, restored)
        current = Metadata(restored, create=False, schema_version=2)
        self.addCleanup(current.close)
        self.assertEqual(summaries({name: value for name, value in read_catalog(current).items() if name in rows}), rows)
        self.assertEqual(tree_manifest(restored / 'runs'), tree_manifest(path / 'runs'))
        restore_catalog(backup, restored)
        current.execute("UPDATE workspace_graphs SET revision=8 WHERE id='graph-1'")
        with self.assertRaisesRegex(ValueError, 'later writes'):
            restore_catalog(backup, restored)
        self.assertEqual(tree_manifest(backup), before)

    def test_legacy_v1_import_receipt_resumes_then_reconciles_after_explicit_upgrade(self):
        source = self.historical_source()
        destination, backup = self.root / 'destination', self.root / 'backup'
        # Emulate the previous tool's actual v1 receipt/schema, retaining its bytes.
        with patch('metadata.SCHEMA_VERSION', 1):
            result = migrate_sqlite(source, destination, backup, quiesced=True)
        self.assertEqual(result['schema_version'], 1)
        self.assertEqual(migrate_sqlite(source, destination, backup, quiesced=True), result)
        receipt_path = destination / '.migration-receipt.json'
        original_receipt = receipt_path.read_bytes()
        receipt_path.write_text(json.dumps(dict(result, schema_version=2)))
        with self.assertRaisesRegex(ValueError, 'contradicts its receipt'):
            migrate_sqlite(source, destination, backup, quiesced=True)
        receipt_path.write_bytes(original_receipt)
        upgrade_catalog(destination, quiesced=True)
        self.assertEqual(migrate_sqlite(source, destination, backup, quiesced=True), result)
        current = Metadata(destination, create=False)
        self.addCleanup(current.close)
        self.workspace_rows(current)
        with self.assertRaisesRegex(ValueError, 'later writes'):
            migrate_sqlite(source, destination, backup, quiesced=True)

    def test_interrupted_v1_import_preserves_its_version_and_identity_on_new_tool_retry(self):
        source = self.historical_source()
        for stage, target in (('rows', 'migrate_sqlite.populate_catalog'),
                              ('manifest', 'metadata._publish_manifest')):
            with self.subTest(stage=stage):
                destination = self.root / ('destination-' + stage)
                backup = self.root / ('backup-' + stage)
                with patch('metadata.SCHEMA_VERSION', 1), patch(target, side_effect=OSError('injected interruption')):
                    with self.assertRaisesRegex(OSError, 'interruption'):
                        migrate_sqlite(source, destination, backup, quiesced=True)
                staging = next(self.root.glob('destination-' + stage + '.migrating-*'))
                saved = (staging / '.migration-receipt.json').read_bytes()
                identity = json.loads(saved)['dataset_id']
                self.schemas.add('catalog_' + identity)
                result = migrate_sqlite(source, destination, backup, quiesced=True)
                self.assertEqual(result['schema_version'], 1)
                self.assertEqual(result['dataset_id'], identity)
                self.assertEqual((destination / '.migration-receipt.json').read_bytes(), saved)
                old = Metadata(destination, create=False, schema_version=1)
                try:
                    expected = read_legacy(source)
                    actual = read_catalog(old)
                    self.assertEqual(summaries({name: actual[name] for name in expected}), summaries(expected))
                finally:
                    old.close()

    def test_retained_v2_import_resumes_exact_receipt_and_reconciles_upgrade_until_audio_write(self):
        source = self.historical_source()
        destination, backup = self.root / 'destination-v2', self.root / 'backup-v2'
        with patch('metadata.SCHEMA_VERSION', 2), patch('migrate_sqlite.populate_catalog', side_effect=OSError('injected interruption')):
            with self.assertRaisesRegex(OSError, 'interruption'):
                migrate_sqlite(source, destination, backup, quiesced=True)
        staging = next(self.root.glob('destination-v2.migrating-*'))
        saved = (staging / '.migration-receipt.json').read_bytes()
        identity = json.loads(saved)['dataset_id']
        self.schemas.add('catalog_' + identity)
        result = migrate_sqlite(source, destination, backup, quiesced=True)
        self.assertEqual(result['schema_version'], 2)
        self.assertEqual(result['dataset_id'], identity)
        self.assertEqual((destination / '.migration-receipt.json').read_bytes(), saved)
        old = Metadata(destination, create=False, schema_version=2)
        expected = read_legacy(source)
        actual = read_catalog(old)
        self.assertEqual(summaries({name: actual[name] for name in expected}), summaries(expected))
        old.close()
        upgrade_catalog(destination, quiesced=True)
        self.assertEqual(migrate_sqlite(source, destination, backup, quiesced=True), result)
        self.assertEqual((destination / '.migration-receipt.json').read_bytes(), saved)
        current = Metadata(destination, create=False)
        self.addCleanup(current.close)
        self.audio_row(current)
        with self.assertRaisesRegex(ValueError, 'later writes'):
            migrate_sqlite(source, destination, backup, quiesced=True)

    def test_upgrade_cli_reopens_catalog_and_never_runs_on_ordinary_startup(self):
        metadata = self.catalog()
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'upgrade_metadata.py'), str(metadata.path)]
        refused = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('Stop all', refused.stderr)
        completed = subprocess.run([*command, '--quiesced'], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['dataset_id'], metadata.dataset_id)
        repeated = subprocess.run([*command, '--quiesced'], capture_output=True, text=True, timeout=30)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)['status'], 'already_current')


if __name__ == '__main__':
    unittest.main()
