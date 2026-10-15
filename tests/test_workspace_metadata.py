"""Real PostgreSQL version evolution and lossless retained backup contracts."""
from contextlib import contextmanager, redirect_stderr
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
                      TABLES_V1, TABLES_V2, TABLES_V3, TABLES_V4, PROJECT_TABLES, WORKSPACE_TABLES, connection_info,
                      definition_hash)
from migrate_sqlite import migrate_sqlite, read_legacy
from upgrade_metadata import UPGRADES, upgrade_catalog

FIXTURE = Path(__file__).parent / 'fixtures' / 'sqlite_migration_workflow'


class WorkspaceSchemaContract(unittest.TestCase):
    def test_retained_v1_definition_is_exactly_the_qualified_19_table_contract(self):
        self.assertEqual(len(TABLES_V1), 19)
        self.assertEqual(definition_hash(1),
                         '859a04c5ee618faae689885bee79054d5e92098e746d058fd2bcb599da4c80db')
        self.assertEqual(SCHEMA_VERSION, 9)
        self.assertEqual(set(WORKSPACE_TABLES),
                         {'workspace_graphs', 'workspace_runs', 'workspace_exposures'})

    def test_retained_v2_definition_is_exactly_the_qualified_22_table_contract(self):
        self.assertEqual(len(TABLES_V2), 22)
        self.assertEqual(definition_hash(2),
                         'ac4d969f8794004dc11942d8fdb53181e453240c489ddf2605ea32606f911274')
        self.assertNotEqual(definition_hash(3), definition_hash(2))
        self.assertEqual([UPGRADES[version][0] for version in (1, 2)],
                         ['workspace-metadata-1-to-2', 'audio-metadata-2-to-3'])

    def test_retained_v3_v4_definitions_and_additive_v5_project_table(self):
        self.assertEqual(len(TABLES_V3), 22)
        self.assertEqual(definition_hash(3), '54fade5b56207edf7c9a33bfa9187f85b3e42ea779869314e7ab0fa8bdc242a4')
        self.assertEqual(len(TABLES_V4), 24)
        self.assertEqual(definition_hash(4), '52242c56f7b88144157b66d93b151d818cecf0b2219226d4aff5734e8a1adcef')
        self.assertEqual(set(PROJECT_TABLES), {'workspace_projects'})
        self.assertEqual(UPGRADES[4], ('project-metadata-4-to-5', tuple(PROJECT_TABLES.values())))
        self.assertNotEqual(definition_hash(5), definition_hash(4))
        self.assertEqual(definition_hash(6), 'e4ca8ba0b092834a3e7ba059f88fce223a66ad2f830ab7fb60c64fe6d1882cf5')


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
        self.assertEqual(reopened.schema_version, 9)
        from app import Dataset
        dataset = Dataset(self.root / 'catalog')
        from auth_helpers import bind_owner
        bind_owner(self, dataset)
        current = read_catalog(reopened)
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
        self.assertEqual(result['migration'], 'model-development-8-to-9')
        self.assertEqual(result['schema_version'], 9)
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
        self.assertEqual(reopened.schema_version, 9)
        self.assertEqual(upgrade_catalog(metadata.path, quiesced=True)['status'], 'already_current')

    def test_failed_backup_cleans_its_read_only_partial_without_changing_source(self):
        from backup_metadata import tree_modes
        metadata = self.catalog(version=8)
        nested = metadata.path / 'readonly'; nested.mkdir()
        (nested / 'data').write_bytes(b'fixture'); (nested / 'data').chmod(0o400)
        nested.chmod(0o500)
        before = tree_manifest(metadata.path); modes = tree_modes(metadata.path, before)
        backup = self.root / 'failed-backup'
        with patch('backup_metadata.write_json', side_effect=OSError('post-copy injected failure')):
            with self.assertRaisesRegex(OSError, 'post-copy injected failure'):
                backup_catalog(metadata.path, backup, quiesced=True)
        self.assertFalse(backup.exists())
        self.assertFalse(list(self.root.glob('failed-backup.partial-*')))
        self.assertEqual(tree_manifest(metadata.path), before)
        self.assertEqual(tree_modes(metadata.path, before), modes)
        nested.chmod(0o700)

    def test_uncertain_partial_cleanup_preserves_original_error_and_external_modes(self):
        metadata = self.catalog(version=8)
        external = self.root / 'external'; external.mkdir(); external.chmod(0o500)
        backup = self.root / 'uncertain-backup'
        def replace(path, value):
            partial = Path(path).parent
            (partial / 'catalog').rename(partial / 'retained-catalog')
            (partial / 'catalog').symlink_to(external, target_is_directory=True)
            raise OSError('original post-copy failure')
        with patch('backup_metadata.write_json', side_effect=replace):
            with self.assertRaisesRegex(OSError, 'original post-copy failure') as caught:
                backup_catalog(metadata.path, backup, quiesced=True)
        self.assertIn('cleanup refused', caught.exception.backup_cleanup_diagnostic)
        self.assertEqual(external.stat().st_mode & 0o777, 0o500)
        self.assertEqual(len(list(self.root.glob('uncertain-backup.partial-*'))), 1)
        external.chmod(0o700)

    def test_backup_cleanup_never_deletes_replacement_root_contents(self):
        import backup_metadata
        metadata = self.catalog(version=8)
        backup = self.root / 'replaced-backup'
        original = backup_metadata._remove_partial_contents
        replacement = []
        def replace(descriptor):
            partial = next(self.root.glob('replaced-backup.partial-*'))
            partial.rename(self.root / 'retained-owned-partial')
            partial.mkdir(); (partial / 'unrelated').write_bytes(b'preserve')
            replacement.append(partial)
            # Only intercept the root call; recursion uses the genuine implementation.
            with patch('backup_metadata._remove_partial_contents', original):
                original(descriptor)
        with patch('backup_metadata.write_json', side_effect=OSError('original failure')):
            with patch('backup_metadata._remove_partial_contents', side_effect=replace):
                with self.assertRaisesRegex(OSError, 'original failure') as caught:
                    backup_catalog(metadata.path, backup, quiesced=True)
        self.assertEqual((replacement[0] / 'unrelated').read_bytes(), b'preserve')
        self.assertIn('identity changed', caught.exception.backup_cleanup_diagnostic)

    def test_cleanup_diagnostic_preserves_original_error_without_note_capability_and_reaches_cli(self):
        import backup_metadata
        class LegacyOSError(OSError):
            add_note = None  # Python 3.10 exceptions have no note capability.
        metadata = self.catalog(version=8)
        before = tree_manifest(metadata.path)
        for error_type in (OSError, LegacyOSError):
            with self.subTest(error_type=error_type.__name__):
                backup = self.root / ('diagnostic-' + error_type.__name__)
                original_error = error_type('original post-copy failure')
                original_args = original_error.args
                with patch('backup_metadata.write_json', side_effect=original_error), \
                        patch('backup_metadata._remove_partial_contents',
                              side_effect=backup_metadata.StorageTransferError('injected custody refusal')):
                    with self.assertRaises(error_type) as caught:
                        backup_catalog(metadata.path, backup, quiesced=True)
                self.assertIs(caught.exception, original_error)
                self.assertEqual(original_error.args, original_args)
                self.assertEqual(str(original_error), 'original post-copy failure')
                partials = list(self.root.glob(backup.name + '.partial-*'))
                self.assertEqual(len(partials), 1)
                diagnostic = original_error.backup_cleanup_diagnostic
                self.assertIn(str(partials[0]), diagnostic)
                self.assertIn('injected custody refusal', diagnostic)
                if callable(getattr(original_error, 'add_note', None)):
                    self.assertIn(diagnostic, original_error.__notes__)
                else:
                    self.assertFalse(hasattr(original_error, '__notes__'))
                stderr = io.StringIO()
                with patch.object(sys, 'argv', ['backup_metadata.py', 'backup',
                                               str(metadata.path), str(backup), '--quiesced']), \
                        patch('backup_metadata.backup_catalog', side_effect=original_error), \
                        redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as exited:
                        backup_metadata.main()
                self.assertEqual(exited.exception.code, 1)
                self.assertEqual(stderr.getvalue(), str(original_error) + '\n' + diagnostic + '\n')
                self.assertEqual(original_error.args, original_args)
                self.assertEqual(tree_manifest(metadata.path), before)

    def test_backup_partial_descriptor_acquisition_failure_closes_parent(self):
        metadata = self.catalog(version=8)
        original = os.open; parents = []
        def fail(name, flags, *args, **kwargs):
            if isinstance(name, str) and name.startswith('open-failure.partial-'):
                parents.append(kwargs['dir_fd'])
                raise OSError('injected descriptor acquisition failure')
            return original(name, flags, *args, **kwargs)
        with patch('backup_metadata.os.open', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'descriptor acquisition failure'):
                backup_catalog(metadata.path, self.root / 'open-failure', quiesced=True)
        self.assertEqual(len(parents), 1)
        with self.assertRaises(OSError):
            os.fstat(parents[0])

    def test_private_manifest_restore_preserves_mode_and_refuses_changed_completed_mode(self):
        from backup_metadata import StorageTransferError, tree_modes
        previous_umask = os.umask(0o022)
        try:
            for mode in (0o400, 0o600):
                with self.subTest(mode=oct(mode)):
                    metadata = self.catalog(name='private-' + oct(mode), version=8)
                    (metadata.path / '.tuldok.json').chmod(mode)
                    backup = self.root / ('backup-' + oct(mode))
                    receipt = backup_catalog(metadata.path, backup, quiesced=True)
                    before = tree_manifest(backup)
                    self.drop(metadata)
                    destination = self.root / ('restored-' + oct(mode))
                    result = restore_catalog(backup, destination)
                    self.assertEqual(restore_catalog(backup, destination), result)
                    self.assertEqual(tree_modes(destination, receipt['files']),
                                     tree_modes(backup / 'catalog', receipt['files']))
                    manifest = destination / '.tuldok.json'
                    manifest.chmod(0o644)
                    with self.assertRaisesRegex(StorageTransferError, 'later writes'):
                        restore_catalog(backup, destination)
                    self.assertEqual(manifest.stat().st_mode & 0o777, 0o644)
                    self.assertEqual(tree_manifest(backup), before)
        finally:
            os.umask(previous_umask)

    def test_private_manifest_restore_retry_preserves_identity_and_refuses_changed_staging_mode(self):
        import backup_metadata
        previous_umask = os.umask(0o077)
        try:
            metadata = self.catalog(version=8)
            (metadata.path / '.tuldok.json').chmod(0o400)
            backup = self.root / 'private-retry-backup'
            backup_catalog(metadata.path, backup, quiesced=True)
            before = tree_manifest(backup)
            self.drop(metadata)
            os.umask(0o022)
            destination = self.root / 'private-retry-restored'
            with patch('backup_metadata.copy_tree', side_effect=OSError('injected pre-copy interruption')):
                with self.assertRaisesRegex(OSError, 'pre-copy interruption'):
                    restore_catalog(backup, destination)
            staging = next(self.root.glob(destination.name + '.restore-*'))
            manifest = staging / '.tuldok.json'
            marker_bytes = manifest.read_bytes()
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o400)
            lock = staging / '.metadata-init.lock'
            self.assertEqual(lock.stat().st_mode & 0o777, 0o600)
            lock.chmod(0o644)
            with self.assertRaisesRegex(backup_metadata.StorageTransferError, 'permissions differ'):
                restore_catalog(backup, destination)
            self.assertEqual(lock.stat().st_mode & 0o777, 0o644)
            lock.chmod(0o600)  # Fixture owner explicitly restores the admitted mode.
            manifest.chmod(0o600)
            with self.assertRaisesRegex(backup_metadata.StorageTransferError, 'permissions differ'):
                restore_catalog(backup, destination)
            self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manifest.read_bytes(), marker_bytes)
            manifest.chmod(0o400)  # Fixture owner explicitly restores the admitted mode.
            result = restore_catalog(backup, destination)
            self.assertEqual(restore_catalog(backup, destination), result)
            self.assertEqual((destination / '.tuldok.json').read_bytes(), marker_bytes)
            self.assertEqual((destination / '.tuldok.json').stat().st_mode & 0o777, 0o400)
            self.assertEqual((destination / '.metadata-init.lock').stat().st_mode & 0o777, 0o600)
            self.assertEqual(tree_manifest(backup), before)
        finally:
            os.umask(previous_umask)

    def test_new_restore_never_repairs_same_owner_files_replaced_after_metadata_creation(self):
        from backup_metadata import StorageTransferError
        for name in ('.tuldok.json', '.metadata-init.lock'):
            with self.subTest(name=name):
                metadata = self.catalog(name='replace-' + name, version=8)
                backup = self.root / ('replace-backup-' + name)
                backup_catalog(metadata.path, backup, quiesced=True)
                self.drop(metadata)
                replaced = []
                def replace(path, *args, **kwargs):
                    current = Metadata(path, *args, **kwargs)
                    target = Path(path) / name
                    value = target.read_bytes()
                    target.unlink(); target.write_bytes(value); target.chmod(0o400)
                    replaced.append((target, value, target.stat().st_ino))
                    return current
                with patch('metadata.Metadata', side_effect=replace):
                    with self.assertRaisesRegex(StorageTransferError, 'permissions differ'):
                        restore_catalog(backup, self.root / ('replace-restored-' + name))
                target, value, inode = replaced[0]
                self.assertEqual(target.stat().st_mode & 0o777, 0o400)
                self.assertEqual(target.stat().st_ino, inode)
                self.assertEqual(target.read_bytes(), value)

    def test_fresh_restore_refuses_preexisting_catalog_initialization_files(self):
        import backup_metadata
        for name in ('.tuldok.json', '.metadata-init.lock'):
            with self.subTest(name=name):
                metadata = self.catalog(name='preexisting-' + name, version=8)
                backup = self.root / ('preexisting-backup-' + name)
                backup_catalog(metadata.path, backup, quiesced=True)
                self.drop(metadata)
                original = backup_metadata.write_json
                foreign = []
                def create(path, value):
                    original(path, value)
                    target = Path(path).parent / name
                    target.write_bytes(b'preserve preexisting file'); target.chmod(0o400)
                    foreign.append(target)
                with patch('backup_metadata.write_json', side_effect=create):
                    with self.assertRaisesRegex((StorageError, backup_metadata.StorageTransferError), 'already exist'):
                        restore_catalog(backup, self.root / ('preexisting-restored-' + name))
                self.assertEqual(foreign[0].stat().st_mode & 0o777, 0o400)
                self.assertEqual(foreign[0].read_bytes(), b'preserve preexisting file')
                foreign[0].unlink()  # The fixture's intentionally invalid manifest is not a catalog.

    def test_private_pending_restore_creates_missing_manifest_without_changing_existing_lock(self):
        from backup_metadata import StorageTransferError, digest
        previous_umask = os.umask(0o077)
        try:
            metadata = self.catalog(version=8)
            (metadata.path / '.tuldok.json').chmod(0o400)
            backup = self.root / 'pending-private-backup'
            receipt = backup_catalog(metadata.path, backup, quiesced=True)
            self.drop(metadata); os.umask(0o022)
            destination = self.root / 'pending-private-restored'
            with patch('metadata._publish_manifest', side_effect=OSError('injected early publication interruption')):
                with self.assertRaisesRegex(OSError, 'early publication interruption'):
                    restore_catalog(backup, destination)
            staging = next(self.root.glob(destination.name + '.restore-*'))
            self.assertFalse(os.path.lexists(staging / '.tuldok.json'))
            lock = staging / '.metadata-init.lock'
            identity = lock.stat().st_ino
            lock.chmod(0o644)
            with self.assertRaisesRegex(StorageTransferError, 'lock bytes or permissions differ'):
                restore_catalog(backup, destination)
            self.assertEqual(lock.stat().st_mode & 0o777, 0o644)
            lock.chmod(0o600)  # Fixture owner restores the mode; the tool never repairs it.
            result = restore_catalog(backup, destination)
            self.assertEqual(restore_catalog(backup, destination), result)
            self.assertEqual((destination / '.metadata-init.lock').stat().st_ino, identity)
            self.assertEqual((destination / '.metadata-init.lock').stat().st_mode & 0o777, 0o600)
            self.assertEqual((destination / '.tuldok.json').stat().st_mode & 0o777, 0o400)
            self.assertEqual(tree_manifest(destination, ('.restore-receipt-' + digest(receipt) + '.json',)),
                             receipt['files'])
        finally:
            os.umask(previous_umask)

    def test_private_pending_restore_preserves_stale_exclusive_manifest_temporary(self):
        metadata = self.catalog(version=8)
        (metadata.path / '.tuldok.json').chmod(0o400)
        backup = self.root / 'stale-temporary-backup'
        backup_catalog(metadata.path, backup, quiesced=True)
        self.drop(metadata)
        destination = self.root / 'stale-temporary-restored'
        original = os.replace
        def interrupt(source, target):
            if Path(target).name == '.tuldok.json':
                raise OSError('injected pre-rename interruption')
            return original(source, target)
        with patch('metadata.os.replace', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'pre-rename interruption'):
                restore_catalog(backup, destination)
        staging = next(self.root.glob(destination.name + '.restore-*'))
        temporary = staging / '.tuldok.json.tmp'
        before = (temporary.read_bytes(), temporary.stat().st_mode, temporary.stat().st_ino)
        with self.assertRaises(FileExistsError):
            restore_catalog(backup, destination)
        self.assertEqual((temporary.read_bytes(), temporary.stat().st_mode, temporary.stat().st_ino), before)
        self.assertFalse(os.path.lexists(staging / '.tuldok.json'))

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

    def test_v4_to_v5_preserves_history_and_only_explicitly_admits_projects(self):
        metadata = self.historical_catalog(version=4)
        self.workspace_rows(metadata)
        self.audio_row(metadata)
        rows = summaries(read_catalog(metadata))
        files = tree_manifest(metadata.path)
        identity = metadata.dataset_id
        with self.assertRaisesRegex(StorageError, 'explicit upgrade'):
            Metadata(metadata.path, create=False)
        with self.assertRaisesRegex(StorageError, 'Stop all'):
            upgrade_catalog(metadata.path)
        result = upgrade_catalog(metadata.path, quiesced=True)
        self.assertEqual((result['schema_version'], result['migration']), (9, 'model-development-8-to-9'))
        current = Metadata(metadata.path, create=False)
        self.addCleanup(current.close)
        self.assertEqual(current.dataset_id, identity)
        self.assertEqual(summaries({name: value for name, value in read_catalog(current).items() if name in rows}), rows)
        self.assertEqual(tree_manifest(current.path), files)
        self.assertEqual(current.execute('SELECT count(*) FROM workspace_projects').fetchone()[0], 0)
        self.assertEqual(upgrade_catalog(current.path, quiesced=True), dict(result, status='already_current'))

    def test_project_upgrade_failure_rolls_back_schema_history_and_ledger(self):
        for source in (1, 4):
            for stage in ('create', 'proof', 'ledger'):
                with self.subTest(source=source, stage=stage):
                    metadata = self.catalog('project-rollback-' + str(source) + '-' + stage, source)
                    before = summaries(read_catalog(metadata))
                    signature = metadata._signature()
                    ledger = metadata.execute('SELECT * FROM catalog_version').fetchall()
                    execute, proof = Metadata.execute, Metadata.expected_signature
                    def fail(owner, statement, parameters=None):
                        result = execute(owner, statement, parameters)
                        if stage == 'create' and statement == UPGRADES[4][1][0]:
                            raise OSError('injected after project table creation')
                        if stage == 'ledger' and isinstance(statement, str) and statement.startswith('UPDATE catalog_version') and parameters[0] == 5:
                            raise OSError('injected after project ledger write')
                        return result
                    def fail_proof(owner, target):
                        return 'wrong' if stage == 'proof' and target == 5 else proof(owner, target)
                    with patch.object(Metadata, 'execute', fail), patch.object(Metadata, 'expected_signature', fail_proof):
                        with self.assertRaises((StorageError, OSError)):
                            upgrade_catalog(metadata.path, quiesced=True)
                    self.assertEqual(metadata._signature(), signature)
                    self.assertEqual(metadata.execute('SELECT * FROM catalog_version').fetchall(), ledger)
                    self.assertEqual(summaries(read_catalog(metadata)), before)
                    metadata.validate_schema()

    def test_retained_v4_backup_restores_exact_old_schema_then_requires_upgrade(self):
        metadata = self.historical_catalog(version=4)
        self.workspace_rows(metadata)
        before = summaries(read_catalog(metadata))
        backup = self.root / 'backup-v4'
        receipt = backup_catalog(metadata.path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], 4)
        self.assertEqual(set(receipt['tables']), set(TABLES_V4))
        backup_files = tree_manifest(backup)
        self.drop(metadata)
        restored = self.root / 'restored-v4'
        restore_catalog(backup, restored)
        with self.assertRaisesRegex(StorageError, 'explicit upgrade'):
            Metadata(restored, create=False)
        old = Metadata(restored, create=False, schema_version=4)
        self.addCleanup(old.close)
        self.assertEqual(summaries(read_catalog(old)), before)
        old.close()
        self.assertEqual(upgrade_catalog(restored, quiesced=True)['schema_version'], 9)
        self.assertEqual(tree_manifest(backup), backup_files)

    def test_v5_backup_restore_preserves_exact_project_snapshot_and_history(self):
        metadata = self.historical_catalog(version=5)
        self.workspace_rows(metadata)
        document = ' { "id":"project-1", "root_alias":"local", "source":"project.json", "sha256":"snapshot", "manifest":{"name":"原本 e\u0301"} } '
        with metadata.transaction():
            metadata.execute('INSERT INTO workspace_projects VALUES (%s,%s)', ('project-1', document))
        with self.assertRaises(psycopg.errors.UniqueViolation), metadata.transaction():
            metadata.execute('INSERT INTO workspace_projects VALUES (%s,%s)', ('project-1', '{}'))
        rows = summaries(read_catalog(metadata))
        backup = self.root / 'backup-v5'
        receipt = backup_catalog(metadata.path, backup, quiesced=True)
        self.assertEqual(receipt['schema_version'], 5)
        self.assertEqual(receipt['tables']['workspace_projects']['count'], 1)
        backup_files = tree_manifest(backup)
        self.drop(metadata)
        restored = self.root / 'restored-v5'
        restore_catalog(backup, restored)
        current = Metadata(restored, create=False, schema_version=5)
        self.addCleanup(current.close)
        self.assertEqual(summaries(read_catalog(current)), rows)
        self.assertEqual(current.execute('SELECT document FROM workspace_projects').fetchone()[0], document)
        restore_catalog(backup, restored)
        current.execute("UPDATE workspace_projects SET document='{}' WHERE id='project-1'")
        with self.assertRaisesRegex(ValueError, 'later writes'):
            restore_catalog(backup, restored)
        self.assertEqual(tree_manifest(backup), backup_files)

    def test_explicit_v8_to_v9_preserves_all_old_rows_files_and_rejects_failed_new_ddl(self):
        from metadata import TABLES_V8, MODEL_DEVELOPMENT_TABLES
        metadata=self.historical_catalog(version=8)
        self.workspace_rows(metadata)
        before=summaries(read_catalog(metadata));files=tree_manifest(metadata.path)
        migration,statements=UPGRADES[8]
        with patch.dict(UPGRADES,{8:(migration,(*statements,'SELECT missing_model_upgrade()'))}):
            with self.assertRaises(psycopg.Error):upgrade_catalog(metadata.path,quiesced=True)
        self.assertEqual(summaries(read_catalog(metadata)),before)
        self.assertEqual(metadata.execute('SELECT version FROM catalog_version').fetchone()[0],8)
        with self.assertRaisesRegex(StorageError,'explicit upgrade'):Metadata(metadata.path,create=False)
        result=upgrade_catalog(metadata.path,quiesced=True)
        self.assertEqual((result['schema_version'],result['migration']),(9,'model-development-8-to-9'))
        current=Metadata(metadata.path,create=False);self.addCleanup(current.close)
        after=read_catalog(current)
        self.assertEqual(summaries({key:after[key] for key in TABLES_V8}),before)
        self.assertTrue(all(after[key]['count']==0 for key in MODEL_DEVELOPMENT_TABLES))
        self.assertEqual(tree_manifest(metadata.path),files)
        with self.assertRaises(StorageError):Metadata(metadata.path,create=False,schema_version=8)

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


class TransferPermissions(unittest.TestCase):
    def test_read_only_tree_and_retry_preserve_modes_and_byte_manifest(self):
        from backup_metadata import copy_tree, tree_modes, StorageTransferError
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'; target = Path(temporary) / 'target'
            (source / 'nested').mkdir(parents=True)
            (source / 'nested/program').write_bytes(b'fixture executable')
            (source / 'data').write_bytes(b'fixture data')
            (source / 'nested/program').chmod(0o500); (source / 'data').chmod(0o400)
            (source / 'nested').chmod(0o500); source.chmod(0o500)
            expected = tree_manifest(source)
            copy_tree(source, target, expected)
            self.assertEqual(tree_manifest(target), expected)
            self.assertEqual(tree_modes(target, expected), tree_modes(source, expected))
            self.assertEqual((target / 'data').stat().st_nlink, 1)
            copy_tree(source, target, expected)
            (target / 'nested').chmod(0o550)
            with self.assertRaisesRegex(StorageTransferError, 'directory permissions differ'):
                copy_tree(source, target, expected)
            (target / 'nested').chmod(0o500)
            (target / 'data').chmod(0o600)
            with self.assertRaisesRegex(StorageTransferError, 'permissions differ'):
                copy_tree(source, target, expected)
            target.chmod(0o700)
            (target / 'data').unlink()
            target.chmod(0o500)
            with self.assertRaisesRegex(StorageTransferError, 'Read-only staging'):
                copy_tree(source, target, expected)
            for root in (source, target):
                root.chmod(0o700); (root / 'nested').chmod(0o700)

    def test_partial_cleanup_cannot_follow_replaced_intermediate_directory(self):
        from backup_metadata import _remove_partial_contents
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'partial'; root.mkdir()
            nested = root / 'catalog'; nested.mkdir()
            external = Path(temporary) / 'external'; external.mkdir(); external.chmod(0o500)
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            original = os.open
            def replace(name, flags, *args, **kwargs):
                if name == 'catalog' and kwargs.get('dir_fd') == descriptor:
                    nested.rename(root / 'retained-catalog')
                    nested.symlink_to(external, target_is_directory=True)
                return original(name, flags, *args, **kwargs)
            try:
                with patch('backup_metadata.os.open', side_effect=replace):
                    with self.assertRaises(OSError):
                        _remove_partial_contents(descriptor)
                self.assertEqual(external.stat().st_mode & 0o777, 0o500)
                self.assertTrue((root / 'retained-catalog').is_dir())
            finally:
                os.close(descriptor); external.chmod(0o700)

    def test_source_mode_change_during_copy_refused(self):
        from backup_metadata import copy_tree, StorageTransferError
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'; source.mkdir()
            payload = source / 'payload'; payload.write_bytes(b'fixture'); payload.chmod(0o400)
            expected = tree_manifest(source)
            original = shutil.copyfileobj
            def change(reader, writer):
                original(reader, writer); payload.chmod(0o600)
            with patch('backup_metadata.shutil.copyfileobj', side_effect=change):
                with self.assertRaisesRegex(StorageTransferError, 'Source changed'):
                    copy_tree(source, Path(temporary) / 'target', expected)
            self.assertFalse((Path(temporary) / 'target/payload').exists())
