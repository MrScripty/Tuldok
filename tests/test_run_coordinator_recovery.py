"""Real PostgreSQL coordinator failure/replacement; neutral custody, no science claim."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
import json
import os
import threading
import time
import copy
from pathlib import Path
import unittest
import subprocess
import sys
from unittest.mock import patch
from urllib.request import Request, urlopen

import psycopg
import agent_api
from app import make_handler
from metadata import connection_info, CommitOutcomeUnknown
from test_external_runs import ExternalCase
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class CoordinatorRecoveryTests(ExternalCase):
    def wait_for(self, predicate, message):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.02)
        self.fail(message)

    def lock_fault(self):
        runs = self.dataset.runs
        # Real separate backend holds precisely the catalog command lock. The
        # disposable test session uses a shorter configured server lock timeout.
        self.dataset.db.connection.execute("SET lock_timeout='150ms'")
        with psycopg.connect(connection_info(), autocommit=True) as other:
            other.execute('SELECT pg_advisory_lock(%s)', (self.dataset.db._lock_key,))
            runs._start()
            self.wait_for(lambda: runs._coordinator.projection()['state'] == 'faulted',
                          'real advisory-lock timeout did not fault the coordinator')
            self.assertTrue(runs._stop.is_set())
            other.execute('SELECT pg_advisory_unlock(%s)', (self.dataset.db._lock_key,))
        runs._thread.join(5)
        self.assertFalse(runs._thread.is_alive())

    def test_real_lock_timeout_http_health_fences_and_concurrent_owner_recovery(self):
        runs = self.dataset.runs
        queued = self.queued(self.body(approval=self.approve()))
        with self.dataset.lock:
            original = runs._load(queued['id'])
        self.lock_fault()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            request = Request(f'http://127.0.0.1:{server.server_port}/api/workspace/coordinator',
                              headers={**self.owner.headers, agent_api.CONTRACT_HEADER:
                                       agent_api.selected_header('runs.coordinator_health', 1)})
            with urlopen(request, timeout=5) as response:
                health = json.load(response)
            self.assertEqual(health['state'], 'faulted')
            self.assertEqual(health['fault']['category'], 'catalog_lock_timeout')
            self.assertFalse(health['admission_ready'])
            with self.owner.bound(self.dataset), self.assertRaises(WorkbenchError):
                runs._available()
            body = {'expected_generation': health['generation'], 'request_key': 'recover-lock-0001'}

            def recover():
                request = Request(f'http://127.0.0.1:{server.server_port}/api/workspace/coordinator/recover',
                    data=json.dumps(body).encode(), headers={**self.owner.headers, 'Content-Type': 'application/json',
                    agent_api.CONTRACT_HEADER: agent_api.selected_header('runs.recover_coordinator', 1)})
                with urlopen(request, timeout=10) as response:
                    return json.load(response)

            with patch('run_capacity.available_memory', return_value=0), ThreadPoolExecutor(2) as executor:
                replies = list(executor.map(lambda _: recover(), range(2)))
                self.assertEqual([r['generation'] for r in replies], [health['generation'] + 1] * 2)
                self.assertTrue(all(r['admission_ready'] for r in replies))
                with self.dataset.lock:
                    retained = runs._load(queued['id'])
                self.assertEqual(retained, original)
                self.assertEqual(runs._confirmed_external, {queued['id']})
                self.assertTrue(runs._thread.is_alive())
            client = agent_api.CoordinatorOwnerClient(f'http://127.0.0.1:{server.server_port}', self.owner.token,
                                                       self.dataset.db.dataset_id)
            genuine = client.call('runs.recover_coordinator', body)
            self.assertEqual(genuine['status'], 200)
            self.assertEqual(genuine['result']['generation'], health['generation'] + 1)
            forged = copy.deepcopy(genuine)
            forged['result']['recovery_request']['request_key'] = 'forged-recovery-0001'
            with patch.object(client, '_request', return_value=forged) as request:
                with self.assertRaises(agent_api.AgentAPIError) as refused:
                    client.call('runs.recover_coordinator', body)
                self.assertEqual(refused.exception.code, 'transport')
                self.assertEqual(request.call_count, 1)
            with patch.object(client, '_request') as request, self.assertRaises(agent_api.AgentAPIError):
                client.call('runs.recover_publication', {})
            request.assert_not_called()
            endpoint = f'http://127.0.0.1:{server.server_port}'
            def config(label, token):
                secret = self.path / (label+'-token'); secret.write_text(token); secret.chmod(0o600)
                file = self.path / (label+'-config.json')
                file.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': self.dataset.db.dataset_id,
                                            'token_file': str(secret)})); file.chmod(0o600)
                return file
            owner_config = config('owner', self.owner.token)
            agent_config = config('agent', self.agent['token'])
            arguments = self.path/'recovery.json'; arguments.write_text(json.dumps(body))
            for configuration, args in ((owner_config, ['recover-coordinator', '--arguments', str(arguments)]),
                                        (agent_config, ['coordinator-status'])):
                process = subprocess.run([sys.executable, 'project_cli.py', '--config', str(configuration), *args],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=15)
                self.assertEqual(process.returncode, 0, process.stderr.decode())
                self.assertEqual(json.loads(process.stdout)['generation'], health['generation']+1)
        finally:
            server.shutdown(); server.server_close(); worker.join(5)
            self.assertFalse(worker.is_alive())

    def test_refused_recovery_never_stops_a_healthy_coordinator(self):
        runs = self.dataset.runs
        runs._start()
        for generation in (1, 999):
            with self.owner.bound(self.dataset), self.assertRaises(WorkbenchError):
                runs.recover_coordinator({'expected_generation': generation, 'request_key': 'refused-healthy-0001'})
            self.assertFalse(runs._stop.is_set())
            self.assertTrue(runs._thread.is_alive())

    def test_runtime_session_lock_loss_stays_fenced_without_reclaim(self):
        from metadata import _key
        runs = self.dataset.runs
        self.lock_fault()
        key = _key(self.dataset.db.schema + ':worker:workspace_runs')
        self.dataset.db.connection.execute('SELECT pg_advisory_unlock(%s)', (key,))
        with self.owner.bound(self.dataset), self.assertRaises(WorkbenchError):
            runs.recover_coordinator({'expected_generation': 1, 'request_key': 'lost-owner-0001'})
        self.assertFalse(self.dataset.db.runtime_owned('workspace_runs'))
        self.assertTrue(runs._stop.is_set())
        self.assertFalse(runs._thread.is_alive())

    def test_close_wins_while_recovery_waits_for_owned_thread(self):
        runs = self.dataset.runs
        released = threading.Event()
        runs._thread = threading.Thread(target=lambda: released.wait(5), daemon=True)
        runs._thread.start()
        runs._coordinator.fault('coordinator_exception')
        errors = []

        def recover():
            try:
                with self.owner.bound(self.dataset):
                    runs.recover_coordinator({'expected_generation': 1, 'request_key': 'close-race-0001'})
            except WorkbenchError as error:
                errors.append(error)

        recovery = threading.Thread(target=recover)
        recovery.start()
        self.wait_for(lambda: runs._coordinator.value['state'] == 'recovering', 'recovery never began joining')
        closer = threading.Thread(target=runs.close)
        closer.start()
        self.wait_for(lambda: runs._closed, 'close did not fence recovery')
        released.set()
        recovery.join(5); closer.join(5)
        self.assertFalse(recovery.is_alive()); self.assertFalse(closer.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertTrue(runs._stop.is_set())
        self.assertEqual(runs._coordinator.projection()['state'], 'stopped')
        self.assertFalse(runs._thread.is_alive())

    def test_failed_replacement_start_keeps_same_request_retryable(self):
        runs = self.dataset.runs
        self.lock_fault()
        body = {'expected_generation': 1, 'request_key': 'start-failure-0001'}
        with self.owner.bound(self.dataset), patch.object(runs, '_start', side_effect=RuntimeError('thread resource unavailable')):
            with self.assertRaises(RuntimeError):
                runs.recover_coordinator(body)
        self.assertIsNone(runs._coordinator.value['request']['completed_generation'])
        self.assertTrue(runs._stop.is_set())
        with self.owner.bound(self.dataset):
            recovered = runs.recover_coordinator(body)
        self.assertTrue(recovered['admission_ready'])
        self.assertTrue(runs._thread.is_alive())

    def test_actual_active_custodian_drains_before_recovery_without_second_go(self):
        import recipe_process
        from runs import process_status
        runs = self.dataset.runs
        graph = copy.deepcopy(self.graph)
        graph['nodes'][1]['parameters']['mode'] = 'sleep'
        with self.owner.bound(self.dataset):
            self.graph = self.dataset.pipelines.save(graph['id'], {'revision': graph['revision'], 'document': graph})
            self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
        run = self.queued(self.body(approval=self.approve()))
        go = recipe_process.Handle.go
        calls = []

        def counted_go(handle, helper):
            calls.append(handle)
            return go(handle, helper)

        with patch.object(recipe_process.Handle, 'go', counted_go):
            runs._start()
            def started():
                with self.owner.bound(self.dataset):
                    return runs.get(run['id'])['custody_phase'] == 'go_intent'
            self.wait_for(started, 'actual neutral helper did not reach GO')
            with self.dataset.lock:
                helper = runs._load(run['id'])['custody_identity']['helper']
                before = self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0]
            self.dataset.db.connection.execute("SET lock_timeout='150ms'")
            with psycopg.connect(connection_info(), autocommit=True) as other:
                other.execute('SELECT pg_advisory_lock(%s)', (self.dataset.db._lock_key,))
                runs._wake.set()
                self.wait_for(lambda: runs._coordinator.projection()['state'] == 'faulted', 'active coordinator did not fault')
                other.execute('SELECT pg_advisory_unlock(%s)', (self.dataset.db._lock_key,))
            runs._thread.join(10)
            self.assertFalse(runs._thread.is_alive())
            self.assertEqual(process_status(helper), 'ceased')
            with self.owner.bound(self.dataset), patch('recipe_process.launch', side_effect=AssertionError('recovery replayed compute')):
                recovered = runs.recover_coordinator({'expected_generation': 1, 'request_key': 'active-drain-0001'})
                current = runs.get(run['id'])
            self.assertTrue(recovered['admission_ready'])
            self.assertIn(current['state'], ('cancelled', 'interrupted'))
            self.assertTrue(runs._external_drain_receipt(runs._load(run['id'])))
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], before)

    def test_same_boot_missing_receipt_stays_unknown_and_fenced(self):
        import recipe_process
        from test_external_runs import sha
        runs = self.dataset.runs
        run = self.queued(self.body(approval=self.approve()))
        # Authored crash envelope, explicitly no claim that this PID ran. Same
        # boot and missing exact receipt must stay unknown even with no process.
        with self.owner.bound(self.dataset), self.dataset.lock, self.dataset.db.transaction():
            retained = runs._load(run['id'])
            retained.update(state='running', custody_phase='go_intent', custody_identity={
                'attempt_id': retained['id'], 'request_sha256': retained['request_sha256'],
                'spec_sha256': sha(recipe_process.encoded(retained['spec'])),
                'helper': {'pid': 2147483647, 'start_ticks': '1',
                           'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}})
            self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (json.dumps(retained), run['id']))
        runs._coordinator.fault('coordinator_exception')
        with self.owner.bound(self.dataset), patch('recipe_process.launch', side_effect=AssertionError('unknown replayed')):
            with self.assertRaises(WorkbenchError):
                runs.recover_coordinator({'expected_generation': 1, 'request_key': 'missing-receipt-0001'})
            self.assertEqual(runs.get(run['id'])['state'], 'unknown')
        self.assertTrue(runs._external_blocked)
        self.assertTrue(runs._stop.is_set())

    def test_preserved_queue_executes_once_after_headroom_returns(self):
        import recipe_process
        runs = self.dataset.runs
        run = self.queued(self.body(approval=self.approve()))
        self.lock_fault()
        with self.dataset.lock:
            request_sha = runs._load(run['id'])['request_sha256']
        go = recipe_process.Handle.go
        calls = []

        def counted(handle, helper):
            calls.append(handle)
            return go(handle, helper)

        headroom = [0]
        with patch.object(recipe_process.Handle, 'go', counted), \
                patch('run_capacity.available_memory', side_effect=lambda: headroom[0]):
            with self.owner.bound(self.dataset):
                runs.recover_coordinator({'expected_generation': 1, 'request_key': 'pending-first-go-0001'})
            # Resource availability is controlled; original capacity budgets and
            # the neutral custodian/GO/process/receipt path remain real.
            headroom[0] = 64 * 1024**3
            runs._wake.set()
            completed = self.await_state(run['id'], ('completed',))
        self.assertEqual(completed['request_key'], run['request_key'])
        self.assertEqual(runs._load(run['id'])['request_sha256'], request_sha)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 1)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)

    def test_unknown_reconciliation_commit_ack_remains_fenced_until_explicit_same_key(self):
        runs = self.dataset.runs
        self.lock_fault()
        transaction = self.dataset.db.transaction
        lost = []

        @contextmanager
        def lose_ack(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            if not lost:
                lost.append(True)
                raise CommitOutcomeUnknown('Injected unknown reconciliation acknowledgement.')

        body = {'expected_generation': 1, 'request_key': 'unknown-reconcile-0001'}
        with self.owner.bound(self.dataset), patch.object(self.dataset.db, 'transaction', side_effect=lose_ack), \
                patch.object(runs, '_start') as start:
            with self.assertRaises(WorkbenchError) as unknown:
                runs.recover_coordinator(body)
            self.assertEqual(unknown.exception.code, 'commit_unknown')
            start.assert_not_called()
        self.assertTrue(runs._stop.is_set())
        self.assertIsNone(runs._coordinator.value['request']['completed_generation'])
        with self.owner.bound(self.dataset):
            self.assertTrue(runs.recover_coordinator(body)['admission_ready'])

    def test_fault_after_go_intent_commit_does_not_send_go(self):
        import recipe_process
        runs = self.dataset.runs
        run = self.queued(self.body(approval=self.approve()))
        transaction = self.dataset.db.transaction
        faulted = []

        @contextmanager
        def fault_at_go(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            retained = runs._load(run['id'])
            if retained['custody_phase'] == 'go_intent' and not faulted:
                faulted.append(True)
                runs._coordinator.fault('coordinator_exception')

        with patch.object(self.dataset.db, 'transaction', side_effect=fault_at_go), \
                patch.object(recipe_process.Handle, 'go') as go:
            runs._start()
            self.wait_for(lambda: bool(faulted), 'real helper did not reach durable GO seam')
            runs._thread.join(10)
            self.assertFalse(runs._thread.is_alive())
            go.assert_not_called()
        with self.owner.bound(self.dataset):
            current = runs.get(run['id'])
            self.assertIn(current['state'], ('cancelled', 'interrupted'))
            self.assertTrue(runs._external_drain_receipt(runs._load(run['id'])))
            self.assertTrue(runs.recover_coordinator({'expected_generation': 1, 'request_key': 'go-seam-0001'})['admission_ready'])
        self.assertFalse(Path(runs._load(run['id'])['spec']['output_dir'], 'result.txt').exists())

    def test_remaining_sql_budget_cancels_real_query_and_restores_session_timeout(self):
        database = self.dataset.db
        before = database.connection.execute('SHOW statement_timeout').fetchone()[0]
        started = time.monotonic()
        with database.lock:
            with self.assertRaises(psycopg.errors.QueryCanceled), database.commands_before(started + .2):
                database.execute('SELECT pg_sleep(5)')
        self.assertLess(time.monotonic()-started, 1)
        self.assertEqual(database.connection.execute('SHOW statement_timeout').fetchone()[0], before)

    def test_catalog_mutex_wait_is_cancelled_by_actual_close(self):
        runs = self.dataset.runs
        errors = []

        def pending():
            try:
                with runs._coordinator.catalog(time.monotonic()+60):
                    self.fail('Closed recovery acquired catalog readiness')
            except WorkbenchError as error:
                errors.append(error)

        with self.dataset.lock:
            waiting = threading.Thread(target=pending)
            waiting.start()
            closer = threading.Thread(target=runs.close)
            closer.start()
            self.wait_for(lambda: runs._closed, 'actual close did not win')
            waiting.join(2)
            self.assertFalse(waiting.is_alive())
            self.assertEqual(len(errors), 1)
        closer.join(5)
        self.assertFalse(closer.is_alive())

    def test_cold_reopen_retains_fault_and_exact_recovery_receipt_without_replaying(self):
        runs = self.dataset.runs
        self.lock_fault()
        with self.owner.bound(self.dataset):
            recovered = runs.recover_coordinator({'expected_generation': 1, 'request_key': 'cold-recovery-0001'})
        self.reopen()
        with self.owner.bound(self.dataset):
            reopened = self.dataset.runs.coordinator_health()
        self.assertEqual(reopened['generation'], recovered['generation'] + 1)
        self.assertEqual(reopened['fault'], recovered['fault'])
        self.assertEqual(reopened['recovery_request'], recovered['recovery_request'])
        self.assertIsNone(self.dataset.runs._thread)

    def test_corrupt_journal_is_retained_and_recovery_fails_closed(self):
        self.dataset.close()
        journal = self.path / 'catalog' / 'workspace-runs' / '.coordinator-v1.json'
        original = b'{"format":"run_coordinator_v1","catalog_id":"changed"}'
        journal.write_bytes(original)
        self.reopen()
        with self.owner.bound(self.dataset):
            health = self.dataset.runs.coordinator_health()
            self.assertFalse(health['admission_ready'])
            self.assertEqual(health['fault']['category'], 'journal_unavailable')
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.recover_coordinator({'expected_generation': 1, 'request_key': 'invalid-journal-0001'})
        self.assertEqual(journal.read_bytes(), original)
        self.assertIsNone(self.dataset.runs._thread)

    def test_ordinary_catalog_mutex_wait_has_a_typed_finite_bound(self):
        from metadata import CatalogBusy
        errors = []
        def wait():
            try:
                with self.dataset.lock:
                    self.fail('Competing thread entered the owned catalog')
            except CatalogBusy as error:
                errors.append(error)
        with self.dataset.lock, patch('metadata.CATALOG_LOCAL_TIMEOUT', .15):
            worker = threading.Thread(target=wait)
            worker.start(); worker.join(1)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)

    def test_secondary_opener_cannot_replace_primary_journal_on_recovery_or_close(self):
        from app import Dataset
        primary = self.dataset.runs
        primary._coordinator.fault('coordinator_exception')
        with self.owner.bound(self.dataset):
            primary.recover_coordinator({'expected_generation': 1, 'request_key': 'primary-owner-0001'})
        journal = primary.path / '.coordinator-v1.json'
        original = journal.read_bytes()
        peer = Dataset(self.path / 'catalog', project_roots={'fixture': self.project_path})
        try:
            self.assertFalse(peer.runs.runtime_owner)
            with self.owner.bound(peer), self.assertRaises(WorkbenchError):
                peer.runs.recover_coordinator({'expected_generation': 1, 'request_key': 'peer-refusal-0001'})
            self.assertEqual(journal.read_bytes(), original)
        finally:
            peer.close()
        self.assertEqual(journal.read_bytes(), original)
        self.assertEqual(primary._coordinator.value['fault']['category'], 'coordinator_exception')

    def test_unknown_commit_survives_timeout_restore_failure_and_retains_fence(self):
        runs = self.dataset.runs
        self.lock_fault()
        original_transaction = self.dataset.db.transaction
        connection = self.dataset.db.connection
        lost, cleanup_failed = [], []

        @contextmanager
        def unknown(*args, **kwargs):
            with original_transaction(*args, **kwargs):
                yield
            if not lost:
                lost.append(True)
                raise CommitOutcomeUnknown('Injected unknown COMMIT followed by cleanup failure.')

        class RestoreFailure:
            def __getattr__(self, name):
                return getattr(connection, name)

            def execute(self, statement, parameters=None):
                if lost and not cleanup_failed and 'set_config' in str(statement) and parameters == ('1min',):
                    cleanup_failed.append(True)
                    raise psycopg.OperationalError('Injected timeout restoration failure.')
                return connection.execute(statement, parameters)

        with self.owner.bound(self.dataset), patch.object(self.dataset.db, 'connection', RestoreFailure()), \
                patch.object(self.dataset.db, 'transaction', side_effect=unknown), patch.object(runs, '_start') as start:
            with self.assertRaises(WorkbenchError) as error:
                runs.recover_coordinator({'expected_generation': 1, 'request_key': 'double-fault-0001'})
            self.assertEqual(error.exception.code, 'commit_unknown')
            start.assert_not_called()
        self.assertTrue(lost)
        self.assertTrue(cleanup_failed)
        self.assertTrue(runs._stop.is_set())
        self.assertIsNone(runs._coordinator.value['request']['completed_generation'])
