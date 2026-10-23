"""Actual note-deletion SDK/CLI/MCP and cold fork, with no execution owners.

Explicit GO and an immutable M4 manifest are mandatory. Local fixture unlink is
an operator action; the public adoption endpoint never removes filesystem bytes.
"""
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import psycopg
from psycopg.conninfo import conninfo_to_dict

import agent_api as api
from tuldok_client import ProjectFilesClient
import test_project_files_m4_clients_http as m4

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and os.environ.get('TULDOK_NOTE_DELETION_GO')=='1',
                     'Requires explicit note-deletion qualification GO and disposable PostgreSQL')
class NoteDeletionClientsHTTP(unittest.TestCase):
    cleanup_owned=m4.ProjectFilesM4ClientsHTTP.cleanup_owned
    select_host=m4.ProjectFilesM4ClientsHTTP.select_host
    request=m4.ProjectFilesM4ClientsHTTP.request
    state=m4.ProjectFilesM4ClientsHTTP.state
    envelope=m4.ProjectFilesM4ClientsHTTP.envelope
    config=m4.ProjectFilesM4ClientsHTTP.config
    setUp=m4.ProjectFilesM4ClientsHTTP.setUp
    receipt=m4.ProjectFilesM4ClientsHTTP.receipt

    @unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('anyio'),
                         'Requires the optional locked MCP dependencies')
    def test_real_note_deletion_restore_history_and_cold_independent_fork(self):
        import anyio
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        cold_dsn=os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']
        source_db=conninfo_to_dict(os.environ['TULDOK_DATABASE_URL'])['dbname']
        with psycopg.connect(cold_dsn) as connection:
            database,source_connect=connection.execute('SELECT current_database(),has_database_privilege(current_user,%s,%s)',(source_db,'CONNECT')).fetchone()
        self.assertNotEqual(database,source_db);self.assertFalse(source_connect)
        owner=ProjectFilesClient(api.ProjectFilesOwnerClient(self.origin,self.owner.token,self.owner.catalog_id,timeout=20))
        owner.new(**self.envelope(),root='fixture',directory='notes',name='Note deletion transport Ω')
        project=self.external/'notes';(project/'notes').mkdir();note=project/'notes/scientist.md'
        text='Unique authored rationale Ω 山\r\nwith retained NUL\0and exact history.\n';raw=text.encode();sha=hashlib.sha256(raw).hexdigest()
        note.write_bytes(raw)
        adopted=owner.file_adopt(**self.envelope(),kind='note',path='notes/scientist.md',expected_revision=0,expected_sha256=sha)['value']
        file_id=adopted['id']
        def read():
            current=self.state();return dict(binding=current['binding'],checkpoint=current['project']['checkpoint'])
        deletion_args=dict(self.envelope(),path='notes/scientist.md',expected_revision=1,expected_sha256=sha)
        unchanged=self.state();raw_owner=owner.client
        denied=raw_owner.call('project_files.file_adopt_deletion',deletion_args)
        self.assertEqual(denied['status'],409);self.assertEqual(note.read_bytes(),raw);self.assertEqual(self.state(),unchanged)
        note.unlink()
        observed=owner.files_inspect(**read())['value']['items'][0]
        self.assertEqual((observed['state'],observed['expected_sha256']),( 'missing',sha))
        wrong=raw_owner.call('project_files.file_adopt_deletion',dict(deletion_args,expected_sha256='0'*64))
        self.assertEqual(wrong['status'],409);self.assertEqual(self.state(),unchanged)
        with self.owner.bound(self.workspace):
            limited=self.workspace.access.issue({'label':'Inspect note only','scopes':['inspect']})
        inspect=api.AgentClient(self.origin,limited['token'],self.owner.catalog_id,timeout=20)
        self.assertEqual(inspect.call('project_files.file_adopt_deletion',deletion_args)['status'],403)
        config=self.config('note-owner',self.owner.token)
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        for key in tuple(environment):
            if key.startswith(('TULDOK_','PG')):environment.pop(key)
        arguments_file=self.path/'delete.arguments.json';arguments_file.write_text(json.dumps(deletion_args))
        command=[sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),'--owner-project-files','file-file-adopt-deletion','--arguments',str(arguments_file)]
        result=subprocess.run(command,cwd=ROOT,env=environment,capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr);deleted=json.loads(result.stdout)
        self.assertEqual((deleted['value']['deleted'],deleted['value']['revision'],deleted['value']['sha256']),(True,2,None))
        self.assertFalse(note.exists());self.assertEqual(owner.file_adopt_deletion(**deletion_args),deleted)
        self.assertEqual(owner.file_get(**read(),file_id=file_id)['value']['version']['text'],None)
        self.performed.append('Real SDK existing-path/hash/role negatives have no effects; named owner CLI retains deletion and exact SDK replay returns the same ACK')
        restored='Explicit restored decision 🌸\n';restored_sha=hashlib.sha256(restored.encode()).hexdigest()
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_stdio.py'),'--project-files-owner','--config',str(config)],cwd=str(ROOT),env=environment)
            with (self.path/'note-mcp.stderr').open('w+') as errors:
                async with stdio_client(params,errlog=errors) as (reader,writer):
                    async with ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=30)) as session:
                        await session.initialize();names={tool.name for tool in (await session.list_tools()).tools}
                        self.assertIn('project_files_file_adopt_deletion',names)
                        async def call(action,fields):
                            response=await session.call_tool('project_files_'+action,fields)
                            self.assertFalse(response.isError,response);envelope=response.structuredContent
                            self.assertEqual(envelope['status'],200,envelope)
                            self.assertEqual(json.loads(response.content[0].text),envelope)
                            return envelope['result']['value']
                        history=await call('file_history',dict(read(),file_id=file_id))
                        self.assertEqual([v.get('deleted',False) for v in history['items']],[False,True])
                        self.assertTrue(all('text' not in v for v in history['items']))
                        old=await call('file_get',dict(read(),file_id=file_id,revision=1));self.assertEqual(old['version']['text'],text)
                        tombstone=await call('file_get',dict(read(),file_id=file_id,revision=2));self.assertIsNone(tombstone['version']['text'])
                        note.write_text(restored)
                        observation=await call('files_inspect',read());self.assertEqual(observation['items'][0]['state'],'changed')
                        self.assertIsNone(observation['items'][0]['expected_sha256'])
                        positive=await call('file_adopt',dict(self.envelope(),kind='note',path='notes/scientist.md',expected_revision=2,expected_sha256=restored_sha))
                        self.assertEqual(positive['revision'],3);self.assertNotIn('deleted',positive)
                        note.unlink()
                        again=await call('file_adopt_deletion',dict(self.envelope(),path='notes/scientist.md',expected_revision=3,expected_sha256=restored_sha))
                        self.assertEqual(again['revision'],4)
                errors.seek(0);self.assertNotIn(self.owner.token,errors.read())
        anyio.run(exercise)
        self.performed.append('Actual owner stdio MCP reads original NUL history, tombstone metadata, restored positive rev3, and explicit second deletion rev4')
        before=self.state();fork=owner.save_as(**self.envelope(),root='fixture',directory='independent',name='Independent deleted note Ω')
        self.assertNotEqual(fork['state']['project']['project_id'],before['project']['project_id'])
        fork_root=self.external/'independent';self.assertFalse((fork_root/'notes/scientist.md').exists())
        files=owner.files_inspect(**read())['value']['items'];self.assertEqual(len(files),1)
        new_id=files[0]['id'];self.assertNotEqual(new_id,file_id);self.assertEqual(files[0]['state'],'deleted')
        self.assertEqual(owner.file_get(**read(),file_id=new_id,revision=1)['value']['version']['text'],text)
        self.assertEqual(raw_owner.call('project_files.file_get',dict(binding=before['binding'],checkpoint=before['project']['checkpoint'],file_id=file_id))['status'],409)
        self.assertFalse(any(self.owner.token.encode() in p.read_bytes() for p in fork_root.rglob('*') if p.is_file()))
        owner.close(**self.envelope())
        cold_root=self.path/'cold-external';cold_root.mkdir();clone=cold_root/'clone'
        git_env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0')
        def git(*args):subprocess.run(['git',*args],env=git_env,check=True,capture_output=True)
        git('init','-q','--template=',str(fork_root));git('-C',str(fork_root),'add','.')
        git('-C',str(fork_root),'-c','user.name=Disposable note QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Retained note deletion')
        git('-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',str(fork_root),str(clone))
        if (fork_root/'artifacts').exists():shutil.copytree(fork_root/'artifacts',clone/'artifacts',dirs_exist_ok=True)
        shutil.rmtree(self.external)
        self.select_host(self.path/'cold-control',{'fixture':cold_root},cold_dsn)
        cold=ProjectFilesClient(api.ProjectFilesOwnerClient(self.origin,self.owner.token,self.owner.catalog_id,timeout=20))
        opened=cold.open(**self.envelope(),root='fixture',directory='clone')
        self.assertEqual(opened['project'],fork['state']['project']);self.assertFalse((clone/'notes/scientist.md').exists())
        inspection=cold.files_inspect(**read())['value']['items'][0];self.assertEqual(inspection['state'],'deleted')
        self.assertIsNone(cold.file_get(**read(),file_id=new_id)['value']['version']['text'])
        self.assertEqual(cold.file_get(**read(),file_id=new_id,revision=1)['value']['version']['text'],text)
        self.assertEqual(cold.file_get(**read(),file_id=new_id,revision=3)['value']['version']['text'],restored)
        self.assertEqual([item['revision'] for item in cold.file_history(**read(),file_id=new_id)['value']['items']],[1,2,3,4])
        self.performed.append('Independent Save As preserves deletion and complete lineage; local Git clone opens cold with distinct role denied source CONNECT after old project roots are removed')


if __name__=='__main__':unittest.main()
