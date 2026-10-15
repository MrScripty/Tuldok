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


def main(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    package=ROOT/'examples/extensions/field-surrogate/v2'
    for name,sha in (('fixture.json',FIXTURE_SHA),('cold_oracle.py',ORACLE_SHA)):
        require(hashlib.sha256((package/name).read_bytes()).hexdigest()==sha,'Frozen '+name+' differs')
    project=output/'project';shutil.copytree(package,project)
    recipe=json.loads((project/'recipe.json').read_bytes());policy=recipe['model_evidence']
    dataset=server=worker=owner=credential=None;endpoint=config=None;sequence=0
    report={'state':'in_progress','scope':'Actual A CPU/Study/custody/cold scientific state; UI/agent field projection pending',
        'host_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'oracle_sha256':ORACLE_SHA,'fixture_sha256':FIXTURE_SHA,'checks':[],
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
            require(inventory['inventory_sha256']==RUNTIME_SHA,'Actual runtime differs from reviewed snapshot')
            report['runtime']=snapshots.create(json.loads(args.runtime_config.read_bytes()),RUNTIME_SHA,quiesced=True)
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
            evidence(run['id'],dict(query,split='test'),expect=409)
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


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-public-fields',action='store_true')
    parser.add_argument('--catalog',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-config',type=Path,required=True);parser.add_argument('--oracle-python',type=Path,required=True)
    main(parser.parse_args())
