"""Real M2 public acceptance using disposable PostgreSQL and authored fixtures.

No training, runtime preflight, provider or user catalog belongs to this suite.
Run only after the lead enables M2 and freezes the complete working source.
"""
import base64
from datetime import timedelta
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

from PIL import Image
import psycopg

import agent_api
import project_workspace
import test_project_files_http as m1

ROOT = Path(__file__).resolve().parents[1]
NOTE = 'M2 retained rationale café 山 — exact authored scientific note.'
RIGHTS = 'Owned synthetic source; corrected by M2 acceptance café 山.'
SOURCE_FILES = ('app.py','agent_api.py','access.py','project_workspace.py','project_dispatch.py',
    'project_projection.py','project_data.py','project_sources.py','project_material.py',
    'project_history.py','project_producers.py','project_session.py','project_store.py',
    'static/project-files.js','static/project-files.html','tuldok_client.py','project_cli.py','mcp_stdio.py')


def subject_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def authored_source(root):
    from qualify_scientific_fields import neutral_bundle
    raw=neutral_bundle();(root/'observed-fields.zip').write_bytes(raw)
    manifest={'schema_version':1,'id':uuid.uuid4().hex,'name':'Authored observed fields café 山',
        'data':[{'id':'fields','label':'Exact authored scientific array','path':'observed-fields.zip','sha256':hashlib.sha256(raw).hexdigest()}],
        'recipes':[],'evidence':[],'requirements':[]}
    (root/'source-project.json').write_text(json.dumps(manifest,indent=3,ensure_ascii=False)+'\n')
    return manifest,raw


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable real local PostgreSQL')
class ProjectFilesM2HTTP(unittest.TestCase):
    cleanup_owned=m1.ProjectFilesHTTP.cleanup_owned
    select_host=m1.ProjectFilesHTTP.select_host
    request=m1.ProjectFilesHTTP.request
    state=m1.ProjectFilesHTTP.state
    envelope=m1.ProjectFilesHTTP.envelope
    action=m1.ProjectFilesHTTP.action
    create=m1.ProjectFilesHTTP.create

    def setUp(self):
        self.assertTrue(project_workspace.M2_ENABLED,'Lead must enable and freeze M2 before acceptance execution')
        self.subject=subject_hashes();self.started=time.monotonic();self.operations=[]
        m1.ProjectFilesHTTP.setUp(self)
        self.addCleanup(self.receipt)

    def receipt(self):
        directory=Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT','/workspace/scratch/tuldok-save-load-qa/artifacts'))/'m2-http'
        directory.mkdir(parents=True,exist_ok=True)
        current=subject_hashes()
        (directory/(self._testMethodName+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps({
            'test':self.id(),'seconds':round(time.monotonic()-self.started,3),'operations':self.operations,
            'source_sha256':self.subject,'end_sha256':current,'source_stable':current==self.subject,
            'fixture':'Disposable authored synthetic inputs; no runtime execution or scientific validity claim.'},indent=2)+'\n')
        self.assertEqual(current,self.subject,'Product source changed during actual acceptance')

    def arguments(self, action, **fields):
        op=agent_api.operation('project_files.'+action)
        state=self.state()
        bound=(self.envelope(state) if op['side_effects'] else
               {'binding':state['binding'],'checkpoint':state['project']['checkpoint']})
        return dict(bound,**fields)

    def transport(self, action, arguments, *, token=None):
        name='project_files.'+action
        method,target,body=agent_api.project_request(name,arguments)
        headers={'Authorization':'Bearer '+(token or self.owner.token),'Content-Type':'application/json',
                 'Origin':self.origin,'Tuldok-Operation-Contract':agent_api.selected_header(name)}
        request=Request(self.origin+target,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),
                        headers=headers,method=method)
        try:response=urlopen(request,timeout=30)
        except HTTPError as error:response=error
        with response:status,value=response.status,json.load(response)
        self.operations.append({'operation':name,'status':status})
        return status,value

    def call(self, action, *, token=None, **fields):
        status,envelope=self.transport(action,self.arguments(action,**fields),token=token)
        self.assertEqual(status,200,envelope)
        self.assertEqual(envelope['binding'],self.state()['binding'])
        return envelope['value']

    def data(self, record_id):return self.call('data_get',record_id=record_id)

    def image(self):
        out=io.BytesIO();Image.new('RGB',(20,12),'#3355aa').save(out,'PNG')
        raw=out.getvalue()
        row=self.call('data_import_image',image=base64.b64encode(raw).decode(),name='Authored blue image café 山',
                      groups=['m2-image'],rights='Owned synthetic pixels')
        return row,raw

    def retain_authored_history(self):
        # Import is M5. Author this explicitly synthetic archived observation
        # through the real closed codec; public readers/disclosure stay real.
        from test_project_history import legacy_run
        from project_history import capture_run,declarations
        projection=self.workspace._projection
        run=legacy_run(projection.project_id)
        run['source_records']=[{'id':'frozen-example','kind':'text','split':'test',
            'text':'PRIVATE-HOLDOUT-M2-SENTINEL','target':'PRIVATE-TARGET-M2-SENTINEL'}]
        run['evidence_context']={'fixture':'PRIVATE-CONTEXT-M2-SENTINEL'}
        record=capture_run(run,payloads=[])
        before=projection.session.snapshot
        records=before['records']+[record,*declarations(record)]
        projection.validate_records(records)
        snapshot=projection.store.commit(records,before['checkpoint'],uuid.uuid4().hex,'e'*64)
        projection.session.adopt(snapshot)
        return run,record

    def config(self,name,token):
        secret=self.path/(name+'.token');secret.write_text(token+'\n');secret.chmod(0o600)
        config=self.path/(name+'.json');config.write_text(json.dumps({'endpoint':self.origin,
            'catalog_id':self.owner.catalog_id,'token_file':str(secret),'timeout':30}));config.chmod(0o600)
        return config

    def test_public_mixed_authoring_git_clone_and_cold_reconstruction(self):
        self.create();image,raw=self.image()
        image=self.call('data_annotate',record_id=image['id'],revision=image['revision'],source_revision=image['source_revision'],
            task='image_caption',annotation={'caption':NOTE},groups=['m2-image','m2-review'],review='human_reviewed')
        corrected=self.call('data_rights',record_id=image['id'],revision=image['revision'],source_revision=image['source_revision'],note=RIGHTS)
        image=corrected['record'];self.assertEqual(image['provenance']['rights_note_correction']['note'],RIGHTS)
        history=self.call('data_history',record_id=image['id'],limit=4)
        self.assertTrue(any(row['annotation']=={'caption':NOTE} for row in history['items']))
        selection=self.call('selection_create',document={'name':'Frozen image revision 山',
            'items':[{key:image[key] for key in ('id','revision','source_revision')}]})
        search=self.call('search_create',document={'name':'Entered exact source search 山',
            'criteria':{'q':'café','kind':'image','review':'','sort':'newest','task':'','label':'','group':'','rights':''}})
        search=self.call('search_rename',search_id=search['id'],revision=1,name='Renamed saved search 山')
        definitions=self.call('definitions')
        template=next(item['model_template'] for item in definitions['recipes'] if item.get('model_template'))
        model=self.call('model_create',**dict(template,name='Retained safe model draft 山'))
        model=self.call('model_save',model_id=model['id'],revision=model['revision'],document=dict(model,name='Revised model intent 山'))
        material=self.call('model_publish',model_id=model['id'],revision=model['revision'])
        self.assertEqual(self.call('model_material',ref=material['ref'],verify=True),material)
        manifest,science=authored_source(self.external)
        registered=self.call('source_register',root='fixture',manifest_path='source-project.json')
        snapshotref={key:registered[key] for key in ('origin_catalog_id','project_id','manifest_sha256')}
        references=self.call('source_references',**snapshotref,limit=1)
        self.assertEqual(references['items'][0]['sha256'],hashlib.sha256(science).hexdigest())
        field=self.call('data_import_scientific',snapshot=snapshotref,reference_id='fields',expected_sha256=hashlib.sha256(science).hexdigest(),
            document={'name':'Observed field sequence café 山','groups':['m2-science'],'rights':'Owned authored arrays'})
        self.assertEqual(field['kind'],'field_sequence')
        field=self.call('data_annotate',record_id=field['id'],revision=field['revision'],source_revision=field['source_revision'],
            task=field['task'],annotation={'note':NOTE},groups=field['groups'],review='human_reviewed')
        policy={'format':'selection_policy_v1','metric_definition_sha256':'b'*64,'checkpoint_rule':'explicit',
            'replicate_reduce':'individual','required_capabilities':[],'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
        study=self.call('study_create',name='Scientific intent only 山',limits={'attempt_slots':3,'admitted_wall_seconds':100,
            'retained_bytes':1000000,'peak_staging_bytes':1000000},policy=policy)
        study=self.call('study_save',study_id=study['id'],revision=study['revision'],name='Revised scientific intent 山',limits=study['limits'],policy=study['policy'])
        origin=self.state()['project']['project_id']
        study_view=self.call('study',study_id=study['id'],origin_catalog_id=origin,limit=1)
        self.assertEqual(study_view['study']['revision'],2)
        self.assertTrue(all(value==0 for value in study_view['charged'].values()))
        run,archived=self.retain_authored_history()
        visible=self.call('run',run_id=run['id'],origin_catalog_id=origin,limit=1)
        self.assertNotIn('PRIVATE-',json.dumps(visible))
        descriptor=visible['document']
        document_arguments=self.arguments('run_document_segment',run_id=run['id'],origin_catalog_id=origin,
            expected_sha256=descriptor['sha256'],offset=0,limit=262144)
        self.assertEqual(self.transport('run_document_segment',document_arguments)[0],403)
        with self.owner.bound(self.workspace):
            inspector=self.workspace.access.issue({'label':'M2 inspect only','scopes':['inspect']})
        before_denial=m1.canonical_bytes(self.external/'alpha')
        self.assertEqual(self.transport('expose_holdout',self.arguments('expose_holdout',run_id=run['id'],origin_catalog_id=origin,
            reason='No scope should deny this request'),token=inspector['token'])[0],403)
        self.assertEqual(m1.canonical_bytes(self.external/'alpha'),before_denial)
        self.call('expose_holdout',run_id=run['id'],origin_catalog_id=origin,reason='Inspect this authored synthetic holdout on this installation.')
        segment=self.call('run_document_segment',run_id=run['id'],origin_catalog_id=origin,
            expected_sha256=descriptor['sha256'],offset=0,limit=262144)
        exact_document=base64.b64decode(segment['base64'])
        self.assertIn(b'PRIVATE-HOLDOUT-M2-SENTINEL',exact_document)
        self.assertEqual(hashlib.sha256(exact_document).hexdigest(),descriptor['sha256'])
        # Missing retained material is a real filesystem negative; restore exact
        # fixture bytes before Git/cold proof so no missing data is concealed.
        blob=material['material']['source_closure'][0]['blob']
        payload=self.external/'alpha'/'artifacts'/'sha256'/blob['sha256'];saved=payload.read_bytes();payload.unlink()
        (self.external/'retained-model-source.bin').write_bytes(saved)
        try:
            self.assertEqual(self.call('artifact_status',sha256=blob['sha256'])['state'],'missing')
            status,error=self.transport('model_material',self.arguments('model_material',ref=material['ref'],verify=True))
            self.assertEqual(status,404,error)
            self.assertEqual(self.call('model_material',ref=material['ref']),material)
            self.call('artifact_resolve',sha256=blob['sha256'],root='fixture',path='retained-model-source.bin')
            self.assertEqual(self.call('artifact_status',sha256=blob['sha256'])['state'],'verified')
            self.assertEqual(payload.read_bytes(),saved)
        finally:
            if not payload.exists():payload.write_bytes(saved);payload.chmod(0o400)
        expected={'image':self.data(image['id']),'image_history':self.call('data_history',record_id=image['id'],limit=4),
            'field':self.data(field['id']),'selection':self.call('selection_get',selection_id=selection['id']),
            'searches':self.call('searches'),'model':self.call('model_get',model_id=model['id']),
            'material':self.call('model_material',ref=material['ref'],verify=True),'study':study_view}
        self.action('save');source_state=self.state();self.action('close')
        source=self.external/'alpha';(source/'scripts').mkdir()
        (source/'scripts'/'sentinel.py').write_text("from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('bad')\n")
        before=m1.canonical_bytes(source)
        forbidden=(self.owner.token.encode(),hashlib.sha256(self.owner.token.encode()).hexdigest().encode(),os.environ['TULDOK_DATABASE_URL'].encode())
        for secret in forbidden:self.assertFalse(any(secret in raw for raw in before.values()),'Actual current credential or database binding leaked')
        git_env=dict(os.environ,GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_NOSYSTEM='1',GIT_TERMINAL_PROMPT='0')
        def git(*args):subprocess.run(['git',*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=git_env,timeout=30)
        git('init','-q','--template=',str(source));git('-C',str(source),'add','.')
        git('-C',str(source),'-c','user.name=Disposable QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false',
            '-c','core.hooksPath=/dev/null','commit','-qm','Authored M2 acceptance fixture')
        coldroot=self.path/'cold-external';coldroot.mkdir();clone=coldroot/'clone'
        git('-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',str(source),str(clone))
        # Binary payloads are deliberately untracked. Transfer that owned
        # sidecar explicitly; Git alone proves the authored text inventory.
        shutil.copytree(source/'artifacts',clone/'artifacts')
        self.assertEqual(m1.canonical_bytes(clone),before)
        cold_dsn=os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']
        source_db=psycopg.conninfo.conninfo_to_dict(os.environ['TULDOK_DATABASE_URL'])['dbname']
        with psycopg.connect(cold_dsn) as connection:
            database,allowed=connection.execute('SELECT current_database(),has_database_privilege(current_user,%s,\'CONNECT\')',(source_db,)).fetchone()
            self.assertNotEqual(database,source_db);self.assertFalse(allowed)
        self.select_host(self.path/'cold-control',{'fixture':coldroot},cold_dsn)
        self.action('open',root='fixture',directory='clone');self.assertEqual(self.state()['project'],source_state['project'])
        self.assertEqual(self.data(image['id']),expected['image']);self.assertEqual(self.data(field['id']),expected['field'])
        self.assertEqual(self.call('data_history',record_id=image['id'],limit=4),expected['image_history'])
        self.assertEqual(self.call('selection_get',selection_id=selection['id']),expected['selection'])
        self.assertEqual(self.call('searches'),expected['searches']);self.assertEqual(self.call('model_get',model_id=model['id']),expected['model'])
        self.assertEqual(self.call('model_material',ref=material['ref'],verify=True),expected['material'])
        self.assertEqual(self.call('study',study_id=study['id'],origin_catalog_id=origin,limit=1),expected['study'])
        cold_run=self.call('run',run_id=run['id'],origin_catalog_id=origin,limit=1)
        self.assertNotIn('PRIVATE-',json.dumps(cold_run))
        self.assertEqual(cold_run['document'],descriptor)
        self.assertEqual(self.transport('run_document_segment',self.arguments('run_document_segment',run_id=run['id'],origin_catalog_id=origin,
            expected_sha256=descriptor['sha256'],offset=0,limit=262144))[0],403,'Historical disclosure is no current authority')
        status,error=self.transport('source_references',self.arguments('source_references',**snapshotref))
        self.assertEqual(status,409,error) # A historical path is no current source grant.
        self.assertFalse((clone/'scripts'/'EXECUTED').exists())
        self.action('save');self.assertEqual(m1.canonical_bytes(clone),before)

    def test_unpinned_scientific_reference_uses_current_observed_hash(self):
        self.create();manifest,raw=authored_source(self.external)
        manifest['data'][0].pop('sha256')
        (self.external/'source-project.json').write_text(json.dumps(manifest,ensure_ascii=False))
        registered=self.call('source_register',root='fixture',manifest_path='source-project.json')
        reference={key:registered[key] for key in ('origin_catalog_id','project_id','manifest_sha256')}
        item=self.call('source_references',**reference)['items'][0]
        self.assertNotIn('sha256',item);self.assertEqual(item['integrity'],'unverified')
        self.assertEqual(item['observed_sha256'],hashlib.sha256(raw).hexdigest())
        row=self.call('data_import_scientific',snapshot=reference,reference_id=item['id'],expected_sha256=item['observed_sha256'],
            document={'name':'Unpinned but explicitly measured source','groups':['m2-unpinned'],'rights':'Owned authored data'})
        self.assertEqual(row['source_sha256'],item['observed_sha256'])

    @unittest.skipUnless(importlib.util.find_spec('mcp'),'Requires pinned real MCP optional dependencies')
    def test_real_sdk_cli_mcp_roles_lost_reply_and_stale_binding(self):
        import anyio
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        from tuldok_client import ProjectFilesClient
        owner=agent_api.ProjectFilesOwnerClient(self.origin,self.owner.token,self.owner.catalog_id,timeout=30)
        owner.bootstrap();owner_files=ProjectFilesClient(owner)
        opened=owner_files.new(root='fixture',directory='adapters',name='M2 actual adapters 山',**self.envelope())
        with self.owner.bound(self.workspace):
            credential=self.workspace.access.issue({'label':'M2 transport editor','scopes':['inspect','edit']})
        client=agent_api.AgentClient(self.origin,credential['token'],self.owner.catalog_id,timeout=30);client.bootstrap()
        files=ProjectFilesClient(client)
        imported=files.data_import_text(**self.arguments('data_import_text',text='M2 SDK authored café 山',name='Adapter source',groups=['m2-adapter'],rights='Owned fixture'))
        record=imported['value']
        denied=self.arguments('data_annotate',record_id=record['id'],revision=record['revision'],source_revision=record['source_revision'],
            task='text_corpus',annotation={'note':NOTE},groups=record['groups'],review='human_reviewed')
        before=m1.canonical_bytes(self.external/'adapters')
        self.assertEqual(client.call('project_files.data_annotate',denied)['status'],403)
        self.assertEqual(client.call('project_files.study_create',self.arguments('study_create',name='Denied owner study',
            limits={'attempt_slots':1,'admitted_wall_seconds':1,'retained_bytes':1,'peak_staging_bytes':1},
            policy={'format':'selection_policy_v1','metric_definition_sha256':'b'*64,'checkpoint_rule':'explicit','replicate_reduce':'individual',
                'required_capabilities':[],'numerical_acceptance':'diagnostic','tie_break':'trial_id'}))['status'],403)
        self.assertEqual(m1.canonical_bytes(self.external/'adapters'),before)
        config=self.config('actual-agent',credential['token']);args=self.path/'cli-arguments.json'
        arguments=dict(denied,review='draft');args.write_text(json.dumps(arguments,ensure_ascii=False))
        environment={key:value for key,value in os.environ.items() if not key.startswith(('TULDOK_','PG'))}
        result=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),'file-data-annotate','--arguments',str(args)],
            cwd=ROOT,env=environment,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn(credential['token'],result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['value']['annotation'],{'note':NOTE})
        async def exercise():
            parameters=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_stdio.py'),'--config',str(config)],cwd=str(ROOT),env=environment)
            with (self.path/'m2-mcp.stderr').open('w+') as errors:
                async with stdio_client(parameters,errlog=errors) as (reader,writer):
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=20)) as session:
                        await session.initialize()
                        names={tool.name for tool in (await session.list_tools()).tools}
                        self.assertTrue({'project_files_data_get','project_files_data_rights','project_files_studies'}<=names)
                        request=self.arguments('data_get',record_id=record['id'])
                        observed=await session.call_tool('project_files_data_get',request)
                        self.assertFalse(observed.isError);self.assertEqual(observed.structuredContent['status'],200)
                        current=observed.structuredContent['result']['value']
                        rights=self.arguments('data_rights',record_id=record['id'],revision=current['revision'],source_revision=current['source_revision'],note=RIGHTS)
                        saved=await session.call_tool('project_files_data_rights',rights)
                        self.assertFalse(saved.isError);self.assertEqual(saved.structuredContent['result']['value']['record']['provenance']['rights_note_correction']['note'],RIGHTS)
        anyio.run(exercise)
        # Discard the actual successful response body, then reconcile with the
        # exact same request key; no mutation retry is hidden by an adapter.
        arguments=self.arguments('data_import_text',text='Lost response exact source 山',name='Lost reply',groups=['m2-lost'],rights='Owned fixture')
        method,target,body=agent_api.project_request('project_files.data_import_text',arguments)
        connection=http.client.HTTPConnection('127.0.0.1',self.hosts[-1][1].server_port,timeout=30)
        connection.request(method,target,json.dumps(body).encode(),{'Authorization':'Bearer '+self.owner.token,
            'Content-Type':'application/json','Tuldok-Operation-Contract':agent_api.selected_header('project_files.data_import_text')})
        response=connection.getresponse();self.assertEqual(response.status,200);connection.close()
        committed=m1.canonical_bytes(self.external/'adapters')
        status,replayed=self.transport('data_import_text',arguments);self.assertEqual(status,200,replayed)
        self.assertEqual(m1.canonical_bytes(self.external/'adapters'),committed)
        old=self.state();self.action('close');self.action('open',root='fixture',directory='adapters')
        status,error=self.transport('data_get',{'binding':old['binding'],'checkpoint':old['project']['checkpoint'],'record_id':record['id']})
        self.assertEqual(status,409,error);self.assertEqual(m1.canonical_bytes(self.external/'adapters'),committed)


if __name__=='__main__':unittest.main()
