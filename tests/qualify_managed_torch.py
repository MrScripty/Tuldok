"""Bounded real managed CUDA/CPU qualification on an explicit disposable catalog.

The pipeline uses the captured pressure trainer, its train-only packet and fresh
Run-artifact CPU restore. Small separate fixtures qualify lifecycle only. No
fixture performs an optimizer update or claims pressure-model accuracy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import recipe_process
import torch_runtime
from app import Dataset
from auth_helpers import ExplicitOwnerFixture
from torch_runtimes import TorchRuntimes
from workbench import WorkbenchError


TERMINAL = {'completed', 'cancelled', 'failed', 'interrupted', 'unknown'}
FIXTURE = '''import json,sys,time
import torch
mode=sys.argv[1]
assert torch.cuda.is_initialized()
network=torch.nn.Linear(4,4,device='cuda',dtype=torch.float32)
optimizer=torch.optim.Adam(network.parameters()) if mode=='cancel' else None
torch.cuda.synchronize()
print(json.dumps({'qualification_barrier':mode,'device':str(next(network.parameters()).device),
 'dtype':str(next(network.parameters()).dtype),'cuda_initialized':torch.cuda.is_initialized(),
 'optimizer_entered':optimizer is not None,'optimizer_updates':0}),flush=True)
if mode=='startup_failure':raise RuntimeError('Declared qualification entrypoint failure')
time.sleep(120)
raise AssertionError('Bounded fixture must cease before completing')
'''


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n')


def fixture_environment(directory):
    """Obtain the explicitly selected private fixture DSN without disclosing it."""
    helper=Path(__file__).resolve().parents[1]/'scripts/local_postgres.py'
    raw=subprocess.check_output([sys.executable,str(helper),'env','--directory',str(directory)],text=True)
    for line in raw.splitlines():
        words=shlex.split(line)
        require(len(words)==2 and words[0]=='export','Unexpected fixture environment response')
        name,value=words[1].split('=',1)
        require(name=='TULDOK_DATABASE_URL','Unexpected fixture environment key')
        os.environ[name]=value


def check_project(args):
    """Validate the planned captured pipeline without a catalog or model import."""
    import projects
    import recipe_contract
    runtime=torch_runtime.load(args.runtime_manifest)
    identity=sha(torch_runtime.encoded(runtime))
    root=args.project_root.resolve()
    raw=(root/args.project_manifest).read_bytes()
    manifest=projects.manifest(json.loads(raw))
    recipes={}
    for mode in ('train','restore'):
        reference=next(row for row in manifest['recipes'] if row['id']==mode)
        definition=recipe_contract.decode_definition((root/reference['path']).read_bytes())
        require(definition['runtime']==torch_runtime.PROFILE
                and definition['runtime_snapshot_sha256']==identity
                and definition['runtime_device']==('cuda' if mode=='train' else 'cpu'),
                'Planned recipe must select the current exact runtime/device')
        sources={}
        for row in definition['sources']:
            path=root/row['path'];contents=path.read_bytes()
            require(sha(contents)==row['sha256'],'Planned captured source changed')
            sources[row['path']]={'bytes':len(contents),'sha256':sha(contents)}
        require(sum(row['bytes'] for row in sources.values())<=recipe_contract.MAX_SOURCE_BYTES,
                'Planned source closure exceeds the capture budget')
        recipes[mode]={'recipe_sha256':sha((root/reference['path']).read_bytes()),
            'entrypoint':definition['entrypoint'],'source_bytes':sum(row['bytes'] for row in sources.values()),
            'sources':sources,'inputs':definition['inputs'],'outputs':definition['outputs']}
    data={row['id']:row for row in manifest['data']}
    for name in recipes['train']['inputs']:
        entry=data[name];contents=(root/entry['path']).read_bytes()
        require(sha(contents)==entry['sha256'],'Planned training input changed')
    result={'kind':'managed-torch-qualification-preparation','execution_performed':False,
        'optimizer_updates':0,'catalog_opened':False,'runtime_manifest_sha256':identity,
        'project_manifest_sha256':sha(raw),'recipes':recipes}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    save(args.output,result)
    print(json.dumps({'status':'prepared','execution_performed':False,'receipt':str(args.output)}),flush=True)


class Qualification:
    def __init__(self,args):
        self.args=args
        self.output=args.output.resolve()
        self.output.mkdir(mode=0o700,parents=True,exist_ok=False)
        self.receipt={'schema_version':1,'kind':'managed-torch-runtime-qualification',
            'command':[sys.executable,*sys.argv], 'driver_sha256':sha(Path(__file__).read_bytes()), 'source_root':str(Path(__file__).resolve().parents[1]),
            'catalog_path':str(self.output/'catalog'),'production_accessed':False,
            'status':'running','optimizer_update_budget':{'success':1,'lifecycle':0},
            'budgets':{'ready_seconds':recipe_process.TORCH_READY_SECONDS,
                'hash_seconds':recipe_process.TORCH_VERIFY_SECONDS,
                'child_seconds':600,'deadline_fixture_child_seconds':30,
                'sigterm_grace_seconds':recipe_process.GRACE_SECONDS,
                'drain_seconds':recipe_process.CLEANUP_SECONDS,'stream_bytes_each':recipe_process.STREAM_LIMIT,
                'output_bytes':recipe_process.OUTPUT_LIMIT,'capture_bytes':320*1024**2,
                'input_total_bytes':256*1024**2,'per_input_bytes':40*1024**2,'controller_poll_seconds':.03},
            'cases':{},'limitations':['Lifecycle fixtures establish custody, not pressure-model accuracy.']}
        self.started=time.monotonic()
        self.dataset=None
        self.persist()
        self.manifest=torch_runtime.load(args.runtime_manifest)
        self.identity=sha(torch_runtime.encoded(self.manifest))
        self.receipt['runtime']={'profile':torch_runtime.PROFILE,'manifest_sha256':self.identity,
            'manifest_bytes':len(torch_runtime.encoded(self.manifest)),
            'file_count':len(self.manifest['files']),'total_bytes':self.manifest['total_bytes'],
            'python':self.manifest['python'],'packages':self.manifest['packages']}
        self.fixture_path=self.output/'lifecycle-project'
        self.build_fixtures()
        self.roots={'lifecycle':self.fixture_path}
        if args.project_root:
            self.roots['pressure']=args.project_root.resolve()
        self.open()
        start=time.monotonic()
        with self.owner.bound(self.dataset):
            descriptor=TorchRuntimes(self.dataset.db,self.dataset.access,self.dataset.db.path).create(self.manifest,self.identity)
            self.dataset.projects.register_snapshot({'root':'lifecycle','manifest_path':'project.json'})
        self.receipt['runtime_registration']={'elapsed_seconds':time.monotonic()-start,'descriptor':descriptor,
            'full_installed_inventory_verified_before_cuda':True}
        self.persist()

    def open(self):
        self.dataset=Dataset(self.output/'catalog',project_roots=self.roots)
        self.owner=ExplicitOwnerFixture.bootstrap(self.dataset)
        self.receipt['catalog_id']=self.dataset.db.dataset_id

    def persist(self):
        self.receipt['elapsed_seconds']=round(time.monotonic()-self.started,3)
        save(self.output/'qualification.json',self.receipt)

    def build_fixtures(self):
        self.fixture_path.mkdir()
        source=FIXTURE.encode();(self.fixture_path/'fixture.py').write_bytes(source)
        recipes=[]
        for mode in ('hash_cancel','cancel','deadline','startup_failure','shutdown'):
            definition={'schema_version':1,'format':'external_recipe_v1','id':mode,'name':'Managed lifecycle '+mode,
                'version':1,'runtime':torch_runtime.PROFILE,'runtime_device':'cuda',
                'runtime_snapshot_sha256':self.identity,'sources':[{'path':'fixture.py','sha256':sha(source)}],
                'entrypoint':'fixture.py','arguments':[{'literal':mode}], 'parameters':{},'inputs':{},
                'outputs':[{'path':'never-success.json','role':'result','max_bytes':4096,'required':True}],
                'environment':{},'resources':{'wall_seconds':30 if mode=='deadline' else 600,'max_output_bytes':8192}}
            raw=torch_runtime.encoded(definition);(self.fixture_path/(mode+'.json')).write_bytes(raw)
            recipes.append({'id':mode,'label':mode,'path':mode+'.json','sha256':sha(raw)})
        self.fixture_manifest={'schema_version':2,'extensions':[],'id':uuid.uuid4().hex,'name':'Migration GPU lifecycle fixtures',
            'data':[],'recipes':recipes,'evidence':[],'requirements':[]}
        save(self.fixture_path/'project.json',self.fixture_manifest)

    def submit(self,manifest,root,recipe_id,bindings=None):
        print(json.dumps({'case':recipe_id,'stage':'preflight'}),flush=True)
        reference=next(item for item in manifest['recipes'] if item['id']==recipe_id)
        raw=(root/reference['path']).read_bytes();definition=json.loads(raw)
        require(definition['runtime']==torch_runtime.PROFILE and definition['runtime_snapshot_sha256']==self.identity,
                'Recipe must select the exact verified current managed runtime')
        data={item['id']:item for item in manifest['data']}
        inputs={}
        for name in definition['inputs']:
            if bindings and name in bindings:
                inputs[name]=bindings[name]
            else:
                item=data[name];contents=(root/item['path']).read_bytes()
                require(item.get('sha256',sha(contents))==sha(contents),'Project input identity differs')
                inputs[name]={'reference_id':name,'expected_sha256':sha(contents)}
        with self.owner.bound(self.dataset):
            graph=self.dataset.pipelines.create_external({'name':'Q3 '+recipe_id,'project_id':manifest['id'],
                'recipe_id':recipe_id,'expected_sha256':sha(raw),'inputs':inputs})
            preflight=self.dataset.pipelines.preflight_external(graph['id'],graph['revision'])
            approval=self.dataset.runs.approve_external({'graph_id':graph['id'],'graph_revision':graph['revision'],
                'expected_digest':preflight['material_sha256'],
                'consumer_actor_id':self.dataset.access.identity()['actor_id']})
            body={'request_key':'managed-q3-'+uuid.uuid4().hex,'graph_id':graph['id'],'graph_revision':graph['revision'],
                'expected_digest':preflight['material_sha256'],'approval_id':approval['id']}
            # Nested admission callbacks dispatch only after this outer commit.
            # Retain the exact budget/material/grant binding before that wake.
            with self.dataset.lock,self.dataset.db.transaction():
                run=self.dataset.runs.submit_external(body)
                self.receipt['cases'].setdefault(recipe_id,{})['prospective_admission']={
                    'run_id':run['id'],'material_sha256':preflight['material_sha256'],
                    'approval_id':approval['id'],'runtime_manifest_sha256':self.identity,
                    'custody_budgets':dict(self.receipt['budgets'],child_seconds=definition['resources']['wall_seconds']),
                    'recorded_before_dispatch_commit':True,
                    'host_files':preflight['material']['host_files']}
                self.persist()
        return run,body,definition

    def inspect(self,run_id):
        with self.owner.bound(self.dataset):
            return self.dataset.runs.get(run_id)

    def wait(self,run_id,predicate=None,timeout=750):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            run=self.inspect(run_id)
            if predicate is None and run['state'] in TERMINAL:return run
            if predicate is not None and predicate(run):return run
            if predicate is not None and run['state'] in TERMINAL:
                raise ValueError('Run terminated before required barrier: '+json.dumps(run['error']))
            time.sleep(.03)
        raise TimeoutError('Qualification Run exceeded declared observation budget: '+run_id)

    def barrier(self,run_id,mode):
        def observed(run):
            with self.owner.bound(self.dataset):
                progress=self.dataset.runs.external_progress(run_id)
            stream=progress['streams'].get('stdout')
            if stream:
                for line in stream['text'].splitlines():
                    try:value=json.loads(line)
                    except ValueError:continue
                    if value.get('qualification_barrier')==mode:
                        require(value['cuda_initialized'] and value['device']=='cuda:0'
                            and value['dtype']=='torch.float32' and value['optimizer_updates']==0,'Actual CUDA barrier differs')
                        self.receipt['cases'][mode]['barrier']=value
                        self.persist()
                        return True
            return False
        return self.wait(run_id,observed,timeout=160)

    def record(self,name,run,started):
        with self.owner.bound(self.dataset):
            progress=self.dataset.runs.external_progress(run['id'])
            with self.dataset.lock:private=self.dataset.runs._load(run['id'])
        custody=self.dataset.runs.path/('.external-'+run['id'])/'custody'
        raw=(custody/'receipt.json').read_bytes()
        receipt=recipe_process.validate_receipt(raw,private['custody_identity'])
        require(receipt['drained'] and run['custody_phase']=='drained','Required descendant drainage missing')
        self.receipt['cases'][name].update({'run_id':run['id'],'state':run['state'],'custody_phase':run['custody_phase'],
            'material_sha256':run['material_sha256'],'approval_id':run['approval_id'],
            'request_sha256':private['request_sha256'],'custody_identity':private['custody_identity'],
            'custody_receipt_sha256':sha(raw),'custody_receipt':receipt,
            'artifacts':[{k:item[k] for k in ('name','sha256','bytes')} for item in run['artifacts']],
            'elapsed_seconds':round(time.monotonic()-started,3),
            'diagnostic_evidence':progress['evidence'],'error':run['error']})
        self.persist()
        return receipt

    def lifecycle(self):
        for mode in ('hash_cancel','cancel','deadline','startup_failure','shutdown'):
            started=time.monotonic();self.receipt['cases'][mode]={}
            run,body,_definition=self.submit(self.fixture_manifest,self.fixture_path,mode)
            self.receipt['cases'][mode]['run_id']=run['id'];self.persist()
            if mode=='hash_cancel':
                self.wait(run['id'],lambda value:value['progress']['stage']=='verify_runtime',timeout=100)
                with self.owner.bound(self.dataset):self.dataset.runs.cancel(run['id'])
            elif mode in ('cancel','deadline','shutdown'):
                self.barrier(run['id'],mode)
                if mode=='cancel':
                    with self.owner.bound(self.dataset):self.dataset.runs.cancel(run['id'])
                elif mode=='shutdown':
                    original={'id':run['id'],'material_sha256':run['material_sha256'],'approval_id':run['approval_id']}
                    self.dataset.close();self.dataset=None
                    self.open()
                    with self.owner.bound(self.dataset):reconciled=self.dataset.runs.submit_external(body)
                    require(all(reconciled[key]==value for key,value in original.items()),'Cold reopen duplicated admission')
                    self.receipt['cases'][mode]['cold_reconciled_same_run']=True
            terminal=self.wait(run['id'])
            receipt=self.record(mode,terminal,started)
            require(terminal['state']!= 'completed' and not terminal['artifacts'],'Failure fixture published success')
            if mode in ('hash_cancel','cancel','shutdown'):
                require(terminal['state']=='cancelled','Expected cancellation')
            if mode=='hash_cancel':require(receipt['go_received'] is True and receipt['leader_returncode'] is None,
                'Hash cancellation must retain received GO and zero model entry')
            if mode=='deadline':require(receipt['outcome']=='failed' and receipt['reason']=='wall_timeout','Deadline fixture did not expire under CUDA barrier')
            if mode=='startup_failure':require(receipt['leader_returncode']!=0,'Entrypoint exception did not fail')
            print(json.dumps({'case':mode,'state':terminal['state'],'elapsed_seconds':time.monotonic()-started}),flush=True)

    def pipeline(self):
        root=self.args.project_root.resolve();manifest=json.loads((root/self.args.project_manifest).read_bytes())
        with self.owner.bound(self.dataset):
            require(manifest['schema_version']==2,'Pressure qualification requires the current Project v2 snapshot')
            self.dataset.projects.register_snapshot({'root':'pressure','manifest_path':self.args.project_manifest})
        final=None
        for mode in ('train','restore'):
            started=time.monotonic();self.receipt['cases'][mode]={}
            bindings={}
            if final is not None:
                for item in final['artifacts']:
                    name='trained_'+item['name'].replace('-','_').replace('.','_')
                    bindings[name]={'kind':'run_artifact','run_id':final['id'],
                        'artifact_name':item['name'],'expected_sha256':item['sha256']}
            run,body,definition=self.submit(manifest,root,mode,bindings)
            self.receipt['cases'][mode]['run_id']=run['id'];self.persist()
            require(definition['runtime_device']==('cuda' if mode=='train' else 'cpu'),'Pipeline explicit device differs')
            terminal=self.wait(run['id']);self.record(mode,terminal,started)
            if terminal['state']!='completed':
                self.receipt['cases'][mode]['optimizer_updates']='unknown; retained partial evidence requires inspection before retry'
                self.persist()
            require(terminal['state']=='completed','Pressure pipeline Run failed; inspect retained custody logs')
            with self.owner.bound(self.dataset):raw,_media=self.dataset.runs.artifact(run['id'],'receipt.json')
            evidence=json.loads(raw);save(self.output/(mode+'-receipt.json'),evidence)
            self.receipt['cases'][mode]['optimizer_updates']=evidence['optimizer_updates']
            require(evidence['optimizer_updates']==(1 if mode=='train' else 0),'Optimizer budget differs')
            require(evidence.get('heldout_evaluations')==0 and evidence.get('diagnostic_population')=='train_only',
                    'Execution qualification must consume training diagnostics only')
            if mode=='train':
                require(evidence['execution']['parameters_gradients_adam_moments_cuda']
                        and evidence['execution']['model_dtype']=='float32','Actual float32 CUDA update evidence missing')
                require(all(case['split']=='train' for case in evidence['cases']),'Qualification consumed heldout cases')
                weights={item['name']:item['sha256'] for item in terminal['artifacts']}
                require(weights['weights.npz']==weights['checkpoint-001.npz']
                        and weights['weights.npz']!=weights['checkpoint-000.npz'],
                        'One optimizer update must change the initial checkpoint')
                final=terminal
            else:
                require(evidence['execution']['device']=='cpu' and evidence['execution']['cuda_initialized'] is False,
                        'Fresh CPU restore initialized CUDA')
                prior={item['name']:item['sha256'] for item in final['artifacts']}
                parity={item['name']:item['sha256']==prior[item['name']] for item in terminal['artifacts']
                    if item['name']=='weights.npz' or item['name'].startswith('checkpoint-')}
                require(parity and all(parity.values()),'Restored weight artifact hashes differ')
                self.receipt['weight_artifact_hash_parity']=parity
            print(json.dumps({'case':mode,'state':terminal['state'],'elapsed_seconds':time.monotonic()-started}),flush=True)

    def close(self):
        if self.dataset is not None:
            self.dataset.close();self.dataset=None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-manifest',type=Path,required=True)
    parser.add_argument('--fixture-directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--project-root',type=Path)
    parser.add_argument('--project-manifest',default='project.json')
    parser.add_argument('--lifecycle',action='store_true')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    require(args.lifecycle or args.project_root,'Select lifecycle fixtures or the actual pressure project')
    if args.check_only:
        require(args.project_root is not None,'Preparation requires the pressure project')
        check_project(args)
        return
    fixture_environment(args.fixture_directory)
    qualification=Qualification(args)
    try:
        if args.project_root:qualification.pipeline()
        if args.lifecycle:qualification.lifecycle()
        qualification.receipt['status']='passed'
        qualification.receipt['observed_optimizer_updates']={
            'pipeline':sum(qualification.receipt['cases'].get(mode,{}).get('optimizer_updates',0) for mode in ('train','restore')),
            'lifecycle':0}
    except BaseException as error:
        qualification.receipt.update(status='failed',failure={'type':type(error).__name__,'message':str(error)})
        raise
    finally:
        qualification.close();qualification.persist()
    print(json.dumps({'status':'passed','receipt':str(qualification.output/'qualification.json')}),flush=True)


if __name__=='__main__':main()
