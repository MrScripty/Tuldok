"""Exact operation negotiation and actual retained/new HTTP owners.

Authored capability variants exercise protocol changes, never model acceptance.
Real PostgreSQL/Access/neutral Runs verify the downstream boundaries.
"""
import copy
import asyncio
import base64
from email.message import Message
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import types
import unittest
import uuid
from unittest.mock import patch

import agent_api as api
import app
from test_agent_api import server as legacy_stub, TOKEN, CATALOG
from test_agent_http import AgentHTTPCase

FIXTURES = Path(__file__).parent / 'fixtures'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


LEGACY = module(FIXTURES/'agent_legacy_f588.py', 'retained_agent_f588')


def server_api():
    return module(Path(api.__file__), 'isolated_server_agent')


class ContractSelectionTests(unittest.TestCase):
    def test_actual_legacy_projection_unchanged_with_additions_and_mutated_live_metadata(self):
        expected = LEGACY.discovery()
        self.assertEqual(api.discovery(), expected)
        original = copy.deepcopy(api._OPERATIONS)
        with patch.object(api, '_OPERATIONS', original + [dict(original[0], operation_id='future.operation')]):
            original[0]['description'] = 'New prose must not mutate retained bytes.'
            self.assertEqual(api.discovery(), expected)
        changed = api.discovery(); changed['operations'][0]['inputSchema'] = {}
        self.assertEqual(api.discovery(), expected)
        self.assertEqual(expected['digest'], 'cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8')

    def test_addition_and_one_incompatible_operation_preserve_unrelated_intersections(self):
        value = api.capabilities(CATALOG)
        unrelated = copy.deepcopy(value['operations'][0]); unrelated['id'] = 'future.operation'
        value['operations'].append(unrelated)
        changed = next(x for x in value['operations'] if x['id'] == 'projects.open')
        changed['contracts'][0]['sha256'] = '0'*64
        selected = api.negotiate(value, CATALOG)
        self.assertIn('context.get', selected)
        self.assertNotIn('projects.open', selected)
        self.assertNotIn('future.operation', selected)

    def test_bounded_malformed_catalog_versions_and_digest_schema_contradiction(self):
        baseline = api.capabilities(CATALOG)
        variants = [dict(baseline, catalog_id='b'*32), dict(baseline, envelope_version=True),
                    dict(baseline, extra=True), dict(baseline, operations=baseline['operations']*5)]
        repeated = copy.deepcopy(baseline); repeated['operations'].append(repeated['operations'][0]);variants.append(repeated)
        for value in variants:
            with self.subTest(keys=list(value)), self.assertRaises(api.AgentAPIError):
                api.negotiate(value, CATALOG)
        value = copy.deepcopy(baseline);item = value['operations'][0]['contracts'][0]
        item['input_schema'] = {'type':'string'}
        self.assertNotIn(value['operations'][0]['id'], api.negotiate(value,CATALOG))
        self.assertEqual(baseline['limits']['response_bytes'], 16*1024*1024)
        self.assertLess(len(api.encoded(baseline)), api.CAPABILITIES_LIMIT)

    def test_schema_prose_does_not_change_contract_but_same_named_data_fields_do(self):
        before = api.contract('projects.open')
        versions = copy.deepcopy(api._CONTRACTS)
        versions['projects.open'][1]['description'] = 'Different public prose.'
        versions['projects.open'][1]['inputSchema']['description'] = 'Schema prose.'
        with patch.object(api, '_CONTRACTS', versions):
            self.assertEqual(api.contract('projects.open'), before)
            versions['projects.open'][1]['inputSchema']['properties']['description'] = {'type':'string'}
            self.assertNotEqual(api.contract('projects.open')['sha256'], before['sha256'])

    def test_request_projection_rejects_wrong_route_query_injection_and_extra_body(self):
        cases = [('data.query', {}, '/api/workbench/records?limit=1&limit=2', None),
                 ('data.query', {}, '/api/workbench/records?surprise=1', None),
                 ('data.import_text', {'text':'fixture','groups':['fixture']}, '/api/workbench/import',
                  {'kind':'image','text':'fixture','groups':['fixture']}),
                 ('projects.open', {'root':'fixture','manifest_path':'project.json'}, '/api/workspace/projects',
                  {'root':'fixture','manifest_path':'project.json','unknown':True})]
        for name, arguments, target, body in cases:
            method = api.operation(name)['method'];h=Message();h[api.CONTRACT_HEADER]=api.selected_header(name)
            selected=api.select_request(h,method,target)
            with self.subTest(name=name), self.assertRaises(api.AgentAPIError):
                api.validate_selected(selected,method,target,body)
        h=Message();h[api.CONTRACT_HEADER]=api.selected_header('projects.get')
        with self.assertRaises(api.AgentAPIError):api.select_request(h,'GET','/api/access/session')
        h[api.CONTRACT_HEADER]=api.selected_header('projects.get')
        with self.assertRaises(api.AgentAPIError):api.select_request(h,'GET','/api/workspace/projects/'+'a'*32)

    def test_new_client_uses_definite_legacy_fallback(self):
        with legacy_stub() as (endpoint,calls):
            client=api.AgentClient(endpoint,TOKEN,CATALOG)
            self.assertEqual(client.call('data.query',{'limit':1})['status'],200)
            self.assertTrue(client._legacy)
            self.assertEqual(sum(path=='/api/agent/capabilities' for _,path,_ in calls),1)

    def test_auth_server_malformed_and_ambiguous_missing_do_not_fallback(self):
        for status, value in [(401, {'error':'Revoked.', 'code':'unauthenticated'}),
                (403, {'error':'Denied.', 'code':'forbidden'}),
                (500, {'error':'Unavailable.', 'code':'storage'}),
                (404, {'error':'Catalog missing.', 'code':'not_found'}),
                (405, {'error':'Unexpected.'}), (200, {'ok':True})]:
            with self.subTest(status=status, value=value), legacy_stub(capabilities=(status,value)) as (endpoint,calls):
                with self.assertRaises(api.AgentAPIError):
                    api.AgentClient(endpoint,TOKEN,CATALOG).bootstrap()
                self.assertFalse(any(path=='/api/agent/operations' for _,path,_ in calls))

    def test_new_only_routes_require_contract_and_select_highest_exact_local_version(self):
        versions=copy.deepcopy(api._CONTRACTS)
        extra=copy.deepcopy(versions['context.get'][1])
        extra.update(operation_id='context.future', path='/api/agent/future')
        versions['context.future']={1:extra}
        original=api.capabilities(CATALOG)
        versions['context.get'][2]=copy.deepcopy(versions['context.get'][1])
        versions['context.get'][2]['inputSchema']={'type':'object','required':['new_field']}
        with patch.object(api,'_CONTRACTS',versions):
            self.assertEqual(api.negotiate(original,CATALOG)['context.get'],1)
            self.assertEqual(api.negotiate(api.capabilities(CATALOG),CATALOG)['context.get'],2)
            with self.assertRaises(api.AgentAPIError):
                api.select_request(Message(),'GET','/api/agent/future')
            self.assertIsNone(api.select_request(Message(),'GET','/api/workspace/context'))
            h=Message();h[api.CONTRACT_HEADER]=api.selected_header('context.future')
            self.assertEqual(api.select_request(h,'GET','/api/agent/future')[0],'context.future')
            extra['path']='/api/workspace/context'
            self.assertIsNone(api.select_request(Message(),'GET','/api/workspace/context'))
            with self.assertRaises(api.AgentAPIError):api.require_selection(None,'context.future')
            h=Message();h[api.CONTRACT_HEADER]=api.selected_header('context.future')
            selected=api.select_request(h,'GET','/api/workspace/context')
            api.require_selection(selected,'context.future')
            h=Message();h[api.CONTRACT_HEADER]=api.selected_header('context.get',1)
            with self.assertRaises(api.AgentAPIError):
                api.require_selection(api.select_request(h,'GET','/api/workspace/context'),'context.future')

    def test_unknown_operations_still_require_valid_closed_schema_and_bounded_metadata(self):
        baseline=api.capabilities(CATALOG)
        extra=copy.deepcopy(baseline['operations'][0]);extra['id']='future.operation'
        for field,value in [('input_schema',{'$ref':'https://invalid.example/schema'}),
                            ('output_schema',{'type':'bogus'}),('bounds',{'arbitrary':True}),
                            ('bounds',dict(extra['contracts'][0]['bounds'],json_depth=True)),
                            ('scopes',['inspect','inspect'])]:
            changed=copy.deepcopy(extra);changed['contracts'][0][field]=value
            with self.subTest(field=field),self.assertRaises(api.AgentAPIError) as error:
                api.negotiate(dict(baseline,operations=baseline['operations']+[changed]),CATALOG)
            self.assertEqual(error.exception.code,'capabilities_invalid')


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ActualNegotiatedHTTPTests(AgentHTTPCase):
    def client(self, cls=api.AgentClient):
        return cls(self.root,self.agent['token'],self.dataset.db.dataset_id)

    def restart_handler(self, factory):
        self.stop_server()
        from http.server import ThreadingHTTPServer
        import threading
        self.server=ThreadingHTTPServer(('127.0.0.1',0),factory(self.dataset))
        self.server_thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.server_thread.start()
        self.root=f'http://127.0.0.1:{self.server.server_port}'

    def handler_factories(self):
        namespace=dict(app.__dict__);namespace['agent_api']=LEGACY
        source=FIXTURES/'http_legacy_f588.py'
        exec(compile(source.read_text(),str(source),'exec'),namespace)
        return namespace['make_handler'],app.make_handler

    def wrapper_config(self):
        token=self.path/'matrix-token';token.write_text(self.agent['token']);token.chmod(0o600)
        config=self.path/'matrix-config.json'
        config.write_text(json.dumps({'endpoint':self.root,'catalog_id':self.dataset.db.dataset_id,
                                     'token_file':str(token)}));config.chmod(0o600)
        return config

    def wrapper_roots(self):
        legacy=self.path/'retained-f588';legacy.mkdir()
        for source,target in [('agent_legacy_f588.py','agent_api.py'),
                              ('cli_legacy_f588.py','project_cli.py'),('mcp_legacy_f588.py','mcp_stdio.py')]:
            (legacy/target).write_bytes((FIXTURES/source).read_bytes())
        return legacy,Path(api.__file__).parent

    def test_actual_old_and_new_clients_against_actual_old_and_new_http_factories(self):
        old,new=self.handler_factories()
        for factory in (old,new):
            self.restart_handler(factory)
            for cls in (LEGACY.AgentClient,api.AgentClient):
                with self.subTest(server='old' if factory==old else 'new',client=cls.__module__):
                    client=self.client(cls)
                    result=client.call('context.get',{})
                    self.assertEqual(result['result']['dataset_id'],self.dataset.db.dataset_id)
                    self.assertEqual(client.call('projects.get',{'project_id':self.manifest['id']})['status'],200)
                    if cls is api.AgentClient:
                        self.assertEqual(client._legacy, factory==old)

    def test_actual_retained_and_upgraded_cli_processes_old_new_server_matrix(self):
        self.agent=self.issue_http(['inspect','edit','execute','cancel'])
        roots=self.wrapper_roots()
        for server_name,factory in zip(('old','new'),self.handler_factories()):
            self.restart_handler(factory);config=self.wrapper_config()
            for root in roots:
                with self.subTest(server=server_name,client='old' if root==roots[0] else 'new'):
                    result=subprocess.run([sys.executable,str(root/'project_cli.py'),'--config',str(config),
                        'open','--root','fixture','--manifest','project.json'],
                        capture_output=True,text=True,timeout=30,cwd=root)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(json.loads(result.stdout)['id'],self.manifest['id'])
                    self.assertNotIn(self.agent['token'],result.stdout+result.stderr)

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Explicit optional MCP environment required')
    def test_actual_retained_and_upgraded_mcp_processes_old_new_server_matrix(self):
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.agent=self.issue_http(['inspect','edit','execute','cancel'])
        roots=self.wrapper_roots()
        async def run(root,config):
            parameters=StdioServerParameters(command=sys.executable,args=[str(root/'mcp_stdio.py'),
                '--config',str(config)],cwd=str(root))
            log=self.path/'matrix-mcp.log'
            with log.open('w+') as errors:
                async with stdio_client(parameters,errlog=errors) as (reader,writer):
                    async with ClientSession(reader,writer) as session:
                        await session.initialize()
                        self.assertIn('projects_open',{tool.name for tool in (await session.list_tools()).tools})
                        context=await session.call_tool('context_get',{})
                        self.assertEqual(context.structuredContent['result']['dataset_id'],self.dataset.db.dataset_id)
                        opened=await session.call_tool('projects_open',{'root':'fixture','manifest_path':'project.json'})
                        self.assertEqual(opened.structuredContent['status'],201)
                        self.assertEqual(opened.structuredContent['result']['id'],self.manifest['id'])
                errors.seek(0);self.assertNotIn(self.agent['token'],errors.read())
        for server_name,factory in zip(('old','new'),self.handler_factories()):
            self.restart_handler(factory);config=self.wrapper_config()
            for root in roots:
                with self.subTest(server=server_name,client='old' if root==roots[0] else 'new'):asyncio.run(run(root,config))

    def test_actual_authenticated_capability_surface_and_current_revocation(self):
        self.assertEqual(self.http('/api/agent/capabilities')[0],401)
        status,value=self.http('/api/agent/capabilities',token=self.agent['token'])
        self.assertEqual(status,200);self.assertEqual(value['catalog_id'],self.dataset.db.dataset_id)
        client=self.client();client.bootstrap()
        self.http('/api/access/credentials/'+self.agent['identity']['credential_id']+'/revoke',{},self.owner.token)
        result=client.call('context.get',{})
        self.assertEqual((result['status'],result['result']['code']),(401,'unauthenticated'))

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Explicit optional MCP environment required')
    def test_full_eight_mib_segment_fits_actual_selected_http_and_mcp_bounds(self):
        from test_agent_workflow import AgentWorkflowTests
        self.input=bytes(range(256))*(8*1024*1024//256)
        size=len(self.input);self.assertEqual(size,8*1024*1024)
        self.definition['inputs']['sample']['max_bytes']=size
        self.definition['outputs'][0]['max_bytes']=size
        self.definition['resources']['max_output_bytes']=size+65536
        self.definition_raw=json.dumps(self.definition).encode()
        self.manifest['id']=uuid.uuid4().hex
        self.manifest['data'][0]['sha256']=hashlib.sha256(self.input).hexdigest()
        self.manifest['recipes'][0]['sha256']=hashlib.sha256(self.definition_raw).hexdigest()
        for name,raw in {'input.bin':self.input,'recipe.json':self.definition_raw,
                         'project.json':json.dumps(self.manifest).encode()}.items():
            (self.project_path/name).write_bytes(raw)
        with self.owner.bound(self.dataset):
            self.dataset.projects.open({'root':'fixture','manifest_path':'project.json'})
            self.graph=self.dataset.pipelines.create_external(self.graph_body())
            self.preflight=self.dataset.pipelines.preflight_external(self.graph['id'],self.graph['revision'])
        run=self.client().call('runs.submit_external',self.body(approval=self.approve()))['result']
        complete=self.await_state(run['id'],{'completed','failed','unknown'})
        self.assertEqual(complete['state'],'completed',complete.get('error'))
        artifact=complete['artifacts'][0]
        arguments={'run_id':run['id'],'name':artifact['name'],'expected_sha256':artifact['sha256'],
                   'offset':0,'max_bytes':size}
        response=self.client().call('runs.artifact_chunk',arguments)
        self.assertEqual(response['status'],200)
        self.assertEqual(base64.b64decode(response['result']['data_base64']),self.input)
        self.assertLess(len(api.encoded(response)),api.RESPONSE_LIMIT)
        self.config_count=0
        async def read():
            async with AgentWorkflowTests.mcp(self,self.agent) as session:
                result=await session.call_tool('runs_artifact_chunk',arguments)
                self.assertFalse(result.isError)
                self.assertEqual(base64.b64decode(result.structuredContent['result']['data_base64']),self.input)
        asyncio.run(read())

    def test_actual_additive_and_incompatible_capabilities_are_operation_scoped(self):
        isolated=server_api()
        extra=copy.deepcopy(isolated._CONTRACTS['context.get'][1]);extra.update(
            operation_id='context.extra',mcp_name='context_extra')
        isolated._CONTRACTS['context.extra']={1:extra}
        isolated._CONTRACTS['projects.open'][1]['inputSchema']['required'].append('future_required')
        with patch('app.agent_api',isolated):
            client=self.client();client.bootstrap()
            self.assertEqual(client.call('context.get',{})['status'],200)
            self.assertNotIn('projects_open',{x['name'] for x in client.tool_definitions()})
            with self.assertRaises(api.AgentAPIError) as error:
                client.call('projects.open',{'root':'fixture','manifest_path':'project.json'})
            self.assertEqual(error.exception.code,'operation_unsupported')
            self.assertNotIn('context.extra',client._selected)

    def test_dispatch_contract_race_refuses_before_real_grant_consumption(self):
        isolated=server_api();grant=self.approve();body=self.body(approval=grant)
        with patch('app.agent_api',isolated):
            client=self.client();client.bootstrap()
            isolated._CONTRACTS['runs.submit_external'][1]['injected']={'future':True}
            result=client.call('runs.submit_external',body)
            self.assertEqual((result['status'],result['result']['code']),(409,'contract_mismatch'))
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_admissions WHERE kind=%s',('runs',)).fetchone()[0],0)

    def test_duplicate_wrong_and_unregistered_headers_leave_actual_catalog_unchanged(self):
        header=api.selected_header('runs.submit_external');body=self.body(approval=self.approve())
        for value in ('runs.submit_external/1/'+'0'*64,api.selected_header('projects.open')):
            status,result=self.http('/api/workspace/runs/submit-external',body,self.agent['token'],headers={api.CONTRACT_HEADER:value})
            self.assertEqual((status,result['code']),(409,'contract_mismatch'))
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.putrequest('GET','/api/access/session');connection.putheader('Authorization','Bearer '+self.agent['token'])
        connection.putheader(api.CONTRACT_HEADER,api.selected_header('identity.get'))
        connection.putheader(api.CONTRACT_HEADER,api.selected_header('identity.get'));connection.endheaders()
        response=connection.getresponse();self.assertEqual(response.status,409);response.read();connection.close()
        status,result=self.http('/api/access/credentials',{'label':'Must not mint','scopes':['inspect']},self.owner.token,
                                headers={api.CONTRACT_HEADER:header})
        self.assertEqual((status,result['code']),(409,'contract_mismatch'))
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def test_selected_request_framing_refuses_before_read_or_mutation(self):
        for framing in ([('Content-Length','10'),('Content-Length','10')],
                        [('Transfer-Encoding','chunked')],
                        [('Content-Length',str(api.REQUEST_LIMIT+1))],
                        [('Content-Length','+12')]):
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            connection.putrequest('POST','/api/workspace/runs/submit-external')
            connection.putheader('Authorization','Bearer '+self.agent['token'])
            connection.putheader(api.CONTRACT_HEADER,api.selected_header('runs.submit_external'))
            for name,value in framing:connection.putheader(name,value)
            connection.endheaders()
            response=connection.getresponse();self.assertEqual(response.status,409);response.read();connection.close()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(),[])
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],0)

    def drop_next_submission_reply(self):
        original=app.make_handler
        def drop_factory(dataset):
            parent=original(dataset)
            class DropOnce(parent):
                dropped=False
                def reply(handler,data,status=200,content_type='application/json',headers=()):
                    if handler.path=='/api/workspace/runs/submit-external' and status==201 and not DropOnce.dropped:
                        DropOnce.dropped=True
                        handler.close_connection=True
                        handler.connection.shutdown(socket.SHUT_RDWR);handler.connection.close();return
                    return super().reply(data,status,content_type,headers)
            return DropOnce
        self.restart_handler(drop_factory)

    def test_lost_post_dispatch_reply_is_not_retried_and_same_key_reconciles_once(self):
        body=self.body(key='negotiated-lost-ack',approval=self.approve())
        self.drop_next_submission_reply();client=self.client();client.bootstrap()
        with self.assertRaises(api.AgentAPIError) as error:client.call('runs.submit_external',body)
        self.assertEqual(error.exception.code,'transport')
        with self.owner.bound(self.dataset):
            before=self.dataset.runs.list();self.assertEqual(len(before),1)
        result=client.call('runs.submit_external',body)
        self.assertEqual(result['status'],201);self.assertEqual(result['result']['id'],before[0]['id'])
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.runs.list()),1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    def test_real_cli_unknown_reply_and_explicit_same_key_reconciliation(self):
        self.drop_next_submission_reply()
        body=self.body(key='negotiated-cli-lost-ack',approval=self.approve())
        config=self.path/'cli-config.json';token=self.path/'cli-token';arguments=self.path/'cli-submit.json'
        token.write_text(self.agent['token']);token.chmod(0o600)
        config.write_text(json.dumps({'endpoint':self.root,'catalog_id':self.dataset.db.dataset_id,
                                     'token_file':str(token)}));config.chmod(0o600)
        arguments.write_text(json.dumps(body))
        command=[sys.executable,str(Path(app.__file__).parent/'project_cli.py'),
                 '--config',str(config),'submit','--arguments',str(arguments)]
        first=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertEqual(first.returncode,1,first.stdout)
        self.assertEqual(json.loads(first.stderr)['code'],'transport')
        self.assertNotIn(self.agent['token'],first.stderr)
        with self.owner.bound(self.dataset):
            before=self.dataset.runs.list();self.assertEqual(len(before),1)
        second=subprocess.run(command,capture_output=True,text=True,timeout=30)
        self.assertEqual(second.returncode,0,second.stderr)
        self.assertEqual(json.loads(second.stdout)['id'],before[0]['id'])
        with self.owner.bound(self.dataset):
            self.assertEqual(len(self.dataset.runs.list()),1)
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Explicit optional MCP environment required')
    def test_real_mcp_unknown_reply_and_explicit_same_key_reconciliation(self):
        from test_agent_workflow import AgentWorkflowTests
        self.drop_next_submission_reply();self.config_count=0
        body=self.body(key='negotiated-mcp-lost-ack',approval=self.approve())
        async def workflow():
            async with AgentWorkflowTests.mcp(self,self.agent) as session:
                first=await session.call_tool('runs_submit_external',body)
                self.assertTrue(first.isError)
                self.assertEqual(first.structuredContent['result']['code'],'transport')
                with self.owner.bound(self.dataset):
                    before=self.dataset.runs.list();self.assertEqual(len(before),1)
                second=await session.call_tool('runs_submit_external',body)
                self.assertFalse(second.isError)
                self.assertEqual(second.structuredContent['result']['id'],before[0]['id'])
                with self.owner.bound(self.dataset):
                    self.assertEqual(len(self.dataset.runs.list()),1)
                    self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM access_execution_consumptions').fetchone()[0],1)
        asyncio.run(workflow())

    @unittest.skipUnless(importlib.util.find_spec('mcp'), 'Explicit optional MCP environment required')
    def test_real_mcp_lists_only_negotiated_compatible_tools(self):
        from test_agent_workflow import AgentWorkflowTests
        isolated=server_api();self.config_count=0
        isolated._CONTRACTS['projects.open'][1]['injected']={'future':True}
        async def workflow():
            async with AgentWorkflowTests.mcp(self,self.agent) as session:
                names={tool.name for tool in (await session.list_tools()).tools}
                self.assertIn('context_get',names);self.assertNotIn('projects_open',names)
                result=await session.call_tool('context_get',{})
                self.assertEqual(result.structuredContent['status'],200)
        with patch('app.agent_api',isolated):asyncio.run(workflow())
