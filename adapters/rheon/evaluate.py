"""Original evaluation numerics with explicit custody and full-field retention hooks."""
import argparse
from contextlib import contextmanager
import hashlib
import io
import math
import os
from pathlib import Path
import shutil
import statistics
import struct
import sys
import tempfile
import zipfile

if __package__:
    from . import cpu_compare, generate, native_transport
else:
    import cpu_compare
    import generate
    import native_transport

SEEDS = (900,901,902,903)
METHODS = ('jacobi','sgs','learned')
CAPTURE_METHODS = ('jacobi','learned')
WIRE_LIMIT = 170*1024*1024
CHUNK_LIMIT = 40*1024*1024
TOTAL_LIMIT = 3500000000
FIELDS = [('rhs','<f8','cell','preprojection RHS'),('pressure','<f8','cell','solved pressure'),
          ('velocity_x','<f4','face_x','corrected velocity'),('velocity_y','<f4','face_y','corrected velocity'),
          ('velocity_z','<f4','face_z','corrected velocity'),('tracer','<f4','cell','advected tracer')]
INPUTS = {'checkpoint':('checkpoint',1024*1024),'freeze':('training_freeze',2*1024*1024),
          'training_inputs':('training_inputs',2*1024*1024),'training_result':('training_result',4*1024*1024)}


def require(condition, message):
    if not condition:raise ValueError(message)


def finite(value, maximum=1e100):
    require(type(value) in (int,float) and 0<=value<=maximum and math.isfinite(value),'Invalid evaluation metric.')
    return value


def encode(value):return generate.encode(value)


def file_hash(path):
    with Path(path).open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()


def progress(stage,completed,total,**metrics):
    print(encode({'format':'tuldok_progress_v1','stage':stage,'completed':completed,'total':total,'metrics':metrics}).decode(),flush=True)


def outputs():
    items=[]
    for method in CAPTURE_METHODS:
        for seed in SEEDS:
            items.append((f'{method}-{seed}.npz','evaluation_arrays',128*1024*1024))
            items.append((f'wire-{method}-{seed}.json','native_wire_index',256*1024))
            items.extend((f'fields-{method}-{seed}-{chunk:03d}.zip','scientific_fields',CHUNK_LIMIT) for chunk in range(8))
    return items+[('viewport.json','evaluation_viewport',320*1024*1024),('result.json','evaluation_result',32*1024*1024),
        ('evaluation-receipt.json','evaluation_receipt',8*1024*1024),('input-model.pt','checkpoint',1024*1024),
        ('input-freeze.json','source_freeze',2*1024*1024),('input-training-receipt.json','training_inputs',2*1024*1024),
        ('input-training-result.json','training_result',4*1024*1024),('input-build-receipt.json','source_build',1024*1024),
        ('result-summary.json','result_summary',65536)]


@contextmanager
def private_workspace(parent):
    # Failed or interrupted attempts keep their own evidence under the existing
    # attempt directory. Only the normal verified-copy path removes duplicates.
    directory=Path(tempfile.mkdtemp(prefix='evaluation-private-',dir=parent))
    try:
        yield directory
    except BaseException:
        raise
    else:
        shutil.rmtree(directory)


class TeeReader:
    """Bound only the observed stdout bytes; process ownership remains with Runs."""
    def __init__(self,source,path):
        self.source=source;self.path=Path(path);self.file=self.path.open('xb');self.count=0
        self.digest=hashlib.sha256();self.closed=False
    def read(self,size=-1):
        require(type(size) is int and 0<=size<=WIRE_LIMIT,'Bounded native read required.')
        raw=self.source.read(size)
        require(self.count+len(raw)<=WIRE_LIMIT,'Native trajectory stdout exceeds bound.')
        self.file.write(raw);self.digest.update(raw);self.count+=len(raw)
        return raw
    def close(self):
        if self.closed:return
        try:
            require(not self.source.read(1), 'Unexpected trailing native stdout.')
            self.file.flush();os.fsync(self.file.fileno())
        finally:
            self.file.close();self.source.close();self.closed=True


def message(handle):
    length,=struct.unpack('<I',native_transport.exact(handle,4))
    require(length<=65536,'Native JSON exceeds bound.')
    value=generate.decode(native_transport.exact(handle,length))
    require(type(value) is dict,'Native message must be an object.')
    return value


def shape(center,n=32):
    result=[n,n,n]
    if center!='cell':result[{'face_x':2,'face_y':1,'face_z':0}[center]]+=1
    return result


def checked_frame(handle,method,index,state,record):
    # Learned native first requests pressure by emitting RHS before its report.
    inference_rhs=native_transport.exact(handle,32**3*8) if method=='learned' else None
    report=message(handle)
    require(report.get('frame')==index and math.isclose(finite(report.get('time')),index/60,rel_tol=1e-12,abs_tol=1e-12),
            'Native capture frame/time differs.')
    require(all(type(v) in (int,float) and abs(v)<=1e12 and math.isfinite(v) for v in report.values()),'Invalid native report.')
    finite(report.get('relative_residual'),1e-8);finite(report.get('actual_divergence_max'),1e-5);finite(report.get('courant'),1)
    require(method!='learned' or report.get('iterations')==0,'Learned trajectory used iterative correction.')
    require(all(record.get(key)==value for key,value in report.items()),'Original report differs from exact wire.')
    arrays=[]
    for name,dtype,center,stage in FIELDS:
        dimensions=shape(center);raw=native_transport.exact(handle,math.prod(dimensions)*(8 if dtype=='<f8' else 4))
        array=state['velocity'][{'velocity_x':0,'velocity_y':1,'velocity_z':2}[name]] if name.startswith('velocity_') else state[name]
        require(array.dtype.str==dtype and array.flags.c_contiguous and array.size==math.prod(dimensions)
                and array.tobytes(order='C')==raw,'Original field differs from native element bytes.')
        import numpy as np
        require(np.isfinite(array).all().item() and (name!='tracer' or ((array>=0)&(array<=1)).all().item()),'Invalid native field values.')
        if name=='rhs' and inference_rhs is not None:require(raw==inference_rhs,'Learned RHS request differs from retained frame RHS.')
        arrays.append({'id':name,'dtype':dtype,'centering':center,'stage':stage,'shape_zyx':dimensions,'raw':raw})
    return report,arrays


def write_chunk(path,method,seed,ready,frames,wire,start,end,identity):
    members={};manifest={'schema_version':1,'format':'scientific_field_sequence_v1',
        'grid':{'shape_xyz':[32]*3,'origin_xyz':[0,0,0],'spacing_xyz':ready['spacing'],
                'orientation':[[1,0,0],[0,1,0],[0,0,1]],'units':'native length units (unspecified)'},
        'fields':[{'id':name,'label':name.replace('_',' '),'dtype':dtype,'centering':center,'stage':stage,
                   'units':'native units (unspecified)'} for name,dtype,center,stage in FIELDS],
        'frames':[],'time_units':'native time units (unspecified)',
        'family':{'namespace':'rheon-trajectory-probe-scene-v1','id':generate.sha(encode({'scene':'rheon-trajectory-probe-source-v1','grid':32,'seed':seed}))},
        'sources':[],'provenance':{'producer':'Optional Rheon autonomous evaluation; '+method,'source_id':''}}
    for report,arrays in frames:
        frame={'time':str(report['time']),'arrays':[]}
        for array in arrays:
            name=f"arrays/{report['frame']:03d}-{array['id']}.npy"
            data=generate.npy(array['raw'],array['dtype'],array['shape_zyx']);members[name]=data
            frame['arrays'].append({'field':array['id'],'path':name,'bytes':len(data),'sha256':generate.sha(data)})
        manifest['frames'].append(frame)
    trace={'schema_version':1,'method':method,'seed':seed,'ready':ready,'frame_start':frames[0][0]['frame'],
           'frame_end':frames[-1][0]['frame'],'stdout_start':start,'stdout_end':end,
           'stdout_sha256':generate.sha(wire),'includes_ready':start==0,'reports':[f[0] for f in frames],
           'learned_rhs_request_before_report':method=='learned','identity':identity}
    trace_raw=encode(trace);manifest['provenance']['source_id']=generate.sha(trace_raw)
    for name,raw in [('sources/wire.bin',wire),('sources/evaluation-trace.json',trace_raw)]:
        members[name]=raw;manifest['sources'].append({'path':name,'bytes':len(raw),'sha256':generate.sha(raw),
            'description':'Exact native stdout segment and evaluation identity; retained source bytes'})
    members['manifest.json']=encode(manifest)
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_STORED) as archive:
        for name,raw in members.items():
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_STORED
            archive.writestr(info,raw)
    with path.open('rb') as handle:os.fsync(handle.fileno())
    require(path.stat().st_size<=CHUNK_LIMIT,'Scientific evaluation chunk exceeds40MiB.')
    # Verify every retained member before the corresponding wire can be removed.
    with zipfile.ZipFile(path) as archive:
        require(set(archive.namelist())==set(members),'Retained chunk inventory changed.')
        for name,raw in members.items():require(archive.read(name)==raw,'Retained chunk bytes differ.')
    return {'path':path.name,'sha256':file_hash(path),'bytes':path.stat().st_size,'frame_start':trace['frame_start'],
            'frame_end':trace['frame_end'],'stdout_start':start,'stdout_end':end,'stdout_sha256':trace['stdout_sha256']}


def retain_trajectory(tee,method,seed,states,reports,output,identity):
    require(tee.closed and len(states)==len(reports)==120,'Incomplete closed accuracy trajectory.')
    require(tee.path.stat().st_size==tee.count and file_hash(tee.path)==tee.digest.hexdigest(),'Captured wire identity differs.')
    chunks=[]
    with tee.path.open('rb') as handle:
        ready=message(handle)
        require(ready.get('schema')=='rheon-trajectory-v1' and ready.get('n')==32 and ready.get('method')==method
                and ready.get('seed')==seed and ready.get('spacing')==[1/32]*3 and ready.get('dt')==1/60
                and ready.get('density')==1.25 and ready.get('face_lengths')==[33792]*3,'Accuracy READY differs.')
        start=0
        for number,first in enumerate(range(0,120,16)):
            frames=[checked_frame(handle,method,i+1,states[i],reports[i]) for i in range(first,min(first+16,120))]
            end=handle.tell();handle.seek(start);raw=native_transport.exact(handle,end-start)
            path=output/f'fields-{method}-{seed}-{number:03d}.zip'
            chunks.append(write_chunk(path,method,seed,ready,frames,raw,start,end,identity));start=end
        require(not handle.read(1) and start==tee.count,'Trailing or unretained native wire.')
    index={'schema_version':1,'method':method,'seed':seed,'stdout_bytes':tee.count,'stdout_sha256':tee.digest.hexdigest(),
           'frames':120,'chunks':chunks,'identity':identity}
    target=output/f'wire-{method}-{seed}.json';target.write_bytes(encode(index))
    with target.open('rb') as handle:os.fsync(handle.fileno())
    require(generate.decode(target.read_bytes())==index,'Retained wire index differs.')
    directory_fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory_fd)
    finally:os.close(directory_fd)
    tee.path.unlink()  # Only this verified task-created redundant tee; all ranges remain in chunks.
    return index


def validate_inputs(raws,evidence,snapshot):
    require(type(evidence) is dict and set(evidence)==set(INPUTS)|{'build_receipt'},'Input evidence slots differ.')
    shared=None
    for name,(role,limit) in INPUTS.items():
        entry=evidence[name]
        require(type(entry) is dict and set(entry)=={'kind','source'} and entry['kind']=='run_artifact','Completed Run artifact required.')
        source=entry['source']
        require(type(source) is dict and type(source.get('schema_version')) is int and source['schema_version']==1 and source.get('artifact_role')==role
                and source.get('artifact_bytes')==len(raws[name])<=limit
                and source.get('measured_sha256')==generate.sha(raws[name]),'Artifact input custody/role differs.')
        origin={key:source.get(key) for key in ('catalog_id','run_id','attempt_id','request_sha256','material_sha256',
                'custody_receipt_sha256','custody_identity','custody_receipt_base64')}
        require(all(value is not None for value in origin.values()),'Incomplete originating Run identity.')
        if shared is None:shared=origin
        require(shared==origin,'Training inputs do not belong to one completed Run.')
    freeze=generate.decode(raws['freeze']);result=generate.decode(raws['training_result']);inputs=generate.decode(raws['training_inputs'])
    require(result.get('status')=='verified' and result.get('freeze_sha256')==generate.sha(raws['freeze'])
            and result.get('checkpoint_sha256')==freeze.get('checkpoint_sha256')==generate.sha(raws['checkpoint'])
            and result.get('input_receipt_sha256')==generate.sha(raws['training_inputs'])
            and result.get('training_data_sha256')==freeze.get('training_data_sha256')
            and result.get('releases')==freeze.get('training_releases')==inputs.get('releases'), 'Training artifact payload hashes disagree.')
    require(freeze.get('schema')=='rheon-trajectory-freeze-v1' and freeze.get('n')==32 and freeze.get('device')=='cpu'
            and freeze.get('test_frames')==120 and freeze.get('test_seeds')==list(SEEDS)
            and freeze.get('benchmark_repetitions')==5 and freeze.get('methods')==list(METHODS)
            and freeze.get('training_frames')==8 and freeze.get('validation_frames')==60,
            'Fresh immutable evaluation configuration differs.')
    require(result.get('source')==freeze.get('source') and result.get('training')==freeze.get('training')
            and result.get('validation')==freeze.get('validation') and result.get('ablation')==freeze.get('ablation')
            == 'untrained_unit_gains_rejected_by_physics_gate','Training result/freeze evidence differs.')
    source=freeze['source']
    require(source.get('source_sha256')==cpu_compare.SOURCES and source.get('binary_sha256')==cpu_compare.BINARY_SHA256
            and source.get('runtime_snapshot_sha256')==snapshot and source.get('device')=='cpu'
            and type(source.get('threads')) is int and 1<=source['threads']<=8
            and source.get('build_receipt_sha256')==generate.sha(raws['build_receipt'])==cpu_compare.BUILD_RECEIPT_SHA256,
            'Training source/runtime/build identity differs.')
    require(inputs.get('shape')==[96,32768] and inputs.get('dtype')=='<f8' and inputs.get('trajectory_order')==list(range(100,112))
            and inputs.get('frame_order')==list(range(1,9)) and len(inputs.get('releases',[]))==6,'Training input evidence incomplete.')
    return freeze,shared


def validate_result(result,freeze,freeze_hash):
    require(result.get('schema')=='rheon-trajectory-result-v1' and result.get('freeze_sha256')==freeze_hash
            and result.get('checkpoint_sha256')==freeze['checkpoint_sha256'],'Original evaluation identity differs.')
    records=result.get('benchmark',[])
    identities=[(r,s,m) for r in range(5) for i,s in enumerate(SEEDS) for m in METHODS[(r+i)%3:]+METHODS[:(r+i)%3]]
    require([(r.get('repetition'),r.get('seed'),r.get('method')) for r in records]==identities,'Benchmark coverage/rotation differs.')
    for record in records:
        require(record.get('frames')==120 and len(record.get('reports',[]))==120,'Incomplete benchmark frames.')
        require(finite(record.get('wall_ms_including_native_startup_teardown'))>0,'Invalid timing.')
        for i,report in enumerate(record['reports'],1):
            require(report.get('frame')==i and math.isclose(finite(report.get('time')),i/60,rel_tol=1e-12,abs_tol=1e-12),'Benchmark frame/time differs.')
            finite(report.get('relative_residual'),1e-8);finite(report.get('actual_divergence_max'),1e-5);finite(report.get('courant'),1)
            require(record['method']!='learned' or report.get('iterations')==0,'Learned benchmark used correction.')
    medians={method:statistics.median(r['wall_ms_including_native_startup_teardown'] for r in records if r['method']==method) for method in METHODS}
    require(result.get('median_120_frame_wall_ms')==medians,'Benchmark medians differ.')
    for method in ('jacobi','sgs'):require(result.get('speedup_vs_'+method)==medians[method]/medians['learned'],'Benchmark ratio differs.')
    accuracy=result.get('accuracy',[])
    require([v.get('seed') for v in accuracy]==list(SEEDS),'Accuracy trajectory coverage differs.')
    for case in accuracy:
        require(case.get('frames')==120 and len(case.get('errors',[]))==120,'Accuracy frames missing.')
        for field in ('relative_velocity_l2','relative_tracer_l2'):
            maximum=max(finite(frame.get(field),1e-5) for frame in case['errors'])
            require(maximum<1e-5 and case.get('max_'+field)==maximum,'Accuracy maximum invalid.')
        for frame in case['errors']:
            finite(frame.get('centered_relative_pressure_l2'));finite(frame.get('tracer_rmse'))
        finite(case.get('max_ai_divergence'),1e-5)
    require(finite(result.get('python_peak_rss_bytes'))<8000000000
            and result.get('gpu_peak_allocated_bytes')==result.get('gpu_peak_reserved_bytes')==0,'Inference memory/device gate failed.')
    finite(result.get('model_warmup_s'))


def run(args):
    root=Path(__file__).resolve().parent;output=Path(args.output)
    require(output.is_dir() and not output.is_symlink() and not any(output.iterdir()),'Empty output directory required.')
    require(generate.HASH.fullmatch(args.runtime_snapshot_sha256),'Runtime snapshot digest required.')
    raws={name:generate.capture(getattr(args,name),limit)[0] for name,(_role,limit) in INPUTS.items()}
    raws['build_receipt']=generate.capture(args.build_receipt,1024*1024)[0]
    evidence=generate.decode(generate.capture(args.input_evidence,1024*1024)[0])
    freeze,origin=validate_inputs(raws,evidence,args.runtime_snapshot_sha256)
    for name,digest in cpu_compare.SOURCES.items():require(generate.sha(generate.capture(root/'lab/scripts'/name,65536)[0])==digest,'Original script changed.')
    binary=root/'lab/target/release/rheon-trajectory-parallel'
    require(generate.sha(generate.capture(binary,8*1024*1024)[0])==cpu_compare.BINARY_SHA256,'Evaluation native changed.')
    os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['RAYON_NUM_THREADS']=str(freeze['source']['threads'])
    sys.path.insert(0,str(root/'lab/scripts'))
    import numpy as np
    import torch
    import trajectory_experiment as exp
    require(torch.__version__==freeze['source']['torch'] and np.__version__==freeze['source']['numpy'],'Frozen framework versions differ.')
    torch.set_num_threads(freeze['source']['threads']);torch.set_num_interop_threads(1)
    checkpoint=torch.load(io.BytesIO(raws['checkpoint']),weights_only=True,map_location='cpu')
    require(checkpoint.get('schema')=='rheon-modal-trajectory-v1' and checkpoint.get('n')==32
            and tuple(checkpoint.get('training_seeds',()))==tuple(range(100,112)),'Fresh checkpoint contract differs.')
    state=checkpoint['state_dict']
    require(set(state)=={'gains','basis'} and tuple(state['gains'].shape)==(32767,) and tuple(state['basis'].shape)==(32,32)
            and all(v.dtype==torch.float64 and torch.isfinite(v).all().item() for v in state.values())
            and (state['gains']>0).all().item(),'Checkpoint state invalid.')
    del checkpoint,state
    identity={'checkpoint_sha256':generate.sha(raws['checkpoint']),'freeze_sha256':generate.sha(raws['freeze']),
              'runtime_snapshot_sha256':args.runtime_snapshot_sha256,'binary_sha256':cpu_compare.BINARY_SHA256,
              'source_sha256':cpu_compare.SOURCES,'training_origin':origin}
    policy=generate.capture(args.native_policy,1024*1024)[0]
    transport=native_transport.Transport(binary,policy,evaluation_mode=True)
    exp.BINARY=binary;exp.subprocess=transport
    exp.provenance=lambda:dict(freeze['source'])  # All returned identity components checked above against captured bytes/runtime.
    original_compare=exp.compare;original_rollout=exp.rollout;indices=[];timed=0
    with private_workspace(output.parent) as directory:
        private=Path(directory);run_dir=private/'run';run_dir.mkdir();wire_dir=private/'wire';wire_dir.mkdir()
        (run_dir/'model.pt').write_bytes(raws['checkpoint']);(run_dir/'freeze.json').write_bytes(raws['freeze'])
        def compare(n,seed,frames,model):
            require(n==32 and seed in SEEDS and frames==120,'Unadmitted accuracy controls.')
            tees={}
            def capture(argv,source):
                method=argv[2]
                require(method in CAPTURE_METHODS and int(argv[3])==seed and method not in tees,'Unexpected accuracy launch.')
                tee=TeeReader(source,wire_dir/f'{method}-{seed}.bin');tees[method]=tee;return tee
            transport.capture_hook=capture
            try:returned=original_compare(n,seed,frames,model)
            finally:transport.capture_hook=None
            result,ref,predicted,teacher,learned=returned
            require(set(tees)==set(CAPTURE_METHODS),'Missing captured accuracy process.')
            for method,states,reports in [('jacobi',teacher,ref['reports']),('learned',learned,predicted['reports'])]:
                indices.append(retain_trajectory(tees[method],method,seed,states,reports,output,identity))
            require(result.get('max_ai_divergence')==max(r['actual_divergence_max'] for r in predicted['reports']),
                    'Accuracy divergence maximum differs.')
            progress('accuracy',len(indices)//2,4,max_relative_velocity_l2=result['max_relative_velocity_l2'],
                     max_relative_tracer_l2=result['max_relative_tracer_l2'])
            return returned
        def rollout(n,method,seed,frames,model=None,capture=False):
            nonlocal timed
            returned=original_rollout(n,method,seed,frames,model,capture=capture)
            if not capture:
                timed+=1;progress('benchmark',timed,60)
            return returned
        exp.compare=compare;exp.rollout=rollout
        progress('accuracy',0,4)
        from types import SimpleNamespace
        exp.evaluate(SimpleNamespace(output=run_dir))
        source=run_dir/'evaluation'
        result_raw=generate.capture(source/'result.json',32*1024*1024)[0];result=generate.decode(result_raw)
        validate_result(result,freeze,generate.sha(raws['freeze']))
        require(len(transport.evidence)==68 and timed==60 and len(indices)==8,'Incomplete native execution inventory.')
        original_names={f'{m}-{s}.npz' for m in CAPTURE_METHODS for s in SEEDS}|{'viewport.json'}
        require(set(result.get('artifact_sha256',{}))==original_names,'Original evaluation artifact inventory differs.')
        for name in original_names:require(file_hash(source/name)==result['artifact_sha256'][name],'Original evaluation output hash differs.')
        progress('publishing',0,1)
        for name in original_names|{'result.json'}:
            with (source/name).open('rb') as read,(output/name).open('xb') as write:
                shutil.copyfileobj(read,write,1024*1024);write.flush();os.fsync(write.fileno())
            require(file_hash(source/name)==file_hash(output/name),'Evaluation output copy differs.')
    retained={'input-model.pt':raws['checkpoint'],'input-freeze.json':raws['freeze'],
              'input-training-receipt.json':raws['training_inputs'],'input-training-result.json':raws['training_result'],
              'input-build-receipt.json':raws['build_receipt']}
    for name,raw in retained.items():
        with (output/name).open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
    summary={'format':'tuldok_result_summary_v1','title':'Autonomous CPU evaluation',
             'metrics':[{'name':'Timed frames','value':7200,'unit':'frames'},
                        {'name':'Accuracy frames','value':960,'unit':'frames'},
                        {'name':'Speedup vs Jacobi','value':result['speedup_vs_jacobi'],'unit':'ratio'},
                        {'name':'Maximum velocity relative L2','value':max(v['max_relative_velocity_l2'] for v in result['accuracy']),'unit':''}],
             'scope':['Fresh CPU checkpoint; previously exposed seeds900..903.','Five repetitions; original numerical algorithms.',
                      'All six fields and exact accuracy stdout retained.','Evaluated input checkpoint; no retraining or GPU acceptance.'],
             'checkpoint':'input-model.pt'}
    (output/'result-summary.json').write_bytes(encode(summary))
    inventory={name:{'bytes':(output/name).stat().st_size,'sha256':file_hash(output/name),'role':role}
               for name,role,_cap in outputs() if name!='evaluation-receipt.json'}
    receipt={'schema_version':1,'evaluation':'fresh_cpu_autonomous_evaluation','identity':identity,'input_evidence':evidence,
             'native_policy':generate.decode(policy),'native_launches':transport.evidence,'outputs':inventory,
             'limitations':['Previously exposed seeds; no independent holdout or GPU claim.',
                            'Explicit provenance, transport and retention hooks around original numerical evaluate.',
                            'Wire evidence is native stdout; pressure input bytes are not retained.']}
    (output/'evaluation-receipt.json').write_bytes(encode(receipt))
    total=0
    for name,_role,cap in outputs():
        size=(output/name).stat().st_size;require(size<=cap,'Declared evaluation file limit exceeded.');total+=size
    require(total<=TOTAL_LIMIT,'Aggregate evaluation output bound exceeded.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('checkpoint','freeze','training-inputs','training-result','build-receipt','input-evidence',
                 'native-policy','runtime-snapshot-sha256','output'):parser.add_argument('--'+name,required=True)
    run(parser.parse_args())


if __name__=='__main__':main()
