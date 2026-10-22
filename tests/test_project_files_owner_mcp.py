"""Explicit project-owner MCP mode over real stdio, HTTP and disposable PG.

The qualification subject is a separate immutable copy of the accepted M4
client source plus exactly this test and the explicit MCP profile change.
No runtime, recipe, provider or scientific execution occurs in this fixture.
"""
from datetime import timedelta
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch
import uuid

import agent_api
import mcp_stdio
import test_project_files_http as http_fixture

ROOT=Path(__file__).resolve().parents[1]
SDK_AVAILABLE=all(importlib.util.find_spec(name) for name in ('mcp','anyio','jsonschema'))


def subject():
    name=os.environ.get('TULDOK_OWNER_MCP_MANIFEST')
    if not name:raise AssertionError('Provide the immutable owner-MCP qualification manifest')
    path=Path(name);value=json.loads(path.read_text())
    if value['qualification_copy']!=str(ROOT):raise AssertionError('Tests must run in the selected immutable copy')
    current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in value['files']}
    if current!=value['files']:raise AssertionError('Immutable owner-MCP source changed before the test')
    return dict(manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                parent_manifest_sha256=value['parent_manifest_sha256'],files=current)


@unittest.skipUnless(SDK_AVAILABLE,'Requires the approved optional MCP dependencies')
class OwnerModeSelection(unittest.TestCase):
    def test_owner_opt_in_selects_only_existing_finite_owner_client_before_serving(self):
        import anyio
        owner=Mock();order=[];owner.bootstrap.side_effect=lambda:order.append('bootstrap')
        def ready(function,client,*args):
            self.assertIs(function,mcp_stdio.serve);self.assertIs(client,owner)
            self.assertEqual(order,['bootstrap']);order.append('serve')
        with (patch.object(agent_api.ProjectFilesOwnerClient,'from_config',return_value=owner) as selected,
              patch.object(agent_api.AgentClient,'from_config',side_effect=AssertionError('No implicit agent fallback')),
              patch.object(anyio,'run',side_effect=ready)):
            self.assertEqual(mcp_stdio.main(['--config','fixture-only','--project-files-owner']),0)
        selected.assert_called_once_with('fixture-only');self.assertEqual(order,['bootstrap','serve'])

    def test_default_agent_and_owner_bootstrap_refusal_never_fall_back(self):
        import anyio
        agent=Mock()
        with (patch.object(agent_api.AgentClient,'from_config',return_value=agent) as selected,
              patch.object(agent_api.ProjectFilesOwnerClient,'from_config',side_effect=AssertionError('Owner mode requires flag')),
              patch.object(anyio,'run') as run):
            self.assertEqual(mcp_stdio.main(['--config','fixture-only']),0)
            self.assertIs(run.call_args.args[1],agent);selected.assert_called_once()
        owner=Mock();owner.bootstrap.side_effect=agent_api.AgentAPIError('Refused fixture identity.','unauthenticated',401)
        with (patch.object(agent_api.ProjectFilesOwnerClient,'from_config',return_value=owner),
              patch.object(agent_api.AgentClient,'from_config',side_effect=AssertionError('No fallback after owner refusal')),
              patch.object(anyio,'run') as run,patch('sys.stderr',new_callable=io.StringIO)):
            self.assertEqual(mcp_stdio.main(['--config','fixture-only','--project-files-owner']),1)
            run.assert_not_called()


@unittest.skipUnless(SDK_AVAILABLE,'Requires the approved optional MCP dependencies')
class TransferModeSelection(unittest.TestCase):
    def test_transfer_opt_in_selects_five_only_owner_client_before_serving(self):
        import anyio
        owner=Mock();order=[];owner.bootstrap.side_effect=lambda:order.append('bootstrap')
        self.assertEqual(agent_api.ProjectTransferOwnerClient.OPERATIONS,
                         frozenset('project_transfer.'+name for name in ('status','preview','report_page','stop','extract')))
        def ready(function,client,*args):
            self.assertIs(function,mcp_stdio.serve);self.assertIs(client,owner)
            self.assertEqual(order,['bootstrap']);order.append('serve')
        with (patch.object(agent_api.ProjectTransferOwnerClient,'from_config',return_value=owner) as selected,
              patch.object(agent_api.ProjectFilesOwnerClient,'from_config',side_effect=AssertionError('No file-owner fallback')),
              patch.object(agent_api.AgentClient,'from_config',side_effect=AssertionError('No agent fallback')),
              patch.object(anyio,'run',side_effect=ready)):
            self.assertEqual(mcp_stdio.main(['--config','fixture-only','--project-transfer-owner']),0)
        selected.assert_called_once_with('fixture-only');self.assertEqual(order,['bootstrap','serve'])

    def test_owner_profile_flags_are_mutually_exclusive_before_configuration_read(self):
        with (patch.object(agent_api.ProjectTransferOwnerClient,'from_config') as transfer,
              patch.object(agent_api.ProjectFilesOwnerClient,'from_config') as files,
              patch.object(agent_api.AgentClient,'from_config') as agent,
              patch('sys.stderr',new_callable=io.StringIO)):
            with self.assertRaises(SystemExit) as refusal:
                mcp_stdio.main(['--config','fixture-only','--project-files-owner','--project-transfer-owner'])
            self.assertEqual(refusal.exception.code,2)
            transfer.assert_not_called();files.assert_not_called();agent.assert_not_called()

    def test_transfer_bootstrap_refusal_cannot_serve_or_select_another_authority(self):
        import anyio
        owner=Mock();owner.bootstrap.side_effect=agent_api.AgentAPIError('Fixture host credential refused.','unauthenticated',401)
        with (patch.object(agent_api.ProjectTransferOwnerClient,'from_config',return_value=owner),
              patch.object(agent_api.ProjectFilesOwnerClient,'from_config',side_effect=AssertionError('No file-owner fallback')),
              patch.object(agent_api.AgentClient,'from_config',side_effect=AssertionError('No agent fallback')),
              patch.object(anyio,'run') as run,patch('sys.stderr',new_callable=io.StringIO)):
            self.assertEqual(mcp_stdio.main(['--config','fixture-only','--project-transfer-owner']),1)
            owner.bootstrap.assert_called_once_with();run.assert_not_called()


@unittest.skipUnless(SDK_AVAILABLE and os.environ.get('TULDOK_DATABASE_URL'),
                     'Requires approved MCP dependencies and disposable PostgreSQL')
class OwnerMCPHTTP(unittest.TestCase):
    def setUp(self):
        self.subject=subject();self.performed=[];self.started=time.monotonic()
        self.fixture=http_fixture.ProjectFilesHTTP('test_authenticated_owner_only_selection_and_inert_control')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.receipt)
        self.environment={key:value for key,value in os.environ.items() if not key.startswith(('TULDOK_','PG'))}
        self.environment['PYTHONDONTWRITEBYTECODE']='1'

    def receipt(self):
        current={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in self.subject['files']}
        target=Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT','/workspace/scratch/tuldok-save-load-qa/artifacts'))/'owner-mcp'
        target.mkdir(parents=True,exist_ok=True)
        value=dict(test=self.id(),seconds=round(time.monotonic()-self.started,3),performed=self.performed,
            qualification_manifest_sha256=self.subject['manifest_sha256'],parent_manifest_sha256=self.subject['parent_manifest_sha256'],
            source_stable=current==self.subject['files'],mcp_stdio_sha256=current['mcp_stdio.py'],
            test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fixture='Actual MCP SDK stdio and authenticated HTTP; disposable PostgreSQL; authored text only')
        (target/(self._testMethodName+'-'+uuid.uuid4().hex+'.json')).write_text(json.dumps(value,indent=2)+'\n')
        self.assertEqual(current,self.subject['files'],'Immutable owner-MCP source changed during the test')

    def config(self,label,token,*,catalog_id=None):
        f=self.fixture;private=f.path/(label+'.token');config=f.path/(label+'.json')
        private.write_text(token+'\n');private.chmod(0o600)
        config.write_text(json.dumps(dict(endpoint=f.origin,catalog_id=catalog_id or f.owner.catalog_id,token_file=str(private),timeout=15)))
        config.chmod(0o600);return config

    def parameters(self,config,*,owner=True):
        from mcp import StdioServerParameters
        return StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_stdio.py'),'--config',str(config),
            *(['--project-files-owner'] if owner else [])],cwd=str(ROOT),env=self.environment)

    async def tools(self,session,*,owner):
        listed=(await session.list_tools()).tools;names={item.name for item in listed}
        self.assertTrue(names)
        if owner:
            allowed={agent_api.operation(name)['mcp_name'] for name in agent_api.ProjectFilesOwnerClient.OPERATIONS}
            self.assertTrue(names<=allowed)
            self.assertFalse({'context_get','identity_get','runs_recover_publication','runs_recover_coordinator'}&names)
            self.assertTrue({'project_files_new','project_files_open','project_files_save','project_files_save_as','project_files_close'}<=names)
        else:self.assertIn('context_get',names)
        return names

    async def tool(self,session,action,arguments,*,status=200):
        result=await session.call_tool('project_files_'+action,arguments)
        envelope=result.structuredContent
        self.assertEqual(envelope['status'],status,envelope)
        self.assertEqual(result.isError,status>=400)
        self.assertEqual(json.loads(result.content[0].text),envelope)
        return envelope['result']

    def test_owner_new_import_save_save_as_close_open_and_nonproject_profile_refusal(self):
        import anyio
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from mcp.shared.exceptions import McpError
        f=self.fixture;config=self.config('owner',f.owner.token)
        async def exercise():
            with (f.path/'owner-mcp.stderr').open('w+') as errors:
                async with stdio_client(self.parameters(config),errlog=errors) as (reader,writer):
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=20)) as session:
                        await session.initialize();names=await self.tools(session,owner=True)
                        self.performed.append(dict(owner_tool_count=len(names),all_tools_finite_project_files=True))
                        with self.assertRaises(McpError) as refusal:
                            await session.call_tool('runs_recover_publication',{})
                        self.assertEqual(refusal.exception.error.code,-32602)
                        initial=await self.tool(session,'status',{})
                        opened=await self.tool(session,'new',f.envelope(initial,root='fixture',directory='owner-source',name='Actual owner MCP 山'))
                        imported=await self.tool(session,'import_text',f.envelope(opened,asset=dict(
                            text=http_fixture.TEXT,name='Actual owner MCP authored observation',groups=['owner-mcp'],parents=[],rights='Owned synthetic fixture')))
                        state=await self.tool(session,'status',{});source_id=state['project']['project_id']
                        source_before=http_fixture.canonical_bytes(f.external/'owner-source')
                        saved=await self.tool(session,'save',f.envelope(state))
                        self.assertEqual(saved['project'],state['project'])
                        fork=await self.tool(session,'save_as',f.envelope(saved,root='fixture',directory='owner-fork',name='Independent MCP Ω'))
                        current=fork['state'];self.assertNotEqual(current['project']['project_id'],source_id)
                        self.assertEqual(http_fixture.canonical_bytes(f.external/'owner-source'),source_before)
                        closed=await self.tool(session,'close',f.envelope(current));self.assertEqual(closed['state'],'no_project_open')
                        reopened=await self.tool(session,'open',f.envelope(closed,root='fixture',directory='owner-fork'))
                        self.assertEqual(reopened['project'],current['project'])
                        page=await self.tool(session,'query',dict(binding=reopened['binding'],checkpoint=reopened['project']['checkpoint']))
                        self.assertEqual(len(page['items']),1);record_id=page['items'][0]['id']
                        self.assertNotEqual(record_id,imported['record']['id'])
                        actual=await self.tool(session,'get',dict(record_id=record_id,binding=reopened['binding'],checkpoint=reopened['project']['checkpoint']))
                        self.assertEqual(actual['record']['text'],http_fixture.TEXT)
                        self.assertIsNone(f.workspace._projection.execution._runs)
                        self.performed.extend(['Actual owner MCP New/import_text/Save/SaveAs/Close/Open completed',
                            'Independent project and record IDs; original source bytes exact; Unicode text cold restored',
                            'Nonproject publication owner tool refused at MCP profile boundary; no execution owner constructed'])
                errors.seek(0);self.assertNotIn(f.owner.token,errors.read())
        anyio.run(exercise)

    def test_bootstrap_denies_wrong_identity_revoked_and_other_catalog_without_fallback(self):
        f=self.fixture
        with f.owner.bound(f.workspace):
            agent=f.workspace.access.issue(dict(label='MCP denial fixture agent',scopes=['inspect','edit']))
        cases=[('owner-without-optin',self.config('owner-default',f.owner.token),False,f.owner.token),
               ('agent-in-owner-mode',self.config('agent-owner-mode',agent['token']),True,agent['token'])]
        saved=(f.workspace,f.owner,f.origin)
        f.select_host(f.path/'other-control',{'fixture':f.external})
        other=f.owner
        f.workspace,f.owner,f.origin=saved
        cases.append(('other-catalog-owner',self.config('other-owner',other.token),True,other.token))
        def refused(label,config,owner,token):
            command=[sys.executable,str(ROOT/'mcp_stdio.py'),'--config',str(config),*(['--project-files-owner'] if owner else [])]
            result=subprocess.run(command,input='',cwd=ROOT,env=self.environment,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,1,(label,result.stdout,result.stderr));self.assertEqual(result.stdout,'')
            self.assertNotIn(token,result.stderr);self.assertNotIn(f.origin,result.stderr)
            self.performed.append(label+' refused before MCP service initialization')
        for case in cases:refused(*case)
        with f.owner.bound(f.workspace):f.workspace.access.revoke(f.owner.identity['credential_id'])
        refused('revoked-owner',self.config('revoked-owner',f.owner.token),True,f.owner.token)
        self.assertEqual(list(f.external.iterdir()),[])

    def test_revocation_after_owner_bootstrap_denies_mutation_and_retains_no_project(self):
        import anyio
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        f=self.fixture;config=self.config('revoke-after-start',f.owner.token)
        async def exercise():
            with (f.path/'revoked-mcp.stderr').open('w+') as errors:
                async with stdio_client(self.parameters(config),errlog=errors) as (reader,writer):
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=20)) as session:
                        await session.initialize();await self.tools(session,owner=True)
                        state=await self.tool(session,'status',{})
                        with f.owner.bound(f.workspace):f.workspace.access.revoke(f.owner.identity['credential_id'])
                        denial=await self.tool(session,'new',f.envelope(state,root='fixture',directory='revoked-write',name='Denied'),status=401)
                        self.assertEqual(denial['code'],'unauthenticated')
                        self.assertFalse((f.external/'revoked-write').exists());self.assertIsNone(f.workspace._store)
                        self.performed.append('Current HTTP credential revocation after MCP bootstrap prevents New without a filesystem effect')
                errors.seek(0);self.assertNotIn(f.owner.token,errors.read())
        anyio.run(exercise)

    def test_default_agent_mcp_still_reads_edits_and_cannot_use_owner_lifecycle(self):
        import anyio
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        f=self.fixture;f.action('new',root='fixture',directory='agent-source',name='Default agent fixture')
        with f.owner.bound(f.workspace):agent=f.workspace.access.issue(dict(label='Default MCP editor',scopes=['inspect','edit']))
        config=self.config('default-agent',agent['token'])
        async def exercise():
            with (f.path/'agent-mcp.stderr').open('w+') as errors:
                async with stdio_client(self.parameters(config,owner=False),errlog=errors) as (reader,writer):
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=20)) as session:
                        await session.initialize();await self.tools(session,owner=False)
                        current=await self.tool(session,'status',{})
                        result=await self.tool(session,'import_text',f.envelope(current,asset=dict(text='Default agent exact text',name='Agent note',groups=['agent'],parents=[],rights='Owned fixture')))
                        self.assertEqual(result['record']['text'],'Default agent exact text')
                        current=await self.tool(session,'status',{});before=http_fixture.canonical_bytes(f.external/'agent-source')
                        await self.tool(session,'save_as',f.envelope(current,root='fixture',directory='agent-denied',name='Denied'),status=403)
                        self.assertFalse((f.external/'agent-denied').exists());self.assertEqual(http_fixture.canonical_bytes(f.external/'agent-source'),before)
                        self.performed.append('Unchanged default agent MCP can inspect/edit; owner SaveAs returns403 with no canonical effect')
                errors.seek(0);self.assertNotIn(agent['token'],errors.read())
        anyio.run(exercise)
