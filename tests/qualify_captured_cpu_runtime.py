"""Actual captured CPU qualification through normal approved production Runs.

No mocks, package installation, runtime copying, historical model loading or
scientific/model acceptance. Requires an existing owner and published snapshot.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
from recipe_process import validate_receipt

PROBE = r'''import hashlib,json,sys,time
from pathlib import Path
import numpy as np
import torch
mode, destination = sys.argv[1:]
out = Path(destination)
torch.set_num_threads(2)
if mode == 'sleep':
    print('cpu_probe_sleep_ready', flush=True)
    time.sleep(120)
    raise RuntimeError('Cancellation qualification was not requested in time')
assert mode == 'compute'
x = torch.arange(12, dtype=torch.float64).reshape(3,4).requires_grad_()
w = torch.arange(8, dtype=torch.float64).reshape(4,2).requires_grad_()
y = x @ w
loss = (y*y).sum()
loss.backward()
expected_y = [[sum(float(i*4+k)*float(k*2+j) for k in range(4)) for j in range(2)] for i in range(3)]
expected_dx = [[sum(2*expected_y[i][j]*float(k*2+j) for j in range(2)) for k in range(4)] for i in range(3)]
expected_dw = [[sum(float(i*4+k)*2*expected_y[i][j] for i in range(3)) for j in range(2)] for k in range(4)]
assert y.tolist() == expected_y and x.grad.tolist() == expected_dx and w.grad.tolist() == expected_dw
assert all(value.device.type == 'cpu' for value in (x,w,y,x.grad,w.grad))
array = np.arange(12, dtype='<f8').reshape(3,4)
assert array.tobytes() == x.detach().numpy().tobytes()
np.save(out/'array.npy', array, allow_pickle=False)
state = {'x':x.detach(),'w':w.detach(),'y':y.detach(),'dx':x.grad,'dw':w.grad}
torch.save(state, out/'checkpoint.pt')
loaded = torch.load(out/'checkpoint.pt', map_location='cpu', weights_only=True)
assert set(loaded) == set(state) and all(torch.equal(loaded[key], value) for key,value in state.items())
runtime_root = Path(np.__file__).parents[2]
for name, module in list(sys.modules.items()):
    location = getattr(module, '__file__', None)
    virtual = {'torch.ops': ('torch._ops','_Ops','_ops.py'), 'torch.classes': ('torch._classes','_Classes','_classes.py')}
    if name in virtual:
        defining_name,class_name,pseudo_file = virtual[name]
        defining = sys.modules[defining_name]
        assert type(module) is vars(defining)[class_name] and location == pseudo_file
        assert type(module).__module__ == defining_name
        location = vars(defining)['__file__']
    if name == '__mp_main__':
        assert Path(location) == Path(__file__).parent.parent/'runtime-bootstrap/recipe_process.py'
        continue
    if location is not None and name != '__main__':
        assert Path(location).is_relative_to(runtime_root), 'Post-compute module outside snapshot: '+name
post_maps = sorted({line.split(maxsplit=5)[5] for line in Path('/proc/self/maps').read_text().splitlines()
    if len(line.split(maxsplit=5))==6 and line.split(maxsplit=5)[5].startswith('/')})
assert all(Path(path).is_relative_to(runtime_root) for path in post_maps)
report = {'scope':'Authored deterministic CPU runtime qualification only; no historical model or scientific acceptance',
    'torch':str(torch.__version__),'numpy':np.__version__,'device':'cpu','threads':torch.get_num_threads(),
    'forward':y.tolist(),'dx':x.grad.tolist(),'dw':w.grad.tolist(),'loss':loss.item(),
    'numpy_payload_sha256':hashlib.sha256(array.tobytes()).hexdigest(),
    'checkpoint_sha256':hashlib.sha256((out/'checkpoint.pt').read_bytes()).hexdigest(),
    'weights_only_reload_exact':True,'post_compute_mappings':post_maps,'post_compute_module_origins_verified':True}
(out/'result.json').write_text(json.dumps(report,sort_keys=True,separators=(',',':')))
print('cpu_probe_compute_complete', flush=True)
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def owner_session(dataset):
    login = dataset.access._local_owner_token(require_existing=True)
    return dataset.access.exchange(login)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2))


def qualify(catalog, snapshot, output):
    output.mkdir(parents=False, exist_ok=False)
    project = output/'project'; project.mkdir()
    source = PROBE.encode(); (project/'probe-λ.py').write_bytes(source)
    definition = {'schema_version':1,'format':'external_recipe_v1','id':'cpu_runtime_probe',
        'name':'Captured CPU runtime qualification','version':1,'runtime':'captured_cpu_python_v1',
        'runtime_snapshot_sha256':snapshot,'sources':[{'path':'probe-λ.py','sha256':sha(source)}],
        'entrypoint':'probe-λ.py','arguments':[{'parameter':'mode'},{'output_dir':True}],
        'parameters':{'mode':{'type':'string','default':'compute','enum':['compute','sleep'],'max_length':16}},
        'inputs':{},'outputs':[{'path':name,'role':role,'max_bytes':limit,'required':True}
            for name,role,limit in [('checkpoint.pt','runtime_checkpoint',1024*1024),
                                    ('array.npy','runtime_numpy',4096),('result.json','runtime_receipt',256*1024)]],
        'environment':{},'resources':{'wall_seconds':240,'max_output_bytes':2*1024*1024}}
    definition_raw=json.dumps(definition).encode();(project/'recipe.json').write_bytes(definition_raw)
    project_id=uuid.uuid4().hex
    manifest={'schema_version':1,'id':project_id,'name':'Authored CPU qualification; no historical model',
        'data':[],'recipes':[{'id':'probe','label':'Deterministic CPU qualification','path':'recipe.json','sha256':sha(definition_raw)}],
        'evidence':[],'requirements':[]}
    write_json(project/'project.json',manifest)
    receipt={'scope':'Production approved Runs with captured CPU snapshot; authored computation, not historical model/science qualification',
        'snapshot_sha256':snapshot,'project_id':project_id,'probe_source_sha256':sha(source),'checks':[],
        'installed_runtime_modified':False,'original_runtime_filesystem_absence_tested':False}
    dataset=None; session=None; active=[]
    def read_run(run_id):
        with dataset.access.bind(session['token']):return dataset.runs.get(run_id)
    def wait(run_id, predicate, timeout=360):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            run=read_run(run_id)
            if predicate(run):return run
            if run['state'] in ('failed','interrupted','unknown','cancelled'):
                raise RuntimeError('Unexpected terminal run: '+json.dumps({key:run.get(key) for key in ('id','state','error','custody_phase')}))
            time.sleep(.1)
        raise RuntimeError('CPU qualification observation deadline expired: '+run_id)
    def create_run(mode):
        with dataset.access.bind(session['token']):
            graph=dataset.pipelines.create_external({'name':'CPU qualification '+mode,'project_id':project_id,
                'recipe_id':'probe','expected_sha256':sha(definition_raw),'inputs':{},'parameters':{'mode':mode}})
            preflight=dataset.pipelines.preflight_external(graph['id'],graph['revision'])
            approval=dataset.runs.approve_external({'graph_id':graph['id'],'graph_revision':graph['revision'],
                'expected_digest':preflight['material_sha256'],'consumer_actor_id':session['identity']['actor_id']})
            run=dataset.runs.submit_external({'request_key':'cpu-qualification-'+uuid.uuid4().hex,
                'graph_id':graph['id'],'graph_revision':graph['revision'],'expected_digest':preflight['material_sha256'],
                'approval_id':approval['id']})
        active.append(run['id']);print('ADMITTED',mode,run['id'],flush=True)
        return run
    def custody(run_id):
        return dataset.runs.path/('.external-'+run_id)/'custody'
    def capture_logs(run):
        directory=custody(run['id']);prefix=output/run['id'];prefix.mkdir()
        raw=(directory/'receipt.json').read_bytes()
        with dataset.access.bind(session['token']), dataset.runs.lock:
            expected=dataset.runs._load(run['id'])['custody_identity']
        verified=validate_receipt(raw,expected)
        for name in ('stdout','stderr'):
            data=(directory/(name+'.log')).read_bytes()
            assert len(data)==verified['streams'][name]['bytes'] and sha(data)==verified['streams'][name]['sha256']
            (prefix/(name+'.log')).write_bytes(data)
        (prefix/'custody-receipt.json').write_bytes(raw)
        write_json(prefix/'run.json',run)
        lines=(prefix/'stdout.log').read_text().splitlines()
        proofs=[json.loads(line)['tuldok_cpu_runtime'] for line in lines if line.startswith('{"tuldok_cpu_runtime":')]
        assert len(proofs)==1 and proofs[0]['snapshot_sha256']==snapshot
        root=Path(run['material']['cpu_snapshot']['root'])
        for path in [*proofs[0]['sys_path'],*proofs[0]['module_paths'].values(),*proofs[0]['mappings']]:
            assert Path(path).is_relative_to(root), 'Observed runtime escaped captured root'
        assert {key:proofs[0]['environment'][key] for key in ('LANG','LC_ALL','PYTHONCOERCECLOCALE','PYTHONUTF8')}=={'LANG':'C','LC_ALL':'C','PYTHONCOERCECLOCALE':'0','PYTHONUTF8':'1'}
        assert set(proofs[0]['virtual_modules'])=={'torch.ops','torch.classes'}
        assert all(Path(item['defining_path']).is_relative_to(root) for item in proofs[0]['virtual_modules'].values())
        assert proofs[0]['packages']=={'numpy':run['material']['cpu_snapshot']['packages']['numpy'],
                                      'torch':run['material']['cpu_snapshot']['packages']['torch']}
        return {'run_id':run['id'],'state':run['state'],'custody_sha256':sha(raw),'runtime':proofs[0]}
    try:
        dataset=Dataset(catalog,project_roots={'qualification':project});session=owner_session(dataset)
        with dataset.access.bind(session['token']):dataset.projects.open({'root':'qualification','manifest_path':'project.json'})
        admitted=create_run('compute');completed=wait(admitted['id'],lambda run:run['state']=='completed')
        assert completed['custody_phase']=='drained' and completed['quality_claim'] is False
        compute=capture_logs(completed);artifacts={}
        with dataset.access.bind(session['token']):
            for item in completed['artifacts']:
                raw,_=dataset.runs.artifact(completed['id'],item['name']);assert sha(raw)==item['sha256']
                artifacts[item['name']]=raw;(output/completed['id']/item['name']).write_bytes(raw)
        report=json.loads(artifacts['result.json']);array=artifacts['array.npy']
        assert array[:8]==b'\x93NUMPY\x01\x00';header_size=struct.unpack('<H',array[8:10])[0]
        header=ast.literal_eval(array[10:10+header_size].decode());assert header=={'descr':'<f8','fortran_order':False,'shape':(3,4)}
        expected=struct.pack('<12d',*range(12));assert array[10+header_size:]==expected
        assert report['numpy_payload_sha256']==sha(expected) and report['checkpoint_sha256']==sha(artifacts['checkpoint.pt'])
        assert report['weights_only_reload_exact'] is True and report['device']=='cpu'
        assert report['post_compute_module_origins_verified'] is True
        assert all(Path(path).is_relative_to(completed['material']['cpu_snapshot']['root']) for path in report['post_compute_mappings'])
        receipt['compute']=compute;receipt['checks'].append('Actual CPU forward/backward, exact NumPy bytes and weights_only tensor checkpoint reload completed behind approved production custody.')
        sleep_run=create_run('sleep')
        def sleep_ready(run):
            path=custody(run['id'])/'stdout.log'
            return path.exists() and b'cpu_probe_sleep_ready\n' in path.read_bytes()
        wait(sleep_run['id'],sleep_ready)
        with dataset.access.bind(session['token']):dataset.runs.cancel(sleep_run['id'])
        cancelled=wait(sleep_run['id'],lambda run:run['state']=='cancelled',timeout=45)
        assert cancelled['custody_phase']=='drained' and not cancelled['artifacts']
        receipt['cancel']=capture_logs(cancelled);receipt['checks'].append('Actual initialized captured CPU child cancelled with confirmed drain and no published artifacts.')
        with dataset.access.bind(session['token']):dataset.access.revoke(session['identity']['credential_id'])
        session=None;dataset.close();dataset=None
        dataset=Dataset(catalog,project_roots={'qualification':project});session=owner_session(dataset)
        with dataset.access.bind(session['token']):
            reopened=dataset.runs.get(completed['id']);assert reopened['state']=='completed'
            for name,raw in artifacts.items():assert dataset.runs.artifact(completed['id'],name)[0]==raw
        receipt['checks'].append('Catalog reopen preserves exact checkpoint, NumPy and result artifact bytes.')
        write_json(output/'receipt.json',receipt);print('PASS captured CPU qualification',output,flush=True)
    except BaseException as error:
        receipt['failure']=str(error)
        if dataset is not None:
            for run_id in active:
                try:
                    directory=custody(run_id)
                    for name in ('stdout.log','stderr.log','receipt.json'):
                        path=directory/name
                        if path.exists():(output/(run_id+'-'+name)).write_bytes(path.read_bytes())
                except OSError:pass
        write_json(output/'failure.json',receipt);raise
    finally:
        if dataset is not None:
            if session is not None:
                with dataset.access.bind(session['token']):dataset.access.revoke(session['identity']['credential_id'])
            dataset.close()
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    qualify(args.catalog.resolve(),args.snapshot,args.output.resolve())
