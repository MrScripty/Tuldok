"""Actual new canonical/catalog A using one owner-granted SDK admission.

Requires accepted shared schema3/canonical hooks. This driver never substitutes
synthetic model results, starts local training, retries an uncertain admission,
or rewrites a historical project/Model/Run. All credentials stay in private files.
"""
import argparse
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_api
from app import Dataset,make_handler
import extension_canonical_fixture as source_author
import extension_evidence as evidence
from prepare_extension_canonical_project import prepare, RUNTIME_SHA, PACKAGE
import recipe_contract
from runtime_snapshots import RuntimeSnapshots


def require(value,reason):
    if not value:raise RuntimeError(reason)



FROZEN_SOURCES = {
    'producer.py':'bcd801264bf05675cc6b2c5207848f723a38090b5bee6211543040831b801922',
    'cold_oracle.py':'573f142de868d13649dcdb6cc109fd629385b8ce48a1968399c0f86cb77feed9',
    'authored-source.json':'3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f',
    'tuldok_extension_sdk/evidence.py':'94e17b5f0e21bdfddf24771e223e85fced6561f73da1fac55250906cf8d4de23',
    'tuldok_extension_sdk/__init__.py':'b7e0b3167de54dd1ce8bf5209af92ee0bcab9ba6eb6fc9f8c7db4e3fea96fc18',
    'infer.py':'15f6bc0da835f4a3f8a54a2abf0552e8a0b6c69a1ac2e6baceebb9288a0b8b15',
    'inference-contract.json':'d60b93699f978c125a567734ef4d610cb4027b3b2f047c31e6d579677121da1d',
}


def verify_frozen_sources(project):
    for name,sha in FROZEN_SOURCES.items():
        require(hashlib.sha256((project/name).read_bytes()).hexdigest()==sha,'Reviewed canonical source differs: '+name)
    require(hashlib.sha256((ROOT/'tests/prepare_extension_canonical_project.py').read_bytes()).hexdigest()==
            'f9c79299af58324e15c1eb778d4cd2dd3678b09006fc3d7b3c1f6b423b84d80e','Reviewed canonical author compiler differs')


def verify_accounting(selection,material,run,context,state):
    envelope=material['material']['resource_envelope']
    dimensions={'attempt_slots','admitted_wall_seconds','retained_bytes','peak_staging_bytes'}
    require(set(envelope)==dimensions and all(type(value) is int and value>=0 for value in envelope.values()),'Expected bounded resource envelope')
    require(len(state['reservations'])==1,'Expected exactly one actual reservation')
    reservation=state['reservations'][0]
    for key in ('study_id','trial_id','actor_id','admission_epoch','request_key'):
        require(evidence.identical(reservation[key],selection[key]),'Reservation identity differs: '+key)
    require(reservation['run_id']==run['id'] and reservation['material_sha256']==selection['expected']['material_sha256'] and
            reservation['parent_run_id'] is None and run['parent_run_id'] is None and reservation['state']=='settled',
            'Reservation Run/material/parent/state differs')
    for actual in (state['charged'],reservation['envelope'],reservation['settled']):
        require(evidence.identical(actual,envelope),'All four reserved/charged/settled resource dimensions must match actual material')
    body={key:selection[key] for key in ('request_key','revision','admission_epoch','trial_id','approval_id')}
    request_sha=evidence.digest(dict(operation_id='studies.admit',version=1,contract_sha256=agent_api.contract('studies.admit',1)['sha256'],
                                     study_id=selection['study_id'],body=body))
    require(reservation['request_sha256']==context['request_sha256']==request_sha,'Actual request semantic/context binding differs')
    return reservation


def sdk_observation(completed,token):
    def clean(value,maximum):
        if isinstance(value,bytes):value=value.decode('utf-8',errors='replace')
        return (value or '').replace(token,'[REDACTED]')[:maximum]
    return dict(returncode=getattr(completed,'returncode',None),stdout=clean(getattr(completed,'stdout',None),262144),
                stderr=clean(getattr(completed,'stderr',None),65536),scope='bounded private SDK process observation; not an admission outcome')


def main(args):
    require(not os.path.lexists(args.catalog),'Choose an absent disposable catalog; existing catalogs are never changed')
    require((PACKAGE/'infer.py').is_file() and (PACKAGE/'inference-contract.json').is_file(),
            'Accepted captured inference authority nomination is absent; no catalog/runtime/Model/admission started')
    verify_frozen_sources(PACKAGE)
    require(callable(getattr(recipe_contract,'is_bound_evidence',None)),
            'Accepted schema3/catalog recipe owner is not composed; no catalog/runtime/admission started')
    output=args.output.resolve();output.mkdir(mode=0o700,parents=True,exist_ok=False)
    source=output/'canonical-source-project';source.mkdir();project=output/'project'
    roots={'canonical-fixture':source,'extension-a':project}
    dataset=server=thread=owner=credential=None;sequence=0;endpoint=config=None
    report=dict(state='in_progress',admission_state='not_started',host_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),catalog_path=str(args.catalog.resolve()),
                project_roots={key:str(value) for key,value in roots.items()},physical_acceptance='not_established')
    def save(name,value):
        path=output/name;path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');return path
    def checkpoint():save('progress.json',report)
    def private(name,value):
        path=output/name;fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(value)
        return path
    def start(initial=False):
        nonlocal dataset,server,thread,owner,endpoint
        available_roots={'canonical-fixture':source} if initial else roots
        dataset=Dataset(args.catalog.resolve(),project_roots=available_roots)
        owner=dataset.access.exchange(dataset.access._local_owner_token(require_existing=not initial))
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        endpoint=f'http://127.0.0.1:{server.server_port}'
    def stop():
        nonlocal dataset,server,thread,owner
        if server is not None:server.shutdown();server.server_close();thread.join(timeout=5);server=thread=None
        if dataset is not None:
            if owner is not None:
                with dataset.access.bind(owner['token']):dataset.access.logout()
            dataset.close();dataset=owner=None
    def http(operation,body,*,version=1,path_override=None):
        nonlocal sequence
        if path_override is None:method,path,data=agent_api.project_request(operation,body,version)
        else:method,path,data='POST',path_override,body
        headers={'Authorization':'Bearer '+owner['token'],'Content-Type':'application/json'}
        if operation is not None:headers[agent_api.CONTRACT_HEADER]=agent_api.selected_header(operation,version)
        request=Request(endpoint+path,method=method,data=None if data is None else agent_api.encoded(data),headers=headers)
        try:
            with urlopen(request,timeout=360) as response:status=response.status;value=json.loads(response.read())
        except HTTPError as error:status=error.code;value=json.loads(error.read())
        sequence+=1;save(f'http-{sequence:03d}.json',dict(operation=operation,status=status,result=value))
        require(200<=status<300,f'Owner HTTP {operation or path} refused {status}: '+str(value)[:1200])
        if operation is not None:agent_api.validate_output(operation,dict(status=status,result=value),version)
        return value
    def cli(operation,body):
        nonlocal sequence
        sequence+=1;selection=save(f'call-{sequence:03d}-input.json',body)
        completed=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),
            'call','--operation',operation,'--arguments',str(selection)],capture_output=True,text=True,timeout=360)
        require(credential['token'] not in completed.stdout+completed.stderr,'Credential disclosure')
        require(completed.returncode==0,'Production CLI refused: '+completed.stderr[:1500])
        value=json.loads(completed.stdout);save(f'call-{sequence:03d}-output.json',value);return value
    def configure(name):
        return private(name,json.dumps(dict(endpoint=endpoint,catalog_id=report['catalog_id'],token_file=str(output/'agent-token.private'))))
    try:
        start(initial=True);report['catalog_id']=dataset.db.dataset_id;checkpoint()
        with dataset.access.bind(owner['token']):
            source_result=source_author.build_canonical_fixture(dataset,source)
            save('canonical-source-receipt.json',source_result['receipt'])
            authored=prepare(source_result,project,runtime_sha256=args.expected_runtime_sha256)
            # The accepted owner must validate the complete NEW recipe before any runtime capture.
            definition=recipe_contract.decode_definition((project/'recipe.json').read_bytes())
            require(recipe_contract.is_bound_evidence(definition),'Expected explicit catalog-bound evidence recipe')
            report.update(project_id=authored['project']['id'],recipe_sha256=authored['recipe_sha256'],
                          canonical_release_sha256=authored['canonical']['release']['sha256'],
                          producer_sha256=hashlib.sha256((project/'producer.py').read_bytes()).hexdigest(),
                          oracle_sha256=hashlib.sha256((project/'cold_oracle.py').read_bytes()).hexdigest())
            require(dataset.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0]==0,'Preparation unexpectedly admitted a Run')
        checkpoint();stop();start()
        opened=http(None,dict(root='extension-a',manifest_path='project.json'),path_override='/api/workspace/project-snapshots')
        selected=authored['project']['recipes'][0]
        inspected=http('recipes.inspect',dict(project_id=opened['id'],reference_id=selected['id'],expected_sha256=selected['sha256']),version=2)
        require(set(inspected['extension_binding']['contributions'][i]['kind'] for i in range(len(inspected['extension_binding']['contributions']))) >=
                {'task','model','trainer','evaluator','view'},'Five exact roles missing from actual owner inspection')
        verify_frozen_sources(project)
        with dataset.access.bind(owner['token']):
            snapshots=RuntimeSnapshots(dataset.db,dataset.access,dataset.path)
            runtime_config=json.loads(args.runtime_config.read_bytes());inventory=snapshots.inspect(runtime_config)
            require(inventory['inventory_sha256']==args.expected_runtime_sha256,'Actual CPU runtime differs; no fallback')
            report['runtime']=snapshots.create(runtime_config,args.expected_runtime_sha256,quiesced=True)
            credential=dataset.access.issue(dict(label='Explicit new canonical A SDK qualification',scopes=['inspect','edit','execute','cancel']))
        report['actor_id']=credential['identity']['actor_id'];private('agent-token.private',credential['token']);config=configure('agent-config.private')
        policy=definition['model_evidence'];canonical=policy['canonical']
        inputs=dict(canonical=dict(kind='frozen_release',release_id=canonical['release']['sha256'],expected_sha256=canonical['release']['sha256']),
                    derivation=dict(reference_id='derivation',expected_sha256=canonical['derivation']['sha256']),
                    provenance=dict(reference_id='provenance',expected_sha256=canonical['provenance']['sha256']))
        graph=cli('graphs.create_external',dict(name='Actual canonical catalog A SDK attempt',project_id=opened['id'],recipe_id=selected['id'],
                  expected_sha256=selected['sha256'],inputs=inputs,parameters=dict(learning_rate=0.1,updates=64)))
        specification=copy.deepcopy(policy['model_specification'])
        specification['configuration']=dict(initial_scale=0.125,initial_offset=-0.25)
        verify_frozen_sources(project)
        model=http('models.create',dict(name='Canonical affine scalar A configured initialization',kind='captured_source',
            task=inspected['model_task'],specification=specification,preprocessing_policy=policy['preprocessing_policy'],output_policy=policy['output_policy'],
            source_selector=dict(project_id=opened['id'],recipe_id=selected['id'],expected_sha256=selected['sha256'])))
        published=http('models.publish',dict(model_id=model['id'],revision=model['revision']))
        study=http('studies.create',dict(name='Finite canonical A training and fresh consumer',policy=inspected['selection_policy'],
            limits=dict(attempt_slots=3,admitted_wall_seconds=1200,retained_bytes=300*1024**2,peak_staging_bytes=300*1024**2)))
        trial=cli('studies.prepare_trial',dict(study_id=study['id'],request_key='prepare-'+uuid.uuid4().hex,revision=study['revision'],
            graph_id=graph['id'],graph_revision=graph['revision'],model=published['ref'],replicate=0))
        material=cli('recipes.material',dict(ref=trial['material']));current=cli('studies.get',dict(study_id=study['id']))['study']
        current=http('studies.continue',dict(study_id=study['id'],request_key='continue-'+uuid.uuid4().hex,revision=current['revision'],admission_epoch=current['admission_epoch']))
        grant=http('studies.approve',dict(study_id=study['id'],trial_id=trial['id'],expected_material_sha256=trial['material']['sha256'],consumer_actor_id=report['actor_id']))
        expected=dict(graph_id=graph['id'],graph_revision=graph['revision'],material_sha256=trial['material']['sha256'],model_sha256=published['ref']['sha256'],
            runtime_sha256=material['material']['runtime']['sha256'],task_sha256=published['material']['task']['sha256'],
            profile_definition_sha256=material['material']['evaluation_profile']['sha256'])
        selection=dict(format='extension_sdk_conformance_selection_v1',catalog_id=report['catalog_id'],actor_id=report['actor_id'],project_id=opened['id'],
            study_id=study['id'],trial_id=trial['id'],revision=current['revision'],admission_epoch=current['admission_epoch'],approval_id=grant['id'],
            request_key='canonical-sdk-'+uuid.uuid4().hex,expected=expected)
        selection_path=save('sdk-selection.json',selection)
        report.update(study_id=study['id'],trial_id=trial['id'],model=published['ref'],material=trial['material'],approval_id=grant['id'],
                      request_key=selection['request_key'],configured_model=specification)
        report['admission_state']='may_have_been_sent';checkpoint()
        try:
            completed=subprocess.run([sys.executable,'-m','tuldok_extension_sdk','conformance','--config',str(config),'--cli',str(ROOT/'project_cli.py'),
            '--cli-sha256',hashlib.sha256((ROOT/'project_cli.py').read_bytes()).hexdigest(),'--selection',str(selection_path),
            '--output',str(output/'artifacts'),'--deadline-seconds','360'],cwd=ROOT,capture_output=True,text=True,timeout=420)
        except subprocess.TimeoutExpired as error:
            private('sdk-process-observation.private.json',json.dumps(sdk_observation(error,credential['token'])))
            raise
        private('sdk-process-observation.private.json',json.dumps(sdk_observation(completed,credential['token'])))
        require(credential['token'] not in completed.stdout+completed.stderr,'SDK credential disclosure')
        sdk=json.loads(completed.stdout);save('sdk-result.json',sdk);report['sdk']=sdk
        report['admission_state']='completed' if sdk.get('state')=='passed' else sdk.get('state','unknown')
        if sdk.get('run_id'):report['run_id']=sdk['run_id']
        checkpoint()
        require(completed.returncode==0 and sdk['state']=='passed','SDK refused/unknown; inspect durable selection, never retry admission: '+str(sdk))
        run=cli('runs.get',dict(run_id=sdk['run_id']));save('run.json',run)
        require(run['state']=='completed' and run['custody_phase']=='drained' and len(run['artifacts'])==32,'Actual canonical producer did not publish/drain all32 outputs')
        context_raw=(output/'artifacts/execution-context.json').read_bytes();context_sha=hashlib.sha256(context_raw).hexdigest()
        oracle=subprocess.run([str(args.oracle_python),str(project/'cold_oracle.py'),'--fixture',str(project/'authored-source.json'),
            '--release',str(project/'canonical-release.zip'),'--derivation',str(project/'canonical-derivation.json'),'--provenance',str(project/'canonical-source.json'),
            '--artifacts',str(output/'artifacts'),'--expected-context-sha256',context_sha,'--report',str(output/'oracle.json')],capture_output=True,text=True,timeout=30)
        require(oracle.returncode==0,'Frozen canonical independent consumer refused: '+oracle.stdout[:1500]+oracle.stderr[:1000])
        report['oracle']=json.loads((output/'oracle.json').read_bytes());checkpoint()
        state=cli('studies.reconcile',dict(study_id=study['id']))
        verify_accounting(selection,material,run,evidence.decode(context_raw),state)
        save('study-accounting.json',state)
        public=cli('runs.model_evidence',dict(run_id=run['id']));save('public-evidence.json',public)
        stop();start();config=configure('cold-agent-config.private')
        require(cli('runs.get',dict(run_id=run['id']))==run,'Cold Run differs')
        require(cli('studies.get',dict(study_id=study['id']))==state,'Cold Study/accounting differs')
        require(cli('recipes.material',dict(ref=trial['material']))==material,'Cold full material differs')
        require(cli('models.material',dict(ref=published['ref']))==published,'Cold Model differs')
        require(cli('runs.model_evidence',dict(run_id=run['id']))==public,'Cold common evidence differs')
        cold=output/'cold-artifacts';cold.mkdir()
        for item in run['artifacts']:
            downloaded=subprocess.run([sys.executable,str(ROOT/'project_cli.py'),'--config',str(config),'download','--run-id',run['id'],
                '--name',item['name'],'--expected-sha256',item['sha256'],'--out',str(cold/item['name'])],capture_output=True,text=True,timeout=120)
            require(downloaded.returncode==0 and (cold/item['name']).read_bytes()==(output/'artifacts'/item['name']).read_bytes(),'Cold whole-hash artifact differs')
        with dataset.access.bind(owner['token']):
            report['counts']={table:dataset.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                ('workspace_runs','access_execution_grants','access_execution_consumptions','model_attempt_reservations')}
        require(set(report['counts'].values())=={1},'Canonical SDK workflow duplicated admission/authority/accounting')
        report.update(state='canonical_sdk_source_numerical_cold_passed',remaining=['Actual canonical UI and full fault/retention/package gates remain separate.'])
        save('receipt.json',report);print(report['state'],report['run_id'],output,flush=True)
    except BaseException as error:
        if report['admission_state']=='may_have_been_sent':report.update(state='unknown',admission_state='unknown')
        if report['state']!='unknown':report['state']='failed'
        report.update(failure=str(error));save('failure.json',report);raise
    finally:
        if dataset is not None and credential is not None:
            with dataset.access.bind(owner['token']):dataset.access.revoke(credential['identity']['credential_id'])
        stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-config',type=Path,required=True);parser.add_argument('--oracle-python',type=Path,required=True)
    parser.add_argument('--expected-runtime-sha256',default=RUNTIME_SHA)
    main(parser.parse_args())
