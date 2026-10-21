"""Explicit same-attempt publication recovery, never compute retry or promotion."""
import copy
from contextlib import contextmanager
import hashlib
import os
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PublicationRecoveryTests(unittest.TestCase):
    def failed_publication(self):
        import test_external_runs as fixtures
        fixture = fixtures.ExternalExecutionTests('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        run = fixture.queued(fixture.body(approval=fixture.approve()))
        run = fixture.dataset.runs._load(run['id'])
        with patch.object(fixture.dataset.runs, '_copy_verified', side_effect=OSError('authored interrupted copy')):
            fixture.dataset.runs._run_attempt(run, (fixture.dataset.runs._capacity.cores[0],),
                                              fixture.dataset.runs._capacity.claim(run))
        fixture.reopen()
        saved = fixture.dataset.runs._load(run['id'])
        self.assertEqual(saved['state'], 'interrupted')
        self.assertEqual(saved['publication_fault']['code'], 'unavailable')
        return fixture, saved

    def body(self, run):
        return {'run_id': run['id'], 'source_ref': run['publication_source'],
                'request_key': 'publication-recovery-stable-request'}

    def counts(self, dataset):
        return {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in ('workspace_runs', 'access_execution_grants',
                              'access_execution_consumptions', 'model_attempt_reservations')}

    def test_same_run_recovers_exact_result_without_replay_or_new_run_or_grant(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        before = self.counts(dataset); events = copy.deepcopy(saved['events'])
        body = self.body(saved)
        with fixture.owner.bound(dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')):
            status = dataset.runs.publication_status(saved['id'])
            self.assertEqual(status['verification'], 'saved_metadata_only')
            self.assertEqual(status['eligibility'], 'requires_verification')
            self.assertEqual(status['source_ref'], body['source_ref'])
            self.assertIsNone(status['continuation'])
            recovered = dataset.runs.recover_publication(body)
            self.assertEqual(recovered['state'], 'published')
            ref = recovered['result_ref']
            self.assertEqual(dataset.runs.publication_status(saved['id'])['continuation']['result_ref'], ref)
            result = dataset.runs.publication_result(ref)
            self.assertEqual(result['original_run_state'], 'interrupted')
            self.assertEqual(result['result_ref'], ref)
            raw, artifact = dataset.runs.publication_artifact(ref, 'result.txt', hashlib.sha256(fixture.input).hexdigest())
            self.assertEqual(raw, fixture.input)
            self.assertEqual(artifact['bytes'], len(raw))
            self.assertEqual(dataset.runs.get(saved['id'])['state'], 'interrupted')
            with self.assertRaises(WorkbenchError): dataset.runs.artifact(saved['id'], 'result.txt')
            with patch.object(dataset.runs, '_copy_verified', wraps=dataset.runs._copy_verified) as copied:
                again = dataset.runs.recover_publication(body)
                self.assertEqual(again['result_ref'], ref)
                # Revalidation may hash bytes; an existing result may not be recopied.
                self.assertFalse(any(len(call.args) > 3 and call.args[3] is not None for call in copied.call_args_list))
        self.assertEqual(self.counts(dataset), before)
        after = dataset.runs._load(saved['id'])
        self.assertEqual(after['events'], events)
        self.assertEqual(after['state'], saved['state'])
        self.assertEqual(after['request_sha256'], saved['request_sha256'])
        with patch('recipe_process.launch', side_effect=AssertionError('Reopen replayed compute')): fixture.reopen()
        with fixture.owner.bound(fixture.dataset):
            self.assertEqual(fixture.dataset.runs.recover_publication(body)['result_ref'], ref)
            self.assertEqual(fixture.dataset.runs.publication_artifact(ref, 'result.txt', artifact['sha256'])[0], fixture.input)

    def test_cancel_or_budget_during_existing_file_verification_preserves_bytes(self):
        import run_publication
        for code in ('cancelled', 'unavailable'):
            with self.subTest(code=code):
                fixture, saved = self.failed_publication(); dataset = fixture.dataset
                destination = dataset.runs.path / saved['id']
                payload = destination / 'result.txt'; payload.write_bytes(fixture.input)
                expected = payload.read_bytes(); identity = destination.stat().st_ino
                original = run_publication._copy
                def stop(runs, directory, *args, **kwargs):
                    if os.fstat(directory).st_ino == identity:
                        raise WorkbenchError('Authored stop during existing output verification', code, 409)
                    return original(runs, directory, *args, **kwargs)
                with fixture.owner.bound(dataset), patch('run_publication._copy', side_effect=stop):
                    with self.assertRaises(WorkbenchError) as caught:
                        dataset.runs.recover_publication(self.body(saved))
                    self.assertEqual(caught.exception.code, code)
                self.assertEqual(payload.read_bytes(), expected)
                self.assertEqual(dataset.runs._load(saved['id'])['publication_continuation']['state'], 'paused')

    def test_existing_study_reservation_and_conservative_charge_survive_recovery(self):
        from http.server import ThreadingHTTPServer
        import json
        from pathlib import Path
        import subprocess
        import sys
        import uuid

        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        import agent_api
        from app import Dataset, make_handler
        import backup_metadata as transfer
        from metadata import Metadata
        import recipe_process
        import test_experiments as fixtures
        from tuldok_client import WorkflowClient

        fixture = fixtures.StudyTests('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        dataset = fixture.dataset
        source_dsn, source_schema = dataset.db.dsn, dataset.db.schema
        cleanup = {}

        def drop_source():
            if cleanup.get('source_schema_removed'):
                return
            dataset.close()
            with psycopg.connect(source_dsn, autocommit=True) as admin:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(source_schema)))
                self.assertIsNone(admin.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',
                                                (source_schema,)).fetchone())
            cleanup['source_schema_removed'] = source_schema
        self.addCleanup(drop_source)

        trial, _ = fixture.prepare(); fixture.open()
        body = fixture.admission_body(trial, fixture.approve())
        with dataset.access.bind(fixture.agent['token']), patch.object(dataset.runs, '_start'):
            admitted = fixture.studies.admit(fixture.study['id'], body)
        run = dataset.runs._load(admitted['run']['id'])
        with patch.object(dataset.runs, '_copy_verified', side_effect=OSError('Authored interrupted Study publication')), \
                patch('recipe_process.launch', wraps=recipe_process.launch) as executed:
            dataset.runs._run_attempt(run, (dataset.runs._capacity.cores[0],),
                                      dataset.runs._capacity.claim(run))
        self.assertEqual(executed.call_count, 1)
        saved = dataset.runs._load(run['id'])
        self.assertEqual(saved['state'], 'interrupted')
        self.assertEqual(saved['custody_phase'], 'drained')
        self.assertEqual(saved['publication_fault']['code'], 'unavailable')
        with fixture.owner.bound(dataset):
            before = fixture.studies.reconcile(fixture.study['id'])
        self.assertEqual(before['reservations'][0]['state'], 'settled')
        self.assertEqual(before['charged'], admitted['reservation']['envelope'])
        reservation = dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s',
                                        (run['id'],)).fetchone()[0]
        counts = self.counts(dataset)
        with fixture.owner.bound(dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed Study compute')):
            first = dataset.runs.recover_publication(self.body(saved))
            self.assertEqual(first['state'], 'published')
            self.assertEqual(dataset.runs.recover_publication(self.body(saved)), first)
            after = fixture.studies.reconcile(fixture.study['id'])
        self.assertEqual(after['reservations'], before['reservations'])
        self.assertEqual(after['charged'], before['charged'])
        self.assertEqual(dataset.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s',
                                         (run['id'],)).fetchone()[0], reservation)
        self.assertEqual(self.counts(dataset), counts)
        current = dataset.runs._load(run['id'])
        self.assertEqual(current['state'], 'interrupted')
        self.assertEqual(current['events'], saved['events'])

        # Transfer this populated, already settled Study and its exact recovered
        # result together. Separate queued-Study and direct-Run restore cases do
        # not prove that this reservation/charge/ref composition survives.
        self.assertEqual(counts, {'workspace_runs': 1, 'access_execution_grants': 1,
            'access_execution_consumptions': 1, 'model_attempt_reservations': 1})
        ref = first['result_ref']
        with fixture.owner.bound(dataset):
            expected_trial = copy.deepcopy(dataset.studies.trial(trial['id']))
            expected_material = copy.deepcopy(dataset.pipelines.recipe_material(trial['material'], verify=True))
            expected_result = copy.deepcopy(dataset.runs.publication_result(ref))
            reader = dataset.access.issue({'label': 'Cold restored Study inspector', 'scopes': ['inspect']})
        dataset.close()
        source_tree = transfer.tree_manifest(dataset.path)
        source_modes = transfer.tree_modes(dataset.path, source_tree)
        original = Metadata(dataset.path, dsn=source_dsn, create=False)
        try:
            source_tables, source_sequences = transfer.read_catalog(original), transfer.read_sequences(original)
            source_version = original.schema_version
        finally:
            original.close()
        backup = fixture.path/'settled-study-backup'
        receipt = transfer.backup_catalog(dataset.path, backup, dsn=source_dsn, quiesced=True)
        backup_tree = transfer.tree_manifest(backup)
        self.assertEqual(receipt['files'], source_tree)
        self.assertEqual(receipt['tables'], transfer.summaries(source_tables))
        self.assertEqual(transfer.tree_modes(backup/'catalog', source_tree), source_modes)

        database = 'study_publication_restore_'+uuid.uuid4().hex
        restored_dsn = make_conninfo(source_dsn, dbname=database)
        with psycopg.connect(source_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))

        def drop_restored_database():
            if cleanup.get('restored_database_removed'):
                return
            with psycopg.connect(source_dsn, autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))
                self.assertIsNone(admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',
                                                (database,)).fetchone())
            cleanup['restored_database_removed'] = database
        self.addCleanup(drop_restored_database)

        restored_path = fixture.path/'restored-settled-study'
        with patch('recipe_process.launch', side_effect=AssertionError('Study transfer replayed compute')) as replay:
            marker = transfer.restore_catalog(backup, restored_path, dsn=restored_dsn)
            marker_name = '.restore-receipt-'+transfer.digest(receipt)+'.json'
            self.assertEqual(marker['dataset_id'], dataset.db.dataset_id)
            self.assertEqual(transfer.tree_manifest(restored_path, (marker_name,)), source_tree)
            self.assertEqual(transfer.tree_modes(restored_path, source_tree), source_modes)
            held = Metadata(restored_path, dsn=restored_dsn, create=False)
            try:
                self.assertEqual(held.schema_version, source_version)
                self.assertEqual(transfer.read_catalog(held), source_tables)
                self.assertEqual(transfer.read_sequences(held), source_sequences)
            finally:
                held.close()

            cold = Dataset(restored_path, dsn=restored_dsn, project_roots={'fixture': fixture.project_path})
            self.addCleanup(cold.close)
            with fixture.owner.bound(cold):
                self.assertEqual(cold.studies.trial(trial['id']), expected_trial)
                self.assertEqual(cold.pipelines.recipe_material(trial['material'], verify=True), expected_material)
                self.assertEqual(cold.studies.reconcile(fixture.study['id']), after)
                self.assertEqual(cold.studies.reconcile(fixture.study['id']), after)
                self.assertEqual(cold.runs._load(run['id']), current)
                self.assertEqual(cold.runs.publication_result(ref), expected_result)
                self.assertEqual(cold.runs.recover_publication(self.body(saved)), first)
                self.assertEqual(cold.db.execute('SELECT document FROM model_attempt_reservations WHERE run_id=%s',
                                               (run['id'],)).fetchone()[0], reservation)
                self.assertEqual(self.counts(cold), counts)
                with self.assertRaises(WorkbenchError):
                    cold.runs.artifact(run['id'], 'result.txt')
            self.assertIsNone(cold.runs._thread)

            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cold))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            stopped = []

            def stop_server():
                if not stopped:
                    server.shutdown(); server.server_close(); worker.join(5)
                    self.assertFalse(worker.is_alive())
                    stopped.append(True)
            self.addCleanup(stop_server)

            endpoint = 'http://127.0.0.1:'+str(server.server_port)
            client = agent_api.AgentClient(endpoint, reader['token'], cold.db.dataset_id)
            self.assertEqual(client.call('studies.get', {'study_id': fixture.study['id']})['result'], after)
            self.assertEqual(client.call('studies.trial', {'trial_id': trial['id']})['result'], expected_trial)
            self.assertEqual(client.call('recipes.material', {'ref': trial['material']})['result'], expected_material)
            workflow = WorkflowClient(client)
            manifest = workflow.collection_manifest(result_ref=ref, names=['result.txt'])
            self.assertEqual(manifest['source'], {'ref': ref})
            sdk_directory = fixture.path/'study-sdk-collected'; sdk_directory.mkdir(mode=0o700)
            sdk_receipt = workflow.collect(manifest, sdk_directory, chunk_bytes=7)
            self.assertEqual(sdk_receipt['state'], 'complete', sdk_receipt)
            self.assertEqual(sdk_receipt['items'][0]['receipt']['result_ref'], ref)
            self.assertEqual((sdk_directory/'result.txt').read_bytes(), fixture.input)

            token = fixture.path/'study-reader.token'; token.write_text(reader['token']); token.chmod(0o600)
            config = fixture.path/'study-reader.json'
            config.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': cold.db.dataset_id,
                'token_file': str(token), 'timeout': 20})); config.chmod(0o600)
            ref_file = fixture.path/'study-result-ref.json'; ref_file.write_text(json.dumps(ref))
            arguments = fixture.path/'study-read.json'
            arguments.write_text(json.dumps({'study_id': fixture.study['id']}))

            def cli(*arguments):
                called = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'project_cli.py'),
                    '--config', str(config), *map(str, arguments)], capture_output=True, text=True, timeout=90)
                self.assertEqual(called.returncode, 0, called.stderr+called.stdout)
                self.assertNotIn(reader['token'], called.stderr+called.stdout)
                return json.loads(called.stdout)

            self.assertEqual(cli('call', '--operation', 'studies.get', '--arguments', arguments), after)
            self.assertEqual(cli('publication-result', '--ref', ref_file), expected_result)
            cli_manifest = cli('collection-manifest', '--ref', ref_file, '--name', 'result.txt')
            self.assertEqual(cli_manifest, manifest)
            manifest_file = fixture.path/'study-collection.json'; manifest_file.write_text(json.dumps(cli_manifest))
            cli_directory = fixture.path/'study-cli-collected'; cli_directory.mkdir(mode=0o700)
            cli_receipt = cli('collect', '--manifest', manifest_file, '--directory', cli_directory)
            self.assertEqual(cli_receipt['state'], 'complete', cli_receipt)
            self.assertEqual(cli_receipt['items'][0]['receipt']['result_ref'], ref)
            self.assertEqual((cli_directory/'result.txt').read_bytes(), fixture.input)
            for path in (sdk_directory/'result.txt', cli_directory/'result.txt'):
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            stop_server()
            self.assertEqual(transfer.read_catalog(cold.db), source_tables)
            self.assertEqual(transfer.read_sequences(cold.db), source_sequences)
            self.assertEqual(cold.runs._load(run['id']), current)
            cold_counts = self.counts(cold)
            self.assertEqual(cold_counts, counts)
            self.assertIsNone(cold.runs._thread)
            replay.assert_not_called()
            cold.close()

        self.assertEqual(transfer.tree_manifest(dataset.path), source_tree)
        self.assertEqual(transfer.tree_modes(dataset.path, source_tree), source_modes)
        self.assertEqual(transfer.tree_manifest(backup), backup_tree)
        self.assertEqual(transfer.tree_modes(backup/'catalog', source_tree), source_modes)
        original = Metadata(dataset.path, dsn=source_dsn, create=False)
        try:
            self.assertEqual(transfer.read_catalog(original), source_tables)
            self.assertEqual(transfer.read_sequences(original), source_sequences)
        finally:
            original.close()
        drop_restored_database()
        drop_source()
        if report_path := os.environ.get('TULDOK_STUDY_RESTORE_ACCEPTANCE_REPORT'):
            report = {'format': 'study_publication_restore_acceptance_v1',
                'scope': 'Real neutral Study recovery, stopped raw transfer and cold current clients; no science/performance claim',
                'schema_version': source_version, 'catalog_id': ref['catalog_id'],
                'study_id': fixture.study['id'], 'trial_id': trial['id'], 'run_id': run['id'],
                'result_ref': ref, 'original_run_state': saved['state'],
                'original_fault': saved['publication_fault'], 'custody_phase': saved['custody_phase'],
                'reservation_document_sha256': hashlib.sha256(reservation.encode()).hexdigest(),
                'settled_reservation': after['reservations'][0], 'charged_before': before['charged'],
                'charged_after': after['charged'], 'original_envelope': admitted['reservation']['envelope'],
                'counts_before': counts, 'counts_after': cold_counts,
                'table_summaries': transfer.summaries(source_tables), 'sequences': source_sequences,
                'source_tree_sha256': transfer.digest(source_tree), 'source_modes_sha256': transfer.digest(source_modes),
                'backup_tree_sha256': transfer.digest(backup_tree), 'source_and_backup_unchanged': True,
                'raw_transfer_equal_before_activation': True, 'cold_tables_and_sequences_unchanged': True,
                'artifact_sha256': hashlib.sha256(fixture.input).hexdigest(), 'artifact_bytes': len(fixture.input),
                'sdk_and_cli_collection_complete': True, 'same_key_result_unchanged': True,
                'actual_attempt_launch_calls': executed.call_count, 'restore_and_consumer_replay_calls': replay.call_count,
                'cleanup': cleanup}
            with Path(report_path).open('x') as stream:
                json.dump(report, stream, indent=2); stream.write('\n')

    def test_partial_copy_capacity_counts_remaining_bytes_before_replacement(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        payload = dataset.runs.path / saved['id'] / 'result.txt'
        self.assertEqual(payload.stat().st_size, 0)
        with fixture.owner.bound(dataset), patch('run_publication.shutil.disk_usage',
                return_value=SimpleNamespace(free=512 * 1024**2 + len(fixture.input) - 1)):
            with self.assertRaises(WorkbenchError): dataset.runs.recover_publication(self.body(saved))
        self.assertEqual(payload.stat().st_size, 0)
        with fixture.owner.bound(dataset), patch('run_publication.shutil.disk_usage',
                return_value=SimpleNamespace(free=512 * 1024**2 + len(fixture.input))):
            self.assertEqual(dataset.runs.recover_publication(self.body(saved))['state'], 'published')

    def test_original_manifest_sync_fault_recovery_syncs_every_reused_file(self):
        import test_external_runs as fixtures
        fixture = fixtures.ExternalExecutionTests('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        dataset = fixture.dataset
        run = dataset.runs._load(fixture.queued(fixture.body(approval=fixture.approve()))['id'])
        sync = os.fsync; failed = []
        def fault(descriptor):
            name = os.readlink('/proc/self/fd/' + str(descriptor))
            if name == str(dataset.runs.path / run['id'] / 'artifact-manifest.json') and not failed:
                failed.append(True); raise OSError('Authored original manifest fsync failure')
            return sync(descriptor)
        with patch('runs.os.fsync', side_effect=fault):
            dataset.runs._run_attempt(run, (dataset.runs._capacity.cores[0],), dataset.runs._capacity.claim(run))
        self.assertTrue(failed)
        fixture.reopen(); dataset = fixture.dataset
        saved = dataset.runs._load(run['id'])
        self.assertEqual(saved['state'], 'interrupted')
        directory = dataset.runs.path / run['id']
        before = {path.name: (path.stat().st_ino, path.read_bytes()) for path in directory.iterdir()}
        self.assertEqual(set(before), {'result.txt', 'custody-receipt.json', 'artifact-manifest.json'})
        synced = set()
        def record(descriptor):
            path = os.readlink('/proc/self/fd/' + str(descriptor))
            if path.startswith(str(directory) + '/'):
                synced.add(path.rsplit('/', 1)[-1])
            return sync(descriptor)
        with fixture.owner.bound(dataset), patch('run_publication.os.fsync', side_effect=record):
            recovered = dataset.runs.recover_publication(self.body(saved))
            self.assertEqual(recovered['state'], 'published')
        self.assertEqual(synced, set(before))
        self.assertEqual({path.name: (path.stat().st_ino, path.read_bytes()) for path in directory.iterdir()}, before)

    def held_recovery(self, fixture, saved):
        import run_publication
        entered = threading.Event(); release = threading.Event(); outcomes = []
        original = run_publication._verify_source
        def held(*args, **kwargs):
            entered.set()
            if not release.wait(15): raise AssertionError('Recovery test release was not delivered')
            return original(*args, **kwargs)
        def run():
            try:
                with fixture.owner.bound(fixture.dataset):
                    outcomes.append(fixture.dataset.runs.recover_publication(self.body(saved)))
            except BaseException as error: outcomes.append(error)
        return entered, release, outcomes, held, run

    def test_concurrent_identical_requests_share_one_continuation(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        entered, release, outcomes, held, run = self.held_recovery(fixture, saved)
        with patch('run_publication._verify_source', side_effect=held):
            worker = threading.Thread(target=run); worker.start()
            try:
                self.assertTrue(entered.wait(10))
                with fixture.owner.bound(dataset):
                    same = dataset.runs.recover_publication(self.body(saved))
                    self.assertEqual((same['state'], same['attempt_count']), ('recovering', 1))
                    different = dict(self.body(saved), request_key='conflicting-publication-request')
                    with self.assertRaises(WorkbenchError): dataset.runs.recover_publication(different)
            finally:
                release.set(); worker.join(20)
        self.assertFalse(worker.is_alive()); self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], dict)
        self.assertEqual((outcomes[0]['state'], outcomes[0]['attempt_count']), ('published', 1))

    def test_cancel_active_publication_pauses_without_changing_original_outcome(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        entered, release, outcomes, held, run = self.held_recovery(fixture, saved)
        with patch('run_publication._verify_source', side_effect=held):
            worker = threading.Thread(target=run); worker.start()
            try:
                self.assertTrue(entered.wait(10))
                with fixture.owner.bound(dataset):
                    status = dataset.runs.cancel_publication({'run_id': saved['id'],
                        'request_key': self.body(saved)['request_key']})
                    self.assertTrue(status['cancel_requested'])
            finally:
                release.set(); worker.join(20)
        self.assertFalse(worker.is_alive()); self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], WorkbenchError); self.assertEqual(outcomes[0].code, 'cancelled')
        current = dataset.runs._load(saved['id'])
        self.assertEqual(current['state'], 'interrupted')
        self.assertEqual(current['publication_continuation']['state'], 'paused')
        self.assertIsNone(current['publication_continuation']['result_ref'])
        with fixture.owner.bound(dataset):
            resumed = dataset.runs.recover_publication(self.body(saved))
            self.assertEqual((resumed['state'], resumed['attempt_count']), ('published', 2))
            committed = dataset.runs.cancel_publication({'run_id': saved['id'],
                'request_key': self.body(saved)['request_key']})
            self.assertEqual(committed['result_ref'], resumed['result_ref'])
            self.assertEqual(committed['state'], 'published')

    def test_shutdown_drains_owned_recovery_before_closing_metadata(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        entered, release, outcomes, held, run = self.held_recovery(fixture, saved)
        closes = []
        def close():
            try: dataset.close(); closes.append('closed')
            except BaseException as error: closes.append(error)
        with patch('run_publication._verify_source', side_effect=held):
            worker = threading.Thread(target=run); worker.start()
            self.assertTrue(entered.wait(10))
            closer = threading.Thread(target=close); closer.start()
            try:
                self.assertTrue(dataset.runs._stop.wait(10))
                self.assertTrue(closer.is_alive())
            finally:
                release.set(); worker.join(20); closer.join(20)
        self.assertFalse(worker.is_alive()); self.assertFalse(closer.is_alive())
        self.assertEqual(closes, ['closed']); self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], WorkbenchError)
        self.assertEqual(outcomes[0].code, 'cancelled')
        fixture.reopen()
        current = fixture.dataset.runs._load(saved['id'])
        self.assertEqual(current['publication_continuation']['state'], 'paused')
        self.assertEqual(current['state'], 'interrupted')

    def test_unowned_partial_and_changed_final_result_refuse(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        directory = dataset.runs.path / saved['id']
        foreign = directory / 'unowned.txt'; foreign.write_bytes(b'preserve unrelated bytes')
        with fixture.owner.bound(dataset):
            with self.assertRaises(WorkbenchError): dataset.runs.recover_publication(self.body(saved))
            self.assertEqual(foreign.read_bytes(), b'preserve unrelated bytes')
            foreign.unlink()
            ref = dataset.runs.recover_publication(self.body(saved))['result_ref']
            payload = directory / 'result.txt'; original = payload.read_bytes()
            payload.write_bytes(b'x' * len(original))
            with self.assertRaises(WorkbenchError):
                dataset.runs.publication_result(ref)
            with self.assertRaises(WorkbenchError):
                dataset.runs.recover_publication(self.body(saved))
            self.assertEqual(dataset.runs._load(saved['id'])['publication_continuation']['result_ref'], ref)
            self.assertEqual(payload.read_bytes(), b'x' * len(original))

    def test_revocation_during_result_storage_prevents_attachment(self):
        from access import AccessError
        import run_publication
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        original = run_publication._store
        def revoke(*args, **kwargs):
            original(*args, **kwargs)
            dataset.access.revoke(dataset.access.identity()['credential_id'])
        with fixture.owner.bound(dataset), patch('run_publication._store', side_effect=revoke):
            with self.assertRaises(AccessError): dataset.runs.recover_publication(self.body(saved))
        current = dataset.runs._load(saved['id'])
        self.assertEqual(current['state'], 'interrupted')
        self.assertIsNone(current['publication_continuation']['result_ref'])
        self.assertNotEqual(current['publication_continuation']['state'], 'published')

    def test_unknown_final_commit_reply_reconciles_exact_result_without_recopy(self):
        from metadata import CommitOutcomeUnknown
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        transaction = dataset.db.transaction; injected = []
        @contextmanager
        def lose_reply(*args, **kwargs):
            with transaction(*args, **kwargs): yield
            current = dataset.runs._load(saved['id']).get('publication_continuation')
            if current is not None and current['state'] == 'published' and not injected:
                injected.append(True); raise CommitOutcomeUnknown('Authored lost final publication reply')
        with fixture.owner.bound(dataset), patch.object(dataset.db, 'transaction', side_effect=lose_reply):
            with self.assertRaises(CommitOutcomeUnknown): dataset.runs.recover_publication(self.body(saved))
        self.assertTrue(injected)
        original = dataset.runs._load(saved['id'])['publication_continuation']['result_ref']
        with fixture.owner.bound(dataset), patch.object(dataset.runs, '_copy_verified', wraps=dataset.runs._copy_verified) as copied:
            reconciled = dataset.runs.recover_publication(self.body(saved))
        self.assertEqual(reconciled['result_ref'], original)
        self.assertEqual(reconciled['attempt_count'], 1)
        self.assertFalse(any(len(call.args) > 3 and call.args[3] is not None for call in copied.call_args_list))

    def test_cold_result_reader_stops_at_deadline_without_changing_publication(self):
        import run_publication
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        with fixture.owner.bound(dataset):
            ref = dataset.runs.recover_publication(self.body(saved))['result_ref']
            before = dataset.runs._load(saved['id'])
            with patch('run_publication.time.monotonic', return_value=2):
                with self.assertRaises(WorkbenchError) as caught:
                    run_publication.result(dataset.runs, ref, deadline=1)
            self.assertEqual(caught.exception.code, 'unavailable')
            self.assertEqual(dataset.runs._load(saved['id']), before)
            self.assertEqual(dataset.runs.publication_result(ref)['result_ref'], ref)

    def test_stopped_backup_restores_original_proof_and_recovers_in_new_directory(self):
        from app import Dataset
        from backup_metadata import backup_catalog, restore_catalog
        from metadata import Metadata
        from psycopg import sql
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        historical_spec = copy.deepcopy(saved['spec'])
        counts = self.counts(dataset)
        dataset.close()
        backup = fixture.path / 'recovery-backup'
        backup_catalog(dataset.path, backup, quiesced=True)
        old = Metadata(dataset.path, create=False)
        try:
            old.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(old.schema)))
        finally:
            old.close()
        restored = fixture.path / 'recovery-restored'
        restore_catalog(backup, restored)
        with patch('recipe_process.launch', side_effect=AssertionError('Restore replayed compute')):
            fixture.dataset = Dataset(restored, project_roots={'fixture': fixture.project_path})
            cold = fixture.dataset
            self.assertNotEqual(cold.path, dataset.path)
            self.assertEqual(cold.runs._load(saved['id'])['spec'], historical_spec)
            with fixture.owner.bound(cold):
                recovered = cold.runs.recover_publication(self.body(saved))
                self.assertEqual(recovered['state'], 'published')
                result = cold.runs.publication_result(recovered['result_ref'])
                self.assertEqual(result['source_ref'], saved['publication_source'])
                self.assertEqual(cold.runs.publication_artifact(recovered['result_ref'], 'result.txt',
                    hashlib.sha256(fixture.input).hexdigest())[0], fixture.input)
        self.assertEqual(self.counts(cold), counts)
        current = cold.runs._load(saved['id'])
        self.assertEqual(current['state'], saved['state'])
        self.assertEqual(current['events'], saved['events'])

    def test_twenty_attempt_limit_stops_without_compute_or_unbounded_history(self):
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        with fixture.owner.bound(dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')), \
                patch('run_publication._verify_source', side_effect=WorkbenchError('Authored bounded pause', 'unavailable', 409)):
            for _ in range(20):
                with self.assertRaises(WorkbenchError): dataset.runs.recover_publication(self.body(saved))
            with self.assertRaises(WorkbenchError) as caught:
                dataset.runs.recover_publication(self.body(saved))
            self.assertEqual(caught.exception.code, 'unsupported')
        value = dataset.runs._load(saved['id'])['publication_continuation']
        self.assertEqual(len(value['attempts']), 20)
        self.assertEqual(value['state'], 'paused'); self.assertIsNone(value['result_ref'])

    def test_changed_source_output_or_capture_refuses_before_copy(self):
        for changed in ('output', 'capture'):
            with self.subTest(changed=changed):
                fixture, saved = self.failed_publication(); dataset = fixture.dataset
                stage = dataset.runs._external_directory(saved)
                path = stage / ('output/result.txt' if changed == 'output' else 'input/sample')
                original = path.read_bytes(); path.chmod(0o600)
                path.write_bytes(b'x' * len(original)); path.chmod(0o400)
                before = self.counts(dataset)
                with fixture.owner.bound(dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')):
                    with self.assertRaises(WorkbenchError): dataset.runs.recover_publication(self.body(saved))
                self.assertEqual(self.counts(dataset), before)
                self.assertEqual(dataset.runs._load(saved['id'])['state'], 'interrupted')

    def test_recovery_is_owner_only_and_exact_source_ref_is_required(self):
        from access import AccessError
        fixture, saved = self.failed_publication(); dataset = fixture.dataset
        with dataset.access.bind(fixture.agent['token']):
            with self.assertRaises(AccessError): dataset.runs.recover_publication(self.body(saved))
        body = self.body(saved); body['source_ref'] = dict(body['source_ref'], sha256='f' * 64)
        with fixture.owner.bound(dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')):
            with self.assertRaises(WorkbenchError): dataset.runs.recover_publication(body)


if __name__ == '__main__':
    unittest.main()
