"""M4 fixed projections and client fault boundaries.

Controlled replies establish transport refusal and exact byte custody, not disk
publication or execution. The loopback case exercises the real HTTP JSON reader.
"""
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import agent_api as api
import project_cli
import project_dispatch
from tuldok_client import ProjectFilesClient

CATALOG, BINDING, PROJECT, ACTOR, FORK = (ch*32 for ch in 'abcdf')
CP, NEXT = 'e'*64, 'f'*64
KEY = 'm4-reviewed-request-0001'
STAMP = '2026-10-22T12:00:00+00:00'
ROOT = Path(__file__).resolve().parents[1]
READ = dict(binding=BINDING, checkpoint=CP)
WRITE = dict(binding=BINDING, expected_checkpoint=CP, request_key=KEY)
ACTIONS = ['new','open','save','close','query','get','import_text','annotate']


def identity(kind='script', path='scripts/inert.py', project=PROJECT):
    return hashlib.sha256((project+'\0'+kind+'\0'+path).encode()).hexdigest()


def version(text, revision=1):
    raw = text.encode('utf-8')
    return dict(revision=revision, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                text=text, adopted_at=STAMP, actor_id=ACTOR)


def selected(text='print("inert")\n', revision=1):
    return dict(id=identity(), project_id=PROJECT, kind='script', path='scripts/inert.py',
                version=version(text, revision))


def bound(value, checkpoint=CP):
    return dict(binding=BINDING, project_id=PROJECT, checkpoint=checkpoint, value=value)


def ready(reply, *, owner=False):
    client = (api.ProjectFilesOwnerClient if owner else api.AgentClient)(
        'http://127.0.0.1:12345', 'fixture-only-m4-transport-token', CATALOG)
    client._ready = True
    client._selected = {name: 1 for name in api.PROJECT_FILES_M4}
    client._request = Mock(return_value=copy.deepcopy(reply))
    return client


class M4Clients(unittest.TestCase):
    def test_capability_profiles_fit_unchanged_budget_and_negotiate_only_intersections(self):
        native = api.capabilities(CATALOG)
        project = api.capabilities(CATALOG, profile='project')
        self.assertLessEqual(len(api.encoded(native)), 1048576)
        self.assertLessEqual(len(api.encoded(project)), 1048576)
        self.assertTrue(all(not op['id'].startswith('project_files.') for op in native['operations']))
        self.assertTrue(all(op['id'].startswith('project_files.') or op['id'] in api.PROJECT_TRANSFER_OPERATIONS or op['id'] in ('context.get','identity.get') for op in project['operations']))
        self.assertTrue(api.PROJECT_FILES_M4 <= set(api.negotiate(project, CATALOG)))
        self.assertFalse(api.PROJECT_FILES_M4 & set(api.negotiate(native, CATALOG)))
        with self.assertRaises(api.AgentAPIError): api.capabilities(CATALOG, profile='arbitrary')
        self.assertEqual(api.REGISTRY_DIGEST, api._LEGACY_DIGEST)

    def test_ten_operations_have_fixed_consumers_and_closed_inputs(self):
        self.assertEqual(len(api.PROJECT_FILES_M4), 10)
        self.assertEqual(project_dispatch.SUPPORTED_OPERATIONS & api.PROJECT_FILES_M4,
                         api.PROJECT_FILES_M4 - {'project_files.save_as'})
        client = ProjectFilesClient(Mock())
        parser = project_cli.parser()
        for operation in api.PROJECT_FILES_M4:
            action = operation.split('.')[1]
            self.assertTrue(callable(getattr(client, action)))
            if action == 'save_as':
                args = ['--binding',BINDING,'--expected-checkpoint',CP,'--request-key',KEY,
                        '--root','fixture','--directory','independent','--name','Independent']
            else: args = ['--arguments','/not-read']
            self.assertEqual(parser.parse_args(['--config','/not-read','file-'+action.replace('_','-'),*args]).command,
                             'file-'+action.replace('_','-'))
        with self.assertRaises(api.AgentAPIError):
            api.validate_arguments('project_files.file_adopt', dict(WRITE, kind='script',path='scripts/inert.py',
                expected_revision=0,expected_sha256=CP,execute=True))
        self.assertEqual(api.contract('project_files.save_as')['authority'],'owner')
        self.assertEqual(api.contract('project_files.file_adopt')['authority'],'agent')
        source=(ROOT/'static/project-files.js').read_text()
        pins=json.loads(re.search(r'PROJECT_FILES_CONTRACTS_START \*/\s*(.*?)\s*/\* PROJECT_FILES_CONTRACTS_END',source,re.S)[1])
        for name in api.PROJECT_FILES_M4: self.assertEqual(pins[name],api.contract(name)['sha256'])

    def test_selected_file_checks_exact_utf8_revision_identity_and_empty_text(self):
        arguments=dict(READ,file_id=identity(),revision=2)
        for text in ('', '\0 exact\r\nΩ 🌸', '🌸'*262144):
            value=bound(selected(text,2));raw=ready(dict(status=200,result=value))
            self.assertEqual(ProjectFilesClient(raw).file_get(**arguments),value)
        value=bound(selected('exact',2));raw=ready(dict(status=200,result=value))
        for change in ({'text':'different'},{'bytes':4},{'sha256':CP},{'revision':3}):
            corrupt=copy.deepcopy(value);corrupt['value']['version'].update(change)
            raw._request.return_value=dict(status=200,result=corrupt)
            with self.assertRaises(api.AgentAPIError): ProjectFilesClient(raw).file_get(**arguments)
        for change in ({'id':CP},{'project_id':ACTOR},{'path':'scripts/another.py'}):
            corrupt=copy.deepcopy(value);corrupt['value'].update(change)
            raw._request.return_value=dict(status=200,result=corrupt)
            with self.assertRaises(api.AgentAPIError): ProjectFilesClient(raw).file_get(**arguments)

    def test_nul_exception_is_only_exact_successful_file_text_leaf_over_real_http(self):
        body=bound(selected('before\0after'))
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                raw=api.encoded(body);self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def log_message(self,*_): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,5);self.addCleanup(server.shutdown)
        client=api.AgentClient(f'http://127.0.0.1:{server.server_port}','fixture-only-m4-token',CATALOG)
        client._ready=True;client._selected={'project_files.file_get':1}
        self.assertEqual(ProjectFilesClient(client).file_get(**READ,file_id=identity()),body)
        with self.assertRaises(api.AgentAPIError): api.decode(api.encoded(body))
        for field in ('path','kind'):
            invalid=copy.deepcopy(body);invalid['value'][field]+='\0'
            with self.assertRaises(api.AgentAPIError):
                api.validate_output('project_files.file_get',dict(status=200,result=invalid))
        with self.assertRaises(api.AgentAPIError):
            api.validate_output('project_files.file_get',dict(status=503,result={'error':'bad\0','code':'unavailable'}))
        with self.assertRaises(api.AgentAPIError):
            api.validate_arguments('project_files.file_adopt',dict(WRITE,kind='script',path='scripts/a\0',expected_revision=0,expected_sha256=CP))
        invalid=copy.deepcopy(body)
        invalid['value']['version']['text']='bad\ud800'
        with self.assertRaises(api.AgentAPIError):
            api.validate_output('project_files.file_get',dict(status=200,result=invalid))

    def test_adoption_history_and_nested_mapping_refuse_wrong_selection(self):
        meta=version('exact');meta.pop('text')
        adopted=dict(id=identity(),project_id=PROJECT,kind='script',path='scripts/inert.py',
            **{k:v for k,v in meta.items() if k!='actor_id'},changed=True)
        arguments=dict(WRITE,kind='script',path='scripts/inert.py',expected_revision=0,expected_sha256=meta['sha256'])
        raw=ready(dict(status=200,result=bound(adopted,NEXT)))
        self.assertEqual(ProjectFilesClient(raw).file_adopt(**arguments)['value'],adopted)
        for change in ({'sha256':CP},{'revision':2},{'changed':False}):
            raw._request.return_value=dict(status=200,result=bound(dict(adopted,**change),NEXT))
            with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).file_adopt(**arguments)
        history=dict(id=identity(),items=[meta],offset=0,limit=40,total=1)
        raw._request.return_value=dict(status=200,result=bound(history))
        self.assertEqual(ProjectFilesClient(raw).file_history(**READ,file_id=identity())['value'],history)
        raw._request.return_value=dict(status=200,result=bound(dict(history,items=[dict(meta,text='forbidden')])) )
        with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).file_history(**READ,file_id=identity())
        mapping=dict(source=None,project_id=PROJECT,mapping=dict(items=[],offset=0,limit=40,total=0),
                     archived_count=0,copied_count=0,missing_regenerable_count=0)
        raw._request.return_value=dict(status=200,result=bound(mapping))
        ProjectFilesClient(raw).fork_info(**READ)
        for change in ({'offset':1},{'limit':1},{'total':1}):
            corrupt=copy.deepcopy(mapping);corrupt['mapping'].update(change)
            raw._request.return_value=dict(status=200,result=bound(corrupt))
            with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).fork_info(**READ)

    def test_save_as_correlates_new_state_and_never_retries_failed_ack(self):
        arguments=dict(WRITE,root='fixture',directory='independent',name='Independent Ω')
        state=dict(format='project_files_state_v1',binding=ACTOR,state='open',roots=['fixture'],
                   project=dict(project_id=FORK,name=arguments['name'],checkpoint=NEXT),available_actions=ACTIONS)
        fork=dict(source_project_id=PROJECT,source_checkpoint=CP,project_id=FORK,checkpoint=NEXT,
                  root='fixture',directory='independent',request_key=KEY,reconciled=False,
                  mapping_count=2,copied_count=3,missing_regenerable_count=1)
        result=dict(state=state,fork=fork);raw=ready(dict(status=200,result=result),owner=True)
        self.assertEqual(ProjectFilesClient(raw).save_as(**arguments),result)
        for field,bad in (('directory','elsewhere'),('source_checkpoint',NEXT),('project_id',PROJECT),('request_key','different-request')):
            corrupt=copy.deepcopy(result);corrupt['fork'][field]=bad
            raw._request.return_value=dict(status=200,result=corrupt)
            with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).save_as(**arguments)
        corrupt=copy.deepcopy(result);corrupt['state']['binding']=BINDING
        raw._request.return_value=dict(status=200,result=corrupt)
        with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).save_as(**arguments)
        raw._request.return_value=dict(status=503,result={'error':'Inspect current selection.','code':'outcome_unknown'})
        before=raw._request.call_count
        with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).save_as(**arguments)
        self.assertEqual(raw._request.call_count-before,1)

    def test_file_observations_and_original_intents_refuse_cross_project_metadata(self):
        meta=version('exact');observation=dict(id=identity(),kind='script',path='scripts/inert.py',revision=1,
            expected_sha256=meta['sha256'],expected_bytes=meta['bytes'],observed_sha256=meta['sha256'],
            observed_bytes=meta['bytes'],state='unchanged',reason=None)
        page=dict(items=[observation],offset=0,limit=40,total=1)
        raw=ready(dict(status=200,result=bound(page)))
        ProjectFilesClient(raw).files_inspect(**READ)
        for change in ({'id':CP},{'observed_sha256':CP},{'observed_bytes':0}):
            raw._request.return_value=dict(status=200,result=bound(dict(page,items=[dict(observation,**change)])))
            with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).files_inspect(**READ)
        origin=dict(project_id=FORK,checkpoint=NEXT,family='model_definition',id=ACTOR,revision=2,created_at=STAMP)
        current=dict(format='project_material_fork_intent_v1',catalog_id=PROJECT,id=ACTOR,revision=1,
            name='Retained original',definition_family='model_definition',
            definition={'source_selector':{'catalog_id':FORK},'specification':{'width':17}},
            required_reselection=['source_selector'])
        detail=dict(family='model_definition',id=PROJECT+'.'+ACTOR,current=current,fork_origin=origin)
        raw._request.return_value=dict(status=200,result=bound(detail))
        self.assertEqual(ProjectFilesClient(raw).material_intent(**READ,family='model_definition',definition_id=ACTOR)['value'],detail)
        for field in ('catalog_id','id','definition_family'):
            corrupt=copy.deepcopy(detail);corrupt['current'][field]='pipeline_graph' if field=='definition_family' else FORK
            raw._request.return_value=dict(status=200,result=bound(corrupt))
            with self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(raw).material_intent(**READ,family='model_definition',definition_id=ACTOR)
        summary=dict(family='model_definition',id=PROJECT+'.'+ACTOR,catalog_id=PROJECT,definition_id=ACTOR,
            name=current['name'],revision=1,required_reselection=current['required_reselection'],fork_origin=origin)
        raw._request.return_value=dict(status=200,result=bound(dict(items=[summary],offset=0,limit=40,total=1)))
        ProjectFilesClient(raw).material_intents(**READ)
        raw._request.return_value=dict(status=200,result=bound(dict(items=[dict(summary,catalog_id=FORK)],offset=0,limit=40,total=1)))
        with self.assertRaises(api.AgentAPIError):ProjectFilesClient(raw).material_intents(**READ)

    def test_dispatch_projects_metadata_pages_without_captured_text_or_definition_bulk(self):
        import threading
        access=SimpleNamespace(lock=threading.RLock(),require=Mock())
        session=SimpleNamespace(access=access,lock=threading.RLock(),db=SimpleNamespace(lock=threading.RLock()),
            check=Mock(return_value={'project_id':PROJECT,'records':[]}))
        files=SimpleNamespace(history=Mock(return_value=[version('large text '+str(i),i+1) for i in range(42)]))
        projection=SimpleNamespace(session=session,files=files)
        page=project_dispatch.dispatch(projection,'project_files.file_history',dict(READ,file_id=identity(),offset=40,limit=2))
        self.assertEqual((page['total'],[item['revision'] for item in page['items']]),(42,[41,42]))
        self.assertTrue(all('text' not in item for item in page['items']))
        api.validate_output('project_files.file_history',dict(status=200,result=bound(page)))


if __name__=='__main__':unittest.main()
