"""Actual native public transports, gated by an explicit immutable qualification.

One real owner CPU probe is reused by SDK/CLI/MCP. A real deferrable SQL ACK
fault starts no worker GO; original local phase reconciliation never repeats GO.
There is no model fit, training Run, provider, or imported execution authority.
"""
from datetime import timedelta
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

# Script-mode browser fixtures must find the repository without PYTHONPATH.
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import psycopg
from psycopg import sql

import agent_api as api
from app import make_handler
from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
from project_workspace import ProjectWorkspace
import project_workspace
from tuldok_client import ProjectFilesClient

MANIFEST_ENV='TULDOK_NATIVE_PUBLIC_FREEZE_MANIFEST'


def frozen_subject():
    name=os.environ.get(MANIFEST_ENV)
    if not name:raise AssertionError('Lead must provide '+MANIFEST_ENV+' before actual native qualification')
    path=Path(name);value=json.loads(path.read_text())
    current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in value['files']}
    if current!=value['files']:raise AssertionError('Immutable native public subject changed')
    return dict(manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),files=current)


class NativePublicFixture:
    """Test-owned real host and optional ACK fault; production owners stay real."""
    def __init__(self,path,*,dsn=None,cold=False):
        if os.environ.get('TULDOK_NATIVE_PROJECT_GO')!='1':raise AssertionError('Explicit native qualification GO required')
        if not project_workspace.M3_ENABLED:raise AssertionError('M3 must be explicitly enabled in the qualified subject')
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.external=self.path/'external';self.external.mkdir(exist_ok=True)
        self.control=self.path/'control';self.dsn=dsn or os.environ['TULDOK_DATABASE_URL']
        self.workspace=ProjectWorkspace(self.control,{'fixture':self.external},dsn=self.dsn)
        self.owner=ExplicitOwnerFixture.bootstrap(self.workspace)
        self.go_events=[];self.fired=[];self.forbidden=[];self.fault_db=None;self.original_before=None;self.patches=[]
        import recipe_process
        original_go=recipe_process.Handle.go
        def observed(handle,helper):
            projection=self.workspace._projection
            self.go_events.append(dict(phase_id=handle.spec['attempt_id'],in_transaction=projection.db.in_transaction))
            if projection.db.in_transaction:raise AssertionError('Native GO occurred before outer SQL acknowledgement')
            return original_go(handle,helper)
        self.patches.append(patch.object(recipe_process.Handle,'go',new=observed));self.patches[-1].start()
        if cold:
            def forbidden(*args,**kwargs):
                self.forbidden.append('native-prepare-or-Runs');raise AssertionError('Cold Open attempted native process or Runs construction')
            for target in ('project_native_process.prepare','runs.Runs'):
                self.patches.append(patch(target,side_effect=forbidden));self.patches[-1].start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.workspace))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)

    @property
    def projection(self):return self.workspace._projection

    def seed(self):
        from test_project_native_study import prepare_text_source
        with self.owner.bound(self.workspace):
            projection=self.projection
            if projection is None:raise AssertionError('Create the test project through real HTTP before seeding')
            rows,release=prepare_text_source(projection,key_prefix='public-native-'+uuid.uuid4().hex)
            body=dict(name='Native public text CPU fixture Ω',recipe='text_classification',release_id=release['id'])
            graph=projection.materials.mutate_definition('pipeline_graph','graphs.create',None,body,
                projection.session.snapshot['checkpoint'],'public-native-graph-'+uuid.uuid4().hex,
                lambda:projection.pipelines.create(body))
            return dict(graph_id=graph['id'],revision=graph['revision'],release_id=release['id'],records=len(rows))

    def install_fault(self):
        if self.original_before is not None:raise AssertionError('Only one explicit fixture fault at a time')
        projection=self.projection;db=projection.db;self.fault_db=db
        with db.lock:
            db.execute('CREATE TEMP TABLE public_native_ack_parent(id INT PRIMARY KEY)')
            db.execute('CREATE TEMP TABLE public_native_ack_child(id INT REFERENCES public_native_ack_parent(id) DEFERRABLE INITIALLY DEFERRED)')
            self.original_before=db._project_before_commit
            original=self.original_before
            def before():
                target=any(doc['events'][-1]['state']=='go_intent' for doc in projection.execution.native._dirty.values())
                original()
                if target and not self.fired:
                    self.fired.append(True);db.execute('INSERT INTO public_native_ack_child VALUES(1)')
            db._project_before_commit=before
        return dict(installed=True,kind='real_deferrable_sql_after_canonical_go_intent')

    def clear_fault(self):
        if self.original_before is not None:
            self.fault_db._project_before_commit=self.original_before;self.original_before=None

    def facts(self):
        p=self.projection
        if p is None:return dict(go_events=list(self.go_events),fired=list(self.fired),forbidden=list(self.forbidden),selected=False)
        with p.db.lock:
            records=p.session.snapshot['records']
            return dict(go_events=list(self.go_events),fired=list(self.fired),forbidden=list(self.forbidden),selected=True,
                available=p.session.available,workspace_runs=p.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],
                portable_phase_count=sum(r['family']=='native_execution_history' for r in records),
                pending=p.custody.has_pending if p.custody is not None else False)

    def close(self):
        self.clear_fault();self.server.shutdown();self.server.server_close();self.thread.join(5)
        close_failure=None
        try:
            try:self.workspace.close()
            except BaseException as error:
                close_failure=error
                # A failed assertion may leave an original ACK fence. Dispose
                # only this fixture's actual bounded children and handles;
                # never claim that public Close or reconciliation succeeded.
                drainage=[]
                for projection in (self.workspace._projection,self.workspace._retained_recovery):
                    if projection is None:continue
                    execution=projection.execution
                    if execution._runs is not None:raise AssertionError('This fixture must never admit a training Run') from error
                    if execution.native._active:raise AssertionError('Native request still active during fixture disposal') from error
                    for handle in tuple(execution.native._handles.values()):
                        receipt=handle.close_control()
                        if not receipt or not receipt.get('drained'):raise AssertionError('Fixture child drainage unconfirmed') from error
                        drainage.append(dict(drained=True,go_received=receipt.get('go_received')))
                    if projection.sources is not None:projection.sources.close()
                    projection.artifacts.close();projection.db.close()
                if self.workspace._store is not None:self.workspace._store.close()
                for _path,descriptor in self.workspace._roots.values():os.close(descriptor)
                self.workspace._roots.clear();self.workspace.db.close();self.workspace._closed=True
                report=Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT','/workspace/scratch/tuldok-save-load-qa/artifacts'))/'native-public-cleanup'
                report.mkdir(parents=True,exist_ok=True)
                (report/(uuid.uuid4().hex+'.json')).write_text(json.dumps(dict(public_close_succeeded=False,
                    close_error=type(error).__name__,fixture_children=drainage),indent=2)+'\n')
        finally:
            for context in reversed(self.patches):context.stop()
        # Cleanup only manifests created below this fixture's own control.
        with psycopg.connect(connection_info(self.dsn),autocommit=True) as connection:
            for manifest in self.control.rglob('.tuldok.json'):
                value=json.loads(manifest.read_bytes())
                schema='projection_'+value['projection_id'] if value['version']==2 else 'catalog_'+value['dataset_id']
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        if close_failure is not None:raise close_failure


@unittest.skipUnless(os.environ.get('TULDOK_NATIVE_PROJECT_GO')=='1' and os.environ.get('TULDOK_DATABASE_URL'),
    'Requires explicit native qualification GO and disposable PostgreSQL')
class NativePublicClientsHTTP(unittest.TestCase):
    def setUp(self):
        self.subject=frozen_subject();self.started=time.monotonic();self.performed=[];self.completed=False
        self.assertTrue(os.environ.get('TULDOK_TRAINING_PYTHON'),'Explicit current qualified CPU interpreter required')
        self.temp=tempfile.TemporaryDirectory(prefix='tuldok-native-public-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name);self.fixture=NativePublicFixture(self.path)
        self.addCleanup(self.fixture.close);self.addCleanup(self.receipt)
        self.owner=ProjectFilesClient(api.ProjectFilesOwnerClient(self.fixture.origin,self.fixture.owner.token,self.fixture.owner.catalog_id,timeout=60))
        self.environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}

    def receipt(self):
        end={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in self.subject['files']}
        directory=Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT','/workspace/scratch/tuldok-save-load-qa/artifacts'))/'native-public-clients';directory.mkdir(parents=True,exist_ok=True)
        (directory/(self._testMethodName+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps(dict(status='pass' if self.completed else 'failed',
            test=self.id(),seconds=round(time.monotonic()-self.started,3),performed=self.performed,subject=self.subject,source_stable=end==self.subject['files'],
            end_sha256=end,facts=self.fixture.facts(),fixture='Real owner HTTP/SDK/CLI/MCP; one CPU probe, real deferred SQL ACK fault with zero GO, no model training.'),indent=2)+'\n')
        self.assertEqual(end,self.subject['files'])

    def bound(self,*,mutation=False,key=None):
        state=self.owner.status()
        return dict(binding=state['binding'],**({'expected_checkpoint':state['project']['checkpoint'],'request_key':key or uuid.uuid4().hex}
            if mutation else {'checkpoint':state['project']['checkpoint']}))

    def config(self,name,token):
        token_file=self.path/(name+'.token');token_file.write_text(token+'\n');token_file.chmod(0o600)
        path=self.path/(name+'.json');path.write_text(json.dumps(dict(endpoint=self.fixture.origin,catalog_id=self.fixture.owner.catalog_id,token_file=str(token_file),timeout=60)));path.chmod(0o600)
        return path

    def cli(self,config,action,args,*,owner=True,success=True):
        file=self.path/('arguments-'+uuid.uuid4().hex+'.json');file.write_text(json.dumps(args))
        result=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),*(['--owner-project-files'] if owner else []),
            'file-'+action.replace('_','-'),'--arguments',str(file)],cwd=ROOT,env=self.environment,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode==0,success,result.stderr)
        self.assertNotIn(self.fixture.owner.token,result.stdout+result.stderr)
        return json.loads(result.stdout) if success else result

    @unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('anyio'),'Requires optional locked MCP dependencies')
    def test_real_native_preflight_replay_zero_go_failure_and_original_phase_recovery(self):
        import anyio
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        state=self.owner.status();opened=self.owner.new(binding=state['binding'],expected_checkpoint=None,request_key=uuid.uuid4().hex,
            root='fixture',directory='alpha',name='Native public actual transport Ω')
        graph=self.fixture.seed();initial=self.bound(mutation=True)
        args=dict(initial,graph_id=graph['graph_id'],revision=graph['revision'])
        result=self.owner.native_preflight(**args);self.assertTrue(result['value']['valid'],result)
        self.assertEqual(len(self.fixture.go_events),1);self.assertEqual(self.fixture.facts()['workspace_runs'],0)
        replay=self.cli(self.config('owner',self.fixture.owner.token),'native_preflight',args)
        self.assertEqual(replay,result);self.assertEqual(len(self.fixture.go_events),1)
        self.performed.append('Real owner SDK CPU preflight; named owner CLI exact request replay without another GO')
        with self.fixture.owner.bound(self.fixture.workspace):
            agent=self.fixture.workspace.access.issue(dict(label='Native transport ordinary editor',scopes=['inspect','edit']))
        ordinary=ProjectFilesClient(api.AgentClient(self.fixture.origin,agent['token'],self.fixture.owner.catalog_id,timeout=60))
        denied=dict(self.bound(mutation=True),graph_id=graph['graph_id'],graph_revision=graph['revision'],validation_token=result['value']['validation_token'])
        before=self.fixture.projection.session.snapshot
        with self.assertRaises(api.AgentAPIError) as error:ordinary.native_submit(**denied)
        self.assertEqual(error.exception.status,403);self.assertEqual(error.exception.code,'forbidden');self.assertEqual(self.fixture.projection.session.snapshot,before)
        self.assertEqual(len(self.fixture.go_events),1);self.assertEqual(self.fixture.facts()['workspace_runs'],0)
        negative=self.cli(self.config('agent',agent['token']),'native_submit',denied,owner=False,success=False)
        self.assertEqual((json.loads(negative.stderr)['status'],json.loads(negative.stderr)['code']),(403,'forbidden'))
        self.performed.append('Actual SDK and named CLI ordinary editor submission denied before probe/admission effects')
        owner_config=self.config('mcp-owner',self.fixture.owner.token)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_stdio.py'),'--project-files-owner','--config',str(owner_config)],cwd=str(ROOT),env=self.environment)
            with (self.path/'mcp.stderr').open('w+') as diagnostics:
                async with stdio_client(params,errlog=diagnostics) as (reader,writer):
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=60)) as session:
                        await session.initialize();tools={tool.name:tool for tool in (await session.list_tools()).tools}
                        for action in ('native_preflight','native_submit','native_retry','native_reconcile','execution_health'):
                            self.assertIn('project_files_'+action,tools)
                        self.assertEqual(tools['project_files_execution_health'].outputSchema,api.operation('project_files.execution_health',2)['outputSchema'])
                        async def call(action,arguments,status=200):
                            response=await session.call_tool('project_files_'+action,arguments);envelope=response.structuredContent
                            self.assertEqual(envelope['status'],status,envelope);self.assertEqual(response.isError,status>=400)
                            api.validate_output('project_files.'+action,envelope,2 if action=='execution_health' else 1)
                            return envelope['result']
                        self.assertEqual(await call('native_preflight',args),result);self.assertEqual(len(self.fixture.go_events),1)
                        stale=dict(args,request_key=uuid.uuid4().hex,graph_revision=graph['revision'],validation_token=result['value']['validation_token']);stale.pop('revision')
                        rejected=await call('native_submit',stale,status=409);self.assertEqual(rejected['code'],'stale_project')
                        await call('native_retry',dict(self.bound(mutation=True),run_id='9'*32),status=409)
                        self.assertEqual(len(self.fixture.go_events),1);self.assertEqual(self.fixture.facts()['workspace_runs'],0)
                        self.fixture.install_fault()
                        failed_args=dict(self.bound(mutation=True),graph_id=graph['graph_id'],revision=graph['revision'])
                        response=await session.call_tool('project_files_native_preflight',failed_args)
                        self.assertTrue(response.isError,response);self.assertEqual(response.structuredContent['status'],503,response.structuredContent)
                        api.validate_output('project_files.native_preflight',response.structuredContent)
                        self.assertEqual(self.fixture.fired,[True]);self.assertEqual(len(self.fixture.go_events),1)
                        self.fixture.clear_fault();current=self.bound()
                        health=await call('execution_health',current)
                        phases=health['value']['native_phases']['items'];failed=[p for p in phases if p['state'] in ('ready','go_intent','unknown')]
                        self.assertEqual(len(failed),1,phases);phase_id=failed[0]['phase_id']
                        self.assertEqual(health['checkpoint'],current['checkpoint'])
                        cli_health=self.cli(owner_config,'execution_health',current)
                        self.assertEqual(cli_health,health)
                        unknown=self.cli(owner_config,'native_reconcile',dict(binding=current['binding'],expected_checkpoint=current['checkpoint'],phase_id='0'*32),success=False)
                        self.assertEqual(json.loads(unknown.stderr)['status'],409);self.assertEqual(len(self.fixture.go_events),1)
                        recovered=await call('native_reconcile',dict(binding=current['binding'],expected_checkpoint=current['checkpoint'],phase_id=phase_id))
                        self.assertEqual(recovered['value']['state'],'failed');self.assertEqual(len(self.fixture.go_events),1)
                        self.assertFalse(self.fixture.facts()['pending']);self.assertTrue(self.fixture.projection.session.available)
                        self.performed.append('Actual owner MCP exact preflight replay, real deferred FK failure with zero additional GO, named CLI health v2 current phase and foreign-phase refusal; original owner MCP reconciliation')
        anyio.run(exercise)
        self.assertEqual(self.fixture.facts()['workspace_runs'],0)
        from test_project_files_http import canonical_bytes
        for raw in canonical_bytes(self.fixture.external/'alpha').values():
            self.assertNotIn(self.fixture.owner.token.encode(),raw);self.assertNotIn(agent['token'].encode(),raw)
        self.completed=True


def serve_fixture():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--serve',action='store_true');parser.add_argument('--root',type=Path,required=True);parser.add_argument('--cold',action='store_true');args=parser.parse_args()
    frozen_subject();fixture=NativePublicFixture(args.root,cold=args.cold)
    print(json.dumps(dict(origin=fixture.origin,control=str(fixture.control),external=str(fixture.external))),flush=True)
    try:
        for line in sys.stdin:
            command=json.loads(line);action=command['action']
            try:
                if action=='seed':value=fixture.seed()
                elif action=='install_fault':value=fixture.install_fault()
                elif action=='clear_fault':fixture.clear_fault();value={'cleared':True}
                elif action=='facts':value=fixture.facts()
                elif action=='stop':print(json.dumps(dict(id=command['id'],result={'stopped':True})),flush=True);break
                else:raise AssertionError('Unknown fixture command')
                print(json.dumps(dict(id=command['id'],result=value)),flush=True)
            except BaseException as error:
                print(json.dumps(dict(id=command['id'],error=type(error).__name__+': '+str(error))),flush=True)
    finally:fixture.close()


if __name__=='__main__':
    if '--serve' in sys.argv:serve_fixture()
    else:unittest.main()
