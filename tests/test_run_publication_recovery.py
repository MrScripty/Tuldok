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
        import test_experiments as fixtures
        fixture = fixtures.StudyTests('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        dataset = fixture.dataset
        trial, _ = fixture.prepare(); fixture.open()
        body = fixture.admission_body(trial, fixture.approve())
        with dataset.access.bind(fixture.agent['token']), patch.object(dataset.runs, '_start'):
            admitted = fixture.studies.admit(fixture.study['id'], body)
        run = dataset.runs._load(admitted['run']['id'])
        with patch.object(dataset.runs, '_copy_verified', side_effect=OSError('Authored interrupted Study publication')):
            dataset.runs._run_attempt(run, (dataset.runs._capacity.cores[0],),
                                      dataset.runs._capacity.claim(run))
        saved = dataset.runs._load(run['id'])
        self.assertEqual(saved['state'], 'interrupted')
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
