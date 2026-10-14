"""Fresh CPU fit from frozen reviewed fields; original numerical code is unchanged."""
import argparse
import io
import json
import math
import os
from pathlib import Path
import resource
import re
import sys
import time
import zipfile

if __package__:
    from . import cpu_compare, generate, native_transport
else:
    import cpu_compare
    import generate
    import native_transport

SERIAL_BUILD_SHA256 = '332aa36d8ce02585be77fbd74f8a7dfcfe9a297a3054b5bb67461ee3556d1e40'
RELEASE_NAMES = tuple('training_'+str(i) for i in range(1, 7))
OUTPUTS = [('training.npz','training_arrays',52*1024*1024), ('model.pt','checkpoint',1024*1024),
           ('freeze.json','training_freeze',2*1024*1024), ('result.json','training_result',4*1024*1024),
           ('input-receipt.json','training_inputs',2*1024*1024), ('result-summary.json','result_summary',65536)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def progress(stage, completed, total, **metrics):
    print(generate.encode({'format':'tuldok_progress_v1','stage':stage,'completed':completed,
                           'total':total,'metrics':metrics}).decode(), flush=True)


def finite(value, maximum=1e100, positive=False):
    require(type(value) in (int,float) and 0 <= value <= maximum and math.isfinite(value)
            and (not positive or value > 0), 'Invalid scientific metric.')
    return value


def validate_policy_evidence(policy, mappings):
    require(type(policy.get('schema_version')) is int and policy['schema_version'] == 1,
            'Producer policy version must be integer1.')
    generate.closed(policy['source'], ('path','sha256'))
    require(type(policy['source']['path']) is str and policy['source']['path'] == 'rheon-trajectory-probe',
            'Producer source path differs.')
    generate.closed(policy['loader'], ('path','bytes','sha256'))
    files = policy['runtime_files']
    require(type(files) is list and len(files) == 4, 'Incomplete producer native closure.')
    expected = {generate.LIBRARY_DIRECTORY+'/'+name for name in ('libgcc_s.so.1','libm.so.6','libc.so.6','ld-linux-x86-64.so.2')}
    observed = set()
    for item in files:
        generate.closed(item, ('path','bytes','sha256'))
        require(type(item['path']) is str and item['path'] in expected and item['path'] not in observed
                and type(item['bytes']) is int and 0 < item['bytes'] <= 8*1024*1024
                and type(item['sha256']) is str and generate.HASH.fullmatch(item['sha256']),
                'Invalid frozen native dependency identity.')
        observed.add(item['path'])
    require(observed == expected and policy['loader']['path'] == generate.LIBRARY_DIRECTORY+'/ld-linux-x86-64.so.2'
            and policy['loader'] in files, 'Frozen loader is outside declared closure.')
    expected_maps = {'sealed-native','sealed-loader'} | (expected-{policy['loader']['path']})
    require(type(mappings) is dict and set(mappings) == expected_maps, 'Producer mapping set differs.')
    for item in mappings.values():
        generate.closed(item, ('device','inode'))
        require(type(item['inode']) is int and item['inode'] > 0
                and type(item['device']) is str and re.fullmatch(r'[0-9a-f]+:[0-9a-f]+',item['device']),
                'Producer mapped file identity is invalid.')


def validate_memory(memory):
    finite(memory.get('python_peak_rss_bytes'))
    require(memory['python_peak_rss_bytes'] < 20000000000
            and memory.get('gpu_peak_allocated_bytes') == 0 and memory.get('gpu_peak_reserved_bytes') == 0,
            'CPU training exceeded original memory/device limits.')


def validate_asset(raw):
    """Reuse generic custody/parser, then enforce this producer's exact training contract."""
    import scientific_fields
    import numpy as np
    metadata = scientific_fields.parse_bundle(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        producer_raw = archive.read('sources/producer-receipt.json')
        producer = generate.decode(producer_raw)
        controls = producer.get('controls', {})
        seed = controls.get('seed')
        require(type(seed) is int and 100 <= seed <= 111 and controls == {'grid':32,'frames':8,'seed':seed,'method':'jacobi'},
                'Training needs whole eight-frame Jacobi seeds 100..111 at grid32.')
        wire = archive.read('sources/wire.bin')
        build = archive.read('sources/build-receipt.json')
        policy = archive.read('sources/native-policy.json')
        build_value = generate.decode(build)
        require(generate.sha(build) == SERIAL_BUILD_SHA256, 'Original serial build evidence differs.')
        policy_value = generate.decode(policy)
        generate.closed(policy_value, ('schema_version','policy','source','loader','library_directory','loader_arguments','runtime_files','absent_paths'))
        require(type(policy_value['schema_version']) is int and policy_value['schema_version'] == 1 and policy_value['policy'] == 'glibc_x86_64_no_preload_v1'
                and policy_value['source'].get('sha256') == generate.BINARY_SHA256
                and policy_value['library_directory'] == generate.LIBRARY_DIRECTORY
                and policy_value['loader_arguments'] == generate.LOADER_ARGUMENTS
                and policy_value['absent_paths'] == ['/etc/ld.so.preload'], 'Producer native policy differs.')
        validate_policy_evidence(policy_value, producer.get('loaded_mappings', {}))
        require(producer.get('wrapper_sha256') == generate.sha(Path(generate.__file__).read_bytes()),
                'Training data was not generated by the captured approved producer version.')
        require(build_value.get('binary_sha256') == generate.BINARY_SHA256
                and all(build_value.get('source',{}).get(name,{}).get('commit') == pin for name,pin in generate.SOURCE_PINS.items()),
                'Training producer source/build identity differs.')
        require(producer.get('binary_sha256') == generate.BINARY_SHA256
                and producer.get('wire_sha256') == generate.sha(wire) and producer.get('wire_bytes') == len(wire)
                and producer.get('build_receipt_sha256') == generate.sha(build)
                and producer.get('native_policy_sha256') == generate.sha(policy)
                and producer.get('stdin_hex') == (bytes([2]*8+[0])).hex(), 'Training wire custody differs.')
        ready, frames = generate.decode_wire(wire, controls)
        for frame in frames:
            finite(frame['report'].get('relative_residual'),1e-8)
        require(producer.get('ready') == ready and producer.get('frames') == [f['report'] for f in frames],
                'Producer report differs from exact native wire.')
        # Reuse producer projection to check coordinates, stage labels, ordering and all source hashes.
        expected = generate.scientific_bundle(wire, controls, build, producer_raw, policy)
        with zipfile.ZipFile(io.BytesIO(expected)) as reference:
            require(metadata['manifest'] == generate.decode(reference.read('manifest.json')),
                    'Training field manifest differs from exact producer projection.')
        rhs, pressure, hashes = [], [], []
        for index, (entry, frame) in enumerate(zip(metadata['manifest']['frames'], frames, strict=True)):
            values = {}
            for declaration, native in zip(entry['arrays'], frame['arrays'], strict=True):
                data = archive.read(declaration['path'])
                array = np.load(io.BytesIO(data), allow_pickle=False)
                require(array.dtype.str == native['dtype'] and list(array.shape) == native['shape_zyx']
                        and array.flags.c_contiguous and array.tobytes(order='C') == native['raw'],
                        'Training array differs from exact native element bytes.')
                values[native['id']] = array.reshape(-1)
            rhs.append(values['rhs']); pressure.append(values['pressure'])
            hashes.append({'frame':index+1,'rhs_sha256':generate.sha(values['rhs'].tobytes()),
                           'pressure_sha256':generate.sha(values['pressure'].tobytes())})
    return seed, rhs, pressure, {'seed':seed,'frames':8,'asset_sha256':generate.sha(raw),
                                'wire_sha256':generate.sha(wire),'arrays':hashes,'reports':[f['report'] for f in frames]}


def load_training(paths):
    require(len(paths) == 6, 'Bind all six frozen training releases.')
    import scientific_release
    from dataset_releases import connected_components
    import numpy as np
    releases, rows, observations = [], [], {}
    seen_hashes, seen_ids = set(), set()
    progress('loading',0,12,frames=0)
    for index, path in enumerate(paths):
        raw = generate.capture(path,40*1024*1024)[0]
        digest = generate.sha(raw)
        require(digest not in seen_hashes,'Duplicate frozen release.')
        seen_hashes.add(digest)
        summary = scientific_release.validate_bytes(raw,digest)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            manifest = generate.decode(archive.read('manifest.json'))
            selected = manifest['records']
            require(len(selected) == 2 and all(row['split']=='train' for row in selected),
                    'Each training release must contain two reviewed training trajectories.')
            for row in selected:
                require(row['id'] not in seen_ids,'Duplicate training record across releases.')
                seen_ids.add(row['id']);rows.append(row)
                seed,rhs,pressure,evidence = validate_asset(archive.read(row['asset']))
                require(seed not in observations,'Duplicate seed or trajectory across releases.')
                evidence.update(record_id=row['id'],release_sha256=digest,revision=row['revision'])
                observations[seed]=(rhs,pressure,evidence)
                progress('loading',len(observations),12,frames=len(observations)*8)
        releases.append({'input':RELEASE_NAMES[index],'sha256':digest,'bytes':len(raw),
                         'field_sequence_count':summary['field_sequence_count']})
    require(set(observations)==set(range(100,112)),'Missing training seeds.')
    components=connected_components(rows)
    require(len(set(components.values()))==12,'Training trajectories share a protected family or ancestry.')
    rhs=np.stack([array for seed in range(100,112) for array in observations[seed][0]])
    pressure=np.stack([array for seed in range(100,112) for array in observations[seed][1]])
    require(rhs.shape==pressure.shape==(96,32768) and rhs.dtype.str==pressure.dtype.str=='<f8',
            'Training requires all96 original ordered float64 observations.')
    receipt={'schema_version':1,'releases':releases,'trajectory_order':list(range(100,112)),
             'frame_order':list(range(1,9)),'shape':[96,32768],'dtype':'<f8',
             'rhs_sha256':generate.sha(rhs.tobytes()),'pressure_sha256':generate.sha(pressure.tobytes()),
             'trajectories':[observations[seed][2] for seed in range(100,112)],
             'scope':'Selected frozen records only; authored QA review is not scientific certification.'}
    return rhs,pressure,receipt


def validate_comparison(value, ref, predicted):
    require(ref.get('method') == 'jacobi' and predicted.get('method') == 'learned', 'Validation methods differ.')
    require(value.get('frames')==60 and len(value.get('errors',[]))==60,'Missing validation frames.')
    for field in ('relative_velocity_l2','relative_tracer_l2'):
        maximum=max(finite(row.get(field),1e-5) for row in value['errors'])
        require(maximum < 1e-5 and value['max_'+field]==maximum,'Validation accuracy failed.')
    for row in value['errors']:
        finite(row.get('centered_relative_pressure_l2'));finite(row.get('tracer_rmse'))
    require(value.get('max_ai_divergence') == max(r.get('actual_divergence_max',-1) for r in predicted.get('reports',[])),
            'Validation divergence maximum differs.')
    for record in (ref,predicted):
        require(record.get('frames')==60 and len(record.get('reports',[]))==60,'Missing native validation.')
        for i,report in enumerate(record['reports'],1):
            require(report.get('frame')==i and math.isclose(report.get('time',-1),i/60,rel_tol=1e-12,abs_tol=1e-12), 'Validation frame/time mismatch.')
            finite(report.get('relative_residual'),1e-8);finite(report.get('actual_divergence_max'),1e-5);finite(report.get('courant'),1)
            require(record['method']!='learned' or report.get('iterations')==0,'Learned validation used iterative corrections.')


def physics_rejection(diagnostic):
    if (diagnostic.get('seed') != 500 or diagnostic.get('method') != 'learned'
            or diagnostic.get('exit_code') != 1):
        return False
    try:
        raw = bytes.fromhex(diagnostic['stderr_hex'])
        if generate.sha(raw) != diagnostic.get('stderr_sha256'):
            return False
        text = raw.decode('utf-8')
    except (KeyError, ValueError, UnicodeError):
        return False
    number = r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
    match = re.fullmatch(r'trajectory probe: (?:stored divergence|relative residual) ('+number+r') exceeds ('+number+r')\n', text)
    return bool(match and math.isfinite(float(match[1])) and float(match[1]) > float(match[2]) == 1e-5)


def run(args):
    require(type(args.runtime_snapshot_sha256) is str and generate.HASH.fullmatch(args.runtime_snapshot_sha256), 'Runtime snapshot identity required.')
    require(type(args.threads) is int and 1<=args.threads<=8,'Threads must be1..8.')
    root=Path(__file__).resolve().parent
    sys.path.insert(0,str(root/'cold'));sys.path.insert(0,str(root/'lab/scripts'))
    for name,digest in cpu_compare.SOURCES.items():
        require(generate.sha(generate.capture(root/'lab/scripts'/name,65536)[0])==digest,'Original algorithm changed.')
    output=Path(args.output)
    require(output.is_dir() and not output.is_symlink() and not any(output.iterdir()),'Empty output directory required.')
    os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['RAYON_NUM_THREADS']=str(args.threads)
    rhs,pressure,input_receipt=load_training(args.release)
    import numpy as np
    import torch
    import trajectory_experiment as exp
    from trajectory_model import ModalPressure
    torch.set_num_threads(args.threads);torch.set_num_interop_threads(1)
    binary=root/'lab/target/release/rheon-trajectory-parallel'
    native=generate.capture(binary,8*1024*1024)[0]
    build=generate.capture(args.build_receipt,1024*1024)[0]
    require(generate.sha(native)==cpu_compare.BINARY_SHA256 and generate.sha(build)==cpu_compare.BUILD_RECEIPT_SHA256,'Parallel build differs.')
    transport=native_transport.Transport(binary,generate.capture(args.native_policy,1024*1024)[0],allowed_seeds=(500,501),capture_diagnostics=True)
    exp.BINARY=binary;exp.subprocess=transport
    np.savez(output/'training.npz',rhs=rhs,pressure=pressure)
    model=ModalPressure(32,'cpu')
    progress('fit',0,1)
    start=time.perf_counter();fitted=model.fit(torch.from_numpy(rhs).to('cpu'),torch.from_numpy(pressure).to('cpu'))
    fitted['training_wall_s']=time.perf_counter()-start;model.eval()
    require(fitted.get('method')=='supervised_modal_least_squares' and fitted.get('optimizer_steps')==0
            and fitted.get('fitted_parameters')==32767,'Unexpected fitting algorithm.')
    finite(fitted.get('minimum_training_modal_energy'),positive=True)
    finite(fitted.get('training_mean_relative_pressure_l2'))
    progress('fit',1,1,training_mean_relative_pressure_l2=fitted['training_mean_relative_pressure_l2'],training_wall_s=fitted['training_wall_s'])
    torch.save({'schema':'rheon-modal-trajectory-v1','n':32,'state_dict':{k:v.cpu() for k,v in model.state_dict().items()},
                'training_seeds':tuple(range(100,112))},output/'model.pt')
    checkpoint = torch.load(output/'model.pt', weights_only=True, map_location='cpu')
    require(checkpoint.get('schema') == 'rheon-modal-trajectory-v1' and checkpoint.get('n') == 32
            and checkpoint.get('training_seeds') == tuple(range(100,112)), 'Saved checkpoint contract differs.')
    state = checkpoint['state_dict']
    require(set(state) == {'gains','basis'} and tuple(state['gains'].shape) == (32767,)
            and tuple(state['basis'].shape) == (32,32), 'Saved checkpoint shapes differ.')
    require(all(value.dtype == torch.float64 and torch.isfinite(value).all().item() for value in state.values())
            and (state['gains'] > 0).all().item(), 'Saved checkpoint contains invalid modal values.')
    reopened = ModalPressure(32,'cpu'); reopened.load_state_dict(state); reopened.eval()
    require(all(torch.equal(value,reopened.state_dict()[name]) for name,value in model.state_dict().items()),
            'Saved checkpoint differs from fitted model.')
    validation=[];validation_records=[];progress('validation',0,2)
    for index,seed in enumerate((500,501),1):
        result,ref,predicted,*_=exp.compare(32,seed,60,model)
        require(result.get('seed') == ref.get('seed') == predicted.get('seed') == seed, 'Validation seed differs.')
        validate_comparison(result,ref,predicted);validation.append(result);validation_records.extend((ref,predicted))
        progress('validation',index,2,max_relative_velocity_l2=result['max_relative_velocity_l2'],
                 max_relative_tracer_l2=result['max_relative_tracer_l2'],max_ai_divergence=result['max_ai_divergence'])
    ablation='unexpectedly_accepted'
    ablation_start=len(transport.diagnostics)
    try:exp.rollout(32,'learned',500,1,ModalPressure(32,'cpu'))
    except RuntimeError:
        if len(transport.diagnostics) == ablation_start+1 and physics_rejection(transport.diagnostics[-1]):
            ablation='untrained_unit_gains_rejected_by_physics_gate'
        else:
            raise ValueError('Untrained ablation failed without verified physics rejection.')
    require(ablation=='untrained_unit_gains_rejected_by_physics_gate','Untrained ablation unexpectedly accepted.')
    checkpoint_hash=generate.sha((output/'model.pt').read_bytes())
    training_hash=generate.sha((output/'training.npz').read_bytes())
    provenance={'binary_sha256':generate.sha(native),'source_sha256':cpu_compare.SOURCES,
                'torch':torch.__version__,'numpy':np.__version__,'python':sys.version,'python_executable':sys.executable,
                'runtime_snapshot_sha256':args.runtime_snapshot_sha256,'device':'cpu','threads':args.threads,'build_receipt_sha256':generate.sha(build)}
    memory={'python_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'gpu_peak_allocated_bytes':0,'gpu_peak_reserved_bytes':0}
    validate_memory(memory)
    freeze={'schema':'rheon-trajectory-freeze-v1','n':32,'device':'cpu','training_frames':8,'validation_frames':60,
            'test_frames':120,'test_seeds':[900,901,902,903],'benchmark_repetitions':5,'methods':['jacobi','sgs','learned'],
            'checkpoint_sha256':checkpoint_hash,'training_data_sha256':training_hash,'source':provenance,
            'training':fitted,'training_trajectories':input_receipt['trajectories'],'training_releases':input_receipt['releases'],
            'validation':validation,'ablation':ablation,'memory':memory,
            'limits':{'training_bytes':20000000000,'inference_bytes':8000000000},
            'scope':'Fresh CPU fit from reviewed frozen fields; fixed sealed uniform box; no historical CUDA reproduction.'}
    progress('publishing',0,1)
    artifacts={'freeze.json':freeze,'input-receipt.json':input_receipt}
    for name,value in artifacts.items():(output/name).write_bytes(generate.encode(value))
    result={'schema_version':1,'status':'verified','training':fitted,'validation':validation,
            'validation_records':validation_records,'ablation':ablation,'memory':memory,'source':provenance,
            'input_receipt_sha256':generate.sha((output/'input-receipt.json').read_bytes()),
            'freeze_sha256':generate.sha((output/'freeze.json').read_bytes()),'checkpoint_sha256':checkpoint_hash,
            'training_data_sha256':training_hash,'native_launches':transport.evidence,'native_diagnostics':transport.diagnostics,'releases':input_receipt['releases']}
    (output/'result.json').write_bytes(generate.encode(result))
    summary={'format':'tuldok_result_summary_v1','title':'Frozen-field CPU fit',
             'metrics':[{'name':'Training frames','value':96,'unit':'frames'},
                        {'name':'Fitted parameters','value':32767,'unit':'parameters'},
                        {'name':'Training relative pressure L2','value':fitted['training_mean_relative_pressure_l2'],'unit':''},
                        {'name':'Validation velocity relative L2','value':max(v['max_relative_velocity_l2'] for v in validation),'unit':''}],
             'scope':['Fresh CPU closed-form fit; zero optimizer steps.','Authored QA review; selected frozen training families only.',
                      'Validation seeds500/501; no autonomous test evaluation yet.','No historical CUDA or GPU acceptance.'],
             'checkpoint':'model.pt'}
    (output/'result-summary.json').write_bytes(generate.encode(summary))
    total=0
    for name,_role,limit in OUTPUTS:
        raw=generate.capture(output/name,limit)[0];total+=len(raw)
        with (output/name).open('rb') as handle:os.fsync(handle.fileno())
    require(total<=64*1024*1024,'Training output budget exceeded.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',action='append',required=True)
    for name in ('build-receipt','native-policy','runtime-snapshot-sha256','output'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--threads',type=int,default=8)
    run(parser.parse_args())


if __name__=='__main__':main()
