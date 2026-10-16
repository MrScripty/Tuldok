"""Canonical v3 independent stdlib numerical consumer; freeze before first Run.

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


def archive(raw, maximum_entries, maximum_bytes):
    """Bound the complete stored canonical ZIP before consuming any member."""
    import io
    import zipfile
    require(type(raw) is bytes and 22<=len(raw)<=maximum_bytes and raw[:4]==b'PK\x03\x04'
            and raw[-22:-18]==b'PK\x05\x06','Invalid canonical ZIP byte envelope.')
    value=zipfile.ZipFile(io.BytesIO(raw))
    try:
        entries=value.infolist(); names=value.namelist()
        require(0<len(entries)<=maximum_entries and len(set(names))==len(names) and not value.comment
                and entries[0].header_offset==0,'Canonical ZIP count/name/comment differs.')
        require(all(entry.compress_type==zipfile.ZIP_STORED and entry.flag_bits==0
                    and entry.file_size==entry.compress_size and not entry.is_dir()
                    and len(entry.filename)<=512 and '\\' not in entry.filename
                    and all(part not in ('','.','..') for part in entry.filename.split('/')) for entry in entries),
                'Only bounded relative stored canonical files are accepted.')
        require(sum(entry.file_size for entry in entries)<=maximum_bytes,'Expanded ZIP exceeds its bound.')
        return value
    except BaseException:
        value.close();raise


def zip_member(archive_value, name, maximum):
    require(0<archive_value.getinfo(name).file_size<=maximum,'Canonical member exceeds its byte bound.')
    with archive_value.open(name) as stream: raw=stream.read(maximum+1)
    require(len(raw)==archive_value.getinfo(name).file_size and len(raw)<=maximum,'Canonical member length differs.')
    return raw


def canonical_source(context, retained, fixture, release_path, derivation_path, provenance_path):
    """Independently verify exact native canonical lineage; standard library only."""
    import io
    import zipfile
    policy=context['static']['policy']; selected=policy['canonical']
    require(policy['format']=='extension_field_policy_v2' and selected['format']=='canonical_field_inputs_v1',
            'Expected explicitly versioned canonical policy.')
    release_raw=read_file(release_path,JSON_LIMIT); derivation_raw=read_file(derivation_path,65536)
    provenance_raw=read_file(provenance_path,65536)
    for key,raw in (('release',release_raw),('derivation',derivation_raw),('provenance',provenance_raw)):
        require(sha256(raw)==selected[key]['sha256'],'Captured canonical '+key+' identity differs.')
    require(retained[selected['derivation']['output']]==derivation_raw,'Retained exact derivation differs.')
    derivation=strict_json(derivation_raw); provenance=strict_json(provenance_raw)
    require(provenance['source_sha256']==FIXTURE_SHA256 and provenance['release_sha256']==sha256(release_raw)
            and provenance['contract']==selected['contract'],'Original compilation/source policy differs.')
    require(derivation['contract_sha256']==sha256(json.dumps(selected['contract'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()),
            'Derivation source contract differs.')
    require(derivation['fit_case_ids']==fixture['fit_member_ids'],'Canonical train-only ordered fit differs.')
    original={case['id']:case for case in fixture['cases']}; used=set(); names=set()
    with archive(release_raw,72,JSON_LIMIT) as release:
        manifest=strict_json(zip_member(release,'manifest.json',65536)); rows={row['id']:row for row in manifest['records']}
        require(len(rows)==len(manifest['records'])==len(selected['members'])==len(derivation['cases'])==3,
                'Complete canonical member population differs.')
        for selected_member,case in zip(selected['members'],derivation['cases'],strict=True):
            require(selected_member['case_id']==case['id'] and case['id'] in original and case['id'] not in used,
                    'Canonical original case identity differs.')
            used.add(case['id']); row=rows[selected_member['record_id']]; authored=original[case['id']]
            require(case['record_id']==row['id'] and case['release_sha256']==sha256(release_raw) and
                    all(type(selected_member[key]) is type(row[key]) and selected_member[key]==row[key] for key in ('revision','source_revision','split'))
                    and row['split']==case['split']==authored['split'] and row['groups']==case['protected_groups'],
                    'Frozen canonical record/revision/split/protected groups differ.')
            bundle_raw=zip_member(release,row['asset'],262144); require(sha256(bundle_raw)==row['asset_sha256'],'Canonical asset identity differs.')
            with archive(bundle_raw,64,262144) as bundle:
                source=strict_json(zip_member(bundle,'manifest.json',65536)); proof=strict_json(zip_member(bundle,'sources/compile-receipt.json',65536))
                require(strict_json(zip_member(bundle,'sources/authored-case.json',65536))==authored and
                        source['grid']==fixture['geometry'] and source['family']==case['family'] and
                        source['time_units']=='not_applicable' and len(source['frames'])==1 and
                        type(case['frame']) is int and case['frame']==0 and case['time']==source['frames'][0]['time']=='0' and
                        proof['source']['sha256']==FIXTURE_SHA256 and proof['compiler_sha256']==provenance['compiler_sha256'] and
                        proof['geometry']==fixture['geometry'] and proof['gauge_policy']==fixture['gauge_policy'] and
                        proof['field_mapping']=={'initial':'initial','target':'reference'} and
                        proof['temporal_encoding']=='storage_frame_label_only_no_physical_time' and
                        proof['source_timeline']=='not_applicable','Canonical compiler geometry/gauge/temporal policy differs.')
                arrays={item['field']:item for item in source['frames'][0]['arrays']}
                require([item['field_id'] for item in case['arrays']]==['initial','reference'],'Canonical required fields differ.')
                for item,key in zip(case['arrays'],('initial','target'),strict=True):
                    native=zip_member(bundle,arrays[item['field_id']]['path'],ARRAY_LIMIT); name=item['output']['name']
                    require(name not in names and retained[name]==native and item['source_sha256']==sha256(native)
                            and item['output']['sha256']==sha256(native) and item['output']['bytes']==len(native),
                            'Canonical lossless native output differs.')
                    names.add(name); actual=npy(native,(4,4,4))
                    require(struct.pack('<64d',*actual)==struct.pack('<64d',*authored[key]) and
                            item['payload_sha256']==sha256(struct.pack('<64d',*actual)),
                            'Canonical native values differ bitwise from original source.')
    require(used==set(original),'Canonical complete source population differs.')
    return sha256(release_raw)


def qualify(fixture_path,artifacts,expected_context_sha256,release_path,derivation_path,provenance_path):
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
    expected_names |= {'train-0-initial.npy','train-0-reference.npy','train-1-initial.npy','train-1-reference.npy','canonical-derivation.json'}
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
    release_sha=canonical_source(context,retained,fixture,release_path,derivation_path,provenance_path)
    require(context['format']=='extension_evidence_context_v1' and static['probe']['data_sha256']==release_sha,'Context canonical Release binding differs.')
    require(policy['fields'][0]['geometry']==grid and policy['fields'][0]['gauge_policy']==gauge,'Admitted explicit field metadata differs.')
    require([item['member_id'] for item in policy['fit_members']]==fixture['fit_member_ids'] and
            all(item['split']=='train' and item['sha256']==release_sha and item['input']==policy['canonical']['release']['input'] for item in policy['fit_members']),'Admitted fit lineage differs.')
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
        factor=1-(1-2*rate)**point;configuration=policy['model_specification']['configuration']
        initial_scale=finite(configuration['initial_scale'],'Admitted model initial scale')
        initial_offset=finite(configuration['initial_offset'],'Admitted model initial offset')
        analytic=(initial_scale*(1-factor)+.5*std*factor,initial_offset*(1-factor)+(.5*mean+.25)*factor)
        weight_error=max(close(actual,expected,'Analytic optimizer state') for actual,expected in zip(weights,analytic,strict=True))
        reconstructed=[weights[0]*((value-transform[0])/transform[1])+weights[1] for value in inputs]
        replay_error=max(close(actual,expected,'Exact retained-state replay') for actual,expected in zip(prediction,reconstructed,strict=True))
        analytic_error=max(close(actual,analytic[0]*((x-mean)/std)+analytic[1],'Independent analytic trajectory') for actual,x in zip(prediction,inputs,strict=True))
        mse=math.fsum((actual-target)**2 for actual,target in zip(prediction,reference,strict=True))/64
        rows=[row for row in observations if row['checkpoint_sha256']==entry['checkpoint']['sha256'] and row['metric_id']=='reference_mse']
        require(len(rows)==1 and rows[0]['state']=='observed' and rows[0]['sample_count']==1,'Metric coverage differs.')
        close(rows[0]['value'],mse,'Independently retallied field MSE')
        results.append({'optimizer_update':point,'reference_mse':mse,'maximum_weight_error':weight_error,
                        'maximum_reconstruction_error':replay_error,'maximum_analytic_prediction_error':analytic_error,
                        'weights_sha256':sha256(retained[weight_name]),'prediction_sha256':sha256(retained[prediction_name])})
    return {'format':'extension_scalar_canonical_cold_oracle_v3','state':'valid','scope':'Actual authored scalar numerical state/probes only; no physical or product acceptance',
            'fixture_sha256':FIXTURE_SHA256,'canonical_release_sha256':release_sha,'oracle_sha256':sha256(Path(__file__).read_bytes()),'context_sha256':expected_context_sha256,
            'run_id':context['run_id'],'composition':context['composition'],'model':static['model'],
            'population_mean':mean,'population_std':std,'observations':results,
            'artifact_sha256':{name:sha256(raw) for name,raw in sorted(retained.items())},
            'absolute_tolerance':ABS_TOLERANCE,'relative_tolerance':REL_TOLERANCE,'product_acceptance':'not_established'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',required=True);parser.add_argument('--artifacts',required=True)
    parser.add_argument('--expected-context-sha256',required=True);parser.add_argument('--report',required=True)
    parser.add_argument('--release',required=True);parser.add_argument('--derivation',required=True);parser.add_argument('--provenance',required=True)
    args=parser.parse_args()
    report_path=Path(args.report).resolve();artifact_path=Path(args.artifacts).resolve()
    require(report_path!=artifact_path and artifact_path not in report_path.parents,'Report must be outside retained artifacts.')
    try:result=qualify(args.fixture,args.artifacts,args.expected_context_sha256,args.release,args.derivation,args.provenance)
    except (OracleError,OSError,KeyError,TypeError,ValueError,RuntimeError) as error:
        result={'state':'invalid','scope':'independent authored scalar oracle','reason':str(error) if isinstance(error,OracleError) else 'Invalid or unavailable required input.'}
    with report_path.open('x') as output:json.dump(result,output,indent=2,allow_nan=False);output.write('\n')
    print(json.dumps(result,allow_nan=False))
    return 0 if result['state']=='valid' else 1


if __name__=='__main__':sys.exit(main())
