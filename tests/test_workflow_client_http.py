"""Real authenticated HTTP + separate consumer/CLI processes; neutral byte custody.

Reply-loss/corruption faults are injected only after actual HTTP delivery. They
are consumer failure witnesses, not model quality or new runtime qualification.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql

from agent_api import AgentAPIError, AgentClient
from metadata import connection_info, CommitOutcomeUnknown
from test_agent_http import AgentHTTPCase
from tuldok_client import WorkflowClient

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL and actual HTTP')
class WorkflowHTTPTests(AgentHTTPCase):
    wall_seconds = 60  # Separate CLI bootstrap must fit before explicit cancel.

    def setUp(self):
        super().setUp()
        self.agent = self.issue_http(['inspect', 'edit', 'execute', 'cancel'])
        self.client = AgentClient(self.root, self.agent['token'], self.dataset.db.dataset_id, timeout=20)
        self.workflow = WorkflowClient(self.client)
        self.config = self.path/'consumer.json'
        token = self.path/'consumer.token'
        token.write_text(self.agent['token']); token.chmod(0o600)
        self.config.write_text(json.dumps({'endpoint': self.root, 'catalog_id': self.client.catalog_id,
                                         'token_file': str(token), 'timeout': 20}))
        self.config.chmod(0o600)
        self.addCleanup(self.drop_fresh_schema)

    def drop_fresh_schema(self):
        # The fixture created this catalog identity in its fresh temporary path.
        schema = self.dataset.db.schema
        self.stop_server()
        self.dataset.close()
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def file(self, name, value):
        path = self.path/name
        path.write_text(json.dumps(value)); path.chmod(0o600)
        return path

    def cli(self, *arguments, expected=0):
        result = subprocess.run([sys.executable, str(ROOT/'project_cli.py'), '--config', str(self.config),
                                 *map(str, arguments)], capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn(self.agent['token'], result.stdout + result.stderr)
        return json.loads(result.stdout or result.stderr)

    def submission_manifest(self, key='workflow-http-stable'):
        grant = self.approve()
        return self.workflow.submission_manifest(self.graph['id'], self.graph['revision'],
            approval_id=grant['id'], request_key=key)

    def completed(self):
        submitted = self.workflow.submit(self.submission_manifest())
        self.assertEqual(submitted['state'], 'acknowledged', submitted)
        run = submitted['envelope']['result']
        terminal = self.workflow.monitor(run['id'], timeout=40, interval=.02, max_interval=.1)
        self.assertEqual(terminal['state'], 'terminal', terminal)
        self.assertEqual(terminal['run']['state'], 'completed', terminal)
        return terminal['run']

    def counts(self):
        with self.owner.bound(self.dataset):
            return (len(self.dataset.runs.list()),
                self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0])

    def test_clean_cli_exports_submits_monitors_and_collects_selected_neutral_result(self):
        grant = self.approve()
        arguments = ('submission-manifest', '--graph-id', self.graph['id'], '--revision', self.graph['revision'],
                     '--approval-id', grant['id'], '--request-key', 'clean-cli-neutral-request')
        manifest = self.cli(*arguments)
        self.assertEqual(manifest, self.cli(*arguments))
        self.assertEqual(manifest['arguments']['expected_digest'], self.preflight['material_sha256'])
        self.assertNotIn(self.agent['token'], json.dumps(manifest))
        path = self.file('submission.json', manifest)
        submitted = self.cli('submit-workflow', '--manifest', path)
        self.assertEqual(submitted['state'], 'acknowledged')
        run_id = submitted['envelope']['result']['id']
        result = self.cli('monitor', '--run-id', run_id, '--timeout', 40)
        self.assertEqual(result['run']['state'], 'completed', result)
        self.assertEqual(self.cli('submit-workflow', '--manifest', path)['envelope']['result']['id'], run_id)
        manifest = self.cli('collection-manifest', '--run-id', run_id, '--name', 'result.txt')
        self.assertEqual(manifest['items'][0]['sha256'], hashlib.sha256(self.input).hexdigest())
        destination = self.path/'collected'; destination.mkdir(mode=0o700)
        receipt = self.cli('collect', '--manifest', self.file('collection.json', manifest), '--directory', destination)
        self.assertEqual(receipt['state'], 'complete')
        self.assertEqual((destination/'result.txt').read_bytes(), self.input)
        self.assertEqual((destination/'result.txt').stat().st_mode & 0o777, 0o600)
        resumed = self.cli('collect', '--manifest', self.path/'collection.json', '--directory', destination,
                           '--resume', self.file('collection-receipt.json', receipt))
        self.assertEqual(resumed['state'], 'complete')
        self.assertEqual(self.counts(), (1, 1))
        # Existing commands and frozen consumer use this same real saved Run.
        self.assertEqual(self.cli('status', '--run-id', run_id)['state'], 'completed')
        self.assertEqual(self.cli('submit', '--arguments', self.file('old-submission.json',
            submitted['manifest']['arguments']))['id'], run_id)
        old_download = self.path/'old-command-download.bin'
        old_receipt = self.cli('download', '--run-id', run_id, '--name', 'result.txt',
            '--expected-sha256', manifest['items'][0]['sha256'], '--out', old_download)
        self.assertEqual(old_receipt['verification'], 'whole_sha256_verified')
        self.assertEqual(old_download.read_bytes(), self.input)
        from test_agent_negotiation import LEGACY
        old_client = LEGACY.AgentClient(self.root, self.agent['token'], self.client.catalog_id)
        self.assertEqual(old_client.call('runs.get', {'run_id': run_id})['result']['state'], 'completed')
        frozen = old_client.call('runs.artifact_chunk', {'run_id': run_id, 'name': 'result.txt',
            'expected_sha256': manifest['items'][0]['sha256'], 'offset': 0, 'max_bytes': 7})
        self.assertEqual(frozen['status'], 200)
        self.assertEqual(base64.b64decode(frozen['result']['data_base64']), self.input[:7])
        self.assertEqual(self.counts(), (1, 1))
        # The neutral recipe has no evidence profile; comparison cannot invent one.
        unsupported = self.cli('comparison-manifest', '--run-id', run_id, '--other-run-id', run_id,
            '--checkpoint-sha256', 'a'*64, '--other-checkpoint-sha256', 'a'*64, '--metric-id', 'loss', expected=1)
        self.assertEqual(unsupported['code'], 'unsupported')

    def test_lost_successful_submit_reply_reconciles_same_identity_and_conflict_never_admits_again(self):
        manifest = self.submission_manifest('http-lost-submit-reply')
        self.client.bootstrap()
        request = self.client._request
        delivered = []
        def lost_reply(method, path, body=None, **kwargs):
            reply = request(method, path, body, **kwargs)
            if path == '/api/workspace/runs/submit-external':
                delivered.append(copy.deepcopy(body))
                self.assertLess(reply['status'], 400)
                raise AgentAPIError('Injected lost successful admission reply.', 'transport', 503)
            return reply
        with patch.object(self.client, '_request', side_effect=lost_reply):
            unknown = self.workflow.submit(manifest)
        self.assertEqual(unknown['state'], 'unknown')
        self.assertEqual(len(delivered), 1)
        self.assertEqual(self.counts(), (1, 1))
        # Reconciliation is a distinct explicit CLI action using the saved receipt.
        reconciled = self.cli('reconcile-submission', '--manifest', self.file('unknown.json', unknown))
        self.assertEqual(reconciled['state'], 'acknowledged')
        self.assertEqual(reconciled['manifest'], manifest)
        run_id = reconciled['envelope']['result']['id']
        self.assertEqual(self.workflow.monitor(run_id, timeout=40)['run']['state'], 'completed')
        changed = dict(manifest['arguments'], expected_digest='0'*64)
        refused = self.client.call('runs.submit_external', changed)
        self.assertEqual((refused['status'], refused['result']['code']), (409, 'conflict'))
        self.assertEqual(self.counts(), (1, 1))

    def test_actual_http_commit_unknown_then_revoked_reconciliation_stays_unknown(self):
        manifest = self.submission_manifest('http-committed-but-uncertain')
        submit = self.dataset.runs.submit_external
        committed = []
        def commit_then_lose(body, **kwargs):
            run = submit(body, **kwargs)
            committed.append(run['id'])
            raise CommitOutcomeUnknown('Injected uncertainty after successful real admission commit.')
        with patch.object(self.dataset.runs, 'submit_external', side_effect=commit_then_lose):
            unknown = self.workflow.submit(manifest)
        self.assertEqual((unknown['state'], unknown['error']['code']), ('unknown', 'commit_unknown'))
        self.assertEqual(len(committed), 1)
        self.assertEqual(self.counts(), (1, 1))
        self.await_state(committed[0], {'completed'})
        self.assertEqual(self.http('/api/access/credentials/' + self.agent['identity']['credential_id'] + '/revoke',
                                  {}, self.owner.token)[0], 200)
        current = self.cli('reconcile-submission', '--manifest', self.file('unknown-committed.json', unknown), expected=1)
        self.assertEqual(current['state'], 'unknown')
        self.assertEqual(current['manifest'], manifest)
        self.assertEqual(current['error']['code'], 'commit_unknown')
        self.assertEqual(current['reconciliation']['error']['code'], 'unauthenticated')
        self.assertEqual(self.counts(), (1, 1))

    def test_real_segment_interruption_resume_whole_hash_and_atomic_no_clobber(self):
        run = self.completed()
        manifest = self.workflow.collection_manifest(run_id=run['id'], names=['result.txt'])
        destination = self.path/'results'; destination.mkdir(mode=0o700)
        request = self.client._request
        offsets = []
        def interrupt(method, path, body=None, **kwargs):
            if '/artifact-segment/' in path:
                offsets.append(body['offset'])
                if len(offsets) == 2:
                    raise AgentAPIError('Injected interruption after one delivered segment.', 'transport', 503)
            return request(method, path, body, **kwargs)
        with patch.object(self.client, '_request', side_effect=interrupt):
            first = self.workflow.collect(manifest, destination, chunk_bytes=7)
        self.assertEqual(offsets, [0, 7])
        self.assertEqual(first['items'][0]['error']['code'], 'transport')
        self.assertEqual(list(destination.iterdir()), [])
        offsets.clear()
        def observe(method, path, body=None, **kwargs):
            if '/artifact-segment/' in path:
                offsets.append(body['offset'])
            return request(method, path, body, **kwargs)
        with patch.object(self.client, '_request', side_effect=observe):
            resumed = self.workflow.collect(manifest, destination, resume=first, chunk_bytes=7)
        self.assertEqual(resumed['state'], 'complete')
        self.assertEqual(offsets[0], 0)
        self.assertEqual((destination/'result.txt').read_bytes(), self.input)
        race_dir = self.path/'race'; race_dir.mkdir()
        link = os.link
        def race(source, target, **kwargs):
            Path(target).write_bytes(b'preserved concurrent work')
            return link(source, target, **kwargs)
        with patch('tuldok_client.os.link', side_effect=race):
            raced = self.workflow.collect(manifest, race_dir, chunk_bytes=7)
        self.assertEqual(raced['items'][0]['error']['code'], 'conflict')
        self.assertEqual((race_dir/'result.txt').read_bytes(), b'preserved concurrent work')
        corrupt_dir = self.path/'corrupt'; corrupt_dir.mkdir()
        def corrupt(method, path, body=None, **kwargs):
            reply = request(method, path, body, **kwargs)
            if '/artifact-segment/' in path and body['offset'] == 0:
                part = reply['result']
                raw = b'!' + base64.b64decode(part['data_base64'])[1:]
                part['data_base64'] = base64.b64encode(raw).decode('ascii')
                part['segment_sha256'] = hashlib.sha256(raw).hexdigest()
            return reply
        with patch.object(self.client, '_request', side_effect=corrupt):
            corrupted = self.workflow.collect(manifest, corrupt_dir, chunk_bytes=7)
        self.assertEqual(corrupted['items'][0]['error']['code'], 'artifact_mismatch')
        self.assertEqual(list(corrupt_dir.iterdir()), [])

    def test_denied_expired_revoked_grants_and_credential_have_no_effect_or_fallback(self):
        grant = self.approve()
        manifest = self.workflow.submission_manifest(self.graph['id'], self.graph['revision'],
            approval_id=grant['id'], request_key='expired-client-grant')
        with self.owner.bound(self.dataset):
            self.dataset.db.execute('UPDATE access_execution_grants SET expires_at=%s WHERE id=%s', (1, grant['id']))
        expired = self.workflow.submit(manifest)
        self.assertEqual(expired['state'], 'refused')
        self.assertEqual(self.counts(), (0, 0))
        revoked_grant = self.approve()
        with self.owner.bound(self.dataset):
            self.dataset.access.revoke_execution(revoked_grant['id'])
        manifest = self.workflow.submission_manifest(self.graph['id'], self.graph['revision'],
            approval_id=revoked_grant['id'], request_key='revoked-client-grant')
        self.assertEqual(self.workflow.submit(manifest)['state'], 'refused')
        inspector = self.issue_http(['inspect'])
        denied = WorkflowClient(AgentClient(self.root, inspector['token'], self.client.catalog_id))
        manifest = self.submission_manifest('insufficient-scope-client')
        refusal = denied.submit(manifest)
        self.assertEqual((refusal['state'], refusal['envelope']['status']), ('refused', 403))
        self.assertEqual(self.counts(), (0, 0))
        self.client.bootstrap()
        self.assertEqual(self.http('/api/access/credentials/' + self.agent['identity']['credential_id'] + '/revoke',
                                  {}, self.owner.token)[0], 200)
        with patch.object(self.client, '_request', wraps=self.client._request) as requests:
            refused = self.workflow.submit(manifest)
        self.assertEqual((refused['state'], refused['envelope']['status']), ('refused', 401))
        self.assertEqual(requests.call_count, 1)
        self.assertEqual(self.counts(), (0, 0))

    def test_collection_event_interrupts_actual_blocked_segment_and_cleans_provisional(self):
        run = self.completed()
        manifest = self.workflow.collection_manifest(run_id=run['id'], names=['result.txt'])
        destination = self.path/'stopped-artifact'; destination.mkdir(mode=0o700)
        handler = self.server.RequestHandlerClass
        original_post = handler.do_POST
        entered, release, stop = threading.Event(), threading.Event(), threading.Event()
        requests = []
        def blocked(instance):
            if '/artifact-segment/' in instance.path:
                requests.append(instance.path)
                entered.set(); release.wait(10)
            try:
                original_post(instance)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def cancel_after_enter():
            if entered.wait(10):
                stop.set()
        trigger = threading.Thread(target=cancel_after_enter)
        trigger.start()
        started = time.monotonic()
        try:
            with patch.object(handler, 'do_POST', blocked):
                receipt = self.workflow.collect(manifest, destination, cancelled=stop, chunk_bytes=7)
        finally:
            release.set(); trigger.join(5)
        self.assertTrue(entered.is_set())
        self.assertEqual(receipt['state'], 'stopped')
        self.assertEqual(receipt['items'][0]['error']['code'], 'stopped')
        self.assertEqual(len(requests), 1)
        self.assertLess(time.monotonic()-started, 2)
        self.assertEqual(list(destination.iterdir()), [])
        self.assertFalse(any(thread.name == 'agent-read-budget' for thread in threading.enumerate()))
        resumed = self.workflow.collect(manifest, destination, resume=receipt, chunk_bytes=7)
        self.assertEqual(resumed['state'], 'complete')
        self.assertEqual((destination/'result.txt').read_bytes(), self.input)
        self.assertEqual(self.counts(), (1, 1))

    def test_cancelled_resume_cannot_complete_with_corrupt_unvisited_prior_success(self):
        source = ("from pathlib import Path\nimport sys\n"
            "raw=Path(sys.argv[2]).read_bytes(); out=Path(sys.argv[3])\n"
            "out.joinpath('one.bin').write_bytes(raw); out.joinpath('two.bin').write_bytes(raw)\n").encode()
        self.definition['sources'][0]['sha256'] = hashlib.sha256(source).hexdigest()
        self.definition['outputs'] = [{'path': name, 'role': 'result', 'max_bytes': 4096, 'required': True}
                                      for name in ('one.bin', 'two.bin')]
        self.definition_raw = json.dumps(self.definition).encode()
        self.manifest['id'] = uuid.uuid4().hex
        self.manifest['recipes'][0]['sha256'] = hashlib.sha256(self.definition_raw).hexdigest()
        for name, raw in {'recipe.py': source, 'recipe.json': self.definition_raw,
                          'project.json': json.dumps(self.manifest).encode()}.items():
            (self.project_path/name).write_bytes(raw)
        with self.owner.bound(self.dataset):
            self.dataset.projects.open({'root': 'fixture', 'manifest_path': 'project.json'})
            self.graph = self.dataset.pipelines.create_external(self.graph_body())
            self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
        run = self.completed()
        manifest = self.workflow.collection_manifest(run_id=run['id'], names=['one.bin', 'two.bin'])
        destination = self.path/'resume-prior'; destination.mkdir(mode=0o700)
        prior = self.workflow.collect(manifest, destination, chunk_bytes=7)
        self.assertEqual(prior['state'], 'complete')
        (destination/'two.bin').write_bytes(b'corrupt local bytes retained for inspection')
        stop = threading.Event()
        from tuldok_client import _verified_local
        def stop_after_first(path, item):
            _verified_local(path, item)
            stop.set()
        with patch('tuldok_client._verified_local', side_effect=stop_after_first):
            current = self.workflow.collect(manifest, destination, resume=prior, cancelled=stop)
        self.assertEqual(current['state'], 'stopped')
        self.assertEqual(current['items'][1], prior['items'][1])
        refused = self.workflow.collect(manifest, destination, resume=current)
        self.assertEqual(refused['state'], 'partial')
        self.assertEqual(refused['items'][1]['error']['code'], 'artifact_mismatch')
        (destination/'two.bin').rename(destination/'two-corrupt-kept.bin')
        completed = self.workflow.collect(manifest, destination, resume=refused, chunk_bytes=7)
        self.assertEqual(completed['state'], 'complete')
        self.assertEqual((destination/'two.bin').read_bytes(), self.input)
        self.assertEqual((destination/'two-corrupt-kept.bin').read_bytes(), b'corrupt local bytes retained for inspection')
        self.assertEqual(self.counts(), (1, 1))

    def test_cold_monitor_deadline_and_cancellation_cooperate_during_registry_validation(self):
        # A fresh consumer process includes first validator import/registry work.
        code = """
import json, sys, threading, time
from tuldok_client import WorkflowClient
workflow = WorkflowClient.from_config(sys.argv[1])
stop = threading.Event()
if sys.argv[2] == 'cancel':
 timer = threading.Timer(.05, stop.set); timer.start()
else:
 timer = None
started = time.monotonic()
result = workflow.monitor('a'*32, timeout=.05 if timer is None else 20, cancelled=stop)
if timer is not None: timer.join()
assert not workflow.client._ready
assert not any(t.name == 'agent-read-budget' for t in threading.enumerate())
print(json.dumps(dict(result, elapsed=time.monotonic()-started)))
"""
        for mode in ('deadline', 'cancel'):
            result = subprocess.run([sys.executable, '-c', code, str(self.config), mode], cwd=ROOT,
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            observed = json.loads(result.stdout)
            self.assertEqual(observed['state'], 'deadline' if mode == 'deadline' else 'stopped')
            self.assertFalse(observed['compute_cancel_requested'])
            self.assertEqual(observed['reads'], 0)
            # Local validator import/schema pair is cooperative, not real time.
            self.assertLess(observed['elapsed'], 10)
        self.assertEqual(self.counts(), (0, 0))

    def test_delayed_actual_bootstrap_shares_deadline_and_blocked_read_observes_event(self):
        handler = self.server.RequestHandlerClass
        original_get = handler.do_GET
        paths = []
        release = threading.Event()
        def delayed(instance):
            if instance.path in ('/api/access/session', '/api/workspace/context', '/api/agent/capabilities'):
                paths.append(instance.path)
                release.wait(4)
            try:
                original_get(instance)
            except (BrokenPipeError, ConnectionResetError):
                pass
        started = time.monotonic()
        try:
            with patch.object(handler, 'do_GET', delayed):
                result = self.workflow.monitor('a'*32, timeout=12)
        finally:
            release.set()
        self.assertEqual(result['state'], 'deadline')
        self.assertGreaterEqual(len(paths), 2, paths)
        self.assertLess(time.monotonic()-started, 14)
        self.assertFalse(any(thread.name == 'agent-read-budget' for thread in threading.enumerate()))
        self.assertEqual(self.counts(), (0, 0))
        # A separate ready client exercises a socket blocked in a real Run read.
        client = AgentClient(self.root, self.agent['token'], self.client.catalog_id, timeout=20)
        client.bootstrap()
        stop, entered, release_read = threading.Event(), threading.Event(), threading.Event()
        def blocked(instance):
            if instance.path == '/api/workspace/runs/' + 'a'*32:
                entered.set(); release_read.wait(10)
            try:
                original_get(instance)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def cancel_after_read():
            if entered.wait(10):
                stop.set()
        trigger = threading.Thread(target=cancel_after_read)
        trigger.start()
        started = time.monotonic()
        try:
            with patch.object(handler, 'do_GET', blocked):
                result = WorkflowClient(client).monitor('a'*32, timeout=15, cancelled=stop)
        finally:
            release_read.set(); trigger.join(5)
        self.assertTrue(entered.is_set())
        self.assertEqual(result['state'], 'stopped')
        self.assertLess(time.monotonic()-started, 2)
        self.assertFalse(any(thread.name == 'agent-read-budget' for thread in threading.enumerate()))
        self.assertEqual(self.counts(), (0, 0))

    def test_monitor_stop_and_deadline_leave_compute_then_explicit_cancel_drains(self):
        with self.owner.bound(self.dataset):
            graph = self.dataset.pipelines.create_external(dict(self.graph_body(), parameters={'mode': 'sleep'}))
            self.graph = graph
            self.preflight = self.dataset.pipelines.preflight_external(graph['id'], graph['revision'])
        manifest = self.submission_manifest('monitor-cancel-neutral')
        run = self.workflow.submit(manifest)['envelope']['result']
        self.await_state(run['id'], {'running'})
        deadline = self.cli('monitor', '--run-id', run['id'], '--timeout', .02, expected=1)
        self.assertEqual(deadline['state'], 'deadline')
        self.assertFalse(deadline['compute_cancel_requested'])
        stop = threading.Event(); stop.set()
        stopped = self.workflow.monitor(run['id'], cancelled=stop)
        self.assertEqual(stopped['state'], 'stopped')
        current = self.client.call('runs.get', {'run_id': run['id']})['result']
        self.assertEqual(current['state'], 'running')
        cancellation = self.cli('cancel-workflow', '--run-id', run['id'])
        self.assertIn(cancellation['state'], ('requested', 'drained'))
        drained = self.workflow.monitor(run['id'], timeout=30, interval=.02, max_interval=.1)
        self.assertEqual((drained['run']['state'], drained['run']['custody_phase']), ('cancelled', 'drained'))
        self.assertEqual(self.workflow.cancel(run['id'])['state'], 'drained')
        self.assertEqual(self.counts(), (1, 1))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL and actual HTTP')
class RetainedWorkflowHTTPTests(unittest.TestCase):
    def serve(self, fixture):
        from app import make_handler
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(fixture.dataset))
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        def cleanup():
            server.shutdown(); server.server_close(); worker.join(5)
            schema = fixture.dataset.db.schema
            fixture.dataset.close()
            with psycopg.connect(connection_info(), autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        self.addCleanup(cleanup)
        return WorkflowClient(AgentClient('http://127.0.0.1:' + str(server.server_port),
            fixture.agent['token'], fixture.dataset.db.dataset_id))

    def test_retained_trial_manifest_delegates_actual_admission_and_reconciles_one_reservation(self):
        from test_experiments import StudyTests
        fixture = StudyTests('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        trial, _ = fixture.prepare(); fixture.open()
        grant = fixture.approve()
        workflow = self.serve(fixture)
        manifest = workflow.trial_submission_manifest(trial['id'], approval_id=grant['id'],
            request_key='consumer-trial-exact-once')
        self.assertEqual(manifest['operation'], 'studies.admit')
        self.assertEqual(manifest['arguments']['trial_id'], trial['id'])
        request = workflow.client._request
        def wrong_catalog(method, path, body=None, **kwargs):
            reply = request(method, path, body, **kwargs)
            if path.endswith('/admit') and reply['status'] < 400:
                reply = copy.deepcopy(reply)
                reply['result']['run']['dataset_id'] = '0'*32
            return reply
        with patch.object(workflow.client, '_request', side_effect=wrong_catalog):
            unknown = workflow.submit(manifest)
        self.assertEqual(unknown['state'], 'unknown', unknown)
        submitted = workflow.reconcile(unknown)
        self.assertEqual(submitted['state'], 'acknowledged', submitted)
        repeated = workflow.submit(json.loads(json.dumps(manifest)))
        self.assertEqual(repeated['state'], 'acknowledged', repeated)
        self.assertEqual(repeated['envelope']['result']['run']['id'], submitted['envelope']['result']['run']['id'])
        run_id = submitted['envelope']['result']['run']['id']
        terminal = workflow.monitor(run_id, timeout=40)
        self.assertEqual(terminal['run']['state'], 'completed', terminal)
        with fixture.owner.bound(fixture.dataset):
            self.assertEqual(fixture.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0], 1)
            self.assertEqual(fixture.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)
            self.assertEqual(fixture.dataset.db.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0], 1)

    def test_exact_attached_publication_collection_and_revocation_on_resume(self):
        from test_run_publication_recovery import PublicationRecoveryTests
        recovery = PublicationRecoveryTests('runTest')
        self.addCleanup(recovery.doCleanups)
        fixture, saved = recovery.failed_publication()
        with fixture.owner.bound(fixture.dataset), patch('recipe_process.launch', side_effect=AssertionError('Recovery replayed compute')):
            ref = fixture.dataset.runs.recover_publication(recovery.body(saved))['result_ref']
        workflow = self.serve(fixture)
        manifest = workflow.collection_manifest(result_ref=ref, names=['result.txt'])
        self.assertEqual(manifest['source'], {'ref': ref})
        destination = fixture.path/'consumer-publication'; destination.mkdir(mode=0o700)
        collected = workflow.collect(manifest, destination, chunk_bytes=7)
        self.assertEqual(collected['state'], 'complete', collected)
        self.assertEqual((destination/'result.txt').read_bytes(), fixture.input)
        self.assertEqual(collected['items'][0]['receipt']['result_ref'], ref)
        resumed = workflow.collect(manifest, destination, resume=collected, chunk_bytes=7)
        self.assertEqual(resumed['state'], 'complete')
        self.assertEqual(resumed['items'][0]['receipt']['result_ref'], ref)
        with fixture.owner.bound(fixture.dataset):
            fixture.dataset.access.revoke(fixture.agent['identity']['credential_id'])
        with patch.object(workflow.client, '_request', wraps=workflow.client._request) as requests:
            with self.assertRaises(AgentAPIError) as caught:
                workflow.collect(manifest, destination, resume=collected)
        self.assertEqual(caught.exception.status, 401)
        self.assertEqual(requests.call_count, 1)
        self.assertEqual((destination/'result.txt').read_bytes(), fixture.input)

    @unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'), 'Requires explicitly selected existing qualified CPU runtime')
    def test_actual_classifier_exact_operands_compare_through_http_and_clean_cli(self):
        # Reuse the existing tiny two-epoch CPU evidence fixture. This exercises
        # retained supported classifier comparison, not a new scientific claim.
        from test_model_evidence import ActualEvidenceTests
        class ConsumerEvidenceFixture(ActualEvidenceTests):
            pass
        ConsumerEvidenceFixture.setUpClass()
        fixture = ConsumerEvidenceFixture
        self.addCleanup(fixture.tearDownClass)
        with fixture.owner.bound(fixture.dataset):
            fixture.agent = fixture.dataset.access.issue({'label': 'Consumer exact comparison', 'scopes': ['inspect']})
        workflow = self.serve(fixture)
        run = fixture.completed_run
        points = fixture.evidence['checkpoint_index']['entries']
        manifest = workflow.comparison_manifest(run['id'], run['id'],
            checkpoint_sha256=points[0]['checkpoint']['sha256'],
            other_checkpoint_sha256=points[1]['checkpoint']['sha256'], metric_id='loss')
        args = manifest['arguments']
        self.assertEqual(args['checkpoint_sha256'], points[0]['checkpoint']['sha256'])
        self.assertEqual(args['other_checkpoint_sha256'], points[1]['checkpoint']['sha256'])
        self.assertEqual(args['metric_definition_sha256'], fixture.evidence['metric_definition_hashes']['loss'])
        compared = workflow.compare(manifest)
        self.assertEqual(compared['status'], 200, compared)
        self.assertEqual(compared['result']['state'], 'compatible')
        self.assertEqual([side['clocks']['epoch'] for side in compared['result']['sides']], [1, 2])
        directory = Path(fixture.temporary.name)
        token, config = directory/'consumer.token', directory/'consumer.json'
        token.write_text(fixture.agent['token']); token.chmod(0o600)
        config.write_text(json.dumps({'endpoint': 'http://127.0.0.1:' + str(workflow.client.port),
            'catalog_id': workflow.client.catalog_id, 'token_file': str(token)})); config.chmod(0o600)
        path = directory/'comparison.json'; path.write_text(json.dumps(manifest))
        def cli(*arguments):
            result = subprocess.run([sys.executable, str(ROOT/'project_cli.py'), '--config', str(config),
                *map(str, arguments)], capture_output=True, text=True, timeout=90)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(fixture.agent['token'], result.stdout + result.stderr)
            return json.loads(result.stdout)
        exported = cli('comparison-manifest', '--run-id', run['id'], '--other-run-id', run['id'],
            '--checkpoint-sha256', points[0]['checkpoint']['sha256'],
            '--other-checkpoint-sha256', points[1]['checkpoint']['sha256'], '--metric-id', 'loss')
        self.assertEqual(exported, manifest)
        self.assertEqual(cli('compare', '--manifest', path), compared)


if __name__ == '__main__':
    unittest.main()
