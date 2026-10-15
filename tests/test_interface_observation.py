"""V2 real interface seams over authored owners, not model workflow acceptance."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from http.server import ThreadingHTTPServer
import http.client
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import agent_api
from app import make_handler
import mcp_observer as obs
import project_cli
import test_mcp_observer as legacy
from test_agent_api import TOKEN, CATALOG

ROOT = Path(__file__).resolve().parents[1]


class AuthoredAccess:
    """Only authorization/data ownership is substituted; HTTP/CLI/client are real."""
    def bind(self, token):
        return nullcontext()

    def require(self, *_args):
        pass

    def denial(self, *_args, **_kwargs):
        pass

    def identity(self):
        return {'kind': 'agent', 'catalog_id': CATALOG, 'actor_id': CATALOG,
                'scopes': ['inspect', 'edit']}


@contextmanager
def http_boundary(observer=None, handler=None):
    dataset = SimpleNamespace(access=AuthoredAccess(), db=SimpleNamespace(dataset_id=CATALOG))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler or make_handler(dataset, observer))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


class InterfaceStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.database = self.directory / 'v2.sqlite'

    def recorder(self, boundary='http', database=None, diagnostics=None, **policy):
        recorder = obs.InterfaceRecorder(obs.RecorderConfig(database or self.database, **policy),
            agent_api.discovery(), boundary=boundary,
            diagnostics=io.StringIO() if diagnostics is None else diagnostics)
        self.addCleanup(recorder.close)
        return recorder

    def rows(self, sql):
        with sqlite3.connect(self.database) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql)]

    def check(self):
        return obs.check_store(self.database, schema_version=2)

    def test_v1_and_foreign_stores_are_preserved_and_reader_requires_exact_version(self):
        old = obs.InteractionRecorder(obs.RecorderConfig(self.database), agent_api.discovery(), diagnostics=io.StringIO())
        old.close()
        before = self.database.read_bytes()
        refused = self.recorder()
        self.assertEqual(refused.health['reason'], 'unsupported-database-schema')
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(obs.check_store(self.database)['schema_version'], 1)
        with self.assertRaises(obs.StorageRejected):
            self.check()
        fresh = self.recorder(database=self.directory / 'fresh.sqlite')
        self.assertEqual(fresh.health['state'], 'healthy')
        self.assertEqual((self.directory / 'fresh.sqlite').stat().st_mode & 0o777, 0o600)
        with self.assertRaises(obs.StorageRejected):
            obs.check_store(self.directory / 'fresh.sqlite')

    def test_http_large_measured_byte_counts_preserve_existing_stream_bounds(self):
        recorder = self.recorder()
        event = recorder.begin_request('POST', 'data.import_image', {}, request_bytes=40 * 1024 * 1024)
        recorder.measure_request(event, 48 * 1024 * 1024)
        recorder.stage(event, 'terminal', response_bytes=64 * 1024 * 1024, delivery='written')
        self.assertEqual(self.rows('SELECT request_bytes FROM interactions')[0]['request_bytes'], 48 * 1024 * 1024)
        self.assertEqual(self.rows('SELECT response_bytes FROM events')[0]['response_bytes'], 64 * 1024 * 1024)

    def test_projection_contract_and_concurrent_requests_do_not_retain_material(self):
        recorder = self.recorder()
        def call(_):
            event = recorder.begin_request('POST', 'runs.submit_external',
                {'graph_id': 'PRIVATE_GRAPH', 'expected_digest': 'PRIVATE_MATERIAL',
                 'request_key': 'PRIVATE_REQUEST', 'annotation': {'PRIVATE_NESTED': 'PRIVATE_TEXT'},
                 'PRIVATE_UNKNOWN': 'PRIVATE_UNKNOWN_VALUE'}, selected_version=1)
            for phase in ('validated', 'admitted', 'dispatch', 'returned', 'terminal'):
                recorder.stage(event, phase, outcome='success', delivery='written' if phase == 'terminal' else 'pending')
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(call, range(20)))
        recorder.close()
        self.assertEqual(self.check()['retained_terminals'], 20)
        self.assertNotIn(b'PRIVATE_', self.database.read_bytes())
        self.assertEqual({row['boundary'] for row in self.rows('SELECT boundary FROM sessions')}, {'http'})
        rows = self.rows('SELECT * FROM interactions')
        self.assertTrue(all(row['contract_version'] == 1 and
                            row['contract_digest'] == agent_api.contract('runs.submit_external')['sha256'] for row in rows))
        shape = json.loads(rows[0]['input_shape'])
        self.assertEqual(shape['fields']['graph_id']['type'], 'string')
        self.assertEqual(shape['unknown_fields'], 2)

    def test_retention_shutdown_and_broken_health_channel(self):
        class BrokenHealth:
            def write(self, *_):
                raise OSError('PRIVATE_HEALTH')
        recorder = self.recorder(max_calls=16, diagnostics=BrokenHealth())
        for _ in range(20):
            event = recorder.begin_request('GET', 'context.get', {})
            recorder.stage(event, 'terminal', outcome='success', delivery='written')
        recorder.begin_request('GET', 'context.get', {})
        recorder.close()
        self.assertEqual(self.check()['retained_starts'], 16)
        self.assertEqual(self.check()['unfinished'], 0)
        self.assertEqual(recorder.health['pruned'], 5)
        self.assertEqual(self.rows("SELECT delivery FROM events WHERE outcome='unknown'")[0]['delivery'], 'incomplete')
        # A read is independent, read-only, and cannot reset policy or start collection.
        before = self.database.read_bytes()
        self.check()
        self.assertEqual(before, self.database.read_bytes())
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE interactions SET started=0 WHERE id=(SELECT id FROM interactions LIMIT 1)')
        self.assertEqual(self.check()['retained_starts'], 16)
        self.assertEqual(obs.check_store(self.database, retain=True, schema_version=2)['retained_starts'], 15)

    def modes(self, boundary):
        for mode in ('disabled', 'healthy', 'full', 'locked', 'unsafe', 'corrupt'):
            path = self.directory / (boundary + '-' + mode + '.sqlite')
            lock = None
            if mode == 'unsafe':
                path.write_bytes(b'PRIVATE_UNSAFE')
                path.chmod(0o644)
            elif mode == 'corrupt':
                path.write_bytes(b'PRIVATE_CORRUPT')
                path.chmod(0o600)
            if mode == 'locked':
                initialized = self.recorder(boundary, database=path)
                initialized.close()
                lock = sqlite3.connect(path, isolation_level=None)
                lock.execute('BEGIN IMMEDIATE')
            recorder = None if mode == 'disabled' else self.recorder(boundary, database=path)
            if mode == 'full':
                original_stage = recorder.stage
                def stage(event, phase, **values):
                    if phase == 'returned' and recorder._connection is not None:
                        db = recorder._connection
                        pages = db.execute('PRAGMA page_count').fetchone()[0]
                        db.execute(f'PRAGMA max_page_count={pages}')
                        recorder._transaction(lambda db: db.execute(
                            'UPDATE interactions SET input_shape=?', ('x' * (pages * 4096),)))
                    original_stage(event, phase, **values)
                recorder.stage = stage
            try:
                yield mode, recorder, path
            finally:
                if lock is not None:
                    lock.execute('ROLLBACK')
                    lock.close()
                if recorder is not None:
                    recorder.close()

    def test_actual_http_boundary_storage_failure_matrix_has_identical_results(self):
        results = []
        for mode, recorder, path in self.modes('http'):
            with http_boundary(recorder) as endpoint:
                client = agent_api.AgentClient(endpoint, TOKEN, CATALOG)
                results.append(client.call('context.get', {}))
            if mode == 'disabled':
                self.assertFalse(path.exists())
            elif mode == 'healthy':
                self.assertEqual(obs.check_store(path, schema_version=2)['unfinished'], 0)
                with sqlite3.connect(path) as db:
                    phases = [row[0] for row in db.execute('SELECT phase FROM events ORDER BY recorded')]
                    selected = db.execute("SELECT contract_version,contract_digest FROM interactions WHERE operation_id='context.get' AND contract_version IS NOT NULL").fetchone()
                self.assertIn('dispatch', phases)
                self.assertEqual(selected, (1, agent_api.contract('context.get')['sha256']))
            else:
                self.assertEqual(recorder.health['state'], 'degraded', mode)
                self.assertEqual(recorder.health['reason'], {'full':'storage-full', 'locked':'storage-locked',
                    'unsafe':'unsafe-storage', 'corrupt':'storage-corrupt'}[mode])
        self.assertTrue(all(result == results[0] for result in results))

    def test_actual_cli_with_real_client_storage_failure_matrix_has_identical_stdout(self):
        arguments = self.directory / 'args.json'
        arguments.write_text('{}')
        results = []
        with http_boundary() as endpoint:
            for mode, recorder, path in self.modes('cli'):
                client = agent_api.AgentClient(endpoint, TOKEN, CATALOG)
                output, errors = io.StringIO(), io.StringIO()
                with patch.object(project_cli.AgentClient, 'from_config', return_value=client), patch('sys.stdout', output), patch('sys.stderr', errors):
                    code = project_cli.main(['--config', 'PRIVATE_CONFIG', 'call',
                        '--operation', 'context.get', '--arguments', str(arguments)], observer=recorder)
                results.append((code, output.getvalue(), errors.getvalue()))
                if mode == 'healthy':
                    self.assertEqual(obs.check_store(path, schema_version=2)['unfinished'], 0)
                    with sqlite3.connect(path) as db:
                        self.assertEqual([row[0] for row in db.execute('SELECT phase FROM events ORDER BY recorded')],
                                         ['validated', 'admitted', 'dispatch', 'returned', 'terminal'])
                elif mode != 'disabled':
                    self.assertEqual(recorder.health['state'], 'degraded', mode)
                    self.assertEqual(recorder.health['reason'], {'full':'storage-full', 'locked':'storage-locked',
                        'unsafe':'unsafe-storage', 'corrupt':'storage-corrupt'}[mode])
        self.assertTrue(all(result == results[0] for result in results), results)
        self.assertEqual(results[0][0], 0)

    def test_http_actual_partial_socket_write_and_shutdown_record_unknown_delivery(self):
        recorder = self.recorder()
        dataset = SimpleNamespace(access=AuthoredAccess(), db=SimpleNamespace(dataset_id=CATALOG))
        parent = make_handler(dataset, recorder)
        class Handler(parent):
            def _get(self):
                # A real closed reader causes the actual socket loop to fail.
                self.reply(b'x' * (16 * 1024 * 1024), content_type='application/octet-stream')
        with http_boundary(recorder, Handler) as endpoint:
            port = int(endpoint.rsplit(':', 1)[1])
            with socket.create_connection(('127.0.0.1', port)) as connection:
                connection.sendall(b'GET / HTTP/1.0\r\nHost: localhost\r\n\r\n')
                connection.recv(4096)
                # TCP reset rather than a graceful read shutdown.
                import struct
                connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
            deadline = time.monotonic() + 5
            while not self.rows("SELECT * FROM events WHERE phase='terminal'"):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.01)
        terminal = self.rows("SELECT * FROM events WHERE phase='terminal'")[0]
        self.assertEqual((terminal['outcome'], terminal['delivery']), ('unknown', 'incomplete'))
        self.assertLess(terminal['response_bytes'], 16 * 1024 * 1024)
        self.assertEqual(self.rows("SELECT outcome FROM events WHERE phase='returned'")[0]['outcome'], 'success')

    def test_cli_operator_selection_and_actual_partial_pipe_delivery(self):
        arguments = self.directory / 'args.json'
        arguments.write_text('{}')
        token, config = self.directory / 'token', self.directory / 'config'
        token.write_text(TOKEN)
        token.chmod(0o600)
        dataset = SimpleNamespace(access=AuthoredAccess(), db=SimpleNamespace(dataset_id=CATALOG))
        parent = make_handler(dataset)
        class LargeContext(parent):
            def _get(self):
                if self.path == '/api/workspace/context':
                    return self.reply({'dataset_id': CATALOG, 'mode': 'real', 'payload': 'x' * (1024 * 1024)})
                return super()._get()
        with http_boundary(handler=LargeContext) as endpoint:
            config.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': CATALOG, 'token_file': str(token)}))
            config.chmod(0o600)
            command = [sys.executable, str(ROOT / 'project_cli.py'), '--config', str(config),
                '--observe-v2-database', str(self.database), 'call', '--operation', 'context.get',
                '--arguments', str(arguments)]
            process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.addCleanup(legacy.ObserverProcessTests.cleanup, self, process)
            # Read one actual pipe prefix then remove the reader while output is pending.
            prefix = os.read(process.stdout.fileno(), 1024)
            self.assertTrue(prefix)
            process.stdout.close()
            self.assertEqual(process.wait(timeout=15), 1)
            self.assertNotIn(TOKEN.encode(), process.stderr.read())
        self.assertEqual(self.check()['unfinished'], 0)
        terminal = self.rows("SELECT * FROM events WHERE phase='terminal'")[0]
        self.assertEqual((terminal['outcome'], terminal['delivery']), ('unknown', 'incomplete'))
        self.assertGreater(terminal['response_bytes'], 0)
        self.assertLess(terminal['response_bytes'], 1024 * 1024)

    def test_cli_actual_partial_os_write_and_broken_sink_preserve_invocation(self):
        recorder = self.recorder('cli')
        event = recorder.begin_request('call', 'context.get', {})
        writes = iter([3, BrokenPipeError()])
        def write(_fd, _raw):
            value = next(writes)
            if isinstance(value, BaseException):
                raise value
            return value
        with patch('project_cli.os.write', side_effect=write):
            self.assertFalse(project_cli._write_output(sys.stdout, {'result': 'PRIVATE_OUTPUT'}, recorder, event))
        terminal = self.rows("SELECT * FROM events WHERE phase='terminal'")[0]
        self.assertEqual((terminal['response_bytes'], terminal['delivery']), (3, 'incomplete'))
        self.assertNotIn(b'PRIVATE_OUTPUT', self.database.read_bytes())


from test_external_runs import ExternalCase


class DomainAuditObservationTests(ExternalCase):
    """Real Access/Runs transactions remain authoritative with passive recording."""
    recorder = InterfaceStoreTests.recorder
    modes = InterfaceStoreTests.modes

    def test_receipt_reconciliation_and_required_audit_rollback_are_independent(self):
        import psycopg
        self.directory = self.path
        self.database = self.path / 'passive.sqlite'
        approval = self.approve()
        body = self.body(key='observation-stable-request', approval=approval)
        results = []
        with patch.object(self.dataset.runs, '_start'):
            for mode, recorder, path in self.modes('http'):
                server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset, recorder))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    client = agent_api.AgentClient('http://127.0.0.1:' + str(server.server_port),
                        self.agent['token'], self.dataset.db.dataset_id)
                    results.append(client.call('runs.submit_external', body))
                    if mode == 'healthy':
                        stored = path.read_bytes()
                        for value in (self.dataset.db.dataset_id, self.agent['identity']['actor_id'],
                                      self.preflight['material_sha256'], approval['id'], body['request_key'],
                                      results[-1]['result']['id']):
                            self.assertNotIn(value.encode('ascii'), stored)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(5)
            self.assertTrue(all(value['status'] == 201 for value in results), results)
            self.assertEqual(len({value['result']['id'] for value in results}), 1)
            with self.owner.bound(self.dataset):
                self.assertEqual(len(self.dataset.runs.list()), 1)
            second = self.approve()
            second_body = self.body(key='observation-audit-failure', approval=second)
            recorder = self.recorder('http', database=self.path / 'audit-v2.sqlite')
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset, recorder))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = agent_api.AgentClient('http://127.0.0.1:' + str(server.server_port),
                    self.agent['token'], self.dataset.db.dataset_id)
                with patch.object(self.dataset.access, 'audit', side_effect=psycopg.OperationalError('PRIVATE_AUDIT')):
                    failed = client.call('runs.submit_external', second_body)
                self.assertEqual((failed['status'], failed['result']['code']), (503, 'storage'))
                with self.owner.bound(self.dataset):
                    self.assertEqual(len(self.dataset.runs.list()), 1)
                # The exact same one-use grant remains usable after the rolled-back audit.
                admitted = client.call('runs.submit_external', second_body)
                self.assertEqual(admitted['status'], 201, admitted)
                self.assertNotEqual(admitted['result']['id'], results[0]['result']['id'])
                cli_store = self.path / 'receipt-cli-v2.sqlite'
                cli_recorder = self.recorder('cli', database=cli_store)
                arguments = self.path / 'cli-arguments.json'
                arguments.write_text(json.dumps(second_body))
                with patch.object(project_cli.AgentClient, 'from_config', return_value=client), patch('sys.stdout', io.StringIO()):
                    code = project_cli.main(['--config', 'PRIVATE_CONFIG', 'call', '--operation',
                        'runs.submit_external', '--arguments', str(arguments)], observer=cli_recorder)
                self.assertEqual(code, 0)
                with sqlite3.connect(cli_store) as db:
                    self.assertEqual(db.execute("SELECT envelope_status,http_status FROM events WHERE phase='terminal'").fetchone(), (201, 201))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(5)
        for path in self.path.glob('*-v2.sqlite'):
            self.assertNotIn(b'PRIVATE_AUDIT', path.read_bytes())


@unittest.skipUnless(legacy.SDK_AVAILABLE, 'Optional pinned MCP environment required')
class MCPV2ProcessTests(legacy.ObserverProcessTests):
    """Selected inherited cases exercise identical real SDK/write paths under v2."""
    def start(self, enabled=True, database=None, child=legacy.CHILD_OBS, **env):
        child = child.replace('from mcp_observer import InteractionRecorder, RecorderConfig',
            'from mcp_observer import InterfaceRecorder, RecorderConfig')
        child = child.replace("InteractionRecorder(RecorderConfig(Path(os.environ['TEST_OBSERVER'])), agent_api.discovery())",
            "InterfaceRecorder(RecorderConfig(Path(os.environ['TEST_OBSERVER'])), agent_api.discovery(), boundary='mcp', selected={'context.get':1})")
        return super().start(enabled, database, child, **env)

    schema_version = 2

    def test_unsafe_and_corrupt_v2_storage_preserve_identical_sdk_results(self):
        values = []
        for mode in ('disabled', 'unsafe', 'corrupt'):
            self.database = self.directory / (mode + '.sqlite')
            if mode != 'disabled':
                self.database.write_bytes(b'PRIVATE_STORE')
                self.database.chmod(0o644 if mode == 'unsafe' else 0o600)
                before = self.database.read_bytes()
            process = self.start(enabled=mode != 'disabled')
            result = [self.ready(process)]
            self.send(process, legacy.request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
            result.append(self.read(process))
            errors = self.stop(process)
            if mode != 'disabled':
                self.assertIn(b'degraded', errors)
                self.assertEqual(self.database.read_bytes(), before)
            values.append(result)
        self.assertEqual(values[0], values[1])
        self.assertEqual(values[0], values[2])

    def test_actual_main_opt_in_default_disabled_config_failure_and_operator_check(self):
        token, config = self.directory / 'token', self.directory / 'config'
        token.write_text(TOKEN)
        token.chmod(0o600)
        with http_boundary() as endpoint:
            config.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': CATALOG, 'token_file': str(token)}))
            config.chmod(0o600)
            process = subprocess.Popen([sys.executable, str(ROOT / 'mcp_stdio.py'), '--config', str(config),
                '--observe-v2-database', str(self.database)], cwd=ROOT, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.addCleanup(self.cleanup, process)
            self.ready(process)
            self.send(process, legacy.request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
            self.assertEqual(self.read(process)['result']['structuredContent']['status'], 200)
            self.assertIn(b'healthy', self.stop(process))
        self.assertEqual(self.check_store(self.database)['retained_starts'], 2)
        checked = subprocess.run([sys.executable, str(ROOT / 'mcp_observer.py'), '--database', str(self.database),
            '--schema-version', '2'], capture_output=True, timeout=5)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)['schema_version'], 2)


def measure_overhead(samples=5):
    """Disposable real-boundary measurement; no universal latency threshold."""
    import platform
    import statistics
    report = {'python': platform.python_version(), 'platform': platform.system(),
              'samples_per_mode': samples, 'unit': 'milliseconds', 'boundaries': {}}
    for boundary in ('http', 'cli', 'mcp'):
        if boundary == 'mcp' and not legacy.SDK_AVAILABLE:
            continue
        rows = {}
        for mode in ('disabled', 'healthy'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                database = root / 'observer.sqlite'
                recorder = (obs.InterfaceRecorder(obs.RecorderConfig(database), agent_api.discovery(),
                    boundary=boundary, diagnostics=io.StringIO()) if mode == 'healthy' and boundary != 'mcp' else None)
                durations = []
                if boundary == 'mcp':
                    case = MCPV2ProcessTests('test_protocol_refusals_before_dispatch_and_id_reuse')
                    case.setUp()
                    process = case.start(enabled=mode == 'healthy', database=database)
                    try:
                        case.ready(process)
                        for index in range(samples):
                            started = time.perf_counter()
                            case.send(process, legacy.request('tools/call', index + 2,
                                {'name':'context_get', 'arguments':{}}))
                            case.read(process)
                            durations.append((time.perf_counter() - started) * 1000)
                        case.stop(process)
                    finally:
                        case.doCleanups()
                else:
                    with http_boundary(recorder if boundary == 'http' else None) as endpoint:
                        if boundary == 'http':
                            client = agent_api.AgentClient(endpoint, TOKEN, CATALOG)
                            client.bootstrap()
                            for _ in range(samples):
                                started = time.perf_counter()
                                client.call('context.get', {})
                                durations.append((time.perf_counter() - started) * 1000)
                        else:
                            token, config, arguments = root/'token', root/'config', root/'args.json'
                            token.write_text(TOKEN)
                            token.chmod(0o600)
                            config.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': CATALOG,
                                                         'token_file': str(token)}))
                            config.chmod(0o600)
                            arguments.write_text('{}')
                            for _ in range(samples):
                                with tempfile.TemporaryFile(mode='w+') as output, patch('sys.stdout', output):
                                    started = time.perf_counter()
                                    status = project_cli.main(['--config', str(config), 'call', '--operation',
                                        'context.get', '--arguments', str(arguments)], observer=recorder)
                                    if status != 0:
                                        raise RuntimeError('CLI measurement failed')
                                    durations.append((time.perf_counter() - started) * 1000)
                obs.observe_close(recorder)
                rows[mode] = {'median_ms': round(statistics.median(durations), 3),
                    'min_ms': round(min(durations), 3), 'max_ms': round(max(durations), 3),
                    'store_bytes': database.stat().st_size if database.exists() else 0,
                    'retained': obs.check_store(database, schema_version=2) if database.exists() else None}
        rows['median_delta_ms'] = round(rows['healthy']['median_ms'] - rows['disabled']['median_ms'], 3)
        report['boundaries'][boundary] = rows
    return report


if __name__ == '__main__':
    unittest.main()
