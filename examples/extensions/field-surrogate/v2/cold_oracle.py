"""Independent stdlib numerical consumer, frozen before the first v2 Run.

The bounded NPY reader is retained from oracle0f6128d7; no producer/host import,
training, live checkpoint deserializer or physical qualification is performed.
"""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys

FIXTURE_SHA256 = '3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f'
ABS_TOLERANCE = REL_TOLERANCE = 1e-10
UPDATES = (16, 32, 48, 64)
JSON_LIMIT = 1024 * 1024
ARRAY_LIMIT = 8192


class OracleError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise OracleError(reason)


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def read_file(path, limit, directory=None):
    """Hold a no-follow regular-file descriptor through the bounded stable read."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink==1, 'Only single-link regular input files are accepted.')
        require(before.st_size <= limit, 'Input file exceeds its byte bound.')
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        content = b''.join(chunks)
        require(len(content) <= limit, 'Input file exceeds its byte bound.')
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and len(content) == after.st_size, 'Input file changed during the read.')
        return content
    finally:
        os.close(fd)


def strict_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field.')
            result[key] = value
        return result
    def constant(_value):
        raise OracleError('Nonfinite JSON constant.')
    try:
        value = json.loads(content.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise OracleError('Input must be strict bounded UTF-8 JSON.') from None
    def visit(node, depth=0):
        require(depth <= 16, 'JSON nesting exceeds the bound.')
        if isinstance(node, float):
            require(math.isfinite(node), 'Nonfinite JSON number.')
        if isinstance(node, str):
            require(len(node) <= 4096 and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF
                                                for c in node), 'Unsupported JSON text.')
        if isinstance(node, dict):
            for key, child in node.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1)
    visit(value)
    return value


def closed(value, fields, label):
    require(isinstance(value, dict) and set(value) == set(fields), label + ' fields differ from the frozen contract.')


def finite(value, label):
    require(type(value) in (int, float), label + ' must be a finite number, without coercion.')
    try:
        result = float(value)
    except OverflowError:
        raise OracleError(label + ' exceeds the numeric bound.') from None
    require(math.isfinite(result), label + ' must be finite.')
    return result


def close(actual, expected, label):
    require(math.isfinite(actual) and math.isfinite(expected), label + ' must be finite.')
    difference = abs(actual - expected)
    require(difference <= ABS_TOLERANCE + REL_TOLERANCE * abs(expected), label + ' differs beyond the frozen tolerance.')
    return difference


def npy(content, expected_shape):
    """Decode only finite, non-pickled little-endian float64 NPY v1/v2 arrays."""
    require(len(content) <= ARRAY_LIMIT and len(content) >= 10 and content[:6] == b'\x93NUMPY', 'Invalid or oversized NPY file.')
    version = tuple(content[6:8])
    require(version in ((1, 0), (2, 0)), 'Unsupported NPY version.')
    width = 2 if version == (1, 0) else 4
    start = 8 + width
    require(len(content) >= start, 'Truncated NPY header length.')
    length = int.from_bytes(content[8:start], 'little')
    end = start + length
    require(0 < length <= 4096 and end <= len(content) and end % 16 == 0, 'Invalid or truncated NPY header bound/alignment.')
    header = content[start:end]
    require(header.endswith(b'\n'), 'NPY header must end with a newline.')
    try:
        expression = ast.parse(header.decode('ascii').strip(), mode='eval')
        nodes = list(ast.walk(expression))
        require(len(nodes) <= 64 and isinstance(expression.body, ast.Dict), 'NPY header is not a bounded literal dictionary.')
        allowed = (ast.Expression, ast.Dict, ast.Tuple, ast.Constant, ast.Load)
        require(all(isinstance(node, allowed) for node in nodes), 'NPY header contains unsupported expressions.')
        keys = [key.value for key in expression.body.keys if isinstance(key, ast.Constant) and type(key.value) is str]
        require(len(keys) == len(expression.body.keys) == len(set(keys)), 'Duplicate or malformed NPY header keys.')
        metadata = ast.literal_eval(expression)
    except (SyntaxError, UnicodeError, ValueError, RecursionError, TypeError):
        raise OracleError('Malformed NPY literal header.') from None
    closed(metadata, ('descr', 'fortran_order', 'shape'), 'NPY header')
    require(metadata['descr'] == '<f8', 'Only explicit little-endian float64 arrays are accepted.')
    require(metadata['fortran_order'] is False, 'Only C-order arrays are accepted.')
    shape = metadata['shape']
    require(type(shape) is tuple and all(type(size) is int and 0 < size <= 64 for size in shape)
            and shape == expected_shape, 'NPY shape differs from the selected artifact contract.')
    count = math.prod(shape)
    require(len(content) == end + count * 8, 'Truncated or trailing NPY payload.')
    values = struct.unpack('<' + str(count) + 'd', content[end:])
    require(all(math.isfinite(value) for value in values), 'NPY payload contains nonfinite values.')
    return values


def qualify(fixture_path,artifacts,expected_context_sha256):
    raw=read_file(fixture_path,JSON_LIMIT)
    require(sha256(raw)==FIXTURE_SHA256,'Frozen explicit fixture differs.')
    fixture=strict_json(raw)
    require(fixture['format']=='extension_a_authored_fixture_v2' and fixture['shape_zyx']==[4,4,4]
            and fixture['dtype']=='<f8' and fixture['order']=='C' and fixture['centering']=='cell'
            and fixture['timeline']=='not_applicable','Unsupported explicit scalar fixture.')
    grid={'shape_xyz':[4,4,4],'origin_xyz':[0,0,0],'spacing_xyz':[1,1,1],
          'orientation':[[1,0,0],[0,1,0],[0,0,1]],'units':'m'}
    gauge={'format':'authored_scalar_gauge_v1','operation':'identity','field_units':'dimensionless'}
    require(fixture['geometry']==grid and fixture['gauge_policy']==gauge,'Explicit origin/orientation/gauge differs.')
    cases={case['id']:case for case in fixture['cases']}
    require(len(cases)==3 and fixture['fit_member_ids']==['train-0','train-1'] and fixture['probe_member_id']=='validation-0','Frozen population differs.')
    for key,case in cases.items():
        require(case['split']==('validation' if key=='validation-0' else 'train'),'Split differs.')
        require(len(case['initial'])==len(case['target'])==64,'Field size differs.')
        for x,y in zip(case['initial'],case['target'],strict=True):close(finite(y,'Target'),.5*finite(x,'Input')+.25,'Authored target equation')
    train=[finite(value,'Training value') for key in fixture['fit_member_ids'] for value in cases[key]['initial']]
    mean=math.fsum(train)/len(train);std=math.sqrt(math.fsum((value-mean)**2 for value in train)/len(train))
    require(std>0,'Training variance is not positive.')
    root=Path(artifacts)
    expected_names={'execution-context.json','model-evidence.json','model-definition.json','profile.json','probe.json',
        'metric-definitions.json','checkpoints.json','observations.json','field-index.json','fitted-transform.json','output-policy.json',
        'diagnostics.json','transform.npy','reference.npy','input-initial.npy'}|{f'{prefix}-{point}.{suffix}' for point in UPDATES
        for prefix,suffix in (('weights','npy'),('prediction','npy'),('checkpoint','json'))}
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        require(set(os.listdir(directory))==expected_names,'Actual output inventory differs.')
        retained={name:read_file(name,65536 if name=='execution-context.json' else JSON_LIMIT if name.endswith('.json') else ARRAY_LIMIT,directory)
                  for name in expected_names}
        require(set(os.listdir(directory))==expected_names,'Actual output inventory changed while reading.')
    finally:os.close(directory)
    context_raw=retained['execution-context.json']
    require(sha256(context_raw)==expected_context_sha256,'Context differs from independently selected custody identity.')
    context=strict_json(context_raw);static=context['static'];policy=static['policy']
    require(context['format']=='extension_evidence_context_v1' and static['probe']['data_sha256']==FIXTURE_SHA256,'Context fixture binding differs.')
    require(policy['fields'][0]['geometry']==grid and policy['fields'][0]['gauge_policy']==gauge,'Admitted explicit field metadata differs.')
    require([item['member_id'] for item in policy['fit_members']]==fixture['fit_member_ids'] and
            all(item['split']=='train' and item['sha256']==FIXTURE_SHA256 for item in policy['fit_members']),'Admitted fit lineage differs.')
    probe=static['probe']['members'];require(len(probe)==1 and probe[0]['frozen_reference']['member_id']=='validation-0' and
            probe[0]['frozen_reference']['split']=='validation','Admitted fixed probe differs.')
    transform=npy(retained['transform.npy'],(2,));close(transform[0],mean,'Train mean');close(transform[1],std,'Train population standard deviation')
    member=cases['validation-0'];inputs=npy(retained['input-initial.npy'],(4,4,4));reference=npy(retained['reference.npy'],(4,4,4))
    for actual,expected in zip(inputs,member['initial'],strict=True):close(actual,expected,'Retained probe input')
    for actual,expected in zip(reference,member['target'],strict=True):close(actual,expected,'Retained probe target')
    manifest=strict_json(retained['model-evidence.json']);index=strict_json(retained['checkpoints.json']);observations=strict_json(retained['observations.json'])
    require(manifest['producer']['run_id']==context['run_id'] and manifest['producer']['material_sha256']==context['composition']['sha256']
            and manifest['model_sha256']==static['model']['sha256'] and manifest['task']==static['task'],'Actual evidence identity differs.')
    require(index['run_id']==context['run_id'] and len(index['entries'])==4,'Actual checkpoint coverage differs.')
    require(sum(entry['selected'] is True for entry in index['entries'])==1 and index['entries'][-1]['selected'] is True,'Last diagnostic checkpoint selection differs.')
    results=[]
    for point,entry in zip(UPDATES,index['entries'],strict=True):
        require(type(entry['clocks']['optimizer_update']) is int and entry['clocks']['optimizer_update']==point and
                entry['clocks']['epoch'] is None and entry['clocks']['fit_pass'] is None and entry['clocks']['physical_time'] is None,'Actual update/standalone clock differs.')
        descriptor_raw=retained[f'checkpoint-{point}.json'];descriptor=strict_json(descriptor_raw)
        require(sha256(descriptor_raw)==entry['checkpoint']['sha256'] and descriptor['run_id']==context['run_id'] and
                descriptor['clocks']==entry['clocks'] and descriptor['model_sha256']==static['model']['sha256'],'Descriptor source/clock binding differs.')
        weight_name=f'weights-{point}.npy';prediction_name=f'prediction-{point}.npy'
        require(descriptor['weights']['name']==weight_name and descriptor['weights']['sha256']==sha256(retained[weight_name]),'Actual weight identity differs.')
        weights=npy(retained[weight_name],(2,));prediction=npy(retained[prediction_name],(4,4,4))
        rate=finite(static['parameters']['learning_rate'],'Admitted learning rate')
        require(0<rate<=.5 and static['parameters']['updates']==64,'Unsupported actual optimizer settings.')
        factor=1-(1-2*rate)**point;analytic=(.5*std*factor,(.5*mean+.25)*factor)
        weight_error=max(close(actual,expected,'Analytic optimizer state') for actual,expected in zip(weights,analytic,strict=True))
        reconstructed=[weights[0]*((value-transform[0])/transform[1])+weights[1] for value in inputs]
        replay_error=max(close(actual,expected,'Exact retained-state replay') for actual,expected in zip(prediction,reconstructed,strict=True))
        analytic_error=max(close(actual,(.5*x+.25)*factor,'Independent analytic trajectory') for actual,x in zip(prediction,inputs,strict=True))
        mse=math.fsum((actual-target)**2 for actual,target in zip(prediction,reference,strict=True))/64
        rows=[row for row in observations if row['checkpoint_sha256']==entry['checkpoint']['sha256'] and row['metric_id']=='reference_mse']
        require(len(rows)==1 and rows[0]['state']=='observed' and rows[0]['sample_count']==1,'Metric coverage differs.')
        close(rows[0]['value'],mse,'Independently retallied field MSE')
        results.append({'optimizer_update':point,'reference_mse':mse,'maximum_weight_error':weight_error,
                        'maximum_reconstruction_error':replay_error,'maximum_analytic_prediction_error':analytic_error,
                        'weights_sha256':sha256(retained[weight_name]),'prediction_sha256':sha256(retained[prediction_name])})
    return {'format':'extension_scalar_cold_oracle_v2','state':'valid','scope':'Actual authored scalar numerical state/probes only; no physical or product acceptance',
            'fixture_sha256':FIXTURE_SHA256,'oracle_sha256':sha256(Path(__file__).read_bytes()),'context_sha256':expected_context_sha256,
            'run_id':context['run_id'],'composition':context['composition'],'model':static['model'],
            'population_mean':mean,'population_std':std,'observations':results,
            'artifact_sha256':{name:sha256(raw) for name,raw in sorted(retained.items())},
            'absolute_tolerance':ABS_TOLERANCE,'relative_tolerance':REL_TOLERANCE,'product_acceptance':'not_established'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',required=True);parser.add_argument('--artifacts',required=True)
    parser.add_argument('--expected-context-sha256',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args()
    report_path=Path(args.report).resolve();artifact_path=Path(args.artifacts).resolve()
    require(report_path!=artifact_path and artifact_path not in report_path.parents,'Report must be outside retained artifacts.')
    try:result=qualify(args.fixture,args.artifacts,args.expected_context_sha256)
    except (OracleError,OSError,KeyError,TypeError,ValueError) as error:
        result={'state':'invalid','scope':'independent authored scalar oracle','reason':str(error) if isinstance(error,OracleError) else 'Invalid or unavailable required input.'}
    with report_path.open('x') as output:json.dump(result,output,indent=2,allow_nan=False);output.write('\n')
    print(json.dumps(result,allow_nan=False))
    return 0 if result['state']=='valid' else 1


if __name__=='__main__':sys.exit(main())
