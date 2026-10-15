"""Explicit canonical field input custody for the next extension policy version.

Callers supply immutable captured bytes. This module validates source identity
and lossless mapping; it never packs tensors, fits transforms or runs a model.
It is not activated by an authored-v1 recipe or by discovery.
"""
import copy
import hashlib
import io
import zipfile

import extension_evidence as evidence
import field_evidence
import scientific_release
import scientific_fields

FORMAT = 'canonical_field_inputs_v1'
POLICY_FORMAT = 'extension_field_policy_v2'
SOURCE_ROLE = 'field_source'
PREDICTION_ROLE = 'field_prediction'
CHECKPOINT_ROLE = 'model_checkpoint'
STATE_ROLE = 'model_state'
OUTPUT_ROLES = {SOURCE_ROLE, PREDICTION_ROLE, CHECKPOINT_ROLE, STATE_ROLE, 'model_context', 'model_evidence', 'field_derivation'}
MEMBER_KEYS = ('case_id', 'record_id', 'revision', 'source_revision', 'split')


def _raw(captured, selected):
    evidence.require(type(captured) is dict, 'Canonical captured inventory must be a dictionary.')
    raw = captured.get('input/' + selected['input'])
    evidence.require(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == selected['sha256'],
                     'Canonical captured input identity differs.', 'unavailable')
    return raw


@evidence.boundary
def validate_declaration(value, policy, definition):
    """Validate the closed declaration without reading providers or a runtime."""
    evidence.require(type(policy) is dict and type(definition) is dict, 'Canonical policy/recipe must be dictionaries.')
    evidence.closed(value, ('format', 'release', 'derivation', 'provenance', 'contract', 'members', 'mapping'), 'Canonical inputs')
    evidence.require(type(definition.get('schema_version')) is int and definition['schema_version'] == 3 and definition.get('format') == 'external_model_evidence_recipe_v2',
                     'Canonical inputs require the catalog-bound schema3 recipe.', 'unsupported')
    evidence.require(value['format'] == FORMAT and policy['format'] == POLICY_FORMAT,
                     'Canonical inputs require the explicit new policy version.', 'unsupported')
    names = set()
    for key in ('release', 'derivation', 'provenance'):
        selected = value[key]
        evidence.closed(selected, ('input', 'sha256', 'output') if key == 'derivation' else ('input', 'sha256'), key)
        evidence.require(type(selected['input']) is str and selected['input'] in definition['inputs'] and
                         selected['input'] not in names, 'Canonical input names must be distinct declared inputs.')
        names.add(selected['input']); evidence.sha(selected['sha256'])
    outputs = {row['path']: row for row in definition['outputs']}
    evidence.require(all(row['role'] in OUTPUT_ROLES for row in outputs.values()), 'Canonical output role is unsupported.', 'unsupported')
    for filename in evidence.COMMON_FILES:
        evidence.require(filename in outputs and outputs[filename]['role'] == ('model_context' if filename == 'execution-context.json' else 'model_evidence'),
                         'Canonical common evidence output role differs.')
    for row in policy['field_outputs']:
        evidence.require(outputs.get(row['prediction'], {}).get('role') == PREDICTION_ROLE and
                         outputs.get(row['reference'], {}).get('role') == SOURCE_ROLE,
                         'Canonical prediction/reference roles must be distinct.')
    for row in policy['probe_inputs']:
        evidence.require(all(outputs.get(item['artifact'], {}).get('role') == SOURCE_ROLE for item in row['fields']),
                         'Canonical probe input must have the source role.')
    output = evidence.name(value['derivation']['output'])
    reserved = evidence.COMMON_FILES | {row[key] for row in policy['field_outputs'] for key in ('prediction', 'reference')}
    reserved |= {field['artifact'] for row in policy['probe_inputs'] for field in row['fields']}
    evidence.require(output not in reserved and output in outputs and outputs[output]['required'] and
                     outputs[output]['role'] == 'field_derivation' and
                     sum(row['role'] == 'field_derivation' for row in outputs.values()) == 1,
                     'Canonical derivation needs one distinct required field_derivation output.')
    contract = field_evidence.validate_contract(value['contract'])
    evidence.require(contract['time_mode'] == 'standalone', 'Canonical initial mode requires standalone fields.', 'unsupported')
    members = value['members']
    evidence.require(type(members) is list and 1 <= len(members) <= field_evidence.MAX_CASES,
                     'Canonical membership must be bounded and complete.')
    cases, records = set(), set()
    for member in members:
        evidence.closed(member, MEMBER_KEYS, 'Canonical member')
        evidence.text(member['case_id'], 'Canonical case ID', 64)
        evidence.require(member['case_id'] not in cases and type(member['record_id']) is str and
                         evidence.ID.fullmatch(member['record_id']) and member['record_id'] not in records,
                         'Canonical case/record identity repeats or differs.')
        cases.add(member['case_id']); records.add(member['record_id'])
        evidence.natural(member['revision'], 'Canonical record revision', 1)
        evidence.natural(member['source_revision'], 'Canonical source revision', 1)
        field_evidence.require_population(member['split'], 'capture')
    release = value['release']
    train = [row['case_id'] for row in members if row['split'] == 'train']
    validation = [row['case_id'] for row in members if row['split'] == 'validation']
    evidence.require(train and validation and policy['probe']['data_input'] == release['input'],
                     'Canonical source needs explicit train and fixed validation membership.')
    expected = lambda row: dict(input=release['input'], sha256=release['sha256'], member_id=row['case_id'], split=row['split'])
    evidence.require(evidence.identical(policy['fit_members'], [expected(row) for row in members if row['split'] == 'train']) and
                     evidence.identical([row['frozen_reference'] for row in policy['probe']['candidates']],
                                        [expected(row) for row in members if row['split'] == 'validation']),
                     'Canonical fit/probe references differ from exact ordered frozen members.')
    targets = policy['field_targets']
    evidence.require(type(targets) is list and len(targets) == len(validation) * len(policy['fields']),
                     'Canonical schema3 requires complete ordered per-field target identities.')
    expected_targets = [(case_id, field['id']) for case_id in validation for field in policy['fields']]
    for row, expected_target in zip(targets, expected_targets, strict=True):
        evidence.closed(row, ('member_id', 'field_id', 'payload_sha256'), 'Canonical field target')
        evidence.require((row['member_id'], row['field_id']) == expected_target, 'Canonical field target order/membership differs.')
        evidence.sha(row['payload_sha256'])
    for candidate in policy['probe']['candidates']:
        expected_hash = evidence.digest([dict(field_id=row['field_id'], payload_sha256=row['payload_sha256'])
            for row in targets if row['member_id'] == candidate['frozen_reference']['member_id']])
        evidence.require(candidate['target_sha256'] == expected_hash,
                         'Canonical schema3 aggregate target identity differs from ordered field targets.')
    mapping = value['mapping']; evidence.closed(mapping, ('inputs', 'target'), 'Canonical field role mapping')
    evidence.require(type(mapping['inputs']) is list and len(mapping['inputs']) == len(contract['inputs']),
                     'Every canonical input field needs an explicit model role.')
    evidence.require(type(policy['fields']) is list and 1 <= len(policy['fields']) <= 4, 'Canonical model field stages must be nonempty and bounded.')
    model_inputs = policy['fields'][0]['contract']['inputs']
    evidence.require(type(model_inputs) is list and 1 <= len(model_inputs) <= 16, 'Canonical model inputs must be nonempty and bounded.')
    evidence.require(len(model_inputs) == len(contract['inputs']), 'Canonical/model required input counts differ.')
    for row, source, target in zip(mapping['inputs'], contract['inputs'], model_inputs, strict=True):
        evidence.closed(row, ('source_field_id', 'model_field_id'), 'Canonical input role')
        evidence.require(row == dict(source_field_id=source['field_id'], model_field_id=target['field_id']) and
                         all(evidence.identical(source[key], target[key]) for key in source if key != 'field_id'),
                         'Canonical input role changes native semantics.')
    evidence.closed(mapping['target'], ('source_field_id',), 'Canonical target role')
    evidence.require(mapping['target']['source_field_id'] == contract['output']['field_id'] and
                     contract['output']['stage'] == 'reference_target', 'Canonical target must be an explicit reference target.')
    for stage in policy['fields']:
        target = stage['contract']['output']
        evidence.require(all(evidence.identical(contract['output'][key], target[key])
                             for key in contract['output'] if key not in ('field_id', 'stage')),
                         'Canonical target/model output native semantics differ.')
    return value


@evidence.boundary
def validate_bindings(value, bindings):
    """Run before capture/runtime: only the named canonical Release kind is allowed."""
    evidence.require(type(bindings) is dict and value['release']['input'] in bindings,
                     'Canonical Release binding is missing.')
    for name, selected in bindings.items():
        evidence.require(type(selected) is dict, 'Canonical input binding is malformed.')
        if name == value['release']['input']:
            evidence.closed(selected, ('kind', 'release_id', 'expected_sha256'), 'Canonical Release binding')
            evidence.require(selected == dict(kind='frozen_release', release_id=value['release']['sha256'],
                                              expected_sha256=value['release']['sha256']),
                             'Canonical Release binding differs from selected source.')
        else:
            evidence.require('kind' not in selected, 'Canonical mode rejects every other kind-tagged input, including unused inputs.', 'unsupported')
            evidence.closed(selected, ('reference_id', 'expected_sha256'), 'Canonical project input binding')
            if name in (value['derivation']['input'], value['provenance']['input']):
                declared = value['derivation'] if name == value['derivation']['input'] else value['provenance']
                evidence.require(selected['expected_sha256'] == declared['sha256'], 'Canonical project binding differs from selected document.')
            evidence.require('kind' not in selected, 'Canonical mode rejects every other kind-tagged input, including unused inputs.', 'unsupported')
    return bindings


@evidence.boundary
def validate_captured(value, policy, definition, material, captured, *, outputs=None):
    """Validate real canonical bytes and all mappings before or after execution.

    Before execution, build a byte-only inventory from the exact source assets.
    After custody, outputs must be the authoritative decoder payloads. Both paths
    call the existing canonical/lossless validators, with no source mutation.
    """
    validate_declaration(value, policy, definition)
    evidence.require(type(material) is dict and type(material['inputs']) is dict and type(captured) is dict,
                     'Canonical material/captured inventories must be dictionaries.')
    receipts = material['inputs']; release = value['release']; selected = receipts.get(release['input'])
    evidence.require(set(receipts) == set(definition['inputs']), 'Canonical declared/captured input inventory differs.')
    evidence.require(all(type(key) is str for key in captured) and
                     {key[6:] for key in captured if key.startswith('input/')} == set(receipts),
                     'Canonical complete captured input inventory differs.')
    evidence.closed(selected, ('kind', 'catalog_id', 'release_id', 'measured_sha256', 'bytes'), 'Captured canonical Release')
    raw = _raw(captured, release)
    evidence.require(selected == dict(kind='frozen_release', catalog_id=material['catalog_id'],
        release_id=release['sha256'], measured_sha256=release['sha256'], bytes=len(raw)),
        'Canonical receipt differs from exact captured source.', 'unavailable')
    for name, receipt in receipts.items():
        evidence.require(type(receipt) is dict and (name == release['input'] or 'kind' not in receipt),
                         'Canonical mode rejects every other captured input kind.', 'unsupported')
        source_raw = captured.get('input/' + name)
        evidence.require(type(source_raw) is bytes and receipt.get('measured_sha256') == hashlib.sha256(source_raw).hexdigest() and
                         name in definition['inputs'] and len(source_raw) <= definition['inputs'][name]['max_bytes'],
                         'Canonical captured input inventory/byte bound differs.', 'unavailable')
    for key in ('derivation', 'provenance'):
        selected = value[key]; document_raw = _raw(captured, selected)
        evidence.require(receipts.get(selected['input'], {}).get('measured_sha256') == selected['sha256'],
                         'Canonical project document receipt differs.', 'unavailable')
        evidence.decode(document_raw)
    derivation_raw = _raw(captured, value['derivation']); derivation = evidence.decode(derivation_raw)
    derivation_rule = next(row for row in definition['outputs'] if row['path'] == value['derivation']['output'])
    evidence.require(type(derivation_rule['max_bytes']) is int and len(derivation_raw) <= derivation_rule['max_bytes'],
                     'Canonical derivation exceeds its declared output byte bound.')
    validated = scientific_release.validate_bytes(raw, release['sha256'])
    for stage in policy['fields']: scientific_fields.grid_contract(stage['geometry'])
    evidence.require(all(evidence.identical(row['manifest']['grid'], stage['geometry']) for row in validated['field_sequences']
                         for stage in policy['fields']), 'Canonical source/model geometry differs.')
    rows = {row['id']: row for row in validated['field_sequences']}
    evidence.require(type(derivation) is dict and type(derivation.get('cases')) is list and
                     len(derivation['cases']) == len(value['members']) == len(rows), 'Canonical complete membership differs.')
    inventory = {} if outputs is None else outputs
    output_rules = {row['path']: row for row in definition['outputs']}; used = set()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frozen = {row['id']: row for row in evidence.decode(archive.read('manifest.json'), 8 * 1024 * 1024)['records']}
        for member, case in zip(value['members'], derivation['cases'], strict=True):
            row = rows.get(member['record_id'])
            evidence.require(row is not None and member['case_id'] == case['id'] and member['record_id'] == case['record_id'] and
                             all(type(row[key]) is type(member[key]) and row[key] == member[key]
                                 for key in ('revision', 'source_revision', 'split')),
                             'Canonical record/revision/case/split identity differs.')
            evidence.require(type(case['frame']) is int and 0 <= case['frame'] < len(row['manifest']['frames']),
                             'Canonical storage frame is invalid.')
            with zipfile.ZipFile(io.BytesIO(archive.read(frozen[row['id']]['asset']))) as bundle:
                arrays = {item['field']: item for item in row['manifest']['frames'][case['frame']]['arrays']}
                for item in case['arrays']:
                    filename = evidence.name(item['output']['name'])
                    evidence.require(filename not in used and filename != value['derivation']['output'] and filename not in evidence.COMMON_FILES and
                                     filename in output_rules and output_rules[filename]['required'] and output_rules[filename]['role'] == SOURCE_ROLE,
                                     'Canonical native output is repeated or not required.')
                    used.add(filename)
                    evidence.require(item['output']['bytes'] <= output_rules[filename]['max_bytes'], 'Canonical native output exceeds its declared bound.')
                    if outputs is None: inventory[filename] = bundle.read(arrays[item['field_id']]['path'])
    evidence.require(used == {filename for filename, rule in output_rules.items() if rule['role'] == SOURCE_ROLE},
                     'Canonical complete native source role inventory differs.')
    lower_bound = len(derivation_raw) + sum(len(inventory[filename]) for filename in used)
    evidence.require(lower_bound <= definition['resources']['max_output_bytes'] and
                     lower_bound <= policy['profile']['limits']['total_output_bytes'], 'Canonical proof cannot fit admitted aggregate output bound.')
    field_evidence.validate_derivation(derivation, value['contract'], {release['sha256']: raw}, inventory)
    by_case = {case['id']: case for case in derivation['cases']}
    probe_inputs = {row['member_id']: row['fields'] for row in policy['probe_inputs']}
    for candidate in policy['probe']['candidates']:
        case_id = candidate['frozen_reference']['member_id']; case = by_case[case_id]
        by_field = {item['field_id']: item for item in case['arrays']}
        expected_inputs = [dict(field_id=role['model_field_id'], artifact=by_field[role['source_field_id']]['output']['name'])
                           for role in value['mapping']['inputs']]
        expected_hash = evidence.digest([dict(field_id=role['model_field_id'], payload_sha256=by_field[role['source_field_id']]['payload_sha256'])
                                         for role in value['mapping']['inputs']])
        target = by_field[value['mapping']['target']['source_field_id']]
        evidence.require(evidence.identical(probe_inputs[case_id], expected_inputs) and candidate['input_sha256'] == expected_hash and
                         all(row['payload_sha256'] == target['payload_sha256'] for row in policy['field_targets'] if row['member_id'] == case_id) and
                         all(row['reference'] == target['output']['name'] for row in policy['field_outputs'] if row['member_id'] == case_id),
                         'Canonical validation input/target bindings differ from retained model probe fields.')
    if outputs is not None:
        validate_output_roles(policy, definition, outputs)
        evidence.require(outputs.get(value['derivation']['output']) == derivation_raw,
                         'Retained derivation differs from exact admitted input.', 'unavailable')
    return dict(format=FORMAT, release_sha256=release['sha256'], derivation_sha256=value['derivation']['sha256'],
                provenance_sha256=value['provenance']['sha256'], members=copy.deepcopy(value['members']),
                source_contract_sha256=field_evidence.digest(value['contract']))


@evidence.boundary
def validate_output_roles(policy, definition, outputs):
    """Repeat purpose separation using authoritative post-decoder JSON bytes."""
    rules = {row['path']: row for row in definition['outputs']}
    def role(filename, expected):
        evidence.require(rules.get(filename, {}).get('role') == expected,
                         'Canonical checkpoint/state/source/prediction output roles collide.')
    index = evidence.decode(outputs['checkpoints.json'])
    evidence.require(type(index['entries']) is list and index['entries'], 'Canonical checkpoint role inventory is missing.')
    descriptors = set()
    for entry in index['entries']:
        filename = entry['checkpoint']['name']; role(filename, CHECKPOINT_ROLE); descriptors.add(filename)
        descriptor = evidence.decode(outputs[filename]); role(descriptor['weights']['name'], STATE_ROLE)
    evidence.require(descriptors == {filename for filename, rule in rules.items() if rule['role'] == CHECKPOINT_ROLE},
                     'Canonical complete checkpoint role inventory differs.')
    transform = evidence.decode(outputs['fitted-transform.json']); role(transform['state']['name'], STATE_ROLE)
    for field in policy['field_outputs']:
        role(field['prediction'], PREDICTION_ROLE); role(field['reference'], SOURCE_ROLE)
    return True
