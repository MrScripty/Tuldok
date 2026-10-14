"""PostgreSQL admission and real neutral external execution, not model acceptance.

Queue suppression is used only for admission/fault tests. Completion tests run the
production queue, trusted system interpreter, custodian and fixture descendant.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
import signal
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from access import AccessError
from app import Dataset
from auth_helpers import ExplicitOwnerFixture, execute_admitted
from metadata import CommitOutcomeUnknown
import recipe_process
from workbench import WorkbenchError


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ExternalCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.project_path = self.path / 'project'
        self.project_path.mkdir()
        self.source = Path(__file__).with_name('fixtures').joinpath('external_recipe.py').read_bytes()
        self.input = b'Neutral execution input: Unicode \xce\bb and exact bytes\x00\xff\n'
        self.definition = {
            'schema_version': 1, 'format': 'external_recipe_v1', 'id': 'neutral',
            'name': 'Neutral process qualification', 'version': 1, 'runtime': 'system_python',
            'sources': [{'path': 'recipe.py', 'sha256': sha(self.source)}],
            'entrypoint': 'recipe.py',
            'arguments': [{'parameter': 'mode'}, {'input': 'sample'}, {'output_dir': True}, {'parameter': 'note'}],
            'parameters': {'mode': {'type': 'string', 'default': 'complete',
                                    'enum': ['complete', 'sleep', 'nonzero'], 'max_length': 16},
                           'note': {'type': 'string', 'default': 'Unicode λ 😀', 'max_length': 32}},
            'inputs': {'sample': {'max_bytes': 4096}},
            'outputs': [{'path': 'result.txt', 'role': 'result', 'max_bytes': 4096, 'required': True}],
            'environment': {}, 'resources': {'wall_seconds': getattr(self, 'wall_seconds', 10), 'max_output_bytes': 16384}}
        self.definition_raw = json.dumps(self.definition).encode()
        self.manifest = {
            'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Neutral fixture; no scientific claim',
            'data': [{'id': 'sample', 'label': 'Exact input', 'path': 'input.bin', 'sha256': sha(self.input)}],
            'recipes': [{'id': 'neutral', 'label': 'Neutral executable definition',
                         'path': 'recipe.json', 'sha256': sha(self.definition_raw)}],
            'evidence': [], 'requirements': []}
        for name, raw in {'recipe.py': self.source, 'input.bin': self.input,
                          'recipe.json': self.definition_raw,
                          'project.json': json.dumps(self.manifest).encode()}.items():
            (self.project_path / name).write_bytes(raw)
        self.dataset = Dataset(self.path / 'catalog', project_roots={'fixture': self.project_path})
        self.addCleanup(lambda: self.dataset.close())
        self.owner = ExplicitOwnerFixture.bootstrap(self.dataset)
        with self.owner.bound(self.dataset):
            self.dataset.projects.open({'root': 'fixture', 'manifest_path': 'project.json'})
            self.agent = self.dataset.access.issue({'label': 'Approved submitter', 'scopes': ['inspect', 'execute']})
            self.other = self.dataset.access.issue({'label': 'Other submitter', 'scopes': ['inspect', 'execute']})
            self.graph = self.dataset.pipelines.create_external(self.graph_body())
            self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])

    def graph_body(self):
        return {'name': 'Neutral exact-byte execution', 'project_id': self.manifest['id'],
                'recipe_id': 'neutral', 'expected_sha256': sha(self.definition_raw),
                'inputs': {'sample': {'reference_id': 'sample', 'expected_sha256': sha(self.input)}}}

    def body(self, key=None, approval=None):
        body = {'request_key': key or 'neutral-request-' + uuid.uuid4().hex,
                'graph_id': self.graph['id'], 'graph_revision': self.graph['revision'],
                'expected_digest': self.preflight['material_sha256']}
        if approval is not None:
            body['approval_id'] = approval['id']
        return body

    def approve(self, actor=None):
        body = {key: value for key, value in self.body().items() if key != 'request_key'}
        body['consumer_actor_id'] = actor or self.agent['identity']['actor_id']
        with self.owner.bound(self.dataset):
            return self.dataset.runs.approve_external(body)

    def queued(self, body, token=None):
        with self.dataset.access.bind(token or self.agent['token']), patch.object(self.dataset.runs, '_start'):
            return self.dataset.runs.submit_external(body)

    def await_state(self, run_id, states, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.owner.bound(self.dataset):
                run = self.dataset.runs.get(run_id)
            if run['state'] in states:
                return run
            time.sleep(.05)
        self.fail(f'External run did not reach {states}: ' + repr({key: run.get(key) for key in ('id', 'state', 'custody_phase', 'progress', 'error')}))

    def reopen(self):
        self.dataset.close()
        self.dataset = Dataset(self.path / 'catalog', project_roots={'fixture': self.project_path})


class ExternalAdmissionTests(ExternalCase):
    def test_same_key_actor_and_digest_reconcile_exact_consumption(self):
        grant = self.approve()
        body = self.body(approval=grant)
        run = self.queued(body)
        self.assertEqual(self.queued(body)['id'], run['id'])
        for changed, token in ((dict(body, expected_digest='0' * 64), self.agent['token']),
                               (body, self.other['token'])):
            with self.subTest(token_actor='same' if token == self.agent['token'] else 'different'):
                with self.assertRaises((AccessError, WorkbenchError)) as error:
                    self.queued(changed, token)
                self.assertEqual(error.exception.code, 'conflict')
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.runs.list()), 1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_admissions WHERE kind=%s', ('runs',)).fetchone()[0], 1)
        self.assertEqual(run['execution_kind'], 'external_recipe')
        self.assertNotIn('release_id', run)
        self.assertEqual(run['material_sha256'], body['expected_digest'])
        with self.assertRaises((AccessError, WorkbenchError)):
            self.queued(self.body(approval=grant))

    def test_same_key_reconciles_after_approval_expiry_and_graph_drift(self):
        grant = self.approve()
        body = self.body(approval=grant)
        run = self.queued(body)
        with self.owner.bound(self.dataset), self.dataset.lock, self.dataset.db.transaction():
            self.dataset.db.execute('UPDATE access_execution_grants SET expires_at=%s WHERE id=%s',
                                    (int(time.time()) - 1, grant['id']))
        (self.project_path / 'recipe.py').write_bytes(self.source + b'\n# later owner edit\n')
        self.assertEqual(self.queued(body)['id'], run['id'])

    def test_same_boot_missing_drain_receipt_fences_after_go_intent(self):
        # Deliberately authored crash envelope tests conservative recovery only;
        # it is not evidence that a real process ran or drained.
        run = self.queued(self.body(approval=self.approve()))
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        with self.owner.bound(self.dataset), self.dataset.lock, self.dataset.db.transaction():
            retained = self.dataset.runs._load(run['id'])
            retained.update(state='running', custody_phase='go_intent', custody_identity={
                'attempt_id': retained['id'], 'request_sha256': retained['request_sha256'],
                'spec_sha256': sha(recipe_process.encoded(retained['spec'])), 'helper': {'pid': 2147483647, 'start_ticks': '1', 'boot_id': boot}})
            self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s',
                                    (json.dumps(retained), run['id']))
        self.reopen()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'unknown')
            self.assertTrue(self.dataset.runs._external_blocked)
        fresh = self.approve()
        with self.assertRaises(WorkbenchError) as error:
            self.queued(self.body(approval=fresh))
        self.assertEqual(error.exception.code, 'unavailable')
        self.assertEqual(self.queued(self.body(key=run['request_key'], approval={'id': run['approval_id']}))['id'], run['id'])

    def test_revocation_and_source_drift_leave_no_run_or_consumption(self):
        grant = self.approve()
        with self.owner.bound(self.dataset):
            self.dataset.access.revoke_execution(grant['id'])
        with self.assertRaises((AccessError, WorkbenchError)):
            self.queued(self.body(approval=grant))
        fresh = self.approve()
        (self.project_path / 'recipe.py').write_bytes(self.source + b'\n# changed after review\n')
        with self.assertRaises((AccessError, WorkbenchError)):
            self.queued(self.body(approval=fresh))
        # Atomic owner approval must also refuse an old reviewed digest.
        with self.assertRaises((AccessError, WorkbenchError)):
            self.queued(self.body(), self.owner.token)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 0)

    def test_consumption_and_run_rollback_together(self):
        grant = self.approve()
        body = self.body(approval=grant)
        consume = self.dataset.access._consume_external_run
        def consume_then_fail(*args, **kwargs):
            consume(*args, **kwargs)
            raise RuntimeError('Injected failure after real consumption, before commit.')
        with patch.object(self.dataset.access, '_consume_external_run', side_effect=consume_then_fail):
            with self.assertRaises(RuntimeError):
                self.queued(body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 0)
        self.assertEqual(self.queued(body)['state'], 'queued')

    def test_lost_ack_is_not_dispatched_by_an_already_running_queue(self):
        grant = self.approve()
        body = self.body(approval=grant)
        self.dataset.runs._start()
        self.assertTrue(self.dataset.runs._thread.is_alive())
        transaction = self.dataset.db.transaction
        @contextmanager
        def lose_ack(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            raise CommitOutcomeUnknown('Injected lost acknowledgement with a live queue.')
        with patch.object(self.dataset.db, 'transaction', side_effect=lose_ack):
            with self.assertRaises(CommitOutcomeUnknown):
                self.queued(body)
        with self.owner.bound(self.dataset):
            retained = self.dataset.runs.list()[0]
        self.assertNotIn(retained['id'], self.dataset.runs._confirmed_external)
        # Wake the actual shared queue repeatedly. The durable but unconfirmed
        # admission must remain behind the submission reconciliation boundary.
        until = time.monotonic() + .6
        while time.monotonic() < until:
            self.dataset.runs._wake.set()
            with self.owner.bound(self.dataset):
                current = self.dataset.runs.get(retained['id'])
            self.assertEqual(current['state'], 'queued')
            self.assertFalse((self.dataset.runs.path / ('.external-' + retained['id']) / 'custody').exists())
            time.sleep(.03)
        with self.dataset.access.bind(self.agent['token']):
            reconciled = self.dataset.runs.submit_external(body)
        self.assertEqual(reconciled['id'], retained['id'])
        terminal = self.await_state(retained['id'], {'completed', 'failed', 'unknown'})
        self.assertEqual(terminal['state'], 'completed', terminal)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)

    def test_lost_commit_ack_reconciles_without_new_approval(self):
        grant = self.approve()
        body = self.body(approval=grant)
        transaction = self.dataset.db.transaction
        @contextmanager
        def lose_ack(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            raise CommitOutcomeUnknown('Injected lost acknowledgement after real commit.')
        with patch.object(self.dataset.db, 'transaction', side_effect=lose_ack):
            with self.assertRaises(CommitOutcomeUnknown):
                self.queued(body)
        run = self.queued(body)
        self.assertEqual(run['approval_id'], grant['id'])
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.runs.list()), 1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)


class ExternalExecutionTests(ExternalCase):
    def test_unknown_go_commit_ack_never_sends_go_to_real_helper(self):
        import recipe_process
        run = self.queued(self.body(approval=self.approve()))
        transaction = self.dataset.db.transaction
        lost = []
        handles = []
        launch = recipe_process.launch
        def retain_handle(*args, **kwargs):
            handle = launch(*args, **kwargs)
            handles.append(handle)
            return handle
        @contextmanager
        def lose_go_ack(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            retained = self.dataset.runs._load(run['id'])
            if retained['custody_phase'] == 'go_intent' and not lost:
                lost.append(True)
                raise CommitOutcomeUnknown('Injected unknown GO-intent commit acknowledgement.')
        with patch('recipe_process.launch', side_effect=retain_handle), patch.object(
                recipe_process.Handle, 'go') as go, patch.object(
                self.dataset.db, 'transaction', side_effect=lose_go_ack):
            with self.assertRaises(CommitOutcomeUnknown):
                execute_admitted(self.dataset, run['id'])
            go.assert_not_called()
        self.assertTrue(lost)
        self.assertEqual(len(handles), 1)
        self.assertEqual(handles[0].process.wait(timeout=20), 0)
        receipt = recipe_process.load_receipt(handles[0].directory / 'receipt.json',
                                              handles[0].expected_identity)
        self.assertTrue(receipt['drained'])
        self.assertTrue(receipt['echild'])
        self.assertFalse(receipt['go_received'])
        self.assertNotEqual(receipt['outcome'], 'completed')
        self.assertFalse(Path(handles[0].spec['output_dir'], 'result.txt').exists())
        self.reopen()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')

    def test_real_running_cancel_retains_consumed_approval(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'][1]['parameters']['mode'] = 'sleep'
        with self.owner.bound(self.dataset):
            self.graph = self.dataset.pipelines.save(graph['id'],
                {'revision': graph['revision'], 'document': graph})
            self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
        grant = self.approve()
        body = self.body(approval=grant)
        with self.dataset.access.bind(self.agent['token']):
            run = self.dataset.runs.submit_external(body)
        end = time.monotonic() + 15
        while time.monotonic() < end:
            with self.owner.bound(self.dataset):
                current = self.dataset.runs.get(run['id'])
            if current['progress']['stage'] == 'execute':
                break
            self.assertIn(current['state'], ('queued', 'running'), current)
            time.sleep(.03)
        else:
            self.fail('Real helper did not reach the committed execution barrier.')
        with self.owner.bound(self.dataset):
            self.dataset.runs.cancel(run['id'])
        terminal = self.await_state(run['id'], {'cancelled', 'failed', 'unknown'})
        self.assertEqual(terminal['state'], 'cancelled', terminal)
        self.assertEqual(terminal['artifacts'], [])
        self.assertEqual(terminal['custody_phase'], 'drained')
        with self.assertRaises((AccessError, WorkbenchError)):
            self.queued(self.body(approval=grant))

    def test_real_unicode_parameter_descendant_output_cold_download_and_restart(self):
        body = self.body(approval=self.approve())
        with self.dataset.access.bind(self.agent['token']):
            run = self.dataset.runs.submit_external(body)
        complete = self.await_state(run['id'], {'completed', 'failed', 'unknown'})
        self.assertEqual(complete['state'], 'completed', complete)
        self.assertTrue(complete['artifacts'])
        receipt = json.loads((self.dataset.runs.path / run['id'] / 'custody-receipt.json').read_bytes())
        self.assertTrue(receipt['go_received'])
        self.assertTrue(receipt['drained'])
        self.assertTrue(receipt['echild'])
        artifact = next(item for item in complete['artifacts'] if item['name'] == 'result.txt')
        self.assertEqual(artifact['sha256'], sha(self.input))
        self.assertEqual(artifact['bytes'], len(self.input))
        with self.owner.bound(self.dataset):
            raw, _ = self.dataset.runs.artifact(run['id'], artifact['name'])
        self.assertEqual(raw, self.input)
        self.reopen()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'completed')
            self.assertEqual(self.dataset.runs.artifact(run['id'], artifact['name'])[0], self.input)
        self.assertEqual((self.project_path / 'recipe.py').read_bytes(), self.source)
        self.assertEqual((self.project_path / 'input.bin').read_bytes(), self.input)
        # A retained completion label does not permit a corrupted cold artifact.
        destination = self.dataset.runs.path / run['id'] / artifact['name']
        destination.write_bytes(b'corrupted after completion')
        with self.owner.bound(self.dataset):
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.artifact(run['id'], artifact['name'])
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.get(run['id'])
            unavailable = next(item for item in self.dataset.runs.list() if item['id'] == run['id'])
            self.assertEqual(unavailable['artifact_status']['status'], 'unavailable')



class ExternalStoppedHelperTests(ExternalCase):
    wall_seconds = 1

    def test_stopped_real_helper_deadline_is_unknown_until_actual_drain(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'][1]['parameters']['mode'] = 'sleep'
        with self.owner.bound(self.dataset):
            self.graph = self.dataset.pipelines.save(graph['id'],
                {'revision': graph['revision'], 'document': graph})
            self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
        body = self.body(approval=self.approve())
        handles = []
        stopped = threading.Event()
        launch, go = recipe_process.launch, recipe_process.Handle.go
        def retain_handle(*args, **kwargs):
            handle = launch(*args, **kwargs)
            handles.append(handle)
            return handle
        def go_then_stop(handle, identity):
            go(handle, identity)
            os.kill(handle.process.pid, signal.SIGSTOP)
            stopped.set()
        try:
            with patch('recipe_process.launch', side_effect=retain_handle), patch.object(
                    recipe_process.Handle, 'go', go_then_stop):
                with self.dataset.access.bind(self.agent['token']):
                    run = self.dataset.runs.submit_external(body)
                self.assertTrue(stopped.wait(15), 'Real helper never passed GO.')
                terminal = self.await_state(run['id'], {'unknown', 'failed', 'completed'}, timeout=45)
                self.assertEqual(terminal['state'], 'unknown')
                self.assertEqual(terminal['artifacts'], [])
                self.assertTrue(self.dataset.runs._external_blocked)
                with self.assertRaises(WorkbenchError):
                    self.queued(self.body(approval=self.approve()))
        finally:
            for handle in handles:
                # This is the still-unreaped Popen child; never kill the helper
                # and abandon its descendants during test cleanup.
                if handle.process.poll() is None:
                    os.kill(handle.process.pid, signal.SIGCONT)
                handle.close_control()
                handle.process.wait(timeout=15)
        self.assertEqual(len(handles), 1)
        receipt = recipe_process.load_receipt(handles[0].directory / 'receipt.json',
                                              handles[0].expected_identity)
        self.assertTrue(receipt['drained'])
        self.assertTrue(receipt['echild'])
        self.reopen()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')
            self.assertFalse(self.dataset.runs._external_blocked)


if __name__ == '__main__':
    unittest.main()
