"""Bounded inference packages and explicitly invoked fresh CPU consumers.

Inspection never imports captured source. Packaging/verifying recipes are ordinary
captured recipes: Pipeline/Experiments/Access/Runs retain execution authority.
Only local/private use is supported while any included rights remain unresolved.
"""
import argparse
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
            and type(candidate.get('id')) is str and re.fullmatch('[a-f0-9]{32}', candidate['id']) is not None,
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
    require(decision.get('run_id') == descriptor.get('run_id')
            and decision.get('checkpoint_sha256') == manifest['checkpoint']['sha256']
            and 'metrics.json' in indexed and decision.get('evaluation_sha256') == indexed['metrics.json']['sha256'],
            'Selected candidate Run/checkpoint/evaluation differs from package closure.')
    require('published-model-material.json' in indexed, 'Published model material bytes are required.')
    published = decode(files['published-model-material.json'])
    require(type(published) is dict, 'Published model material must be an object.')
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
    task = decode(files[manifest['task']['name']]); metrics = decode(files['metrics.json'])
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
    require(referenced | exempt == set(indexed), 'Unreferenced package content is not permitted.')
    return manifest


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
            require(run['graph'].get('recipe') == 'image_classification_model_v2', 'Candidate packaging is qualified only for TinyCNN v2.', 'unsupported')
            artifacts = {item['name']: dataset.runs.artifact(run['id'], item['name'])[0] for item in run['artifacts']
                         if item['name'] not in ('test-metrics.json', 'predictions-test.json', 'artifact-manifest.json')}
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
                access.require('edit', operation, study_id, owner_only=True)
                prior = experiments._receipt(context.actor_id, operation, body['request_key'], identity)
                if prior:
                    require(prior['trial'] == trial, 'Preparation receipt is bound to another trial.')
                    return
                experiments.db.on_rollback(lambda: shutil.rmtree(destination, ignore_errors=True))
                result = {'state': 'prepared', 'candidate_id': body['candidate_id'], 'trial': trial,
                          'graph': graph, 'model': operation_material['ref'], 'runtime_snapshot_sha256': snapshot['manifest_sha256']}
                if kind == 'verify':
                    result.update(package_run_id=body['package_run_id'], package_sha256=body['package_sha256'])
                experiments._save_receipt(context.actor_id, operation, body['request_key'], identity, result)
                access.audit(operation, body['candidate_id'], {'study_id': study_id, 'trial_id': trial['id'], 'material_sha256': trial['material']['sha256']})
            experiments.prepare_trial(study_id, {'request_key': kind + '-' + identity, 'revision': body['revision'],
                'graph_id': graph['id'], 'graph_revision': graph['revision'], 'model': operation_material['ref'], 'replicate': 0}, _publish=publish)
            with experiments.lock:
                result = experiments._receipt(context.actor_id, operation, body['request_key'], identity)
            require(result is not None, 'Prepared trial lacks its atomic operation receipt.', 'unavailable')
            return result
        except CommitOutcomeUnknown:
            raise
        except BaseException:
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
