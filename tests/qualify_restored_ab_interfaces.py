"""Explicit restored-only official CLI/MCP field, whole-byte and revocation witness.

Requires a completed reviewed retention report and an explicit restored-copy lease.
No Project roots, execution grant, SDK conformance, admission or reconciliation.
"""
import argparse, asyncio, hashlib, json, os, re, signal, subprocess, sys, time
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(value,message):
    if not value:raise AssertionError(message)
def bounded(path,limit=2*1024**2):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        import stat
        before=os.fstat(fd);require(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'Not a bounded regular receipt')
        raw=os.read(fd,limit+1);after=os.fstat(fd)
        require(len(raw)==before.st_size and (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),'Receipt changed')
        return raw
    finally:os.close(fd)
def private(path,value):
    raw=(json.dumps(value,indent=2)+'\n').encode() if not isinstance(value,bytes) else value
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)
def private_stream(path,mode):
    private(path,b'');return path.open(mode)
def reviewed(ref):
    raw=bounded(ref['path']);require(sha(raw)==ref['sha256'],'Reviewed reference changed')
    value=json.loads(raw)
    if set(value) in ({'status','result'},{'operation','status','result'}):
        require(200<=value['status']<300,'Failed reviewed HTTP response');value=value['result']
    return value

def separate(left,right):
    left,right=Path(left).resolve(),Path(right).resolve()
    return left!=right and left not in right.parents and right not in left.parents

def guard_output(output,protected):
    require(all(separate(output,path) for path in protected),'Output overlaps an original, restored, source or Project tree')

def run(a):
    require(a.restored_copy_lease is True,'Explicit restored-copy lease required')
    harness_sha=sha(Path(__file__).read_bytes())
    sys.path.insert(0,str(a.source))
    import agent_api
    from metadata import Metadata, connection_info
    from access import Access
    from psycopg.conninfo import make_conninfo
    report_raw=bounded(a.retention_report);require(sha(report_raw)==a.retention_sha256,'Retention report changed')
    retention=json.loads(report_raw)
    require(retention.get('format')=='extension_ab_retention_qualification_v1' and retention.get('restored_database_retained') is True,'Successful retained restore format required')
    require(retention['state'] in ('passed','rootless_retention_verified_disable_pending') and retention['source_unchanged'] is True and retention['rootless_warm'] is True and retention['rootless_cold'] is True,'Completed rootless retention phase required')
    database=retention['restored_database'];require(re.fullmatch('tuldok_ab_retention_[a-f0-9]{32}',database),'Restored test database required')
    require(Path(retention['output']).is_absolute() and Path(retention['source']).is_absolute(),'Absolute retained paths required')
    require(a.retention_report.resolve().parent==Path(retention['output']).resolve(),'Report output path differs')
    catalog=Path(retention['output']).resolve()/'restored-catalog'
    require(catalog.is_dir() and not catalog.is_symlink(),'Existing restored catalog required')
    selection_raw=bounded(a.selection);selection=json.loads(selection_raw)
    require(selection['format']=='extension_ab_retention_selection_v1' and sha(selection_raw)==retention['selection_sha256'],'Wrong or changed reviewed selection')
    require(retention['reviewed_references']==selection,'Reviewed reference closure differs')
    roots=reviewed(selection['current_roots'])
    require(type(roots) is dict and 1<=len(roots)<=8 and all(type(k) is str and 1<=len(k)<=64 and type(v) is str and Path(v).is_absolute() for k,v in roots.items()),'Exact bounded absolute current roots required')
    require(type(retention['backup']['receipt_digest']) is str and re.fullmatch('[a-f0-9]{64}',retention['backup']['receipt_digest']),'Exact backup digest required')
    marker_name='.restore-receipt-'+retention['backup']['receipt_digest']+'.json'
    require(json.loads(bounded(catalog/marker_name,4096))==dict(kind='postgresql-restore',backup_sha256=retention['backup']['receipt_digest'],dataset_id=selection['catalog_id']),'Exact restore marker differs')
    guard_output(a.output,[Path(retention['source']),catalog,a.source,Path(__file__).resolve().parents[1],Path(retention['output'])/'restored-only-b-source',*[Path(v) for v in roots.values()]])
    require(separate(Path(retention['source']),catalog),'Original and restored catalog overlap')
    selected={label:reviewed(selection[label]['run']) for label in ('a','b')}
    rows=[]
    for label,pairs in (('a',[('raw','train')]),('b',[('raw','raw_inference'),('corrected','boundary_enforcement')])):
        fields=retention['side_by_side'][label]['fields']
        for field_id,stage in pairs:
            chosen=[row for row in fields if row['query']['field_id']==field_id][-1]
            query=dict(run_id=selected[label]['id'],**chosen['query'])
            rows.append(dict(label=label,stage=stage,query=query,projection_sha256=chosen['projection_sha256']))
    artifacts={label:next(item for item in selected[label]['artifacts'] if item['name']=='execution-context.json') for label in ('a','b')}
    for item in artifacts.values():require(0<item['bytes']<=8*1024**2,'Whole context exceeds bounded interface witness')
    runtime_files=('app.py','agent_api.py','project_cli.py','mcp_stdio.py','mcp_observer.py','extension_evidence.py','runs.py','access.py','static/workspace-real.js')
    source_hashes={name:sha(bounded(a.source/name,8*1024**2)) for name in runtime_files}
    expected_runs=[selected['a'],selected['b'],reviewed(selection['a']['package_run']),reviewed(selection['a']['verifier_run'])]
    expected_ids={row['id'] for row in expected_runs}
    require(len(expected_ids)==4 and all(row['state']=='completed' and row['custody_phase']=='drained' for row in expected_runs),'Four distinct reviewed completed drained Runs required')
    a.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    metadata=Metadata(catalog,dsn=make_conninfo(connection_info(),dbname=database),create=False)
    current=[json.loads(row[0]) for row in metadata.execute('SELECT document FROM workspace_runs').fetchall()]
    require({row['id'] for row in current}==expected_ids and all(row['state']=='completed' and row['custody_phase']=='drained' for row in current),'Only exact four completed drained Runs may be opened')
    require(metadata.dataset_id==selection['catalog_id'],'Restored catalog identity differs')
    access=Access(metadata,catalog);owner=access.exchange(access._local_owner_token(require_existing=True))
    with access.bind(owner['token']):reader=access.issue({'label':'Restored official CLI MCP inspect parity','scopes':['inspect'],'ttl_seconds':600})
    tokenpath=a.output/'token.private';private(tokenpath,reader['token'].encode())
    tables=('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations','model_studies','model_trials')
    def counts():return {table:metadata.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in tables}
    before=counts();server=None;revoked=False;proofs=[];whole_proofs=[];denials=[];legacy=[];out=err=None;config=None
    try:
        out=private_stream(a.output/'server.stdout.private','r+');err=private_stream(a.output/'server.stderr.private','w')
        env=dict(os.environ,TULDOK_DATABASE_URL=make_conninfo(connection_info(),dbname=database))
        bootstrap="import app; from unittest.mock import patch; forbidden=lambda *a,**k: (_ for _ in ()).throw(AssertionError('Read-only interface server must not execute')); guards=[patch('runs.Runs._start',forbidden),patch('recipe_process.launch',forbidden),patch('subprocess.Popen',forbidden)]; [g.start() for g in guards]; app.main()"
        server=subprocess.Popen([sys.executable,'-u','-c',bootstrap,'--data',str(catalog),'--port','0'],cwd=a.source,env=env,stdout=out,stderr=err)
        endpoint=None;deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            out.seek(0);match=re.search(r'http://127\.0\.0\.1:\d+',out.read())
            if match:endpoint=match[0];break
            require(server.poll() is None,'HTTP child exited; inspect private stderr')
            time.sleep(.05)
        require(endpoint,'HTTP readiness missing')
        config=a.output/'client.private.json';private(config,dict(endpoint=endpoint,catalog_id=metadata.dataset_id,token_file=str(tokenpath)))
        client=agent_api.AgentClient.from_config(config)
        require(client.selected_contracts()['runs.model_evidence']==2,'Selected evidence contract2 required')
        def cli(arguments,name,expected=0):
            result=subprocess.run([sys.executable,'project_cli.py','--config',str(config),*arguments],cwd=a.source,capture_output=True,timeout=60)
            private(a.output/(name+'.stdout.private'),result.stdout);private(a.output/(name+'.stderr.private'),result.stderr)
            require(result.returncode==expected,'Unexpected CLI exit '+name)
            if expected==0:require(result.stderr==b'','Successful CLI stderr changed');return json.loads(result.stdout)
            diagnostic=json.loads(result.stderr);require(diagnostic['status']==401,'CLI revoked refusal not401')
            return diagnostic
        def whole(label):
            item=artifacts[label];url=endpoint+'/api/workspace/runs/'+selected[label]['id']+'/artifacts/'+item['name']
            request=Request(url,headers={'Authorization':'Bearer '+reader['token']})
            with urlopen(request,timeout=60) as response:raw=response.read(item['bytes']+1)
            require(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'HTTP whole identity differs')
            return raw,request
        for i,row in enumerate(rows):
            result=client.call('runs.model_evidence',row['query']);require(result['status']==200,'HTTP field failed')
            require(sha(agent_api.encoded(result['result']))==row['projection_sha256'],'HTTP result differs from rootless retention witness')
            require(result['result']['field']['stage']==row['stage'],'Actual stage differs')
            arg=a.output/('query-'+str(i)+'.json');private(arg,row['query']);row['argument_file']=arg
            require(cli(['call','--operation','runs.model_evidence','--arguments',str(arg)],'field-'+str(i))==result['result'],'CLI field differs')
            row['expected']=result
        # The shipped CLI/MCP expose negotiated versions, with no version-forcing flag.
        # Pin the actual public HTTP wire explicitly with the shipped header encoder;
        # this is a selected-v1 request, never an invented legacy client binary.
        for label in ('a','b'):
            row=next(row for row in rows if row['label']==label)
            path='/api/workspace/runs/'+selected[label]['id']+'/model-evidence'
            headers={'Authorization':'Bearer '+reader['token'],'Content-Type':'application/json',agent_api.CONTRACT_HEADER:agent_api.selected_header('runs.model_evidence',1)}
            for kind,body in (('summary',{}),('field_selector',{k:v for k,v in row['query'].items() if k!='run_id'})):
                request=Request(endpoint+path,data=agent_api.encoded(body),headers=headers,method='POST')
                try:
                    with urlopen(request,timeout=60) as response:status=response.status;value=json.loads(response.read(65537))
                except HTTPError as error:status=error.code;value=json.loads(error.read(65537))
                if kind=='summary':require(status==200 and value=={'state':'unsupported','reason':'Scientific field evidence requires its explicit selected query contract.'},'V1 summary reinterpreted field evidence')
                else:require(status==400 and value.get('code')=='invalid','V1 field selector was not closed-invalid')
                legacy.append(dict(label=label,request=kind,contract_version=1,contract_sha256=agent_api.contract('runs.model_evidence',1)['sha256'],status=status,response=value,transport='public HTTP with shipped selected_header encoder'))
        for label,item in artifacts.items():
            raw,request=whole(label);item['request']=request;item['whole']=raw
            destination=a.output/(label+'-context.json')
            cli(['download','--run-id',selected[label]['id'],'--name',item['name'],'--expected-sha256',item['sha256'],'--out',str(destination)],label+'-download')
            require(bounded(destination,8*1024**2)==raw,'CLI whole differs')
        async def official_mcp():
            from mcp import ClientSession,StdioServerParameters
            from mcp.client.stdio import stdio_client
            params=StdioServerParameters(command=sys.executable,args=['mcp_stdio.py','--config',str(config)],cwd=str(a.source))
            with private_stream(a.output/'mcp.stderr.private','w') as error_log:
                async with stdio_client(params,errlog=error_log) as (read,write):
                    async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=60)) as session:
                        await session.initialize();tools=await session.list_tools()
                        require({'runs_model_evidence','runs_artifact_chunk'}<={tool.name for tool in tools.tools},'Official selected tools missing')
                        for row in rows:
                            result=await session.call_tool('runs_model_evidence',row['query'])
                            require(not result.isError and result.structuredContent==row['expected'],'Official MCP field differs')
                            proofs.append(dict(label=row['label'],query=row['query'],stage=row['stage'],projection_sha256=row['projection_sha256'],interfaces=['selected_agent_http_v2','official_project_cli','official_mcp_sdk']))
                        for label,item in artifacts.items():
                            data=bytearray();offset=0
                            while True:
                                request=dict(run_id=selected[label]['id'],name=item['name'],expected_sha256=item['sha256'],offset=offset,max_bytes=65536)
                                result=await session.call_tool('runs_artifact_chunk',request)
                                require(not result.isError and result.structuredContent['status']==200,'MCP segment failed')
                                value=result.structuredContent['result'];data.extend(agent_api.validate_segment(value,request))
                                require(len(data)<=item['bytes'] and value['total_bytes']==item['bytes'],'MCP segment total differs')
                                offset=value['next_offset']
                                if value['eof']:break
                            require(bytes(data)==item['whole'] and sha(data)==item['sha256'],'Complete official MCP bytes differ')
                            whole_proofs.append(dict(label=label,run_id=selected[label]['id'],name=item['name'],bytes=len(data),sha256=sha(data),interfaces=['http_whole','official_cli_verified_download','official_mcp_validated_segments_whole_sha256']))
                        with access.bind(owner['token']):access.revoke(reader['identity']['credential_id'])
                        nonlocal revoked
                        revoked=True
                        for i,row in enumerate(rows):
                            require(client.call('runs.model_evidence',row['query'])['status']==401,'Revoked HTTP field accepted')
                            cli(['call','--operation','runs.model_evidence','--arguments',str(row['argument_file'])],'revoked-field-'+str(i),1)
                            result=await session.call_tool('runs_model_evidence',row['query'])
                            require(result.isError and result.structuredContent['status']==401,'Revoked MCP field accepted')
                            denials.append(dict(label=row['label'],operation='runs.model_evidence',field_id=row['query']['field_id'],http_status=401,cli_status=401,cli_refusal_stage='fresh process credential bootstrap',mcp_status=401))
                        for label,item in artifacts.items():
                            try:urlopen(item['request'],timeout=30)
                            except HTTPError as error:require(error.code==401,'Wrong HTTP whole refusal')
                            else:raise AssertionError('Revoked HTTP whole accepted')
                            destination=a.output/(label+'-revoked-download.json')
                            cli(['download','--run-id',selected[label]['id'],'--name',item['name'],'--expected-sha256',item['sha256'],'--out',str(destination)],label+'-revoked-download',1)
                            require(not destination.exists(),'Revoked CLI published destination')
                            request=dict(run_id=selected[label]['id'],name=item['name'],expected_sha256=item['sha256'],offset=0,max_bytes=65536)
                            result=await session.call_tool('runs_artifact_chunk',request)
                            require(result.isError and result.structuredContent['status']==401,'Revoked MCP segment accepted')
                            denials.append(dict(label=label,operation='artifact_whole_or_segment',http_status=401,cli_status=401,cli_refusal_stage='fresh process credential bootstrap',mcp_status=401))
        asyncio.run(official_mcp())
        after=counts();require(after==before,'Inspect-only official interfaces changed domain counts')
        require(source_hashes=={name:sha(bounded(a.source/name,8*1024**2)) for name in runtime_files},'Interface bytes changed during witness')
        require(bounded(a.retention_report)==report_raw and bounded(a.selection)==selection_raw,'Reviewed inputs changed during witness')
        receipt=dict(format='restored_ab_official_interface_qualification_v1',state='passed',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),source_file_sha256=source_hashes,harness_sha256=harness_sha,retention_report_sha256=a.retention_sha256,selection_sha256=sha(selection_raw),catalog_id=metadata.dataset_id,field_contract=dict(version=2,sha256=agent_api.contract('runs.model_evidence',2)['sha256']),field_proofs=proofs,whole_proofs=whole_proofs,actual_credential_revocation=denials,legacy_selected_wire=legacy,legacy_scope='Current CLI/MCP negotiate v2 and expose no forced-v1 option; v1 results above are actual explicitly pinned HTTP, not an old binary or fabricated classifier history',server_execution_tripwires=['runs.Runs._start','recipe_process.launch','subprocess.Popen (HTTP child only)'],domain_counts_before=before,domain_counts_after=after,project_roots={},collector='disabled; no observation store activated',scope='Restored-copy current selected field and bounded whole-artifact parity through official clients; no new execution, grant, admission, numerical or physical acceptance claim.')
    finally:
        try:
            if server is not None and server.poll() is None:
                server.send_signal(signal.SIGINT)
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
            with access.bind(owner['token']):
                if not revoked:access.revoke(reader['identity']['credential_id'])
                access.logout()
        finally:
            metadata.close()
            if out is not None:out.close()
            if err is not None:err.close()
            tokenpath.unlink(missing_ok=True)
            if config is not None:config.unlink(missing_ok=True)
    require(sha(Path(__file__).read_bytes())==harness_sha,'Witness source changed during execution')
    require(not tokenpath.exists() and config is not None and not config.exists(),'Private credential cleanup incomplete')
    receipt['credential_config_removed']=True
    receipt['server_drained']=server.poll() is not None
    private(a.output/'receipt.json',receipt);print(json.dumps(receipt,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--retention-report',type=Path,required=True)
    p.add_argument('--retention-sha256',required=True)
    p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--restored-copy-lease',action='store_true',required=True)
    run(p.parse_args())
