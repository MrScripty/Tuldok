"""Authored dimensionless scalar training; no host imports or physics operators."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

import numpy as np
from evidence_writer import Evidence


def main(fixture_path,context_path,output_path):
    started=time.monotonic();output=Path(output_path)
    fixture_raw=Path(fixture_path).read_bytes();context_raw=Path(context_path).read_bytes()
    if len(fixture_raw)>65536 or len(context_raw)>65536:raise ValueError('Inputs exceed explicit bounds')
    fixture=json.loads(fixture_raw);evidence=Evidence(output,context_raw)
    if (fixture['format']!='extension_a_authored_fixture_v2' or fixture['timeline']!='not_applicable' or
            fixture['geometry']!=evidence.policy['fields'][0]['geometry'] or
            fixture['gauge_policy']!=evidence.policy['fields'][0]['gauge_policy'] or
            hashlib.sha256(fixture_raw).hexdigest()!=evidence.static['probe']['data_sha256']):
        raise ValueError('Admitted explicit fixture geometry/gauge/data differs')
    cases={row['id']:row for row in fixture['cases']}
    fit=[member['member_id'] for member in evidence.policy['fit_members']]
    if fit!=fixture['fit_member_ids'] or any(cases[key]['split']!='train' for key in fit):raise ValueError('Fit population differs')
    train_x=np.concatenate([np.asarray(cases[key]['initial'],dtype='<f8') for key in fit])
    train_y=np.concatenate([np.asarray(cases[key]['target'],dtype='<f8') for key in fit])
    if not np.isfinite(train_x).all() or not np.isfinite(train_y).all():raise ValueError('Training values must be finite')
    mean=float(np.mean(train_x));std=float(np.sqrt(np.mean((train_x-mean)**2)))
    if not np.isfinite(std) or std<=0:raise ValueError('Training-only variance must be positive')
    x=(train_x-mean)/std
    def save(name,values):
        with (output/name).open('xb') as handle:np.save(handle,np.ascontiguousarray(values,dtype='<f8'),allow_pickle=False)
    save('transform.npy',[mean,std]);evidence.transform('transform.npy')
    for row in evidence.policy['probe_inputs']:
        case=cases[row['member_id']]
        for field in row['fields']:
            save(field['artifact'],np.asarray(case[field['field_id']],dtype='<f8').reshape(fixture['shape_zyx']))
    rate=evidence.static['parameters']['learning_rate'];updates=evidence.static['parameters']['updates']
    a=b=0.0;observations=[]
    for update in range(1,updates+1):
        residual=a*x+b-train_y
        a-=rate*2*float(np.mean(residual*x));b-=rate*2*float(np.mean(residual))
        if update%16:continue
        save(f'weights-{update}.npy',[a,b]);mse=[]
        for member in evidence.static['probe']['members']:
            key=member['frozen_reference']['member_id'];case=cases[key]
            if case['split']!='validation' or key in fit:raise ValueError('Probe population differs')
            initial=np.asarray(case['initial'],dtype='<f8');target=np.asarray(case['target'],dtype='<f8')
            normalized_probe=(initial-mean)/std
            prediction=a*normalized_probe+b
            if not np.isfinite(prediction).all():raise ValueError('Nonfinite field prediction')
            binding=next(item for item in evidence.policy['field_outputs'] if item['clock']==update and item['member_id']==key)
            save(binding['prediction'],prediction.reshape(fixture['shape_zyx']))
            if not (output/binding['reference']).exists():save(binding['reference'],target.reshape(fixture['shape_zyx']))
            mse.append(float(np.mean((prediction-target)**2)))
        clocks={'optimizer_update':update,'epoch':None,'fit_pass':None,'physical_time':None,
                'wall_elapsed_ms':int((time.monotonic()-started)*1000)}
        evidence.checkpoint(update,clocks,f'weights-{update}.npy',{'reference_mse':float(np.mean(mse))})
        observations.append({'optimizer_update':update,'reference_mse':float(np.mean(mse))})
        print('optimizer_update',update,flush=True)
    evidence.finish()
    evidence.write('diagnostics.json',{'format':'extension_scalar_training_v1','fit_member_ids':fit,
        'learning_rate':rate,'updates':updates,'observations':observations,'fixture_sha256':hashlib.sha256(fixture_raw).hexdigest()})
    print(json.dumps({'cost':{'main_elapsed_seconds':time.monotonic()-started,
        'process_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}},allow_nan=False),flush=True)


if __name__=='__main__':
    if len(sys.argv)!=4:raise SystemExit('Use producer.py FIXTURE HOST_CONTEXT OUTPUT_DIRECTORY')
    main(*sys.argv[1:])
