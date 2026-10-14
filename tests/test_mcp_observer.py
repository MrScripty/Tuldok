"""Synthetic local SQLite and real SDK process evidence; never model analytics."""
import hashlib
import io
import json
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import agent_api
import mcp_observer as obs
import test_mcp_stdio as protocol

ROOT, SDK_AVAILABLE = protocol.ROOT, protocol.SDK_AVAILABLE
CHILD, initialize, request = protocol.CHILD, protocol.initialize, protocol.request

CHILD_OBS = CHILD.replace('anyio.run(serve, AuthoredClient())', '''
from pathlib import Path
import agent_api
from mcp_observer import InteractionRecorder, RecorderConfig
observer = None
if os.environ.get('TEST_OBSERVER'):
    observer = InteractionRecorder(RecorderConfig(Path(os.environ['TEST_OBSERVER'])), agent_api.discovery())
anyio.run(serve, AuthoredClient(), 0, 1, observer)
''')


class StoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.database = self.directory / 'observations.sqlite'
        self.diagnostics = io.StringIO()

    def recorder(self, path=None, **policy):
        value = obs.InteractionRecorder(obs.RecorderConfig(path or self.database, **policy),
            agent_api.discovery(), diagnostics=self.diagnostics)
        self.addCleanup(value.close)
        return value

    def rows(self, sql):
        with sqlite3.connect(self.database) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql)]

    def begin(self, recorder):
        return recorder.begin(request('tools/call', params={'name': 'context_get', 'arguments': {}}), 101)

    def test_new_migration_reopen_identity_and_separate_stages(self):
        first = self.recorder()
        event = self.begin(first)
        for phase in ('validated', 'admitted', 'dispatch'):
            first.stage(event, phase)
        first.stage(event, 'returned', outcome='success', http_status=200)
        first.stage(event, 'terminal', outcome='success', http_status=200,
                    response_bytes=13, delivery='written')
        first.close()
        again = self.recorder()
        self.assertNotEqual(first.session, again.session)
        other = self.begin(again)
        again.close()
        self.assertEqual(obs.check_store(self.database)['retained_starts'], 2)
        self.assertEqual(len(self.rows('SELECT * FROM sessions')), 2)
        self.assertEqual([x['outcome'] for x in self.rows("SELECT * FROM events WHERE phase='terminal' ORDER BY recorded")], ['success', 'unknown'])
        self.assertEqual(self.rows('PRAGMA user_version')[0]['user_version'], 1)
        self.assertEqual(self.rows('PRAGMA application_id')[0]['application_id'], obs.APPLICATION_ID)
        self.assertEqual(len(self.rows('SELECT * FROM events')), 6)
        self.assertEqual(self.database.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(other.identity), 32)

    def test_actual_locked_full_unavailable_and_broken_diagnostics_fail_open(self):
        recorder = self.recorder()
        with sqlite3.connect(self.database, isolation_level=None) as lock:
            lock.execute('BEGIN IMMEDIATE')
            started = time.monotonic()
            self.assertIsNone(self.begin(recorder))
            self.assertLess(time.monotonic() - started, 1)
            lock.execute('ROLLBACK')
        self.assertEqual(recorder.health['reason'], 'storage-locked')
        full = self.recorder()
        event = self.begin(full)
        db = full._connection
        # Fill retained structural column to page boundaries, then cap real SQLite.
        db.execute('UPDATE interactions SET input_shape=?', ('x' * 3950,))
        pages = db.execute('PRAGMA page_count').fetchone()[0]
        db.execute(f'PRAGMA max_page_count={pages}')
        # Existing terminal page has capacity; force real SQLITE_FULL in its index/table.
        with self.assertRaises(sqlite3.OperationalError) as raised:
            db.execute('UPDATE interactions SET input_shape=?', ('x' * (pages * 4096),))
        self.assertEqual(raised.exception.sqlite_errorcode, sqlite3.SQLITE_FULL)
        full._transaction(lambda connection: connection.execute('UPDATE interactions SET input_shape=?', ('x' * (pages * 4096),)))
        self.assertEqual(full.health['reason'], 'storage-full')
        self.assertEqual(obs.check_store(self.database)['unfinished'], 1)
        unavailable = self.recorder(self.directory / 'missing' / 'private-sentinel')
        self.assertEqual(unavailable.health['state'], 'degraded')
        self.assertNotIn('private-sentinel', self.diagnostics.getvalue())
        class Broken:
            def write(self, value): raise OSError('DIAGNOSTIC_SECRET')
            def flush(self): raise OSError('DIAGNOSTIC_SECRET')
        broken = obs.InteractionRecorder(obs.RecorderConfig(self.directory / 'absent' / 'db'),
            agent_api.discovery(), diagnostics=Broken())
        broken.close()
        self.assertEqual(broken.health['state'], 'degraded')

    def test_foreign_future_partial_corrupt_nonpristine_and_wal_stay_intact(self):
        for name, setup in (
            ('foreign', 'CREATE TABLE private(value TEXT)'),
            ('future', 'PRAGMA user_version=99'),
            ('partial', f'PRAGMA user_version=1; PRAGMA application_id={obs.APPLICATION_ID}; CREATE TABLE sessions(id TEXT)'),
            ('old-private', "PRAGMA secure_delete=OFF; CREATE TABLE private(value TEXT); INSERT INTO private VALUES('DELETED_PRIVATE_SENTINEL'); DROP TABLE private"),
            ('wal', 'PRAGMA journal_mode=WAL'),
        ):
            with self.subTest(name=name):
                path = self.directory / name
                with sqlite3.connect(path) as db: db.executescript(setup)
                path.chmod(0o600)
                before = path.read_bytes()
                recorder = self.recorder(path)
                self.assertEqual(recorder.health['state'], 'degraded')
                self.assertEqual(path.read_bytes(), before)
        corrupt = self.directory / 'corrupt'
        corrupt.write_bytes(b'SENSITIVE_NOT_SQLITE')
        corrupt.chmod(0o600)
        self.assertEqual(self.recorder(corrupt).health['reason'], 'storage-corrupt')
        self.assertEqual(corrupt.read_bytes(), b'SENSITIVE_NOT_SQLITE')

    def test_private_directory_files_symlinks_hardlinks_and_policy_mismatch(self):
        target = self.directory / 'target'
        target.touch(mode=0o600)
        link = self.directory / 'link'
        link.symlink_to(target)
        self.assertEqual(self.recorder(link).health['state'], 'degraded')
        hard = self.directory / 'hard'
        os.link(target, hard)
        self.assertEqual(self.recorder(hard).health['reason'], 'unsafe-storage')
        public = self.directory / 'public'
        public.touch(mode=0o644)
        public.chmod(0o644)
        self.assertEqual(self.recorder(public).health['reason'], 'unsafe-storage')
        recorder = self.recorder(max_calls=16)
        self.assertEqual(self.recorder(max_calls=17).health['reason'], 'retention-policy-mismatch')
        recorder.close()
        journal = Path(str(self.database) + '-journal')
        journal.symlink_to(target)
        self.assertEqual(self.recorder(max_calls=16).health['state'], 'degraded')
        self.assertEqual(target.read_bytes(), b'')
        journal.unlink()
        self.directory.chmod(0o755)
        self.assertEqual(self.recorder().health['reason'], 'unsafe-storage')
        self.directory.chmod(0o700)

    def test_concurrent_sessions_retention_eviction_and_bounded_active_state(self):
        first = self.recorder(max_calls=16)
        held = self.begin(first)
        second = self.recorder(max_calls=16)
        for _ in range(20):
            event = self.begin(second)
            second.stage(event, 'terminal', outcome='success', delivery='written', response_bytes=2)
        first.stage(held, 'terminal', outcome='success', delivery='written')
        self.assertEqual(first.health['state'], 'healthy')
        self.assertEqual(first.health['dropped'], 1)
        self.assertEqual(obs.check_store(self.database)['retained_starts'], 16)
        later = self.begin(first)
        first.stage(later, 'terminal', outcome='success', delivery='written')
        self.assertEqual(len(self.rows('SELECT * FROM sessions')), 2)
        for _ in range(18):
            third = self.recorder(max_calls=16)
            event = self.begin(third)
            third.stage(event, 'terminal', outcome='response', delivery='written')
            third.close()
        self.assertLessEqual(len(self.rows('SELECT * FROM sessions')), 16)
        now = self.recorder(max_calls=16)
        self.assertIsNotNone(self.begin(now))
        self.assertIsNotNone(self.begin(now))
        self.assertIsNone(self.begin(now))
        self.assertEqual(now.health['reason'], 'observation-capacity')

    def test_age_retention_offline_maintenance_and_readonly_health(self):
        recorder = self.recorder(max_age_seconds=60)
        event = self.begin(recorder)
        recorder.stage(event, 'terminal', outcome='success', delivery='written')
        before = self.database.read_bytes()
        self.assertEqual(obs.check_store(self.database)['retained_starts'], 1)
        self.assertEqual(self.database.read_bytes(), before)
        with self.assertRaises(BlockingIOError): obs.check_store(self.database, retain=True)
        recorder.close()
        with patch.object(obs.time, 'time', return_value=time.time() + 61):
            self.assertEqual(obs.check_store(self.database, retain=True)['retained_starts'], 0)
        self.assertEqual(self.rows('SELECT * FROM sessions'), [])
        missing = self.directory / 'never-create'
        with self.assertRaises(FileNotFoundError): obs.check_store(missing)
        with self.assertRaises(FileNotFoundError): obs.check_store(missing, retain=True)
        self.assertFalse(missing.exists())

    def test_bad_policy_and_partial_record_refuse_without_deleting_evidence(self):
        recorder = self.recorder()
        event = self.begin(recorder)
        recorder.stage(event, 'terminal', outcome='success', delivery='written')
        recorder.close()
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE policy SET max_calls=0,max_age_seconds=-1')
        before = self.database.read_bytes()
        for retain in (False, True):
            with self.assertRaisesRegex(obs.StorageRejected, 'invalid-retention-policy'):
                obs.check_store(self.database, retain=retain)
            self.assertEqual(self.database.read_bytes(), before)
        with sqlite3.connect(self.database) as db:
            db.execute('UPDATE policy SET max_calls=10000,max_age_seconds=604800')
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute("UPDATE events SET interaction='missing-start'")
        before = self.database.read_bytes()
        with self.assertRaisesRegex(obs.StorageRejected, 'invalid-database-records'):
            obs.check_store(self.database, retain=True)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.recorder().health['reason'], 'invalid-database-records')
        self.assertEqual(self.database.read_bytes(), before)

    def test_privacy_closed_shape_and_disk_projection(self):
        recorder = self.recorder()
        secrets = ['UNIQUE_' + str(i) + '_SECRET_ASSET_PATH' for i in range(7)]
        for operation in agent_api.discovery()['operations']:
            args = {name: {secrets[0]: secrets[1]} for name in operation['inputSchema'].get('properties', {})}
            args.update({secrets[2]: secrets[3], 'text': secrets[4], 'files': {secrets[5]: secrets[6]}})
            message = request('tools/call', secrets[0], {'name': operation['mcp_name'], 'arguments': args, '_meta': {'token': secrets[1]}})
            event = recorder.begin(message, 500)
            recorder.stage(event, 'terminal', outcome='invalid-parameters', delivery='written')
        recorder.close()
        for path in self.directory.iterdir():
            raw = path.read_bytes()
            for secret in secrets:
                self.assertNotIn(secret.encode(), raw)
                self.assertNotIn(hashlib.sha256(secret.encode()).hexdigest().encode(), raw)
        for secret in secrets: self.assertNotIn(secret, self.diagnostics.getvalue())
        self.assertEqual(obs.input_shape({'properties': {'annotation': {}}}, {'annotation': {'text': secrets[0]}})['fields']['annotation'], 'redacted')
        self.assertEqual(obs.input_shape({'properties': {'q': {}}}, {'q': secrets[0]})['fields']['q'], {'type': 'string', 'size': len(secrets[0])})

    def test_simultaneous_process_first_open_and_writes(self):
        release = self.directory / 'release'
        code = '''
import io,sys,time
from pathlib import Path
import agent_api,mcp_observer as o
deadline=time.monotonic()+8
while not Path(sys.argv[2]).exists():
    if time.monotonic()>=deadline: raise RuntimeError('test gate deadline')
    time.sleep(.01)
r=o.InteractionRecorder(o.RecorderConfig(Path(sys.argv[1])),agent_api.discovery(),diagnostics=io.StringIO())
# SQLite's declared lock budget can legitimately degrade a competing writer.
if r.health['state']=='healthy':
    e=r.begin({'id':1,'method':'ping'},12)
    r.stage(e,'terminal',outcome='response',delivery='written')
r.close()
print(r.health['state'])
'''
        processes = [subprocess.Popen([sys.executable, '-c', code, str(self.database), str(release)],
                     cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
        for process in processes:
            self.addCleanup(protocol.SDKProcessTests.cleanup, self, process)
        release.touch()
        results = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stderr, b'')
            results.append(stdout.strip())
        self.assertIn(b'healthy', results)
        checked = obs.check_store(self.database)
        self.assertGreaterEqual(checked['retained_starts'], 1)
        self.assertEqual(checked['unfinished'], 0)

    def test_interrupted_initialization_rolls_back_before_reopen(self):
        code = '''
import io,os,sys
from pathlib import Path
import agent_api,mcp_observer as o
o._validate_schema=lambda db: os._exit(7)
o.InteractionRecorder(o.RecorderConfig(Path(sys.argv[1])),agent_api.discovery(),diagnostics=io.StringIO())
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.database)], cwd=ROOT,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 7)
        recorder = self.recorder()
        self.assertEqual(recorder.health['state'], 'healthy')
        self.assertIsNotNone(self.begin(recorder))
        recorder.close()
        self.assertEqual(obs.check_store(self.database)['unfinished'], 0)


@unittest.skipUnless(SDK_AVAILABLE, 'Optional pinned MCP environment required')
class ObserverProcessTests(unittest.TestCase):
    cleanup = protocol.SDKProcessTests.cleanup
    ready = protocol.SDKProcessTests.ready

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.database = self.directory / 'observer.sqlite'
        self.sent = self.received = 0
        self.raw_replies = []

    def start(self, enabled=True, database=None, child=CHILD_OBS, **env):
        process = subprocess.Popen([sys.executable, '-c', child], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, TEST_OBSERVER=str(database or self.database) if enabled else '', **env))
        self.addCleanup(self.cleanup, process)
        return process

    def send(self, process, value):
        raw = json.dumps(value).encode() + b'\n'
        process.stdin.write(raw)
        process.stdin.flush()
        if 'id' in value: self.sent += len(raw)

    def read(self, process, timeout=8):
        deadline, raw = time.monotonic() + timeout, bytearray()
        while not raw.endswith(b'\n'):
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0)
            self.assertTrue(select.select([process.stdout], [], [], remaining)[0])
            block = os.read(process.stdout.fileno(), 1)
            self.assertTrue(block, 'Bridge closed before reply')
            raw.extend(block)
        self.received += len(raw)
        self.raw_replies.append(bytes(raw))
        return json.loads(raw)

    def rows(self, sql):
        with sqlite3.connect(self.database) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(sql)]

    def stop(self, process):
        process.stdin.close()
        self.assertEqual(process.wait(timeout=8), 0)
        return process.stderr.read()

    def test_cold_session_exact_frame_bytes_order_schema_identity_and_disabled_parity(self):
        replies, raw_replies = [], []
        for enabled in (False, True):
            process = self.start(enabled=enabled)
            self.sent = self.received = 0
            self.raw_replies = []
            values = [self.ready(process)]
            self.send(process, request('tools/list', 2))
            values.append(self.read(process))
            self.send(process, request('tools/call', 3, {'name': 'context_get', 'arguments': {}}))
            values.append(self.read(process))
            errors = self.stop(process)
            if not enabled:
                self.assertFalse(self.database.exists())
                self.assertEqual(errors, b'')
            replies.append(values)
            raw_replies.append(self.raw_replies)
        self.assertEqual(replies[0], replies[1])
        self.assertEqual(raw_replies[0], raw_replies[1])
        starts = self.rows('SELECT * FROM interactions ORDER BY ordinal')
        self.assertEqual([r['method'] for r in starts], ['initialize', 'tools/list', 'tools/call'])
        self.assertEqual([r['ordinal'] for r in starts], [1, 2, 3])
        self.assertEqual(len({r['id'] for r in starts}), 3)
        self.assertEqual(sum(r['request_bytes'] for r in starts), self.sent)
        terminals = self.rows("SELECT * FROM events WHERE phase='terminal'")
        self.assertEqual(sum(r['response_bytes'] for r in terminals), self.received)
        self.assertTrue(all(r['delivery'] == 'written' and r['duration_ms'] >= 0 for r in terminals))
        self.assertEqual(starts[2]['operation_id'], 'context.get')
        self.assertEqual(starts[2]['input_schema'], obs._digest(agent_api.operation('context_get')['inputSchema']))
        self.assertEqual(self.rows('SELECT registry_digest FROM sessions')[0]['registry_digest'], 'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')
        self.assertEqual(hashlib.sha256(agent_api.encoded(agent_api.tool_definitions())).hexdigest(), 'deeb2a54844707e6bc1c27df98e489b41123cd251283a9bc1d8007ec5f0d779a')

    def test_protocol_refusals_before_dispatch_and_id_reuse(self):
        process = self.start()
        self.ready(process)
        bad = [request('secret-unknown-method', 2), request('tools/call', 3, {'name': 'secret-tool'}),
               request('tools/call', 4, {'name': 'context_get', 'arguments': {'secret-field': 'secret-value'}}),
               request('tools/call', 5, {'name': 'context_get', 'arguments': []}),
               request('initialize', 6)]
        for value in bad:
            self.send(process, value)
            self.assertIn('error', self.read(process))
        process.stdin.write(b'{INVALID_SECRET_JSON\n')
        process.stdin.flush()
        self.assertEqual(self.read(process)['error']['code'], -32700)
        for _ in range(2):
            self.send(process, request('tools/call', 7, {'name': 'context_get', 'arguments': {}}))
            self.assertEqual(self.read(process)['result']['structuredContent']['status'], 200)
        self.stop(process)
        self.assertEqual(len(self.rows('SELECT * FROM interactions')), 9)
        self.assertEqual(len(self.rows("SELECT * FROM events WHERE phase='terminal'")), 9)
        self.assertEqual(len(self.rows("SELECT * FROM events WHERE phase='dispatch'")), 2)
        self.assertNotIn(b'secret-', self.database.read_bytes())
        self.assertNotIn(b'INVALID_SECRET', self.database.read_bytes())

    def test_overlap_duplicate_refusal_keeps_original_correlation(self):
        gate = self.directory / 'release'
        process = self.start(TULDOK_TEST_GATE=str(gate))
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        self.send(process, request('ping', 2))
        self.assertIsNone(self.read(process)['id'])
        self.send(process, request('ping', 3))
        self.assertEqual(self.read(process)['error']['code'], -32000)
        gate.touch()
        self.assertEqual(self.read(process)['id'], 2)
        self.stop(process)
        self.assertEqual(len(self.rows('SELECT * FROM interactions')), 4)
        self.assertEqual(len(self.rows("SELECT * FROM events WHERE phase='terminal'")), 4)
        self.assertEqual(len(self.rows("SELECT * FROM events WHERE phase='dispatch'")), 1)
        self.assertEqual([r['outcome'] for r in self.rows("SELECT * FROM events WHERE phase='returned'")], ['success'])

    def test_restart_sigkill_retains_unknown_without_rewriting_live_session(self):
        first = self.start(TULDOK_TEST_GATE=str(self.directory / 'never-release'))
        self.ready(first)
        self.send(first, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        deadline = time.monotonic() + 5
        while not self.rows("SELECT * FROM events WHERE phase='dispatch'"):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        original = self.rows("SELECT interaction FROM events WHERE phase='dispatch'")[0]['interaction']
        second = self.start()
        self.ready(second)
        self.assertFalse(self.rows(f"SELECT * FROM events WHERE interaction='{original}' AND phase='terminal'"))
        first.kill()
        first.wait(timeout=5)
        self.stop(second)
        third = self.start()
        self.ready(third)
        self.stop(third)
        self.assertFalse(self.rows(f"SELECT * FROM events WHERE interaction='{original}' AND phase='terminal'"))
        self.assertEqual(obs.check_store(self.database)['unfinished'], 1)

    def test_unavailable_and_locked_storage_preserve_identical_replies(self):
        replies = []
        recorder = obs.InteractionRecorder(obs.RecorderConfig(self.database), agent_api.discovery(), diagnostics=io.StringIO())
        recorder.close()
        for mode in ('disabled', 'unavailable', 'locked'):
            with sqlite3.connect(self.database, isolation_level=None) as lock:
                if mode == 'locked': lock.execute('BEGIN IMMEDIATE')
                process = self.start(enabled=mode != 'disabled', database=self.directory / 'missing' / 'SECRET_PATH' if mode == 'unavailable' else self.database)
                values = [self.ready(process)]
                self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
                values.append(self.read(process))
                errors = self.stop(process)
                if mode == 'locked': lock.execute('ROLLBACK')
                if mode != 'disabled': self.assertIn(b'degraded', errors)
                self.assertNotIn(b'SECRET_PATH', errors)
                replies.append(values)
        self.assertEqual(replies[0], replies[1])
        self.assertEqual(replies[0], replies[2])

    def test_broken_stdout_records_return_separately_from_unknown_delivery(self):
        gate = self.directory / 'release'
        process = self.start(TULDOK_TEST_GATE=str(gate))
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        process.stdout.close()
        gate.touch()
        process.wait(timeout=8)
        returned = self.rows("SELECT * FROM events WHERE phase='returned'")
        self.assertEqual([r['outcome'] for r in returned], ['success'])
        terminal = self.rows("SELECT * FROM events WHERE phase='terminal' AND outcome='unknown'")
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0]['delivery'], 'incomplete')
        self.assertEqual(terminal[0]['response_bytes'], 0)

    def test_oversize_and_partial_eof_frame_have_one_terminal(self):
        for raw in (b' ' * (1024 * 1024 + 1), b'{"secret":"PRIVATE_EOF"'):
            self.database = self.directory / ('store-' + str(len(raw)))
            process = self.start()
            process.stdin.write(raw)
            process.stdin.close()
            self.assertEqual(self.read(process)['error']['code'], -32700)
            self.assertEqual(process.wait(timeout=8), 0)
            self.assertEqual(obs.check_store(self.database)['retained_starts'], 1)
            self.assertEqual(obs.check_store(self.database)['retained_terminals'], 1)
            self.assertNotIn(b'PRIVATE_EOF', self.database.read_bytes())

    def test_typed_execution_outcomes_do_not_store_error_text_or_output(self):
        typed_child = CHILD_OBS.replace("        time.sleep(float(os.environ.get('TULDOK_TEST_DELAY', '0')))", '''
        from agent_api import AgentAPIError
        mode = os.environ['TEST_MODE']
        if mode == 'transport': raise AgentAPIError('PRIVATE_TRANSPORT', 'transport', 503)
        if mode == 'permission': return {'status':403,'result':{'code':'PRIVATE_CODE','error':'PRIVATE_PERMISSION'}}
        if mode == 'domain': return {'status':409,'result':{'code':'PRIVATE_CODE','error':'PRIVATE_DOMAIN'}}
        if mode == 'invalid-output': return {'status':200,'result':{}}
        if mode == 'bridge': raise RuntimeError('PRIVATE_EXCEPTION')
''')
        for mode, outcome, status, actual in [('transport', 'transport-error', 503, None),
            ('permission', 'permission-refusal', 403, 403), ('domain', 'domain-error', 409, 409),
            ('invalid-output', 'transport-error', 502, 200), ('bridge', 'bridge-error', 502, None)]:
            with self.subTest(mode=mode):
                self.database = self.directory / mode
                process = self.start(child=typed_child, TEST_MODE=mode)
                self.ready(process)
                self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
                self.assertEqual(self.read(process)['result']['structuredContent']['status'], status)
                self.stop(process)
                returned = self.rows("SELECT * FROM events WHERE phase='returned'")[0]
                self.assertEqual((returned['outcome'], returned['envelope_status'], returned['http_status']), (outcome, status, actual))
                self.assertNotIn(b'PRIVATE_', self.database.read_bytes())

    def test_final_encoding_substitution_counts_actual_small_reply(self):
        process = self.start(TULDOK_TEST_PAYLOAD=str(17 * 1024 * 1024))
        self.ready(process)
        before = self.received
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        reply = self.read(process)
        self.assertEqual(reply['result']['structuredContent']['result']['code'], 'response_too_large')
        self.stop(process)
        returned = self.rows("SELECT * FROM events WHERE phase='returned'")[0]
        terminal = self.rows("SELECT * FROM events WHERE phase='terminal' AND outcome='response-too-large'")[0]
        self.assertEqual(returned['outcome'], 'success')
        self.assertEqual(terminal['response_bytes'], self.received - before)
        self.assertEqual(terminal['http_status'], 200)
        self.assertEqual(terminal['envelope_status'], 502)

    def test_actual_partial_stdout_timeout_preserves_written_byte_count(self):
        process = self.start(TULDOK_TEST_PAYLOAD=str(1024 * 1024))
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        # Keep stdout's read endpoint open but do not drain it until write timeout.
        process.wait(timeout=12)
        raw = process.stdout.read()
        terminals = self.rows("SELECT * FROM events WHERE phase='terminal' AND delivery='incomplete'")
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0]['response_bytes'], len(raw))
        self.assertGreater(len(raw), 0)
        self.assertFalse(raw.endswith(b'\n'))

    def test_real_sqlite_full_during_post_call_recording_preserves_one_result(self):
        child = CHILD_OBS.replace('anyio.run(serve, AuthoredClient(), 0, 1, observer)', '''
original_stage = observer.stage
def quota_stage(event, phase, **values):
    if phase == 'returned':
        db = observer._connection
        pages = db.execute('PRAGMA page_count').fetchone()[0]
        db.execute(f'PRAGMA max_page_count={pages}')
        # Actual SQLITE_FULL within the recorder's fail-open transaction owner.
        observer._transaction(lambda db: db.execute('UPDATE interactions SET input_shape=?', ('x' * (pages*4096),)))
    original_stage(event, phase, **values)
observer.stage = quota_stage
anyio.run(serve, AuthoredClient(), 0, 1, observer)
''')
        process = self.start(child=child)
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        reply = self.read(process)
        self.assertEqual(reply['result']['structuredContent']['status'], 200)
        errors = self.stop(process)
        self.assertIn(b'storage-full', errors)
        self.assertEqual(len(self.rows("SELECT * FROM events WHERE phase='dispatch'")), 1)
        self.assertEqual(obs.check_store(self.database)['unfinished'], 1)

    def test_actual_main_opt_in_default_disabled_config_failure_and_operator_check(self):
        from test_agent_api import server, TOKEN, CATALOG
        token, config = self.directory / 'token', self.directory / 'config'
        token.write_text(TOKEN)
        token.chmod(0o600)
        with server('normal') as (endpoint, calls):
            config.write_text(json.dumps({'endpoint': endpoint, 'catalog_id': CATALOG, 'token_file': str(token)}))
            config.chmod(0o600)
            replies = []
            for mode in ('disabled', 'enabled', 'unavailable', 'invalid-policy'):
                args = [sys.executable, str(ROOT / 'mcp_stdio.py'), '--config', str(config)]
                if mode != 'disabled':
                    args.extend(['--observe-database', str(self.database if mode != 'unavailable' else self.directory / 'missing' / 'SECRET_PATH')])
                if mode == 'invalid-policy': args.extend(['--observe-max-calls', 'SECRET_CONFIG'])
                process = subprocess.Popen(args, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.addCleanup(self.cleanup, process)
                values = [self.ready(process)]
                self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
                values.append(self.read(process))
                errors = self.stop(process)
                replies.append(values)
                if mode == 'disabled':
                    self.assertFalse(self.database.exists())
                    self.assertEqual(errors, b'')
                elif mode == 'enabled': self.assertIn(b'healthy', errors)
                else: self.assertIn(b'tuldok observer', errors)
                for secret in (TOKEN, 'SECRET_PATH', 'SECRET_CONFIG', str(config)):
                    self.assertNotIn(secret.encode(), errors)
            for values in replies[1:]: self.assertEqual(values, replies[0])
        checked = subprocess.run([sys.executable, str(ROOT / 'mcp_observer.py'), '--database', str(self.database)],
            capture_output=True, timeout=5)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)['retained_starts'], 2)
        disabled = self.start(enabled=False)
        self.ready(disabled)
        self.stop(disabled)
        self.assertEqual(obs.check_store(self.database)['retained_starts'], 2)


if __name__ == '__main__':
    unittest.main()
