"""Closed TF-IDF + MultinomialNB CPU adapter for frozen text classification.

Only this module fits text features. Runs owns admission, process supervision,
publication and exposure. No model download, arbitrary code or pickle loading.
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
import unicodedata
import zipfile

# The existing adapter owns these unchanged bounded JSON/process primitives.
from image_training import TrainingError, HASH, IDENTIFIER, _json, _invalid, guard_parent, _emit, _write_json
import text_classification_export as projection
from frozen_classification import validate_families

ADAPTER = {'name': 'tfidf_multinomial_nb_cpu', 'version': 1}
MODEL_ADAPTER = dict(ADAPTER, version=2)
MODEL_RECIPE = 'text_classification_model_v2'
PARAMETER_BOUNDS = {
    'max_features': {'minimum': 64, 'maximum': 4096, 'default': 1024, 'type': 'integer'},
    'alpha': {'minimum': 0.01, 'maximum': 10, 'default': 1, 'type': 'number'},
}
TRANSFORM = {'name': 'word_tfidf', 'version': 1, 'fit_scope': 'train', 'lowercase': True,
             'token_pattern': r'(?u)\b\w\w+\b', 'ngram_range': [1, 1], 'norm': 'l2',
             'use_idf': True, 'smooth_idf': True, 'sublinear_tf': False}
MAX_ZIP_BYTES, MAX_EXPANDED_BYTES = 8 * 1024**2, 16 * 1024**2
MAX_JOB_BYTES = 16 * 1024
REFERENCE_KEYS = ('id', 'revision', 'source_revision', 'source_sha256', 'asset_sha256', 'content_sha256')


def validate_parameters(value):
    if not isinstance(value, dict) or set(value) != set(PARAMETER_BOUNDS):
        _invalid('Supply exactly max_features and alpha for the text recipe.')
    for name, rule in PARAMETER_BOUNDS.items():
        number = value[name]
        if (not (type(number) is int if rule['type'] == 'integer' else type(number) in (int, float))
                or not rule['minimum'] <= number <= rule['maximum'] or not math.isfinite(number)):
            _invalid(f'{name} must be {rule["type"]} from {rule["minimum"]} to {rule["maximum"]}.')
    return dict(value)


def _checked_job(value):
    fields = {'schema_version', 'dataset_id', 'run_id', 'graph_sha256', 'release_id',
              'release_sha256', 'release_path', 'output_dir', 'parameters', 'parent_pid'}
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] not in (1, 2):
        raise TrainingError('unsupported', 'Only training job schemas 1 and 2 are supported.')
    if value['schema_version'] == 2:
        fields |= {'adapter', 'evidence'}
    if set(value) != fields:
        _invalid('Training job fields differ from its selected schema.')
    if value['schema_version'] == 2:
        from one_fit_evidence import validate_job_selection
        validate_job_selection(value, ADAPTER)
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


def inspect_release(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        _invalid('Expected text release SHA-256 is invalid.')
    try:
        with Path(path).open('rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                _invalid('Frozen release must be a regular file.')
            raw = handle.read(MAX_ZIP_BYTES + 1)
    except OSError as error:
        raise TrainingError('unavailable', 'Frozen text release bytes are unavailable.') from error
    if len(raw) > MAX_ZIP_BYTES:
        _invalid('Frozen text release exceeds the 8 MiB archive limit.')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _invalid('Frozen text release SHA-256 does not match its identity.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) > projection.MAX_RECORDS + 5 or len(names) != len(set(names)):
                _invalid('Text release has duplicate or too many ZIP entries.')
            if sum(item.file_size for item in infos) > MAX_EXPANDED_BYTES:
                _invalid('Frozen text release exceeds the 16 MiB expanded limit.')
            for item in infos:
                name, mode = PurePosixPath(item.filename), item.external_attr >> 16
                if (name.is_absolute() or '..' in name.parts or '\\' in item.filename or str(name) != item.filename
                        or item.is_dir() or item.flag_bits & 1 or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                    _invalid('Text release contains an unsafe ZIP entry.')
            if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size > projection.MAX_PAYLOAD_BYTES:
                _invalid('Frozen text manifest is absent or oversized.')
            manifest = _json(archive.read('manifest.json'), 'Text release manifest')
            if not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1:
                raise TrainingError('unsupported', 'Only text release schema 1 is supported.')
            if manifest.get('format') != projection.FORMAT:
                raise TrainingError('unsupported', 'Choose a frozen text_classification_v1 release.')
            if manifest.get('consumer') != projection.CONSUMER or manifest.get('text_contract') != projection.TEXT_CONTRACT:
                _invalid('Frozen text consumer or normalization contract differs.')
            records = manifest.get('records')
            if not isinstance(records, list) or not 6 <= len(records) <= projection.MAX_RECORDS:
                _invalid('Text training requires 6–512 frozen records.')
            seen, assets, hashes = set(), {}, {}
            for row in records:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not IDENTIFIER.fullmatch(row['id']) or row['id'] in seen:
                    _invalid('Frozen text identifiers must be canonical and unique.')
                seen.add(row['id'])
                if (row.get('kind') != 'text' or row.get('task') != 'text_classification' or row.get('review') != 'human_reviewed'
                        or row.get('source_available') is not True or row.get('source_lineage_known') is not True):
                    _invalid('Every frozen text requires available, human-reviewed classification and known lineage.')
                if any(type(row.get(key)) is not int or row[key] < 1 for key in ('revision', 'source_revision')):
                    _invalid('Frozen text revisions must be positive integers.')
                if any(not isinstance(row.get(key), str) or not HASH.fullmatch(row[key]) for key in ('content_hash', 'asset_sha256', 'source_sha256')):
                    _invalid('Frozen text requires original source and canonical content hashes.')
                value, annotation, split = row.get('text'), row.get('annotation'), row.get('split')
                if not isinstance(value, str) or not value.strip() or '\r' in value or unicodedata.normalize('NFC', value) != value:
                    _invalid('Frozen text must retain canonical NFC/LF content.')
                encoded = value.encode('utf-8')
                if len(encoded) > projection.MAX_TEXT_BYTES:
                    _invalid('Frozen text exceeds 16 KiB of UTF-8.')
                if (not isinstance(annotation, dict) or set(annotation) != {'label'} or not isinstance(annotation['label'], str)
                        or not annotation['label'].strip() or annotation['label'].strip() != annotation['label'] or len(annotation['label']) > 80):
                    _invalid('Frozen text label is invalid.')
                if split not in projection.SPLITS:
                    _invalid('Frozen text split is invalid.')
                asset = 'assets/' + row['id'] + '.txt'
                if row.get('asset') != asset or row['asset_sha256'] != row['content_hash'] or hashlib.sha256(encoded).hexdigest() != row['content_hash']:
                    _invalid('Frozen text content and asset identities differ.')
                if archive.read(asset) != encoded:
                    _invalid('Frozen text asset bytes differ from the manifest.')
                if row['content_hash'] in hashes and hashes[row['content_hash']] != split:
                    _invalid('Identical canonical text crosses split boundaries.')
                hashes[row['content_hash']] = split
                assets[asset] = encoded
            labels = sorted({row['annotation']['label'] for row in records})
            vocabulary = [{'label': label, 'index': index} for index, label in enumerate(labels)]
            if not 2 <= len(labels) <= projection.MAX_CLASSES:
                _invalid('Text training requires 2–8 exact classes.')
            mapping = {item['label']: item['index'] for item in vocabulary}
            if (manifest.get('class_vocabulary') != vocabulary or manifest.get('class_to_idx') != mapping
                    or any(type(item.get('index')) is not int for item in manifest['class_vocabulary'])
                    or any(type(index) is not int for index in manifest['class_to_idx'].values())):
                _invalid('Frozen text vocabulary differs from its exact labels.')
            if any(type(row.get('class_index')) is not int or row['class_index'] != mapping[row['annotation']['label']] for row in records):
                _invalid('Frozen text class indices differ from their labels.')
            for split in projection.SPLITS:
                expected_rows = [row for row in records if row['split'] == split]
                if {row['annotation']['label'] for row in expected_rows} != set(labels):
                    _invalid('Every frozen text split must contain every class; no examples are dropped or reassigned.')
                actual = [_json(line, 'Text split row') for line in archive.read(split + '/records.jsonl').splitlines()]
                if actual != expected_rows:
                    _invalid('Frozen text JSONL differs from its manifest mapping.')
            validate_families(manifest)
            if set(names) != set(assets) | {'manifest.json', 'README.txt'} | {split + '/records.jsonl' for split in projection.SPLITS}:
                _invalid('Text release contains undeclared or missing files.')
            return manifest
    except (zipfile.BadZipFile, KeyError, OSError, ValueError, TypeError, UnicodeError, NotImplementedError) as error:
        if isinstance(error, TrainingError):
            raise
        raise TrainingError('invalid', 'Frozen text ZIP or metadata cannot be decoded.') from error


def probe_runtime(model_aware=False):
    runtime, problems = {'python': platform.python_version(), 'device': 'cpu', 'threads': 1}, []
    if sys.platform != 'linux':
        problems.append({'code': 'unsupported', 'message': 'The supervised text adapter requires Linux.'})
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
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.naive_bayes import MultinomialNB
            MultinomialNB().fit(TfidfVectorizer().fit_transform(['one word', 'other word']), [0, 1])
            from threadpoolctl import threadpool_info
            runtime['threads'] = max((item['num_threads'] for item in threadpool_info()), default=1)
            if runtime['threads'] != 1:
                problems.append({'code': 'unavailable', 'message': 'CPU math libraries must be limited to one thread.'})
        except Exception:
            problems.append({'code': 'unavailable', 'message': 'The pinned local text runtime could not load.'})
    return {'schema_version': 1, 'available': not problems, 'adapter': dict(MODEL_ADAPTER if model_aware else ADAPTER), 'runtime': runtime, 'problems': problems}


def _vectorizer(max_features, vocabulary=None):
    from sklearn.feature_extraction.text import TfidfVectorizer
    return TfidfVectorizer(max_features=max_features, lowercase=TRANSFORM['lowercase'],
                           token_pattern=TRANSFORM['token_pattern'], ngram_range=tuple(TRANSFORM['ngram_range']),
                           norm=TRANSFORM['norm'], use_idf=True, smooth_idf=True, sublinear_tf=False,
                           vocabulary=vocabulary)


def validate_model(model):
    """Decode a data-only model; no imported or uploaded executable checkpoint."""
    required = {'schema_version', 'source_identity', 'adapter', 'parameters', 'transform', 'class_vocabulary',
                'class_to_idx', 'vocabulary', 'idf', 'class_log_prior', 'feature_log_prob'}
    if not isinstance(model, dict) or set(model) != required or type(model['schema_version']) is not int or model['schema_version'] != 1 or model['adapter'] not in (ADAPTER, dict(ADAPTER, version=2)) or type(model['adapter'].get('version')) is not int:
        _invalid('Unsupported text model envelope.')
    identity = model['source_identity']
    if not isinstance(identity, dict) or set(identity) != {'dataset_id', 'run_id', 'graph_sha256', 'release_id', 'release_sha256'}:
        _invalid('Text model source identity is invalid.')
    for key, value in identity.items():
        pattern = IDENTIFIER if key in ('dataset_id', 'run_id') else HASH
        if not isinstance(value, str) or not pattern.fullmatch(value):
            _invalid('Text model source identity is invalid.')
    if identity['release_id'] != identity['release_sha256']:
        _invalid('Text model release identity differs from its digest.')
    parameters = validate_parameters(model['parameters'])
    if model['transform'] != TRANSFORM:
        _invalid('Text model transform differs from the fixed recipe.')
    vocabulary = model['vocabulary']
    if (not isinstance(vocabulary, dict) or not 1 <= len(vocabulary) <= parameters['max_features']
            or any(not isinstance(token, str) or not token or len(token.encode('utf-8')) > projection.MAX_TEXT_BYTES or type(index) is not int for token, index in vocabulary.items())
            or sorted(vocabulary.values()) != list(range(len(vocabulary)))):
        _invalid('Text model vocabulary is invalid.')
    classes = model['class_vocabulary']
    if not isinstance(classes, list) or not 2 <= len(classes) <= projection.MAX_CLASSES:
        _invalid('Text model classes are invalid.')
    labels = [item.get('label') if isinstance(item, dict) else None for item in classes]
    if (any(not isinstance(label, str) or not label or label.strip() != label or len(label) > 80 for label in labels)
            or labels != sorted(set(labels)) or classes != [{'label': label, 'index': index} for index, label in enumerate(labels)]
            or model['class_to_idx'] != {label: index for index, label in enumerate(labels)}
            or any(type(item.get('index')) is not int for item in classes)
            or any(type(index) is not int for index in model['class_to_idx'].values())):
        _invalid('Text model class mapping is invalid.')
    width, count = len(vocabulary), len(classes)
    def vector(values, length, low, high):
        return isinstance(values, list) and len(values) == length and all(type(n) in (int, float) and math.isfinite(n) and low <= n <= high for n in values)
    if (not vector(model['idf'], width, 1, 100) or not vector(model['class_log_prior'], count, -100, 0)
            or not isinstance(model['feature_log_prob'], list) or len(model['feature_log_prob']) != count
            or any(not vector(row, width, -100, 0) for row in model['feature_log_prob'])):
        _invalid('Text model numeric arrays are invalid.')
    return model


def predict_model(model, texts):
    """Cold-read JSON vocabulary/statistics with the same pinned sparse transform."""
    validate_model(model)
    import numpy as np
    from scipy.special import logsumexp
    vectorizer = _vectorizer(model['parameters']['max_features'], model['vocabulary'])
    vectorizer.idf_ = np.array(model['idf'])
    transformed = vectorizer.transform(texts)
    scores = transformed @ np.array(model['feature_log_prob']).T + np.array(model['class_log_prior'])
    return np.exp(scores - logsumexp(scores, axis=1)[:, None])


def verify_evidence(directory, job):
    """Validate v2 evidence against the exact frozen release and JSON reader."""
    job = _checked_job(job)
    if job['schema_version'] != 2:
        raise TrainingError('unsupported', 'Historical one-fit results have no model evidence snapshot.')
    from one_fit_evidence import verify_directory
    manifest = inspect_release(job['release_path'], job['release_sha256'])
    from model_evidence import read_document
    saved = validate_model(read_document(Path(directory), 'model.json'))
    _verify_fit_statistics(saved, [row['text'] for row in manifest['records'] if row['split'] == 'train'])
    manifest = dict(manifest, records=[dict(row, content_sha256=row['content_hash']) for row in manifest['records']])
    inputs = [row['text'] for row in manifest['records'] if row['split'] == 'validation']
    return verify_directory(directory, job=job, adapter=ADAPTER, manifest=manifest,
                            reference_keys=REFERENCE_KEYS, expected_inputs=inputs)


def _verify_fit_statistics(model, texts):
    """Recompute train-only counts and IDF without fitting another estimator."""
    from collections import Counter
    import numpy as np
    analyzer = _vectorizer(model['parameters']['max_features']).build_analyzer()
    documents = [Counter(analyzer(text)) for text in texts]
    frequency = Counter()
    for document in documents:
        frequency.update(document)
    terms = sorted(frequency)
    limit = model['parameters']['max_features']
    # Match the pinned vectorizer's lexically sorted columns and NumPy tie
    # ordering for its frequency cap, rather than selecting held-out features.
    if len(terms) > limit:
        indices = (-np.array([frequency[term] for term in terms], dtype=np.int64)).argsort()[:limit]
        terms = sorted(terms[int(index)] for index in indices)
    vocabulary = {term: index for index, term in enumerate(terms)}
    frequency = np.array([1 + sum(term in document for document in documents) for term in terms], dtype=np.float64)
    expected_idf = np.full_like(frequency, 1 + len(documents)) / frequency
    np.log(expected_idf, out=expected_idf)
    expected_idf += 1
    if model['vocabulary'] != vocabulary or not np.array_equal(model['idf'], expected_idf):
        raise TrainingError('failed', 'Frozen text vocabulary/IDF differ from exact training-only statistics.')


def train(job):
    job = _checked_job(job)
    guard_parent(job['parent_pid'])
    started = time.monotonic()
    manifest = inspect_release(job['release_path'], job['release_sha256'])
    readiness = probe_runtime()
    if not readiness['available']:
        raise TrainingError('unavailable', '; '.join(item['message'] for item in readiness['problems']))
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
    import numpy as np
    import resource
    output = Path(job['output_dir'])
    if output.is_symlink() or not output.is_dir() or any(output.iterdir()):
        _invalid('The run owner must supply an existing empty output directory.')
    params = job['parameters']
    identity = {key: job[key] for key in ('dataset_id', 'run_id', 'graph_sha256', 'release_id', 'release_sha256')}
    selected = job['schema_version'] == 2
    envelope = {'schema_version': 1, 'adapter': dict(job['adapter'] if selected else ADAPTER), 'source_identity': identity}
    vocabulary, mapping = manifest['class_vocabulary'], manifest['class_to_idx']
    splits = {split: [row for row in manifest['records'] if row['split'] == split] for split in projection.SPLITS}
    vectorizer = _vectorizer(params['max_features'])
    _emit('started', epochs=1)
    try:
        x = vectorizer.fit_transform([row['text'] for row in splits['train']])
    except ValueError as error:
        raise TrainingError('invalid', 'Training text contains no usable two-character word tokens.') from error
    model = MultinomialNB(alpha=params['alpha']).fit(x, [row['class_index'] for row in splits['train']])
    fitted_elapsed = time.monotonic() - started
    saved = {**envelope, 'parameters': params, 'transform': TRANSFORM, 'class_vocabulary': vocabulary,
             'class_to_idx': mapping, 'vocabulary': {key: int(index) for key, index in vectorizer.vocabulary_.items()},
             'idf': vectorizer.idf_.tolist(), 'class_log_prior': model.class_log_prior_.tolist(),
             'feature_log_prob': model.feature_log_prob_.tolist()}
    _write_json(output / 'model.json', saved)
    saved = _json((output / 'model.json').read_bytes(), 'Saved text model')
    def evaluate(split):
        sources = splits[split]
        probability = predict_model(saved, [row['text'] for row in sources])
        truth = [row['class_index'] for row in sources]
        predicted = probability.argmax(axis=1)
        labels = list(range(len(vocabulary)))
        metric = {'split': split, 'examples': len(sources), 'loss': float(log_loss(truth, probability, labels=labels)),
                  'accuracy': float(accuracy_score(truth, predicted)),
                  'macro_f1': float(f1_score(truth, predicted, labels=labels, average='macro', zero_division=0)),
                  'confusion_matrix': confusion_matrix(truth, predicted, labels=labels).tolist()}
        rows = [{**{key: source[key] for key in REFERENCE_KEYS if key != 'content_sha256'},
                 'content_sha256': source['content_hash'], 'split': split,
                 'truth_label': source['annotation']['label'], 'truth_index': source['class_index'],
                 'predicted_label': vocabulary[int(prediction)]['label'], 'predicted_index': int(prediction),
                 'probabilities': scores.tolist()} for source, prediction, scores in zip(sources, predicted, probability, strict=True)]
        return metric, rows
    # The persisted JSON reader must reproduce the actual fitted estimator.
    if not np.allclose(predict_model(saved, [row['text'] for row in splits['train']]), model.predict_proba(x), rtol=1e-12, atol=1e-12):
        raise TrainingError('failed', 'The saved text model does not reproduce the fitted estimator.')
    training, _ = evaluate('train')
    validation, validation_rows = evaluate('validation')
    _emit('epoch', epoch=1, epochs=1, validation=validation)
    test, test_rows = evaluate('test')
    runtime = dict(readiness['runtime'], elapsed_seconds=time.monotonic() - started,
                   peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    metrics = {**envelope, 'parameters': params, 'transform': TRANSFORM,
                'class_vocabulary': vocabulary, 'class_to_idx': mapping, 'validation': validation,
                'history': [{'epoch': 1, 'training_loss': training['loss'], 'validation': validation}],
                'best_epoch': 1, 'runtime': runtime}
    if selected:
        from one_fit_evidence import fit_clocks
        metrics.pop('history')
        metrics.pop('best_epoch')
        metrics['clocks'] = fit_clocks(fitted_elapsed)
    _write_json(output / 'metrics.json', metrics)
    _write_json(output / 'test-metrics.json', {**envelope, 'split': 'test', 'metrics': test})
    for split, rows in (('validation', validation_rows), ('test', test_rows)):
        _write_json(output / f'predictions-{split}.json', {**envelope, 'split': split,
                    'class_vocabulary': vocabulary, 'class_to_idx': mapping, 'rows': rows})
    if selected:
        from one_fit_evidence import capture
        capture_manifest = dict(manifest, records=[dict(row, content_sha256=row['content_hash']) for row in manifest['records']])
        capture(output, job=job, adapter=ADAPTER, manifest=capture_manifest, reference_keys=REFERENCE_KEYS,
                saved=saved, inputs=[row['text'] for row in splits['validation']], validation=validation,
                rows=validation_rows, clocks=metrics['clocks'])
    artifacts = []
    for name, split in (('metrics.json', 'validation'), ('test-metrics.json', 'test'),
                        ('predictions-validation.json', 'validation'), ('predictions-test.json', 'test'), ('model.json', None)):
        raw = (output / name).read_bytes()
        artifacts.append({'name': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                          'media_type': 'application/json', 'split': split})
    if selected:
        from one_fit_evidence import CAPTURE_NAMES
        for name in sorted(CAPTURE_NAMES):
            raw = (output / name).read_bytes()
            artifacts.append({'name': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                              'media_type': 'application/json', 'split': 'validation' if name in ('probe.json', 'probe-inputs.json', 'probes-fit-0001.json', 'observations.json') else None})
    _write_json(output / 'artifact-manifest.json', {**envelope, 'artifacts': artifacts})
    _emit('completed', epochs=1)


def main():
    for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[variable] = '1'
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
        with (args.verify_evidence or args.job).open('rb') as handle:
            raw = handle.read(MAX_JOB_BYTES + 1)
        if len(raw) > MAX_JOB_BYTES:
            _invalid('Training job exceeds 16 KiB.')
        job = _json(raw, 'Text training job')
        if args.verify_evidence:
            guard_parent(job['parent_pid'])
            verify_evidence(job['output_dir'], job)
        else:
            train(job)
        return 0
    except TrainingError as error:
        _emit('failed', outcome=error.outcome, message=str(error)[:400])
        return 2
    except Exception:
        _emit('failed', outcome='failed', message='Local text adapter failed; private outputs were not published.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
