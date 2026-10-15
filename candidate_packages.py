"""Bounded inference packages and explicitly invoked fresh CPU consumers.

Inspection never imports captured source. Packaging/verifying recipes are ordinary
captured recipes: Pipeline/Experiments/Access/Runs retain execution authority.
Only local/private use is supported while any included rights remain unresolved.
"""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

FORMAT = 'inference_package_v1'
MAX_PACKAGE_BYTES = 40 * 1024**2
MAX_EXPANDED_BYTES = 64 * 1024**2
MAX_DOCUMENT_BYTES = 1024**2
MAX_FILES = 128
HASH = re.compile(r'[a-f0-9]{64}\Z')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z')
MANIFEST_FIELDS = {'format', 'candidate', 'checkpoint', 'model', 'sources',
                   'transforms', 'task', 'inference_entry', 'runtime', 'evidence',
                   'lineage', 'probes', 'expected_outputs', 'licenses', 'inventory',
                   'limitations'}
SCALAR_A_CONTRACT_SHA256 = '468e3e15ad5aa88ce3e43deaeb7c5487bd16a77651b8328a618c89e2b78717fe'
SCALAR_A_SOURCE_SHA256 = 'cdfdf92c798538afcbf974e16dd9686b3bac7837f001c300ac422bb9395d98eb'
SCALAR_A_NOTICE_SHA256 = '6d60e9f2a605434edd38842f1b5248953b98b0f002fe3abe94c6688ad77429b6'
SCALAR_A_TASK_FORMAT = 'package_scalar_a_task_v1'
SCALAR_A_ADAPTERS = {
    SCALAR_A_CONTRACT_SHA256: {'revision': 1, 'source_sha256': SCALAR_A_SOURCE_SHA256,
        'recipe_sha256': '90ce14a7bfcb1079f376ca93858ec90d1ebcc11533e54ec476639a44e006a644',
        'runtime_snapshot_sha256': None, 'directory': 'inference-v1'},
    '9588ee2632a90dc647e65b4f2b6289ef78338de29ec3f16480f02f6ea02f7dd8': {
        'revision': 2, 'source_sha256': 'b77face4f2e51345a565216fc5139271aa02bd17577ac099706393b3149acc2c',
        'recipe_sha256': '4cebb6b2083e48e32234f7ba9f29ca6c7684c51d8d90ed028e37535c9d233508',
        'runtime_snapshot_sha256': '50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d',
        'directory': 'inference-v2-private-qa'}}


class PackageError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = self.outcome = code


def require(condition, message, code='invalid'):
    if not condition:
        raise PackageError(code, message)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    require(len(raw) <= MAX_DOCUMENT_BYTES, 'Package JSON exceeds its bound.')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate package JSON field.')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False, 'Nonfinite package JSON.'))
        pending = [(value, 0)]; visited = 0
        while pending:
            node, depth = pending.pop(); visited += 1
            require(depth <= 64 and visited <= 100000, 'Package JSON exceeds structural bounds.')
            if type(node) is float:
                require(math.isfinite(node), 'Nonfinite package JSON.')
            elif type(node) is dict:
                pending.extend((item, depth + 1) for item in node.values())
            elif type(node) is list:
                pending.extend((item, depth + 1) for item in node)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, PackageError):
            raise
        raise PackageError('invalid', 'Package JSON cannot be decoded.') from error


def closed(value, fields):
    require(type(value) is dict and set(value) == set(fields), 'Package fields differ from the declared contract.')


def blob(name, raw, media_type='application/json'):
    require(type(name) is str and NAME.fullmatch(name) is not None, 'Package filename must be flat and bounded.')
    return {'name': name, 'sha256': sha(raw), 'bytes': len(raw), 'media_type': media_type}


def check_blob(item):
    closed(item, ('name', 'sha256', 'bytes', 'media_type'))
    require(type(item['name']) is str and NAME.fullmatch(item['name']) is not None and item['name'] != 'manifest.json',
            'Unsafe or reserved package filename.')
    require(type(item['sha256']) is str and HASH.fullmatch(item['sha256']) is not None,
            'Package blob requires its exact SHA256.')
    require(type(item['bytes']) is int and 0 <= item['bytes'] <= MAX_PACKAGE_BYTES,
            'Package blob exceeds its byte bound.')
    require(type(item['media_type']) is str and 1 <= len(item['media_type']) <= 100,
            'Package media type is invalid.')


def archive_files(raw):
    """Validate ZIP metadata before decompressing; never use extractall."""
    require(type(raw) is bytes and len(raw) <= MAX_PACKAGE_BYTES, 'Package exceeds its whole byte bound.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            require(1 <= len(infos) <= MAX_FILES and len({x.filename for x in infos}) == len(infos),
                    'Duplicate or excessive package files.')
            require(sum(x.file_size for x in infos) <= MAX_EXPANDED_BYTES, 'Package expanded size exceeds bound.')
            for item in infos:
                mode = item.external_attr >> 16
                require(NAME.fullmatch(item.filename) is not None and not item.is_dir()
                        and not item.flag_bits & 1 and stat.S_IFMT(mode) in (0, stat.S_IFREG),
                        'Unsafe package ZIP entry.')
            return {item.filename: archive.read(item) for item in infos}
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise PackageError('invalid', 'Package archive cannot be decoded.') from error


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            require(NAME.fullmatch(name) is not None, 'Unsafe package ZIP name.')
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o400) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    result = buffer.getvalue()
    require(len(result) <= MAX_PACKAGE_BYTES, 'Package archive exceeds its byte bound.')
    return result


def validate_manifest(manifest, files, *, distribution='local_private'):
    """Prove byte closure without importing source or loading model weights."""
    closed(manifest, MANIFEST_FIELDS)
    require(manifest['format'] == FORMAT, 'Unsupported inference package format.', 'unsupported')
    require(distribution in ('local_private', 'redistribution'), 'Unknown requested distribution mode.')
    candidate = manifest['candidate']
    closed(candidate, ('kind', 'catalog_id', 'id', 'sha256'))
    require(type(candidate) is dict and candidate.get('kind') == 'candidate'
            and type(candidate.get('sha256')) is str and HASH.fullmatch(candidate['sha256']) is not None
            and type(candidate.get('id')) is str and re.fullmatch('[a-f0-9]{32}', candidate['id']) is not None
            and type(candidate.get('catalog_id')) is str and re.fullmatch('[a-f0-9]{32}', candidate['catalog_id']) is not None,
            'Package requires an exact immutable candidate reference.')
    inventory = manifest['inventory']
    require(type(inventory) is list and 1 <= len(inventory) < MAX_FILES, 'Package inventory exceeds bound.')
    indexed = {}
    for item in inventory:
        check_blob(item)
        require(item['name'] not in indexed, 'Duplicate package inventory blob.')
        raw = files.get(item['name'])
        require(type(raw) is bytes and len(raw) == item['bytes'] and sha(raw) == item['sha256'],
                'Missing or changed package blob: ' + item['name'])
        indexed[item['name']] = item
    require(set(files) == set(indexed) | {'manifest.json'}, 'Package contains undeclared or missing files.')
    require(sum(map(len, files.values())) <= MAX_EXPANDED_BYTES, 'Expanded package exceeds bound.')
    require('candidate-decision.json' in indexed, 'Immutable candidate decision bytes are required.')
    decision = decode(files['candidate-decision.json'])
    closed(decision, ('format', 'id', 'study_id', 'trial_id', 'run_id', 'checkpoint_sha256', 'evaluation_sha256', 'policy', 'decision', 'limitations'))
    require(decision.get('format') == 'candidate_v1' and decision.get('id') == candidate['id']
            and sha(encoded(decision)) == candidate['sha256'], 'Candidate decision identity differs.')
    referenced = set()
    def ref(item):
        check_blob(item)
        require(indexed.get(item['name']) == item, 'Dependency differs from package inventory.')
        referenced.add(item['name'])
    for name in ('checkpoint', 'model', 'task', 'inference_entry', 'lineage'):
        ref(manifest[name])
    for name in ('sources', 'transforms', 'evidence', 'licenses'):
        require(type(manifest[name]) is list and 1 <= len(manifest[name]) <= MAX_FILES, 'Required package closure is empty.')
        for item in manifest[name]:
            ref(item)
    closed(manifest['runtime'], ('contract', 'provision'))
    require(manifest['runtime']['provision'] == 'external', 'Only explicit external CPU runtime is supported.', 'unsupported')
    ref(manifest['runtime']['contract'])
    runtime = decode(files[manifest['runtime']['contract']['name']])
    closed(runtime, ('format', 'snapshot'))
    require(runtime['format'] == 'package_runtime_v1', 'Unsupported package runtime contract.', 'unsupported')
    snapshot = runtime['snapshot']
    closed(snapshot, ('schema_version', 'profile', 'catalog_id', 'root', 'manifest_sha256', 'manifest_bytes', 'file_count', 'total_bytes', 'python_version', 'packages', 'launch'))
    require(type(snapshot['schema_version']) is int and snapshot['schema_version'] == 1
            and snapshot['profile'] == 'captured_cpu_python_v1' and snapshot['python_version'] == '3.12'
            and type(snapshot['manifest_sha256']) is str and HASH.fullmatch(snapshot['manifest_sha256']) is not None,
            'Unsupported captured runtime identity.', 'unsupported')
    for name in ('probes', 'expected_outputs'):
        if manifest[name] is not None:
            ref(manifest[name])
    require((manifest['probes'] is None) == (manifest['expected_outputs'] is None), 'Probes and expected outputs must be paired.')
    require(type(manifest['limitations']) is list and len(manifest['limitations']) <= 32
            and all(type(x) is str and 0 < len(x) <= 500 for x in manifest['limitations']), 'Invalid package limitations.')
    # Lineage lists only identities. No training/test records or files are inferred safe.
    lineage = decode(files[manifest['lineage']['name']])
    closed(lineage, ('format', 'sources', 'data_policy'))
    require(lineage['format'] == 'package_lineage_v1' and lineage['data_policy'] == 'references_only',
            'Private training data must remain permissioned lineage references.')
    require(type(lineage['sources']) is list and len(lineage['sources']) <= MAX_FILES, 'Lineage exceeds bound.')
    for source in lineage['sources']:
        closed(source, ('run_id', 'artifact_name', 'sha256', 'population'))
        require(type(source['run_id']) is str and re.fullmatch('[a-f0-9]{32}', source['run_id']) is not None
                and type(source['artifact_name']) is str and NAME.fullmatch(source['artifact_name']) is not None
                and type(source['sha256']) is str and HASH.fullmatch(source['sha256']) is not None,
                'Invalid package source identity.')
        require(source['population'] in ('train', 'validation', 'test', 'unknown'), 'Invalid source population.')
        require(source['population'] in ('train', 'validation'),
                'Protected or unknown populations cannot be exported by this package profile.', 'unsupported')
    # Every material has a disposition, including code and weights with unknown rights.
    rights = {}
    for item in manifest['licenses']:
        notice = decode(files[item['name']])
        closed(notice, ('format', 'materials', 'authority', 'terms', 'redistribution'))
        require(notice['format'] == 'package_rights_v1' and type(notice['materials']) is list
                and notice['materials'] and len(notice['materials']) <= MAX_FILES, 'Invalid rights inventory.')
        require(notice['redistribution'] in ('unknown', 'denied', 'permitted'), 'Invalid rights decision.')
        require(notice['authority'] is None or type(notice['authority']) is str, 'Invalid rights authority.')
        require(notice['terms'] is None or type(notice['terms']) is str, 'Invalid authoritative terms.')
        if notice['redistribution'] == 'permitted':
            require(bool(notice['authority']) and bool(notice['terms']), 'Permitted redistribution needs authoritative terms.')
        for name in notice['materials']:
            require(name in indexed and name not in rights, 'Unknown or duplicate rights material.')
            rights[name] = notice['redistribution']
    exempt = {x['name'] for x in manifest['licenses']}
    require(set(rights) == set(indexed) - exempt, 'Every included material requires a rights disposition.')
    if distribution == 'redistribution':
        require(all(x == 'permitted' for x in rights.values()),
                'Unresolved or denied material rights prevent redistribution.', 'unsupported')
    descriptor = decode(files[manifest['checkpoint']['name']])
    closed(descriptor, ('format', 'run_id', 'model_sha256', 'weights', 'fitted_transform_sha256', 'clocks'))
    require(descriptor.get('format') == 'checkpoint_state_v1', 'Unsupported checkpoint contract.', 'unsupported')
    ref(descriptor['weights'])
    task = decode(files[manifest['task']['name']])
    require(type(task) is dict and task.get('format') in ('package_classifier_task_v1', SCALAR_A_TASK_FORMAT),
            'Unqualified package task profile.', 'unsupported')
    evaluation_name = 'model-evidence.json' if type(task) is dict and task.get('format') == SCALAR_A_TASK_FORMAT else 'metrics.json'
    require(decision.get('run_id') == descriptor.get('run_id')
            and decision.get('checkpoint_sha256') == manifest['checkpoint']['sha256']
            and evaluation_name in indexed and decision.get('evaluation_sha256') == indexed[evaluation_name]['sha256'],
            'Selected candidate Run/checkpoint/evaluation differs from package closure.')
    require('published-model-material.json' in indexed, 'Published model material bytes are required.')
    published = decode(files['published-model-material.json'])
    require(type(published) is dict and published.get('catalog_id') == candidate['catalog_id']
            and snapshot['catalog_id'] == candidate['catalog_id'], 'Published model/runtime catalog differs from candidate.')
    require(published.get('format') == 'model_material_v1' and sha(encoded(published)) == descriptor.get('model_sha256'),
            'Published model identity differs from checkpoint.')
    source_by_path = {item['name']: item for item in manifest['sources']}
    for source in published.get('source_closure', []):
        require(type(source) is dict and set(source) == {'import_path', 'blob'}, 'Invalid published import closure.')
        retained = source['blob']; captured = source_by_path.get(source['import_path'])
        require(captured is not None and captured['sha256'] == retained.get('sha256') and captured['bytes'] == retained.get('bytes'),
                'Captured inference source differs from published model material.')
    require(bool(published.get('source_closure')), 'Published source import closure is empty.')
    model_definition = decode(files[manifest['model']['name']])
    for key in ('specification', 'preprocessing_policy', 'output_policy'):
        name = 'published-' + key + '.json'
        require(name in indexed and published[key]['sha256'] == indexed[name]['sha256']
                and published[key]['bytes'] == indexed[name]['bytes']
                and decode(files[name]) == model_definition[key], 'Published model policy/shape differs from inference definition.')
    require(len(manifest['transforms']) == 2 and decode(files[manifest['transforms'][0]['name']]) == model_definition['preprocessing_policy']
            and manifest['transforms'][1]['sha256'] == descriptor['fitted_transform_sha256'], 'Declared transforms differ from published/checkpoint policies.')
    for source in lineage['sources']:
        if source['artifact_name'] in indexed:
            require(source['sha256'] == indexed[source['artifact_name']]['sha256']
                    and source['run_id'] == descriptor['run_id'], 'Included source artifact differs from retained lineage.')
    if type(task) is dict and task.get('format') == SCALAR_A_TASK_FORMAT:
        _validate_scalar_a(manifest, files, task, descriptor, published, ref)
        require(referenced | exempt == set(indexed), 'Unreferenced package content is not permitted.')
        return manifest
    metrics = decode(files['metrics.json'])
    require(task.get('class_vocabulary') == metrics.get('class_vocabulary') and task.get('class_to_idx') == metrics.get('class_to_idx'), 'Declared class order differs from selected evaluation.')
    # Auxiliary probe images must be named explicitly by the probe document.
    if manifest['probes'] is not None:
        probes = decode(files[manifest['probes']['name']])
        closed(probes, ('format', 'rows'))
        require(probes['format'] == 'package_image_probes_v1' and type(probes['rows']) is list
                and 1 <= len(probes['rows']) <= 128, 'Invalid fixed probes.')
        ids = set()
        for row in probes['rows']:
            closed(row, ('id', 'image'))
            require(type(row['id']) is str and row['id'] not in ids, 'Duplicate or invalid probe identity.')
            ids.add(row['id']); ref(row['image'])
    if manifest['expected_outputs'] is not None:
        expected = decode(files[manifest['expected_outputs']['name']])
        closed(expected, ('run_id', 'checkpoint_sha256', 'probe_sha256', 'rows'))
        require('probe.json' in indexed, 'Fixed probe contract is missing.')
        probe = decode(files['probe.json'])
        require(type(probe) is dict and probe.get('format') == 'probe_v1' and probe.get('split') == 'validation'
                and expected['run_id'] == descriptor['run_id'] and expected['checkpoint_sha256'] == manifest['checkpoint']['sha256']
                and expected['probe_sha256'] == indexed['probe.json']['sha256'], 'Expected fixed probe/checkpoint binding differs.')
        members = probe.get('members'); rows = expected['rows']; count = len(task['class_vocabulary'])
        require(type(members) is list and type(rows) is list and len(members) == len(rows) == len(probes['rows']) <= 128,
                'Fixed probe output membership differs.')
        for ordinal, (member, row, image) in enumerate(zip(members, rows, probes['rows'], strict=True)):
            closed(row, ('ordinal', 'truth_index', 'predicted_index', 'probabilities'))
            require(type(member) is dict and type(member.get('ordinal')) is int and member['ordinal'] == ordinal
                    and type(row['ordinal']) is int and row['ordinal'] == ordinal
                    and type(row['truth_index']) is int and 0 <= row['truth_index'] < count
                    and type(row['predicted_index']) is int and 0 <= row['predicted_index'] < count
                    and member.get('target_sha256') == sha(encoded(row['truth_index']))
                    and type(member.get('frozen_reference')) is dict and member['frozen_reference'].get('id') == image['id']
                    and member.get('input_sha256') == image['image']['sha256'], 'Fixed probe input/target/index binding differs.')
            scores = row['probabilities']
            require(type(scores) is list and len(scores) == count
                    and all(type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value) for value in scores)
                    and abs(sum(scores) - 1) <= 1e-4 and scores.index(max(scores)) == row['predicted_index'],
                    'Invalid fixed probe probabilities/predicted class.')
    require(referenced | exempt == set(indexed), 'Unreferenced package content is not permitted.')
    return manifest


def _scalar_npy(raw, shape):
    """Bounded native data decoding only; model arithmetic belongs to the author."""
    require(type(raw) is bytes and 10 <= len(raw) <= 8192 and raw[:6] == b'\x93NUMPY'
            and raw[6:8] in (b'\x01\x00', b'\x02\x00'), 'Invalid scalar A native array.')
    start = 10 if raw[6:8] == b'\x01\x00' else 12
    end = start + int.from_bytes(raw[8:start], 'little')
    require(start < end <= min(len(raw), start + 4096) and end % 16 == 0 and raw[end-1:end] == b'\n', 'Invalid native array header bound.')
    try:
        tree = ast.parse(raw[start:end].decode('ascii').strip(), mode='eval')
        nodes = list(ast.walk(tree))
        require(len(nodes) <= 64 and type(tree.body) is ast.Dict
                and all(type(node) in (ast.Expression, ast.Dict, ast.Tuple, ast.Constant, ast.Load) for node in nodes), 'Invalid native literal header.')
        keys = [node.value for node in tree.body.keys if type(node) is ast.Constant and type(node.value) is str]
        require(len(keys) == len(tree.body.keys) == len(set(keys)), 'Duplicate native header keys.')
        header = ast.literal_eval(tree)
    except (SyntaxError, ValueError, UnicodeError, TypeError, RecursionError) as error:
        if isinstance(error, PackageError):
            raise
        raise PackageError('invalid', 'Invalid scalar A native header.') from error
    require(type(header) is dict and set(header) == {'descr', 'fortran_order', 'shape'}
            and header['descr'] == '<f8' and header['fortran_order'] is False
            and type(header['shape']) is tuple and all(type(n) is int for n in header['shape'])
            and header['shape'] == tuple(shape), 'Scalar A dtype/order/shape differs.')
    count = math.prod(shape)
    require(len(raw) == end + 8 * count, 'Scalar A native payload length differs.')
    values = struct.unpack('<' + str(count) + 'd', raw[end:])
    require(all(math.isfinite(value) for value in values), 'Nonfinite scalar A native payload.')
    return raw[end:], values


def _validate_scalar_a(manifest, files, task, descriptor, published, ref):
    try:
        return _validate_scalar_a_body(manifest, files, task, descriptor, published, ref)
    except PackageError:
        raise
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, RecursionError):
        raise PackageError('invalid', 'Malformed scalar A package contract.') from None


def _validate_scalar_a_body(manifest, files, task, descriptor, published, ref):
    """One frozen task-owned profile; never import its captured executable here."""
    closed(task, ('format', 'contract', 'context', 'probe', 'field_index', 'profile'))
    for key in ('contract', 'context', 'probe', 'field_index', 'profile'):
        ref(task[key])
    nomination = SCALAR_A_ADAPTERS.get(task['contract']['sha256'])
    require(nomination is not None and task['contract']['name'] == 'inference-contract.json'
            and sha(files.get('infer.py', b'')) == nomination['source_sha256']
            and sha(files.get('inference-NOTICE.txt', b'')) == SCALAR_A_NOTICE_SHA256,
            'Unqualified scalar A inference entry/contract/notice.', 'unsupported')
    contract = decode(files['inference-contract.json']); policy = contract['policy']
    require(contract['adapter'] == {'id': 'example.scalar-a:inference', 'revision': nomination['revision']}
            and contract['source_authority']['recipe_sha256'] == nomination['recipe_sha256'], 'Scalar A nomination identity differs.', 'unsupported')
    if nomination['runtime_snapshot_sha256'] is not None:
        require(decode(files[manifest['runtime']['contract']['name']])['snapshot']['manifest_sha256'] == nomination['runtime_snapshot_sha256'],
                'Scalar A private QA nomination requires its exact selected captured runtime.', 'unsupported')
    context = decode(files[task['context']['name']]); static = context['static']; authored = static['policy']
    require(encoded(decode(files['recipe.json'])['model_evidence']) == encoded(authored),
            'Scalar A admitted policy differs from its captured recipe definition.')
    require(context['format'] == 'extension_evidence_context_v1' and context['run_id'] == descriptor['run_id']
            and static['catalog_id'] == manifest['candidate']['catalog_id']
            and static['model']['sha256'] == descriptor['model_sha256']
            and static['model']['catalog_id'] == static['catalog_id'], 'Scalar A selected context differs.')
    evidence = decode(files['model-evidence.json'])
    require(evidence['format'] == 'model_evidence_v1' and type(evidence['schema_version']) is int and evidence['schema_version'] == 1
            and evidence['producer']['run_id'] == descriptor['run_id']
            and evidence['producer']['catalog_id'] == static['catalog_id']
            and evidence['producer']['material_sha256'] == context['composition']['sha256']
            and evidence['model_sha256'] == descriptor['model_sha256'] and evidence['task'] == static['task']
            and evidence['profile_sha256'] == sha(encoded(static['profile'])), 'Scalar A retained evaluation context differs.')
    for item in (evidence['probe'], evidence['checkpoints'], evidence['metric_definitions'], evidence['field_index'],
                 *evidence['observations'], *evidence['inference']['fitted_transforms']):
        ref(item)
    require(evidence['probe'] == task['probe'] and evidence['field_index'] == task['field_index']
            and evidence['inference']['fitted_transforms'] == [manifest['transforms'][1]]
            and evidence['inference']['output_policy_sha256'] == sha(encoded(policy['output_policy'])),
            'Scalar A evaluation probe/field/transform policy differs.')
    index = decode(files[evidence['checkpoints']['name']])
    require(index['format'] == 'checkpoint_index_v1' and index['run_id'] == descriptor['run_id']
            and type(index['entries']) is list and len(index['entries']) == 4, 'Scalar A checkpoint cadence differs.')
    for point, entry in zip((16, 32, 48, 64), index['entries'], strict=True):
        ref(entry['checkpoint']); checkpoint = decode(files[entry['checkpoint']['name']]); ref(checkpoint['weights'])
        require(type(entry['clocks']['optimizer_update']) is int and entry['clocks']['optimizer_update'] == point
                and checkpoint['clocks'] == entry['clocks'] and checkpoint['model_sha256'] == descriptor['model_sha256']
                and checkpoint['run_id'] == descriptor['run_id'] and entry['model_sha256'] == descriptor['model_sha256']
                and checkpoint['fitted_transform_sha256'] == entry['fitted_transform_sha256'] == descriptor['fitted_transform_sha256'],
                'Scalar A checkpoint descriptor/index/model binding differs.')
    require(sum(entry['checkpoint'] == manifest['checkpoint'] for entry in index['entries']) == 1,
            'Scalar A candidate checkpoint is absent from retained evaluation index.')
    for key in ('task', 'profile'):
        actual = static['task'] if key == 'task' else static['profile']['definition']
        expected = policy[key]
        require(actual['id'] == expected['id'] and type(actual['revision']) is int and actual['revision'] == expected['revision']
                and actual['sha256'] == expected['definition_sha256'], 'Scalar A task/profile definition differs.', 'unsupported')
    require(encoded(authored['model_specification']) == encoded(policy['model_specification'])
            and encoded(authored['preprocessing_policy']) == encoded(policy['preprocessing_policy'])
            and encoded(authored['output_policy']) == encoded(policy['output_policy'])
            and encoded(authored['fields']) == encoded([{'id': policy['field_id'], 'contract': policy['field_contract'],
                'geometry': policy['geometry'], 'gauge_policy': policy['gauge_policy']}]),
            'Scalar A field/model/preprocessing/geometry/gauge policy differs.', 'unsupported')
    require(decode(files[task['profile']['name']]) == static['profile'], 'Scalar A retained profile differs.')
    require(published['task'] == static['task'], 'Scalar A published task differs.')
    source_map = {item['import_path']: item['blob'] for item in published['source_closure']}
    require(set(source_map) == {'producer.py', 'evidence_writer.py', 'task.json', 'extension.json', 'NOTICE.txt', 'recipe.json'},
            'Scalar A requires its five published training sources and owner-captured recipe definition.')
    require({item['path']: item['sha256'] for item in decode(files['recipe.json'])['sources']}
            == {name: item['sha256'] for name, item in source_map.items() if name != 'recipe.json'},
            'Scalar A captured recipe/source/notice inventory differs.')
    for path, key in (('producer.py', 'producer_sha256'), ('evidence_writer.py', 'evidence_writer_sha256'),
                      ('task.json', 'task_sha256'), ('extension.json', 'extension_sha256'), ('recipe.json', 'recipe_sha256')):
        require(source_map[path]['sha256'] == contract['source_authority'][key], 'Scalar A published source authority differs.', 'unsupported')
    fitted = decode(files[manifest['transforms'][1]['name']])
    closed(fitted, ('format', 'fit_scope', 'fit_members', 'state'))
    require(fitted['format'] == 'fitted_transform_v1' and fitted['fit_scope'] == 'train'
            and fitted['fit_members'] == authored['fit_members'], 'Scalar A training transform lineage differs.')
    ref(fitted['state'])
    _scalar_npy(files[descriptor['weights']['name']], (2,))
    _payload, statistics = _scalar_npy(files[fitted['state']['name']], (2,))
    require(statistics[1] > 0, 'Scalar A training standard deviation must be positive.')
    probe = decode(files[task['probe']['name']])
    require(probe == static['probe'] and probe['format'] == 'probe_v1' and probe['split'] == 'validation'
            and type(probe['members']) is list and len(probe['members']) == 1, 'Scalar A fixed validation probe differs.', 'unsupported')
    require(type(descriptor['clocks']['optimizer_update']) is int and descriptor['clocks']['optimizer_update'] in (16, 32, 48, 64)
            and descriptor['clocks']['epoch'] is None and descriptor['clocks']['physical_time'] is None,
            'Scalar A checkpoint clock differs.', 'unsupported')
    groups = decode(files[task['field_index']['name']])
    require(type(groups) is list and len(groups) == 4, 'Scalar A retained field cadence differs.')
    checkpoint_ids = {entry['checkpoint']['sha256'] for entry in index['entries']}
    require({group['checkpoint_sha256'] for group in groups} == checkpoint_ids, 'Scalar A field checkpoint membership differs.')
    for group in groups:
        require(group['run_id'] == descriptor['run_id'] and group['probe_sha256'] == task['probe']['sha256']
                and type(group['cases']) is list and len(group['cases']) == 1, 'Scalar A field evidence membership differs.')
        row = group['cases'][0]
        for item in (row['predicted'], row['reference']):
            ref(item); _scalar_npy(files[item['name']], (4, 4, 4))
        require(type(row['member_ordinal']) is int and row['member_ordinal'] == 0 and row['mask'] is None
                and row['geometry_sha256'] == sha(encoded(policy['geometry']))
                and row['gauge_policy_sha256'] == policy['field_contract']['output']['gauge_policy_sha256'],
                'Scalar A retained field geometry/gauge differs.')
    selected = [group for group in groups if group['checkpoint_sha256'] == manifest['checkpoint']['sha256']]
    require(len(selected) == 1, 'Selected scalar A field group is unavailable.')
    group = selected[0]
    require(group['run_id'] == descriptor['run_id'] and group['probe_sha256'] == task['probe']['sha256']
            and len(group['cases']) == 1, 'Scalar A field context differs.')
    case = group['cases'][0]; member = probe['members'][0]
    require(type(case['member_ordinal']) is int and case['member_ordinal'] == member['ordinal'] == 0
            and case['geometry_sha256'] == sha(encoded(policy['geometry'])) and case['time_units'] == 'not_applicable'
            and case['gauge_policy_sha256'] == policy['field_contract']['output']['gauge_policy_sha256']
            and case['mask'] is None, 'Scalar A field member/geometry/gauge differs.')
    binding = [row for row in authored['field_outputs'] if row['clock'] == descriptor['clocks']['optimizer_update']
               and row['field_id'] == 'raw' and row['member_id'] == member['frozen_reference']['member_id']]
    require(len(binding) == 1 and case['predicted']['name'] == binding[0]['prediction']
            and case['reference']['name'] == binding[0]['reference'], 'Scalar A selected output/clock binding differs.')
    inputs = decode(files[manifest['probes']['name']]); expected = decode(files[manifest['expected_outputs']['name']])
    closed(inputs, ('format', 'rows')); closed(expected, ('format', 'run_id', 'checkpoint_sha256', 'probe_sha256', 'rows'))
    require(inputs['format'] == 'package_scalar_a_probes_v1' and type(inputs['rows']) is list and len(inputs['rows']) == 1
            and expected['format'] == 'package_scalar_a_expected_v1' and expected['run_id'] == descriptor['run_id']
            and expected['checkpoint_sha256'] == manifest['checkpoint']['sha256'] and expected['probe_sha256'] == task['probe']['sha256']
            and type(expected['rows']) is list and len(expected['rows']) == 1, 'Scalar A fixed inference membership differs.')
    initial = inputs['rows'][0]; target = expected['rows'][0]
    closed(initial, ('ordinal', 'input')); closed(target, ('ordinal', 'prediction', 'reference'))
    require(type(initial['ordinal']) is int and type(target['ordinal']) is int and initial['ordinal'] == target['ordinal'] == 0,
            'Scalar A fixed inference ordinal differs.')
    for item in (initial['input'], target['prediction'], target['reference']):
        ref(item)
    require(target['prediction'] == case['predicted'] and target['reference'] == case['reference'], 'Scalar A expected field bytes differ from retained selected field.')
    binding = authored['probe_inputs'][0]
    require(binding['member_id'] == member['frozen_reference']['member_id'] and binding['fields'] == [{'field_id': 'initial', 'artifact': initial['input']['name']}],
            'Scalar A probe input source differs.')
    native, _ = _scalar_npy(files[initial['input']['name']], (4, 4, 4))
    require(sha(encoded([{'field_id': 'initial', 'payload_sha256': sha(native)}])) == member['input_sha256'],
            'Scalar A raw-file input does not match admitted native field payload.')
    native, _ = _scalar_npy(files[target['reference']['name']], (4, 4, 4))
    require(sha(native) == member['target_sha256'], 'Scalar A reference differs from fixed probe target.')
    _scalar_npy(files[target['prediction']['name']], (4, 4, 4))


def _infer_scalar_a(manifest, files, package_sha256, snapshot_sha256):
    """Execute the exact frozen author adapter after normal admitted runtime checks."""
    require(manifest['inference_entry']['sha256'] == sha(Path(__file__).read_bytes()), 'Consumer implementation differs.')
    contract = decode(files['inference-contract.json'])
    nomination = SCALAR_A_ADAPTERS[sha(files['inference-contract.json'])]
    descriptor = decode(files[manifest['checkpoint']['name']]); fitted = decode(files[manifest['transforms'][1]['name']])
    initial = decode(files[manifest['probes']['name']])['rows'][0]['input']
    expected = decode(files[manifest['expected_outputs']['name']])['rows'][0]
    request = {'format': 'scalar_affine_inference_request_v1', 'policy': contract['policy'],
        'sha256': {'initial': initial['sha256'], 'weights': descriptor['weights']['sha256'], 'transform': fitted['state']['sha256']}}
    with tempfile.TemporaryDirectory(prefix='tuldok-scalar-a-consumer-') as directory:
        root = Path(directory)
        (root / 'infer.py').write_bytes(files['infer.py']); (root / 'NOTICE.txt').write_bytes(files['inference-NOTICE.txt'])
        spec = importlib.util.spec_from_file_location('captured_scalar_a_inference_v1', root / 'infer.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        try:
            module.validate_contract(contract)
            output = module.predict(files[initial['name']], files[descriptor['weights']['name']], files[fitted['state']['name']], request)
        except ValueError as error:
            raise PackageError('invalid', 'Captured scalar A adapter refused its selected inputs: ' + str(error)) from None
    _, values = _scalar_npy(output, (4, 4, 4)); _, targets = _scalar_npy(files[expected['prediction']['name']], (4, 4, 4))
    tolerance = contract['reconstruction']
    require(all(abs(x-y) <= tolerance['absolute_tolerance'] + tolerance['relative_tolerance'] * abs(y)
                for x, y in zip(values, targets, strict=True)), 'Fresh scalar A inference differs from frozen evaluator tolerance.')
    return {'format': 'fresh_field_inference_verification_v1', 'package_sha256': package_sha256,
        'candidate': manifest['candidate'], 'checkpoint_sha256': manifest['checkpoint']['sha256'],
        'weights_sha256': descriptor['weights']['sha256'], 'runtime_snapshot_sha256': snapshot_sha256,
        'consumer_sha256': manifest['inference_entry']['sha256'], 'adapter_sha256': nomination['source_sha256'],
        'adapter_revision': nomination['revision'], 'contract_sha256': sha(files['inference-contract.json']),
        'expected_outputs_sha256': manifest['expected_outputs']['sha256'],
        'probes_sha256': manifest['probes']['sha256'], 'verified': True, 'numerical_acceptance': 'not_evaluated',
        'implementation': 'captured_author_adapter_v1', 'reconstruction': tolerance,
        'outputs': [{'ordinal': 0, 'field_id': 'raw', **{key: contract['policy']['field_contract']['output'][key]
            for key in ('dtype', 'shape_zyx', 'stage', 'units', 'gauge_policy_sha256')},
            'sha256': sha(output), 'values_c_order': list(values),
            'max_absolute_difference': max(abs(x-y) for x, y in zip(values, targets, strict=True))}]}


def inspect_package(raw, expected_sha256, *, distribution='local_private'):
    require(type(expected_sha256) is str and HASH.fullmatch(expected_sha256) is not None
            and sha(raw) == expected_sha256, 'Downloaded whole package SHA256 differs.')
    files = archive_files(raw)
    require('manifest.json' in files, 'Package manifest is missing.')
    manifest = decode(files['manifest.json'])
    return validate_manifest(manifest, files, distribution=distribution), files


def create_package(manifest, blobs, *, authorize=None):
    """Called in an admitted captured worker, after exact input capture."""
    require(type(blobs) is dict and all(type(x) is bytes for x in blobs.values()), 'Package blobs must be exact bytes.')
    files = dict(blobs, **{'manifest.json': encoded(manifest)})
    validate_manifest(manifest, files)
    if authorize is not None:
        # Server-only convenience: all retained dependencies, never candidate alone.
        for item in manifest['inventory']:
            authorize(item)
        for source in decode(files[manifest['lineage']['name']])['sources']:
            authorize(source)
    return _zip(files)


def runtime_contract(descriptor):
    """Reuse the approved RuntimeSnapshot owner and its full file/license closure."""
    import recipe_process
    descriptor = recipe_process.validate_cpu_snapshot_descriptor(descriptor)
    recipe_process.verify_cpu_snapshot(descriptor)
    return {'format': 'package_runtime_v1', 'snapshot': descriptor}


def _captured_runtime_helper(files):
    require('recipe_process.py' in files, 'Captured runtime verifier source is missing.')
    with tempfile.TemporaryDirectory(prefix='tuldok-runtime-reader-') as directory:
        path = Path(directory) / 'recipe_process.py'; path.write_bytes(files['recipe_process.py'])
        spec = importlib.util.spec_from_file_location('captured_runtime_reader', path)
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    return helper


def check_runtime(value, snapshot_sha256, files):
    closed(value, ('format', 'snapshot'))
    require(value['format'] == 'package_runtime_v1', 'Unsupported package runtime.', 'unsupported')
    helper = _captured_runtime_helper(files)
    descriptor = helper.validate_cpu_snapshot_descriptor(value['snapshot'])
    require(descriptor['manifest_sha256'] == snapshot_sha256, 'Selected runtime snapshot differs.', 'unsupported')
    helper.verify_cpu_snapshot(descriptor)
    require(Path(sys.executable) == Path(descriptor['root']) / descriptor['launch']['python'],
            'Consumer must execute in the explicitly approved captured runtime.', 'unsupported')
    return descriptor


def infer_package(raw, expected_sha256, snapshot_sha256):
    """Execute only after the owner authorizes this separate consumer attempt."""
    manifest, files = inspect_package(raw, expected_sha256)
    require(manifest['probes'] is not None, 'Fixed probes are unavailable; verification remains pending.', 'unavailable')
    check_runtime(decode(files[manifest['runtime']['contract']['name']]), snapshot_sha256, files)
    descriptor = decode(files[manifest['checkpoint']['name']])
    weights = descriptor['weights']
    task = decode(files[manifest['task']['name']])
    definition = decode(files[manifest['model']['name']])
    if type(task) is dict and task.get('format') == SCALAR_A_TASK_FORMAT:
        return _infer_scalar_a(manifest, files, expected_sha256, snapshot_sha256)
    require(descriptor.get('format') == 'checkpoint_state_v1' and definition.get('format') == 'tinycnn_definition_v2'
            and task.get('format') == 'package_classifier_task_v1', 'This consumer supports TinyCNN v2 only.', 'unsupported')
    require(task.get('input') == {'dtype': 'uint8', 'shape': ['height', 'width', 3], 'units': 'rgb_0_255'}
            and task.get('output') == {'dtype': 'float32', 'shape': ['batch', 'classes'], 'units': 'probabilities'}
            and task.get('stage') == 'inference' and task.get('gauge') == 'none', 'Input/output/stage/gauge differs.')
    model_spec = {key: definition['specification'][key] for key in ('widths', 'input_size', 'head')}
    transforms = [decode(files[x['name']]) for x in manifest['transforms']]
    require(transforms == [definition['preprocessing_policy'], {'format': 'fitted_transform_v1', 'fit_scope': 'none', 'statistics': []}]
            and manifest['transforms'][1]['sha256'] == descriptor['fitted_transform_sha256'], 'Transform closure differs from checkpoint.')
    require(definition['output_policy'] == {'kind': 'class_probabilities', 'class_order': 'frozen_vocabulary'}, 'Output policy differs.')
    expected = decode(files[manifest['expected_outputs']['name']])
    require(expected['checkpoint_sha256'] == manifest['checkpoint']['sha256'] and expected['run_id'] == descriptor['run_id'],
            'Expected output checkpoint binding differs.')
    probe_documents = [decode(files[item['name']]) for item in manifest['evidence'] if item['name'] == 'probe.json']
    require(len(probe_documents) == 1, 'Fixed probe contract is missing.')
    probe_contract = probe_documents[0]
    require(expected['probe_sha256'] == sha(files['probe.json']) and probe_contract['format'] == 'probe_v1'
            and probe_contract['split'] == 'validation', 'Fixed probe identity differs.')
    # Tolerances belong to this qualified evaluator, never to package supplied values.
    atol, rtol = 1e-6, 1e-5
    require(manifest['inference_entry']['sha256'] == sha(Path(__file__).read_bytes()), 'Consumer implementation differs.')
    require(any(x['name'] == 'image_training.py' for x in manifest['sources']), 'Captured training source provenance is missing.')
    import torch
    from PIL import Image
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    require(torch.version.cuda is None, 'CPU-only inference runtime is required.', 'unsupported')
    with tempfile.TemporaryDirectory(prefix='tuldok-inference-') as directory:
        checkpoint = torch.load(io.BytesIO(files[weights['name']]), map_location='cpu', weights_only=True)
        require(checkpoint['transform'] == definition['preprocessing_policy']
                and checkpoint['class_vocabulary'] == task['class_vocabulary']
                and checkpoint['class_to_idx'] == task['class_to_idx']
                and checkpoint['epoch'] == descriptor['clocks']['epoch'], 'Loaded weights metadata differs.')
        parameters = checkpoint['parameters']
        require({key: parameters[key] for key in ('widths', 'input_size', 'head')} == model_spec,
                'Weights model specification differs.')
        widths = model_spec['widths']; size = model_spec['input_size']
        require(type(widths) is list and len(widths) == 3 and all(type(x) is int and 4 <= x <= 64 for x in widths)
                and size in (32, 64, 96) and model_spec['head'] == 'linear', 'Unsupported independent TinyCNN topology.')
        require(definition['preprocessing_policy'] == {'name': 'resize_rgb_tensor', 'version': 2,
                'size': [size, size], 'fit_scope': 'none', 'augmentation': False}, 'Unsupported transform semantics.')
        # Independent reconstruction of the declared topology: no training adapter
        # import, model factory, torchvision transform, source checkout or cache.
        nn = torch.nn; a, b, c = widths
        model = nn.Sequential(nn.Conv2d(3, a, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(a, b, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(b, c, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
            nn.Flatten(), nn.Linear(c, len(task['class_vocabulary'])))
        model.load_state_dict(checkpoint['state_dict'], strict=True); model.eval()
        def preprocess(image):
            height, width = definition['preprocessing_policy']['size']
            rgb = image.resize((width, height), resample=Image.Resampling.BILINEAR)
            return torch.frombuffer(bytearray(rgb.tobytes()), dtype=torch.uint8).reshape(height, width, 3).permute(2, 0, 1).contiguous().to(dtype=torch.float32).div(255)
        probes = decode(files[manifest['probes']['name']])['rows']
        require([x['id'] for x in probes] == [x['frozen_reference']['id'] for x in probe_contract['members']]
                and [x['ordinal'] for x in expected['rows']] == list(range(len(probes))), 'Fixed probe membership/order differs.')
        require(all(probe['image']['sha256'] == member['input_sha256'] for probe, member in zip(probes, probe_contract['members'], strict=True)), 'Fixed probe input differs.')
        outputs = []
        with torch.no_grad():
            for probe, target in zip(probes, expected['rows'], strict=True):
                with Image.open(io.BytesIO(files[probe['image']['name']])) as image:
                    require(image.format == 'PNG' and image.width * image.height <= 4 * 1024**2, 'Invalid probe PNG.')
                    inputs = preprocess(image.convert('RGB')).unsqueeze(0)
                logits = model(inputs)[0]
                actual = logits.tolist(); probabilities = logits.softmax(0).tolist()
                for key, values in (('probabilities', probabilities),):
                    require(len(values) == len(target[key]) and all(type(y) in (int, float) and math.isfinite(y)
                            and math.isclose(x, y, abs_tol=atol, rel_tol=rtol) for x, y in zip(values, target[key], strict=True)),
                            'Fresh inference differs from evaluator-owned fixed outputs.')
                outputs.append({'id': probe['id'], 'logits': actual, 'probabilities': probabilities,
                                'predicted_index': probabilities.index(max(probabilities)), 'truth_index': target['truth_index']})
    count = len(task['class_vocabulary'])
    confusion = [[sum(row['truth_index'] == i and row['predicted_index'] == j for row in outputs) for j in range(count)] for i in range(count)]
    accuracy = sum(confusion[i][i] for i in range(count)) / len(outputs)
    f1 = []
    for i in range(count):
        denominator = sum(confusion[i]) + sum(row[i] for row in confusion)
        f1.append(2 * confusion[i][i] / denominator if denominator else 0.0)
    return {'format': 'fresh_inference_verification_v1', 'package_sha256': expected_sha256,
            'candidate': manifest['candidate'], 'checkpoint_sha256': manifest['checkpoint']['sha256'],
            'weights_sha256': weights['sha256'], 'runtime_snapshot_sha256': snapshot_sha256,
            'consumer_sha256': manifest['inference_entry']['sha256'], 'probes_sha256': manifest['probes']['sha256'],
            'expected_outputs_sha256': manifest['expected_outputs']['sha256'], 'verified': True,
            'numerical_acceptance': 'not_evaluated', 'independent_implementation': True,
            'classification_recount': {'confusion_matrix': confusion, 'accuracy': accuracy, 'macro_f1': sum(f1) / count}, 'tolerances': {'absolute': atol, 'relative': rtol}, 'outputs': outputs}


def fresh_verify(package_path, runtime, expected_sha256, snapshot_sha256, output, *, masked_paths=()):
    """Launch a clean process with package/runtime only; never inherit model caches."""
    package_path = Path(package_path)
    raw = package_path.read_bytes()
    manifest, files = inspect_package(raw, expected_sha256)
    with tempfile.TemporaryDirectory(prefix='tuldok-fresh-consumer-') as directory:
        root = Path(directory); (root / 'package.zip').write_bytes(raw)
        runner = root / 'candidate_packages.py'
        runner.write_bytes(files[manifest['inference_entry']['name']])
        home = root / 'private-home'; home.mkdir(mode=0o700)
        contract = decode(files[manifest['runtime']['contract']['name']])
        descriptor = contract['snapshot']
        require(Path(runtime) == Path(descriptor['root']) / descriptor['launch']['python'],
                'Explicit runtime path differs from approved snapshot.', 'unsupported')
        helper = root / 'recipe_process.py'; helper.write_bytes(files['recipe_process.py'])
        descriptor_path = root / 'snapshot.json'; descriptor_path.write_bytes(encoded(descriptor))
        command = ['/usr/bin/python3', '-I', '-S', '-B', str(helper), '--cpu-launch', str(descriptor_path), str(runner),
                   'consume', '--package', str(root / 'package.zip'), '--expected-sha256', expected_sha256,
                   '--runtime-snapshot-sha256', snapshot_sha256, '--output-dir', str(root)]
        if masked_paths:
            bubblewrap = shutil.which('bwrap')
            require(bubblewrap is not None, 'Filesystem-masked qualification requires bubblewrap.', 'unavailable')
            checked = []
            for path in masked_paths:
                path = Path(path).resolve(strict=True)
                require(path.is_dir() and str(path) != '/' and not root.is_relative_to(path)
                        and not Path(descriptor['root']).is_relative_to(path), 'Invalid checkout/cache mask boundary.')
                checked.append(str(path))
            guard = root / 'isolation_guard.py'
            guard.write_text("import json,os,sys\nfrom pathlib import Path\npaths=json.loads(sys.argv[1])\n"
                "assert all(not any(Path(p).iterdir()) for p in paths)\n"
                "Path('isolation.json').write_text(json.dumps({'masked_paths':paths,'verified_empty':True}))\n"
                "os.execv(sys.argv[2],sys.argv[2:])\n")
            command = [bubblewrap, '--die-with-parent', '--new-session', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc', '--bind', str(root), str(root),
                       *[token for path in checked for token in ('--tmpfs', path)], '--',
                       '/usr/bin/python3', '-I', '-S', '-B', str(guard), json.dumps(checked), *command]
        result = subprocess.run(command, cwd=root, env={'PATH': '/usr/bin:/bin', 'HOME': str(home),
            'XDG_CACHE_HOME': str(home), 'TORCH_HOME': str(home), 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        require(result.returncode == 0, 'Fresh consumer failed: ' + result.stderr.decode(errors='replace')[-1000:], 'unavailable')
        receipt = decode((root / 'verification.json').read_bytes())
        require(receipt.get('verified') is True and receipt.get('package_sha256') == expected_sha256,
                'Fresh consumer receipt differs.')
        if masked_paths:
            receipt['isolation'] = decode((root / 'isolation.json').read_bytes())
        Path(output).write_bytes(encoded(receipt))
        return receipt


def classifier_closure(candidate, artifact_bytes, probe_images, sources, runtime, published_model):
    """Create an inert closure from an exact selection and permitted byte reads.

    artifact_bytes contains the candidate descriptor, its weights, model definition,
    preprocessing/fitted policies, fixed probes and evaluation. probe_images maps
    frozen IDs to exact PNG bytes, never whole releases with private/test members.
    The caller obtains these bytes through current authorized owner accessors.
    """
    checkpoint_name = candidate['checkpoint']['name']
    descriptor = decode(artifact_bytes[checkpoint_name]); epoch = descriptor['clocks']['epoch']
    require(type(epoch) is int and epoch >= 1, 'This package profile requires TinyCNN epoch checkpoints.', 'unsupported')
    expected_name = f'probes-epoch-{epoch:04d}.json'
    names = {checkpoint_name, descriptor['weights']['name'], 'model-definition.json',
             'fitted-transform.json', 'probe.json', expected_name, 'metrics.json'}
    require(names <= set(artifact_bytes), 'Candidate inference artifact closure is incomplete.')
    definition = decode(artifact_bytes['model-definition.json'])
    metrics = decode(artifact_bytes['metrics.json'])
    probes = decode(artifact_bytes['probe.json'])
    require(candidate['checkpoint']['sha256'] == sha(artifact_bytes[checkpoint_name]), 'Selection checkpoint differs.')
    require(candidate['run_id'] == descriptor['run_id'], 'Selection Run differs.')
    require(set(probe_images) == {x['frozen_reference']['id'] for x in probes['members']}, 'Explicit fixed probe image closure differs.')
    require('image_training.py' in sources, 'Inference source closure is missing.')
    blobs = {name: artifact_bytes[name] for name in names}
    blobs.update(sources)
    require(type(published_model) is dict and set(published_model) == {'material', 'specification', 'preprocessing_policy', 'output_policy'}, 'Exact published model closure is required.')
    blobs['published-model-material.json'] = encoded(published_model['material'])
    for key in ('specification', 'preprocessing_policy', 'output_policy'):
        blobs['published-' + key + '.json'] = published_model[key]
    blobs['candidate_packages.py'] = Path(__file__).read_bytes()
    blobs['recipe_process.py'] = Path(__file__).with_name('recipe_process.py').read_bytes()
    blobs['candidate-decision.json'] = encoded(candidate['candidate'])
    blobs['transform.json'] = encoded(definition['preprocessing_policy'])
    blobs['runtime.json'] = encoded(runtime)
    blobs['task.json'] = encoded({'format': 'package_classifier_task_v1',
        'input': {'dtype': 'uint8', 'shape': ['height', 'width', 3], 'units': 'rgb_0_255'},
        'output': {'dtype': 'float32', 'shape': ['batch', 'classes'], 'units': 'probabilities'},
        'stage': 'inference', 'gauge': 'none', 'class_vocabulary': metrics['class_vocabulary'],
        'class_to_idx': metrics['class_to_idx']})
    fixed = []
    for index, member in enumerate(probes['members']):
        record_id = member['frozen_reference']['id']; raw = probe_images[record_id]
        require(sha(raw) == member['input_sha256'], 'Fixed probe asset differs from frozen input.')
        name = f'probe-{index:04d}.png'; blobs[name] = raw
        fixed.append({'id': record_id, 'image': blob(name, raw, 'image/png')})
    blobs['probe-images.json'] = encoded({'format': 'package_image_probes_v1', 'rows': fixed})
    blobs['lineage.json'] = encoded({'format': 'package_lineage_v1', 'data_policy': 'references_only',
        'sources': [{'run_id': candidate['run_id'], 'artifact_name': name, 'sha256': sha(artifact_bytes[name]),
                     'population': 'validation' if name in ('probe.json', expected_name, 'metrics.json') else 'train'} for name in sorted(names)]})
    # Unknown terms are explicitly retained; no default SPDX/permissive assertion.
    blobs['rights.json'] = encoded({'format': 'package_rights_v1', 'materials': sorted(blobs),
        'authority': None, 'terms': None, 'redistribution': 'unknown'})
    refs = {name: blob(name, raw, 'image/png' if name.endswith('.png') else
                       'text/x-python' if name.endswith('.py') else 'application/octet-stream' if name.endswith('.pt') else 'application/json')
            for name, raw in blobs.items()}
    manifest = {'format': FORMAT, 'candidate': candidate['ref'], 'checkpoint': refs[checkpoint_name],
        'model': refs['model-definition.json'], 'sources': [refs[name] for name in sorted(set(sources) | {'recipe_process.py'})],
        'transforms': [refs['transform.json'], refs['fitted-transform.json']], 'task': refs['task.json'],
        'inference_entry': refs['candidate_packages.py'], 'runtime': {'contract': refs['runtime.json'], 'provision': 'external'},
        'evidence': [refs[name] for name in ('candidate-decision.json', 'metrics.json', 'probe.json', 'published-model-material.json', 'published-specification.json', 'published-preprocessing_policy.json', 'published-output_policy.json')],
        'lineage': refs['lineage.json'], 'probes': refs['probe-images.json'], 'expected_outputs': refs[expected_name],
        'licenses': [refs['rights.json']], 'inventory': [refs[name] for name in sorted(refs)],
        'limitations': ['Local/private workflow only; unresolved rights deny redistribution.',
                        'Inference reconstruction does not establish physical validity or training resume.']}
    validate_manifest(manifest, dict(blobs, **{'manifest.json': encoded(manifest)}))
    return manifest, blobs


def scalar_a_closure(candidate, artifact_bytes, sources, runtime, published_model, inference_files=None):
    """Close one explicitly frozen scientific A selection; no training or inference.

    All producer bytes are obtained through current authorized Run/Model owners.
    Expected values are retained native producer fields, never host calculations.
    """
    context = decode(artifact_bytes['execution-context.json']); static = context['static']; policy = static['policy']
    checkpoint_name = candidate['checkpoint']['name']; descriptor = decode(artifact_bytes[checkpoint_name])
    require(candidate['run_id'] == descriptor['run_id'] and candidate['checkpoint']['sha256'] == sha(artifact_bytes[checkpoint_name]),
            'Scalar A immutable candidate selection differs.')
    index = decode(artifact_bytes['checkpoints.json']); field_index = decode(artifact_bytes['field-index.json'])
    selected = [group for group in field_index if group['checkpoint_sha256'] == candidate['checkpoint']['sha256']]
    require(len(selected) == 1 and len(selected[0]['cases']) == 1, 'Scalar A selected native fields are unavailable.', 'unsupported')
    case = selected[0]['cases'][0]
    names = {'execution-context.json', 'model-evidence.json', 'model-definition.json', 'profile.json', 'probe.json',
             'metric-definitions.json', 'checkpoints.json', 'observations.json', 'field-index.json',
             'fitted-transform.json', 'output-policy.json'}
    for entry in index['entries']:
        name = entry['checkpoint']['name']; names.add(name)
        names.add(decode(artifact_bytes[name])['weights']['name'])
    for group in field_index:
        for row in group['cases']:
            names.update((row['predicted']['name'], row['reference']['name']))
    for binding in policy['probe_inputs']:
        names.update(item['artifact'] for item in binding['fields'])
    fitted = decode(artifact_bytes['fitted-transform.json']); names.add(fitted['state']['name'])
    require(names <= set(artifact_bytes), 'Scalar A retained byte closure is incomplete.')
    require(set(sources) == {'producer.py', 'evidence_writer.py', 'task.json', 'extension.json', 'NOTICE.txt', 'recipe.json'},
            'Scalar A published source/recipe closure differs.')
    blobs = {name: artifact_bytes[name] for name in names}; blobs.update(sources)
    blobs['published-model-material.json'] = encoded(published_model['material'])
    policies = {}
    for key in ('specification', 'preprocessing_policy', 'output_policy'):
        blobs['published-' + key + '.json'] = published_model[key]; policies[key] = decode(published_model[key])
    blobs['package-model-definition.json'] = encoded({'format': 'package_scalar_a_model_v1', **policies})
    blobs['transform-policy.json'] = published_model['preprocessing_policy']
    if inference_files is None:
        matches = [row for row in SCALAR_A_ADAPTERS.values() if row['recipe_sha256'] == sha(sources['recipe.json'])]
        require(len(matches) == 1, 'Scalar A source recipe has no explicitly nominated inference adapter.', 'unsupported')
        root = Path(__file__).parent / 'examples/extensions/field-surrogate' / matches[0]['directory']
        require(root.is_dir(), 'Nominated scalar A inference closure is not installed.', 'unavailable')
        inference_files = {name: (root / name).read_bytes() for name in ('infer.py', 'contract.json', 'NOTICE.txt')}
    require(set(inference_files) == {'infer.py', 'contract.json', 'NOTICE.txt'}, 'Scalar A frozen adapter closure differs.')
    blobs['infer.py'] = inference_files['infer.py']; blobs['inference-contract.json'] = inference_files['contract.json']
    blobs['inference-NOTICE.txt'] = inference_files['NOTICE.txt']
    blobs['candidate_packages.py'] = Path(__file__).read_bytes(); blobs['recipe_process.py'] = Path(__file__).with_name('recipe_process.py').read_bytes()
    blobs['candidate-decision.json'] = encoded(candidate['candidate']); blobs['runtime.json'] = encoded(runtime)
    def reference(name):
        return blob(name, blobs[name], 'application/octet-stream' if name.endswith('.npy') else
                    'text/x-python' if name.endswith('.py') else 'text/plain' if name.endswith('.txt') else 'application/json')
    input_name = policy['probe_inputs'][0]['fields'][0]['artifact']
    blobs['package-field-probes.json'] = encoded({'format': 'package_scalar_a_probes_v1',
        'rows': [{'ordinal': 0, 'input': reference(input_name)}]})
    blobs['package-field-expected.json'] = encoded({'format': 'package_scalar_a_expected_v1', 'run_id': descriptor['run_id'],
        'checkpoint_sha256': candidate['checkpoint']['sha256'], 'probe_sha256': sha(blobs['probe.json']),
        'rows': [{'ordinal': 0, 'prediction': case['predicted'], 'reference': case['reference']}]})
    blobs['package-field-task.json'] = encoded({'format': SCALAR_A_TASK_FORMAT, 'contract': reference('inference-contract.json'),
        'context': reference('execution-context.json'), 'probe': reference('probe.json'),
        'field_index': reference('field-index.json'), 'profile': reference('profile.json')})
    validation_names = {'probe.json', 'field-index.json', 'observations.json', 'model-evidence.json', 'metric-definitions.json', input_name}
    validation_names.update(row[key]['name'] for group in field_index for row in group['cases'] for key in ('predicted', 'reference'))
    blobs['lineage.json'] = encoded({'format': 'package_lineage_v1', 'data_policy': 'references_only',
        'sources': [{'run_id': candidate['run_id'], 'artifact_name': name, 'sha256': sha(artifact_bytes[name]),
                    'population': 'validation' if name in validation_names else 'train'} for name in sorted(names)]})
    blobs['rights.json'] = encoded({'format': 'package_rights_v1', 'materials': sorted(blobs),
        'authority': None, 'terms': None, 'redistribution': 'denied'})
    refs = {name: reference(name) for name in blobs}
    principal = {checkpoint_name, 'package-model-definition.json', 'transform-policy.json', 'fitted-transform.json',
        'package-field-task.json', 'candidate_packages.py', 'runtime.json', 'lineage.json', 'package-field-probes.json',
        'package-field-expected.json', 'rights.json', *sources, 'infer.py', 'recipe_process.py'}
    manifest = {'format': FORMAT, 'candidate': candidate['ref'], 'checkpoint': refs[checkpoint_name],
        'model': refs['package-model-definition.json'], 'sources': [refs[name] for name in sorted({*sources, 'infer.py', 'recipe_process.py'})],
        'transforms': [refs['transform-policy.json'], refs['fitted-transform.json']], 'task': refs['package-field-task.json'],
        'inference_entry': refs['candidate_packages.py'], 'runtime': {'contract': refs['runtime.json'], 'provision': 'external'},
        'evidence': [refs[name] for name in sorted(set(blobs) - principal)], 'lineage': refs['lineage.json'],
        'probes': refs['package-field-probes.json'], 'expected_outputs': refs['package-field-expected.json'],
        'licenses': [refs['rights.json']], 'inventory': [refs[name] for name in sorted(refs)],
        'limitations': ['Private authored scientific A QA only; redistribution is not granted.',
            'Fixed-probe reconstruction establishes neither independent numerical quality nor physical validity or training resume.']}
    validate_manifest(manifest, dict(blobs, **{'manifest.json': encoded(manifest)}))
    return manifest, blobs


def authorize_transitive_inputs(runs, run, *, seen=None):
    """Reauthorize retained inputs on every derived read, including summaries.

    Wire at Runs._external_inventory (whole/segment/capture/summary) and before
    preflight/capture of recipe material. A package inherits the union of its
    input populations; captured receipts never replace current authority.
    """
    from workbench import WorkbenchError
    seen = set() if seen is None else seen
    if run['id'] in seen:
        raise WorkbenchError('Cyclic derived Run input lineage.', 'unavailable', 409)
    if len(seen) >= 64:
        raise WorkbenchError('Derived Run input lineage exceeds its bound.', 'unsupported', 409)
    seen = seen | {run['id']}
    if not runs._external(run):
        return
    authorize_material_inputs(runs,run['material'],seen=seen)


def authorize_material_inputs(runs,material,*,seen=None):
    """Reauthorize an exact retained input material without inventing a Run."""
    from workbench import WorkbenchError
    seen=set() if seen is None else seen
    for item in material['inputs'].values():
        if item.get('kind') != 'run_artifact':
            continue
        source = item['source']; source_id = source['run_id']; name = source['artifact_name']
        runs.access.require('inspect', 'runs.artifact', source_id)
        parent = runs._load(source_id)
        if parent['state'] != 'completed':
            raise WorkbenchError('Derived source is no longer a completed Run.', 'unavailable', 409)
        if not runs._external(parent):
            protected = name in ('predictions-test.json', 'test-metrics.json', 'release.zip')
            if protected and not parent.get('exposure_events'):
                raise WorkbenchError('Derived artifact includes an undisclosed protected population.', 'conflict', 409)
            available = parent['artifacts']
            if name == 'release.zip':
                actual = parent['release_sha256']
            else:
                artifact = next((x for x in available if x['name'] == name), None)
                actual = artifact['sha256'] if artifact else None
        else:
            authorize_transitive_inputs(runs, parent, seen=seen)
            artifact = next((x for x in parent['artifacts'] if x['name'] == name), None)
            actual = artifact['sha256'] if artifact else None
        if actual != source['measured_sha256']:
            raise WorkbenchError('Derived source identity differs from retained capture.', 'unavailable', 409)


def _write_project(root, files):
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for name, raw in files.items():
            with (root / name).open('xb') as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            (root / name).chmod(0o400)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise


def prepare_project(destination, manifest, blobs, *, snapshot_sha256=None):
    """Assemble inert declared pack/verify recipes; never grant or admit a Run.

    The returned graph bodies enter the existing finite study preparation seam.
    The caller must preserve current source authority while preparing the exact
    input bindings. Source closure and dependency bytes are immutable project data.
    """
    import uuid
    create_package(manifest, blobs)  # Validate before publishing inert project files.
    root = Path(destination)
    source = Path(__file__).read_bytes()
    request, payload = encoded(manifest), _zip(blobs)
    data = {'request.json': request, 'closure.zip': payload}
    sources = [{'path': 'candidate_packages.py', 'sha256': sha(source)}]
    common = {'schema_version': 1, 'format': 'external_recipe_v1', 'version': 1,
              'runtime': 'captured_cpu_python_v1' if snapshot_sha256 else 'system_python',
              'sources': sources, 'entrypoint': 'candidate_packages.py', 'parameters': {},
              'environment': {}, 'resources': {'wall_seconds': 120, 'max_output_bytes': MAX_PACKAGE_BYTES + MAX_DOCUMENT_BYTES}}
    if snapshot_sha256:
        common['runtime_snapshot_sha256'] = snapshot_sha256
    lineage = decode(blobs[manifest['lineage']['name']])['sources']
    source_inputs = {f'lineage_{index}': source for index, source in enumerate(lineage)}
    require(len(source_inputs) <= 30, 'Package lineage exceeds recipe input bound.')
    pack = dict(common, id='candidate-package', name='Package exact candidate closure',
        arguments=[{'literal': 'pack'}, {'literal': '--request'}, {'input': 'request'},
            {'literal': '--blobs'}, {'input': 'closure'}, {'literal': '--output-dir'}, {'output_dir': True}],
        inputs={'request': {'max_bytes': MAX_DOCUMENT_BYTES}, 'closure': {'max_bytes': MAX_PACKAGE_BYTES},
                **{name: {'max_bytes': MAX_PACKAGE_BYTES} for name in source_inputs}},
        outputs=[{'path': 'package.zip', 'role': 'inference_package', 'max_bytes': MAX_PACKAGE_BYTES, 'required': True},
                 {'path': 'package-result.json', 'role': 'package_result', 'max_bytes': MAX_DOCUMENT_BYTES, 'required': True}])
    project = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Exact candidate inference package',
        'data': [{'id': name.split('.')[0], 'label': name, 'path': name, 'sha256': sha(raw)} for name, raw in data.items()],
        'recipes': [{'id': 'package', 'label': 'Package exact candidate closure', 'path': 'package-recipe.json', 'sha256': sha(encoded(pack))}],
        'evidence': [], 'requirements': []}
    _write_project(root, dict(data, **{'candidate_packages.py': source, 'package-recipe.json': encoded(pack), 'project.json': encoded(project)}))
    return {'manifest': project, 'graph': {'name': 'Package exact candidate closure', 'project_id': project['id'],
        'recipe_id': 'package', 'expected_sha256': sha(encoded(pack)),
        'inputs': {'request': {'reference_id': 'request', 'expected_sha256': sha(request)},
                   'closure': {'reference_id': 'closure', 'expected_sha256': sha(payload)},
                   **{name: {'kind': 'run_artifact', 'run_id': item['run_id'], 'artifact_name': item['artifact_name'],
                             'expected_sha256': item['sha256']} for name, item in source_inputs.items()}}}}


def prepare_verifier_project(destination, package_source, snapshot_sha256):
    """Declare a charged fresh consumer bound to an approved CPU RuntimeSnapshot."""
    import uuid
    closed(package_source, ('kind', 'run_id', 'artifact_name', 'expected_sha256'))
    require(package_source['kind'] == 'run_artifact', 'Verifier input must be an exact package Run artifact.')
    require(type(snapshot_sha256) is str and HASH.fullmatch(snapshot_sha256) is not None, 'An exact approved CPU RuntimeSnapshot is required.')
    source = Path(__file__).read_bytes()
    definition = {'schema_version': 1, 'format': 'external_recipe_v1', 'version': 1,
        'id': 'candidate-verifier', 'name': 'Verify exact candidate in a fresh captured CPU process',
        'runtime': 'captured_cpu_python_v1', 'runtime_snapshot_sha256': snapshot_sha256,
        'sources': [{'path': 'candidate_packages.py', 'sha256': sha(source)}], 'entrypoint': 'candidate_packages.py',
        'arguments': [{'literal': 'consume'}, {'literal': '--package'}, {'input': 'package'},
                      {'literal': '--expected-sha256'}, {'literal': package_source['expected_sha256']},
                      {'literal': '--runtime-snapshot-sha256'}, {'literal': snapshot_sha256},
                      {'literal': '--output-dir'}, {'output_dir': True}],
        'parameters': {}, 'inputs': {'package': {'max_bytes': MAX_PACKAGE_BYTES}},
        'outputs': [{'path': 'verification.json', 'role': 'inference_verification', 'max_bytes': MAX_DOCUMENT_BYTES, 'required': True}],
        'environment': {}, 'resources': {'wall_seconds': 180, 'max_output_bytes': MAX_DOCUMENT_BYTES}}
    project = {'schema_version': 1, 'id': uuid.uuid4().hex, 'name': 'Fresh candidate inference verification',
        'data': [], 'recipes': [{'id': 'verify', 'label': 'Verify exact candidate package', 'path': 'recipe.json', 'sha256': sha(encoded(definition))}],
        'evidence': [], 'requirements': []}
    root = Path(destination)
    _write_project(root, {'candidate_packages.py': source, 'recipe.json': encoded(definition), 'project.json': encoded(project)})
    return {'manifest': project, 'graph': {'name': 'Verify exact candidate package', 'project_id': project['id'],
        'recipe_id': 'verify', 'expected_sha256': sha(encoded(definition)), 'inputs': {'package': package_source}}}


def _prefix_project_references(destination, prefix, prepared):
    """Projects references are relative to the configured root, not the manifest."""
    project = prepared['manifest']
    for item in project['data']:
        item['path'] = prefix + '/' + item['path']
    for item in project['recipes']:
        path = destination / item['path']
        definition = decode(path.read_bytes())
        definition['entrypoint'] = prefix + '/' + definition['entrypoint']
        for source in definition['sources']:
            source['path'] = prefix + '/' + source['path']
        path.chmod(0o600)
        with path.open('wb') as handle:
            handle.write(encoded(definition)); handle.flush(); os.fsync(handle.fileno())
        path.chmod(0o400)
        item.update(path=prefix + '/' + item['path'], sha256=sha(encoded(definition)))
        prepared['graph']['expected_sha256'] = item['sha256']
    path = destination / 'project.json'
    path.chmod(0o600)
    with path.open('wb') as handle:
        handle.write(encoded(project)); handle.flush(); os.fsync(handle.fileno())
    path.chmod(0o400)


def _prepare_operation(experiments, study_id, body, kind):
    """Owner composition, atomic metadata, and existing exact study preparation."""
    from metadata import CommitOutcomeUnknown
    from model_definitions import checked_json
    from pipeline import digest
    from runtime_snapshots import RuntimeSnapshots
    from workbench import WorkbenchError
    require(not experiments.db.in_transaction, 'Candidate preparation cannot run inside a caller metadata transaction.', 'unsupported')
    operation = 'studies.prepare_package' if kind == 'package' else 'studies.prepare_verifier'
    fields = {'request_key', 'revision', 'candidate_id', 'root', 'directory', 'runtime_snapshot_sha256'}
    if kind == 'verify':
        fields |= {'package_run_id', 'package_sha256'}
    closed(body, fields)
    body = checked_json(body)
    from experiments import request_key
    request_key(body['request_key'])
    access = experiments.access; dataset = experiments.dataset
    context = access.require('edit', operation, study_id, owner_only=True)
    identity = digest({'study_id': study_id, 'body': body})
    with experiments.lock:
        prior = experiments._receipt(context.actor_id, operation, body['request_key'], identity)
        if prior:
            experiments.candidate(body['candidate_id'])
            return prior
        study = experiments._study(study_id); experiments._expected(study, body)
    candidate = experiments.candidate(body['candidate_id'])
    require(candidate['candidate']['study_id'] == study_id, 'Candidate and preparation study differ.')
    require(type(body['root']) is str and body['root'] in dataset.projects.roots,
            'Choose an explicitly configured project root.', 'unavailable')
    require(type(body['directory']) is str and NAME.fullmatch(body['directory']) is not None,
            'Choose a new bounded flat directory inside the configured root.')
    root_fd = os.dup(dataset.projects.roots[body['root']][0])
    try:
        destination = Path('/proc/self/fd') / str(root_fd) / body['directory']
        require(not destination.exists(), 'Preparation directory exists without this exact operation receipt.', 'unavailable')
        snapshot = RuntimeSnapshots(dataset.db, access, dataset.path).get(body['runtime_snapshot_sha256'])
        if kind == 'package':
            run = dataset.runs._load(candidate['run_id'])
            scientific = dataset.runs._extension(run)
            require(scientific or run['graph'].get('recipe') == 'image_classification_model_v2',
                    'Candidate package profile is unsupported.', 'unsupported')
            if scientific:
                require(dataset.runs.model_evidence(run['id'], {}, contract_version=2)['state'] == 'verified',
                        'Scientific source requires verified current field evidence.', 'unsupported')
            artifacts = {item['name']: dataset.runs.artifact(run['id'], item['name'])[0] for item in run['artifacts']
                         if item['name'] not in ('test-metrics.json', 'predictions-test.json', 'artifact-manifest.json')}
            if not scientific:
                probe = decode(artifacts['probe.json'])
                release, media = dataset.runs.artifact(run['id'], 'release.zip')
                require(sha(release) == run['release_sha256'], 'Frozen probe source differs.')
                # Extract permitted fixed validation assets only. Never export the mixed release.
                with zipfile.ZipFile(io.BytesIO(release)) as archive:
                    release_manifest = decode(archive.read('manifest.json'))
                    by_id = {row['id']: row for row in release_manifest['records'] if row['split'] == 'validation'}
                    images = {member['frozen_reference']['id']: archive.read(by_id[member['frozen_reference']['id']]['asset'])
                              for member in probe['members']}
            source_trial = experiments.trial(candidate['candidate']['trial_id'])
            source_material = dataset.pipelines.recipe_material(source_trial['material'])['material']
            model = dataset.models.material(source_material['model'], verify=True)
            sources = {item['import_path']: dataset.models.read_blob(model['ref'], item['blob']) for item in model['material']['source_closure']}
            published = {'material': model['material'], **{key: dataset.models.read_blob(model['ref'], model['material'][key]) for key in ('specification', 'preprocessing_policy', 'output_policy')}}
            if scientific:
                manifest, blobs = scalar_a_closure(candidate, artifacts, sources, runtime_contract(snapshot), published)
            else:
                manifest, blobs = classifier_closure(candidate, artifacts, images, sources, runtime_contract(snapshot), published)
            prepared = prepare_project(destination, manifest, blobs)
        else:
            package_raw, _media = dataset.runs.artifact(body['package_run_id'], 'package.zip')
            manifest, files = inspect_package(package_raw, body['package_sha256'])
            require(manifest['candidate'] == candidate['ref'], 'Package belongs to another candidate.')
            require(decode(files[manifest['runtime']['contract']['name']])['snapshot'] == snapshot,
                    'Verifier runtime differs from package.', 'unsupported')
            prepared = prepare_verifier_project(destination, {'kind': 'run_artifact', 'run_id': body['package_run_id'],
                'artifact_name': 'package.zip', 'expected_sha256': body['package_sha256']}, snapshot['manifest_sha256'])
        publication_owned = False
        published_result = None
        try:
            _prefix_project_references(destination, body['directory'], prepared)
            os.fsync(root_fd)
            with experiments.lock:
                access.require('edit', operation, study_id, owner_only=True)
                prior = experiments._receipt(context.actor_id, operation, body['request_key'], identity)
                if prior:
                    return prior
                experiments._expected(experiments._study(study_id), body)
                root_entry = dataset.projects.roots.get(body['root'])
                require(root_entry is not None and tuple(os.fstat(root_entry[0])[key] for key in (stat.ST_DEV, stat.ST_INO)) == tuple(os.fstat(root_fd)[key] for key in (stat.ST_DEV, stat.ST_INO)), 'Configured project root changed during preparation.', 'unavailable')
            dataset.projects.open({'root': body['root'], 'manifest_path': body['directory'] + '/project.json'})
            graph = dataset.pipelines.create_external(prepared['graph'])
            # Inert owner preparation uses each existing owner's short transaction.
            # Expensive source/runtime capture remains outside a caller DB lock.
            task = {'kind': 'task', 'catalog_id': dataset.db.dataset_id, 'id': 'candidate_' + kind,
                    'revision': 1, 'sha256': digest({'format': 'candidate_' + kind + '_operation_v1'})}
            operation_model = dataset.models.create({'name': 'Candidate ' + kind + ' operation closure', 'task': task,
                'kind': 'captured_source', 'specification': {'format': 'candidate_' + kind + '_operation_v1', 'candidate': candidate['ref']},
                'source_selector': {key: prepared['graph'][key] for key in ('project_id', 'recipe_id', 'expected_sha256')},
                'preprocessing_policy': {'kind': 'exact_captured_bytes'}, 'output_policy': {'kind': 'inference_package' if kind == 'package' else 'inference_verification'}})
            operation_material = dataset.models.publish(operation_model['id'], {'revision': operation_model['revision']})
            def publish(trial):
                nonlocal publication_owned, published_result
                publication_owned = True
                experiments.db.on_rollback(lambda: shutil.rmtree(destination, ignore_errors=True))
                access.require('edit', operation, study_id, owner_only=True)
                prior = experiments._receipt(context.actor_id, operation, body['request_key'], identity)
                if prior:
                    require(prior['trial'] == trial, 'Preparation receipt is bound to another trial.')
                    published_result = prior
                    return
                result = {'state': 'prepared', 'candidate_id': body['candidate_id'], 'trial': trial,
                          'graph': graph, 'model': operation_material['ref'], 'runtime_snapshot_sha256': snapshot['manifest_sha256']}
                if kind == 'verify':
                    result.update(package_run_id=body['package_run_id'], package_sha256=body['package_sha256'])
                experiments._save_receipt(context.actor_id, operation, body['request_key'], identity, result)
                access.audit(operation, body['candidate_id'], {'study_id': study_id, 'trial_id': trial['id'], 'material_sha256': trial['material']['sha256']})
                published_result = result
            experiments.prepare_trial(study_id, {'request_key': kind + '-' + identity, 'revision': body['revision'],
                'graph_id': graph['id'], 'graph_revision': graph['revision'], 'model': operation_material['ref'], 'replicate': 0}, _publish=publish)
            publication_owned = True
            if published_result is not None:
                return published_result
            with experiments.lock:
                result = experiments._receipt(context.actor_id, operation, body['request_key'], identity)
            require(result is not None, 'Prepared trial lacks its atomic operation receipt.', 'unavailable')
            return result
        except CommitOutcomeUnknown:
            raise
        except BaseException:
            if not publication_owned:
                shutil.rmtree(destination, ignore_errors=True)
            raise

    finally:
        os.close(root_fd)


def prepare_candidate_package(experiments, study_id, body):
    return _prepare_operation(experiments, study_id, body, 'package')


def prepare_candidate_verifier(experiments, study_id, body):
    return _prepare_operation(experiments, study_id, body, 'verify')


def candidate_package_state(experiments, candidate_id):
    """Read current authorized package/verification receipts without executing code."""
    experiments.access.require('inspect', 'studies.package_state', candidate_id)
    candidate = experiments.candidate(candidate_id)
    result = {'candidate': candidate, 'state': 'selected', 'packages': [], 'verifications': []}
    rows = experiments.db.execute("SELECT operation_id,document FROM model_operation_receipts WHERE operation_id IN (%s,%s) AND (document::jsonb)->>'candidate_id'=%s ORDER BY actor_id,request_key LIMIT 101",
        ('studies.prepare_package', 'studies.prepare_verifier', candidate_id)).fetchall()
    require(len(rows) <= 100, 'Candidate package receipt limit exceeded.', 'unsupported')
    from model_definitions import retained_json
    for row in rows:
        prepared = retained_json(row['document'])
        if prepared.get('candidate_id') != candidate_id:
            continue
        reservations = experiments.db.execute('SELECT run_id FROM model_attempt_reservations WHERE trial_id=%s ORDER BY run_id LIMIT 101',
                                              (prepared['trial']['id'],)).fetchall()
        require(len(reservations) <= 100, 'Candidate package reservation limit exceeded.', 'unsupported')
        for reservation in reservations:
            run = experiments.dataset.runs.get(reservation['run_id'])
            if run['state'] != 'completed':
                continue
            collection = 'packages' if row['operation_id'] == 'studies.prepare_package' else 'verifications'
            require(len(result[collection]) < 100, 'Candidate package state result limit exceeded.', 'unsupported')
            if row['operation_id'] == 'studies.prepare_package':
                raw, _ = experiments.dataset.runs.artifact(run['id'], 'package.zip')
                item = next(item for item in run['artifacts'] if item['name'] == 'package.zip')
                manifest, files = inspect_package(raw, item['sha256'])
                require(manifest['candidate'] == candidate['ref'], 'Published package candidate differs.')
                result['packages'].append({'run_id': run['id'], 'sha256': item['sha256'], 'bytes': item['bytes'],
                    'artifact_name': 'package.zip', 'url': f"/api/workspace/runs/{run['id']}/artifacts/package.zip"})
            else:
                raw, _ = experiments.dataset.runs.artifact(run['id'], 'verification.json')
                receipt = decode(raw)
                require(receipt.get('verified') is True and receipt.get('candidate') == candidate['ref']
                        and receipt.get('package_sha256') == prepared['package_sha256'], 'Published fresh verification differs.')
                result['verifications'].append({'run_id': run['id'], 'receipt': receipt})
    if result['packages']:
        result['state'] = 'package_complete'
    package_hashes = {item['sha256'] for item in result['packages']}
    if any(item['receipt']['package_sha256'] in package_hashes for item in result['verifications']):
        result['state'] = 'fresh_verified'
    require(len(encoded(result)) <= MAX_DOCUMENT_BYTES, 'Candidate package state exceeds its response bound.', 'unsupported')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('pack', 'consume'))
    parser.add_argument('--request'); parser.add_argument('--blobs')
    parser.add_argument('--package'); parser.add_argument('--expected-sha256')
    parser.add_argument('--runtime-snapshot-sha256'); parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    try:
        output = Path(args.output_dir)
        if args.action == 'pack':
            manifest = decode(Path(args.request).read_bytes())
            raw = create_package(manifest, archive_files(Path(args.blobs).read_bytes()))
            (output / 'package.zip').write_bytes(raw)
            (output / 'package-result.json').write_bytes(encoded({'format': 'package_result_v1',
                'package_sha256': sha(raw), 'bytes': len(raw), 'verification': 'verification_pending'}))
        else:
            receipt = infer_package(Path(args.package).read_bytes(), args.expected_sha256, args.runtime_snapshot_sha256)
            (output / 'verification.json').write_bytes(encoded(receipt))
        return 0
    except (PackageError, KeyError, TypeError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
