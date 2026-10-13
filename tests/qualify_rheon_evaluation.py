"""Independent all-frame wire/NPY/NPZ and numerical audit; never evaluates a model."""
import argparse
import base64
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import struct

import numpy as np

FIELDS = (
    ('rhs','<f8',(32,32,32),'cell','preprojection RHS'),
    ('pressure','<f8',(32,32,32),'cell','solved pressure'),
    ('velocity_x','<f4',(32,32,33),'face_x','corrected velocity'),
    ('velocity_y','<f4',(32,33,32),'face_y','corrected velocity'),
    ('velocity_z','<f4',(33,32,32),'face_z','corrected velocity'),
    ('tracer','<f4',(32,32,32),'cell','advected tracer'))


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(raw):return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    h=hashlib.sha256();size=0
    with Path(path).open('rb') as source:
        while raw:=source.read(1024*1024):h.update(raw);size+=len(raw)
    return size,h.hexdigest()


def decode_segment(raw,method,seed,first_frame,count):
    """Decode exact wire independently, including learned pre-report RHS requests."""
    offset=0
    def take(count):
        nonlocal offset
        require(0<=count<=len(raw)-offset,'Truncated native stream')
        value=raw[offset:offset+count];offset+=count;return value
    def message():
        length,=struct.unpack('<I',take(4));require(length<=65536,'Unbounded native message')
        return json.loads(take(length))
    ready=None
    if first_frame==1:
        ready=message()
        require(ready['schema']=='rheon-trajectory-v1' and (ready['n'],ready['method'],ready['seed'])==(32,method,seed),'Wrong native READY')
        require(ready['dt']==1/60 and ready['density']==1.25 and ready['spacing']==[1/32]*3 and ready['face_lengths']==[33792]*3,'Wrong physical READY controls')
    frames=[]
    for index in range(first_frame,first_frame+count):
        extra=take(32768*8) if method=='learned' else None
        report=message();require(report['frame']==index and math.isclose(report['time'],index/60,rel_tol=1e-12,abs_tol=1e-12),'Wrong frame/time sequence')
        arrays={name:np.frombuffer(take(math.prod(shape)*np.dtype(dtype).itemsize),dtype=dtype).reshape(shape) for name,dtype,shape,_,_ in FIELDS}
        require(all(np.isfinite(array).all() for array in arrays.values()),'Nonfinite native array')
        if extra is not None:require(np.isfinite(np.frombuffer(extra,dtype='<f8')).all(),'Nonfinite learned RHS request')
        frames.append((report,arrays,extra))
    require(offset==len(raw),'Trailing/overlapping native bytes')
    return ready,frames


def physics(report,arrays):
    u,v,w=(arrays[name].astype(np.float64) for name in ('velocity_x','velocity_y','velocity_z'))
    divergence=((u[:,:,1:]-u[:,:,:-1])+(v[:,1:,:]-v[:,:-1,:])+(w[1:,:,:]-w[:-1,:,:]))*32
    maximum=float(np.max(np.abs(divergence)))
    require(maximum==report['actual_divergence_max'] and maximum<=1e-5,'Independent MAC divergence differs or fails')
    require(all(np.count_nonzero(side)==0 for side in (u[:,:,0],u[:,:,-1],v[:,0,:],v[:,-1,:],w[0,:,:],w[-1,:,:])),'Nonzero sealed normal velocity')
    tracer=arrays['tracer'].astype(np.float64)
    require(tracer.min()>=0 and tracer.max()<=1,'Tracer bounds fail')
    integral=float(np.sum(tracer)/32**3)
    require(math.isclose(integral,report['tracer_integral'],rel_tol=1e-12,abs_tol=1e-15),'Independent tracer integral differs')
    for key,limit in [('relative_residual',1e-8),('courant',1)]:
        require(type(report[key]) in (int,float) and math.isfinite(report[key]) and 0<=report[key]<=limit,'Reported physics gate fails')
    return maximum


def compare(truth,predicted):
    # Preserve the original arithmetic precision deliberately: denominator norm
    # and tracer subtraction are float32, centered pressure is float64.
    def relative(a,b):return float(np.linalg.norm(a.astype(np.float64)-b)/max(np.linalg.norm(b),1e-30))
    tv=np.concatenate([truth[name].reshape(-1) for name in ('velocity_x','velocity_y','velocity_z')])
    pv=np.concatenate([predicted[name].reshape(-1) for name in ('velocity_x','velocity_y','velocity_z')])
    tp=truth['pressure'].reshape(-1);pp=predicted['pressure'].reshape(-1)
    return {'relative_velocity_l2':relative(pv,tv),'relative_tracer_l2':relative(predicted['tracer'].reshape(-1),truth['tracer'].reshape(-1)),
            'tracer_rmse':float(np.sqrt(np.mean((predicted['tracer'].reshape(-1)-truth['tracer'].reshape(-1))**2))),
            'centered_relative_pressure_l2':relative(pp-pp.mean(),tp-tp.mean())}


def benchmark(result,freeze):
    require(freeze['test_seeds']==[900,901,902,903] and freeze['test_frames']==120 and freeze['benchmark_repetitions']==5,'Frozen evaluation controls changed')
    methods=['jacobi','sgs','learned'];require(freeze['methods']==methods,'Frozen methods changed')
    expected=[]
    for repetition in range(5):
        for index,seed in enumerate(range(900,904)):
            offset=(repetition+index)%3
            expected.extend((repetition,seed,method) for method in methods[offset:]+methods[:offset])
    records=result['benchmark'];require([(row['repetition'],row['seed'],row['method']) for row in records]==expected,'Incomplete or reordered original benchmark')
    for row in records:
        require(row['frames']==120 and len(row['reports'])==120,'Missing benchmark frames')
        require(math.isfinite(row['wall_ms_including_native_startup_teardown']) and row['wall_ms_including_native_startup_teardown']>0,'Invalid wall timing')
        for index,report in enumerate(row['reports'],1):
            require(report['frame']==index and math.isclose(report['time'],index/60,rel_tol=1e-12,abs_tol=1e-12),'Benchmark frame/time drift')
            for key,limit in [('relative_residual',1e-8),('actual_divergence_max',1e-5),('courant',1)]:
                require(type(report[key]) in (int,float) and math.isfinite(report[key]) and 0<=report[key]<=limit,'Benchmark diagnostic fails')
            if row['method']=='learned':require(report['iterations']==0,'Learned benchmark used iterative correction')
    medians={method:statistics.median(row['wall_ms_including_native_startup_teardown'] for row in records if row['method']==method) for method in methods}
    require(medians==result['median_120_frame_wall_ms'],'Incorrect original median arithmetic')
    for method in ('jacobi','sgs'):require(result['speedup_vs_'+method]==medians[method]/medians['learned'],'Incorrect original timing ratio')
    return {'trajectories':60,'frames':7200,'median_120_frame_wall_ms':medians}


def trajectory(directory,method,seed,npz,checks,identity):
    import zipfile
    index=json.loads((directory/f'wire-{method}-{seed}.json').read_text())
    require((index['method'],index['seed'],index['frames'])==(method,seed,120) and len(index['chunks'])==8,'Wrong trajectory index')
    require(index['identity']==identity,'Trajectory identity differs from outer receipt')
    stream_hash=hashlib.sha256();offset=0;ready=None
    family={'namespace':'rheon-trajectory-probe-scene-v1','id':digest(json.dumps({'scene':'rheon-trajectory-probe-source-v1','grid':32,'seed':seed},sort_keys=True,separators=(',',':')).encode())}
    for number,chunk in enumerate(index['chunks']):
        first=number*16+1;count=min(16,121-first);name=f'fields-{method}-{seed}-{number:03d}.zip'
        require(chunk['path']==name and chunk['frame_start']==first and chunk['frame_end']==first+count-1 and chunk['stdout_start']==offset,'Overlapping/missing chunk/frame ranges')
        require(file_digest(directory/name)==(chunk['bytes'],chunk['sha256']),'Chunk index custody mismatch')
        with zipfile.ZipFile(directory/name) as archive:
            manifest=json.loads(archive.read('manifest.json'));trace=json.loads(archive.read('sources/evaluation-trace.json'));wire=archive.read('sources/wire.bin')
            require(manifest['family']==family and len(manifest['frames'])==count,'Wrong protected trajectory family')
            require(manifest['grid']=={'shape_xyz':[32]*3,'origin_xyz':[0,0,0],'spacing_xyz':[1/32]*3,'orientation':[[1,0,0],[0,1,0],[0,0,1]],'units':'native length units (unspecified)'},'Scientific grid drift')
            require('unspecified' in manifest['time_units'],'Invented time units')
            require(trace['identity']==index['identity'] and trace['method']==method and trace['seed']==seed,'Trace identity differs')
            for key in ('frame_start','frame_end','stdout_start','stdout_end','stdout_sha256'):require(trace[key]==chunk[key],'Trace range/hash mismatch')
            require(trace['includes_ready']==(number==0) and trace['learned_rhs_request_before_report']==(method=='learned'),'Wire protocol metadata mismatch')
            require(len(wire)==chunk['stdout_end']-offset and digest(wire)==chunk['stdout_sha256'],'Wire segment identity mismatch')
            for source in manifest['sources']:
                raw=archive.read(source['path']);require(len(raw)==source['bytes'] and digest(raw)==source['sha256'],'Embedded source custody mismatch')
            observed_ready,frames=decode_segment(wire,method,seed,first,count)
            if number==0:ready=observed_ready
            require(trace['ready']==ready,'Repeated READY declarations differ')
            stream_hash.update(wire);offset+=len(wire)
            require(trace['reports']==[frame[0] for frame in frames],'Wire reports differ from trace')
            require(len(manifest['fields'])==6,'Wrong field inventory')
            for fi,(report,arrays,extra_rhs) in enumerate(frames):
                frame=manifest['frames'][fi];require(float(frame['time'])==report['time'] and len(frame['arrays'])==6,'Frame metadata drift')
                for name,dtype,shape,center,stage in FIELDS:
                    field=next(item for item in manifest['fields'] if item['id']==name)
                    require((field['dtype'],field['centering'],field['stage'])==(dtype,center,stage),'Field declaration drift')
                    item=next(item for item in frame['arrays'] if item['field']==name);raw=archive.read(item['path'])
                    require(len(raw)==item['bytes'] and digest(raw)==item['sha256'] and raw[:8]==b'\x93NUMPY\x01\x00','NPY identity/version mismatch')
                    value=np.load(io.BytesIO(raw),allow_pickle=False)
                    require(value.dtype.str==dtype and value.shape==shape and value.flags.c_contiguous,'NPY dtype/order/shape mismatch')
                    require(value.tobytes()==arrays[name].tobytes(),'NPY bytes differ from original native stdout')
                    if name!='rhs':
                        npz_name={'velocity_x':'velocity_0','velocity_y':'velocity_1','velocity_z':'velocity_2'}.get(name,name)
                        original=npz[npz_name][first+fi-1]
                        require(original.dtype==value.dtype and original.tobytes()==value.tobytes(),'Original NPZ and retained complete field differ')
                if extra_rhs is not None:require(extra_rhs==arrays['rhs'].tobytes(),'Learned request RHS differs from accepted-frame RHS')
                maximum=physics(report,arrays)
                if method=='learned':require(report['iterations']==0,'Learned accuracy used iterative correction')
                checks.append({'method':method,'seed':seed,'frame':first+fi,'fields':6,'divergence':maximum,'wire_rhs_request_preserved':extra_rhs is not None})
                yield report,arrays
    require(offset==index['stdout_bytes'] and stream_hash.hexdigest()==index['stdout_sha256'],'Complete disjoint stdout reconstruction fails')


def audit(directory,http_inventory):
    directory=Path(directory);inventory=json.loads(Path(http_inventory).read_text())
    require(len(inventory)==89 and len({item['name'] for item in inventory})==89,'Expected89 distinct HTTP outputs')
    for item in inventory:
        require(Path(item['name']).name==item['name'],'Nonflat artifact')
        require(file_digest(directory/item['name'])==(item['bytes'],item['sha256']),'Owner-local artifact differs from HTTP verified bytes')
    measured={item['name']:item for item in inventory}
    freeze_raw=(directory/'input-freeze.json').read_bytes();freeze=json.loads(freeze_raw)
    result=json.loads((directory/'result.json').read_text())
    require(result['schema']=='rheon-trajectory-result-v1' and result['freeze_sha256']==digest(freeze_raw),'Original result/freeze mismatch')
    require(result['checkpoint_sha256']==freeze['checkpoint_sha256']==measured['input-model.pt']['sha256'],'Original checkpoint identity mismatch')
    for name,expected in result['artifact_sha256'].items():require(measured[name]['sha256']==expected,'Original output hash map differs')
    outer=json.loads((directory/'evaluation-receipt.json').read_text())
    require(outer['schema_version']==1 and outer['evaluation']=='fresh_cpu_autonomous_evaluation','Wrong outer evaluation receipt')
    require(set(outer['outputs'])==set(measured)-{'evaluation-receipt.json'},'Outer output inventory incomplete')
    for name,item in outer['outputs'].items():require(item['sha256']==measured[name]['sha256'] and item['bytes']==measured[name]['bytes'],'Outer output identity mismatch')
    identity=outer['identity'];require(identity['checkpoint_sha256']==result['checkpoint_sha256'] and identity['freeze_sha256']==digest(freeze_raw),'Outer input identities differ')
    for key in ('runtime_snapshot_sha256','binary_sha256','source_sha256'):require(identity[key]==freeze['source'][key],'Captured source/runtime/native identity differs')
    evidence=outer['input_evidence'];require(set(evidence)=={'checkpoint','freeze','training_inputs','training_result','build_receipt'},'Wrong input receipt slots')
    slots={'checkpoint':('input-model.pt','checkpoint'),'freeze':('input-freeze.json','training_freeze'),'training_inputs':('input-training-receipt.json','training_inputs'),'training_result':('input-training-result.json','training_result')}
    for slot,(name,role) in slots.items():
        require(evidence[slot]['kind']=='run_artifact','Evaluation did not directly consume prior Run artifacts')
        source=evidence[slot]['source'];require(source['measured_sha256']==measured[name]['sha256'] and source['artifact_bytes']==measured[name]['bytes'] and source['artifact_role']==role,'Training artifact typed receipt differs')
        require({key:source[key] for key in identity['training_origin']}==identity['training_origin'],'Inputs have different originating training Runs')
        raw=base64.b64decode(source['custody_receipt_base64'],validate=True);require(digest(raw)==source['custody_receipt_sha256'],'Training custody receipt hash mismatch')
        custody=json.loads(raw);require(custody['outcome']=='completed' and custody['drained'] and custody['echild'] and custody['go_received'],'Training custody did not complete')
        require(all(custody[key]==value for key,value in source['custody_identity'].items()),'Original training custody identity mismatch')
    training=json.loads((directory/'input-training-result.json').read_text());inputs=json.loads((directory/'input-training-receipt.json').read_text())
    require(training['checkpoint_sha256']==result['checkpoint_sha256'] and training['freeze_sha256']==digest(freeze_raw) and training['input_receipt_sha256']==measured['input-training-receipt.json']['sha256'],'Prior training payload hashes disagree')
    require(training['releases']==inputs['releases']==freeze['training_releases'] and training['training']==freeze['training'],'Prior immutable training evidence changed')
    launches=outer['native_launches'];require(Counter((item['seed'],item['method']) for item in launches)==Counter({(seed,method):(5 if method=='sgs' else 6) for seed in range(900,904) for method in ('jacobi','sgs','learned')}),'Wrong complete evaluation launch coverage')
    policy=outer['native_policy'];expected_maps={'sealed-native','sealed-loader'}|{item['path'] for item in policy['runtime_files'] if item['path']!=policy['loader']['path']}
    for launch in launches:
        require(set(launch['mappings'])==expected_maps,'Native loaded map closure differs')
        require((launch['ready']['n'],launch['ready']['method'],launch['ready']['seed'])==(32,launch['method'],launch['seed']),'Native READY identity differs')
    benchmark_result=benchmark(result,freeze)
    require([case['seed'] for case in result['accuracy']]==list(range(900,904)),'Missing accuracy trajectory')
    checks=[];maxima=[]
    for seed in range(900,904):
        originals={}
        for method in ('jacobi','learned'):
            with np.load(directory/f'{method}-{seed}.npz',allow_pickle=False) as loaded:
                require(set(loaded.files)=={'pressure','tracer','velocity_0','velocity_1','velocity_2'},'Original NPZ inventory changed')
                originals[method]={name:loaded[name] for name in loaded.files}
            require(all(value.shape[0]==120 for value in originals[method].values()),'NPZ missing frames')
        expected=result['accuracy'][seed-900];require(expected['frames']==120 and len(expected['errors'])==120,'Missing original accuracy errors')
        viewport=json.loads((directory/'viewport.json').read_text()) if seed==900 else None
        if viewport:require(viewport['n']==32 and viewport['seed']==900 and viewport['dt']==1/60 and viewport['accuracy']==expected,'Original viewport identity/accuracy mismatch')
        errors=[];divergences=[]
        teacher=trajectory(directory,'jacobi',seed,originals['jacobi'],checks,identity)
        predicted=trajectory(directory,'learned',seed,originals['learned'],checks,identity)
        for index,((ref,truth),(ai,pred)) in enumerate(zip(teacher,predicted,strict=True)):
            error=compare(truth,pred);errors.append(error);divergences.append(ai['actual_divergence_max'])
            for key,value in error.items():
                require(math.isfinite(value) and math.isclose(value,expected['errors'][index][key],rel_tol=1e-12,abs_tol=1e-15),'Independent all-field error differs: '+key)
            if viewport:
                for label,report,arrays in [('reference',ref,truth),('learned',ai,pred)]:
                    original=viewport[label][index]
                    require(all(original['report'][key]==value for key,value in report.items()),'Viewport report differs from wire')
                    require(np.asarray(original['tracer'],dtype='<f4').tobytes()==arrays['tracer'].tobytes(),'Viewport full tracer differs')
        require(len(errors)==120,'Missing accuracy frames')
        for field in ('relative_velocity_l2','relative_tracer_l2'):
            maximum=max(error[field] for error in errors);require(maximum<1e-5 and math.isclose(maximum,expected['max_'+field],rel_tol=1e-12,abs_tol=1e-15),'Accuracy maximum fails');maxima.append(maximum)
        require(max(divergences)==expected['max_ai_divergence'],'Original maximum learned divergence differs')
        del originals,viewport
    return {'qualification':'Independent all-frame native stdout/NPY/original NPZ/viewport comparison and original numerical arithmetic audit',
            'local_qa_authority':'Owner-local immutable artifact reads independently matched every completed HTTP byte count/SHA; not agent API parity',
            'limitations':['Previously exposed seeds900–903; no new holdout or GPU qualification.','RHS retained exactly but original comparison has no RHS accuracy metric.'],
            'artifacts':89,'http_matched_bytes':sum(item['bytes'] for item in inventory),'accuracy_frames':len(checks),'six_field_arrays':len(checks)*6,
            'complete_wire_trajectories':8,'maximum_relative_velocity_or_tracer_error':max(maxima),'maximum_divergence':max(row['divergence'] for row in checks),
            'benchmark':benchmark_result,'checkpoint_sha256':result['checkpoint_sha256'],'frame_checks':checks}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifacts',required=True);parser.add_argument('--http-inventory',required=True);parser.add_argument('--report')
    args=parser.parse_args();result=audit(args.artifacts,args.http_inventory);raw=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.report:Path(args.report).write_text(raw)
    print(raw,end='')


if __name__=='__main__':main()
