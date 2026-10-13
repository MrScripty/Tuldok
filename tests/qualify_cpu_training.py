"""Independent frozen-input/NumPy/checkpoint audit of actual P5b fitting evidence."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import torch
import scientific_release


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(artifacts, prepared):
    artifacts = Path(artifacts)
    prepared = json.loads(Path(prepared).read_text())
    rows, releases, ids, states, families = [], [], set(), set(), set()
    require(len(prepared['releases']) == 6, 'Six frozen releases required')
    for entry in prepared['releases']:
        raw = Path(entry['path']).read_bytes()
        require(sha(raw) == entry['id'] and len(raw) == entry['bytes'], 'Frozen release custody changed')
        validated = scientific_release.validate_bytes(raw, entry['id'])
        require(validated['split_counts'] == {'train': 2, 'validation': 0, 'test': 0}, 'Only complete train pairs accepted')
        releases.append({'sha256': sha(raw), 'bytes': len(raw)})
        with zipfile.ZipFile(io.BytesIO(raw)) as outer:
            manifest = json.loads(outer.read('manifest.json'))
            for row in manifest['records']:
                require(row['id'] not in ids and row['review'] == 'human_reviewed' and row['split'] == 'train', 'Duplicate or unreviewed/nontraining record')
                ids.add(row['id'])
                bundle_raw = outer.read(row['asset'])
                require(sha(bundle_raw) == row['content_hash'], 'Bundle custody differs')
                with zipfile.ZipFile(io.BytesIO(bundle_raw)) as bundle:
                    fields = json.loads(bundle.read('manifest.json'))
                    receipt = json.loads(bundle.read('sources/producer-receipt.json'))
                    seed = receipt['controls']['seed']
                    require(receipt['controls'] == {'grid': 32, 'frames': 8, 'seed': seed, 'method': 'jacobi'}, 'Wrong source controls')
                    require(100 <= seed <= 111 and len(fields['frames']) == 8 and len(fields['fields']) == 6, 'Incomplete training trajectory')
                    state = row['field_sequence']['first_observed_state_sha256']
                    family = json.dumps(fields['family'], sort_keys=True)
                    require(state not in states and family not in families, 'Repeated state/family across frozen releases')
                    states.add(state);families.add(family)
                    for index, frame in enumerate(fields['frames']):
                        arrays = {entry['field']: entry for entry in frame['arrays']}
                        selected = {}
                        for field in ('rhs', 'pressure'):
                            value = arrays[field]
                            array_raw = bundle.read(value['path'])
                            require(sha(array_raw) == value['sha256'], 'Array custody mismatch')
                            array = np.load(io.BytesIO(array_raw), allow_pickle=False)
                            require(array.dtype == np.dtype('<f8') and array.shape == (32, 32, 32) and np.isfinite(array).all(), 'Wrong consumed array dtype/shape/value')
                            selected[field] = array.reshape(-1)
                        rows.append((seed, index+1, selected))
    require(len(rows) == 96 and {(seed, frame) for seed, frame, _ in rows} == {(seed, frame) for seed in range(100,112) for frame in range(1,9)}, 'Missing/duplicate fit observation')
    rows.sort(key=lambda item: item[:2])
    expected = {field: np.stack([arrays[field] for _, _, arrays in rows]) for field in ('rhs','pressure')}
    with np.load(artifacts/'training.npz', allow_pickle=False) as saved:
        require(set(saved.files) == {'rhs','pressure'}, 'Unexpected training NPZ fields')
        for name, array in expected.items():
            require(saved[name].dtype == np.dtype('<f8') and saved[name].shape == (96,32768), 'Wrong NPZ shape/dtype')
            require(saved[name].tobytes(order='C') == array.tobytes(order='C'), 'Frozen observations were not the exact NPZ training inputs')
    checkpoint_raw = (artifacts/'model.pt').read_bytes()
    checkpoint = torch.load(io.BytesIO(checkpoint_raw), map_location='cpu', weights_only=True)
    require(set(checkpoint) == {'schema','n','state_dict','training_seeds'} and checkpoint['schema'] == 'rheon-modal-trajectory-v1' and checkpoint['n'] == 32 and list(checkpoint['training_seeds']) == list(range(100,112)), 'Wrong checkpoint schema')
    require(set(checkpoint['state_dict']) == {'basis','gains'}, 'Unexpected model state')
    state = checkpoint['state_dict']
    basis = np.cos(np.pi*np.arange(32,dtype=np.float64)[:,None]*(np.arange(32,dtype=np.float64)[None,:]+.5)/32)*np.sqrt(2/32)
    basis[0] /= np.sqrt(2)
    require(tuple(state['basis'].shape) == (32,32) and tuple(state['gains'].shape) == (32767,), 'Checkpoint shape mismatch')
    require(all(tensor.dtype == torch.float64 and torch.isfinite(tensor).all().item() for tensor in state.values()), 'Checkpoint nonfinite or downcast')
    np.testing.assert_allclose(state['basis'].numpy(),basis,rtol=1e-13,atol=1e-14)
    def transform(array, inverse=False):
        value = array.reshape(-1,32,32,32)
        matrix = basis if inverse else basis.T
        for axis in (-1,-2,-3):
            value = np.moveaxis(np.moveaxis(value,axis,-1) @ matrix,-1,axis)
        return value.reshape(-1,32768)
    x = transform(expected['rhs'])[:,1:];y = transform(expected['pressure'])[:,1:]
    energy = np.sum(x*x,axis=0);require(np.isfinite(energy).all() and energy.min()>0,'Unexcited/nonfinite fitted mode')
    gains = np.sum(x*y,axis=0)/energy
    require(np.isfinite(gains).all() and gains.min()>0,'Nonpositive/nonfinite fitted gains')
    np.testing.assert_allclose(state['gains'].numpy(),gains,rtol=1e-8,atol=1e-12)
    prediction = transform(transform(expected['rhs'])*np.concatenate(([0.],gains)),True)
    prediction -= prediction[:,:1]
    relative = np.linalg.norm(prediction-expected['pressure'],axis=1)/np.linalg.norm(expected['pressure'],axis=1)
    require(np.isfinite(relative).all(),'Nonfinite independently replayed fit error')
    freeze=json.loads((artifacts/'freeze.json').read_text())
    require(freeze['checkpoint_sha256'] == sha(checkpoint_raw) and freeze['training_data_sha256'] == sha((artifacts/'training.npz').read_bytes()),'Freeze output identity mismatch')
    require(freeze['training_frames']==8 and freeze['validation_frames']==60 and freeze['test_seeds']==[900,901,902,903], 'Changed acceptance controls')
    require(freeze['ablation']=='untrained_unit_gains_rejected_by_physics_gate','Missing actual ablation refusal')
    fitted=freeze['training'];require(fitted['optimizer_steps']==0 and fitted['fitted_parameters']==32767,'Fabricated optimizer progress or reduced modes')
    np.testing.assert_allclose(fitted['training_mean_relative_pressure_l2'],relative.mean(),rtol=1e-7,atol=1e-12)
    input_receipt=json.loads((artifacts/'input-receipt.json').read_text())
    require(input_receipt['trajectory_order']==list(range(100,112)) and input_receipt['frame_order']==list(range(1,9)), 'Receipt order differs')
    for field,array in expected.items():
        require(input_receipt[field+'_sha256']==sha(array.tobytes(order='C')), 'Actual consumed-array receipt differs')
    require([item['sha256'] for item in input_receipt['releases']]==[item['sha256'] for item in releases], 'Consumed release identities differ')
    result=json.loads((artifacts/'result.json').read_text())
    require(result['status']=='verified' and result['training']==fitted and result['validation']==freeze['validation'], 'Final report drift')
    for key,name in [('input_receipt_sha256','input-receipt.json'),('freeze_sha256','freeze.json'),('checkpoint_sha256','model.pt'),('training_data_sha256','training.npz')]:
        require(result[key]==sha((artifacts/name).read_bytes()), 'Final output custody mismatch: '+name)
    validation=result['validation'];require([case['seed'] for case in validation]==[500,501], 'Wrong validation seeds')
    for case in validation:
        require(case['frames']==60 and len(case['errors'])==60, 'Incomplete validation')
        for field in ('relative_velocity_l2','relative_tracer_l2'):
            values=np.array([row[field] for row in case['errors']],dtype=np.float64)
            require(np.isfinite(values).all() and values.min()>=0 and values.max()<1e-5 and case['max_'+field]==values.max(), 'Validation report maximum fails')
    reports=result['validation_records']
    require({(row['seed'],row['method']) for row in reports}=={(seed,method) for seed in (500,501) for method in ('jacobi','learned')} and len(reports)==4, 'Missing validation native reports')
    for row in reports:
        require(len(row['reports'])==60,'Missing validation frames')
        for index,frame in enumerate(row['reports'],1):
            require(frame['frame']==index,'Wrong validation frame order')
            for key,limit in [('relative_residual',1e-8),('actual_divergence_max',1e-5),('courant',1)]:
                require(type(frame[key]) in (int,float) and np.isfinite(frame[key]) and 0<=frame[key]<=limit,'Validation physics report fails')
            if row['method']=='learned':require(frame['iterations']==0,'Learned validation used iterations')
    return {'qualification':'Independent NumPy replay of exact frozen training inputs and closed-form checkpoint gains; original producer validation reports retained separately',
            'limitations':['QA-authored owner review, not independent end-user scientific acceptance.','No new holdout, GPU, general 3D or autonomous evaluation acceptance.'],
            'releases':releases,'records':len(ids),'observations':96,'fitted_parameters':32767,'optimizer_steps':0,
            'ordered_input_array_sha256':{name:sha(value.tobytes(order='C')) for name,value in expected.items()},
            'model_sha256':sha(checkpoint_raw),'training_npz_sha256':sha((artifacts/'training.npz').read_bytes()),
            'minimum_training_modal_energy':float(energy.min()),'training_mean_relative_pressure_l2':float(relative.mean()),
            'maximum_gain_relative_difference':float(np.max(np.abs(state['gains'].numpy()-gains)/gains))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',required=True);parser.add_argument('--prepared-inputs',required=True);parser.add_argument('--report')
    args=parser.parse_args();result=audit(args.artifacts,args.prepared_inputs)
    raw=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.report:Path(args.report).write_text(raw)
    print(raw,end='')


if __name__=='__main__':main()
