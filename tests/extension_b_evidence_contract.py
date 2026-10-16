"""Independent B evidence identity/shape checks; no producer or application import.

Only actual owner-selected context/whole-hash downloaded bytes may support a Run
claim. Unit witnesses are explicitly representative and do not establish E3.
Numerical trajectory/replay acceptance belongs to the separate analytic oracle.
"""
import hashlib

from tuldok_extension_sdk.evidence import EvidenceError, canonical, decode, digest, load_context, validate_projection


class BContractError(ValueError):
    pass


def require(condition, message):
    if not condition: raise BContractError(message)


def same(left, right): return canonical(left) == canonical(right)


def closed(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ' fields differ.')


def sha(value):
    require(type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value), 'Expected exact lowercase SHA256.')
    return value


def validate(context_raw, projection, blobs, *, expected, roles, points=(32,64)):
    """Check fixed B semantics against independently selected authoritative IDs.

    ``roles`` names the exact future author's input/field/stage IDs explicitly;
    this module never guesses names or changes a host/parser policy. A successful
    result proves identity and complete declared artifact structure only.
    """
    try:
        return _validate(context_raw, projection, blobs, expected, roles, points)
    except BContractError: raise
    except EvidenceError as error: raise BContractError(str(error)) from None
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, RecursionError):
        raise BContractError('Malformed required B evidence.') from None


def _validate(context_raw, projection, blobs, expected, roles, points):
    from extension_b_numerical_oracle import decode_npy
    closed(expected, ('catalog_id','run_id','model_sha256','task_sha256','material_sha256','context_sha256'), 'Expected identity')
    closed(roles, ('inputs','fields','producer_stages'), 'B role selection')
    closed(roles['inputs'], ('initial','source','mask'), 'B required inputs')
    closed(roles['fields'], ('raw','corrected'), 'B required fields')
    closed(roles['producer_stages'], ('raw','corrected'), 'B producer stages')
    for selected in (roles['inputs'], roles['fields'], roles['producer_stages']):
        require(all(type(value) is str and value for value in selected.values()) and len(set(selected.values())) == len(selected),
                'B roles need distinct exact author IDs.')
    require(type(context_raw) is bytes and hashlib.sha256(context_raw).hexdigest() == expected['context_sha256'],
            'Context differs from independently selected custody/Run artifact identity.')
    context = load_context(context_raw); static=context['static']; policy=static['policy']
    require(context['run_id'] == expected['run_id'] and static['catalog_id'] == expected['catalog_id'] and
            static['model']['sha256'] == expected['model_sha256'] and static['task']['sha256'] == expected['task_sha256'] and
            context['composition']['sha256'] == expected['material_sha256'], 'B evidence belongs to another selected Run/material/Model/Task.')
    for key in ('model_sha256','task_sha256','material_sha256','context_sha256'): sha(expected[key])
    validate_projection(projection, context_raw, blobs)
    require(type(points) is tuple and points == (32,64) and all(type(point) is int for point in points), 'B capture contract requires exact updates32/64.')
    capture = static['profile']['capture']
    require(capture['clock'] == 'optimizer_update' and type(capture['interval']) is int and capture['interval'] == 32 and
            type(capture['max_snapshots']) is int and capture['max_snapshots'] == 2, 'B admitted capture cadence differs.')
    fields = policy['fields']
    require(type(fields) is list and len(fields) == 2 and [row['id'] for row in fields] == list(roles['fields'].values()),
            'B must retain ordered raw and corrected field stages.')
    inputs=fields[0]['contract']['inputs']; input_ids=[row['field_id'] for row in inputs]
    require(len(inputs) == 3 and len(set(input_ids)) == 3 and set(input_ids) == set(roles['inputs'].values()),
            'Every required initial/source/mask input must be retained.')
    shape=fields[0]['contract']['output']['shape_zyx']
    require(type(shape) is list and len(shape) == 3 and all(type(size) is int and 1 <= size <= 64 for size in shape), 'B native shape differs.')
    for semantic, field in zip(('raw','corrected'), fields, strict=True):
        contract=field['contract']; output=contract['output']
        require(same(contract['inputs'],inputs) and same(field['geometry'],fields[0]['geometry']) and output['shape_zyx'] == shape and
                output['dtype'] == '<f8' and output['centering'] == 'cell' and output['stage'] == roles['producer_stages'][semantic] and
                contract['time_mode'] == 'standalone', 'B stage/input/native field semantics differ.')
        require(digest(field['gauge_policy']) == output['gauge_policy_sha256'], 'B explicit gauge policy differs.')
    require(all(row['dtype'] == '<f8' and row['centering'] == 'cell' and row['shape_zyx'] == shape for row in inputs),
            'B required input native types/shape differ.')
    members=static['probe']['members']; candidates=policy['probe']['candidates']
    require(static['probe']['split'] == 'validation' and type(members) is list and members and len(members) == len(candidates),
            'B requires the complete fixed validation population.')
    by_candidate={row['frozen_reference']['member_id']:row for row in candidates}
    require(len(by_candidate) == len(candidates), 'B candidate member repeats.')
    for ordinal,member in enumerate(members):
        require(type(member['ordinal']) is int and member['ordinal'] == ordinal and member['frozen_reference']['split'] == 'validation' and
                same({key:value for key,value in member.items() if key != 'ordinal'},by_candidate[member['frozen_reference']['member_id']]),
                'B fixed validation membership/ordinal differs.')
    targets=policy['field_targets']; expected_keys=[(row['frozen_reference']['member_id'],field['id']) for row in candidates for field in fields]
    require(type(targets) is list and len(targets) == len(expected_keys), 'B requires a complete explicit per-stage target map.')
    target_map={}
    for row,key in zip(targets,expected_keys,strict=True):
        closed(row, ('member_id','field_id','payload_sha256'), 'B target')
        require((row['member_id'],row['field_id']) == key and key not in target_map, 'B target map order/identity differs.')
        target_map[key]=sha(row['payload_sha256'])
    for member in members:
        member_id=member['frozen_reference']['member_id']
        require(member['target_sha256'] == digest([dict(field_id=field['id'],payload_sha256=target_map[member_id,field['id']]) for field in fields]),
                'B aggregate target digest differs from ordered raw/corrected references.')
    probe_inputs=policy['probe_inputs']
    require(type(probe_inputs) is list and len(probe_inputs) == len(members), 'B complete probe input inventory differs.')
    input_map={row['member_id']:row['fields'] for row in probe_inputs}
    require(set(input_map) == set(by_candidate), 'B probe inputs name different members.')
    for member in members:
        member_id=member['frozen_reference']['member_id']; declared=input_map[member_id]
        require(type(declared) is list and [row['field_id'] for row in declared] == input_ids, 'B required input field order differs.')
        hashes=[]
        for row in declared:
            array=decode_npy(blobs[row['artifact']],shape)
            hashes.append(dict(field_id=row['field_id'],payload_sha256=array['payload_sha256']))
            if row['field_id'] == roles['inputs']['mask']:
                require(all(value in (0.0,1.0) for value in array['values']), 'B boundary mask must contain only0/1.')
        require(digest(hashes) == member['input_sha256'], 'B required probe input payload identity differs.')
    bindings={}
    for row in policy['field_outputs']:
        closed(row, ('clock','field_id','member_id','prediction','reference'), 'B output binding')
        key=(row['clock'],row['field_id'],row['member_id'])
        require(type(row['clock']) is int and key not in bindings and row['prediction'] != row['reference'],
                'B output clock repeats or source target is relabelled as prediction.')
        bindings[key]=row
    require(set(bindings) == {(point,field['id'],member['frozen_reference']['member_id']) for point in points for field in fields for member in members},
            'B requires complete two-clock/two-stage/member coverage.')
    index=projection['checkpoint_index']['entries']
    require(len(index) == len(points) and [entry['clocks']['optimizer_update'] for entry in index] == list(points), 'B checkpoint clocks differ.')
    groups=decode(blobs['field-index.json'])
    require(type(groups) is list and len(groups) == len(points)*len(fields), 'B field group coverage differs.')
    projected=[]; checked=0
    for entry,point in zip(index,points,strict=True):
        require(type(entry['clocks']['optimizer_update']) is int and entry['clocks']['physical_time'] is None,
                'B optimizer clock must not become physical time.')
        for field in fields:
            group=groups[checked];checked+=1
            require(group['run_id'] == context['run_id'] and group['checkpoint_sha256'] == entry['checkpoint']['sha256'] and
                    group['probe_sha256'] == projection['manifest']['probe']['sha256'] and len(group['cases']) == len(members),
                    'B field group identity/coverage differs.')
            for member,case in zip(members,group['cases'],strict=True):
                member_id=member['frozen_reference']['member_id'];binding=bindings[point,field['id'],member_id];output=field['contract']['output']
                require(type(case['member_ordinal']) is int and case['member_ordinal'] == member['ordinal'] and
                        case['predicted']['name'] == binding['prediction'] and case['reference']['name'] == binding['reference'] and
                        case['geometry_sha256'] == digest(field['geometry']) and case['gauge_policy_sha256'] == output['gauge_policy_sha256'] and
                        case['time_units'] == 'not_applicable' and case['mask'] is None, 'B stage/native pair binding differs.')
                prediction=decode_npy(blobs[binding['prediction']],shape);reference=decode_npy(blobs[binding['reference']],shape)
                require(reference['payload_sha256'] == target_map[member_id,field['id']], 'B raw/corrected reference payload differs from its own admitted target.')
                projected.append(dict(checkpoint_sha256=entry['checkpoint']['sha256'],member_ordinal=member['ordinal'],field_id=field['id'],
                    stage=output['stage'],shape_zyx=shape,units=output['units']))
    require(same(projection['fields'],projected), 'B public field projection differs from actual retained stage records.')
    return dict(state='passed',scope='B required_inputs_ordered_stage_target_and_whole_blob_identity',
        run_id=context['run_id'],material_sha256=context['composition']['sha256'],checkpoint_count=len(index),
        field_count=len(projected),required_input_fields=input_ids,numerical='not_evaluated',physical='not_evaluated')
