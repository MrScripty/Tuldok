"""Closed, bounded scratch CPU trainer for frozen image_classification_v1 releases.

This module owns decoding and training, never admission, queues, cancellation,
publication, or annotation changes. Heavy dependencies are loaded only by the
isolated CLI runtime. See docs/contracts/workspace-image-training.md.
"""
import argparse
import ctypes
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import shutil
import stat
import sys
import tempfile
import time
import zipfile

ADAPTER = {'name': 'tinycnn_cpu', 'version': 1}
MODEL_ADAPTER = {'name': 'tinycnn_cpu', 'version': 2}
MODEL_RECIPE = 'image_classification_model_v2'
PARAMETER_BOUNDS = {
    'epochs': {'minimum': 1, 'maximum': 5, 'default': 1, 'type': 'integer'},
    'batch_size': {'minimum': 1, 'maximum': 16, 'default': 8, 'type': 'integer'},
    'learning_rate': {'minimum': 0.00001, 'maximum': 0.01, 'default': 0.001, 'type': 'number'},
    'seed': {'minimum': 0, 'maximum': 2**32 - 1, 'default': 42, 'type': 'integer'},
}
RUNTIME_PINS = {'torch': '2.8.0+cpu', 'torchvision': '0.23.0+cpu', 'scikit-learn': '1.7.2'}
MAX_IMAGES, MAX_CLASSES = 128, 8
MAX_ZIP_BYTES, MAX_EXPANDED_BYTES = 40 * 1024**2, 64 * 1024**2
MAX_MANIFEST_BYTES, MAX_JOB_BYTES = 1024**2, 16 * 1024
MAX_IMAGE_PIXELS, MAX_IMAGE_DIMENSION = 4 * 1024**2, 8192
TRANSFORM = {'name': 'resize_rgb_tensor', 'version': 1, 'size': [96, 96],
             'fit_scope': 'none', 'augmentation': False}
HASH = re.compile(r'[a-f0-9]{64}\Z')
IDENTIFIER = re.compile(r'[a-f0-9]{32}\Z')


class TrainingError(ValueError):
    def __init__(self, outcome, message):
        super().__init__(message)
        self.outcome = self.code = outcome


def _invalid(message):
    raise TrainingError('invalid', message)


def _json(raw, description):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                _invalid(f'{description} contains duplicate fields.')
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: _invalid(f'{description} contains nonfinite numbers.'))
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, TrainingError):
            raise
        _invalid(f'{description} is not valid bounded JSON.')


def validate_parameters(value):
    """Canonical closed parameter decoder shared by graph admission and worker."""
    if not isinstance(value, dict) or set(value) != set(PARAMETER_BOUNDS):
        _invalid('Supply exactly epochs, batch_size, learning_rate and seed.')
    for name, rule in PARAMETER_BOUNDS.items():
        number = value[name]
        accepted = (type(number) is int if rule['type'] == 'integer' else type(number) in (int, float))
        if (not accepted or not rule['minimum'] <= number <= rule['maximum']
                or not math.isfinite(number)):
            _invalid(f'{name} must be {rule["type"]} from {rule["minimum"]} to {rule["maximum"]}.')
    return dict(value)



def validate_architecture(value):
    if (type(value) is not dict or set(value) != {'widths', 'input_size', 'head'}
            or type(value['widths']) is not list or len(value['widths']) != 3
            or any(type(width) is not int or not 4 <= width <= 64 for width in value['widths'])
            or type(value['input_size']) is not int or value['input_size'] not in (32, 64, 96)
            or value['head'] != 'linear'):
        _invalid('TinyCNN v2 requires three integer widths4–64, input_size32/64/96 and head linear.')
    return dict(value, widths=list(value['widths']))


def validate_model_parameters(value):
    if type(value) is not dict or set(value) != set(PARAMETER_BOUNDS) | {'widths', 'input_size', 'head'}:
        _invalid('Supply exactly epochs, batch_size, learning_rate, seed, widths, input_size and head.')
    return {**validate_parameters({key:value[key] for key in PARAMETER_BOUNDS}),
            **validate_architecture({key:value[key] for key in ('widths', 'input_size', 'head')})}


def transform_for_parameters(parameters):
    if 'input_size' not in parameters:
        return dict(TRANSFORM)
    return dict(TRANSFORM, version=2, size=[parameters['input_size']] * 2)


def build_model(torch, widths, class_count):
    """Owned reconstructable TinyCNN topology; no imported project source."""
    nn = torch.nn
    a, b, c = widths
    return nn.Sequential(nn.Conv2d(3, a, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                         nn.Conv2d(a, b, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                         nn.Conv2d(b, c, 3, padding=1), nn.ReLU(),
                         nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(c, class_count))

def _checked_job(value):
    fields = {'schema_version', 'dataset_id', 'run_id', 'graph_sha256', 'release_id',
              'release_sha256', 'release_path', 'output_dir', 'parameters', 'parent_pid'}
    if isinstance(value, dict) and value.get('schema_version') == 2:
        fields.add('evidence_context')
    if not isinstance(value, dict) or set(value) != fields:
        _invalid('Training job must contain exactly the version 1 job fields.')
    if type(value['schema_version']) is not int or value['schema_version'] not in (1, 2):
        raise TrainingError('unsupported', 'Only training job schema version 1 is supported.')
    for key in ('dataset_id', 'run_id'):
        if not isinstance(value[key], str) or not IDENTIFIER.fullmatch(value[key]):
            _invalid(f'{key} must be a canonical 32-character identifier.')
    for key in ('graph_sha256', 'release_id', 'release_sha256'):
        if not isinstance(value[key], str) or not HASH.fullmatch(value[key]):
            _invalid(f'{key} must be a lowercase SHA-256.')
    if value['release_id'] != value['release_sha256']:
        _invalid('Release identity and expected release SHA-256 differ.')
    for key in ('release_path', 'output_dir'):
        if (not isinstance(value[key], str) or not value[key] or '\0' in value[key]
                or not Path(value[key]).is_absolute()):
            _invalid(f'{key} must be an absolute path supplied by the run owner.')
    if type(value['parent_pid']) is not int or value['parent_pid'] < 1:
        _invalid('parent_pid must identify the owning local process.')
    return dict(value, parameters=(validate_model_parameters if value['schema_version'] == 2 else validate_parameters)(value['parameters']))


def _read_release(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        _invalid('Expected release SHA-256 is invalid.')
    try:
        with Path(path).open('rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                _invalid('Frozen release must be a regular file.')
            raw = handle.read(MAX_ZIP_BYTES + 1)
    except OSError as error:
        raise TrainingError('unavailable', 'Frozen release bytes are unavailable.') from error
    if len(raw) > MAX_ZIP_BYTES:
        _invalid('Frozen release exceeds the 40 MiB training limit.')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _invalid('Frozen release SHA-256 does not match its identity.')
    try:
        from PIL import Image
        from image_classification_export import CONSUMER, FORMAT, SPLIT_MAPPING
    except ImportError as error:
        raise TrainingError('unavailable', 'Pillow and the local export contract are required.') from error
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_IMAGES + 2 or len(set(names)) != len(names):
                _invalid('Frozen release has duplicate or too many ZIP entries.')
            if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
                _invalid('Frozen release exceeds the 64 MiB expanded limit.')
            for info in infos:
                name = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (name.is_absolute() or '..' in name.parts or '\\' in info.filename
                        or str(name) != info.filename or info.is_dir()
                        or info.flag_bits & 1 or stat.S_ISLNK(mode)
                        or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))):
                    _invalid('Frozen release contains an unsafe ZIP entry.')
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > MAX_MANIFEST_BYTES:
                _invalid('Frozen release manifest is missing or exceeds 1 MiB.')
            manifest = _json(archive.read('manifest.json'), 'Release manifest')
            if not isinstance(manifest, dict):
                _invalid('Release manifest must be an object.')
            if manifest.get('schema_version') != 1 or type(manifest.get('schema_version')) is not int:
                raise TrainingError('unsupported', 'Only release schema version 1 is supported.')
            if manifest.get('format') != FORMAT:
                raise TrainingError('unsupported', 'Only frozen image_classification_v1 releases can train.')
            if manifest.get('consumer') != CONSUMER or manifest.get('split_mapping') != SPLIT_MAPPING:
                _invalid('Frozen consumer or split mapping differs from image_classification_v1.')
            vocabulary = manifest.get('class_vocabulary')
            if not isinstance(vocabulary, list) or not 2 <= len(vocabulary) <= MAX_CLASSES:
                _invalid('Training requires 2–8 classes.')
            labels = []
            for index, item in enumerate(vocabulary):
                if (not isinstance(item, dict) or set(item) != {'label', 'folder', 'index'}
                        or type(item['index']) is not int or item['index'] != index
                        or item['folder'] != f'class_{index:06d}'
                        or not isinstance(item['label'], str) or not item['label'].strip()
                        or item['label'].strip() != item['label']
                        or len(item['label']) > 200 or any(0xD800 <= ord(c) <= 0xDFFF for c in item['label'])):
                    _invalid('Frozen class vocabulary is invalid.')
                labels.append(item['label'])
            if labels != sorted(set(labels)):
                _invalid('Frozen class labels must be unique and sorted without normalization.')
            mapping = {item['folder']: item['index'] for item in vocabulary}
            if (manifest.get('class_to_idx') != mapping or not isinstance(manifest.get('class_to_idx'), dict)
                    or any(type(index) is not int for index in manifest['class_to_idx'].values())):
                _invalid('Frozen class_to_idx does not match the vocabulary.')
            records, components = manifest.get('records'), manifest.get('protected_components')
            if not isinstance(records, list) or not 6 <= len(records) <= MAX_IMAGES:
                _invalid('Training requires 6–128 frozen image records.')
            if not isinstance(components, dict):
                _invalid('Frozen release must preserve protected components.')
            seen, assets, groups, pixels = set(), {}, {}, {}
            coverage = {split: set() for split in SPLIT_MAPPING}
            for row in records:
                if not isinstance(row, dict):
                    _invalid('Frozen record must be an object.')
                record_id = row.get('id')
                if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id) or record_id in seen:
                    _invalid('Frozen record identifiers must be canonical and unique.')
                seen.add(record_id)
                if (row.get('kind') != 'image' or row.get('task') != 'image_classification'
                        or row.get('review') != 'human_reviewed'):
                    _invalid('Every frozen image requires human-reviewed classification.')
                if any(type(row.get(key)) is not int or row[key] < 1 for key in ('revision', 'source_revision')):
                    _invalid('Frozen record revisions must be positive integers.')
                if any(not isinstance(row.get(key), str) or not HASH.fullmatch(row[key]) for key in
                       ('source_sha256', 'content_hash', 'pixel_hash', 'asset_sha256', 'exported_pixel_sha256')):
                    _invalid('Frozen record source, asset and pixel hashes are required.')
                index, split = row.get('class_index'), row.get('split')
                if (type(index) is not int or not 0 <= index < len(vocabulary)
                        or not isinstance(split, str) or split not in SPLIT_MAPPING):
                    _invalid('Frozen record class index or split is invalid.')
                item = vocabulary[index]
                asset = f'{SPLIT_MAPPING[split]}/{item["folder"]}/{record_id}.png'
                if (row.get('class_folder') != item['folder'] or row.get('annotation') != {'label': item['label']}
                        or row.get('export_split') != SPLIT_MAPPING[split] or row.get('asset') != asset
                        or row['asset_sha256'] != row['content_hash']
                        or row['exported_pixel_sha256'] != row['pixel_hash'] or asset not in names):
                    _invalid('Frozen record class, asset or hash mapping is inconsistent.')
                group = row.get('export_group')
                if (not isinstance(group, str) or group not in components
                        or not isinstance(components[group], list)
                        or not any(isinstance(member, dict) and member.get('id') == record_id for member in components[group])):
                    _invalid('Frozen record is missing its protected component evidence.')
                for identities, key in ((groups, group), (pixels, row['pixel_hash'])):
                    if key in identities and identities[key] != split:
                        _invalid('Frozen family or duplicate pixels cross split boundaries.')
                    identities[key] = split
                asset_raw = archive.read(asset)
                if hashlib.sha256(asset_raw).hexdigest() != row['asset_sha256']:
                    _invalid('Frozen image asset SHA-256 does not match its manifest.')
                with Image.open(io.BytesIO(asset_raw)) as image:
                    if (image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1
                            or max(image.size) > MAX_IMAGE_DIMENSION or image.width * image.height > MAX_IMAGE_PIXELS):
                        _invalid('Frozen image exceeds the single PNG dimension/pixel limits.')
                    rgb = image.convert('RGB')
                    pixel_hash = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                    if (pixel_hash != row['exported_pixel_sha256']
                            or (row.get('width'), row.get('height')) != rgb.size):
                        _invalid('Frozen decoded pixels or dimensions do not match their manifest.')
                assets[asset] = asset_raw
                coverage[split].add(index)
            if set(names) != set(assets) | {'manifest.json', 'README.txt'}:
                _invalid('Frozen release contains undeclared or missing files.')
            if any(indices != set(range(len(vocabulary))) for indices in coverage.values()):
                _invalid('Every frozen split must contain every class; no records are dropped or reassigned.')
            return manifest, assets
    except (zipfile.BadZipFile, KeyError, OSError, ValueError, NotImplementedError,
            Image.DecompressionBombError) as error:
        if isinstance(error, TrainingError):
            raise
        raise TrainingError('invalid', 'Frozen release ZIP or image bytes cannot be decoded.') from error


def inspect_release(path, expected_sha256):
    """Check the immutable consumer boundary without importing the training runtime."""
    return _read_release(path, expected_sha256)[0]


def probe_runtime(model_aware=False):
    runtime, problems = {'python': platform.python_version(), 'device': 'cpu', 'threads': 1}, []
    if sys.platform != 'linux':
        problems.append({'code': 'unsupported', 'message': 'The supervised CPU adapter currently requires Linux.'})
    for name, expected in RUNTIME_PINS.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = None
        runtime[name.replace('-', '_')] = actual
        if actual != expected:
            problems.append({'code': 'unavailable', 'message': f'{name}=={expected} is required.'})
    if not problems:
        try:
            import torch
            import torchvision
            import sklearn.metrics
            if torch.version.cuda is not None or not callable(torchvision.datasets.ImageFolder):
                raise RuntimeError('CPU runtime mismatch')
            torch.zeros(1).add_(1)
        except Exception:
            problems.append({'code': 'unavailable', 'message': 'Pinned CPU training dependencies could not load.'})
    return {'schema_version': 1, 'available': not problems, 'adapter': dict(MODEL_ADAPTER if model_aware else ADAPTER),
            'runtime': runtime, 'problems': problems}


def guard_parent(parent_pid):
    """Arm Linux parent-death kill before heavy imports; the run owner retains wait()."""
    if sys.platform != 'linux':
        raise TrainingError('unsupported', 'Parent-death supervision currently requires Linux.')
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
            raise OSError(ctypes.get_errno(), 'prctl')
    except (AttributeError, OSError) as error:
        raise TrainingError('unavailable', 'Parent-death supervision could not be armed.') from error
    if os.getppid() != parent_pid:
        raise TrainingError('unavailable', 'The owning training process has already changed.')


def _emit(event, **fields):
    print(json.dumps({'schema_version': 1, 'event': event, **fields}, allow_nan=False,
                     ensure_ascii=True, separators=(',', ':')), flush=True)


def _write_json(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=True, sort_keys=True, allow_nan=False, separators=(',', ':'))
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def train(job):
    """Produce private staged results. The supervisor separately verifies/publishes."""
    job = _checked_job(job)
    guard_parent(job['parent_pid'])
    started = time.monotonic()
    manifest, assets = _read_release(job['release_path'], job['release_sha256'])
    model_aware = job['schema_version'] == 2
    readiness = probe_runtime(model_aware)
    if not readiness['available']:
        raise TrainingError('unavailable', '; '.join(item['message'] for item in readiness['problems']))
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from torchvision import datasets, transforms
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
    import resource

    output = Path(job['output_dir'])
    if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
        _invalid('The run owner must supply an existing empty output directory.')
    params = job['parameters']
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(params['seed'])
    torch.use_deterministic_algorithms(True)
    identity = {key: job[key] for key in ('dataset_id', 'run_id', 'graph_sha256', 'release_id', 'release_sha256')}
    envelope = {'schema_version': 1, 'adapter': dict(MODEL_ADAPTER if model_aware else ADAPTER), 'source_identity': identity}
    transform = transform_for_parameters(params)
    checkpoints = []
    context = job.get('evidence_context')
    updates = 0
    vocabulary, mapping = manifest['class_vocabulary'], manifest['class_to_idx']
    by_asset = {row['asset']: row for row in manifest['records']}
    history, best_loss, best_epoch = [], math.inf, None
    # A new private directory holds only verified bytes, never extractall paths.
    with tempfile.TemporaryDirectory(prefix='.images-', dir=output.parent) as extracted:
        root = Path(extracted)
        for name, raw in assets.items():
            destination = root.joinpath(*PurePosixPath(name).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        preprocessing = transforms.Compose([transforms.Resize(tuple(transform['size'])), transforms.ToTensor()])
        data = {split: datasets.ImageFolder(root / folder, transform=preprocessing)
                for split, folder in manifest['split_mapping'].items()}
        for split, source in data.items():
            if source.class_to_idx != mapping:
                _invalid('Actual ImageFolder class indices differ from the frozen vocabulary.')
            expected = {row['asset'] for row in manifest['records'] if row['split'] == split}
            if {Path(path).relative_to(root).as_posix() for path, _ in source.samples} != expected:
                _invalid('Actual ImageFolder membership differs from the frozen release.')
        loaders = {split: DataLoader(source, batch_size=params['batch_size'], shuffle=split == 'train',
                                      num_workers=0, generator=torch.Generator().manual_seed(params['seed']))
                   for split, source in data.items()}
        model = build_model(torch, params.get('widths', [16, 32, 64]), len(vocabulary))
        optimizer = torch.optim.AdamW(model.parameters(), lr=params['learning_rate'], weight_decay=0.0001)

        @torch.no_grad()
        def evaluate(split, include_rows=False, include_logits=False):
            model.eval()
            truth, predicted, scores, raw_logits, loss_sum = [], [], [], [], 0.0
            for x, y in loaders[split]:
                logits = model(x)
                loss_sum += float(nn.functional.cross_entropy(logits, y)) * len(x)
                truth.extend(y.tolist())
                predicted.extend(logits.argmax(1).tolist())
                if include_rows:
                    scores.extend(logits.softmax(1).tolist())
                    raw_logits.extend(logits.tolist())
            metrics = {'split': split, 'examples': len(truth), 'loss': loss_sum / len(truth),
                       'accuracy': float(accuracy_score(truth, predicted)),
                       'macro_f1': float(f1_score(truth, predicted, average='macro',
                                                labels=list(range(len(vocabulary))), zero_division=0)),
                       'confusion_matrix': confusion_matrix(truth, predicted, labels=list(range(len(vocabulary)))).tolist()}
            rows = []
            if include_rows:
                for (path, target), prediction, probability in zip(data[split].samples, predicted, scores, strict=True):
                    frozen = by_asset[Path(path).relative_to(root).as_posix()]
                    if target != frozen['class_index']:
                        _invalid('ImageFolder target differs from the frozen record class.')
                    rows.append({**{key: frozen[key] for key in ('id', 'revision', 'source_revision',
                                 'source_sha256', 'asset_sha256', 'exported_pixel_sha256')},
                                 'split': split, 'truth_label': vocabulary[target]['label'], 'truth_index': target,
                                 'predicted_label': vocabulary[prediction]['label'], 'predicted_index': prediction,
                                 'probabilities': probability})
                    if include_logits:
                        rows[-1]['logits'] = raw_logits[len(rows)-1]
            return metrics, rows

        _emit('started', epochs=params['epochs'])
        for epoch in range(1, params['epochs'] + 1):
            model.train()
            training_loss = 0.0
            for x, y in loaders['train']:
                optimizer.zero_grad(set_to_none=True)
                loss = nn.functional.cross_entropy(model(x), y)
                if not torch.isfinite(loss):
                    raise TrainingError('failed', 'Training produced a nonfinite loss.')
                loss.backward()
                optimizer.step()
                updates += 1
                training_loss += float(loss.detach()) * len(x)
            validation, probe_rows = evaluate('validation', model_aware, model_aware)
            history.append({'epoch': epoch, 'training_loss': training_loss / len(data['train']), 'validation': validation})
            if validation['loss'] < best_loss:
                best_loss, best_epoch = validation['loss'], epoch
                torch.save({**envelope, 'state_dict': model.state_dict(), 'class_vocabulary': vocabulary,
                            'class_to_idx': mapping, 'parameters': params, 'transform': transform,
                            'epoch': epoch}, output / 'checkpoint.pt')
            if model_aware:
                from model_evidence import capture_epoch
                checkpoint = {**envelope, 'state_dict': model.state_dict(), 'class_vocabulary': vocabulary,
                              'class_to_idx': mapping, 'parameters': params, 'transform': transform, 'epoch': epoch}
                checkpoints.append(capture_epoch(output, checkpoint, validation, probe_rows, manifest, torch, context,
                    {'optimizer_update': updates, 'epoch': epoch, 'fit_pass': None, 'physical_time': None,
                     'wall_elapsed_ms': int((time.monotonic()-started)*1000)}))
            _emit('epoch', epoch=epoch, epochs=params['epochs'], validation=validation)
        if model_aware:
            shutil.copyfile(output / f'weights-epoch-{best_epoch:04d}.pt', output / 'checkpoint.pt')
        saved = torch.load(output / 'checkpoint.pt', map_location='cpu', weights_only=True)
        model.load_state_dict(saved['state_dict'])
        validation, validation_rows = evaluate('validation', True)
        # Test is evaluated exactly once after checkpoint selection. Its content
        # never enters the default metrics or bounded progress stream.
        test, test_rows = evaluate('test', True)
        runtime = dict(readiness['runtime'], elapsed_seconds=time.monotonic() - started,
                       peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        _write_json(output / 'metrics.json', {**envelope, 'parameters': params, 'transform': transform,
                    'class_vocabulary': vocabulary, 'class_to_idx': mapping, 'validation': validation,
                    'history': history, 'best_epoch': best_epoch, 'runtime': runtime})
        _write_json(output / 'test-metrics.json', {**envelope, 'split': 'test', 'metrics': test})
        for split, rows in (('validation', validation_rows), ('test', test_rows)):
            _write_json(output / f'predictions-{split}.json', {**envelope, 'split': split,
                        'class_vocabulary': vocabulary, 'class_to_idx': mapping, 'rows': rows})
    if model_aware:
        from model_evidence import finish_capture
        finish_capture(output, envelope, checkpoints, best_epoch, context)
    artifacts = []
    entries = [('metrics.json', 'validation'), ('test-metrics.json', 'test'),
                        ('predictions-validation.json', 'validation'), ('predictions-test.json', 'test'),
                        ('checkpoint.pt', None)]
    if model_aware:
        from model_evidence import payload_names
        entries.extend((name, 'validation' if name.startswith('probes-') else None)
                       for name in sorted(payload_names(params['epochs']) - {item[0] for item in entries}))
    for name, split in entries:
        with (output / name).open('rb') as handle:
            raw = handle.read()
            os.fsync(handle.fileno())
        artifacts.append({'name': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                          'media_type': 'application/json' if name.endswith('.json') else 'application/octet-stream',
                          'split': split})
    _write_json(output / 'artifact-manifest.json', {**envelope, 'artifacts': artifacts})
    _emit('completed', epochs=params['epochs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--probe', action='store_true')
    action.add_argument('--job', type=Path)
    action.add_argument('--verify-evidence', type=Path)
    parser.add_argument('--model-aware', action='store_true')
    args = parser.parse_args()
    try:
        if args.probe:
            result = probe_runtime(args.model_aware)
            print(json.dumps(result, allow_nan=False), flush=True)
            return 0 if result['available'] else 2
        if args.verify_evidence:
            from model_evidence import replay_checkpoints
            replay_checkpoints(args.verify_evidence)
            return 0
        with args.job.open('rb') as handle:
            raw = handle.read(MAX_JOB_BYTES + 1)
        if len(raw) > MAX_JOB_BYTES:
            _invalid('Training job exceeds 16 KiB.')
        train(_json(raw, 'Training job'))
        return 0
    except TrainingError as error:
        _emit('failed', outcome=error.outcome, message=str(error)[:400])
        return 2
    except Exception as error:
        # Paths, arbitrary labels and held-out metrics are not diagnostic text.
        _emit('failed', outcome='failed', message=f'Training adapter failed ({type(error).__name__}).')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
