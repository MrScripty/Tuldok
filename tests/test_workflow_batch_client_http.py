"""Actual HTTP and clean CLI witnesses for explicit whole-artifact batching.

The producer copies tiny neutral bytes through actual authorized custody. Faults
are explicit service failures or changes after real HTTP delivery. No numerical,
training, runtime-performance or scientific acceptance claim is made here.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

import agent_api
from agent_api import AgentAPIError, AgentClient
from benchmark_lab_workflow import Fixture
from tuldok_client import WorkflowClient
from workbench import WorkbenchError

ROOT = Path(__file__).resolve().parents[1]
BATCH_PATH = '/api/workspace/artifact-segments'


def record_cleanup(label, value):
    report = os.environ.get('TULDOK_BATCH_CLEANUP_REPORT')
    if report:
        path = Path(report)
        path = path.with_name(path.stem+'-'+label+path.suffix)
        with path.open('x') as stream:
            json.dump(value, stream, sort_keys=True)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL and actual HTTP')
class BatchWorkflowHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture(20, 1280)
        try:
            cls.fixture.populate_one()
            cls.dataset = cls.fixture.dataset
            cls.run_id = cls.fixture.target
            cls.events = copy.deepcopy(cls.dataset.runs._load(cls.run_id)['events'])
            cls.before = cls.counts()
        except BaseException:
            cls.fixture.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cleaned = cls.fixture.cleanup()
        if not cleaned['dropped']:
            raise AssertionError('Fresh batch consumer schema was not removed.')
        # Optional report path is selected by the qualification runner, never a
        # catalog lookup or a pre-existing schema inferred by this fixture.
        record_cleanup('twenty', cleaned)

    @classmethod
    def counts(cls):
        return {table: cls.dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                for table in ('workspace_runs', 'access_execution_grants', 'access_execution_consumptions')}

    def setUp(self):
        self.path = self.fixture.path/self._testMethodName
        self.path.mkdir(mode=0o700)
        self.output = self.path/'output'; self.output.mkdir(mode=0o700)
        with self.fixture.owner.bound(self.dataset):
            self.agent = self.dataset.access.issue({'label': 'Explicit batch consumer witness', 'scopes': ['inspect']})
        self.client = AgentClient(self.fixture.endpoint, self.agent['token'], self.dataset.db.dataset_id, timeout=10)
        self.workflow = WorkflowClient(self.client)
        self.manifest = self.workflow.collection_manifest(run_id=self.run_id,
            names=[item['name'] for item in self.fixture.expected])
        self.request_start = len(self.fixture.metrics.requests)
        token = self.path/'token'; token.write_text(self.agent['token']); token.chmod(0o600)
        self.config = self.file('agent.json', {'endpoint': self.fixture.endpoint,
            'catalog_id': self.client.catalog_id, 'token_file': str(token), 'timeout': 10})

    def tearDown(self):
        self.assertEqual(self.counts(), self.before)
        self.assertEqual(self.dataset.runs._load(self.run_id)['events'], self.events)
        self.assertEqual(list(self.output.glob('.tuldok-download-*')), [])

    def file(self, name, value):
        path = self.path/name; path.write_text(json.dumps(value)); path.chmod(0o600)
        return path

    def cli(self, *arguments, expected=0):
        result = subprocess.run([sys.executable, str(ROOT/'project_cli.py'), '--config', str(self.config),
            *map(str, arguments)], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
        self.assertNotIn(self.agent['token'], result.stdout+result.stderr)
        return json.loads(result.stdout or result.stderr)

    def calls(self):
        return self.fixture.metrics.requests[self.request_start:]

    def assert_wholes(self, receipt):
        self.assertEqual(receipt['state'], 'complete', receipt)
        self.assertEqual(len(receipt['items']), 20)
        for index, item in enumerate(self.fixture.expected):
            path = self.output/item['name']
            raw = path.read_bytes()
            self.assertEqual(raw, self.fixture.payload[index*64:(index+1)*64])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(receipt['items'][index]['receipt']['verification'], 'whole_sha256_verified')

    def test_actual_sdk_twenty_wholes_use_one_batch_without_compute(self):
        with patch('recipe_process.launch', side_effect=AssertionError('Read consumer replayed compute')):
            receipt = self.workflow.collect_batch(self.manifest, self.output)
        self.assert_wholes(receipt)
        self.assertEqual([row['path'] for row in self.calls()],
                         ['/api/workspace/runs/'+self.run_id, BATCH_PATH])

    def test_clean_cli_twenty_wholes_and_ordinary_explicit_resume(self):
        manifest = self.file('manifest.json', self.manifest)
        receipt = self.cli('collect-batch', '--manifest', manifest, '--directory', self.output)
        self.assert_wholes(receipt)
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)
        self.assertFalse(any('/artifact-segment/' in row['path'] for row in self.calls()))
        saved = self.file('receipt.json', receipt)
        resumed = self.cli('collect', '--manifest', manifest, '--directory', self.output, '--resume', saved)
        self.assert_wholes(resumed)
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)
        self.assertEqual(sum('/artifact-segment/' in row['path'] for row in self.calls()), 20)

    def test_actual_item_refusal_yields_partial_then_only_explicit_ordinary_resume_restarts(self):
        original = self.dataset.runs.artifact_segment
        def refusal(run_id, name, body, **kwargs):
            if name == self.manifest['items'][1]['name']:
                raise WorkbenchError('Authored exact item refusal', 'conflict', 409)
            return original(run_id, name, body, **kwargs)
        with patch.object(self.dataset.runs, 'artifact_segment', side_effect=refusal):
            receipt = self.cli('collect-batch', '--manifest', self.file('manifest.json', self.manifest),
                               '--directory', self.output, expected=1)
        self.assertEqual(receipt['state'], 'partial')
        self.assertEqual([row['state'] for row in receipt['items']], ['verified', 'refused']+['outstanding']*18)
        self.assertEqual(receipt['items'][1]['error'],
                         {'code': 'conflict', 'error': 'Authored exact item refusal', 'status': 409})
        self.assertEqual([path.name for path in self.output.iterdir()], [self.manifest['items'][0]['name']])
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)
        resumed = self.cli('collect', '--manifest', self.path/'manifest.json', '--directory', self.output,
                           '--resume', self.file('partial.json', receipt))
        self.assert_wholes(resumed)
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)

    def test_actual_revocation_at_delivery_discards_batch_and_publishes_nothing(self):
        original = agent_api.validate_output
        revoked = []
        def revoke(name, envelope, *args, **kwargs):
            result = original(name, envelope, *args, **kwargs)
            if name == 'runs.artifact_segments' and envelope['status'] == 200 and not revoked:
                with self.fixture.owner.bound(self.dataset):
                    self.dataset.access.revoke(self.agent['identity']['credential_id'])
                revoked.append(True)
            return result
        with patch('agent_api.validate_output', side_effect=revoke):
            with self.assertRaises(AgentAPIError) as caught:
                self.workflow.collect_batch(self.manifest, self.output)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(revoked, [True])
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)

    def test_actual_http_response_whole_corruption_and_identity_mismatch_never_fallback(self):
        request = self.client._request
        def corrupt(method, path, body=None, **kwargs):
            reply = request(method, path, body, **kwargs)
            if path == BATCH_PATH:
                reply = copy.deepcopy(reply)
                segment = reply['result']['items'][0]['result']
                raw = b'X'*segment['bytes']
                segment['data_base64'] = base64.b64encode(raw).decode()
                segment['segment_sha256'] = hashlib.sha256(raw).hexdigest()
            return reply
        with patch.object(self.client, '_request', side_effect=corrupt):
            receipt = self.workflow.collect_batch(self.manifest, self.output)
        self.assertEqual(receipt['items'][0]['error']['code'], 'artifact_mismatch')
        self.assertEqual(receipt['state'], 'partial')
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)
        def wrong_source(method, path, body=None, **kwargs):
            reply = request(method, path, body, **kwargs)
            if path == BATCH_PATH:
                reply = copy.deepcopy(reply)
                reply['result']['items'][0]['source']['run_id'] = 'a'*32
            return reply
        with patch.object(self.client, '_request', side_effect=wrong_source):
            with self.assertRaises(AgentAPIError):
                self.workflow.collect_batch(self.manifest, self.output)
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 2)
        self.assertFalse(any('/artifact-segment/' in row['path'] for row in self.calls()))

    def test_actual_cancellation_interrupts_held_http_read_without_cancel_or_retry(self):
        watchdogs_before = {thread.ident for thread in threading.enumerate() if thread.name == 'agent-read-budget'}
        entered = threading.Event(); release = threading.Event(); stop = threading.Event(); left = threading.Event()
        attempts = []
        original = self.dataset.runs.artifact_segments
        def held(body, **kwargs):
            attempts.append(copy.deepcopy(body))
            entered.set()
            if not release.wait(10):
                raise AssertionError('Held batch test did not release owner')
            try:
                return original(body, **kwargs)
            finally:
                left.set()
        def cancel():
            if entered.wait(10): stop.set()
        worker = threading.Thread(target=cancel); worker.start()
        start = time.monotonic()
        try:
            with patch.object(self.dataset.runs, 'artifact_segments', side_effect=held), \
                    patch.object(self.client, '_request', wraps=self.client._request) as requests:
                receipt = self.workflow.collect_batch(self.manifest, self.output, cancelled=stop)
                self.assertEqual(receipt['state'], 'stopped', receipt)
                self.assertLess(time.monotonic()-start, 5)
                self.assertEqual([call.args[1] for call in requests.call_args_list],
                                 ['/api/workspace/runs/'+self.run_id, BATCH_PATH])
                release.set()
                # Keep the service fault active until its handler has left it.
                self.assertTrue(left.wait(5))
        finally:
            release.set(); worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(attempts), 1)
        # A separate clean CLI process receives real SIGINT only after the real
        # service has accepted its batch request; it must save a stopped receipt.
        entered.clear(); release.clear(); left.clear()
        arguments = [sys.executable, str(ROOT/'project_cli.py'), '--config', str(self.config),
            'collect-batch', '--manifest', str(self.file('cancel-manifest.json', self.manifest)),
            '--directory', str(self.output)]
        with patch.object(self.dataset.runs, 'artifact_segments', side_effect=held):
            process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            interrupt_done = threading.Event()
            def interrupt_cli():
                while not interrupt_done.wait(.025):
                    if process.poll() is not None:
                        return
                    if entered.is_set():
                        process.send_signal(signal.SIGINT)
                        return
            interrupter = threading.Thread(target=interrupt_cli); interrupter.start()
            try:
                stdout, stderr = process.communicate(timeout=90)
                self.assertEqual(process.returncode, 1, stdout+stderr)
                self.assertNotIn(self.agent['token'], stdout+stderr)
                self.assertEqual(json.loads(stdout)['state'], 'stopped', stdout+stderr)
            finally:
                release.set(); interrupt_done.set(); interrupter.join(5)
                if process.poll() is None:
                    process.kill(); process.communicate(timeout=5)
            self.assertTrue(left.wait(5))
        self.assertEqual(len(attempts), 2)
        self.assertFalse(interrupter.is_alive())
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertFalse(any('/cancel' in row['path'] or '/artifact-segment/' in row['path'] for row in self.calls()))
        self.assertFalse(any(thread.name == 'agent-read-budget' and thread.ident not in watchdogs_before
                             for thread in threading.enumerate()))

    def test_actual_cli_known_collision_refuses_before_bootstrap_and_race_preserves_sentinel(self):
        destination = self.output/self.manifest['items'][0]['name']
        destination.write_bytes(b'keep existing bytes')
        receipt = self.cli('collect-batch', '--manifest', self.file('manifest.json', self.manifest),
                           '--directory', self.output, expected=1)
        self.assertEqual(receipt['items'][0]['error']['code'], 'conflict')
        self.assertEqual(self.calls(), [])
        self.assertEqual(destination.read_bytes(), b'keep existing bytes')
        destination.unlink()
        link = os.link
        def raced(source, target, **kwargs):
            Path(target).write_bytes(b'racing creator')
            return link(source, target, **kwargs)
        with patch('tuldok_client.os.link', side_effect=raced):
            receipt = self.workflow.collect_batch(self.manifest, self.output)
        self.assertEqual(receipt['items'][0]['error']['code'], 'conflict')
        self.assertEqual(destination.read_bytes(), b'racing creator')
        self.assertEqual(sum(row['path'] == BATCH_PATH for row in self.calls()), 1)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL and actual HTTP')
class BatchPublicationHTTPTests(unittest.TestCase):
    def test_exact_attached_publication_ref_uses_batch_and_original_run_remains_interrupted(self):
        from test_run_artifact_segments import ArtifactSegmentsHTTPTests
        fixture = ArtifactSegmentsHTTPTests('runTest')
        def cleanup():
            fixture.doCleanups()
            if hasattr(fixture, 'schema'):
                import psycopg
                with psycopg.connect(fixture.dsn, autocommit=True) as connection:
                    self.assertIsNone(connection.execute('SELECT to_regnamespace(%s)', (fixture.schema,)).fetchone()[0])
                record_cleanup('publication', {'schema': fixture.schema, 'dropped': True})
        self.addCleanup(cleanup); fixture.setUp()
        client = AgentClient(fixture.endpoint, fixture.fixture.agent['token'], fixture.dataset.db.dataset_id)
        workflow = WorkflowClient(client)
        manifest = workflow.collection_manifest(result_ref=fixture.ref, names=['result.txt'])
        destination = fixture.fixture.path/'batch-publication'; destination.mkdir(mode=0o700)
        with patch('recipe_process.launch', side_effect=AssertionError('Batch publication replayed compute')):
            receipt = workflow.collect_batch(manifest, destination)
        self.assertEqual(receipt['state'], 'complete', receipt)
        self.assertEqual(receipt['items'][0]['receipt']['result_ref'], fixture.ref)
        self.assertEqual((destination/'result.txt').read_bytes(), fixture.fixture.input)
        self.assertEqual((destination/'result.txt').stat().st_mode & 0o777, 0o600)
        fixture.unchanged()


if __name__ == '__main__':
    unittest.main()
