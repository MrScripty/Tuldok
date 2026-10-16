"""Author-side lossless QA compiler for the exact authored scalar A v2 fixture.

This creates new scientific bundles and real canonical Releases. It is not an
E2 producer, adapter input resolver, training driver, or numerical physics test.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import field_evidence
import scientific_fields
import scientific_release
from workbench import encode

SOURCE_COMMIT = '057c8ab'
SOURCE_PATH = 'examples/extensions/field-surrogate/v2/fixture.json'
SOURCE_SHA256 = '3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f'
TEMPORAL_ENCODING = 'storage_frame_label_only_no_physical_time'
FIELD_MAPPING = {'initial': 'initial', 'target': 'reference'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned_source(repository=ROOT):
    """Read the exact upstream authored source object; never write that checkout."""
    raw = subprocess.check_output(['git', '-C', str(repository), 'show', SOURCE_COMMIT + ':' + SOURCE_PATH])
    if sha(raw) != SOURCE_SHA256:
        raise ValueError('Pinned authored A fixture bytes differ.')
    return raw


def npy(values):
    """Independent standard-library NPY v1 writer, C-order float64 ZYX."""
    header = repr(dict(descr='<f8', fortran_order=False, shape=(4, 4, 4))).encode('ascii')
    header += b' ' * (-(10 + len(header) + 1) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack('<64d', *values)


def archive_bytes(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        for name, raw in members.items():
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100600 << 16
            archive.writestr(entry, raw)
    return stream.getvalue()


def blob(name, raw):
    return dict(name=name, bytes=len(raw), sha256=sha(raw), media_type='application/x-npy')


def compile_authored_a(source_raw):
    """Compile exact source bytes; return new QA bundles, arrays and source contract.

    JSON initial/target values are packed directly as little-endian doubles. The
    original target becomes a field named reference, never a model prediction.
    """
    if type(source_raw) is not bytes or sha(source_raw) != SOURCE_SHA256:
        raise ValueError('Only the exact pinned authored A v2 fixture is supported.')
    source = json.loads(source_raw)
    compiler_sha = sha(Path(__file__).read_bytes())
    gauge_sha = field_evidence.digest(source['gauge_policy'])
    definitions = [dict(id='initial', label='Authored input initial', dtype='<f8', centering='cell', units='dimensionless', stage='input'),
                   dict(id='reference', label='Authored reference target', dtype='<f8', centering='cell', units='dimensionless', stage='reference_target')]
    expected_fields = [dict(field_id=field['id'], dtype=field['dtype'], shape_zyx=[4, 4, 4], centering=field['centering'],
                            stage=field['stage'], units=field['units'], gauge_policy_sha256=gauge_sha) for field in definitions]
    contract = dict(format='field_adapter_contract_v1', owner='Authored scalar A canonical source fixture; private QA only',
        adapter=dict(name='authored_scalar_a_canonical_source', version=1), source_sha256=compiler_sha,
        inputs=expected_fields[:1], output=expected_fields[1], time_mode='standalone')
    bundles, arrays, manifests = {}, {}, {}
    for case in source['cases']:
        native = {field: npy(case[original]) for original, field in FIELD_MAPPING.items()}
        # Every payload is independently checked against the original JSON values;
        # no source fixture arithmetic, normalization, gauge or prediction occurs.
        payload_hashes = {field: sha(struct.pack('<64d', *case[original])) for original, field in FIELD_MAPPING.items()}
        proof = dict(format='authored_a_canonical_compilation_v1', source=dict(commit=SOURCE_COMMIT, path=SOURCE_PATH, sha256=SOURCE_SHA256),
            compiler_sha256=compiler_sha, case_id=case['id'], original_split=case['split'], field_mapping=FIELD_MAPPING,
            geometry=source['geometry'], gauge_policy=source['gauge_policy'], source_timeline=source['timeline'],
            temporal_encoding=TEMPORAL_ENCODING, array_payload_sha256=payload_hashes,
            numerical_transform='none; JSON numeric values packed as little-endian float64 C-order ZYX',
            scope='New canonical QA source; no physical trajectory, independence, training or inference claim')
        proof_raw = encode(proof).encode()
        case_raw = encode(case).encode()
        refs = [dict(field=field['id'], path='arrays/' + field['id'] + '.npy', bytes=len(native[field['id']]),
                     sha256=sha(native[field['id']])) for field in definitions]
        manifest = dict(format='scientific_field_sequence_v1', schema_version=1, grid=copy.deepcopy(source['geometry']),
            time_units='not_applicable', fields=copy.deepcopy(definitions), frames=[dict(time='0', arrays=refs)],
            family=dict(namespace='authored-extension-a-v2-qa', id=case['id']),
            sources=[dict(path='sources/authored-case.json', bytes=len(case_raw), sha256=sha(case_raw), description='Exact case excerpt from the pinned private authored A v2 fixture'),
                     dict(path='sources/compile-receipt.json', bytes=len(proof_raw), sha256=sha(proof_raw), description='Explicit author-side QA compilation and temporal/gauge policy')],
            provenance=dict(producer='Authored scalar A canonical QA compiler v1', source_id='git:' + SOURCE_COMMIT + ':' + SOURCE_PATH + '#' + case['id']))
        members = {'manifest.json': encode(manifest).encode(), **{'arrays/' + key + '.npy': raw for key, raw in native.items()},
                   'sources/authored-case.json': case_raw, 'sources/compile-receipt.json': proof_raw}
        bundles[case['id']] = archive_bytes(members)
        scientific_fields.parse_bundle(bundles[case['id']])
        arrays[case['id']], manifests[case['id']] = native, manifest
    field_evidence.validate_contract(contract)
    return dict(source=source, source_raw=source_raw, compiler_sha256=compiler_sha, contract=contract, bundles=bundles, arrays=arrays, manifests=manifests)


def verify_source_arrays(compilation, releases):
    """Independently bind original case values, explicit policy and real ZIP assets."""
    source = json.loads(compilation['source_raw'])
    if sha(compilation['source_raw']) != SOURCE_SHA256 or compilation['source'] != source:
        raise ValueError('Original pinned authored source changed.')
    contract = compilation['contract']
    field_evidence.validate_contract(contract)
    expected_fields = [dict(field_id=field_id, dtype=source['dtype'], shape_zyx=source['shape_zyx'],
        centering=source['centering'], stage=stage, units=source['field_units'],
        gauge_policy_sha256=field_evidence.digest(source['gauge_policy']))
        for field_id, stage in (('initial', 'input'), ('reference', 'reference_target'))]
    if (contract['inputs'] + [contract['output']] != expected_fields or contract['time_mode'] != 'standalone'
            or contract['source_sha256'] != compilation['compiler_sha256']):
        raise ValueError('Canonical source contract differs from the declared original geometry/gauge/field semantics.')
    expected = {case['id']: case for case in source['cases']}
    seen = set()
    for release_sha, raw in releases.items():
        scientific_release.validate_bytes(raw, release_sha)
        with zipfile.ZipFile(io.BytesIO(raw)) as release:
            frozen = json.loads(release.read('manifest.json'))
            for row in frozen['records']:
                with zipfile.ZipFile(io.BytesIO(release.read(row['asset']))) as bundle:
                    manifest = json.loads(bundle.read('manifest.json'))
                    proof = json.loads(bundle.read('sources/compile-receipt.json'))
                    case_id = proof['case_id']
                    if case_id not in expected or case_id in seen:
                        raise ValueError('Unknown or duplicate original authored case.')
                    seen.add(case_id); case = expected[case_id]
                    if (row['split'] != case['split'] or manifest != compilation['manifests'][case_id]
                            or manifest['grid'] != source['geometry'] or manifest['time_units'] != 'not_applicable'
                            or manifest['family'] != dict(namespace='authored-extension-a-v2-qa', id=case_id)
                            or len(manifest['frames']) != 1 or manifest['frames'][0]['time'] != '0'
                            or json.loads(bundle.read('sources/authored-case.json')) != case
                            or proof['source']['sha256'] != SOURCE_SHA256 or proof['compiler_sha256'] != compilation['compiler_sha256']
                            or proof['geometry'] != source['geometry'] or proof['gauge_policy'] != source['gauge_policy']
                            or proof['temporal_encoding'] != TEMPORAL_ENCODING or proof['source_timeline'] != 'not_applicable'
                            or proof['field_mapping'] != FIELD_MAPPING or proof['original_split'] != case['split']):
                        raise ValueError('Canonical QA source declaration differs from the original authored case.')
                    for original, field_id in FIELD_MAPPING.items():
                        field = next(field for field in manifest['fields'] if field['id'] == field_id)
                        raw_array = bundle.read('arrays/' + field_id + '.npy')
                        payload, shape = scientific_fields.npy_payload(raw_array, field, manifest['grid'])
                        if (shape != [4, 4, 4] or payload != struct.pack('<64d', *case[original])
                                or proof['array_payload_sha256'][field_id] != sha(payload)):
                            raise ValueError('Canonical native array differs bitwise from the authored JSON values.')
    if seen != set(expected):
        raise ValueError('Canonical release membership omits an original authored case.')
    return True


def build_canonical_fixture(dataset, project_root, *, root_name='canonical-fixture', source_raw=None):
    """Import/review/freeze under the caller's ordinary bound owner.

    Dataset must declare project_roots[root_name] == project_root. Returns receipt,
    exact releases/NPY outputs, reviewed records and compilation for driver reuse.
    """
    compilation = compile_authored_a(pinned_source() if source_raw is None else source_raw)
    project_root = Path(project_root)
    project_root.mkdir(parents=True, exist_ok=True)
    project = dict(schema_version=1, id=uuid.uuid4().hex, name='New authored A canonical QA source', data=[], recipes=[], evidence=[], requirements=[])
    for case in compilation['source']['cases']:
        name = case['id'] + '.zip'; raw = compilation['bundles'][case['id']]
        with (project_root / name).open('xb') as output:
            output.write(raw)
        project['data'].append(dict(id=case['id'], label='Canonical QA ' + case['id'], path=name, sha256=sha(raw)))
    with (project_root / 'project.json').open('x') as output:
        output.write(encode(project))
    dataset.projects.open(dict(root=root_name, manifest_path='project.json'))
    records = {}
    for case in compilation['source']['cases']:
        raw = compilation['bundles'][case['id']]
        captured, source = dataset.projects.read_data_reference(project['id'], case['id'], sha(raw), scientific_fields.BUNDLE_LIMIT)
        if captured != raw:
            raise ValueError('Project capture changes the newly compiled source.')
        row = dataset.workbench.scientific.admit(captured, dict(name='Canonical QA ' + case['id'],
            rights='Private authored QA only; no redistribution or physical-validity claim.', groups=[], parents=[]), source)
        records[case['id']] = dataset.workbench.save(row['id'], dict(row, review='human_reviewed',
            annotation={'note': 'Reviewed exact authored A source values and explicit QA coordinate/gauge declaration.'}))
    request = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in records.values()],
                   ratios=dict(train=67, validation=33, test=0), seed=0)
    desired = {records[case['id']]['id']: case['split'] for case in compilation['source']['cases']}
    for seed in range(1000):
        request['seed'] = seed
        preview = dataset.releases.preview(request)
        if preview['eligible'] and preview['assignments'] == desired:
            break
    else:
        raise ValueError('Could not preserve the exact authored train/validation membership through Release allocation.')
    release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
    raw = dataset.releases.locate(release['id']).read_bytes()
    releases = {sha(raw): raw}; outputs, cases = {}, []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frozen_rows = {row['id']: row for row in json.loads(archive.read('manifest.json'))['records']}
    for original in compilation['source']['cases']:
        row = frozen_rows[records[original['id']]['id']]; manifest = compilation['manifests'][original['id']]
        mappings = []
        for expected in compilation['contract']['inputs'] + [compilation['contract']['output']]:
            field_id = expected['field_id']; native = compilation['arrays'][original['id']][field_id]
            payload, _shape = scientific_fields.npy_payload(native, expected, manifest['grid'])
            name = original['id'] + '-' + field_id + '.npy'; outputs[name] = native
            mappings.append(dict(field_id=field_id, source_sha256=sha(native), payload_sha256=sha(payload),
                gauge_policy_sha256=expected['gauge_policy_sha256'], output=blob(name, native)))
        cases.append(dict(id=original['id'], release_sha256=sha(raw), record_id=row['id'], split=row['split'],
            family=manifest['family'], protected_groups=row['groups'], frame=0, time='0', geometry_sha256=field_evidence.digest(manifest['grid']), arrays=mappings))
    derivation = dict(format='field_input_derivation_v1', contract_sha256=field_evidence.digest(compilation['contract']),
        family_scope='selected_records_only', cases=cases, fit_case_ids=compilation['source']['fit_member_ids'])
    field_evidence.validate_derivation(derivation, compilation['contract'], releases, outputs)
    verify_source_arrays(compilation, releases)
    receipt = dict(format='extension_a_canonical_qa_fixture_v1', source_commit=SOURCE_COMMIT, source_path=SOURCE_PATH,
        source_sha256=SOURCE_SHA256, compiler_sha256=compilation['compiler_sha256'], catalog_id=dataset.db.dataset_id,
        project_id=project['id'], release=release, release_sha256=sha(raw), release_bytes=len(raw), split_seed=request['seed'],
        contract=compilation['contract'], gauge_policy=compilation['source']['gauge_policy'], temporal_encoding=TEMPORAL_ENCODING,
        original_mapping=compilation['source']['mapping'], derivation=derivation, native_array_count=len(outputs),
        native_payload_values_bitwise_unchanged=True, actual_workbench_review=True, actual_canonical_release=True,
        e2_canonical_execution=False, limitation='E2 resolver currently rejects frozen Release/Run inputs; no training/inference/physics or E2 canonical acceptance claim.')
    return dict(receipt=receipt, releases=releases, outputs=outputs, records=records, compilation=compilation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    from app import Dataset
    from auth_helpers import ExplicitOwnerFixture
    project_root = args.output / 'source'
    project_root.mkdir()
    dataset = Dataset(args.output / 'catalog', project_roots={'canonical-fixture': project_root})
    owner = ExplicitOwnerFixture.bootstrap(dataset)
    try:
        with owner.bound(dataset):
            result = build_canonical_fixture(dataset, project_root)
        for name, raw in result['outputs'].items():
            (args.output / name).write_bytes(raw)
        (args.output / 'authored-source.json').write_bytes(result['compilation']['source_raw'])
        (args.output / 'frozen-release.zip').write_bytes(next(iter(result['releases'].values())))
        (args.output / 'receipt.json').write_text(json.dumps(result['receipt'], indent=2) + '\n')
        print(json.dumps(result['receipt'], indent=2))
    finally:
        dataset.close()


if __name__ == '__main__':
    main()
