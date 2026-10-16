"""Actual HTTP bound-recipe inspection/refusal; no runtime or fabricated Run.

Compose the binding owner's fixture at runtime so its contract evolution is
shared, without inheriting or collecting that owner's test suite.
"""
import copy
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_api
from app import make_handler
from auth_helpers import ExplicitOwnerFixture
import recipe_contract
import test_extension_bindings as binding_fixture


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the extension validator')
class BoundExtensionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = binding_fixture.BoundExtensionRecipeTests('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.dataset = self.fixture.dataset
        self.owner = self.fixture.owner
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def http(self, path, *, version=2, token=None, header=None, body=None, operation='recipes.inspect'):
        headers = {'Authorization': 'Bearer ' + (self.owner.token if token is None else token)}
        if header is not None:
            headers[agent_api.CONTRACT_HEADER] = header
        elif version is not None:
            headers[agent_api.CONTRACT_HEADER] = agent_api.selected_header(operation, version)
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers['Content-Type'] = 'application/json'
        request = Request(self.base + path, data=data, headers=headers)
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def route(self, **query):
        selector = self.fixture.selector
        arguments = {'expected_sha256': selector['expected_sha256'], **query}
        return ('/api/workspace/projects/' + selector['project_id'] + '/recipes/'
                + selector['recipe_id'] + '?' + urlencode(arguments))

    def counts(self):
        tables = ('workspace_runs', 'access_execution_grants', 'access_execution_consumptions',
                  'model_attempt_reservations', 'model_trials', 'model_materials',
                  'model_definition_drafts', 'workspace_graphs', 'workspace_projects')
        return {table: self.dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in tables}

    def test_selected_v2_owner_returns_exact_closed_binding_without_execution(self):
        before = self.counts()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Inspection must be inert')):
            status, result = self.http(self.route())
        self.assertEqual(status, 200, result)
        self.assertEqual(set(result), {'definition', 'receipt', 'parameter_definitions', 'inputs',
                                       'outputs', 'runtime', 'extension_binding', 'model_task',
                                       'selection_policy'})
        self.assertEqual(result['definition'], self.fixture.recipe)
        binding = result['extension_binding']
        self.assertEqual(set(binding), {'format', 'project', 'schema_sha256', 'selections',
                                        'contributions', 'inventory'})
        self.assertEqual({item['kind'] for item in binding['contributions']},
                         {'task', 'model', 'trainer', 'evaluator', 'view'})
        self.assertEqual(binding['project']['id'], self.fixture.manifest['id'])
        self.assertEqual(result['model_task'], self.fixture.body()['task'])
        self.assertEqual(result['selection_policy']['numerical_acceptance'], 'diagnostic')
        for item in binding['contributions']:
            self.assertEqual(set(item['provider']), {'reference_id', 'id', 'version', 'sha256',
                                                     'runtime', 'effects', 'resources'})
            self.assertEqual(item['provider']['runtime'], self.fixture.extension['runtime'])
            self.assertEqual(item['provider']['effects'], self.fixture.extension['effects'])
            self.assertEqual(item['provider']['resources'], self.fixture.extension['resources'])
        agent_api.validate_output('recipes.inspect', {'status': status, 'result': result}, 2)
        bad = copy.deepcopy(result)
        bad['extension_binding']['blobs'] = {'producer.py': 'unselected source bytes'}
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.validate_output('recipes.inspect', {'status': 200, 'result': bad}, 2)
        self.assertEqual(agent_api.contract('recipes.inspect', 1)['sha256'],
                         '096de78ee573233201b14b6766e6267f6d2dff53904acc533f4a003cb2b973f8')
        self.assertEqual(agent_api.contract('recipes.inspect', 2)['sha256'],
                         'be0cfb596b3ae741e2903be57413684bac28e9fa3c59987086fde49e514284ea')
        self.assertEqual(self.counts(), before)

    def test_absent_or_legacy_selection_refuses_bound_projection_without_mutation(self):
        before = self.counts()
        for version in (None, 1):
            with self.subTest(version=version):
                status, result = self.http(self.route(), version=version)
                self.assertEqual((status, result['code']), (409, 'unsupported'))
                self.assertNotIn('extension_binding', result)
        self.assertEqual(self.counts(), before)

    def test_agent_owner_only_denial_and_current_credential_revocation(self):
        agent = self.dataset.access.issue({'label': 'Bound HTTP inspector',
                                            'scopes': ['inspect', 'edit', 'execute']})
        second_owner = ExplicitOwnerFixture.bootstrap(self.dataset)
        before = self.counts()
        status, result = self.http(self.route(), token=agent['token'])
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        self.assertNotIn('extension_binding', result)
        self.assertEqual(self.http(self.route(), token=second_owner.token)[0], 200)
        self.dataset.access.revoke(second_owner.identity['credential_id'])
        self.dataset.access.revoke(agent['identity']['credential_id'])
        for token in (second_owner.token, agent['token']):
            with self.subTest(revoked_actor=token == second_owner.token):
                status, result = self.http(self.route(), token=token)
                self.assertEqual((status, result['code']), (401, 'unauthenticated'))
                self.assertNotIn('extension_binding', result)
        self.assertEqual(self.counts(), before)

    def test_malformed_selection_and_selected_query_refuse_before_recipe_owner(self):
        before = self.counts()
        valid = agent_api.selected_header('recipes.inspect', 2)
        cases = [(self.route(), 'recipes.inspect/2/' + '0'*64, 409, 'contract_mismatch'),
                 (self.route(), valid + '/extra', 409, 'contract_mismatch'),
                 (self.route(), agent_api.selected_header('context.get'), 409, 'contract_mismatch'),
                 (self.route(contract_version='2'), valid, 409, 'contract_mismatch'),
                 (self.route(expected_sha256='wrong'), valid, 400, 'invalid'),
                 (self.route() + '&expected_sha256=' + 'a'*64, valid, 409, 'contract_mismatch')]
        with patch.object(self.dataset.pipelines, 'inspect_external_recipe',
                          wraps=self.dataset.pipelines.inspect_external_recipe) as inspect:
            for path, header, expected, code in cases:
                with self.subTest(path=path, header=header):
                    status, result = self.http(path, header=header)
                    self.assertEqual((status, result['code']), (expected, code), result)
            inspect.assert_not_called()
        self.assertEqual(self.counts(), before)

    def test_changed_source_provider_and_project_refuse_without_fallback(self):
        before = self.counts()
        paths = [(self.fixture.project / self.fixture.recipe['entrypoint'], 'unavailable'),
                 (self.fixture.project / 'provider.json', 'unavailable'),
                 (self.fixture.project / 'project.json', 'stale')]
        for path, code in paths:
            raw = path.read_bytes()
            try:
                path.write_bytes(raw + b'\n')
                with self.subTest(path=path.name):
                    status, result = self.http(self.route())
                    self.assertEqual((status, result['code']), (409, code), result)
                    self.assertNotIn('extension_binding', result)
            finally:
                path.write_bytes(raw)
            self.assertEqual(self.http(self.route())[0], 200)
        self.assertEqual(self.counts(), before)

    def test_unused_kind_input_preflight_refuses_before_input_capture_or_runtime(self):
        self.fixture.recipe['inputs']['unused'] = {'max_bytes': 64}
        self.fixture._rebind_definitions()
        data = self.fixture.manifest['data'][0]
        graphs = []
        for kind, binding in (
                ('run_artifact', {'kind': 'run_artifact', 'run_id': 'a'*32,
                                  'artifact_name': 'unused.bin', 'expected_sha256': 'b'*64}),
                ('frozen_release', {'kind': 'frozen_release', 'release_id': 'a'*64,
                                    'expected_sha256': 'b'*64})):
            status, graph = self.http('/api/workspace/graphs/external',
                operation='graphs.create_external', version=1,
                body={'name': 'Bound unused ' + kind, **self.fixture.selector,
                      'inputs': {'fixture': {'reference_id': data['id'], 'expected_sha256': data['sha256']},
                                 'unused': binding}})
            self.assertEqual(status, 201, graph)
            graphs.append(graph)
        before = self.counts()
        with patch.object(self.dataset.runs, 'capture_artifact') as capture, \
                patch.object(self.dataset.releases, 'capture_input') as release, \
                patch.object(self.dataset.projects, 'read_snapshot_data_reference') as data_read, \
                patch.object(recipe_contract, 'runtime_identity') as runtime:
            for graph in graphs:
                status, result = self.http('/api/workspace/graphs/' + graph['id'] + '/preflight-external',
                    operation='graphs.preflight_external', version=1, body={'revision': graph['revision']})
                self.assertEqual((status, result['code']), (409, 'unsupported'), result)
                self.assertIn('including unused inputs', result['error'])
            for call in (capture, release, data_read, runtime):
                call.assert_not_called()
        self.assertEqual(self.counts(), before)


if __name__ == '__main__':
    unittest.main()
