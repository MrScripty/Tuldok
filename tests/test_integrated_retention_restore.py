"""Stopped M2/M3/publication transfer and cold public consumers; no science claim."""
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

import agent_api
import backup_metadata as transfer
from app import Dataset, make_handler
from backup_metadata import (backup_catalog, read_catalog, read_sequences,
                             restore_catalog, summaries, tree_manifest, tree_modes)
from metadata import Metadata, connection_info
from tuldok_client import WorkflowClient
from workbench import WorkbenchError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class IntegratedRetentionRestoreTests(unittest.TestCase):
    def test_stopped_transfer_retains_recovery_timing_and_exact_publication_consumers(self):
        from test_run_coordinator_recovery import CoordinatorRecoveryTests

        fixture = CoordinatorRecoveryTests('runTest')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        source = fixture.dataset
        original_dsn = source.db.dsn
        schema = source.db.schema
        cleanup = {}

        def drop_source():
            if cleanup.get('source_schema_removed'):
                return
            source.close()
            with psycopg.connect(original_dsn, autocommit=True) as admin:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                self.assertIsNone(admin.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',
                                                (schema,)).fetchone())
            cleanup['source_schema_removed'] = schema
        self.addCleanup(drop_source)

        admitted = fixture.queued(fixture.body(approval=fixture.approve()))
        run = source.runs._load(admitted['id'])
        # This executes the real neutral helper exactly once. Only publication's
        # original copy boundary is faulted, after acknowledged process drainage.
        with patch.object(source.runs, '_copy_verified', side_effect=OSError('Authored transfer copy fault')):
            source.runs._run_attempt(run, (source.runs._capacity.cores[0],),
                                     source.runs._capacity.claim(run))
        failed = copy.deepcopy(source.runs._load(run['id']))
        self.assertEqual((failed['state'], failed['custody_phase']), ('interrupted', 'drained'))
        self.assertEqual(failed['publication_fault']['code'], 'unavailable')

        # Existing fixture holds the real catalog advisory lock on another PG
        # connection until the actual coordinator times out and joins.
        fixture.lock_fault()
        with fixture.owner.bound(source):
            recovered_health = source.runs.recover_coordinator({
                'expected_generation': 1, 'request_key': 'transfer-coordinator-recovery-0001'})
            self.assertEqual(recovered_health['generation'], 2)
            self.assertEqual(recovered_health['fault']['category'], 'catalog_lock_timeout')
            with patch('recipe_process.launch', side_effect=AssertionError('Publication replayed compute')):
                recovered = source.runs.recover_publication({
                    'run_id': run['id'], 'source_ref': failed['publication_source'],
                    'request_key': 'transfer-publication-recovery-0001'})
            self.assertEqual(recovered['state'], 'published')
            ref = recovered['result_ref']
            reader = source.access.issue({'label': 'Restored inspect-only consumer', 'scopes': ['inspect']})
            before_run = copy.deepcopy(source.runs._load(run['id']))
            before_result = source.runs.publication_result(ref)
            warm_timings = source.runs.phase_timings(run['id'])
        self.assertEqual(before_run['events'], failed['events'])
        self.assertEqual(before_run['state'], failed['state'])
        stored_timings = before_run['_phase_timings']
        stored_spans = [span for record in stored_timings for span in record['spans']]
        self.assertTrue(any(span['phase'] == 'publication' and span['state'] == 'incomplete'
                            for span in stored_spans))
        self.assertTrue(any(span['phase'] == 'recovery_publication' and span['state'] == 'measured'
                            for span in stored_spans))
        self.assertEqual(warm_timings['original_run_state'], 'interrupted')

        source.close()
        original_tree = tree_manifest(source.path)
        original_modes = tree_modes(source.path, original_tree)
        journal_path = source.path/'workspace-runs'/'.coordinator-v1.json'
        journal_bytes = journal_path.read_bytes()
        journal = json.loads(journal_bytes)
        self.assertEqual(journal['request'], recovered_health['recovery_request'])
        self.assertEqual(journal['request']['completed_generation'], 2)
        metadata = Metadata(source.path, dsn=original_dsn, create=False)
        try:
            # Retain a nontrivial sequence high-water mark even with no live job
            # row. This authored fixture state must survive every restore retry.
            sequence = read_sequences(metadata)['generation_jobs']
            metadata.connection.execute('SELECT setval(pg_get_serial_sequence(%s,%s),%s,true)',
                ('generation_jobs', 'ordinal', sequence['last_value'] + 19))
            original_tables, original_sequences = read_catalog(metadata), read_sequences(metadata)
            original_version = metadata.schema_version
        finally:
            metadata.close()
        backup = fixture.path/'stopped-integrated-backup'
        receipt = backup_catalog(source.path, backup, dsn=original_dsn, quiesced=True)
        backup_tree = tree_manifest(backup)
        self.assertEqual(tree_modes(backup/'catalog', original_tree), original_modes)
        self.assertEqual(receipt['files'], original_tree)
        self.assertEqual(receipt['tables'], summaries(original_tables))

        database = 'retention_restore_'+uuid.uuid4().hex
        restored_dsn = make_conninfo(original_dsn, dbname=database)
        with psycopg.connect(original_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))

        def drop_restored_database():
            if cleanup.get('restored_database_removed'):
                return
            with psycopg.connect(original_dsn, autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
                self.assertIsNone(admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',
                                                (database,)).fetchone())
            cleanup['restored_database_removed'] = database
        self.addCleanup(drop_restored_database)

        restored_path = fixture.path/'restored-integrated-catalog'
        staging = restored_path.with_name(restored_path.name+'.restore-'+receipt['dataset_id'])
        marker_name = '.restore-receipt-'+digest(receipt)+'.json'
        interruptions = []

        class AuthoredRestoreInterruption(OSError):
            pass

        def unchanged_originals():
            self.assertEqual(tree_manifest(source.path), original_tree)
            self.assertEqual(tree_modes(source.path, original_tree), original_modes)
            self.assertEqual(tree_manifest(backup), backup_tree)
            self.assertEqual(tree_modes(backup/'catalog', original_tree), original_modes)
            original = Metadata(source.path, dsn=original_dsn, create=False)
            try:
                self.assertEqual(read_catalog(original), original_tables)
                self.assertEqual(read_sequences(original), original_sequences)
            finally:
                original.close()

        def checkpoint(seam, expected_tables, expected_sequences, *, published=False):
            self.assertEqual(restored_path.exists(), published)
            self.assertEqual(staging.exists(), not published)
            path = restored_path if published else staging
            self.assertEqual(json.loads((path/marker_name).read_bytes()), {
                'kind': 'postgresql-restore', 'backup_sha256': digest(receipt),
                'dataset_id': receipt['dataset_id']})
            held = Metadata(path, dsn=restored_dsn, create=False)
            try:
                tables, sequences = read_catalog(held), read_sequences(held)
                self.assertEqual(tables, expected_tables)
                self.assertEqual(sequences, expected_sequences)
            finally:
                held.close()
            unchanged_originals()
            tree = tree_manifest(path, (marker_name,))
            interruptions.append({'seam': seam, 'destination_published': published,
                'table_sha256': digest(tables), 'sequence_sha256': digest(sequences),
                'tree_sha256': digest(tree), 'source_and_backup_unchanged': True})
            return tree

        with patch('recipe_process.launch', side_effect=AssertionError('Transfer/read replayed compute')) as launch:
            # Real PostgreSQL inserts occur before the authored exception. The
            # catalog transaction rolls back; its private staging identity stays
            # resumable and no final destination has been published.
            empty = {}
            populate = transfer.populate_catalog

            def interrupt_population(metadata, tables):
                empty['tables'], empty['sequences'] = read_catalog(metadata), read_sequences(metadata)
                populate(metadata, tables)
                self.assertEqual(read_catalog(metadata), original_tables)
                raise AuthoredRestoreInterruption('after real population, before commit')

            with patch.object(transfer, 'populate_catalog', side_effect=interrupt_population):
                with self.assertRaisesRegex(AuthoredRestoreInterruption, 'before commit'):
                    restore_catalog(backup, restored_path, dsn=restored_dsn)
            self.assertFalse(any(table['count'] for table in empty['tables'].values()))
            checkpoint('metadata_transaction_rollback', empty['tables'], empty['sequences'])

            # Interrupt after one exact journal file has actually been copied
            # and renamed, while later Run artifacts are still absent. Metadata
            # has committed; the public destination must still be absent.
            rename = transfer.os.rename
            journal_target = staging/'workspace-runs'/'.coordinator-v1.json'

            def interrupt_copy(src, dst):
                rename(src, dst)
                if Path(dst) == journal_target:
                    raise AuthoredRestoreInterruption('after journal file copy')

            with patch.object(transfer.os, 'rename', side_effect=interrupt_copy):
                with self.assertRaisesRegex(AuthoredRestoreInterruption, 'journal file copy'):
                    restore_catalog(backup, restored_path, dsn=restored_dsn)
            partial = checkpoint('committed_metadata_partial_files', original_tables, original_sequences)
            self.assertEqual(journal_target.read_bytes(), journal_bytes)
            self.assertLess(set(partial), set(original_tree))
            self.assertTrue(all(original_tree[name] == entry for name, entry in partial.items()))

            # A lost reply after the real final rename leaves a complete result.
            # Retrying must reconcile that result instead of overwriting it.
            def lose_rename_reply(src, dst):
                rename(src, dst)
                if Path(dst) == restored_path:
                    raise AuthoredRestoreInterruption('after destination rename')

            with patch.object(transfer.os, 'rename', side_effect=lose_rename_reply):
                with self.assertRaisesRegex(AuthoredRestoreInterruption, 'destination rename'):
                    restore_catalog(backup, restored_path, dsn=restored_dsn)
            self.assertEqual(checkpoint('published_destination_lost_reply', original_tables,
                                       original_sequences, published=True), original_tree)
            self.assertEqual(tree_modes(restored_path, original_tree), original_modes)
            marker = restore_catalog(backup, restored_path, dsn=restored_dsn)
            self.assertEqual(marker['dataset_id'], source.db.dataset_id)
            self.assertEqual(tree_manifest(restored_path, (marker_name,)), original_tree)
            self.assertEqual((restored_path/'workspace-runs'/'.coordinator-v1.json').read_bytes(), journal_bytes)
            restored_metadata = Metadata(restored_path, dsn=restored_dsn, create=False)
            try:
                self.assertEqual(restored_metadata.schema_version, original_version)
                self.assertEqual(read_catalog(restored_metadata), original_tables)
                self.assertEqual(read_sequences(restored_metadata), original_sequences)
            finally:
                restored_metadata.close()

            # Actual application activation may advance its diagnostic generation;
            # it cannot rewrite the immutable completed acknowledgement or Run.
            restored = Dataset(restored_path, dsn=restored_dsn,
                               project_roots={'fixture': fixture.project_path})
            self.addCleanup(restored.close)
            with fixture.owner.bound(restored):
                health = restored.runs.coordinator_health()
                self.assertEqual(health['generation'], journal['generation']+1)
                self.assertEqual(health['recovery_request'], journal['request'])
                self.assertEqual(health['fault'], journal['fault'])
                self.assertIsNone(restored.runs._thread)
                self.assertEqual(restored.runs._load(run['id']), before_run)
                self.assertEqual(restored.runs.publication_result(ref), before_result)
                cold_timings = restored.runs.phase_timings(run['id'])
                self.assertFalse(any(span['state'] == 'open'
                    for record in cold_timings['records'] for span in record['spans']))
                for record in stored_timings:
                    actual = next(item for item in cold_timings['records'] if item['clock_id'] == record['clock_id'])
                    self.assertEqual(actual, record)
                with self.assertRaises(WorkbenchError):
                    restored.runs.artifact(run['id'], 'result.txt')

            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(restored))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            server_stopped = []

            def stop_server():
                if not server_stopped:
                    server.shutdown(); server.server_close(); worker.join(5)
                    self.assertFalse(worker.is_alive())
                    server_stopped.append(True)
            self.addCleanup(stop_server)
            endpoint = 'http://127.0.0.1:'+str(server.server_port)
            client = agent_api.AgentClient(endpoint, reader['token'], restored.db.dataset_id)
            workflow = WorkflowClient(client)
            self.assertEqual(client.call('runs.coordinator_health', {})['result']['recovery_request'], journal['request'])
            self.assertEqual(client.call('runs.phase_timings', {'run_id': run['id']})['result'], cold_timings)
            manifest = workflow.collection_manifest(result_ref=ref, names=['result.txt'])
            self.assertEqual(manifest['source'], {'ref': ref})
            sdk_directory = fixture.path/'sdk-collected'; sdk_directory.mkdir(mode=0o700)
            sdk_receipt = workflow.collect(manifest, sdk_directory, chunk_bytes=7)
            self.assertEqual(sdk_receipt['state'], 'complete', sdk_receipt)
            self.assertEqual(sdk_receipt['items'][0]['receipt']['result_ref'], ref)
            self.assertEqual((sdk_directory/'result.txt').read_bytes(), fixture.input)

            token = fixture.path/'restored-consumer.token'
            token.write_text(reader['token']); token.chmod(0o600)
            config = fixture.path/'restored-consumer.json'
            config.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': restored.db.dataset_id,
                                          'token_file': str(token), 'timeout': 20})); config.chmod(0o600)
            ref_file = fixture.path/'result-ref.json'; ref_file.write_text(json.dumps(ref))

            def cli(*arguments):
                called = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'project_cli.py'),
                    '--config', str(config), *map(str, arguments)], capture_output=True, text=True, timeout=90)
                self.assertEqual(called.returncode, 0, called.stderr+called.stdout)
                self.assertNotIn(reader['token'], called.stderr+called.stdout)
                return json.loads(called.stdout)

            self.assertEqual(cli('coordinator-status')['recovery_request'], journal['request'])
            self.assertEqual(cli('phase-timings', '--run-id', run['id']), cold_timings)
            self.assertEqual(cli('publication-result', '--ref', ref_file), before_result)
            cli_manifest = cli('collection-manifest', '--ref', ref_file, '--name', 'result.txt')
            self.assertEqual(cli_manifest, manifest)
            manifest_file = fixture.path/'collection-manifest.json'
            manifest_file.write_text(json.dumps(cli_manifest))
            cli_directory = fixture.path/'cli-collected'; cli_directory.mkdir(mode=0o700)
            cli_receipt = cli('collect', '--manifest', manifest_file, '--directory', cli_directory)
            self.assertEqual(cli_receipt['state'], 'complete', cli_receipt)
            self.assertEqual(cli_receipt['items'][0]['receipt']['result_ref'], ref)
            self.assertEqual((cli_directory/'result.txt').read_bytes(), fixture.input)
            self.assertEqual((cli_directory/'result.txt').stat().st_mode & 0o777, 0o600)
            self.assertEqual((sdk_directory/'result.txt').stat().st_mode & 0o777, 0o600)
            stop_server()
            self.assertEqual(read_catalog(restored.db), original_tables)
            self.assertEqual(read_sequences(restored.db), original_sequences)
            self.assertEqual(restored.runs._load(run['id'])['_phase_timings'], stored_timings)
            self.assertIsNone(restored.runs._thread)
            launch.assert_not_called()
            restored.close()

        unchanged_originals()
        drop_restored_database()
        drop_source()
        if report_path := os.environ.get('TULDOK_RETENTION_ACCEPTANCE_REPORT'):
            report = {'format': 'integrated_retention_restore_acceptance_v2',
                'scope': 'Real neutral custody, PostgreSQL stopped transfer and current HTTP/SDK/CLI; no science or performance claim',
                'schema_version': original_version, 'catalog_id': ref['catalog_id'], 'run_id': run['id'],
                'result_ref': ref, 'table_summaries': summaries(original_tables),
                'sequences': original_sequences, 'catalog_tree_sha256': digest(original_tree),
                'backup_tree_sha256': digest(backup_tree), 'journal_sha256': hashlib.sha256(journal_bytes).hexdigest(),
                'retained_timing_sha256': digest(stored_timings), 'recovery_request': journal['request'],
                'stored_span_states': sorted({span['state'] for span in stored_spans}),
                'artifact_sha256': hashlib.sha256(fixture.input).hexdigest(), 'artifact_bytes': len(fixture.input),
                'raw_transfer_equal': True, 'source_and_backup_unchanged': True,
                'restore_interruptions': interruptions, 'raw_permissions_equal': True,
                'authored_sequence_fixture': {'table': 'generation_jobs', 'before': sequence,
                    'retained': original_sequences['generation_jobs']},
                'cold_reads_and_collection_preserve_all_tables_and_sequences': True,
                'compute_replay_calls': launch.call_count, 'cleanup': cleanup}
            with Path(report_path).open('x') as stream:
                json.dump(report, stream, indent=2); stream.write('\n')
