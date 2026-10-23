"""Current managed composition and admission; fixture assets never execute Torch.

Real Metadata/Projects/Model/Study/Trial/Run owners exercise static custody and
finite admission. A small ordinary native process supplies actual prior-Run
custody for the restore-input check. These are not pressure/GPU qualification.
"""
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
import uuid

import agent_api
from app import make_handler
from auth_helpers import execute_admitted
import recipe_contract
import recipe_process
import test_bound_torch_recipe_contract as bound_fixtures
import test_extension_bindings as model_fixtures
import test_external_runs as run_fixtures
import test_torch_runtime as runtime_fixtures
import torch_runtime
from torch_runtimes import TorchRuntimes
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires explicit isolated PostgreSQL')
class ManagedModelWorkflowTests(unittest.TestCase):
    setUp = bound_fixtures.BoundTorchRecipeContractTests.setUp
    write_project = bound_fixtures.BoundTorchRecipeContractTests.write_project
    inspect = bound_fixtures.BoundTorchRecipeContractTests.inspect
    managed = bound_fixtures.BoundTorchRecipeContractTests.managed
    body = model_fixtures.BoundExtensionRecipeTests.body

    def prepare_trial(self):
        self.managed()
        draft = self.models.create(self.body())
        self.published = self.models.publish(draft['id'], {'revision': 1})
        self.graph = self.dataset.pipelines.create_external({'name': 'Managed field custody fixture', **self.selector,
            'inputs': {'fixture': {'reference_id': 'fixture', 'expected_sha256': self.manifest['data'][0]['sha256']}}})
        self.policy = self.inspect()['selection_policy']
        self.study = self.dataset.studies.create({'name': 'Finite managed field fixture; no execution',
            'limits': {'attempt_slots': 1, 'admitted_wall_seconds': 2000,
                       'retained_bytes': 512*1024**2, 'peak_staging_bytes': 1024**3}, 'policy': self.policy})
        self.trial = self.dataset.studies.prepare_trial(self.study['id'],
            {'request_key': uuid.uuid4().hex, 'revision': self.study['revision'],
             'graph_id': self.graph['id'], 'graph_revision': self.graph['revision'],
             'model': self.published['ref'], 'replicate': 0})
        return self.dataset.pipelines.recipe_material(self.trial['material'], verify=True)

    def test_selected_inspection_accepts_exact_managed_provider_contract(self):
        self.managed()
        actor = self.dataset.access.issue({'label': 'Managed evidence inspector', 'scopes': ['inspect']})
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = agent_api.AgentClient(f'http://127.0.0.1:{server.server_port}', actor['token'], self.dataset.db.dataset_id)
            with patch('subprocess.Popen', side_effect=AssertionError('Inspection must not execute')):
                response = client.call('recipes.inspect', dict(project_id=self.selector['project_id'],
                    reference_id=self.selector['recipe_id'], expected_sha256=self.selector['expected_sha256']))
            self.assertEqual(response['status'], 200, response)
            self.assertEqual(response['result']['runtime'], torch_runtime.PROFILE)
            for item in response['result']['extension_binding']['contributions']:
                self.assertEqual(item['provider']['runtime']['profile'], torch_runtime.PROFILE)
        finally:
            server.shutdown(); server.server_close(); thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_trial_runtime_identity_and_budget_include_measured_managed_verification(self):
        with patch('subprocess.Popen', side_effect=AssertionError('Static Trial preparation must not execute')):
            composition = self.prepare_trial()
            preflight = self.dataset.pipelines.preflight_recipe_material(self.trial['material'])
        descriptor = preflight['material']['torch_runtime']
        identity = recipe_contract.digest(descriptor)
        self.assertEqual(composition['material']['runtime']['sha256'], identity)
        self.assertNotEqual(identity, recipe_contract.digest(preflight['runtime']))
        self.assertEqual(recipe_process.preparation_seconds(preflight['material']), recipe_process.TORCH_READY_SECONDS)
        self.assertEqual(recipe_process.verification_seconds(preflight['material']), recipe_process.TORCH_VERIFY_SECONDS)
        # READY preparation, acknowledged-owner GO waiting, and post-GO runtime
        # verification are separate bounded phases in the actual custodian.
        expected = (self.recipe['resources']['wall_seconds'] + recipe_process.TORCH_READY_SECONDS + 2
                    + recipe_process.GO_WAIT_SECONDS + recipe_process.TORCH_VERIFY_SECONDS + 15)
        self.assertEqual(composition['material']['resource_envelope']['admitted_wall_seconds'], expected)
        self.assertEqual(composition['material']['model'], self.published['ref'])
        self.assertEqual(self.dataset.runs.list(), [])

    def test_finite_admission_binds_exact_trial_model_runtime_and_readonly_context_once(self):
        self.prepare_trial()
        state = self.dataset.studies.get(self.study['id'])['study']
        self.dataset.studies.continue_study(state['id'], {'request_key': uuid.uuid4().hex,
            'revision': state['revision'], 'admission_epoch': state['admission_epoch']})
        actor = self.dataset.access.issue({'label': 'Exact managed Trial consumer', 'scopes': ['inspect', 'execute']})
        grant = self.dataset.studies.approve(self.study['id'], {'trial_id': self.trial['id'],
            'expected_material_sha256': self.trial['material']['sha256'], 'consumer_actor_id': actor['identity']['actor_id']})
        state = self.dataset.studies.get(self.study['id'])['study']
        body = {'request_key': uuid.uuid4().hex, 'revision': state['revision'],
                'admission_epoch': state['admission_epoch'], 'trial_id': self.trial['id'], 'approval_id': grant['id']}
        with self.dataset.access.bind(actor['token']), patch.object(self.dataset.runs, '_start'):
            admitted = self.dataset.studies.admit(self.study['id'], body)
            self.assertEqual(self.dataset.studies.admit(self.study['id'], body)['run']['id'], admitted['run']['id'])
        run = self.dataset.runs._load(admitted['run']['id'])
        recipe_process.validate_spec(run['spec'])
        context = run['extension_context']
        self.assertEqual(context['static']['model'], self.published['ref'])
        self.assertEqual(context['composition'], self.trial['material'])
        self.assertEqual(run['spec']['argv'][7], 'cuda')
        self.assertIn('torch_runtime', run['spec'])
        self.assertNotIn('cpu_snapshot', run['spec'])
        path = Path(run['spec']['model_evidence_context']['path'])
        self.assertEqual(path.read_bytes(), json.dumps(context,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
        self.assertEqual(path.stat().st_mode & 0o777, 0o400)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0], 1)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0], 1)
        self.dataset.runs.cancel(run['id'])

    def test_changed_measured_assets_refuse_grant_before_run_creation(self):
        self.prepare_trial()
        actor = self.dataset.access.issue({'label': 'Unavailable managed Trial consumer', 'scopes': ['inspect', 'execute']})
        (self.site / 'changed.py').write_bytes(b'changed after static preparation')
        with self.assertRaises(WorkbenchError):
            self.dataset.studies.approve(self.study['id'], {'trial_id': self.trial['id'],
                'expected_material_sha256': self.trial['material']['sha256'],
                'consumer_actor_id': actor['identity']['actor_id']})
        self.assertEqual(self.dataset.runs.list(), [])
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_grants').fetchone()[0], 0)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires explicit isolated PostgreSQL')
class CurrentManagedRestoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture = run_fixtures.ExternalCase('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.dataset, self.owner = self.fixture.dataset, self.fixture.owner
        runtime_fixtures.InstalledAssets.setUp(self)
        manifest = torch_runtime.inventory(self.config)
        self.identity = torch_runtime.sha(torch_runtime.encoded(manifest))
        with self.owner.bound(self.dataset):
            self.descriptor = TorchRuntimes(self.dataset.db,self.dataset.access,self.dataset.db.path).create(manifest,self.identity)

    def current_project(self):
        definition = copy.deepcopy(self.fixture.definition)
        definition.update(runtime=torch_runtime.PROFILE,runtime_device='cpu',runtime_snapshot_sha256=self.identity)
        raw = json.dumps(definition).encode()
        (self.fixture.project_path / 'recipe.json').write_bytes(raw)
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest.update(schema_version=2,extensions=[],id=uuid.uuid4().hex)
        manifest['recipes'][0]['sha256'] = hashlib.sha256(raw).hexdigest()
        (self.fixture.project_path / 'project.json').write_text(json.dumps(manifest))
        self.dataset.projects.register_snapshot({'root':'fixture','manifest_path':'project.json'})
        return dict(self.fixture.graph_body(),project_id=manifest['id'],expected_sha256=hashlib.sha256(raw).hexdigest())

    def test_ordinary_current_v2_cpu_restore_preserves_actual_run_artifact_custody_to_admission(self):
        original = self.fixture.queued(self.fixture.body(approval=self.fixture.approve()))
        execute_admitted(self.dataset, original['id'])
        completed = self.fixture.await_state(original['id'], {'completed','failed','unknown'})
        self.assertEqual(completed['state'], 'completed', completed)
        artifact = completed['artifacts'][0]
        with self.owner.bound(self.dataset):
            body = self.current_project()
            body['inputs'] = {'sample': {'kind':'run_artifact','run_id':completed['id'],
                'artifact_name':artifact['name'],'expected_sha256':artifact['sha256']}}
            graph = self.dataset.pipelines.create_external(body)
            preflight = self.dataset.pipelines.preflight_external(graph['id'],1)
            captured = self.dataset.pipelines.capture_external(graph['id'],1,preflight['material_sha256'],self.fixture.path/'restore-capture')
            receipt = captured['material']['inputs']['sample']['source']
            self.assertEqual(receipt['run_id'],completed['id'])
            self.assertEqual(receipt['measured_sha256'],artifact['sha256'])
            self.assertEqual((self.fixture.path/'restore-capture/input/sample').read_bytes(),self.fixture.input)
            self.assertEqual(captured['spec']['argv'][7],'cpu')
            self.assertNotIn('model_evidence_context',captured['spec'])
            grant = self.dataset.runs.approve_external({'graph_id':graph['id'],'graph_revision':1,
                'expected_digest':preflight['material_sha256'],'consumer_actor_id':self.owner.identity['actor_id']})
            with patch.object(self.dataset.runs,'_start'):
                admitted = self.dataset.runs.submit_external({'request_key':uuid.uuid4().hex,'graph_id':graph['id'],
                    'graph_revision':1,'expected_digest':preflight['material_sha256'],'approval_id':grant['id']})
            stored = self.dataset.runs._load(admitted['id'])
            self.assertEqual(stored['material']['inputs']['sample']['source'],receipt)
            recipe_process.validate_spec(stored['spec'])
            self.dataset.runs.cancel(stored['id'])

    def test_ordinary_current_source_capture_rejects_changed_manifest(self):
        with self.owner.bound(self.dataset):
            body = self.current_project()
            graph = self.dataset.pipelines.create_external(body)
            self.dataset.pipelines.preflight_external(graph['id'],1)
            path = self.fixture.project_path/'project.json'
            path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaises(WorkbenchError) as caught:
                self.dataset.pipelines.preflight_external(graph['id'],1)
            self.assertEqual(caught.exception.code,'stale')


if __name__ == '__main__':
    unittest.main()
