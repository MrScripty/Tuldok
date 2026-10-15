"""Independent cold NumPy inference for the pinned pressure CNN; never trains."""
import argparse
import ast
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import sys
import zipfile

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np

SOURCE_COMMIT = '2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15'
SOURCE_PINS = {
    'scripts/train_cpu.py': 'ee384926b3e3326356aa6c9b033b53c3c3236117514c848c2ebfc3a413115c37',
    'tuldok/cnn.py': '4a90ec2be9ab3c231400eab6c6b57608e613705e295769f97e538e95ecfb9949',
}
FIXTURE_PINS = {
    'dataset.npz': '38cd317657d222145b6007792ee68eb2bdf70ba92ed2735f34cb9daa6ebbd9cf',
    'splits.json': '90843f15ba82154f2f371e63534a6a016abc615660688b289ea843b8dcdd9096',
    'dataset-receipt.json': '9d4e0be76f59939b5af9be897b0d5e32b47561776059ae96a5dc536aa2b8dbf9',
}
CHECKPOINT_SHA256 = '7f514ff90acf5adc42b009fa42c715658b4d8087ae9e4ca0e547af7f62c64121'
ARTIFACT_NAMES = frozenset(('weights.npz', 'predictions.npz', 'normalization.json',
                            'splits.json', 'receipt.json', 'summary.json'))
TRAIN_IDS = tuple('white_noise-' + str(seed) for seed in range(1000, 1004)) + tuple(
    'polynomial_mix-' + str(seed) for seed in range(2000, 2004))
VALIDATION_IDS = tuple('localized_blob-' + str(seed) for seed in range(3000, 3004))
TEST_IDS = tuple('oscillatory_modes-' + str(seed) for seed in range(4000, 4004))
ABS_TOLERANCE = REL_TOLERANCE = 1e-10
JSON_LIMIT = 1024 * 1024
ARCHIVE_LIMIT = 2 * 1024 * 1024


class VerificationError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise VerificationError(reason)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_file(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit,
                'Input must be a bounded regular file.')
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        content = b''.join(chunks)
        require(len(content) <= limit and len(content) == after.st_size
                and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Input changed or exceeded its read bound.')
        return content
    finally:
        os.close(fd)


def read_directory(path, names, limits):
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(set(os.listdir(directory)) == set(names), 'Directory inventory differs from the selected contract.')
        # /proc is not used: open each flat file relative to the held directory.
        result = {}
        for name in sorted(names):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                before = os.fstat(fd)
                limit = limits[name]
                require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'Artifact is not a bounded regular file.')
                chunks, remaining = [], limit + 1
                while remaining:
                    chunk = os.read(fd, min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                after = os.fstat(fd)
                content = b''.join(chunks)
                require(len(content) <= limit and len(content) == after.st_size
                        and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                        (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'Artifact changed or exceeded its read bound.')
                result[name] = content
            finally:
                os.close(fd)
        require(set(os.listdir(directory)) == set(names), 'Directory inventory changed during inspection.')
        return result
    finally:
        os.close(directory)


def closed(value, fields, label):
    require(isinstance(value, dict) and set(value) == set(fields), label + ' fields differ from the frozen contract.')


def strict_json(content):
    def pairs(items):
        result = {}
        for key, child in items:
            require(key not in result, 'Duplicate JSON key.')
            result[key] = child
        return result
    def constant(_value):
        raise VerificationError('Nonfinite JSON constant.')
    require(len(content) <= JSON_LIMIT, 'JSON exceeds its byte limit.')
    value = json.loads(content.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    remaining = 32768
    def visit(node, depth=0):
        nonlocal remaining
        remaining -= 1
        require(depth <= 16 and remaining >= 0, 'JSON exceeds its structural bounds.')
        if isinstance(node, float):
            require(math.isfinite(node), 'Nonfinite JSON value.')
        if isinstance(node, str):
            require(len(node) <= 4096 and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in node), 'Unsupported JSON text.')
        if isinstance(node, dict):
            for key, child in node.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1)
    visit(value)
    return value


def number(value, label):
    require(type(value) in (int, float), label + ' must be numeric without coercion.')
    result = float(value)
    require(math.isfinite(result), label + ' must be finite.')
    return result


def compare(actual, expected, label):
    require(math.isfinite(actual) and math.isfinite(expected), label + ' must be finite.')
    error = abs(actual - expected)
    require(error <= ABS_TOLERANCE + REL_TOLERANCE * abs(expected), label + ' exceeds the frozen agreement tolerance.')
    return error


def decode_array(content, shape, dtype):
    require(content[:6] == b'\x93NUMPY' and len(content) >= 10, 'Invalid NPY magic or length.')
    version = tuple(content[6:8])
    require(version in ((1, 0), (2, 0)), 'Unsupported NPY version.')
    width = 2 if version == (1, 0) else 4
    start = 8 + width
    require(len(content) >= start, 'Truncated NPY length.')
    length = int.from_bytes(content[8:start], 'little')
    end = start + length
    require(0 < length <= 4096 and end <= len(content) and end % 16 == 0
            and content[end - 1:end] == b'\n', 'Invalid NPY header size/alignment.')
    expression = ast.parse(content[start:end].decode('ascii').strip(), mode='eval')
    nodes = list(ast.walk(expression))
    require(len(nodes) <= 64 and isinstance(expression.body, ast.Dict)
            and all(isinstance(node, (ast.Expression, ast.Dict, ast.Tuple, ast.Constant, ast.Load)) for node in nodes),
            'NPY header must be a bounded literal dictionary.')
    keys = [key.value for key in expression.body.keys if isinstance(key, ast.Constant) and type(key.value) is str]
    require(len(keys) == len(expression.body.keys) == len(set(keys)), 'Duplicate or invalid NPY header keys.')
    header = ast.literal_eval(expression)
    closed(header, ('descr', 'shape', 'fortran_order'), 'NPY header')
    require(header['descr'] == dtype and header['fortran_order'] is False,
            'NPY dtype/order differs; object/pickled/native/Fortran arrays are not accepted.')
    require(type(header['shape']) is tuple and all(type(n) is int for n in header['shape'])
            and header['shape'] == shape, 'NPY shape differs from the selected contract.')
    expected_bytes = math.prod(shape) * np.dtype(dtype).itemsize
    require(len(content) == end + expected_bytes, 'NPY payload is truncated or has trailing bytes.')
    value = np.frombuffer(content, dtype=dtype, count=math.prod(shape), offset=end).reshape(shape)
    require(value.flags.c_contiguous, 'Array must have C-order storage.')
    if dtype == '<f8':
        require(bool(np.isfinite(value).all()), 'Numeric array contains nonfinite values.')
    return value


def archive_arrays(content, layout, selected=None):
    """Bound ZIP expansion before loading exact, non-pickled NPY members."""
    require(len(content) <= ARCHIVE_LIMIT, 'Archive exceeds its byte limit.')
    chosen = set(layout) if selected is None else set(selected)
    require(chosen <= set(layout), 'Unknown selected archive member.')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        expected_names = {name + '.npy' for name in layout}
        require(len(entries) == len(layout) and {item.filename for item in entries} == expected_names,
                'Archive has missing/duplicate/undeclared members.')
        total = 0
        for item in entries:
            name = item.filename[:-4]
            shape, dtype = layout[name]
            bound = math.prod(shape) * np.dtype(dtype).itemsize + 4096 + 12
            require(item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and not item.flag_bits & 1 and 10 <= item.file_size <= bound,
                    'Archive member exceeds its selected bound or uses unsupported encoding.')
            total += item.file_size
        require(total <= ARCHIVE_LIMIT, 'Archive exceeds its aggregate expansion bound.')
        result = {}
        for name in sorted(chosen):
            item = archive.getinfo(name + '.npy')
            with archive.open(item) as member:
                raw = member.read(item.file_size + 1)
            require(len(raw) == item.file_size, 'Archive member expansion differs from inventory.')
            result[name] = decode_array(raw, *layout[name])
        return result


def selected_fixture(raw):
    require({name: digest(value) for name, value in raw.items()} == FIXTURE_PINS, 'Captured fixture bytes differ from the pre-execution pins.')
    splits = strict_json(raw['splits.json'])
    closed(splits, ('schema', 'shape_xyz', 'dtype', 'rheon_revision', 'generator_revision', 'manifest_sha256',
                    'dataset_sha256', 'cases', 'policy'), 'Splits')
    require(splits['schema'] == 'rheon-cnn-splits-v1' and splits['shape_xyz'] == [8, 7, 6]
            and splits['dtype'] == '<f8' and splits['generator_revision'] == SOURCE_COMMIT
            and splits['rheon_revision'] == '34235d33c886aa05b5bdf95d920b863d1fb2ad6f'
            and splits['dataset_sha256'] == FIXTURE_PINS['dataset.npz']
            and splits['policy'] == 'whole seeds and scenario families; standalone fields; checks excluded', 'Split semantics differ.')
    expected_ids = TRAIN_IDS + VALIDATION_IDS + TEST_IDS
    require(isinstance(splits['cases'], list) and len(splits['cases']) == 16, 'Split member count differs.')
    for row, identity in zip(splits['cases'], expected_ids):
        closed(row, ('id', 'family', 'seed', 'split', 'trajectory'), 'Case')
        family, seed = identity.rsplit('-', 1)
        split = 'train' if identity in TRAIN_IDS else 'validation' if identity in VALIDATION_IDS else 'test'
        require(row['id'] == row['trajectory'] == identity and row['family'] == family
                and type(row['seed']) is int and row['seed'] == int(seed) and row['split'] == split, 'Case/split/family identity differs.')
    layout = {split + '_' + field: ((count, 6, 7, 8), '<f8')
              for split, count in (('train', 8), ('validation', 4), ('test', 4)) for field in ('rhs', 'pressure')}
    arrays = archive_arrays(raw['dataset.npz'], layout, ('train_rhs', 'train_pressure', 'validation_rhs', 'validation_pressure'))
    # Test member data are not decompressed or fitted by this oracle.
    for field in ('train_pressure', 'validation_pressure'):
        require(bool((arrays[field][:, 0, 0, 0] == 0).all()), 'Selected reference pressure has a different cell-zero gauge.')
    rhs = [float(value) for value in arrays['train_rhs'].flat]
    pressure = [float(value) for value in arrays['train_pressure'].flat]
    mean = math.fsum(rhs) / len(rhs)
    std = math.sqrt(math.fsum((value - mean) ** 2 for value in rhs) / len(rhs))
    rms = math.sqrt(math.fsum(value * value for value in pressure) / len(pressure))
    require(std > 0 and rms > 0, 'Training-only normalization scales must be positive.')
    return splits, arrays, {'rhs_mean': mean, 'rhs_std': std, 'pressure_rms': rms, 'fit_case_ids': list(TRAIN_IDS)}


def cold_prediction(rhs, normalization, params):
    """Direct spatial convolution; no producer patches/encode/forward implementation."""
    fields = np.empty((4, 6, 7, 8), dtype='<f8')
    fields[0] = (rhs - normalization['rhs_mean']) / normalization['rhs_std']
    for z in range(6):
        for y in range(7):
            for x in range(8):
                fields[1, z, y, x] = 2 * (x + 0.5) / 8 - 1
                fields[2, z, y, x] = 2 * (y + 0.5) / 7 - 1
                fields[3, z, y, x] = 2 * (z + 0.5) / 6 - 1
    kernel = params['kernel'].reshape(4, 3, 3, 3, 16)
    raw = np.empty((6, 7, 8), dtype='<f8')
    for z in range(6):
        for y in range(7):
            for x in range(8):
                terms = [[] for _ in range(16)]
                for channel in range(4):
                    for kz in range(3):
                        iz = z + kz - 1
                        for ky in range(3):
                            iy = y + ky - 1
                            for kx in range(3):
                                ix = x + kx - 1
                                if 0 <= iz < 6 and 0 <= iy < 7 and 0 <= ix < 8:
                                    value = float(fields[channel, iz, iy, ix])
                                    for hidden in range(16):
                                        terms[hidden].append(value * float(kernel[channel, kz, ky, kx, hidden]))
                activated = np.tanh(np.array([math.fsum(values) + float(params['bias'][hidden])
                                             for hidden, values in enumerate(terms)], dtype='<f8'))
                raw[z, y, x] = math.fsum(float(activated[h]) * float(params['output'][h]) for h in range(16))
    return ((raw - raw[0, 0, 0]) * normalization['pressure_rms']).reshape(336)


def validate_receipt(receipt, normalization, hashes, mode):
    closed(receipt, ('schema', 'status', 'dataset_sha256', 'splits_sha256', 'weights_sha256',
                     'normalization_sha256', 'predictions_sha256', 'source_sha256', 'wrapper_sha256', 'numpy',
                     'python', 'model', 'dtype', 'seed', 'optimizer', 'optimizer_steps', 'training_ids',
                     'normalization', 'history', 'split_metrics', 'fitting_seconds', 'wall_seconds_after_imports',
                     'restored_predictions_equal', 'scope'), 'Training/restore receipt')
    require(receipt['schema'] == ('rheon-cnn-training-v1' if mode == 'train' else 'rheon-cnn-restored-v1')
            and receipt['status'] == 'complete' and receipt['numpy'] == '2.3.5'
            and receipt['source_sha256'] == SOURCE_PINS['scripts/train_cpu.py']
            and receipt['wrapper_sha256'] == SOURCE_PINS['tuldok/cnn.py']
            and receipt['dataset_sha256'] == FIXTURE_PINS['dataset.npz']
            and receipt['splits_sha256'] == FIXTURE_PINS['splits.json'], 'Receipt source/data/format identity differs.')
    for field, name in (('weights_sha256', 'weights.npz'), ('normalization_sha256', 'normalization.json'), ('predictions_sha256', 'predictions.npz')):
        require(receipt[field] == hashes[name], 'Receipt artifact hash differs from actual bytes.')
    require(receipt['weights_sha256'] == CHECKPOINT_SHA256 and receipt['training_ids'] == list(TRAIN_IDS)
            and receipt['normalization'] == normalization, 'Checkpoint/training/normalization lineage differs.')
    require(receipt['model'] == 'original 1760-parameter radius-one NumPy CNN' and receipt['dtype'] == 'float64'
            and type(receipt['seed']) is int and receipt['seed'] == 2026
            and receipt['optimizer'] == 'original full-batch Adam lr0.01 beta(0.9,0.999) eps1e-8'
            and receipt['scope'] == 'neural optimization/restore diagnostic; no native physics or acceleration qualification; historical exposed test family',
            'Model, scope or optimization declaration differs.')
    require(type(receipt['optimizer_steps']) is int and receipt['optimizer_steps'] == (200 if mode == 'train' else 0)
            and receipt['restored_predictions_equal'] is (mode == 'restore'), 'Optimizer clock or restore declaration differs.')
    require(number(receipt['fitting_seconds'], 'Fitting duration') >= 0
            and number(receipt['wall_seconds_after_imports'], 'Worker wall duration') >= 0, 'Negative timing declaration.')
    history = receipt['history']
    require(isinstance(history, list), 'History must be a list.')
    if mode == 'restore':
        require(history == [] and receipt['fitting_seconds'] == 0, 'Restore claims optimizer work.')
    else:
        require(len(history) == 5, 'Expected original optimizer observations at0,50,100,150,200.')
        for step, point in zip((0, 50, 100, 150, 200), history):
            closed(point, ('step', 'normalized_mse'), 'History observation')
            require(type(point['step']) is int and point['step'] == step
                    and number(point['normalized_mse'], 'Training loss') >= 0, 'History clock/value differs.')


def qualify(fixture, artifacts, source_root, mode):
    require(np.__version__ == '2.3.5', 'Use the independently selected NumPy2.3.5 environment.')
    require(not any(name in sys.modules for name in ('train_cpu', 'cnn', 'app', 'torch')), 'Producer/application modules must not be imported.')
    source_hashes = {name: digest(read_file(Path(source_root) / name, 65536)) for name in SOURCE_PINS}
    require(source_hashes == SOURCE_PINS, 'Read-only numerical source differs from its frozen pins.')
    fixture_raw = read_directory(fixture, FIXTURE_PINS, {name: ARCHIVE_LIMIT for name in FIXTURE_PINS})
    splits, arrays, expected_normalization = selected_fixture(fixture_raw)
    raw = read_directory(artifacts, ARTIFACT_NAMES, {name: 65536 if name in ('weights.npz', 'normalization.json', 'splits.json', 'summary.json')
                                                  else JSON_LIMIT for name in ARTIFACT_NAMES})
    hashes = {name: digest(content) for name, content in raw.items()}
    require(hashes['weights.npz'] == CHECKPOINT_SHA256 and raw['splits.json'] == fixture_raw['splits.json'], 'Retained checkpoint or splits differ from exact selection.')
    normalization = strict_json(raw['normalization.json'])
    closed(normalization, ('rhs_mean', 'rhs_std', 'pressure_rms', 'fit_case_ids'), 'Normalization')
    require(normalization['fit_case_ids'] == list(TRAIN_IDS), 'Normalization includes a different fit population.')
    for key in ('rhs_mean', 'rhs_std', 'pressure_rms'):
        compare(number(normalization[key], key), expected_normalization[key], 'Train-only ' + key)
    require(normalization['rhs_std'] > 0 and normalization['pressure_rms'] > 0, 'Retained normalization scales must be positive.')
    params = archive_arrays(raw['weights.npz'], {'kernel': ((108, 16), '<f8'), 'bias': ((16,), '<f8'), 'output': ((16,), '<f8')})
    case_ids = TRAIN_IDS + VALIDATION_IDS + (TEST_IDS if mode == 'restore' else ())
    predictions = archive_arrays(raw['predictions.npz'], {'pressure': ((len(case_ids), 336), '<f8'), 'case_ids': ((len(case_ids),), '<U80')})
    require(predictions['case_ids'].tolist() == list(case_ids), 'Prediction member/split order differs.')
    require(bool((predictions['pressure'][:, 0] == 0).all()), 'Retained predictions have a different cell-zero gauge.')
    receipt = strict_json(raw['receipt.json'])
    validate_receipt(receipt, normalization, hashes, mode)
    expected_splits = ('train', 'validation') if mode == 'train' else ('train', 'validation', 'test')
    closed(receipt['split_metrics'], expected_splits, 'Split metrics')
    for split in expected_splits:
        metric = receipt['split_metrics'][split]
        closed(metric, ('cases', 'mean_relative_pressure_l2', 'max_relative_pressure_l2'), 'Split metric')
        require(type(metric['cases']) is int and metric['cases'] == (8 if split == 'train' else 4), 'Metric member count differs.')
        require(0 <= number(metric['mean_relative_pressure_l2'], 'Mean diagnostic error')
                <= number(metric['max_relative_pressure_l2'], 'Maximum diagnostic error'), 'Diagnostic metric range differs.')
    summary = strict_json(raw['summary.json'])
    closed(summary, ('format', 'title', 'checkpoint', 'metrics', 'scope'), 'Summary')
    require(summary['format'] == 'tuldok_result_summary_v1' and summary['title'] == 'Captured CNN ' + mode
            and summary['checkpoint'] == 'weights.npz' and isinstance(summary['metrics'], list)
            and len(summary['metrics']) == len(expected_splits)
            and summary['scope'] == ['Original radius-one CNN has known global-pressure limitations',
                                     'Actual Adam optimization; restore does not fit holdout',
                                     'Diagnostic numeric errors; no solver quality or speedup claim'], 'Summary metadata differs.')
    for split, metric in zip(expected_splits, summary['metrics']):
        closed(metric, ('name', 'value', 'unit'), 'Summary metric')
        require(metric['name'] == split + '_pressure_relative_l2' and metric['unit'] == 'ratio', 'Summary metric identity differs.')
        compare(number(metric['value'], 'Summary error'), receipt['split_metrics'][split]['mean_relative_pressure_l2'], 'Summary/receipt agreement')
    observations, relative_errors = [], []
    for index, identity in enumerate(VALIDATION_IDS):
        reconstructed = cold_prediction(arrays['validation_rhs'][index], normalization, params)
        emitted = predictions['pressure'][len(TRAIN_IDS) + index]
        differences = [compare(float(actual), float(expected), 'Fixed validation cold inference') for actual, expected in zip(emitted, reconstructed)]
        reference = arrays['validation_pressure'][index].reshape(336)
        numerator = math.sqrt(math.fsum((float(actual) - float(target)) ** 2 for actual, target in zip(emitted, reference)))
        denominator = max(math.sqrt(math.fsum(float(value) ** 2 for value in reference)), 1e-30)
        relative_errors.append(numerator / denominator)
        observations.append({'case_id': identity, 'split': 'validation', 'shape_zyx': [6, 7, 8],
                             'points_compared': 336, 'max_abs_error': max(differences),
                             'gauge_cell_pressure': float(reconstructed[0]),
                             'reference_relative_l2_diagnostic': relative_errors[-1]})
    compare(receipt['split_metrics']['validation']['mean_relative_pressure_l2'], math.fsum(relative_errors) / 4, 'Independent validation mean error tally')
    compare(receipt['split_metrics']['validation']['max_relative_pressure_l2'], max(relative_errors), 'Independent validation maximum error tally')
    return {'format': 'pressure_cnn_cold_oracle_v1', 'state': 'valid', 'mode': mode,
            'scope': 'independent cold inference diagnostic; no training, native physics, acceleration or E2/E3 acceptance',
            'consumer_sha256': digest(Path(__file__).read_bytes()), 'source_commit_pin': SOURCE_COMMIT,
            'source_sha256': source_hashes, 'fixture_sha256': FIXTURE_PINS, 'artifact_sha256': hashes,
            'numpy': np.__version__, 'absolute_tolerance': ABS_TOLERANCE, 'relative_tolerance': REL_TOLERANCE,
            'fit_case_ids': list(TRAIN_IDS), 'retained_normalization': normalization,
            'independent_normalization': expected_normalization, 'observations': observations,
            'test_arrays_loaded': False, 'optimizer_steps_performed_by_consumer': 0,
            'product_acceptance': 'not_established'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, help='Exact captured dataset/splits/receipt directory.')
    parser.add_argument('--artifacts', required=True, help='Exact completed train or restore artifact directory.')
    parser.add_argument('--source-root', required=True, help='Read-only pinned source, checked as bytes only.')
    parser.add_argument('--mode', required=True, choices=('train', 'restore'))
    parser.add_argument('--report', required=True, help='New report outside fixture, artifacts and source roots.')
    args = parser.parse_args(argv)
    try:
        report = Path(args.report).resolve()
        for directory in (args.fixture, args.artifacts, args.source_root):
            selected = Path(directory).resolve()
            require(report != selected and selected not in report.parents, 'Select a report outside all retained input roots.')
    except (VerificationError, OSError, RuntimeError):
        print(json.dumps({'state': 'invalid', 'reason': 'Unsafe report destination.'}))
        return 2
    try:
        result = qualify(args.fixture, args.artifacts, args.source_root, args.mode)
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, SyntaxError, UnicodeError,
            OverflowError, RecursionError, zipfile.BadZipFile, NotImplementedError) as error:
        result = {'format': 'pressure_cnn_cold_oracle_v1', 'state': 'invalid',
                  'reason': str(error) if isinstance(error, VerificationError) else 'Input cannot be safely decoded.',
                  'product_acceptance': 'not_established'}
    try:
        with open(args.report, 'x', encoding='utf-8') as output:
            output.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    except OSError:
        print(json.dumps({'state': 'invalid', 'reason': 'Cannot create a new report; existing files are never overwritten.'}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0 if result['state'] == 'valid' else 1


if __name__ == '__main__':
    sys.exit(main())
