"""Real authored A through normal owner/Study/custody and independent cold state.

Provision a disposable PostgreSQL URL and the reviewed CPU runtime separately.
This does not assert UI/agent field projection or physical/product acceptance.
"""
import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api
from app import Dataset,make_handler
from pipeline import digest
from runtime_snapshots import RuntimeSnapshots

ORACLE_SHA='ccfbe3bc92badf265ea882382d392e05daca091f5694f528f268ec3d6e38764b'
FIXTURE_SHA='3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f'
RUNTIME_SHA='0b15b611ead55bd5fa6f2f7bbcc56870f6e9f9f60f2192d989e7473ef8af1826'


def require(value,reason):
    if not value:raise RuntimeError(reason)


def qualification_inputs(args):
    package=getattr(args,'project_template',ROOT/'examples/extensions/field-surrogate/v2').resolve()
    expected=getattr(args,'expected_runtime_sha256',RUNTIME_SHA)
    require(type(expected) is str and len(expected)==64 and all(c in '0123456789abcdef' for c in expected),
            'Select an exact expected runtime snapshot SHA256')
    for name,sha in (('fixture.json',FIXTURE_SHA),('cold_oracle.py',ORACLE_SHA)):
        require(hashlib.sha256((package/name).read_bytes()).hexdigest()==sha,'Frozen '+name+' differs')
    recipe=json.loads((package/'recipe.json').read_bytes())
    require(recipe['runtime']=='captured_cpu_python_v1' and recipe['runtime_snapshot_sha256']==expected,
            'Project runtime nomination differs from explicitly expected snapshot; no fallback')
    return package,expected


def main(args):
    package,expected_runtime=qualification_inputs(args)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    project=args.project.resolve() if args.project is not None else output/'project'
    if args.project is None:shutil.copytree(package,project)
    else:
        template_recipe=json.loads((package/'recipe.json').read_bytes())
        for name in ['project.json','recipe.json','fixture.json',*[row['path'] for row in template_recipe['sources']]]:
            require((project/name).read_bytes()==(package/name).read_bytes(),'Existing exact project differs: '+name)
    recipe=json.loads((project/'recipe.json').read_bytes());policy=recipe['model_evidence']
    require(recipe['runtime_snapshot_sha256']==expected_runtime,'Copied project runtime nomination changed')
    dataset=server=worker=owner=credential=None;endpoint=config=None;sequence=0
    report={'state':'in_progress','scope':'Actual A CPU/Study/custody/cold scientific state; UI/agent field projection pending',
        'host_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'oracle_sha256':ORACLE_SHA,'fixture_sha256':FIXTURE_SHA,'checks':[],
        'catalog_path':str(args.catalog.resolve()),'project_roots':{'extension-a':str(project)},
        'expected_runtime_snapshot_sha256':expected_runtime,
        'project_runtime_nomination':{'template':str(package),'recipe_sha256':hashlib.sha256((project/'recipe.json').read_bytes()).hexdigest(),
            'runtime':recipe['runtime'],'runtime_snapshot_sha256':recipe['runtime_snapshot_sha256'],
            'relationship':'original_0b15_profile' if expected_runtime==RUNTIME_SHA else 'explicit_new_runtime_QA_nomination'},
        'physical_acceptance':'not_established','product_acceptance':'not_established'}
    def write(name,value):
        path=output/name
        with path.open('x') as handle:json.dump(value,handle,indent=2,allow_nan=False);handle.write('\n')
        return path
    def private(name,raw):
        path=output/name;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(raw)
        return path
    def start():
        nonlocal dataset,owner,server,worker,endpoint
        dataset=Dataset(args.catalog.resolve(),project_roots={'extension-a':project})
        owner=dataset.access.exchange(dataset.access._local_owner_token())
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        endpoint=f'http://127.0.0.1:{server.server_port}'
    def stop():
        nonlocal dataset,owner,server,worker
        if server is not None:server.shutdown();server.server_close();worker.join(timeout=5);server=worker=None
        if dataset is not None:
            if owner is not None:
                with dataset.access.bind(owner['token']):dataset.access.logout()
            dataset.close();dataset=owner=None
    def cli(*values):
        result=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),*map(str,values)],
            capture_output=True,text=True,timeout=360)
        require(credential['token'] not in result.stdout+result.stderr,'Credential disclosure')
        require(result.returncode==0,'Production CLI refused: '+result.stderr[:2000])
        return json.loads(result.stdout)
    def call(operation,body):
        nonlocal sequence
        sequence+=1;path=write(f'call-{sequence:03d}-{operation}-input.json',body)
        value=cli('call','--operation',operation,'--arguments',path)
        write(f'call-{sequence:03d}-{operation}-output.json',value);return value
    def http(operation,body,*,path_override=None,expect=None,version=1):
        nonlocal sequence
        sequence+=1
        if path_override is None:method,path,data=agent_api.project_request(operation,body,1)
        else:method,path,data='POST',path_override,body
        request=Request(endpoint+path,method=method,data=None if data is None else agent_api.encoded(data),
            headers={'Authorization':'Bearer '+owner['token'],'Content-Type':'application/json',
                     agent_api.CONTRACT_HEADER:agent_api.selected_header(operation,version)})
        try:
            with urlopen(request,timeout=360) as response:status=response.status;value=json.loads(response.read())
        except HTTPError as error:status=error.code;value=json.loads(error.read())
        write(f'http-{sequence:03d}-{operation}.json',{'status':status,'result':value})
        require((200<=status<300) if expect is None else status==expect, f'{operation} HTTP{status}: '+str(value)[:1500])
        if expect is None:agent_api.validate_output(operation,{'status':status,'result':value},version)
        return value
    def evidence(run_id,selectors=None,expect=None):
        return http('runs.model_evidence',{} if selectors is None else selectors,
                    path_override=f'/api/workspace/runs/{run_id}/model-evidence',expect=expect,version=2)
    def download(run,name):
        target=output/name;target.mkdir();receipts=[]
        for item in run['artifacts']:
            value=cli('download','--run-id',run['id'],'--name',item['name'],'--expected-sha256',item['sha256'],'--out',target/item['name'])
            require(value['verification']=='whole_sha256_verified' and value['bytes']==item['bytes'],'Download integrity differs')
            receipts.append(value)
        return receipts
    try:
        start();report['catalog_id']=dataset.db.dataset_id
        with dataset.access.bind(owner['token']):
            snapshots=RuntimeSnapshots(dataset.db,dataset.access,dataset.path)
            inventory=snapshots.inspect(json.loads(args.runtime_config.read_bytes()))
            require(inventory['inventory_sha256']==expected_runtime,'Actual runtime differs from explicitly nominated snapshot')
            report['runtime']=snapshots.create(json.loads(args.runtime_config.read_bytes()),expected_runtime,quiesced=True)
            credential=dataset.access.issue({'label':'Explicit extension A CPU qualification','scopes':['inspect','edit','execute','cancel']})
        private('agent-token.private',credential['token'])
        def configure(name):return private(name,json.dumps({'endpoint':endpoint,'catalog_id':report['catalog_id'],'token_file':str(output/'agent-token.private')}))
        config=configure('agent-config.private');report['actor_id']=credential['identity']['actor_id']
        opened=cli('open','--root','extension-a','--manifest','project.json');write('opened.json',opened)
        registration=json.loads((project/'project.json').read_bytes());selected=registration['recipes'][0]
        graph=cli('prepare','--arguments',write('graph-input.json',{'name':'Actual explicit A evidence',
            'project_id':opened['id'],'recipe_id':selected['id'],'expected_sha256':selected['sha256'],
            'inputs':{'fixture':{'reference_id':'fixture','expected_sha256':FIXTURE_SHA}},'parameters':{}}))
        write('graph.json',graph)
        model=http('models.create',{'name':'Authored affine scalar A v2','kind':'captured_source',
            'task':{'kind':'task','catalog_id':report['catalog_id'],'id':policy['task']['id'],'revision':policy['task']['revision'],'sha256':digest(policy['task']['definition'])},
            'specification':policy['model_specification'],'preprocessing_policy':policy['preprocessing_policy'],
            'output_policy':policy['output_policy'],'source_selector':{'project_id':opened['id'],'recipe_id':selected['id'],'expected_sha256':selected['sha256']}})
        published=http('models.publish',{'model_id':model['id'],'revision':model['revision']})
        selection={'format':'selection_policy_v1','metric_definition_sha256':digest(policy['metric_definitions'][0]),
            'checkpoint_rule':'last','replicate_reduce':'individual','required_capabilities':policy['profile']['required_capabilities'],
            'numerical_acceptance':'diagnostic','tie_break':'trial_id'}
        study=http('studies.create',{'name':'One actual authored A evidence attempt','policy':selection,
            'limits':{'attempt_slots':1,'admitted_wall_seconds':600,'retained_bytes':100*1024**2,'peak_staging_bytes':100*1024**2}})
        trial=call('studies.prepare_trial',{'study_id':study['id'],'request_key':'prepare-'+uuid.uuid4().hex,
            'revision':study['revision'],'graph_id':graph['id'],'graph_revision':graph['revision'],'model':published['ref'],'replicate':0})
        material=call('recipes.material',{'ref':trial['material']})
        current=call('studies.get',{'study_id':study['id']})['study']
        current=http('studies.continue',{'study_id':study['id'],'request_key':'continue-'+uuid.uuid4().hex,
            'revision':current['revision'],'admission_epoch':current['admission_epoch']})
        grant=http('studies.approve',{'study_id':study['id'],'trial_id':trial['id'],
            'expected_material_sha256':trial['material']['sha256'],'consumer_actor_id':report['actor_id']})
        body={'study_id':study['id'],'request_key':'admit-'+uuid.uuid4().hex,'revision':current['revision'],
            'admission_epoch':current['admission_epoch'],'trial_id':trial['id'],'approval_id':grant['id']}
        admitted=call('studies.admit',body);run=admitted['run'];report.update(study_id=study['id'],trial_id=trial['id'],
            model=published['ref'],material=trial['material'],run_id=run['id'],approval_id=grant['id'],envelope=material['material']['resource_envelope'])
        print('ADMITTED actual E2 A',run['id'],flush=True)
        deadline=time.monotonic()+420
        while run['state'] in ('queued','running','cancelling') and time.monotonic()<deadline:
            time.sleep(.5);run=cli('status','--run-id',run['id'])
        write('run.json',run)
        require(run['state']=='completed' and run['custody_phase']=='drained','Actual A not completed/drained: '+str(run.get('error')))
        report['downloads']=download(run,'artifacts')
        with dataset.access.bind(owner['token']),dataset.lock:
            retained=dataset.runs._load(run['id']);context_ref=retained['spec']['model_evidence_context']
            report['custody_context']=context_ref
            report['captured_files']=len(retained['spec']['captured_files'])
            report['captured_bytes']=sum(row['bytes'] for row in retained['spec']['captured_files'])
        oracle=subprocess.run([str(args.oracle_python),str(package/'cold_oracle.py'),'--fixture',str(project/'fixture.json'),
            '--artifacts',str(output/'artifacts'),'--expected-context-sha256',context_ref['sha256'],'--report',str(output/'oracle.json')],
            capture_output=True,text=True,timeout=30)
        require(oracle.returncode==0,'Frozen independent consumer refused: '+oracle.stdout[:1500]+oracle.stderr[:1500])
        report['oracle']=json.loads((output/'oracle.json').read_bytes())
        try:agent_api.contract('runs.model_evidence',2);field_contract=True
        except agent_api.AgentAPIError:field_contract=False
        public=evidence(run['id']) if field_contract else None;field=None
        if public is not None:write('evidence.json',public)
        report['selected_field_state']=public['state'] if public is not None else 'unavailable; selected contract2 not composed'
        if public is not None and public['state']=='verified':
            require([row['clocks']['optimizer_update'] for row in public['checkpoint_index']['entries']]==[16,32,48,64],'Actual checkpoints missing')
            selected_sha=public['checkpoint_index']['entries'][-1]['checkpoint']['sha256']
            query={'checkpoint_sha256':selected_sha,'member_ordinal':0,'field_id':'raw','axis':'z','index':1}
            field=evidence(run['id'],query);write('field.json',field)
            require(field['field']['shape_zyx']==[4,4,4],'Native field shape differs')
            evidence(run['id'],dict(query,split='test'),expect=400)
            evidence(run['id'],dict(query,checkpoint_sha256='f'*64),expect=409)
        else:
            require(public is None or public['state']=='unsupported','Unexpected evidence outcome')
            require(not args.require_public_fields,'Main-owned explicit public field projection is unavailable; actual oracle evidence retained')
        duplicate=call('studies.admit',body)
        require(duplicate['run']['id']==run['id'] and duplicate['reservation']['id']==admitted['reservation']['id'],'Exact receipt changed')
        state=call('studies.reconcile',{'study_id':study['id']})
        require(state['charged']['attempt_slots']==1 and len(state['reservations'])==1 and state['reservations'][0]['state']=='settled','Finite Study accounting differs')
        report['checks'].append('Actual captured CPU fit64 updates,4 checkpoints/probes, ordinary exact grant/custody/drainage, all declared whole-hash downloads and independent stdlib numerical consumer passed.')
        stop();start();config=configure('cold-agent-config.private')
        require(cli('status','--run-id',run['id'])==run,'Cold Run changed')
        require(call('recipes.material',{'ref':trial['material']})==material,'Cold material changed')
        require(call('models.material',{'ref':published['ref']})==published,'Cold Model changed')
        if public is not None:require(evidence(run['id'])==public,'Cold evidence meaning changed')
        if field is not None:require(evidence(run['id'],query)==field,'Cold field query changed')
        require(call('studies.get',{'study_id':study['id']})==state,'Cold Study/accounting changed')
        report['cold_downloads']=download(run,'cold-artifacts')
        report['checks'].append('Cold service/catalog reopen preserves exact Model/material/Study/Run and every whole-hash download; public evidence availability preserves its actual meaning.')
        report['state']='source_custody_numerical_passed' if field is None else 'public_field_path_passed'
        report['remaining']=['Main-owned explicit selected public field operation and native UI; full E2 acceptance pending.'] if field is None else ['Native UI and all E2 negatives; full E2 acceptance pending.']
        write('receipt.json',report);print(report['state'],output,flush=True)
    except BaseException as error:
        report['failure']=str(error);write('failure.json',report);raise
    finally:
        if dataset is not None and credential is not None:
            with dataset.access.bind(owner['token']):dataset.access.revoke(credential['identity']['credential_id'])
        stop()


def qualify_retained_negatives(args):
    """Fault only task-owned source/retained files, restore in finally; no new Run."""
    from workbench import WorkbenchError
    base=args.existing_receipt.resolve().parent
    original=json.loads(args.existing_receipt.read_bytes())
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    dataset=Dataset(args.catalog.resolve(),project_roots={'extension-a':args.project.resolve()})
    owner=dataset.access.exchange(dataset.access._local_owner_token(require_existing=True))
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    endpoint=f'http://127.0.0.1:{server.server_port}';checks=[];sequence=0
    def counts():
        with dataset.lock:
            return {table:dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                    ('workspace_runs','access_execution_consumptions','access_execution_grants','model_attempt_reservations')}
    def http(operation,body,expected=None):
        nonlocal sequence
        method,path,data=agent_api.project_request(operation,body,1)
        request=Request(endpoint+path,method=method,data=None if data is None else agent_api.encoded(data),
            headers={'Authorization':'Bearer '+owner['token'],'Content-Type':'application/json',
                     agent_api.CONTRACT_HEADER:agent_api.selected_header(operation)})
        try:
            with urlopen(request,timeout=360) as response:status=response.status;value=json.loads(response.read())
        except HTTPError as error:status=error.code;value=json.loads(error.read())
        sequence+=1;(output/f'{sequence:02d}-{operation}.json').write_text(json.dumps({'status':status,'result':value},indent=2)+'\n')
        require((200<=status<300) if expected is None else status==expected,operation+' unexpected HTTP'+str(status)+': '+str(value)[:1000])
        agent_api.validate_output(operation,{'status':status,'result':value},1)
        return value
    def refused(label,action):
        try:action()
        except WorkbenchError as error:
            require(error.code in ('unavailable','unsupported','stale','invalid','conflict'),label+' unexpected refusal')
            checks.append({'check':label,'state':'refused','code':error.code});return
        raise RuntimeError(label+' unexpectedly succeeded')
    def fault(path,raw,action):
        before=path.read_bytes();mode=path.stat().st_mode&0o777
        try:
            path.chmod(0o600);path.write_bytes(raw);path.chmod(mode);action()
        finally:
            path.chmod(0o600);path.write_bytes(before);path.chmod(mode)
    try:
        with dataset.access.bind(owner['token']):
            run=dataset.runs.get(original['run_id']);baseline=counts()
            require(run['state']=='completed' and run['custody_phase']=='drained','Expected retained completed Run')
            graph=run['graph'];material=dataset.pipelines.recipe_material(original['material'],verify=True)
            def unchanged(label):require(counts()==baseline,label+' changed admission/grant/reservation counts')
            current=dataset.pipelines.preflight_external(graph['id'],graph['revision'])
            http('runs.submit_external',{'request_key':'plain-model-evidence-'+uuid.uuid4().hex,
                'graph_id':graph['id'],'graph_revision':graph['revision'],'expected_digest':current['material_sha256'],
                'approval_id':original['approval_id']},expected=409)
            unchanged('Legacy submission refusal');checks.append({'check':'New variant refuses executable-only legacy submission before implicit grant/Run/reservation','state':'passed'})
            source=args.project.resolve()/'producer.py'
            def source_fault():
                http('graphs.preflight_external',{'graph_id':graph['id'],'revision':graph['revision']},expected=409)
                unchanged('Source drift refusal')
            fault(source,source.read_bytes()+b'\n# exact captured source drift negative\n',source_fault)
            checks.append({'check':'Actual changed project source refuses retained-material preflight without admission effects','state':'passed'})
            profile=dataset.pipelines.material_path/original['material']['sha256']/'profile.json'
            bad=json.loads(profile.read_bytes());bad['capture']['interval']+=1
            def profile_fault():
                http('recipes.material',{'ref':original['material']},expected=409)
                http('runs.get',{'run_id':run['id']},expected=409)
                unchanged('Profile tamper refusal')
            fault(profile,agent_api.encoded(bad),profile_fault)
            checks.append({'check':'Changed retained profile refuses material and actual cold Run reads','state':'passed'})
            name='execution-context.json';item=next(item for item in run['artifacts'] if item['name']==name)
            path=dataset.runs.path/run['id']/name;raw=path.read_bytes().replace(run['id'].encode(),b'f'*32)
            require(len(raw)==item['bytes'] and raw!=path.read_bytes(),'Context corruption fixture is not same-length distinct bytes')
            def context_fault():
                refused('whole artifact',lambda:dataset.runs.artifact(run['id'],name))
                def stream():
                    with dataset.runs.open_artifact(run['id'],name):pass
                refused('stream artifact',stream)
                refused('artifact segment',lambda:dataset.runs.artifact_segment(run['id'],name,{'expected_sha256':item['sha256'],'offset':0,'max_bytes':1024}))
                refused('artifact capture',lambda:dataset.runs.capture_artifact(run['id'],name,item['sha256']))
                refused('model evidence query',lambda:dataset.runs.model_evidence(run['id'],{},contract_version=2))
                entry=next(row for row in dataset.runs.input_candidates()['runs'] if row['run_id']==run['id'])
                require(entry['status']=='unavailable' and entry['artifacts']==[],'Invalid scientific output leaked through input inventory')
                checks.append({'check':'Run input inventory','state':'unavailable; no artifacts'})
                http('runs.artifact_chunk',{'run_id':run['id'],'name':name,'expected_sha256':item['sha256'],'offset':0,'max_bytes':1024},expected=409)
                unchanged('Wrong context refusal')
            fault(path,raw,context_fault)
            refused('scientific test selector',lambda:dataset.runs.model_evidence(run['id'],{'split':'test'},contract_version=2))
            # Wrong Task is a separately published inert Model, never a forged Run.
            policy=json.loads((args.project.resolve()/'recipe.json').read_bytes())['model_evidence']
            published=dataset.models.material(original['model'],verify=True)
            wrong=http('models.create',{'name':'Actual mismatched Task negative','kind':'captured_source',
                'task':dict(published['material']['task'],id='example.scalar-a:wrong-task'),
                'specification':policy['model_specification'],'preprocessing_policy':policy['preprocessing_policy'],
                'output_policy':policy['output_policy'],'source_selector':published['material']['source_selector']})
            wrong=http('models.publish',{'model_id':wrong['id'],'revision':wrong['revision']})
            study=http('studies.create',{'name':'Bounded mismatched Task preparation negative',
                'limits':{'attempt_slots':1,'admitted_wall_seconds':600,'retained_bytes':100*1024**2,'peak_staging_bytes':100*1024**2},
                'policy':{'format':'selection_policy_v1','metric_definition_sha256':digest(policy['metric_definitions'][0]),
                    'checkpoint_rule':'last','replicate_reduce':'individual','required_capabilities':policy['profile']['required_capabilities'],
                    'numerical_acceptance':'diagnostic','tie_break':'trial_id'}})
            http('studies.prepare_trial',{'study_id':study['id'],'request_key':'wrong-task-'+uuid.uuid4().hex,
                'revision':study['revision'],'graph_id':graph['id'],'graph_revision':graph['revision'],'model':wrong['ref'],'replicate':0},expected=409)
            unchanged('Mismatched Task preparation')
            checks.append({'check':'Actual published wrong-Task Model refuses normal HTTP Study preparation before grant/reservation/Run','state':'passed'})
            require(dataset.runs.get(run['id'])==run,'Restored Run meaning changed')
            require(dataset.pipelines.recipe_material(original['material'],verify=True)==material,'Restored material changed')
            require(dataset.runs.model_evidence(run['id'],{},contract_version=2)['state']=='verified','Restored evidence did not verify')
            for item in run['artifacts']:
                current=dataset.runs.artifact(run['id'],item['name'])[0]
                require(hashlib.sha256(current).hexdigest()==item['sha256'] and current==(base/'artifacts'/item['name']).read_bytes(),'Negative cleanup changed retained artifact')
            unchanged('Final cleanup')
            receipt={'state':'passed','scope':'Actual retained source/context/profile/Task/legacy-admission negatives; no new execution or public contract2/UI claim',
                'host_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'run_id':run['id'],
                'counts_before':baseline,'counts_after':counts(),'checks':checks,'all_original_artifacts_restored':True}
            (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PASS actual retained negatives',output,flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        with dataset.access.bind(owner['token']):dataset.access.logout()
        dataset.close()


def qualify_public_fields(args):
    """Inspect a real retained Run through selected HTTP and production agent CLI."""
    original=json.loads(args.existing_receipt.read_bytes());output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    dataset=Dataset(args.catalog.resolve(),project_roots={'extension-a':args.project.resolve()})
    owner=dataset.access.exchange(dataset.access._local_owner_token(require_existing=True));credential=None
    headers=[];base=make_handler(dataset)
    class ObservedHandler(base):
        def do_POST(self):
            headers.append({'path':self.path,'selection':self.headers.get(agent_api.CONTRACT_HEADER)})
            return super().do_POST()
    server=ThreadingHTTPServer(('127.0.0.1',0),ObservedHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();endpoint=f'http://127.0.0.1:{server.server_port}'
    sequence=0
    def save(name,value):
        path=output/name;path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');return path
    def private(name,value):
        path=output/name;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as handle:handle.write(value)
        return path
    def query(body,version=2,expected=200):
        nonlocal sequence
        request=Request(endpoint+f'/api/workspace/runs/{original["run_id"]}/model-evidence',method='POST',data=agent_api.encoded(body),
            headers={'Authorization':'Bearer '+owner['token'],'Content-Type':'application/json',
                     agent_api.CONTRACT_HEADER:agent_api.selected_header('runs.model_evidence',version)})
        try:
            with urlopen(request,timeout=60) as response:status=response.status;value=json.loads(response.read())
        except HTTPError as error:status=error.code;value=json.loads(error.read())
        require(status==expected,'Unexpected selected field HTTP'+str(status)+': '+str(value)[:1000])
        agent_api.validate_output('runs.model_evidence',{'status':status,'result':value},version)
        sequence+=1;save(f'owner-{sequence:02d}-v{version}.json',{'body':body,'status':status,'result':value});return value
    try:
        with dataset.access.bind(owner['token']):
            run=dataset.runs.get(original['run_id']);before=dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0]
            credential=dataset.access.issue({'label':'Read-only actual field contract2 co-test','scopes':['inspect']})
        token=private('token.private',credential['token'])
        config=private('config.private',json.dumps({'endpoint':endpoint,'catalog_id':original['catalog_id'],'token_file':str(token)}))
        def cli(body):
            nonlocal sequence
            sequence+=1;path=save(f'agent-{sequence:02d}-arguments.json',dict(body,run_id=run['id']))
            result=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),'call',
                '--operation','runs.model_evidence','--arguments',str(path)],capture_output=True,text=True,timeout=120)
            require(credential['token'] not in result.stdout+result.stderr,'Agent credential disclosure')
            require(result.returncode==0,'Actual agent field call refused: '+result.stderr[:1000])
            value=json.loads(result.stdout);save(f'agent-{sequence:02d}-result.json',value);return value
        require(query({},1)['state']=='unsupported','Classifier v1 meaning changed for external evidence')
        public=query({});require(public['state']=='verified' and cli({})==public,'Index HTTP/agent parity differs')
        requests=[]
        for entry in public['checkpoint_index']['entries']:
            for field in public['fields']:
                if field['checkpoint_sha256']!=entry['checkpoint']['sha256']:continue
                for axis in ('x','y','z'):
                    body={'checkpoint_sha256':entry['checkpoint']['sha256'],'member_ordinal':field['member_ordinal'],
                        'field_id':field['field_id'],'axis':axis,'index':field['shape_zyx']['zyx'.index(axis)]-1,'split':'validation'}
                    current=query(body);require(cli(body)==current,'Exact selected field HTTP/agent parity differs')
                    require(current['field']['checkpoint_sha256']==body['checkpoint_sha256'] and current['field']['axis']==axis,
                            'Wrong field context replaced selection')
                    requests.append(body)
        query({'split':'test'},expected=400)
        query(dict(requests[0],checkpoint_sha256='f'*64),expected=409)
        query(dict(requests[0],run_id='f'*32),expected=409)
        with dataset.access.bind(owner['token']):
            require(dataset.runs.get(run['id'])==run,'Read-only field inspection changed the Run')
            require(dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0]==before,'Field inspection admitted a Run')
        require(all(row['path'].endswith('/model-evidence') for row in headers),'Unexpected mutation route')
        require(sum(row['selection']==agent_api.selected_header('runs.model_evidence',2) for row in headers)>=2*len(requests),
                'Production agent did not actually select contract2')
        receipt={'state':'passed','scope':'Actual selected HTTP and production read-only agent contract2 parity on retained A; no producer replay',
            'host_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'run_id':run['id'],
            'catalog_id':original['catalog_id'],'contract2_sha256':agent_api.contract('runs.model_evidence',2)['sha256'],
            'exact_requests':requests,'request_headers':headers,'run_count_before':before,'run_count_after':before,
            'v1_state':'unsupported','selected_test_state':'400 invalid','wrong_checkpoint_state':'409 stale',
            'physical_acceptance':'not_established','canonical_release_derivation':'unsupported in authored-only mode'}
        save('receipt.json',receipt);print('PASS actual selected HTTP/agent field parity',output,flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
        with dataset.access.bind(owner['token']):
            if credential is not None:dataset.access.revoke(credential['identity']['credential_id'])
            dataset.access.logout()
        dataset.close()


def argument_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-only',action='store_true',help='Co-test selected HTTP and agent fields for an existing real receipt; never admit')
    parser.add_argument('--existing-receipt',type=Path,help='Run only retained fault negatives against a prior real qualification receipt')
    parser.add_argument('--project',type=Path)
    parser.add_argument('--require-public-fields',action='store_true')
    parser.add_argument('--project-template',type=Path,default=ROOT/'examples/extensions/field-surrogate/v2')
    parser.add_argument('--expected-runtime-sha256',default=RUNTIME_SHA)
    parser.add_argument('--catalog',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-config',type=Path,required=True);parser.add_argument('--oracle-python',type=Path,required=True)
    return parser


if __name__=='__main__':
    parser=argument_parser();arguments=parser.parse_args()
    if arguments.existing_receipt is not None:
        if arguments.project is None:parser.error('--existing-receipt requires --project')
        (qualify_public_fields if arguments.public_only else qualify_retained_negatives)(arguments)
    else:main(arguments)
