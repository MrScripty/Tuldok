"""Negotiated ordinary-agent snapshot authoring; real owners, no executed Run."""
import copy
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_api as api
from app import make_handler
import test_extension_bindings as fixtures
import test_extension_http as catalog_fixtures


class SnapshotRegistryTests(unittest.TestCase):
    def test_explicit_snapshot_contracts_preserve_the_installed_legacy_registry(self):
        self.assertEqual(api.discovery()['digest'],
            'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')
        self.assertFalse(any(item['operation_id'].startswith('project_snapshots.')
                             for item in api.discovery()['operations']))
        selected = api.negotiate(api.capabilities('b' * 32), 'b' * 32)
        for name in ('list', 'get', 'open'):
            self.assertEqual(selected['project_snapshots.' + name], 1)
        for name, version in (('recipes.inspect', 3), ('graphs.create_external', 2),
                ('graphs.preflight_external', 2), ('models.publish', 2),
                ('studies.prepare_trial', 2)):
            self.assertEqual(selected[name], version)

    def test_snapshot_arguments_are_closed_and_bounded(self):
        api.validate_arguments('project_snapshots.list', {'limit': 20})
        for arguments in ({'limit': 21}, {'limit': True}, {'cursor': '../escape'},
                          {'contract_version': 1}):
            with self.subTest(arguments=arguments), self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_snapshots.list', arguments)
        for arguments in ({'root': 'fixture', 'manifest_path': 'project.json', 'execute': True},
                          {'root': 'fixture'}):
            with self.subTest(arguments=arguments), self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_snapshots.open', arguments)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires isolated PostgreSQL and the extension validator')
class AgentSnapshotHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BoundExtensionRecipeTests('runTest')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.dataset, self.owner = self.fixture.dataset, self.fixture.owner
        self.agent = self.dataset.access.issue({'label': 'Ordinary snapshot author',
            'scopes': ['inspect', 'edit', 'execute']})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.client = api.AgentClient(self.base, self.agent['token'], self.dataset.db.dataset_id)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def counts(self):
        return {name: self.dataset.db.execute('SELECT count(*) FROM ' + name).fetchone()[0]
            for name in ('workspace_projects', 'model_definition_drafts', 'model_materials',
                'workspace_graphs', 'model_studies', 'model_trials', 'workspace_runs',
                'access_execution_grants', 'access_execution_consumptions', 'model_attempt_reservations')}

    def call(self, name, arguments, status=200):
        result = self.client.call(name, arguments)
        self.assertEqual(result['status'], status, result)
        return result['result']

    def http(self, name, arguments, *, version=None, token=None, selected=True):
        version = max(api._CONTRACTS[name]) if version is None else version
        method, route, body = api.project_request(name, arguments, version)
        headers = {'Authorization': 'Bearer ' + (token or self.agent['token'])}
        if selected:
            headers[api.CONTRACT_HEADER] = api.selected_header(name, version)
        raw = None if body is None else json.dumps(body).encode()
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        try:
            response = urlopen(Request(self.base + route, method=method, data=raw,
                                       headers=headers), timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def own_project(self):
        value = copy.deepcopy(self.fixture.manifest)
        value['id'] = uuid.uuid4().hex
        (self.fixture.project / 'agent-project.json').write_text(json.dumps(value))
        return self.call('project_snapshots.open',
            {'root': 'fixture', 'manifest_path': 'agent-project.json'}, 201)

    def graph_body(self):
        return {'name': 'Agent-authored bound graph', **self.fixture.selector,
                'inputs': {'fixture': {'reference_id': 'fixture',
                    'expected_sha256': self.fixture.manifest['data'][0]['sha256']}}}

    def test_agent_discovers_opens_and_inspects_exact_bound_source_without_execution(self):
        before = self.counts()
        source = {path: path.read_bytes() for path in self.fixture.project.rglob('*') if path.is_file()}
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Discovery must remain inert')):
            listing = self.call('project_snapshots.list', {'limit': 1})
            self.assertEqual(len(listing['projects']), 1)
            self.assertEqual(listing['projects'][0]['schema_version'], 2)
            project = self.call('project_snapshots.get', {'project_id': self.fixture.manifest['id']})
            self.assertEqual(project['schema_version'], 2)
            self.assertEqual(self.call('project_snapshots.open',
                {'root': 'fixture', 'manifest_path': 'project.json'}, 201), project)
            inspected = self.call('recipes.inspect',
                {'project_id': project['id'], 'reference_id': self.fixture.selector['recipe_id'],
                 'expected_sha256': self.fixture.selector['expected_sha256']})
            self.assertEqual(inspected['extension_binding']['project']['id'], project['id'])
            self.assertNotIn('blobs', inspected['extension_binding'])
        self.assertEqual(self.counts(), before)
        self.assertEqual(source, {path: path.read_bytes() for path in source})

    def test_new_agent_project_and_model_publication_use_normal_edit_owners(self):
        before = self.counts()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Static preparation must remain inert')):
            project = self.own_project()
            body = copy.deepcopy(self.fixture.body())
            body['source_selector']['project_id'] = project['id']
            draft = self.call('models.create', body, 201)
            material = self.call('models.publish', {'model_id': draft['id'], 'revision': 1})
            self.assertEqual(material['material']['source_selector']['project_id'], project['id'])
        after = self.counts()
        self.assertEqual(after['workspace_projects'], before['workspace_projects'] + 1)
        self.assertEqual(after['model_definition_drafts'], before['model_definition_drafts'] + 1)
        self.assertEqual(after['model_materials'], before['model_materials'] + 1)
        for name in ('workspace_runs', 'access_execution_grants',
                     'access_execution_consumptions', 'model_attempt_reservations', 'model_trials'):
            self.assertEqual(after[name], before[name])

    def test_selected_catalog_keeps_invalid_siblings_and_explicit_v1_shape(self):
        case = catalog_fixtures.ExtensionHTTPTests('runTest')
        self.addCleanup(case.doCleanups)
        case.setUp()
        actor = case.dataset.access.issue({'label':'Inert catalog agent','scopes':['inspect','edit']})
        client = api.AgentClient(case.base,actor['token'],case.dataset.db.dataset_id)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Catalog code must remain inert')):
            result = client.call('project_snapshots.open',case.body)
            self.assertEqual(result['status'],201,result)
            self.assertEqual([item['state'] for item in result['result']['extensions']['packages']],
                             ['valid','invalid','unavailable'])
            legacy = copy.deepcopy(case.value)
            legacy.update(schema_version=1,id=uuid.uuid4().hex)
            del legacy['extensions']
            (case.external/'legacy.json').write_text(json.dumps(legacy))
            result = client.call('project_snapshots.open',{'root':'fixture','manifest_path':'legacy.json'})
            self.assertEqual(result['status'],201,result)
            self.assertEqual(result['result']['schema_version'],1)
            self.assertNotIn('extensions',result['result'])
            ordinary = client.call('projects.get',{'project_id':legacy['id']})
            self.assertEqual(ordinary['status'],200)
            self.assertNotIn('schema_version',ordinary['result'])

    def test_old_snapshot_and_bound_recipe_contracts_keep_their_owner_boundary(self):
        before = self.counts()
        self.assertEqual(self.http('project_snapshots.list', {}, selected=False)[0], 403)
        for version in (1, 2):
            status, result = self.http('recipes.inspect',
                {'project_id': self.fixture.selector['project_id'],
                 'reference_id': self.fixture.selector['recipe_id'],
                 'expected_sha256': self.fixture.selector['expected_sha256']}, version=version)
            self.assertEqual((status, result['code']), (403, 'forbidden'))
        self.assertEqual(self.counts(), before)

    def test_old_static_versions_cannot_publish_or_prepare_bound_material(self):
        draft = self.call('models.create', self.fixture.body(), 201)
        before = self.counts()
        status, result = self.http('models.publish', {'model_id': draft['id'], 'revision': 1}, version=1)
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        status, result = self.http('graphs.create_external', self.graph_body(), version=1)
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        self.assertEqual(self.counts(), before)
        graph = self.call('graphs.create_external', self.graph_body(), 201)
        before = self.counts()
        status, result = self.http('graphs.preflight_external',
            {'graph_id': graph['id'], 'revision': graph['revision']}, version=1)
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        published = self.call('models.publish', {'model_id': draft['id'], 'revision': 1})
        study = self.dataset.studies.create({'name': 'Owner finite budget',
            'limits': dict(attempt_slots=1,admitted_wall_seconds=60,
                           retained_bytes=1048576,peak_staging_bytes=1048576),
            'policy': self.fixture.inspect(2)['selection_policy']})
        before = self.counts()
        status, result = self.http('studies.prepare_trial', {'study_id': study['id'],
            'request_key': uuid.uuid4().hex, 'revision': study['revision'],
            'graph_id': graph['id'], 'graph_revision': graph['revision'],
            'model': published['ref'], 'replicate': 0}, version=1)
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        status, result = self.http('models.publish', {'model_id': draft['id'], 'revision': 1,
            'reconcile_capture': True}, version=2)
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        self.assertEqual(self.counts(), before)

    def test_owner_budget_epoch_and_approval_authority_is_unchanged(self):
        policy = self.fixture.inspect(2)['selection_policy']
        body = {'name': 'Owner-only finite budget', 'policy': policy,
                'limits': dict(attempt_slots=1, admitted_wall_seconds=60,
                               retained_bytes=1048576, peak_staging_bytes=1048576)}
        before = self.counts()
        self.assertEqual(self.call('studies.create', body, 403)['code'], 'forbidden')
        self.assertEqual(self.counts(), before)

    def test_model_source_guard_uses_exact_revision_and_preserves_published_replay(self):
        legacy = copy.deepcopy(self.fixture.manifest)
        legacy.update(schema_version=1,id=uuid.uuid4().hex)
        del legacy['extensions']
        (self.fixture.project/'legacy.json').write_text(json.dumps(legacy))
        self.dataset.projects.open({'root':'fixture','manifest_path':'legacy.json'})
        draft = self.call('models.create',self.fixture.body(),201)
        published = self.call('models.publish',{'model_id':draft['id'],'revision':1})
        newer = copy.deepcopy(draft)
        newer['source_selector']['project_id'] = legacy['id']
        self.dataset.models.save(draft['id'],{'revision':1,'document':newer})
        self.assertEqual(self.call('models.publish',{'model_id':draft['id'],'revision':1}),published)
        # Verified retained replay captures nothing, even with the old contract.
        before = self.counts()
        status,result = self.http('models.publish',{'model_id':draft['id'],'revision':1},version=1)
        self.assertEqual((status,result),(200,published))
        self.assertEqual(self.counts(),before)

    def test_future_revision_cannot_pass_an_old_source_gate(self):
        draft = self.call('models.create',self.fixture.body(),201)
        graph = self.call('graphs.create_external',self.graph_body(),201)
        study = self.dataset.studies.create({'name':'Closed owner revision guard test',
            'policy':self.fixture.inspect(2)['selection_policy'],
            'limits':dict(attempt_slots=1,admitted_wall_seconds=60,
                          retained_bytes=1048576,peak_staging_bytes=1048576)})
        before = self.counts()
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Refused static operation must not execute')):
            # A speculative future revision must fail before a second read could
            # observe a concurrent save switching v1 source to bound v2 source.
            with patch.object(self.dataset.models,'get',return_value=draft) as get:
                status,result = self.http('models.publish',{'model_id':draft['id'],'revision':2},version=1)
                self.assertEqual((status,result['code']),(409,'stale'))
                self.assertEqual(get.call_count,1)
            for name,arguments in (
                    ('graphs.preflight_external',{'graph_id':graph['id'],'revision':2}),
                    ('studies.prepare_trial',{'study_id':study['id'],'request_key':uuid.uuid4().hex,
                        'revision':study['revision'],'graph_id':graph['id'],'graph_revision':2,'replicate':0,
                        'model':{'kind':'model','catalog_id':self.dataset.db.dataset_id,
                            'id':uuid.uuid4().hex,'revision':1,'sha256':'a'*64}})):
                with self.subTest(operation=name), patch.object(self.dataset.pipelines,'get',return_value=graph) as get:
                    status,result = self.http(name,arguments,version=1)
                    self.assertEqual((status,result['code']),(409,'stale'))
                    self.assertEqual(get.call_count,1)
        self.assertEqual(self.counts(),before)

    def test_old_v1_project_trial_receipt_survives_later_graph_revision(self):
        from test_experiments import StudyTests
        case = StudyTests('runTest')
        self.addCleanup(case.doCleanups)
        case.setUp()
        with case.owner.bound(case.dataset):
            actor = case.dataset.access.issue({'label':'Legacy v1 author','scopes':['inspect','edit']})
            body = {'study_id':case.study['id'],'revision':case.study['revision'],
                'request_key':uuid.uuid4().hex,'graph_id':case.graph['id'],
                'graph_revision':case.graph['revision'],'model':case.model['ref'],'replicate':0}
        prior_base,self.base = self.base,case.server()
        try:
            with patch.object(subprocess,'Popen',side_effect=AssertionError('Legacy static preparation is inert')):
                status,trial = self.http('studies.prepare_trial',body,version=1,token=actor['token'])
                self.assertEqual(status,201,trial)
                with case.owner.bound(case.dataset):
                    newer = copy.deepcopy(case.graph)
                    newer['name'] = 'Later graph revision preserves original receipt'
                    case.dataset.pipelines.save(case.graph['id'],{'revision':1,'document':newer})
                status,repeated = self.http('studies.prepare_trial',body,version=1,token=actor['token'])
                self.assertEqual((status,repeated),(201,trial))
            self.assertEqual(case.dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)
            self.assertEqual(case.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)
        finally:
            self.base = prior_base

    def test_agent_graph_preflight_and_trial_preparation_are_inert_under_owner_budget(self):
        """Tiny non-runnable runtime bytes prove static capture, never CPU execution."""
        from runtime_snapshots import RuntimeSnapshots
        python = self.fixture.root/'static-runtime-python'
        packages = self.fixture.root/'static-runtime-packages'
        (python/'bin').mkdir(parents=True)
        (python/'lib/python3.12/lib-dynload').mkdir(parents=True)
        shutil.copyfile('/usr/bin/true',python/'bin/python3.12')
        (python/'lib/python3.12/lib-dynload/fixture.txt').write_text('Static capture fixture only')
        names = []
        for name in ('torch','numpy'):
            (packages/name).mkdir(parents=True)
            (packages/name/'__init__.py').write_text('fixture = True\n')
            metadata = packages/(name+'-0.0.dist-info'); metadata.mkdir()
            (metadata/'METADATA').write_text('Name: '+name+'\nVersion: 0.0\n')
            (metadata/'LICENSE').write_text('Static test fixture')
            names.extend((name,metadata.name))
        configuration = dict(schema_version=1,python_root=str(python),python_version='3.12',
                             site_packages=str(packages),packages=names)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('Static preparation must not execute')):
            runtimes = RuntimeSnapshots(self.dataset.db,self.dataset.access,self.dataset.path)
            descriptor = runtimes.create(configuration,runtimes.inspect(configuration)['inventory_sha256'],quiesced=True)
            self.fixture.recipe['runtime_snapshot_sha256'] = descriptor['manifest_sha256']
            self.fixture.extension['runtime']['snapshot_sha256'] = descriptor['manifest_sha256']
            self.fixture.manifest['id'] = uuid.uuid4().hex
            self.fixture.write_project()
            self.call('project_snapshots.open',{'root':'fixture','manifest_path':'project.json'},201)
            inspected = self.call('recipes.inspect',{'project_id':self.fixture.selector['project_id'],
                'reference_id':self.fixture.selector['recipe_id'],
                'expected_sha256':self.fixture.selector['expected_sha256']})
            draft = self.call('models.create',self.fixture.body(),201)
            model = self.call('models.publish',{'model_id':draft['id'],'revision':1})
            graph = self.call('graphs.create_external',self.graph_body(),201)
            preflight = self.call('graphs.preflight_external',{'graph_id':graph['id'],'revision':graph['revision']})
            self.assertEqual(preflight['material']['project']['project_id'],self.fixture.selector['project_id'])
            study = self.dataset.studies.create({'name':'Owner finite static-only budget',
                'policy':inspected['selection_policy'],
                'limits':dict(attempt_slots=1,admitted_wall_seconds=60,
                              retained_bytes=1048576,peak_staging_bytes=1048576)})
            before = self.counts()
            trial_arguments = {'study_id':study['id'],'revision':study['revision'],
                'request_key':uuid.uuid4().hex,'graph_id':graph['id'],'graph_revision':graph['revision'],
                'model':model['ref'],'replicate':0}
            trial = self.call('studies.prepare_trial',trial_arguments,201)
            newer = copy.deepcopy(graph)
            newer['name'] = 'Later saved draft does not alter the Trial receipt'
            self.dataset.pipelines.save(graph['id'],{'revision':graph['revision'],'document':newer})
            self.assertEqual(self.call('studies.prepare_trial',trial_arguments,201),trial)
            status,result = self.http('studies.prepare_trial',trial_arguments,version=1)
            self.assertEqual((status,result),(201,trial))
            state = self.call('studies.get',{'study_id':study['id']})['study']
            self.assertFalse(state['open'])
            self.assertEqual(state['admission_epoch'],0)
            self.assertEqual(state['trial_ids'],[trial['id']])
            self.assertEqual(self.call('studies.continue',{'study_id':study['id'],
                'revision':state['revision'],'admission_epoch':0,'request_key':uuid.uuid4().hex},403)['code'],'forbidden')
            self.assertEqual(self.call('studies.approve',{'study_id':study['id'],'trial_id':trial['id'],
                'expected_material_sha256':trial['material']['sha256'],
                'consumer_actor_id':self.agent['identity']['actor_id']},403)['code'],'forbidden')
        after = self.counts()
        self.assertEqual(after['model_trials'],before['model_trials']+1)
        for name in ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations'):
            self.assertEqual(after[name],before[name])

    def test_selected_header_mismatch_refuses_before_registration(self):
        before = self.counts()
        body = json.dumps({'root':'fixture','manifest_path':'project.json'}).encode()
        for header in (api.selected_header('context.get'),
                       'project_snapshots.open/1/' + '0'*64):
            request = Request(self.base+'/api/workspace/project-snapshots',data=body,
                headers={'Authorization':'Bearer '+self.agent['token'],
                    'Content-Type':'application/json',api.CONTRACT_HEADER:header})
            with self.subTest(header=header), self.assertRaises(HTTPError) as caught:
                urlopen(request,timeout=20)
            with caught.exception as response:
                self.assertEqual(response.code,409)
                self.assertEqual(json.load(response)['code'],'contract_mismatch')
        self.assertEqual(self.counts(),before)

    def test_missing_scope_unknown_root_and_revocation_refuse_without_project_mutation(self):
        before = self.counts()
        read_only = self.dataset.access.issue({'label': 'Inspect only', 'scopes': ['inspect']})
        status, result = self.http('project_snapshots.open',
            {'root': 'fixture', 'manifest_path': 'project.json'}, token=read_only['token'])
        self.assertEqual((status, result['code']), (403, 'forbidden'))
        result = self.call('project_snapshots.open', {'root': 'unknown', 'manifest_path': 'project.json'}, 409)
        self.assertEqual(result['code'], 'unavailable')
        self.dataset.access.revoke(self.agent['identity']['credential_id'])
        for name, arguments in (('project_snapshots.list', {}),
                ('project_snapshots.get', {'project_id': self.fixture.manifest['id']}),
                ('project_snapshots.open', {'root': 'fixture', 'manifest_path': 'project.json'})):
            with self.subTest(operation=name):
                self.assertEqual(self.client.call(name, arguments)['status'], 401)
        self.assertEqual(self.counts(), before)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('mcp')
                     and importlib.util.find_spec('jsonschema'),
                     'Requires the isolated official MCP agent environment and PostgreSQL')
class SnapshotTransportTests(unittest.TestCase):
    def setUp(self):
        self.case = AgentSnapshotHTTPTests('runTest')
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.root = Path(__file__).resolve().parents[1]
        self.environment = {key:value for key,value in os.environ.items() if not key.startswith('TULDOK_')}
        self.environment['PYTHONDONTWRITEBYTECODE'] = '1'
        token = self.case.fixture.root/'snapshot.token'
        token.write_text(self.case.agent['token']); token.chmod(0o600)
        self.config = self.case.fixture.root/'snapshot.config.json'
        self.config.write_text(json.dumps({'endpoint':self.case.base,
            'catalog_id':self.case.dataset.db.dataset_id,'token_file':str(token),'timeout':30}))
        self.config.chmod(0o600)

    def test_actual_cli_and_official_mcp_use_selected_snapshots_and_revoke_cached_session(self):
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        expected = self.case.client.call('project_snapshots.list',{'limit':1})
        arguments = self.case.fixture.root/'snapshot-arguments.json'
        arguments.write_text(json.dumps({'limit':1})); arguments.chmod(0o600)
        command = [sys.executable,str(self.root/'project_cli.py'),'--config',str(self.config),
                   'call','--operation','project_snapshots.list','--arguments',str(arguments)]
        result = subprocess.run(command,env=self.environment,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),expected['result'])

        async def exercise():
            params = StdioServerParameters(command=sys.executable,
                args=[str(self.root/'mcp_stdio.py'),'--config',str(self.config)],
                cwd=str(self.root),env=self.environment)
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    tools = {tool.name for tool in (await session.list_tools()).tools}
                    self.assertTrue({'project_snapshots_list','project_snapshots_open','project_snapshots_get'} <= tools)
                    result = await session.call_tool('project_snapshots_list',{'limit':1})
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent,expected)
                    self.case.dataset.access.revoke(self.case.agent['identity']['credential_id'])
                    result = await session.call_tool('project_snapshots_list',{'limit':1})
                    self.assertTrue(result.isError)
                    self.assertEqual(result.structuredContent,self.case.client.call('project_snapshots.list',{'limit':1}))
                    self.assertEqual(result.structuredContent['status'],401)
        anyio.run(exercise)
        result = subprocess.run(command,env=self.environment,capture_output=True,text=True,timeout=30)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stderr)['code'],'unauthenticated')


if __name__ == '__main__':
    unittest.main()
