"""Bounded source-channel PCM feature classification, with data-only models.

Runs owns admission and process lifecycle. This adapter owns checked frozen
audio, fixed measurements and train-only scaling/classification. No ASR.
"""
import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import sys
import time
import zipfile

import audio_assets
import audio_classification_export as projection
from frozen_classification import validate_families
from image_training import TrainingError, HASH, IDENTIFIER, _json, _invalid, guard_parent, _emit, _write_json
from workbench import WorkbenchError, encode

ADAPTER = {'name': 'audio_features_logistic_cpu', 'version': 1}
PARAMETER_BOUNDS = {'C': {'minimum': 0.01, 'maximum': 100, 'default': 1, 'type': 'number'}}
FEATURE_NAMES = ['mean', 'rms', 'zero_crossing_fraction', 'spectral_centroid_nyquist',
                 'power_0_25', 'power_25_50', 'power_50_75', 'power_75_100']
TRANSFORM = {'name': 'pcm_interval_features', 'version': 1, 'fit_scope': 'train',
             'features': FEATURE_NAMES, 'sample_scale': 32768, 'window': 'rectangular',
             'spectrum': 'numpy_rfft_power_undoubled', 'zero_sign': 'nonnegative',
             'centroid_weight': 'power', 'band_edges': 'lower_included_upper_excluded_last_included', 'band_edges_nyquist': [0, .25, .5, .75, 1],
             'standardization': 'train_mean_population_std', 'solver': 'lbfgs', 'max_iter': 200, 'tol': 1e-6}
MAX_ZIP_BYTES = MAX_EXPANDED_BYTES = 48 * 1024**2
MAX_JOB_BYTES = 16 * 1024
REFERENCE_KEYS = ('id', 'revision', 'source_revision', 'source_sha256', 'asset_sha256',
                  'pcm_sha256', 'audio_family_sha256', 'sample_rate_hz', 'channels',
                  'channel', 'start_frame', 'end_frame')


def validate_parameters(value):
    if not isinstance(value, dict) or set(value) != {'C'}:
        _invalid('Supply exactly C for the audio classifier.')
    number = value['C']
    if type(number) not in (int, float) or not math.isfinite(number) or not .01 <= number <= 100:
        _invalid('C must be a finite number from 0.01 to 100.')
    return dict(value)


def _read_release(path, expected_sha256):
    """Return the validated manifest and the exact owned bytes it describes."""
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        _invalid('Expected audio release SHA-256 is invalid.')
    try:
        with Path(path).open('rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                _invalid('Frozen release must be a regular file.')
            raw = handle.read(MAX_ZIP_BYTES + 1)
    except OSError as error:
        raise TrainingError('unavailable', 'Frozen audio release bytes are unavailable.') from error
    if len(raw) > MAX_ZIP_BYTES:
        _invalid('Frozen audio release exceeds the 48 MiB archive limit.')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _invalid('Frozen audio release SHA-256 does not match its identity.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) > projection.MAX_RECORDS + 5 or len(names) != len(set(names)):
                _invalid('Audio release has duplicate or too many ZIP entries.')
            if sum(item.file_size for item in infos) > MAX_EXPANDED_BYTES:
                _invalid('Frozen audio release exceeds the 48 MiB expanded limit.')
            for item in infos:
                name, mode = PurePosixPath(item.filename), item.external_attr >> 16
                if (name.is_absolute() or '..' in name.parts or '\\' in item.filename or str(name) != item.filename
                        or item.is_dir() or item.flag_bits & 1 or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                    _invalid('Audio release contains an unsafe ZIP entry.')
            metadata_names = {'manifest.json', 'README.txt'} | {split + '/records.jsonl' for split in projection.SPLITS}
            if not metadata_names <= set(names) or sum(archive.getinfo(name).file_size for name in metadata_names) > projection.MAX_METADATA_BYTES:
                _invalid('Frozen audio metadata is absent or exceeds 7 MiB.')
            value = _json(archive.read('manifest.json'), 'Audio release manifest')
            if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
                raise TrainingError('unsupported', 'Only audio release schema 1 is supported.')
            if value.get('format') != projection.FORMAT:
                raise TrainingError('unsupported', 'Choose a frozen audio_classification_v1 release.')
            if value.get('consumer') != projection.CONSUMER or value.get('audio_contract') != projection.CONTRACT:
                _invalid('Frozen audio consumer or source-coordinate contract differs.')
            records = value.get('records')
            if not isinstance(records, list) or not 6 <= len(records) <= projection.MAX_RECORDS:
                _invalid('Audio training requires 6–256 frozen recordings.')
            seen, assets, families = set(), set(), {}
            total_bytes = total_frames = 0
            for row in records:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not IDENTIFIER.fullmatch(row['id']) or row['id'] in seen:
                    _invalid('Frozen audio identifiers must be canonical and unique.')
                seen.add(row['id'])
                if row.get('source_lineage_known') is not True:
                    _invalid('Frozen audio requires known source lineage.')
                if any(type(row.get(key)) is not int or row[key] < 1 for key in ('revision', 'source_revision')):
                    _invalid('Frozen audio revisions must be positive integers.')
                if any(not isinstance(row.get(key), str) or not HASH.fullmatch(row[key]) for key in
                       ('content_hash', 'source_sha256', 'asset_sha256', 'pcm_sha256', 'audio_family_sha256')):
                    _invalid('Frozen audio requires original and decoded PCM hashes.')
                segment = projection.target(row)
                asset = 'assets/' + row['id'] + '.wav'
                if row.get('asset') != asset or archive.getinfo(asset).file_size > audio_assets.MAX_WAV_BYTES:
                    _invalid('Frozen audio asset reference or size is invalid.')
                source = archive.read(asset)
                meta, _ = audio_assets.parse_wav(source)
                digest = hashlib.sha256(source).hexdigest()
                family = hashlib.sha256(encode([meta['sample_rate_hz'], meta['channels'], meta['pcm_sha256']]).encode()).hexdigest()
                mandatory = ['audio-source:' + digest, 'audio-family:' + family]
                if any(row[key] != digest for key in ('source_sha256', 'asset_sha256', 'content_hash')):
                    _invalid('Frozen audio original bytes differ from their source references.')
                if row.get('audio') != dict(meta, protected_groups=mandatory) or not set(mandatory) <= set(row['groups']):
                    _invalid('Frozen audio metadata or mandatory protected families differ from decoded WAV.')
                if (row['pcm_sha256'] != meta['pcm_sha256'] or row['audio_family_sha256'] != family
                        or any(type(row.get(key)) is not int or row[key] != meta[key] for key in ('sample_rate_hz', 'channels'))
                        or any(type(row.get(key)) is not int or row[key] != segment[key] for key in ('channel', 'start_frame', 'end_frame'))
                        or row.get('target_label') != segment['label']):
                    _invalid('Frozen audio projection differs from its reviewed source interval.')
                split = row.get('split')
                if split not in projection.SPLITS:
                    _invalid('Frozen audio split is invalid.')
                if family in families and families[family] != split:
                    _invalid('Identical decoded PCM crosses split boundaries.')
                families[family] = split
                assets.add(asset)
                total_bytes += len(source)
                total_frames += segment['end_frame'] - segment['start_frame']
            if total_bytes > projection.MAX_SOURCE_BYTES or total_frames > projection.MAX_TOTAL_FRAMES:
                _invalid('Frozen audio exceeds the total source-byte or analyzed-frame bound.')
            vocabulary, _, blockers = projection.inspect_projection(records, {row['id']: row['split'] for row in records})
            if blockers:
                _invalid(blockers[0])
            mapping = {item['label']: item['index'] for item in vocabulary}
            if (value.get('class_vocabulary') != vocabulary or value.get('class_to_idx') != mapping
                    or any(type(item.get('index')) is not int for item in value['class_vocabulary'])
                    or any(type(index) is not int for index in value['class_to_idx'].values())):
                _invalid('Frozen audio vocabulary differs from its exact labels.')
            if any(type(row.get('class_index')) is not int or row['class_index'] != mapping[row['target_label']] for row in records):
                _invalid('Frozen audio class indices differ from their labels.')
            for split in projection.SPLITS:
                actual = [_json(line, 'Audio split row') for line in archive.read(split + '/records.jsonl').splitlines()]
                if actual != [row for row in records if row['split'] == split]:
                    _invalid('Frozen audio JSONL differs from its manifest mapping.')
            validate_families(value, 'audio')
            if set(names) != assets | metadata_names:
                _invalid('Audio release contains undeclared or missing files.')
            return value, raw
    except (zipfile.BadZipFile, KeyError, OSError, ValueError, TypeError, UnicodeError, NotImplementedError) as error:
        if isinstance(error, TrainingError):
            raise
        if isinstance(error, WorkbenchError):
            raise TrainingError('invalid', str(error)) from None
        raise TrainingError('invalid', 'Frozen audio ZIP or metadata cannot be decoded.') from error


def inspect_release(path, expected_sha256):
    return _read_release(path, expected_sha256)[0]


def probe_runtime():
    runtime, problems = {'python': platform.python_version(), 'device': 'cpu', 'threads': 1}, []
    if sys.platform != 'linux':
        problems.append({'code': 'unsupported', 'message': 'The supervised audio adapter requires Linux.'})
    for package in ('scikit-learn', 'numpy', 'scipy', 'Pillow'):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = None
        runtime[package.replace('-', '_')] = version
        if version is None or (package == 'scikit-learn' and version != '1.7.2'):
            problems.append({'code': 'unavailable', 'message': package + ('==1.7.2' if package == 'scikit-learn' else '') + ' is required.'})
    if not problems:
        try:
            from sklearn.linear_model import LogisticRegression
            LogisticRegression(solver='lbfgs').fit([[0] * 8, [1] * 8], [0, 1])
            from threadpoolctl import threadpool_info
            runtime['threads'] = max((item['num_threads'] for item in threadpool_info()), default=1)
            if runtime['threads'] != 1:
                problems.append({'code': 'unavailable', 'message': 'CPU math libraries must be limited to one thread.'})
        except Exception:
            problems.append({'code': 'unavailable', 'message': 'The pinned local audio runtime could not load.'})
    return {'schema_version': 1, 'available': not problems, 'adapter': dict(ADAPTER), 'runtime': runtime, 'problems': problems}


def extract_features(raw, start_frame, end_frame, channel):
    """Measure only the exact source-channel interval; never publish changed audio."""
    meta, pcm = audio_assets.parse_wav(raw)
    if (type(start_frame) is not int or type(end_frame) is not int or type(channel) is not int
            or not 0 <= channel < meta['channels'] or not 0 <= start_frame < end_frame <= meta['frame_count']
            or not projection.MIN_FRAMES <= end_frame - start_frame <= projection.MAX_FRAMES
            or end_frame - start_frame > meta['sample_rate_hz'] * 10):
        _invalid('Feature input must be an eligible source-frame interval and channel.')
    import numpy as np
    samples = np.frombuffer(pcm, dtype='<i2').reshape(-1, meta['channels'])[start_frame:end_frame, channel].astype(np.float64) / 32768
    power = np.abs(np.fft.rfft(samples)) ** 2
    frequency = np.fft.rfftfreq(len(samples)) * 2
    total = float(power.sum())
    # Zero is nonnegative. DC is in the first band, Nyquist in the last;
    # one-sided power is intentionally not doubled and uses actual odd-N bins.
    bands = [float(power[(frequency >= low) & ((frequency < high) if high < 1 else (frequency <= high))].sum() / total)
             if total else 0.0 for low, high in zip((0, .25, .5, .75), (.25, .5, .75, 1))]
    return [float(samples.mean()), float(np.sqrt(np.mean(samples ** 2))),
            float(np.mean(np.signbit(samples[1:]) != np.signbit(samples[:-1]))),
            float(np.dot(frequency, power) / total) if total else 0.0, *bands]


def validate_model(model):
    required = {'schema_version', 'source_identity', 'adapter', 'parameters', 'transform',
                'class_vocabulary', 'class_to_idx', 'mean', 'scale', 'coefficients', 'intercepts'}
    if (not isinstance(model, dict) or set(model) != required or type(model['schema_version']) is not int
            or model['schema_version'] != 1 or model['adapter'] != ADAPTER or type(model['adapter'].get('version')) is not int):
        _invalid('Unsupported audio model envelope.')
    identity = model['source_identity']
    if not isinstance(identity, dict) or set(identity) != {'dataset_id', 'run_id', 'graph_sha256', 'release_id', 'release_sha256'}:
        _invalid('Audio model source identity is invalid.')
    for key, value in identity.items():
        pattern = IDENTIFIER if key in ('dataset_id', 'run_id') else HASH
        if not isinstance(value, str) or not pattern.fullmatch(value):
            _invalid('Audio model source identity is invalid.')
    if identity['release_id'] != identity['release_sha256']:
        _invalid('Audio model release identity differs from its digest.')
    validate_parameters(model['parameters'])
    if model['transform'] != TRANSFORM:
        _invalid('Audio model transform differs from the fixed recipe.')
    classes, mapping = model['class_vocabulary'], model['class_to_idx']
    if not isinstance(classes, list) or not 2 <= len(classes) <= projection.MAX_CLASSES or not isinstance(mapping, dict):
        _invalid('Audio model classes are invalid.')
    labels = [item.get('label') if isinstance(item, dict) else None for item in classes]
    if (any(not isinstance(label, str) or not label or label.strip() != label or len(label) > 80 for label in labels)
            or labels != sorted(set(labels)) or classes != [{'label': label, 'index': index} for index, label in enumerate(labels)]
            or mapping != {label: index for index, label in enumerate(labels)}
            or any(type(item['index']) is not int for item in classes) or any(type(index) is not int for index in mapping.values())):
        _invalid('Audio model class mapping is invalid.')
    def vector(values, length, low, high):
        return isinstance(values, list) and len(values) == length and all(type(n) in (int, float) and math.isfinite(n) and low <= n <= high for n in values)
    count = 1 if len(classes) == 2 else len(classes)
    if (not vector(model['mean'], 8, -1, 1) or not vector(model['scale'], 8, 0, 10)
            or any(n <= 0 for n in model['scale']) or not vector(model['intercepts'], count, -1e6, 1e6)
            or not isinstance(model['coefficients'], list) or len(model['coefficients']) != count
            or any(not vector(row, 8, -1e6, 1e6) for row in model['coefficients'])):
        _invalid('Audio model numeric arrays are invalid.')
    return model


def predict_features(model, features):
    """Cold data-only reader: scaling and stable logistic/softmax, no estimator load."""
    validate_model(model)
    probabilities = []
    for row in features:
        if len(row) != 8 or any(type(value) not in (int, float) or not math.isfinite(value) for value in row):
            _invalid('Audio feature vector is invalid.')
        scaled = [(value - mean) / scale for value, mean, scale in zip(row, model['mean'], model['scale'], strict=True)]
        scores = [sum(weight * value for weight, value in zip(weights, scaled, strict=True)) + bias
                  for weights, bias in zip(model['coefficients'], model['intercepts'], strict=True)]
        if len(scores) == 1:
            score = scores[0]
            positive = 1 / (1 + math.exp(-score)) if score >= 0 else math.exp(score) / (1 + math.exp(score))
            probabilities.append([1 - positive, positive])
        else:
            maximum = max(scores)
            weights = [math.exp(score - maximum) for score in scores]
            total = sum(weights)
            probabilities.append([weight / total for weight in weights])
    return probabilities


def _checked_job(value):
    fields = {'schema_version', 'dataset_id', 'run_id', 'graph_sha256', 'release_id',
              'release_sha256', 'release_path', 'output_dir', 'parameters', 'parent_pid'}
    if not isinstance(value, dict) or set(value) != fields:
        _invalid('Training job must contain exactly the version 1 job fields.')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
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
        if not isinstance(value[key], str) or '\0' in value[key] or not Path(value[key]).is_absolute():
            _invalid(f'{key} must be an absolute path supplied by the run owner.')
    if type(value['parent_pid']) is not int or value['parent_pid'] < 1:
        _invalid('parent_pid must identify the owning local process.')
    return dict(value, parameters=validate_parameters(value['parameters']))



def train(job):
    job = _checked_job(job)
    guard_parent(job['parent_pid'])
    started = time.monotonic()
    manifest, release_bytes = _read_release(job['release_path'], job['release_sha256'])
    readiness = probe_runtime()
    if not readiness['available']:
        raise TrainingError('unavailable', '; '.join(item['message'] for item in readiness['problems']))
    import numpy as np
    import resource
    import warnings
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
    output = Path(job['output_dir'])
    if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
        _invalid('The run owner must supply an existing empty output directory.')
    parameters = job['parameters']
    identity = {key: job[key] for key in ('dataset_id', 'run_id', 'graph_sha256', 'release_id', 'release_sha256')}
    envelope = {'schema_version': 1, 'adapter': dict(ADAPTER), 'source_identity': identity}
    vocabulary, mapping = manifest['class_vocabulary'], manifest['class_to_idx']
    splits = {split: [row for row in manifest['records'] if row['split'] == split] for split in projection.SPLITS}
    _emit('started', epochs=1)
    # Never reopen the path after verification: a concurrent file replacement
    # must not change the samples bound to this attempt's frozen identity.
    with zipfile.ZipFile(io.BytesIO(release_bytes)) as archive:
        features = {row['id']: extract_features(archive.read(row['asset']), row['start_frame'], row['end_frame'], row['channel'])
                    for row in manifest['records']}
    x = [features[row['id']] for row in splits['train']]
    scaler = StandardScaler().fit(x)
    transformed = scaler.transform(x)
    estimator = LogisticRegression(C=parameters['C'], solver='lbfgs', max_iter=200, tol=1e-6)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            estimator.fit(transformed, [row['class_index'] for row in splits['train']])
    except ConvergenceWarning as error:
        raise TrainingError('failed', 'Audio classifier did not converge within 200 iterations; inspect the data or choose another C.') from error
    saved = {**envelope, 'parameters': parameters, 'transform': TRANSFORM, 'class_vocabulary': vocabulary,
             'class_to_idx': mapping, 'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
             'coefficients': estimator.coef_.tolist(), 'intercepts': estimator.intercept_.tolist()}
    _write_json(output / 'model.json', saved)
    saved = _json((output / 'model.json').read_bytes(), 'Saved audio model')
    if not np.allclose(predict_features(saved, x), estimator.predict_proba(transformed), rtol=1e-12, atol=1e-12):
        raise TrainingError('failed', 'The saved audio model does not reproduce the fitted estimator.')
    def evaluate(split):
        sources = splits[split]
        probability = np.array(predict_features(saved, [features[row['id']] for row in sources]))
        truth = [row['class_index'] for row in sources]
        predicted = probability.argmax(axis=1)
        labels = list(range(len(vocabulary)))
        metric = {'split': split, 'examples': len(sources), 'loss': float(log_loss(truth, probability, labels=labels)),
                  'accuracy': float(accuracy_score(truth, predicted)),
                  'macro_f1': float(f1_score(truth, predicted, labels=labels, average='macro', zero_division=0)),
                  'confusion_matrix': confusion_matrix(truth, predicted, labels=labels).tolist()}
        rows = [{**{key: source[key] for key in REFERENCE_KEYS}, 'split': split,
                 'truth_label': source['target_label'], 'truth_index': source['class_index'],
                 'predicted_label': vocabulary[int(prediction)]['label'], 'predicted_index': int(prediction),
                 'probabilities': scores.tolist()} for source, prediction, scores in zip(sources, predicted, probability, strict=True)]
        return metric, rows
    training, _ = evaluate('train')
    validation, validation_rows = evaluate('validation')
    _emit('epoch', epoch=1, epochs=1, validation=validation)
    test, test_rows = evaluate('test')
    runtime = dict(readiness['runtime'], elapsed_seconds=time.monotonic() - started,
                   peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    _write_json(output / 'metrics.json', {**envelope, 'parameters': parameters, 'transform': TRANSFORM,
                'class_vocabulary': vocabulary, 'class_to_idx': mapping, 'validation': validation,
                'history': [{'epoch': 1, 'training_loss': training['loss'], 'validation': validation}],
                'best_epoch': 1, 'runtime': runtime})
    _write_json(output / 'test-metrics.json', {**envelope, 'split': 'test', 'metrics': test})
    for split, rows in (('validation', validation_rows), ('test', test_rows)):
        _write_json(output / f'predictions-{split}.json', {**envelope, 'split': split,
                    'class_vocabulary': vocabulary, 'class_to_idx': mapping, 'rows': rows})
    artifacts = []
    for name, split in (('metrics.json', 'validation'), ('test-metrics.json', 'test'),
                        ('predictions-validation.json', 'validation'), ('predictions-test.json', 'test'), ('model.json', None)):
        raw = (output / name).read_bytes()
        artifacts.append({'name': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                          'media_type': 'application/json', 'split': split})
    _write_json(output / 'artifact-manifest.json', {**envelope, 'artifacts': artifacts})
    _emit('completed', epochs=1)


def main():
    for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[variable] = '1'
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--probe', action='store_true')
    action.add_argument('--job', type=Path)
    args = parser.parse_args()
    try:
        if args.probe:
            result = probe_runtime()
            print(json.dumps(result, allow_nan=False), flush=True)
            return 0 if result['available'] else 2
        with args.job.open('rb') as handle:
            raw = handle.read(MAX_JOB_BYTES + 1)
        if len(raw) > MAX_JOB_BYTES:
            _invalid('Training job exceeds 16 KiB.')
        train(_json(raw, 'Audio training job'))
        return 0
    except TrainingError as error:
        _emit('failed', outcome=error.outcome, message=str(error)[:400])
        return 2
    except Exception:
        _emit('failed', outcome='failed', message='Local audio adapter failed; private outputs were not published.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
