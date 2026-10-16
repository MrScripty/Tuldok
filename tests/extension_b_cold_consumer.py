"""Independent B retained-artifact consumer; stdlib and public SDK only.

The analytic kernel was frozen before inspecting B's producer. This adapter reads
its declared fixture/state protocol, never imports author code or trains. An
operator must supply independently retained Run/context/source identities.
"""
import hashlib
import math
import os
import stat
import sys
from pathlib import Path

if __name__=='__main__':
    source=Path(__file__).resolve()
    sys.path[:0]=[str(source.parent),str(source.parents[1])]

from tuldok_extension_sdk.evidence import canonical, decode, load_context
from extension_b_evidence_contract import validate as validate_contract
from extension_b_numerical_oracle import (OracleError, Population, closed_form_state, decode_npy,
    reconstruct, reference_fields, retallied_mse, training_population, verify_values)

ROLES=dict(inputs=dict(initial='initial',source='source',mask='boundary_mask'),
    fields=dict(raw='raw',corrected='corrected'),
    producer_stages=dict(raw='raw_inference',corrected='boundary_enforcement'))


def require(condition,reason):
    if not condition:raise OracleError(reason)


def read_regular(path,maximum=8*1024**2):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and 0<before.st_size<=maximum,'Expected bounded regular consumer input.')
        raw=source.read(maximum+1);after=os.fstat(source.fileno())
        require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
            and len(raw)==after.st_size<=maximum,'Consumer input changed during read.')
        return raw


def read_artifacts(directory,report):
    require(directory.is_dir() and not directory.is_symlink(),'Expected downloaded artifact directory.')
    require(not report.resolve().is_relative_to(directory.resolve()),'Keep consumer reports outside downloaded artifacts.')
    blobs={};remaining=16*1024**2
    # Path.iterdir on supported CPython3.12 first materializes os.listdir.
    with os.scandir(directory) as entries:
        for entry in entries:
            require(len(blobs)<64 and remaining>0,'B artifact count/aggregate bytes exceed bound.')
            raw=read_regular(entry.path,min(8*1024**2,remaining));remaining-=len(raw);blobs[entry.name]=raw
    require(blobs,'B artifact inventory is empty.')
    return blobs


def verify(context_raw,projection,blobs,fixture_raw,*,expected,fixture_sha256):
    """Return numerical reconstruction/trajectory diagnostics for actual bytes.

    ``expected`` must come from separately fetched public Run/custody/material
    receipts; ``fixture_sha256`` from the author inventory frozen before admission.
    This consumer proves neither owner authority nor scientific qualification.
    """
    structure=validate_contract(context_raw,projection,blobs,expected=expected,roles=ROLES)
    require(type(fixture_raw) is bytes and hashlib.sha256(fixture_raw).hexdigest()==fixture_sha256,
            'Reviewed B source fixture identity differs.')
    context=load_context(context_raw);static=context['static'];policy=static['policy'];fixture=decode(fixture_raw)
    require(static['inputs']['fixture']['measured_sha256']==fixture_sha256,
            'Retained B composition input differs from reviewed fixture.')
    require(static['probe']['data_sha256']==fixture_sha256,'B probe source differs from reviewed fixture.')
    shape=fixture['shape_zyx'];require(shape==[4,4,4] and fixture['dtype']=='<f8' and fixture['centering']=='cell',
        'Independent B source shape/native semantics differ.')
    require(fixture['order']=='C' and fixture['timeline']=='not_applicable','B frozen order/timeline differs.')
    for field in policy['fields']:
        require(canonical(field['geometry'])==canonical(fixture['geometry']) and
            canonical(field['gauge_policy'])==canonical(fixture['gauge_policy']),
            'Admitted B geometry/gauge differs from frozen source.')
    cases=fixture['cases'];case_by_id={case['id']:case for case in cases}
    require(len(cases)==len(case_by_id) and fixture['fit_member_ids']==['train-0','train-1'] and
            [case['id'] for case in cases if case['split']=='train']==fixture['fit_member_ids'],
            'Exact ordered B training population differs.')
    fit=policy['fit_members'];require(len(fit)==2,'B requires both train-only members.')
    for reference,member_id in zip(fit,fixture['fit_member_ids'],strict=True):
        require(reference==dict(input='fixture',sha256=fixture_sha256,member_id=member_id,split='train'),
            'Retained B train-only source identity/order differs.')
    require(policy['preprocessing_policy']==dict(kind='population_standardization',fit_scope='train',
        fields=['initial','source'],fit_members=fixture['fit_member_ids']), 'B train-only preprocessing declaration differs.')
    population=training_population([x for member in fixture['fit_member_ids'] for x in case_by_id[member]['initial']],
        [x for member in fixture['fit_member_ids'] for x in case_by_id[member]['source']])
    native_count=math.prod(shape)
    for case in cases:
        require(all(type(case[key]) is list and len(case[key])==native_count for key in
            ('initial','source','boundary_mask','raw_target','corrected_target')), 'B source native population differs.')
        target=reference_fields(case['initial'],case['source'],case['boundary_mask'],shape=tuple(shape))
        verify_values(case['raw_target'],target.raw,'Source raw target')
        verify_values(case['corrected_target'],target.corrected,'Source corrected target')
    members=static['probe']['members']
    require([member['frozen_reference']['member_id'] for member in members]==[fixture['probe_member_id']] and
            [case['id'] for case in cases if case['split']=='validation']==[fixture['probe_member_id']],
            'B complete fixed validation population differs.')
    for member in members:
        ref=member['frozen_reference']
        require(ref==dict(input='fixture',sha256=fixture_sha256,member_id=fixture['probe_member_id'],split='validation'),
            'B validation source identity differs.')
    transform=decode(blobs['fitted-transform.json']);state=decode_npy(blobs[transform['state']['name']],[2,2])['values']
    transform_error=verify_values(state,(population.mean_initial,population.mean_source,population.std_initial,population.std_source),
        'Retained train-only normalization')
    retained_population=Population(state[0],state[2],state[1],state[3],population.correlation,population.count)
    parameters=static['parameters'];require(set(parameters)=={'learning_rate','updates'} and
        type(parameters['updates']) is int and parameters['updates']==64,'B admitted training parameters differ.')
    architecture=policy['model_specification']['architecture']
    require(architecture==dict(kind='two_feature_affine',weights_shape=[3],feature_order=['initial','source'],
        initial_weights=[0,0,0],boundary_policy='where(boundary_mask,0,raw)'), 'B explicit architecture differs.')
    observations=projection['observations'];diagnostics=[]
    for entry,descriptor in zip(projection['checkpoint_index']['entries'],projection['checkpoints'],strict=True):
        point=entry['clocks']['optimizer_update'];weights=decode_npy(blobs[descriptor['weights']['name']],[3])['values']
        expected_weights=closed_form_state(population,parameters['learning_rate'],point,tuple(architecture['initial_weights']))
        weight_error=verify_values(weights,expected_weights,'Retained analytic B state at update '+str(point))
        for member in members:
            member_id=member['frozen_reference']['member_id'];source=case_by_id[member_id]
            input_rows=next(row['fields'] for row in policy['probe_inputs'] if row['member_id']==member_id)
            inputs={row['field_id']:decode_npy(blobs[row['artifact']],shape)['values'] for row in input_rows}
            for field_id,values in inputs.items():verify_values(values,source[field_id],'Exact B validation '+field_id)
            replay=reconstruct(inputs['initial'],inputs['source'],inputs['boundary_mask'],retained_population,weights,shape=tuple(shape))
            for semantic in ('raw','corrected'):
                binding=next(row for row in policy['field_outputs'] if row['clock']==point and row['field_id']==semantic and row['member_id']==member_id)
                predicted=decode_npy(blobs[binding['prediction']],shape)['values'];reference=decode_npy(blobs[binding['reference']],shape)['values']
                replay_error=verify_values(predicted,getattr(replay,semantic),'Retained B '+semantic+' replay')
                verify_values(reference,source[semantic+'_target'],'Exact B '+semantic+' reference')
                mse=retallied_mse(predicted,reference)
                metrics=[row for row in observations if row['checkpoint_sha256']==entry['checkpoint']['sha256'] and row['metric_id']==semantic+'_reference_mse']
                require(len(metrics)==1 and metrics[0]['sample_count']==len(members),'B metric checkpoint/population differs.')
                metric_error=verify_values([metrics[0]['value']],[mse],'Retallied B '+semantic+' reference MSE')
                diagnostics.append(dict(update=point,member_id=member_id,field_id=semantic,reference_mse=mse,
                    max_replay_error=replay_error,max_weight_error=weight_error,metric_error=metric_error))
    return dict(state='passed',scope='independent_B_closed_form_trajectory_retained_replay_train_only_fit_and_stage_MSE',
        context_sha256=expected['context_sha256'],run_id=expected['run_id'],fixture_sha256=fixture_sha256,
        analytic_kernel_frozen_commit='81c0c5d',identity=structure,normalization_max_error=transform_error,
        diagnostics=diagnostics,quality='diagnostic_only',physical='not_evaluated')


def main():
    import argparse
    import json
    from extension_b_evidence_contract import BContractError
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts','projection','identity','fixture','report'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--fixture-sha256',required=True)
    args=parser.parse_args()
    try:
        blobs=read_artifacts(args.artifacts,args.report)
        result=verify(blobs['execution-context.json'],decode(read_regular(args.projection)),blobs,read_regular(args.fixture),
            expected=decode(read_regular(args.identity)),fixture_sha256=args.fixture_sha256)
        fd=os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as output:json.dump(result,output,indent=2,allow_nan=False);output.write('\n')
        print('Independent B retained replay and analytic trajectory passed:',result['run_id'])
    except (OracleError,BContractError,OSError,KeyError,TypeError,ValueError,IndexError,OverflowError) as error:
        parser.exit(2,'Independent B consumer refused: '+str(error)+'\n')


if __name__=='__main__':main()
