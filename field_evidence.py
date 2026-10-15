"""Generic scientific co-test contracts, without numerical or permission policy.

The domain adapter owns field/stage/gauge semantics and canonical-release
derivation. These checks establish representation and lossless custody only.
No registered scientific model adapter is qualified by importing this module.
"""
import hashlib
import io
import math
import zipfile

import scientific_fields as fields
import scientific_release
from workbench import IDENTIFIER, WorkbenchError, encode

MAX_CASES = 256
ACCESSORS = ('whole', 'segment', 'capture', 'import', 'query', 'summary', 'cache', 'export')


def _require(condition, message, code='invalid'):
    if not condition:
        raise WorkbenchError('Field evidence: ' + message, code)


def _exact(value, keys, label):
    _require(type(value) is dict and set(value) == set(keys), label + ' fields differ from the contract.')


def _sha(value):
    _require(type(value) is str and fields.HASH.fullmatch(value), 'Expected a lowercase SHA-256.')
    return value


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def validate_contract(value):
    """Validate an adapter-owned versioned input/output/stage contract."""
    _exact(value, ('format', 'owner', 'adapter', 'source_sha256', 'inputs', 'output', 'time_mode'), 'Adapter')
    _require(value['format'] == 'field_adapter_contract_v1', 'Unsupported adapter contract.', 'unsupported')
    fields.text(value['owner'], 160, 'Domain owner')
    _exact(value['adapter'], ('name', 'version'), 'Adapter identity')
    fields.text(value['adapter']['name'], 64, 'Adapter name')
    _require(type(value['adapter']['version']) is int and 1 <= value['adapter']['version'] <= 2**53-1, 'Adapter version must be a positive safe integer.')
    _sha(value['source_sha256'])
    _require(value['time_mode'] in ('standalone', 'sequence'), 'Unsupported temporal semantics.', 'unsupported')
    _require(type(value['inputs']) is list and 1 <= len(value['inputs']) <= 16, 'Declare 1 to 16 input fields.')
    ids = set()
    for item in value['inputs'] + [value['output']]:
        _exact(item, ('field_id', 'dtype', 'shape_zyx', 'centering', 'stage', 'units', 'gauge_policy_sha256'), 'Field')
        key = item['field_id']
        _require(type(key) is str and fields.TOKEN.fullmatch(key) and key not in ids, 'Field IDs must be unique tokens.')
        ids.add(key)
        _require(item['dtype'] in ('<f4', '<f8') and item['centering'] in fields.CENTERINGS, 'Unsupported dtype or centering.', 'unsupported')
        shape = item['shape_zyx']
        _require(type(shape) is list and len(shape) == 3 and all(type(n) is int and 1 <= n <= 129 for n in shape), 'Field shape must be bounded ZYX.')
        fields.text(item['stage'], 160, 'Field stage')
        fields.text(item['units'], 80, 'Field units')
        _sha(item['gauge_policy_sha256'])
    return value


def require_population(split, accessor):
    """Fail closed for test at every accessor until an owned protection proof exists.

    This is deliberately not a caller-supplied `permission_proved` switch.
    Access/Runs must qualify the full accessor population before replacing it.
    """
    _require(accessor in ACCESSORS, 'Unknown scientific accessor.')
    _require(split in ('train', 'validation', 'test'), 'Unknown split.')
    _require(split != 'test', 'Scientific test evidence is unsupported until all-accessor protection is qualified.', 'unsupported')


def validate_pair(value, contract, blobs):
    """Check exact standalone pressure arrays without conversion or re-gauging."""
    validate_contract(contract)
    _require(contract['time_mode'] == 'standalone', 'A standalone pair cannot represent a trajectory.', 'unsupported')
    _exact(value, ('geometry', 'dtype', 'shape_zyx', 'centering', 'stage', 'units', 'gauge_policy_sha256', 'prediction', 'reference', 'mask'), 'Pressure pair')
    output = contract['output']
    shape = value['shape_zyx']
    _require(type(shape) is list and len(shape) == 3 and all(type(n) is int and 1 <= n <= 129 for n in shape), 'Pair shape must contain exact positive ZYX integers.')
    _require(value['mask'] is None, 'Masked pressure pairs require a separately qualified domain contract.', 'unsupported')
    fields.grid_contract(value['geometry'])
    for name in ('dtype', 'shape_zyx', 'centering', 'stage', 'units', 'gauge_policy_sha256'):
        _require(value[name] == output[name], 'Output ' + name + ' differs from the selected adapter contract.')
    _require(value['dtype'] == '<f8' and value['centering'] == 'cell', 'pressure_field_pair_v1 requires float64 cell arrays.', 'unsupported')
    field = dict(dtype=value['dtype'], centering=value['centering'])
    _require(value['shape_zyx'] == fields.shape_for(value['geometry'], field), 'Pair shape differs from geometry.')
    for name in ('prediction', 'reference'):
        raw = _blob(value[name], blobs)
        fields.npy_payload(raw, field, value['geometry'])
    return value


def _blob(ref, blobs):
    _exact(ref, ('name', 'sha256', 'bytes', 'media_type'), 'Blob')
    fields.text(ref['name'], 120, 'Blob name')
    _require('/' not in ref['name'] and '\\' not in ref['name'] and ref['name'] not in ('.', '..'), 'Blob names must be flat.')
    fields.text(ref['media_type'], 80, 'Blob media type')
    _sha(ref['sha256'])
    _require(type(ref['bytes']) is int and 0 < ref['bytes'] <= fields.BUNDLE_LIMIT, 'Invalid blob byte bound.')
    raw = blobs.get(ref['name'])
    _require(type(raw) is bytes, 'Required retained blob is unavailable.', 'unavailable')
    _require(len(raw) == ref['bytes'] and hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Retained blob identity differs.')
    return raw


def validate_derivation(receipt, contract, releases, outputs):
    """Verify an adapter receipt maps exact source NPYs into retained outputs.

    The adapter runs separately under Runs. This verifier never constructs NPZ
    tensors or infers source coordinates. Packing/reshaping beyond exact NPY
    copies requires an adapter-owned independent oracle, not this contract check.
    """
    validate_contract(contract)
    _exact(receipt, ('format', 'contract_sha256', 'family_scope', 'cases', 'fit_case_ids'), 'Derivation')
    _require(receipt['format'] == 'field_input_derivation_v1', 'Unsupported input derivation.', 'unsupported')
    _require(receipt['contract_sha256'] == digest(contract), 'Derivation contract differs from selected material.')
    _require(receipt['family_scope'] == 'selected_records_only', 'Canonical v1 cannot certify omitted family bridges.', 'unsupported')
    cases = receipt['cases']
    _require(type(cases) is list and 1 <= len(cases) <= MAX_CASES, 'Derivation requires bounded complete case membership.')
    source_rows, parsed, source_manifests, ids, families, mappings, train = {}, {}, {}, set(), {}, set(), []
    members, frames = set(), set()
    for case in cases:
        _exact(case, ('id', 'release_sha256', 'record_id', 'split', 'family', 'protected_groups', 'frame', 'time', 'geometry_sha256', 'arrays'), 'Case')
        fields.text(case['id'], 160, 'Case ID')
        _require(case['id'] not in ids, 'Duplicate derivation case.')
        ids.add(case['id'])
        _require(type(case['record_id']) is str and IDENTIFIER.fullmatch(case['record_id']), 'Source member ID must be canonical.')
        require_population(case['split'], 'capture')
        release_sha = _sha(case['release_sha256'])
        raw = releases.get(release_sha)
        _require(type(raw) is bytes, 'Canonical source release is unavailable.', 'unavailable')
        if release_sha not in source_rows:
            validated = scientific_release.validate_bytes(raw, release_sha)
            for summary in validated['field_sequences']:
                source_manifests[release_sha, summary['id']] = summary['manifest']
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                manifest = fields.decode(archive.read('manifest.json'))
                source_rows[release_sha] = {row['id']: row for row in manifest['records']}
                for row in manifest['records']:
                    parsed[release_sha, row['id']] = archive.read(row['asset'])
        row = source_rows[release_sha].get(case['record_id'])
        _require(row is not None and row['split'] == case['split'], 'Case membership differs from the canonical frozen split.')
        members.add((release_sha, case['record_id']))
        _require(case['protected_groups'] == row['groups'], 'Derivation must retain exact frozen protected groups.')
        source = source_manifests[release_sha, case['record_id']]
        _require(case['family'] == source['family'], 'Case family differs from the source.')
        # Whole-source/state/family groups survive derivation, across releases.
        for family in row['groups']:
            _require(family not in families or families[family] == case['split'], 'Protected family crosses derivation splits.')
            families[family] = case['split']
        frame = case['frame']
        _require(type(frame) is int and 0 <= frame < len(source['frames']), 'Source frame is out of bounds.')
        frames.add((release_sha, case['record_id'], frame))
        _require(case['time'] == source['frames'][frame]['time'], 'Source time spelling differs.')
        _require(case['geometry_sha256'] == digest(source['grid']), 'Source geometry differs.')
        _require(type(case['arrays']) is list and len(case['arrays']) == len(contract['inputs']) + 1, 'Every declared input and target is required.')
        by_id = {field['id']: field for field in source['fields']}
        arrays = {item['field']: item for item in source['frames'][frame]['arrays']}
        with zipfile.ZipFile(io.BytesIO(parsed[release_sha, case['record_id']])) as archive:
            for item, expected in zip(case['arrays'], contract['inputs'] + [contract['output']], strict=True):
                _exact(item, ('field_id', 'source_sha256', 'payload_sha256', 'gauge_policy_sha256', 'output'), 'Array mapping')
                key = item['field_id']
                _require(key == expected['field_id'] and key in by_id and key in arrays, 'Source field mapping differs.')
                source_field = by_id[key]
                _require(all(source_field[name] == expected[name] for name in ('dtype', 'centering', 'stage', 'units')), 'Source field semantics differ.')
                _require(item['gauge_policy_sha256'] == expected['gauge_policy_sha256'], 'Gauge policy differs.')
                array = archive.read(arrays[key]['path'])
                payload, shape = fields.npy_payload(array, source_field, source['grid'])
                _require(shape == expected['shape_zyx'], 'Source shape differs from selected adapter.')
                _require(item['source_sha256'] == hashlib.sha256(array).hexdigest() and item['payload_sha256'] == hashlib.sha256(payload).hexdigest(), 'Source array/payload identity differs.')
                _require(_blob(item['output'], outputs) == array, 'Input derivation changes source array bytes.')
                mapping = (release_sha, case['record_id'], frame, key)
                _require(mapping not in mappings, 'A source field is mapped more than once.')
                mappings.add(mapping)
        if case['split'] == 'train':
            train.append(case['id'])
    _require(type(receipt['fit_case_ids']) is list and receipt['fit_case_ids'] == train and train, 'Fitted statistics must name exactly the ordered training case IDs.')
    _require(set(releases) == set(source_rows), 'Every selected source release must have declared derivation membership.')
    _require(members == {(sha, member) for sha, rows in source_rows.items() for member in rows}, 'Every frozen source member must be accounted for; no silent case drops.')
    _require(frames == {(sha, member, frame) for (sha, member), source in source_manifests.items()
                       for frame in range(len(source['frames']))}, 'Every frozen source frame must be accounted for; no silent frame drops.')
    return receipt


def validate_co_test(value, contract):
    """Keep exact inference and physical acceptance independent, including failure."""
    validate_contract(contract)
    _exact(value, ('format', 'contract_sha256', 'inference', 'physical'), 'Co-test')
    _require(value['format'] == 'field_co_test_v1' and value['contract_sha256'] == digest(contract), 'Co-test contract differs.')
    for name in ('inference', 'physical'):
        item = value[name]
        _exact(item, ('state', 'reason', 'metrics'), name)
        _require(item['state'] in ('passed', 'failed', 'unavailable', 'unsupported'), 'Unknown co-test outcome.')
        fields.text(item['reason'], 500, 'Co-test reason')
        _require(type(item['metrics']) is dict and len(item['metrics']) <= 32, 'Metrics must be bounded.')
        for key, number in item['metrics'].items():
            fields.text(key, 64, 'Metric name')
            try:
                finite = type(number) in (int, float) and math.isfinite(number)
            except OverflowError:
                finite = False
            _require(finite, 'Co-test metric must be finite; undefined values need an explicit domain outcome.')
    return value
