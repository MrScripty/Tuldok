"""One fresh main505 agent-authored canonical A qualification.

The owner supplies roots, reviewed canonical source, an explicit qualified CPU
runtime, the agent credential and one exact execution approval. All snapshot,
Model, graph and Trial authoring uses negotiated public agent interfaces. The
owner creates the finite closed Study and reviews its epoch and exact grant. One
SDK admission runs the unchanged producer. Never retry an uncertain admission.
"""
import argparse
import asyncio
import copy
from contextlib import ExitStack
from datetime import timedelta
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from urllib.request import Request, urlopen
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api
from app import Dataset, make_handler
import backup_metadata as transfer
import extension_canonical_fixture as fixture
import extension_evidence as evidence
from prepare_extension_canonical_project import prepare, PACKAGE
from qualify_extension_canonical import (sdk_observation, verify_accounting,
    verify_context_custody, verify_frozen_sources)
from qualify_extension_author import regular
from runtime_snapshots import RuntimeSnapshots, inventory, canonical, sha

RUNTIME_SHA='50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d'
PARENT=Path('/workspace/shared')
PREFIX='main505-agent-authoring-'
CONFIGURATION={'initial_scale':-0.375,'initial_offset':0.5}
FIXED={'project_snapshots.list':1,'project_snapshots.open':1,'project_snapshots.get':1,
       'recipes.inspect':3,'models.publish':2,'graphs.create_external':2,
       'graphs.preflight_external':2,'studies.prepare_trial':2}
AUTHORING=('models.create','models.publish','graphs.create_external',
           'graphs.preflight_external','studies.prepare_trial')
OWNER_ONLY=('studies.create','studies.save','studies.continue','studies.approve')
COUNTERS=('workspace_runs','access_execution_grants','access_execution_consumptions',
          'model_attempt_reservations','model_studies','model_trials','workspace_projects')


def require(value,reason):
    if not value:raise RuntimeError(reason)


def digest(path):return hashlib.sha256(regular(Path(path),8*1024**2)).hexdigest()


def guard_workspace(workspace, *, parent=PARENT):
    workspace=Path(workspace).absolute()
    require(workspace.parent==parent.resolve() and not workspace.is_symlink() and
        re.fullmatch(re.escape(PREFIX)+'[a-f0-9]{32}',workspace.name),
        'Choose a new direct shared child with the explicit main505 nonce namespace.')
    require(not os.path.lexists(workspace),'Preserve every earlier attempt; workspace must be absent.')
    transfer.separate_paths(ROOT,workspace)
    return workspace,'tuldok_main505_agent_'+workspace.name[len(PREFIX):]


def required_contracts():
    """Refuse the old host before any directory, database, runtime or actor."""
    advertised={row['id']:row['contracts'] for row in agent_api.capabilities('a'*32)['operations']}
    selected={}
    for name in (*FIXED,*AUTHORING):
        choices=advertised.get(name,[])
        choices=[row for row in choices if row['version']==FIXED[name]] if name in FIXED else choices
        require(choices,'Required negotiated operation is absent: '+name)
        chosen=max(choices,key=lambda row:row['version'])
        require(chosen['authority']=='agent','Agent authoring authority is unavailable: '+name)
        selected[name]=chosen
    for name in OWNER_ONLY:
        require(advertised.get(name) and all(row['authority']=='owner' for row in advertised[name]),
                'Preserve the existing owner-only Study authority: '+name)
    return selected


def disk_plan(runtime_bytes,free_bytes):
    # One immutable CPU snapshot; conservative additional capture/staging space.
    required=runtime_bytes+3*320*1024**2+1024**3
    require(free_bytes>=required,'Insufficient space for measured runtime, bounded captures and 1 GiB reserve.')
    return dict(runtime_bytes=runtime_bytes,capture_and_staging_bytes=3*320*1024**2,
                reserve_bytes=1024**3,required_bytes=required,free_bytes=free_bytes)


def source_inventory():
    tracked=subprocess.check_output(['git','ls-files','*.py','static/workspace-real.js'],cwd=ROOT,text=True).splitlines()
    return {name:digest(ROOT/name) for name in tracked}


def tree_inventory(root):
    return {str(path.relative_to(root)):digest(path) for path in sorted(root.rglob('*'))
            if path.is_file() or path.is_symlink()}


def counters(dataset):
    return {name:dataset.db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in COUNTERS}


def domain(dataset):
    with dataset.lock,dataset.db.transaction():tables=transfer.summaries(transfer.read_catalog(dataset.db))
    return {name:value for name,value in tables.items() if name not in ('access_audit','access_actors','access_credentials')}


def main(args):
    workspace,database=guard_workspace(args.workspace)
    require(args.expected_runtime_sha256==RUNTIME_SHA,'This qualifier selects main505 only; no runtime fallback.')
    require(re.fullmatch('[a-f0-9]{40}',args.expected_host_commit or ''),'Pin the full reviewed new application commit.')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(commit==args.expected_host_commit,'Reviewed application commit differs.')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'Freeze a clean qualification source.')
    contracts=required_contracts();verify_frozen_sources(PACKAGE)
    runtime_config=evidence.decode(regular(args.runtime_config,65536),65536)
    require(args.oracle_python.is_absolute() and args.oracle_python.is_file(),
            'Explicit absolute independent oracle interpreter is absent.')
    oracle_info=subprocess.run([str(args.oracle_python),'-I','-S','-c',
        'import json,sys;print(json.dumps({"implementation":sys.implementation.name,"version":list(sys.version_info[:3])}))'],
        capture_output=True,text=True,timeout=10,check=True)
    oracle_info=json.loads(oracle_info.stdout)
    require(oracle_info['implementation']=='cpython' and oracle_info['version'][:2]==[3,12],
            'Frozen oracle requires the explicitly nominated CPython 3.12 interpreter.')
    original_connection=os.environ['TULDOK_DATABASE_URL']
    with psycopg.connect(original_connection,autocommit=True) as admin:
        require(admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',(database,)).fetchone() is None,
                'Fresh qualification database already exists; do not reuse it.')
    runtime_manifest,_runtime_sources=inventory(runtime_config)
    require(sha(canonical(runtime_manifest))==RUNTIME_SHA,'Nominated runtime inventory differs before mutation.')
    storage=disk_plan(runtime_manifest['total_bytes'],shutil.disk_usage(workspace.parent).free)
    frozen=source_inventory();workspace.mkdir(mode=0o700)
    output=workspace/'qualification';output.mkdir(mode=0o700)
    catalog=workspace/'catalog';source=workspace/'canonical-source-project';source.mkdir()
    project=workspace/'project';roots={'canonical-fixture':source,'agent-extension':project}
    connection=make_conninfo(original_connection,dbname=database)
    report=dict(format='main505_agent_authoring_qualification_v1',state='preparing',admission_state='not_started',
        nonce=workspace.name[len(PREFIX):],host_commit=commit,driver_sha256=digest(__file__),
        database=database,catalog_path=str(catalog),project_roots={key:str(value) for key,value in roots.items()},
        configuration=CONFIGURATION,expected_runtime_sha256=RUNTIME_SHA,storage_preflight=storage,
        oracle_interpreter=oracle_info,runtime_config_sha256=digest(args.runtime_config),
        physical_acceptance='not_established',quality_acceptance='not_established')
    dataset=server=thread=owner=credential=client=None;config=None;token_path=None;sequence=0
    private_paths=[];calls=[];cold_guards=ExitStack();cold_execution_attempts=[]
    def save(name,value):
        path=output/name
        raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        return path
    def progress():
        save('progress-'+uuid.uuid4().hex+'.json',report)
    def private(name,raw):
        path=output/name;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        private_paths.append(path);return path
    def stop():
        nonlocal dataset,server,thread,owner
        if server is not None:server.shutdown();server.server_close();thread.join(timeout=5);server=thread=None
        if dataset is not None:
            if owner is not None:
                with dataset.access.bind(owner['token']):dataset.access.logout()
            dataset.close();dataset=owner=None
    def start(available_roots,initial=False):
        nonlocal dataset,server,thread,owner,client,config
        dataset=Dataset(catalog,dsn=connection,project_roots=available_roots)
        require(dataset.db.connection.info.dbname==database,'Fresh database target differs.')
        owner=dataset.access.exchange(dataset.access._local_owner_token(require_existing=not initial))
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        if credential is not None:
            config=private('agent-config-'+uuid.uuid4().hex+'.private.json',json.dumps(dict(
                endpoint=f'http://127.0.0.1:{server.server_port}',catalog_id=report['catalog_id'],token_file=str(token_path))).encode())
            client=agent_api.AgentClient.from_config(config)
            versions=client.selected_contracts()
            require(all(versions.get(name)==contract['version'] for name,contract in contracts.items()),'Negotiated authoring contracts differ.')
    def record(operation,arguments,value,interface,status=200):
        nonlocal sequence
        sequence+=1
        version=client.selected_contracts()[operation]
        envelope=dict(status=status,result=value)
        agent_api.validate_output(operation,envelope,version)
        save(f'agent-{sequence:03d}.json',dict(operation=operation,arguments=arguments,interface=interface,
            contract=agent_api.contract(operation,version),response=envelope))
        calls.append(dict(operation=operation,interface=interface,status=status,version=version))
        return value
    def cli(operation,arguments,*,refused=False):
        path=save('arguments-'+uuid.uuid4().hex+'.json',arguments)
        result=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),'call',
            '--operation',operation,'--arguments',str(path)],cwd=ROOT,capture_output=True,text=True,timeout=360)
        require(credential['token'] not in result.stdout+result.stderr,'CLI credential disclosure.')
        if refused:
            require(result.returncode==1,'Revoked CLI unexpectedly succeeded.')
            diagnostic=json.loads(result.stderr);require(diagnostic['status']==401,'Wrong revoked CLI refusal.')
            return diagnostic
        require(result.returncode==0,'Official CLI refused '+operation+': '+result.stderr[:1000])
        return record(operation,arguments,json.loads(result.stdout),'official_cli')
    async def mcp(operation,arguments):
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        path=private('mcp-stderr-'+uuid.uuid4().hex+'.private',b'')
        with path.open('w') as diagnostic:
            async with stdio_client(StdioServerParameters(command=sys.executable,
                    args=[str(ROOT/'mcp_stdio.py'),'--config',str(config)],cwd=str(ROOT)),errlog=diagnostic) as (read,write):
                async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=360)) as session:
                    await session.initialize();tools=await session.list_tools()
                    require(operation.replace('.','_') in {row.name for row in tools.tools},'Official MCP operation absent.')
                    result=await session.call_tool(operation.replace('.','_'),arguments)
                    require(not result.isError and result.structuredContent['status']<300,'Official MCP refused '+operation)
                    value=result.structuredContent['result']
        require(credential['token'] not in path.read_text(),'MCP credential disclosure.')
        return record(operation,arguments,value,'official_mcp')
    def call(operation,arguments):
        result=client.call(operation,arguments)
        require(result['status']<300,'Negotiated AgentClient refused '+operation)
        return record(operation,arguments,result['result'],'negotiated_agent_client',result['status'])
    def refusal(operation,arguments,status,code=None):
        before=domain(dataset);counts=counters(dataset)
        result=client.call(operation,arguments)
        require(result['status']==status and (code is None or result['result']['code']==code),
                'Unexpected refusal for '+operation)
        record(operation,arguments,result['result'],'negotiated_agent_client',status)
        require(before==domain(dataset) and counts==counters(dataset),'Refused operation changed domain/accounting.')
        return result
    def owner_approval(study_id,trial,material):
        body=dict(study_id=study_id,trial_id=trial['id'],expected_material_sha256=material['ref']['sha256'],
                  consumer_actor_id=report['actor_id'],ttl_seconds=600)
        method,path,data=agent_api.project_request('studies.approve',body,1)
        request=Request(f'http://127.0.0.1:{server.server_port}'+path,method=method,data=agent_api.encoded(data),
            headers={'Authorization':'Bearer '+owner['token'],'Content-Type':'application/json',
                     agent_api.CONTRACT_HEADER:agent_api.selected_header('studies.approve',1)})
        with urlopen(request,timeout=360) as response:value=json.loads(response.read())
        agent_api.validate_output('studies.approve',dict(status=200,result=value),1)
        save('owner-exact-approval.json',value);return value
    try:
        with psycopg.connect(original_connection,autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        start({'canonical-fixture':source},initial=True);report['catalog_id']=dataset.db.dataset_id
        with dataset.access.bind(owner['token']):
            fixture_result=fixture.build_canonical_fixture(dataset,source)
            save('owner-canonical-source.json',fixture_result['receipt'])
            authored=prepare(fixture_result,project,runtime_sha256=RUNTIME_SHA)
            verify_frozen_sources(project)
            snapshots=RuntimeSnapshots(dataset.db,dataset.access,dataset.path)
            inspected_runtime=snapshots.inspect(runtime_config)
            require(inspected_runtime['inventory_sha256']==RUNTIME_SHA,'Explicit main505 runtime differs; no fallback.')
            report['runtime']=snapshots.create(runtime_config,RUNTIME_SHA,quiesced=True)
            credential=dataset.access.issue(dict(label='Fresh main505 agent author',scopes=['inspect','edit','execute'],ttl_seconds=3600))
        report['actor_id']=credential['identity']['actor_id'];token_path=private('agent-token.private',credential['token'].encode())
        project_files=tree_inventory(project);fixture_files=tree_inventory(source)
        save('author-compiled-project.json',authored);save('application-source-freeze.json',frozen)
        save('compiled-project-inventory.json',project_files);save('canonical-fixture-inventory.json',fixture_files)
        stop();start(roots)
        identity=call('identity.get',{})
        require(identity['kind']=='agent' and set(identity['scopes'])=={'inspect','edit','execute'},'Expected ordinary scoped agent, never owner bootstrap.')
        listed=cli('project_snapshots.list',{})
        require('agent-extension' in listed['roots'] and authored['project']['id'] not in {row['id'] for row in listed['projects']},
                'Owner must not have opened the new extension snapshot.')
        opened=asyncio.run(mcp('project_snapshots.open',dict(root='agent-extension',manifest_path='project.json')))
        require(opened['id']==authored['project']['id'] and opened['manifest_sha256']==authored['project_sha256'],'Agent snapshot identity differs.')
        fetched=call('project_snapshots.get',dict(project_id=opened['id']))
        require(fetched==opened and fetched['schema_version']==2,'Agent opened/get snapshot differs.')
        refusal('projects.get',dict(project_id=opened['id']),400,'unsupported')
        require(len(fetched['recipes'])==1,'Select the single publicly discovered canonical recipe.')
        selected=fetched['recipes'][0]
        require(selected['integrity']=='verified' and selected['observed_sha256']==selected['sha256'],
                'Discovered recipe bytes differ from the snapshot declaration.')
        inspected=cli('recipes.inspect',dict(project_id=opened['id'],reference_id=selected['id'],expected_sha256=selected['sha256']))
        require({'task','model','trainer','evaluator','view'} <= {row['kind'] for row in inspected['extension_binding']['contributions']},'Five bound roles missing.')
        policy=inspected['definition']['model_evidence'];canonical_policy=policy['canonical']
        # Budget and epoch authority remain with the owner. No prepared Trial,
        # Model or graph is supplied by setup.
        with dataset.access.bind(owner['token']):
            study=dataset.studies.create(dict(name='Finite main505 agent-authoring Study',policy=inspected['selection_policy'],
                limits=dict(attempt_slots=1,admitted_wall_seconds=600,retained_bytes=64*1024**2,peak_staging_bytes=128*1024**2)))
        save('owner-closed-finite-study.json',study)
        require(study['open'] is False and study['trial_ids']==[],'Owner setup must leave an empty closed Study.')
        refusal('studies.continue',dict(study_id=study['id'],revision=study['revision'],
            admission_epoch=study['admission_epoch'],request_key='refused-agent-continue-'+uuid.uuid4().hex),403)
        specification=copy.deepcopy(policy['model_specification']);specification['configuration']=dict(CONFIGURATION)
        draft=cli('models.create',dict(name='Agent-authored nondefault canonical scalar A',kind='captured_source',
            task=inspected['model_task'],specification=specification,preprocessing_policy=policy['preprocessing_policy'],
            output_policy=policy['output_policy'],source_selector=dict(project_id=opened['id'],recipe_id=selected['id'],expected_sha256=selected['sha256'])))
        published=asyncio.run(mcp('models.publish',dict(model_id=draft['id'],revision=draft['revision'])))
        graph=cli('graphs.create_external',dict(name='Agent-authored main505 canonical finite graph',project_id=opened['id'],recipe_id=selected['id'],
            expected_sha256=selected['sha256'],inputs=dict(canonical=dict(kind='frozen_release',release_id=canonical_policy['release']['sha256'],expected_sha256=canonical_policy['release']['sha256']),
            derivation=dict(reference_id='derivation',expected_sha256=canonical_policy['derivation']['sha256']),
            provenance=dict(reference_id='provenance',expected_sha256=canonical_policy['provenance']['sha256'])),parameters=dict(learning_rate=.1,updates=64)))
        preflight=asyncio.run(mcp('graphs.preflight_external',dict(graph_id=graph['id'],revision=graph['revision'])))
        require(preflight['valid'] is True,'Agent-created graph did not pass negotiated preflight.')
        trial=cli('studies.prepare_trial',dict(study_id=study['id'],revision=study['revision'],request_key='prepare-'+uuid.uuid4().hex,
            graph_id=graph['id'],graph_revision=graph['revision'],model=published['ref'],replicate=0))
        material=call('recipes.material',dict(ref=trial['material']))
        require(material['material']['model']==published['ref'] and
                published['material']['specification']['sha256']==evidence.digest(specification),
                'Typed nondefault specification did not reach published/composed material.')
        current=cli('studies.get',dict(study_id=study['id']))['study']
        with dataset.access.bind(owner['token']):
            current=dataset.studies.continue_study(study['id'],dict(revision=current['revision'],
                admission_epoch=current['admission_epoch'],request_key='owner-continue-'+uuid.uuid4().hex))
        save('owner-reviewed-open-epoch.json',current)
        require(counters(dataset)['workspace_runs']==counters(dataset)['access_execution_grants']==0,'Agent authoring unexpectedly executed or granted.')
        refusal('studies.approve',dict(study_id=study['id'],trial_id=trial['id'],
            expected_material_sha256=material['ref']['sha256'],consumer_actor_id=report['actor_id'],ttl_seconds=600),403)
        grant=owner_approval(study['id'],trial,material)
        expected=dict(graph_id=graph['id'],graph_revision=graph['revision'],material_sha256=trial['material']['sha256'],
            model_sha256=published['ref']['sha256'],runtime_sha256=material['material']['runtime']['sha256'],
            task_sha256=published['material']['task']['sha256'],profile_definition_sha256=material['material']['evaluation_profile']['sha256'])
        selection=dict(format='extension_sdk_conformance_selection_v1',catalog_id=report['catalog_id'],actor_id=report['actor_id'],
            project_id=opened['id'],study_id=study['id'],trial_id=trial['id'],revision=current['revision'],admission_epoch=current['admission_epoch'],
            approval_id=grant['id'],request_key='main505-sdk-'+uuid.uuid4().hex,expected=expected)
        selection_path=save('sdk-selection.json',selection)
        report.update(state='authored_and_exactly_granted',project_id=opened['id'],study_id=study['id'],trial_id=trial['id'],model=published['ref'],
            material=material['ref'],approval_id=grant['id'],request_key=selection['request_key'],contracts=contracts,calls=calls)
        save('before-admission.json',report)
        report['admission_state']='may_have_been_sent';progress()
        command=[sys.executable,'-m','tuldok_extension_sdk','conformance','--config',str(config),'--cli',str(ROOT/'project_cli.py'),
            '--cli-sha256',digest(ROOT/'project_cli.py'),'--selection',str(selection_path),'--output',str(output/'artifacts'),'--deadline-seconds','600']
        try:completed=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=660)
        except subprocess.TimeoutExpired as error:
            save('sdk-process-observation.json',sdk_observation(error,credential['token']));raise
        save('sdk-process-observation.json',sdk_observation(completed,credential['token']))
        require(credential['token'] not in completed.stdout+completed.stderr,'SDK credential disclosure.')
        sdk=json.loads(completed.stdout);save('sdk-result.json',sdk)
        report['sdk_state']=sdk.get('state')
        report['admission_state']=sdk_admission_state(sdk)
        if sdk.get('run_id'):report['run_id']=sdk['run_id']
        require(completed.returncode==0 and sdk.get('state')=='passed','SDK did not establish completion; preserve state and never retry admission.')
        run=cli('runs.get',dict(run_id=sdk['run_id']))
        require(run['state']=='completed' and run['custody_phase']=='drained' and len(run['artifacts'])==32,'Actual canonical Run did not publish/drain its32 outputs.')
        save('run.json',run)
        context_raw=(output/'artifacts/execution-context.json').read_bytes();context_sha=verify_context_custody(run,context_raw)
        context=evidence.decode(context_raw)
        require(context['static']['model_specification']['configuration']==CONFIGURATION,'Actual context lost nondefault agent configuration.')
        oracle=subprocess.run([str(args.oracle_python),'-I','-S',str(project/'cold_oracle.py'),'--fixture',str(project/'authored-source.json'),
            '--release',str(project/'canonical-release.zip'),'--derivation',str(project/'canonical-derivation.json'),
            '--provenance',str(project/'canonical-source.json'),'--artifacts',str(output/'artifacts'),
            '--expected-context-sha256',context_sha,'--report',str(output/'oracle.json')],capture_output=True,text=True,timeout=60)
        require(oracle.returncode==0,'Frozen independent oracle refused: '+oracle.stderr[:1000]+oracle.stdout[:1000])
        report['oracle']=json.loads((output/'oracle.json').read_bytes())
        state=cli('studies.reconcile',dict(study_id=study['id']))
        verify_accounting(selection,material,run,context,state)
        require(state['study']['limits']['attempt_slots']==state['charged']['attempt_slots']==1,'Expected one finite charged slot.')
        save('study-accounting.json',state)
        public=cli('runs.model_evidence',dict(run_id=run['id']))
        require([row['clocks']['optimizer_update'] for row in public['checkpoint_index']['entries']]==[16,32,48,64],'Actual64-update/four-cadence evidence differs.')
        before=domain(dataset);before_counts=counters(dataset)
        stop()
        from runs import Runs
        from experiments import Experiments
        def no_cold_execution(*unused,**kwargs):
            cold_execution_attempts.append('attempted')
            raise AssertionError('Cold inspection cannot admit, submit or start execution.')
        for owner_class,name in ((Runs,'_start'),(Runs,'submit'),(Runs,'submit_external'),(Experiments,'admit')):
            cold_guards.enter_context(patch.object(owner_class,name,no_cold_execution))
        start({})
        require(dataset.projects.roots=={},'Cold inspection must have no configured original roots.')
        require(cli('runs.get',dict(run_id=run['id']))==run and cli('studies.get',dict(study_id=study['id']))==state and
            cli('models.material',dict(ref=published['ref']))==published and call('recipes.material',dict(ref=material['ref']))==material and
            cli('runs.model_evidence',dict(run_id=run['id']))==public,'Cold agent source/Model/material/Study/evidence differs.')
        cold=output/'cold-artifacts';cold.mkdir(mode=0o700)
        for item in run['artifacts']:
            downloaded=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),'download','--run-id',run['id'],
                '--name',item['name'],'--expected-sha256',item['sha256'],'--out',str(cold/item['name'])],cwd=ROOT,capture_output=True,text=True,timeout=180)
            require(downloaded.returncode==0 and digest(cold/item['name'])==item['sha256'] and
                (cold/item['name']).read_bytes()==(output/'artifacts'/item['name']).read_bytes(),'Cold agent whole artifact identity differs.')
        require(before==domain(dataset) and before_counts==counters(dataset),'Cold reads changed domain rows or execution/accounting counts.')
        require(all(before_counts[key]==1 for key in COUNTERS[:6]),'Exactly one Run/grant/consumption/reservation/Study/trial required.')
        report.update(state='agent_authoring_sdk_numerical_cold_passed',admission_state='completed',calls=calls,
            counts=before_counts,charged=state['charged'],cold_configured_roots={},artifacts=run['artifacts'],
            owner_authoring_operations=['canonical_source_fixture','runtime_capture','credential_issue',
                'finite_closed_study_create','reviewed_study_continue','one_exact_execution_approval'],
            agent_authoring_operations=list(AUTHORING),additional_admission=False,source_frozen=frozen==source_inventory(),
            remaining=['current credential revocation and old-client refusal are required before final receipt'])
        # Completion of these read-only negative controls is deliberately below
        # the sole admission. They never invoke a Study/Run mutation.
        before_negative=domain(dataset)
        module_spec=importlib.util.spec_from_file_location('main505_legacy_agent',ROOT/'tests/fixtures/agent_legacy_f588.py')
        legacy=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(legacy)
        old=legacy.AgentClient(f'http://127.0.0.1:{server.server_port}',credential['token'],report['catalog_id'])
        legacy_identity=old.call('identity.get',{})
        require(legacy_identity['status']==200 and legacy_identity['result']['actor_id']==report['actor_id'] and
                legacy_identity['result']['kind']=='agent','Frozen old client lost its supported identity operation.')
        save('old-client-identity.json',legacy_identity)
        try:old.call('project_snapshots.get',dict(project_id=opened['id']))
        except legacy.AgentAPIError as error:
            require(error.code=='unknown_operation' and error.status==400,'Wrong old-client operation refusal.')
            report['old_client_refusal']=dict(code=error.code,status=error.status)
        else:raise RuntimeError('Old client silently acquired the new snapshot operation.')
        async def revoke_controls():
            from mcp import ClientSession,StdioServerParameters
            from mcp.client.stdio import stdio_client
            path=private('revocation-mcp-stderr.private',b'')
            with path.open('w') as diagnostic:
                async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_stdio.py'),'--config',str(config)],cwd=str(ROOT)),errlog=diagnostic) as (read,write):
                    async with ClientSession(read,write,read_timeout_seconds=timedelta(seconds=180)) as session:
                        await session.initialize()
                        good=await session.call_tool('project_snapshots_get',dict(project_id=opened['id']))
                        require(not good.isError,'Cold current MCP snapshot inspection failed.')
                        require(good.structuredContent['result']['manifest_sha256']==opened['manifest_sha256'],'Cold snapshot declaration identity differs.')
                        with dataset.access.bind(owner['token']):dataset.access.revoke(credential['identity']['credential_id'])
                        bad=await session.call_tool('project_snapshots_get',dict(project_id=opened['id']))
                        require(bad.isError and bad.structuredContent['status']==401,'Persistent MCP accepted revoked snapshot read.')
            require(client.call('project_snapshots.get',dict(project_id=opened['id']))['status']==401,'Current AgentClient accepted revoked read.')
            cli('project_snapshots.get',dict(project_id=opened['id']),refused=True)
        asyncio.run(revoke_controls())
        require(domain(dataset)==before_negative,'Old-client/refused/revoked reads changed domain rows.')
        require(source_inventory()==frozen and tree_inventory(project)==project_files and tree_inventory(source)==fixture_files and
                digest(project/'producer.py')==verify_source_sha('producer.py'),'Frozen application/authored/fixture source changed.')
        for path in private_paths:
            if path.exists():path.unlink()
        require(all(not path.exists() for path in private_paths),'Private credential/config cleanup failed.')
        report.update(remaining=[],current_revocation=dict(agent_http=401,official_mcp_persistent=401,official_cli_bootstrap=401),
            no_owner_agent_client=True,private_credentials_removed=True,source_frozen=True,authored_project_unchanged=True,
            canonical_fixture_unchanged=True,
            cold_execution_attempts=cold_execution_attempts)
        require(not cold_execution_attempts,'Cold execution tripwire was reached.')
        save('receipt.json',report)
        print(report['state'],run['id'],output,flush=True)
    except BaseException as error:
        if report['admission_state']=='may_have_been_sent':report['admission_state']='unknown'
        report.update(state='failed' if report['admission_state']!='unknown' else 'unknown',failure_type=type(error).__name__,failure=str(error))
        save('failure.json',report);raise
    finally:
        try:
            if dataset is not None and credential is not None and owner is not None:
                with dataset.access.bind(owner['token']):dataset.access.revoke(credential['identity']['credential_id'])
        finally:
            try:stop()
            finally:
                cold_guards.close()
                for path in private_paths:
                    if path.exists():path.unlink()


def sdk_admission_state(result):
    if result.get('state')=='passed':return 'completed'
    if result.get('run_id'):return 'run_observed'
    if result.get('state') in ('refused','stale','unsupported'):return 'refused'
    return 'unknown'


def verify_source_sha(name):
    from qualify_extension_canonical import FROZEN_SOURCES
    return FROZEN_SOURCES[name]


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--workspace',type=Path,required=True)
    result.add_argument('--expected-host-commit',required=True)
    result.add_argument('--runtime-config',type=Path,required=True)
    result.add_argument('--oracle-python',type=Path,required=True)
    result.add_argument('--expected-runtime-sha256',default=RUNTIME_SHA)
    return result


if __name__=='__main__':main(parser().parse_args())
