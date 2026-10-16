"""Opt-in actual A-only restored client parity; never admit or replay work.

The already-qualified restored copy may gain inspect credentials and read audit
rows only. Original source and all domain/grant/Run/accounting state stay exact.
Official CLI and official MCP SDK are transport consumers, never numerical code.
"""
import argparse
import asyncio
import base64
from contextlib import AsyncExitStack
from datetime import timedelta
import hashlib
from http.server import ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api
from app import Dataset,make_handler
from auth_helpers import ExplicitOwnerFixture
import backup_metadata as transfer
from qualify_extension_retention import expected_a_stage,require
from qualify_scientific_restore import compare,snapshot

RETENTION_SHA='e3f4fc3d3be14050bc129c13dcf08dd3b77f0a4d4d82be4d27177dc377b9ae63'
P5_SHA='008920a6ed2c8ec061b7c6c0140c20e67f170e57f9297512176981db07955d26'
BASELINE_SHA='0cafe285d90a459af375488f253971d01966654d79904e83c7c5c1ca91be3cbe'
HISTORICAL_COMMIT='8673509d5430e6aa1162986f4d7b1c071aa1c82e'
LEGACY={
 'agent_legacy_f588.py':('agent_api.py','820ec62f22d49aa5834c05858d865bcf109529689a54bdc06ebc3e186c955dd2'),
 'cli_legacy_f588.py':('project_cli.py','8df37da8a88ff7f97e62a2ac056a06594cbf62109a29e6dcd6d28a6e5edc6528'),
 'mcp_legacy_f588.py':('mcp_stdio.py','7a87261212474b06dad85ab7f8ab8693c20cd0fec90ded0ba034f2adf0ced344')}
ACCESS_TABLES={'access_actors','access_credentials','access_audit'}
COUNTS=('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations')
READ_OPERATIONS={'runs.get','runs.model_evidence','studies.package_state','runs.artifact_chunk'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path,limit):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit,'Bounded regular QA input required.')
        raw=stream.read(limit+1);after=os.fstat(stream.fileno())
        keys=('st_dev','st_ino','st_mode','st_nlink','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')
        require(all(getattr(before,key)==getattr(after,key) for key in keys) and len(raw)==before.st_size,
                'QA input changed while reading.')
        return raw


def document(path,wanted,limit):
    raw=regular(path,limit)
    require(digest(raw)==wanted,'Previously frozen QA input hash differs.')
    return json.loads(raw)


def save(path,value):
    raw=json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,indent=2).encode()+b'\n'
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as output:output.write(raw)
    return digest(raw)


def log(message):
    print(message,flush=True)


def historical_tree(root):
    """Check the complete authentic read-only P1 checkout; never import old owners."""
    env={key:value for key,value in os.environ.items() if not key.startswith('TULDOK_')}
    def git(*arguments):
        return subprocess.check_output(['git','-C',str(root),*arguments],env=env,timeout=30)
    require(git('rev-parse','HEAD').decode().strip()==HISTORICAL_COMMIT,'Exact historical P1 checkout required.')
    inventory={}
    for row in git('ls-tree','-rz','HEAD').split(b'\0'):
        if not row:continue
        head,name=row.split(b'\t',1);mode,kind,wanted=head.decode().split();name=name.decode()
        require(kind=='blob' and mode in ('100644','100755') and not Path(name).is_absolute() and '..' not in Path(name).parts,
                'Only exact regular historical source files are supported.')
        path=root/name;raw=regular(path,64*1024*1024)
        require(not path.stat().st_mode&0o222 and not path.parent.stat().st_mode&0o222 and
            hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==wanted,
            'Historical tracked bytes or read-only source mode differs.')
        inventory[name]=dict(bytes=len(raw),sha256=digest(raw),git_blob=wanted)
    require(inventory and all(name in inventory for name in ('agent_api.py','project_cli.py','mcp_stdio.py')),
            'Complete historical transport source closure required.')
    observed=set()
    for base,directories,files in os.walk(root,followlinks=False):
        require(not Path(base).is_symlink() and not Path(base).stat().st_mode&0o222,
                'Historical checkout directories must remain read-only.')
        for name in directories:
            require(not (Path(base)/name).is_symlink(),'Historical directory symlinks are unsupported.')
        for name in files:observed.add(str((Path(base)/name).relative_to(root)))
    require(observed==set(inventory)|{'.git'},'Historical checkout contains extra or missing files.')
    return dict(commit=HISTORICAL_COMMIT,tree=git('rev-parse','HEAD^{tree}').decode().strip(),
                files=inventory,inventory_sha256=transfer.digest(inventory),read_only=True)


class Clients:
    def __init__(self,args,dataset,owner,endpoint,output,report,p5):
        self.args,self.dataset,self.owner=args,dataset,owner
        self.endpoint,self.output,self.report,self.p5=endpoint,output,report,p5
        self.sequence=0;self.tokens=[];self.entries={};self.launches=[]
        self.child_env={key:value for key,value in os.environ.items() if not key.startswith('TULDOK_')}
        self.child_env['PYTHONDONTWRITEBYTECODE']='1'
        if args.historical_root is not None:
            self.legacy=args.historical_root.resolve()
            self.historical=historical_tree(self.legacy)
        else:
            self.legacy=output/'legacy-f588';self.legacy.mkdir(mode=0o700)
            for name,(target,wanted) in LEGACY.items():
                raw=regular(ROOT/'tests/fixtures'/name,1024*1024)
                require(digest(raw)==wanted,'Frozen retained client source differs.')
                path=self.legacy/target;path.write_bytes(raw);path.chmod(0o400)
        for root in (ROOT,self.legacy):
            for name in ('project_cli.py','mcp_stdio.py','agent_api.py'):
                path=root/name;self.entries[str(path)]=digest(regular(path,1024*1024))

    def issue(self,label):
        with self.owner.bound(self.dataset):
            credential=self.dataset.access.issue({'label':label,'scopes':['inspect'],'ttl_seconds':3600})
        self.tokens.append(credential['token'])
        stem='reader-'+str(len(self.tokens));token=self.output/(stem+'.token.private')
        descriptor=os.open(token,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as stream:stream.write(credential['token'])
        config=self.output/(stem+'.config.private.json')
        save(config,dict(endpoint=self.endpoint,catalog_id=self.dataset.db.dataset_id,token_file=str(token),timeout=180))
        return credential,config

    def launch_guard(self,original):
        def guarded(command,*args,**kwargs):
            require(isinstance(command,(tuple,list)) and len(command)>=4 and
                str(command[0])==str(self.args.agent_python) and str(command[1]) in self.entries and
                Path(command[1]).name in ('project_cli.py','mcp_stdio.py') and command[2]=='--config',
                'Only the frozen official client transport children may launch.')
            require(digest(regular(Path(command[1]),1024*1024))==self.entries[str(command[1])],
                'Official transport entry changed before launch.')
            require(type(kwargs.get('env')) is dict and
                not any(key.startswith('TULDOK_') for key in kwargs['env']),
                'Client children must not inherit catalog/runtime environment.')
            if Path(command[1]).name=='project_cli.py':
                require(len(command)>4 and command[4] in ('call','status','download'),'Only read-only CLI commands may launch.')
                if command[4]=='call':
                    require('--operation' in command and command[command.index('--operation')+1] in READ_OPERATIONS,
                        'CLI operation must remain read-only.')
            self.launches.append(dict(entry=Path(command[1]).name,legacy=Path(command[1]).parent==self.legacy))
            return original(command,*args,**kwargs)
        return guarded

    def cli(self,config,operation,arguments,*,root=ROOT,refused=False):
        require(operation in READ_OPERATIONS,'Only a selected read operation is qualified.')
        self.sequence+=1;stem=f'cli-{self.sequence:03d}';path=self.output/(stem+'-arguments.json')
        save(path,arguments)
        command=([str(self.args.agent_python),str(root/'project_cli.py'),'--config',str(config),'status','--run-id',arguments['run_id']]
                 if root==self.legacy and operation=='runs.get' else
                 [str(self.args.agent_python),str(root/'project_cli.py'),'--config',str(config),'call',
                  '--operation',operation,'--arguments',str(path)])
        result=subprocess.run(command,cwd=root,env=self.child_env,capture_output=True,timeout=200)
        require(len(result.stdout)+len(result.stderr)<=4*1024*1024,'Bounded official CLI output required.')
        require(all(token.encode() not in result.stdout+result.stderr for token in self.tokens),'Credential leaked from client.')
        (self.output/(stem+'-stdout.private')).write_bytes(result.stdout)
        (self.output/(stem+'-stderr.private')).write_bytes(result.stderr)
        if refused:
            require(result.returncode==1 and not result.stdout,'Revoked CLI unexpectedly returned data.')
            error=json.loads(result.stderr)
            require((error.get('status'),error.get('code'))==(401,'unauthenticated'),'Revoked CLI refusal differs.')
            return error
        require(result.returncode==0,'Official CLI read failed; retained diagnostics require inspection.')
        return json.loads(result.stdout)

    def download(self,config,run,item,*,root=ROOT,refused=False):
        self.sequence+=1;destination=self.output/f'whole-{self.sequence:03d}.private'
        result=subprocess.run([str(self.args.agent_python),str(root/'project_cli.py'),'--config',str(config),
            'download','--run-id',run,'--name',item['name'],'--expected-sha256',item['sha256'],'--out',str(destination)],
            cwd=root,env=self.child_env,capture_output=True,timeout=200)
        require(all(token.encode() not in result.stdout+result.stderr for token in self.tokens),'Credential leaked from download.')
        if refused:
            require(result.returncode==1 and not destination.exists(),'Revoked CLI download published data.')
            error=json.loads(result.stderr)
            require((error.get('status'),error.get('code'))==(401,'unauthenticated'),'Revoked download refusal differs.')
            require(not list(self.output.glob('.tuldok-download-*')),'Revoked provisional download remained.')
            return
        require(result.returncode==0,'Official CLI whole download failed.')
        raw=regular(destination,1024*1024)
        require(len(raw)==item['bytes'] and digest(raw)==item['sha256'],'CLI whole downloaded identity differs.')

    def raw(self,token,method,path,body=None,selection=None):
        headers={'Authorization':'Bearer '+token}
        if selection is not None:headers[agent_api.CONTRACT_HEADER]=selection
        raw=None if body is None else agent_api.encoded(body)
        if raw is not None:headers['Content-Type']='application/json'
        try:response=urlopen(Request(self.endpoint+path,data=raw,headers=headers,method=method),timeout=180)
        except HTTPError as error:response=error
        with response:
            raw=response.read(2*1024*1024+1)
            require(len(raw)<=2*1024*1024,'Raw HTTP bound exceeded.')
            return response.status,raw

    async def session(self,stack,config,root,label):
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        errors=stack.enter_context((self.output/(label+'-mcp-stderr.private')).open('w+'))
        parameters=StdioServerParameters(command=str(self.args.agent_python),
            args=[str(root/'mcp_stdio.py'),'--config',str(config)],cwd=str(root),env={'PYTHONDONTWRITEBYTECODE':'1'})
        reader,writer=await stack.enter_async_context(stdio_client(parameters,errlog=errors))
        session=await stack.enter_async_context(ClientSession(reader,writer,read_timeout_seconds=timedelta(seconds=240)))
        await session.initialize()
        tools={tool.name for tool in (await session.list_tools()).tools}
        if root==ROOT:require({'runs_model_evidence','studies_package_state','runs_artifact_chunk'}<=tools,'Current MCP tools missing.')
        else:require('runs_get' in tools and 'runs_artifact_chunk' in tools and
                     'runs_model_evidence' not in tools and 'studies_package_state' not in tools,
                     'Frozen legacy tool surface changed.')
        return session

    async def mcp(self,session,operation,arguments,*,refused=False):
        result=await session.call_tool(operation.replace('.','_'),arguments)
        envelope=result.structuredContent
        require(type(envelope) is dict,'Official MCP result lacks structured envelope.')
        text=[item.text for item in result.content if item.type=='text']
        require(len(text)==1 and json.loads(text[0])==envelope,'MCP text/structured envelope differs.')
        if refused:
            require(result.isError and envelope['status']==401 and envelope['result']['code']=='unauthenticated',
                    'Reused revoked MCP session returned data.')
        else:require(not result.isError and envelope['status']==200,'Official MCP read failed.')
        return envelope

    async def triplet(self,client,config,session,operation,arguments,label,expected=None):
        http=client.call(operation,arguments)
        require(http['status']==200,'Selected HTTP read failed.')
        cli=self.cli(config,operation,arguments)
        mcp=await self.mcp(session,operation,arguments)
        require(cli==http['result'] and mcp==http,'Decoded selected HTTP/CLI/MCP results differ.')
        if expected is not None:require(http==expected,'New current reader changed retained meaning.')
        self.sequence+=1;path=self.output/f'{label}-{self.sequence:03d}-result.json'
        save(path,http)
        self.report['calls'].append(dict(phase=label,operation=operation,arguments=arguments,
            result_sha256=transfer.digest(http),private_result=path.name))
        return http

    async def matrix(self,client,config,session,label,expected=None):
        p5=self.p5;run=p5['source_run_id'];checkpoint=p5['fresh_verification']['checkpoint_sha256']
        query=dict(run_id=run,checkpoint_sha256=checkpoint,member_ordinal=0,field_id='raw',axis='z',index=2)
        operations=[('runs.get',dict(run_id=run)),('runs.model_evidence',dict(run_id=run)),
                    ('runs.model_evidence',query),('studies.package_state',dict(candidate_id=p5['candidate_id']))]
        values=[]
        for index,(operation,arguments) in enumerate(operations):
            values.append(await self.triplet(client,config,session,operation,arguments,label,
                None if expected is None else expected[index]))
        require(values[0]['result']['state']=='completed' and values[0]['result']['custody_phase']=='drained' and
            values[1]['result']['state']=='verified' and values[2]['result']['field']['stage']==expected_a_stage(p5) and
            values[3]['result']['state']=='fresh_verified','Actual retained source/package meaning differs.')
        wanted=p5['fresh_verification']['outputs'][0]['values_c_order']
        require(values[2]['result']['field']['prediction']==[wanted[i:i+4] for i in range(32,48,4)],'Retained native slice differs.')
        weight=next(item for item in values[0]['result']['artifacts'] if item['sha256']==p5['fresh_verification']['weights_sha256'])
        with self.dataset.access.bind(client._token):package_run=self.dataset.runs.get(p5['package_run_id'])
        package=next(item for item in package_run['artifacts'] if item['name']=='package.zip' and item['sha256']==p5['package_sha256'])
        self.targets=[(run,weight),(p5['package_run_id'],package)]
        offset_index=len(values)
        for identity,item in self.targets:
            require(2<=item['bytes']<=1024*1024,'Actual selected artifact must fit two bounded segments.')
            assembled=bytearray();size=(item['bytes']+1)//2
            for offset in (0,size):
                arguments=dict(run_id=identity,name=item['name'],expected_sha256=item['sha256'],offset=offset,max_bytes=size)
                value=await self.triplet(client,config,session,'runs.artifact_chunk',arguments,label,
                    None if expected is None else expected[offset_index])
                values.append(value);offset_index+=1
                agent_api.validate_segment(value['result'],arguments)
                assembled.extend(base64.b64decode(value['result']['data_base64'],validate=True))
            require(len(assembled)==item['bytes'] and digest(assembled)==item['sha256'],'Reassembled whole MCP/CLI/HTTP identity differs.')
            status,raw=self.raw(client._token,'GET',f'/api/workspace/runs/{identity}/artifacts/{item["name"]}')
            require(status==200 and raw==assembled,'Whole HTTP differs from exact segmented bytes.')
            self.download(config,identity,item)
            self.report['whole_artifacts'].append(dict(phase=label,run_id=identity,name=item['name'],bytes=len(raw),sha256=digest(raw),segments=2))
        return values

    async def exercise(self):
        first,config=self.issue('Independent restored A HTTP CLI MCP reader')
        successor,next_config=self.issue('Independent successor restored A reader')
        require(first['identity']['actor_id']!=successor['identity']['actor_id'] and
            first['identity']['credential_id']!=successor['identity']['credential_id'],
            'Successor must be an independent current inspect reader.')
        self.report['reader_identities']={label:{key:value['identity'][key] for key in ('actor_id','credential_id')}
            for label,value in (('revoked',first),('successor',successor))}
        client=agent_api.AgentClient.from_config(config)
        require(client.selected_contracts()['runs.model_evidence']==2,'Field contract2 not actually selected.')
        async with AsyncExitStack() as stack:
            current=await self.session(stack,config,ROOT,'current')
            legacy=await self.session(stack,config,self.legacy,'legacy')
            log('Compare actual current selected HTTP, production CLI and official MCP')
            expected=await self.matrix(client,config,current,'current')
            source=expected[0]['result'];arguments=dict(run_id=source['id'])
            require(self.cli(config,'runs.get',arguments,root=self.legacy)==source,'Frozen legacy CLI Run projection differs.')
            require((await self.mcp(legacy,'runs.get',arguments))['result']==source,'Frozen legacy MCP Run projection differs.')
            identity,item=self.targets[0];self.download(config,identity,item,root=self.legacy)
            request=dict(run_id=identity,name=item['name'],expected_sha256=item['sha256'],offset=0,max_bytes=item['bytes'])
            legacy_chunk=(await self.mcp(legacy,'runs.artifact_chunk',request))['result']
            agent_api.validate_segment(legacy_chunk,request)
            require(digest(base64.b64decode(legacy_chunk['data_base64'],validate=True))==item['sha256'],'Frozen legacy MCP whole hash differs.')
            status,raw=self.raw(first['token'],'GET','/api/agent/operations')
            require(status==200 and json.loads(raw)['digest']=='cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8',
                    'Frozen56-operation discovery projection differs.')
            path=f'/api/workspace/runs/{source["id"]}/model-evidence'
            status,raw=self.raw(first['token'],'POST',path,{},agent_api.selected_header('runs.model_evidence',1))
            require(status==200 and json.loads(raw)['state']=='unsupported','Actual classifier v1 meaning changed.')
            for selection in (None,'runs.model_evidence/2/'+'0'*64):
                status,raw=self.raw(first['token'],'POST',path,{},selection)
                require(status==409 and json.loads(raw)['code']=='contract_mismatch','Strict selected contract refusal changed.')
            self.report['legacy']=dict(discovery_digest='cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8',
                cli_run=True,cli_whole_hash=True,mcp_run=True,mcp_whole_hash=True,
                field_and_package_tools='absent as frozen',classifier_v1='unsupported',missing_or_wrong_selected_header=409)
            with self.owner.bound(self.dataset):self.dataset.access.revoke(first['identity']['credential_id'])
            log('Revoke reader; prove cached HTTP, new CLI and both reused MCP sessions refuse')
            self.report['revoked']=[]
            for operation,arguments in [('runs.model_evidence',self.report['calls'][2]['arguments']),
                    ('studies.package_state',dict(candidate_id=self.p5['candidate_id'])),('runs.artifact_chunk',request)]:
                response=client.call(operation,arguments)
                require(response['status']==401 and response['result']['code']=='unauthenticated','Cached selected HTTP revoked read accepted.')
                self.cli(config,operation,arguments,refused=True)
                await self.mcp(current,operation,arguments,refused=True)
                self.report['revoked'].append(operation)
            await self.mcp(legacy,'runs.get',dict(run_id=source['id']),refused=True)
            await self.mcp(legacy,'runs.artifact_chunk',request,refused=True)
            self.cli(config,'runs.get',dict(run_id=source['id']),root=self.legacy,refused=True)
            self.download(config,identity,item,refused=True)
            status,raw=self.raw(first['token'],'GET',f'/api/workspace/runs/{identity}/artifacts/{item["name"]}')
            require(status==401 and json.loads(raw)['code']=='unauthenticated','Revoked whole HTTP download accepted.')
            self.report['reused_legacy_mcp_revoked']=True
        log('New independent current reader repeats exact retained meaning across current transports')
        next_client=agent_api.AgentClient.from_config(next_config)
        async with AsyncExitStack() as stack:
            current=await self.session(stack,next_config,ROOT,'successor')
            await self.matrix(next_client,next_config,current,'successor',expected)
        self.report['successor_reader_exact']=True
        require(all(digest(regular(Path(path),1024*1024))==wanted for path,wanted in self.entries.items()),'Transport source changed.')
        for path in self.output.glob('*-mcp-stderr.private'):
            raw=regular(path,2*1024*1024)
            require(all(token.encode() not in raw for token in self.tokens),'Credential leaked from MCP diagnostics.')
        self.report.update(transport_sources=self.entries,transport_children=self.launches,
            credential_scope=['inspect'],observation='disabled',mcp_sdk=importlib.metadata.version('mcp'),
            transport_children_catalog_environment='absent',
            agent_lock_sha256=digest(regular(ROOT/'requirements-agent.lock',1024*1024)),
            client_environment={name:importlib.metadata.version(name) for name in ('mcp','anyio','jsonschema','psycopg','Pillow')})

    async def exercise_historical(self):
        """Only supported P1 executable reads; current-v2 matrix is separately retained."""
        first,config=self.issue('Historical P1 restored A inspect reader')
        successor,next_config=self.issue('Independent historical P1 successor reader')
        require(first['identity']['actor_id']!=successor['identity']['actor_id'],'Independent historical successor required.')
        self.report['reader_identities']={label:{key:value['identity'][key] for key in ('actor_id','credential_id')}
            for label,value in (('revoked',first),('successor',successor))}
        self.report['historical_checkout']=self.historical
        async def reads(credential,configuration,label,expected=None):
            client=agent_api.AgentClient.from_config(configuration)
            arguments=dict(run_id=self.p5['source_run_id'])
            async with AsyncExitStack() as stack:
                session=await self.session(stack,configuration,self.legacy,label)
                http=client.call('runs.get',arguments)
                require(http['status']==200 and self.cli(configuration,'runs.get',arguments,root=self.legacy)==http['result'] and
                    await self.mcp(session,'runs.get',arguments)==http,'Historical executable/current HTTP Run results differ.')
                run=http['result'];require(run['state']=='completed' and run['custody_phase']=='drained','Completed historical Run required.')
                item=next(row for row in run['artifacts'] if row['sha256']==self.p5['fresh_verification']['weights_sha256'])
                values=[http];assembled=bytearray();size=(item['bytes']+1)//2
                require(2<=item['bytes']<=1024*1024,'Bounded historical artifact required.')
                for offset in (0,size):
                    request=dict(run_id=run['id'],name=item['name'],expected_sha256=item['sha256'],offset=offset,max_bytes=size)
                    value=client.call('runs.artifact_chunk',request)
                    require(value['status']==200 and await self.mcp(session,'runs.artifact_chunk',request)==value,
                            'Historical MCP/current HTTP segment differs.')
                    agent_api.validate_segment(value['result'],request)
                    assembled.extend(base64.b64decode(value['result']['data_base64'],validate=True));values.append(value)
                require(len(assembled)==item['bytes'] and digest(assembled)==item['sha256'],'Historical whole fitted-state hash differs.')
                self.download(configuration,run['id'],item,root=self.legacy)
                if expected is not None:require(values==expected,'Historical successor changed retained meaning.')
                for index,value in enumerate(values):
                    path=self.output/f'{label}-{index:02d}-result.json';save(path,value)
                    self.report['calls'].append(dict(phase=label,operation='runs.get' if index==0 else 'runs.artifact_chunk',
                        result_sha256=transfer.digest(value),private_result=path.name))
                self.report['whole_artifacts'].append(dict(phase=label,run_id=run['id'],name=item['name'],bytes=item['bytes'],sha256=item['sha256'],segments=2))
                if expected is None:
                    with self.owner.bound(self.dataset):self.dataset.access.revoke(credential['identity']['credential_id'])
                    require(client.call('runs.get',arguments)['status']==401,'Historical reader HTTP revocation differs.')
                    self.cli(configuration,'runs.get',arguments,root=self.legacy,refused=True)
                    await self.mcp(session,'runs.get',arguments,refused=True)
                    await self.mcp(session,'runs.artifact_chunk',request,refused=True)
                    self.download(configuration,run['id'],item,root=self.legacy,refused=True)
                    self.report['historical_reused_session_revoked']=True
                return values
        log('Authentic historical P1 CLI/MCP reads and reused-session revocation, through HTTP only')
        expected=await reads(first,config,'historical-current')
        await reads(successor,next_config,'historical-successor',expected)
        require(all(digest(regular(Path(path),1024*1024))==wanted for path,wanted in self.entries.items()),'Transport source changed.')
        for path in self.output.glob('*-mcp-stderr.private'):
            raw=regular(path,2*1024*1024)
            require(all(token.encode() not in raw for token in self.tokens),'Credential leaked from historical MCP diagnostics.')
        self.report.update(historical_only=True,successor_reader_exact=True,transport_sources=self.entries,
            transport_children=self.launches,credential_scope=['inspect'],mcp_sdk=importlib.metadata.version('mcp'),
            transport_children_catalog_environment='absent',historical_store_access='HTTP only; no old Dataset or Metadata',
            historical_features='Frozen P1 Run/artifact operations only; no field2/package-state tool claim')


def main(args):
    output=args.output.resolve();output.mkdir(parents=True,mode=0o700,exist_ok=False)
    report=dict(format='extension_a_restored_client_qualification_v1',state='in_progress',started_unix=time.time(),
        host_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        driver_sha256=digest(Path(__file__).read_bytes()),retention_receipt_sha256=RETENTION_SHA,p5_receipt_sha256=P5_SHA,
        scope='Actual restored canonical A/0b HTTP CLI MCP parity only; no B, shared matrix, physics or execution claim.',
        calls=[],whole_artifacts=[])
    dataset=server=thread=None;clients=None
    try:
        retention=document(args.retention_receipt,RETENTION_SHA,1024*1024)
        p5=document(args.p5_receipt,P5_SHA,1024*1024)
        baseline=document(args.source_baseline,BASELINE_SHA,16*1024*1024)
        require(retention['state']=='passed' and retention['source_unchanged'] and retention['cold_reopen'] and
            retention['source_run_id']==p5['source_run_id'] and retention['package_run_id']==p5['package_run_id'] and
            retention['verifier_run_id']==p5['verifier_run_id'],'Exact completed retention/P5 identities required.')
        original=Path(retention['source']).resolve();restored=args.restored_catalog.resolve()
        require(restored==Path(retention['output']).resolve()/'restored-catalog' and restored!=original and
                not output.is_relative_to(restored) and not output.is_relative_to(original),'Only the previously qualified restored copy is selected.')
        require(importlib.metadata.version('mcp')=='1.30.0','Exact provisioned official MCP SDK1.30.0 required.')
        require(args.agent_python.is_absolute() and args.agent_python.is_file() and
            str(args.agent_python)==sys.executable,'The same explicitly provisioned MCP client interpreter is required.')
        original_connection=os.environ['TULDOK_CLIENT_SOURCE_DATABASE_URL'];connection=os.environ['TULDOK_DATABASE_URL']
        log('Raw original/restore identities and finite state before issuing any reader')
        source_before=snapshot(original,original_connection);compare(source_before,baseline)
        excluded=tuple(path.name for path in restored.glob('.restore-receipt-*.json'))
        before=snapshot(restored,connection,exclude=excluded)
        require(before['database_identity_sha256']!=source_before['database_identity_sha256'] and
            before['dataset_id']==baseline['dataset_id'] and before['run_states']==baseline['run_states'],
            'Restored database identity or exact three completed Runs differs.')
        require(all(before['tables'][name]==baseline['tables'][name] for name in baseline['tables'] if name not in ACCESS_TABLES)
            and all(before[key]==baseline[key] for key in ('files','modes','custody','sequences','runtime_manifests')),
            'Previously qualified restored immutable meaning differs from original baseline.')
        report.update(catalog_id=baseline['dataset_id'],source_run_id=p5['source_run_id'],package_run_id=p5['package_run_id'],
            verifier_run_id=p5['verifier_run_id'],charged=p5['charged'],counts_before={name:before['tables'][name]['count'] for name in COUNTS})
        with patch('runs.Runs._start',side_effect=AssertionError('Client reads must not schedule')), \
             patch('runs.Runs._execute',side_effect=AssertionError('Client reads must not execute a Run')):
            dataset=Dataset(restored,dsn=connection,project_roots={});owner=ExplicitOwnerFixture.bootstrap(dataset)
            require(dataset.projects.roots=={},'Configured project roots must stay absent.')
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            clients=Clients(args,dataset,owner,'http://127.0.0.1:'+str(server.server_port),output,report,p5)
            with patch('subprocess.Popen',side_effect=clients.launch_guard(subprocess.Popen)):
                asyncio.run(asyncio.wait_for(clients.exercise_historical() if args.historical_root is not None else clients.exercise(),timeout=1800))
            if args.historical_root is not None:
                require(historical_tree(clients.legacy)==clients.historical,'Historical checkout source closure changed.')
            require(dataset.runs._thread is None,'Client reads started the Runs scheduler.')
            server.shutdown();server.server_close();thread.join(timeout=5);require(not thread.is_alive(),'HTTP server did not stop.')
            server=None;dataset.close();dataset=None
        log('Final immutable restored domain and untouched original raw parity')
        final=snapshot(restored,connection,exclude=excluded)
        immutable=[name for name in before['tables'] if name not in ACCESS_TABLES]
        require(all(final['tables'][name]==before['tables'][name] for name in immutable),
            'Client qualification changed domain/grant/reservation/consumption rows.')
        require(all(final[key]==before[key] for key in ('files','modes','custody','sequences','run_states','runtime_manifests')),
            'Client qualification changed retained files/modes/custody/sequences/Runs/runtime.')
        compare(snapshot(original,original_connection),source_before)
        report.update(state='passed',root_absent=True,original_unchanged=True,restored_immutable_tables=immutable,
            counts_after={name:final['tables'][name]['count'] for name in COUNTS},
            admission_or_execution=False,run_scheduler_blocked=True,finished_unix=time.time())
        require(all(token not in json.dumps(report) for token in clients.tokens),'Report contains a credential.')
        save(output/'report.json',report);log('PASS actual restored canonical A HTTP CLI MCP '+str(output))
    except BaseException as error:
        report.update(state='failed',error_type=type(error).__name__,failure='Actual qualification incomplete; inspect private diagnostics. No admission retry authorized.')
        save(output/'failure.json',report)
        raise
    finally:
        if server is not None:server.shutdown();server.server_close();thread.join(timeout=5)
        if dataset is not None:dataset.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('restored-catalog','retention-receipt','p5-receipt','source-baseline','agent-python','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--historical-root',type=Path,help='Exact complete read-only P1 checkout; run only supported historical client cases.')
    main(parser.parse_args())
