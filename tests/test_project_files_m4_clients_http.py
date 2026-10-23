"""Actual M4 SDK, CLI and MCP over an authenticated disposable HTTP server.

Requires lead-enabled M4 and an explicit frozen product manifest. No provider,
preflight, runtime capture, script execution or ambient user catalog is used.
"""
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid

import agent_api as api
import project_workspace
from tuldok_client import ProjectFilesClient
import test_project_files_http as m1

ROOT=Path(__file__).resolve().parents[1]


def frozen_subject():
    name=os.environ.get('TULDOK_M4_FREEZE_MANIFEST')
    if not name:raise AssertionError('Lead must provide TULDOK_M4_FREEZE_MANIFEST before actual acceptance')
    value=json.loads(Path(name).read_text());files=value['files']
    current={file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in files}
    if current!=files:raise AssertionError('Frozen product changed before actual acceptance')
    return dict(manifest_sha256=hashlib.sha256(Path(name).read_bytes()).hexdigest(),files=current)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ProjectFilesM4ClientsHTTP(unittest.TestCase):
    cleanup_owned=m1.ProjectFilesHTTP.cleanup_owned
    select_host=m1.ProjectFilesHTTP.select_host
    request=m1.ProjectFilesHTTP.request
    state=m1.ProjectFilesHTTP.state
    envelope=m1.ProjectFilesHTTP.envelope

    def setUp(self):
        self.assertTrue(project_workspace.M4_ENABLED,'Lead must enable M4 for actual public acceptance')
        self.subject=frozen_subject();self.performed=[];self.started=time.monotonic()
        m1.ProjectFilesHTTP.setUp(self)
        self.addCleanup(self.receipt)

    def receipt(self):
        current={file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in self.subject['files']}
        report=Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT','/workspace/scratch/tuldok-save-load-qa/artifacts'))/'m4-clients'
        report.mkdir(parents=True,exist_ok=True)
        (report/(self._testMethodName+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps(dict(
            test=self.id(),seconds=round(time.monotonic()-self.started,3),performed=self.performed,
            source=self.subject,end_sha256=current,source_stable=current==self.subject['files'],
            test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fixture='Disposable local PG; real HTTP/SDK/CLI/MCP transports; inert exact UTF8 files'),indent=2)+'\n')
        self.assertEqual(current,self.subject['files'],'Product changed during actual acceptance')

    def config(self,name,token):
        token_file=self.path/(name+'.token');config_file=self.path/(name+'.config.json')
        token_file.write_text(token+'\n');token_file.chmod(0o600)
        config_file.write_text(json.dumps(dict(endpoint=self.origin,catalog_id=self.owner.catalog_id,
            token_file=str(token_file),timeout=15)));config_file.chmod(0o600)
        return config_file

    @unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('anyio'), 'Requires optional locked MCP dependencies')
    def test_exact_file_revisions_save_as_and_current_role_through_sdk_cli_mcp(self):
        import anyio
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        owner=ProjectFilesClient(api.ProjectFilesOwnerClient(self.origin,self.owner.token,self.owner.catalog_id,timeout=15))
        initial=owner.status();opened=owner.new(root='fixture',directory='transport',name='Exact file project Ω',**self.envelope(initial))
        root=self.external/'transport';(root/'scripts').mkdir();(root/'notes').mkdir()
        sentinel=self.path/'must-not-execute'
        script=('from pathlib import Path\nPath('+repr(str(sentinel))+').write_text("executed")\n# inert NUL follows\n\0Ω 🌸\r\n').encode()
        (root/'scripts/inert.py').write_bytes(script);(root/'notes/empty.md').write_bytes(b'')
        with self.owner.bound(self.workspace):
            credential=self.workspace.access.issue({'label':'M4 current editor','scopes':['inspect','edit']})
        agent=api.AgentClient(self.origin,credential['token'],self.owner.catalog_id,timeout=15)
        self.assertEqual(agent.bootstrap()['identity']['kind'],'agent');files=ProjectFilesClient(agent)
        script_result=files.file_adopt(**self.envelope(),kind='script',path='scripts/inert.py',expected_revision=0,
            expected_sha256=hashlib.sha256(script).hexdigest())['value']
        empty_result=files.file_adopt(**self.envelope(),kind='note',path='notes/empty.md',expected_revision=0,
            expected_sha256=hashlib.sha256(b'').hexdigest())['value']
        def read():
            state=self.state();return dict(binding=state['binding'],checkpoint=state['project']['checkpoint'])
        self.assertEqual(files.file_get(**read(),file_id=script_result['id'])['value']['version']['text'].encode(),script)
        self.assertEqual(files.file_get(**read(),file_id=empty_result['id'])['value']['version']['text'],'')
        self.performed.append('Actual current-agent SDK adopts and reads exact NUL/Unicode and empty UTF8 files')
        agent_config=self.config('agent',credential['token']);owner_config=self.config('owner',self.owner.token)
        environment={key:value for key,value in os.environ.items() if not key.startswith(('TULDOK_','PG'))}
        environment['PYTHONDONTWRITEBYTECODE']='1'
        def cli(config,command,*,owner_mode=False,arguments=None,flags=()):
            command=[sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),
                     *(['--owner-project-files'] if owner_mode else []),command,*flags]
            if arguments is not None:
                path=self.path/('args-'+uuid.uuid4().hex+'.json');path.write_text(json.dumps(arguments));command+=['--arguments',str(path)]
            result=subprocess.run(command,cwd=ROOT,env=environment,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn(self.owner.token,result.stdout+result.stderr);self.assertNotIn(credential['token'],result.stdout+result.stderr)
            return json.loads(result.stdout)
        original=cli(agent_config,'file-file-get',arguments=dict(read(),file_id=script_result['id'],revision=1))
        self.assertEqual(original['value']['version']['text'].encode(),script)
        changed=script+b'# second authored observation\n';(root/'scripts/inert.py').write_bytes(changed)
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_stdio.py'),'--config',str(agent_config)],cwd=str(ROOT),env=environment)
            with (self.path/'mcp.stderr').open('w+') as errors:
                async with stdio_client(params,errlog=errors) as (reader,writer):
                    started=time.monotonic()
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=20)) as session:
                        await session.initialize();self.performed.append(dict(actual_mcp_initialize_seconds=round(time.monotonic()-started,3),deadline_seconds=20))
                        tools={tool.name for tool in (await session.list_tools()).tools}
                        self.assertTrue({'project_files_file_get','project_files_file_adopt','project_files_file_history'}<=tools)
                        async def tool(action,args):
                            result=await session.call_tool('project_files_'+action,args)
                            self.assertFalse(result.isError,result)
                            envelope=result.structuredContent;self.assertEqual(envelope['status'],200,envelope)
                            self.assertEqual(json.loads(result.content[0].text),envelope)
                            return envelope['result']
                        exact=await tool('file_get',dict(read(),file_id=script_result['id'],revision=1))
                        self.assertEqual(exact['value']['version']['text'].encode(),script)
                        adopted=await tool('file_adopt',dict(self.envelope(),kind='script',path='scripts/inert.py',expected_revision=1,
                            expected_sha256=hashlib.sha256(changed).hexdigest()))
                        self.assertEqual(adopted['value']['revision'],2)
                        page=await tool('file_history',dict(read(),file_id=script_result['id'],offset=0,limit=1))
                        self.assertEqual((page['value']['total'],page['value']['items'][0]['revision']),(2,1))
                        self.assertNotIn('text',page['value']['items'][0])
                        page=await tool('file_history',dict(read(),file_id=script_result['id'],offset=1,limit=1))
                        self.assertEqual(page['value']['items'][0]['revision'],2)
                errors.seek(0);self.assertNotIn(credential['token'],errors.read())
        anyio.run(exercise)
        self.performed.append('Actual MCP reads original NUL bytes, adopts revision2, pages metadata-only history')
        from test_project_material_fork import recipe
        original_recipe=recipe(self.state()['project']['project_id'])
        recipe_body={key:value for key,value in original_recipe.items() if key not in ('format','id','revision')}
        retained_recipe=files.recipe_create(**self.envelope(),**recipe_body)['value']
        self.performed.append('Actual SDK authors an inert recipe draft with explicit historical reference fields; no material preparation')
        source=self.state();args=self.envelope(source)
        denial=agent.call('project_files.save_as',dict(args,root='fixture',directory='denied',name='Denied'))
        self.assertEqual(denial['status'],403);self.assertFalse((self.external/'denied').exists())
        fork=cli(owner_config,'file-save-as',owner_mode=True,flags=[
            '--binding',args['binding'],'--expected-checkpoint',args['expected_checkpoint'],'--request-key',args['request_key'],
            '--root','fixture','--directory','independent','--name','Independent exact transport Ω'])
        self.assertNotEqual(fork['fork']['project_id'],source['project']['project_id'])
        self.assertEqual(fork['state'],self.state())
        self.assertEqual((self.external/'independent/scripts/inert.py').read_bytes(),changed)
        self.assertEqual((self.external/'independent/notes/empty.md').read_bytes(),b'')
        old=agent.call('project_files.file_get',dict(binding=source['binding'],checkpoint=source['project']['checkpoint'],file_id=script_result['id']))
        self.assertEqual(old['status'],409)
        observed=files.files_inspect(**read())['value']['items'];self.assertEqual(len(observed),2)
        self.assertTrue(all(item['state']=='unchanged' for item in observed))
        current=next(item for item in observed if item['kind']=='script')
        self.assertNotEqual(current['id'],script_result['id'])
        self.assertEqual(files.file_get(**read(),file_id=current['id'],revision=1)['value']['version']['text'].encode(),script)
        self.assertEqual(files.file_get(**read(),file_id=current['id'],revision=2)['value']['version']['text'].encode(),changed)
        intents=files.material_intents(**read())['value']['items']
        self.assertEqual(len(intents),1)
        intent=files.material_intent(**read(),family=intents[0]['family'],definition_id=intents[0]['definition_id'])['value']
        self.assertEqual(intent['current']['definition'],retained_recipe)
        self.assertEqual(intent['current']['definition']['runtime']['catalog_id'],source['project']['project_id'])
        self.assertNotEqual(intent['current']['catalog_id'],source['project']['project_id'])
        capabilities=files.material_intent_capabilities(**read())['value']['items']
        self.assertTrue(any(item['id']==intent['id'] and 'runtime' in item['requires_reselection'] for item in capabilities))
        self.assertFalse(sentinel.exists())
        self.performed.append('Actual owner CLI Save As selects independent identities; old binding rejected; both exact histories retained; script never executed')

    def test_fork_text_v1_refuses_before_mutation_and_v2_retains_exact_origin(self):
        files=ProjectFilesClient(api.ProjectFilesOwnerClient(self.origin,self.owner.token,self.owner.catalog_id,timeout=15))
        source=files.new(root='fixture',directory='text-source',name='Source for versioned text',**self.envelope(files.status()))
        original=files.import_text({'name':'Original authored Ω','text':'Exact scientific decision 山',
            'groups':['fixture'],'parents':[],'rights':'Owned text fixture'},**self.envelope(source))['record']
        fork=files.save_as(root='fixture',directory='text-fork',name='Versioned fork Ω',**self.envelope())
        current=files.status();query=files.query(binding=current['binding'],checkpoint=current['project']['checkpoint'])
        row=query['items'][0];self.assertNotEqual(row['id'],original['id'])
        read=dict(binding=current['binding'],checkpoint=current['project']['checkpoint'],record_id=row['id'])
        detail=files.get(row['id'],binding=current['binding'],checkpoint=current['project']['checkpoint'])
        provenance=detail['record']['provenance'];self.assertEqual(provenance['method'],'project_fork')
        self.assertEqual(provenance['origin']['project_id'],source['project']['project_id'])
        self.assertEqual(provenance['origin']['id'],original['id'])
        before=m1.canonical_bytes(self.external/'text-fork')
        transport=files.client
        route=api.operation('project_files.get',1)['path'].replace('{record_id}',row['id'])
        from urllib.parse import urlencode
        old=transport._request('GET',route+'?'+urlencode({k:v for k,v in read.items() if k!='record_id'}),selection=('project_files.get',1))
        self.assertEqual(old['status'],409,old);self.assertEqual(old['result']['code'],'unsupported')
        annotation=dict(revision=detail['record']['revision'],source_revision=detail['record']['source_revision'],
            task='text_corpus',annotation={'note':'New independent rationale Ω'},groups=detail['record']['groups'],review='draft')
        body=dict(self.envelope(current),annotation=annotation)
        old=transport._request('POST',route,body,selection=('project_files.annotate',1))
        self.assertEqual(old['status'],409,old);self.assertEqual(old['result']['code'],'unsupported')
        self.assertEqual(m1.canonical_bytes(self.external/'text-fork'),before)
        saved=files.annotate(row['id'],annotation,**self.envelope(current))
        self.assertEqual(saved['record']['provenance'],provenance)
        self.assertEqual(saved['record']['annotation'],annotation['annotation'])
        latest=files.get(row['id'],binding=saved['binding'],checkpoint=saved['checkpoint'],history_limit=4)
        self.assertEqual([r['revision'] for r in latest['history']],[2,1])
        self.assertTrue(all(r['provenance']==provenance for r in latest['history']))
        self.performed.append('Actual v1 get/annotate reject fork provenance before any canonical write; negotiated v2 reads and annotates exact origin/history')


if __name__=='__main__':unittest.main()
