"""Owner-observed diagnostics only; neutral process fixtures make no science claim."""
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

import agent_api
import phase_timings
from recipe_process import PhaseTimings, PHASE_MAX_MS
from workbench import WorkbenchError


class OwnerPhaseTimingTests(unittest.TestCase):
    def clock(self):
        self.tick = 0
        self.wall = 1000000000
        return PhaseTimings('runs', clock=lambda: self.tick, wall=lambda: self.wall)

    def advance(self, milliseconds):
        self.tick += milliseconds*1000000

    def envelope(self, record):
        return {'status': 200, 'result': {'format': 'run_phase_timings_v1', 'catalog_id': 'a'*32,
            'run_id': 'b'*32, 'original_run_state': 'running', 'evidence': 'owner_observed', 'records': [record]}}

    def test_overlapping_owner_spans_use_monotonic_time_and_are_not_added(self):
        clock = self.clock()
        first = clock.begin('queue', 'scheduler'); self.advance(30)
        second = clock.begin('launch_verification', 'verifying_captures'); self.advance(20)
        self.wall = 1  # UTC adjustment cannot shorten either owner interval.
        clock.finish(first); self.advance(10); clock.finish(second)
        value = clock.snapshot(); phase_timings.validate_record(value)
        self.assertEqual([item['elapsed_ms'] for item in value['spans']], [50, 30])
        self.assertEqual([item['started_offset_ms'] for item in value['spans']], [0, 30])
        self.assertEqual([item['ended_offset_ms'] for item in value['spans']], [50, 60])
        self.assertEqual(value['observed_at_ms'], 0)
        agent_api.validate_output('runs.phase_timings', self.envelope(value))

    def test_open_snapshot_cold_reopen_and_failed_phase_never_invent_an_end(self):
        clock = self.clock(); clock.begin('queue', 'scheduler'); self.advance(17)
        live = clock.snapshot(); cold = phase_timings.incomplete(live)
        self.advance(1000)
        self.assertEqual(cold['spans'][0], dict(live['spans'][0], state='incomplete', wait_reason=None))
        self.assertIsNone(cold['spans'][0]['ended_offset_ms'])
        with self.assertRaisesRegex(OSError, 'authored'):
            with phase_timings.observe(clock, 'publication', 'copying_outputs'):
                self.advance(7); raise OSError('authored copy fault')
        failed = clock.snapshot()['spans'][-1]
        self.assertEqual((failed['state'], failed['elapsed_ms'], failed['ended_offset_ms']), ('incomplete', 7, None))

    def test_history_and_long_lived_open_span_are_bounded_without_false_duration(self):
        clock = self.clock()
        for _ in range(80):
            clock.finish(clock.begin('publication'))
        value = clock.snapshot()
        self.assertEqual((len(value['spans']), value['dropped_spans']), (32, 48))
        span = clock.begin('queue', 'scheduler'); self.advance(PHASE_MAX_MS + 1); clock.finish(span)
        self.assertEqual(clock.snapshot()['spans'][-1]['state'], 'incomplete')
        self.assertIsNone(clock.snapshot()['spans'][-1]['ended_offset_ms'])
        book = phase_timings.Book()
        for number in range(100): book.start(number, 'pipeline')
        self.assertIsNone(book.get(0)); self.assertIsNotNone(book.get(99))
        self.assertEqual(len(book._records), 64)

    def test_all_open_span_cap_reports_each_missing_observation_without_closing_owners(self):
        clock = self.clock()
        sequences = [clock.begin('queue', 'scheduler') for _ in range(32)]
        self.assertIsNone(clock.begin('publication'))
        self.assertIsNone(clock.begin('output_validation'))
        value = phase_timings.validate_record(clock.snapshot())
        self.assertEqual((len(value['spans']), value['dropped_spans']), (32, 2))
        self.assertTrue(all(item['state'] == 'open' for item in value['spans']))
        clock.finish(sequences[0]); kept = clock.begin('publication')
        self.assertIsNotNone(kept)
        self.assertEqual(clock.snapshot()['dropped_spans'], 3)
        agent_api.validate_output('runs.phase_timings', self.envelope(clock.snapshot()))

    def test_closed_wire_refuses_duplicate_clocks_forged_durations_and_waits(self):
        clock = self.clock(); span = clock.begin('queue', 'scheduler'); self.advance(3); clock.finish(span)
        good = self.envelope(clock.snapshot())
        for mutate in (lambda value: value['result']['records'].append(copy.deepcopy(value['result']['records'][0])),
                       lambda value: value['result']['records'][0]['spans'][0].update(elapsed_ms=4),
                       lambda value: value['result']['records'][0].update(owner='custodian'),
                       lambda value: value['result']['records'][0]['spans'][0].update(wait_reason='scheduler'),
                       lambda value: value['result'].update(ready=True),
                       lambda value: value['result'].update(evidence='unknown_granularity')):
            bad = copy.deepcopy(good); mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_output('runs.phase_timings', bad)

    def test_client_correlates_exact_run_catalog_graph_revision_and_never_retries(self):
        client = agent_api.AgentClient('http://127.0.0.1:12345', 'x'*32, 'a'*32)
        client._ready = True
        client._selected = {name: 1 for name in ('runs.phase_timings', 'graphs.preparation_timings')}
        run = self.envelope(self.clock().snapshot())
        graph = {'status': 200, 'result': {'format': 'graph_preparation_timings_v1', 'catalog_id': 'a'*32,
            'actor_id': 'c'*32, 'graph_id': 'd'*32, 'graph_revision': 2,
            'selection': 'latest_actor_graph_revision_observation', 'observation': None,
            'evidence': 'unknown_granularity', 'records': []}}
        for operation, arguments, good, field, foreign in (
                ('runs.phase_timings', {'run_id': 'b'*32}, run, 'run_id', 'f'*32),
                ('runs.phase_timings', {'run_id': 'b'*32}, run, 'catalog_id', 'f'*32),
                ('graphs.preparation_timings', {'graph_id': 'd'*32, 'revision': 2}, graph, 'graph_id', 'f'*32),
                ('graphs.preparation_timings', {'graph_id': 'd'*32, 'revision': 2}, graph, 'graph_revision', 3)):
            bad = copy.deepcopy(good); bad['result'][field] = foreign
            client._request = Mock(return_value=bad)
            with self.subTest(operation=operation, field=field), self.assertRaisesRegex(agent_api.AgentAPIError, 'differs from its requested identity'):
                client.call(operation, arguments)
            self.assertEqual(client._request.call_count, 1)

    def test_full_baseline_contracts_and_legacy_discovery_are_identical(self):
        previous = json.loads((Path(__file__).with_name('fixtures') /
            'agent_contract_hashes_phase5a1feac.json').read_text())
        count = 0
        for name, versions in previous['contracts'].items():
            for version, expected in versions.items():
                self.assertEqual(hashlib.sha256(agent_api.encoded(agent_api.contract(name, int(version)))).hexdigest(),
                                 expected, (name, version))
                count += 1
        self.assertEqual(hashlib.sha256(agent_api.encoded(agent_api.discovery())).hexdigest(),
                         previous['legacy_discovery_sha256'])
        self.assertEqual(count, previous['count'])
        self.assertEqual(count, 120)



@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ActualPhaseTimingTests(unittest.TestCase):
    def fixture(self):
        from test_external_runs import ExternalExecutionTests
        case = ExternalExecutionTests('runTest'); self.addCleanup(case.doCleanups); case.setUp()
        return case

    def test_pre_run_preparation_is_live_actor_revision_scoped_and_has_no_run_effect(self):
        case = self.fixture(); dataset = case.dataset
        entered = threading.Event(); release = threading.Event(); failures = []
        import recipe_contract
        original = recipe_contract.prepare
        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(10): raise AssertionError('preparation witness timed out')
            return original(*args, **kwargs)
        def prepare():
            try:
                with case.owner.bound(dataset): dataset.pipelines.preflight_external(case.graph['id'], 1)
            except BaseException as error: failures.append(error)
        self.addCleanup(release.set)
        with patch('recipe_contract.prepare', side_effect=blocked):
            worker = threading.Thread(target=prepare); worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with case.owner.bound(dataset):
                    value = dataset.pipelines.preparation_timings(case.graph['id'], 1)
                    self.assertEqual(value['evidence'], 'owner_observed')
                    self.assertEqual(value['observation']['operation'], 'graphs.preflight_external')
                    self.assertIsNone(value['observation']['material_sha256'])
                    self.assertEqual(value['observation']['clock_id'], value['records'][0]['clock_id'])
                    self.assertEqual(value['records'][0]['spans'][0]['state'], 'open')
                    self.assertEqual(value['records'][0]['spans'][0]['wait_reason'], 'preparing_material')
                    self.assertEqual(dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 0)
                    with self.assertRaises(WorkbenchError): dataset.pipelines.preparation_timings(case.graph['id'], 2)
                with dataset.access.bind(case.other['token']):
                    self.assertEqual(dataset.pipelines.preparation_timings(case.graph['id'], 1)['evidence'], 'unknown_granularity')
            finally:
                release.set(); worker.join(10)
            self.assertFalse(worker.is_alive()); self.assertEqual(failures, [])
        with case.owner.bound(dataset):
            measured = dataset.pipelines.preparation_timings(case.graph['id'], 1)
        self.assertEqual(measured['records'][0]['spans'][0]['state'], 'measured')
        self.assertEqual(measured['observation']['material_sha256'], case.preflight['material_sha256'])
        agent_api.validate_output('graphs.preparation_timings', {'status': 200, 'result': measured})

    def test_actual_queue_copy_fault_recovery_and_cold_read_preserve_original_authority(self):
        case = self.fixture(); runs = case.dataset.runs
        queued = case.queued(case.body(approval=case.approve()))
        with case.owner.bound(case.dataset):
            before = runs.phase_timings(queued['id'])
            public_before = runs.get(queued['id'])
        self.assertNotIn('_phase_timings', public_before)
        self.assertTrue(any(span['phase'] == 'capture' and span['state'] == 'measured'
            for record in before['records'] for span in record['spans']))
        self.assertTrue(any(span['phase'] == 'queue' and span['state'] == 'open'
            for record in before['records'] for span in record['spans']))
        saved = runs._load(queued['id'])
        with patch.object(runs, '_copy_verified', side_effect=OSError('authored timing publication fault')):
            runs._run_attempt(saved, (runs._capacity.cores[0],), runs._capacity.claim(saved))
        with case.owner.bound(case.dataset):
            failed = runs.phase_timings(queued['id']); run = runs._load(queued['id'])
        spans = [span for record in failed['records'] for span in record['spans']]
        for phase in ('queue', 'launch_verification', 'custodian_preparation', 'go_wait',
                      'runtime_verification', 'leader_lifetime', 'drain', 'output_validation'):
            self.assertTrue(any(span['phase'] == phase and span['state'] == 'measured' for span in spans), phase)
        self.assertTrue(any(span['phase'] == 'publication' and span['state'] == 'incomplete' for span in spans))
        self.assertIn(run['state'], ('failed', 'interrupted'))
        original = copy.deepcopy(run)
        counts = {table: case.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                  for table in ('workspace_runs', 'access_execution_grants', 'access_execution_consumptions', 'model_attempt_reservations')}
        with case.owner.bound(case.dataset), patch('recipe_process.launch', side_effect=AssertionError('Timing recovery replayed compute')):
            recovered = runs.recover_publication({'run_id': run['id'], 'source_ref': run['publication_source'],
                'request_key': 'timing-recovery-stable-request'})
            self.assertEqual(recovered['state'], 'published')
            timed = runs.phase_timings(run['id'])
            self.assertEqual(timed['original_run_state'], original['state'])
            for phase in ('recovery_verification', 'recovery_publication'):
                self.assertTrue(any(span['phase'] == phase and span['state'] == 'measured'
                    for record in timed['records'] for span in record['spans']), phase)
            after = runs._load(run['id'])
            self.assertEqual((after['state'], after['events']), (original['state'], original['events']))
            self.assertEqual(counts, {table: case.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in counts})
        case.reopen()
        with case.owner.bound(case.dataset):
            cold = case.dataset.runs.phase_timings(run['id'])
            self.assertFalse(any(span['state'] == 'open' for record in cold['records'] for span in record['spans']))
            agent_api.validate_output('runs.phase_timings', {'status': 200, 'result': cold})
            self.assertEqual(case.dataset.runs.get(run['id'])['state'], original['state'])
            with self.assertRaises(WorkbenchError): case.dataset.runs.artifact(run['id'], 'result.txt')

    def test_selected_http_cli_old_run_unknown_and_bounded_catalog_wait(self):
        case = self.fixture(); dataset = case.dataset
        run = case.queued(case.body(approval=case.approve()))
        # An old document carries coarse UTC labels only. Never manufacture spans.
        with dataset.lock, dataset.db.transaction():
            old = dataset.runs._load(run['id']); old.pop('_phase_timings', None)
            dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (json.dumps(old), run['id']))
        dataset.runs._phase_book = phase_timings.Book()
        from app import make_handler
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        endpoint = 'http://127.0.0.1:'+str(server.server_port)
        try:
            client = agent_api.AgentClient(endpoint, case.agent['token'], dataset.db.dataset_id)
            result = client.call('runs.phase_timings', {'run_id': run['id']})
            self.assertEqual(result['status'], 200, result)
            self.assertEqual(result['result']['evidence'], 'unknown_granularity')
            self.assertEqual(result['result']['records'], [])
            preparation = client.call('graphs.preparation_timings', {'graph_id': case.graph['id'], 'revision': 1})
            self.assertEqual(preparation['status'], 200, preparation)
            self.assertEqual(preparation['result']['selection'], 'latest_actor_graph_revision_observation')
            # queued() actually captured under this agent before admission.
            self.assertEqual(preparation['result']['actor_id'], case.agent['identity']['actor_id'])
            self.assertEqual(preparation['result']['observation']['operation'], 'graphs.capture_external')
            self.assertEqual(preparation['result']['observation']['material_sha256'], run['material_sha256'])
            self.assertEqual(preparation['result']['observation']['clock_id'], preparation['result']['records'][0]['clock_id'])
            from urllib.request import Request, urlopen
            from urllib.error import HTTPError
            with self.assertRaises(HTTPError) as missing_selection:
                urlopen(Request(endpoint+'/api/workspace/runs/'+run['id']+'/phase-timings',
                    headers={'Authorization': 'Bearer '+case.agent['token']}), timeout=15)
            self.assertEqual(missing_selection.exception.code, 409)
            missing_selection.exception.close()
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                config = Path(directory)/'agent.json'
                token = Path(directory)/'token'; token.write_text(case.agent['token']); token.chmod(0o600)
                config.write_text(json.dumps({'endpoint': endpoint,
                    'catalog_id': dataset.db.dataset_id, 'token_file': str(token)})); config.chmod(0o600)
                called = subprocess.run([sys.executable, 'project_cli.py', '--config', str(config),
                    'phase-timings', '--run-id', run['id']], capture_output=True, text=True, timeout=90)
                self.assertEqual(called.returncode, 0, called.stderr+called.stdout)
                self.assertEqual(json.loads(called.stdout)['records'], [])
            import psycopg
            from metadata import connection_info
            with case.owner.bound(dataset), psycopg.connect(connection_info(), autocommit=True) as peer:
                peer.execute('SELECT pg_advisory_lock(%s)', (dataset.db._lock_key,))
                try:
                    started = time.monotonic()
                    with self.assertRaises(WorkbenchError) as caught: dataset.runs.phase_timings(run['id'])
                    self.assertLess(time.monotonic()-started, 2)
                    self.assertEqual(caught.exception.code, 'unavailable')
                finally:
                    peer.execute('SELECT pg_advisory_unlock(%s)', (dataset.db._lock_key,))
        finally:
            server.shutdown(); server.server_close(); worker.join(5)

    def test_real_capacity_wait_single_go_and_active_cancel_keep_observations_separate(self):
        import recipe_process
        case = self.fixture(); runs = case.dataset.runs
        graph = copy.deepcopy(case.graph); graph['nodes'][1]['parameters']['mode'] = 'sleep'
        with case.owner.bound(case.dataset):
            case.graph = case.dataset.pipelines.save(graph['id'], {'revision': graph['revision'], 'document': graph})
            case.preflight = case.dataset.pipelines.preflight_external(case.graph['id'], case.graph['revision'])
        queued = case.queued(case.body(approval=case.approve()))
        go = recipe_process.Handle.go; calls = []; headroom = [0]
        def counted(handle, helper):
            calls.append(handle); return go(handle, helper)
        def wait_for(predicate):
            deadline = time.monotonic()+12
            while time.monotonic() < deadline:
                with case.owner.bound(case.dataset): value = runs.phase_timings(queued['id'])
                if predicate(value): return value
                time.sleep(.03)
            self.fail('actual phase observation did not arrive')
        with patch('run_capacity.available_memory', side_effect=lambda: headroom[0]), patch.object(recipe_process.Handle, 'go', counted):
            runs._start()
            waiting = wait_for(lambda value: any(span['wait_reason'] == 'capacity'
                for record in value['records'] for span in record['spans']))
            self.assertEqual(waiting['original_run_state'], 'queued'); self.assertEqual(calls, [])
            headroom[0] = 64*1024**3; runs._wake.set()
            live = wait_for(lambda value: any(record['owner'] == 'custodian' and span['phase'] == 'leader_lifetime'
                and span['state'] == 'open' for record in value['records'] for span in record['spans']))
            self.assertEqual(live['original_run_state'], 'running')
            with case.owner.bound(case.dataset): runs.cancel(queued['id'])
            terminal = case.await_state(queued['id'], {'cancelled', 'unknown', 'failed'})
        self.assertEqual(terminal['state'], 'cancelled'); self.assertEqual(len(calls), 1)
        with case.owner.bound(case.dataset):
            final = runs.phase_timings(queued['id'])
            self.assertFalse(any(span['state'] == 'open' for record in final['records'] for span in record['spans']))
            self.assertTrue(any(span['phase'] == 'drain' and span['state'] == 'measured'
                for record in final['records'] for span in record['spans']))
            self.assertEqual(case.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 1)
            self.assertEqual(case.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)
            agent_api.validate_output('runs.phase_timings', {'status': 200, 'result': final})

    def test_actual_catalog_mutex_wait_is_measured_by_owner_without_reconstructing_events(self):
        case = self.fixture(); runs = case.dataset.runs
        run = case.queued(case.body(approval=case.approve()))
        ready = threading.Event(); proceed = threading.Event(); done = threading.Event(); failures = []
        begin = PhaseTimings.begin
        def gated(clock, phase, reason=None):
            token = begin(clock, phase, reason)
            if phase == 'catalog_lock_wait':
                ready.set()
                if not proceed.wait(5): raise AssertionError('wait witness gate timed out')
            return token
        def acquire():
            try:
                with runs._phase_catalog(run['id']): pass
            except BaseException as error: failures.append(error)
            finally: done.set()
        with patch.object(PhaseTimings, 'begin', gated):
            worker = threading.Thread(target=acquire); worker.start()
            try:
                self.assertTrue(ready.wait(5))
                # The real catalog mutex is held by another thread. No SQL,
                # wall-duration patch, event timestamp, or fabricated result.
                with case.dataset.lock:
                    proceed.set()
                    self.assertFalse(done.wait(.12))
            finally:
                proceed.set(); worker.join(5)
        self.assertFalse(worker.is_alive()); self.assertEqual(failures, [])
        with case.owner.bound(case.dataset): value = runs.phase_timings(run['id'])
        wait = [span for record in value['records'] for span in record['spans'] if span['phase'] == 'catalog_lock_wait']
        self.assertEqual(len(wait), 1); self.assertEqual(wait[0]['state'], 'measured')
        self.assertGreaterEqual(wait[0]['elapsed_ms'], 100)

    def test_missing_or_foreign_custodian_diagnostics_cannot_change_completed_result(self):
        case = self.fixture(); runs = case.dataset.runs
        run = case.queued(case.body(approval=case.approve()))
        saved = runs._load(run['id'])
        runs._run_attempt(saved, (runs._capacity.cores[0],), runs._capacity.claim(saved))
        with case.owner.bound(case.dataset):
            completed = runs.get(run['id']); self.assertEqual(completed['state'], 'completed')
            sidecar = runs._external_directory(saved)/'custody'/'phase-timings-v1.json'
            actual = sidecar.read_bytes(); forged = json.loads(actual)
            forged['spec_sha256'] = 'f'*64
            for raw in (json.dumps(forged).encode(), b'{malformed'):
                sidecar.write_bytes(raw)
                observed = runs.phase_timings(run['id'])
                self.assertEqual(observed['evidence'], 'partial')
                self.assertEqual(runs.get(run['id']), completed)
                self.assertEqual(runs.artifact(run['id'], 'result.txt')[0], case.input)
                agent_api.validate_output('runs.phase_timings', {'status': 200, 'result': observed})
            sidecar.unlink()
            self.assertEqual(runs.phase_timings(run['id'])['evidence'], 'partial')
            self.assertEqual(runs.get(run['id']), completed)
            self.assertEqual(runs.artifact(run['id'], 'result.txt')[0], case.input)

    def test_overlapping_same_actor_preparations_expose_latest_clock_without_rebinding_old_reply(self):
        import recipe_contract
        case = self.fixture(); dataset = case.dataset
        entered = threading.Event(); release = threading.Event(); failures = []; replies = []
        original = recipe_contract.prepare
        first_thread = threading.current_thread()
        def blocked(*args, **kwargs):
            if threading.current_thread() is not first_thread:
                entered.set()
                if not release.wait(10): raise AssertionError('old preparation release timed out')
            return original(*args, **kwargs)
        def old_request():
            try:
                with case.owner.bound(dataset): replies.append(dataset.pipelines.preflight_external(case.graph['id'], 1))
            except BaseException as error: failures.append(error)
        with patch('recipe_contract.prepare', side_effect=blocked):
            worker = threading.Thread(target=old_request); worker.start()
            try:
                self.assertTrue(entered.wait(5))
                with case.owner.bound(dataset):
                    older = dataset.pipelines.preparation_timings(case.graph['id'], 1)
                    fresh_reply = dataset.pipelines.preflight_external(case.graph['id'], 1)
                    latest = dataset.pipelines.preparation_timings(case.graph['id'], 1)
                self.assertNotEqual(older['observation']['clock_id'], latest['observation']['clock_id'])
                self.assertEqual(latest['observation']['material_sha256'], fresh_reply['material_sha256'])
                self.assertEqual(latest['selection'], 'latest_actor_graph_revision_observation')
            finally:
                release.set(); worker.join(10)
        self.assertFalse(worker.is_alive()); self.assertEqual(failures, []); self.assertEqual(len(replies), 1)
        with case.owner.bound(dataset): after = dataset.pipelines.preparation_timings(case.graph['id'], 1)
        self.assertEqual(after['observation'], latest['observation'])
        self.assertEqual(after['records'][0]['clock_id'], latest['records'][0]['clock_id'])
        self.assertNotIn('observation', fresh_reply); self.assertNotIn('observation', replies[0])
        agent_api.validate_output('graphs.preparation_timings', {'status': 200, 'result': after})
        for mutate in (lambda value: value['observation'].update(clock_id=older['observation']['clock_id']),
                       lambda value: value['observation'].update(operation='graphs.capture_external'),
                       lambda value: value.update(observation=None)):
            bad = copy.deepcopy(after); mutate(bad)
            with self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_output('graphs.preparation_timings', {'status': 200, 'result': bad})
