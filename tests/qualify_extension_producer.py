"""Independent cold oracle for the frozen A producer preparation; stdlib only."""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys

FIXTURE_SHA256 = '0074fd7a67701a94babd9abf9e166d3435427bb032ba9b49c9d63636b397f2f3'
ABS_TOLERANCE = REL_TOLERANCE = 1e-10
UPDATES = (16, 64)
INVENTORY = frozenset(('transform.npy', 'weights-16.npy', 'weights-64.npy',
                       'prediction-16.npy', 'prediction-64.npy', 'diagnostics.json'))
JSON_LIMIT = 64 * 1024
ARRAY_LIMIT = 8192


class OracleError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise OracleError(reason)


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def read_file(path, limit, directory=None):
    """Hold a no-follow regular-file descriptor through the bounded stable read."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode), 'Only regular input files are accepted.')
        require(before.st_size <= limit, 'Input file exceeds its byte bound.')
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(fd)
        content = b''.join(chunks)
        require(len(content) <= limit, 'Input file exceeds its byte bound.')
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                and len(content) == after.st_size, 'Input file changed during the read.')
        return content
    finally:
        os.close(fd)


def strict_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field.')
            result[key] = value
        return result
    def constant(_value):
        raise OracleError('Nonfinite JSON constant.')
    try:
        value = json.loads(content.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise OracleError('Input must be strict bounded UTF-8 JSON.') from None
    def visit(node, depth=0):
        require(depth <= 16, 'JSON nesting exceeds the bound.')
        if isinstance(node, float):
            require(math.isfinite(node), 'Nonfinite JSON number.')
        if isinstance(node, str):
            require(len(node) <= 4096 and not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF
                                                for c in node), 'Unsupported JSON text.')
        if isinstance(node, dict):
            for key, child in node.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1)
    visit(value)
    return value


def closed(value, fields, label):
    require(isinstance(value, dict) and set(value) == set(fields), label + ' fields differ from the frozen contract.')


def finite(value, label):
    require(type(value) in (int, float), label + ' must be a finite number, without coercion.')
    try:
        result = float(value)
    except OverflowError:
        raise OracleError(label + ' exceeds the numeric bound.') from None
    require(math.isfinite(result), label + ' must be finite.')
    return result


def close(actual, expected, label):
    require(math.isfinite(actual) and math.isfinite(expected), label + ' must be finite.')
    difference = abs(actual - expected)
    require(difference <= ABS_TOLERANCE + REL_TOLERANCE * abs(expected), label + ' differs beyond the frozen tolerance.')
    return difference


def npy(content, expected_shape):
    """Decode only finite, non-pickled little-endian float64 NPY v1/v2 arrays."""
    require(len(content) <= ARRAY_LIMIT and len(content) >= 10 and content[:6] == b'\x93NUMPY', 'Invalid or oversized NPY file.')
    version = tuple(content[6:8])
    require(version in ((1, 0), (2, 0)), 'Unsupported NPY version.')
    width = 2 if version == (1, 0) else 4
    start = 8 + width
    require(len(content) >= start, 'Truncated NPY header length.')
    length = int.from_bytes(content[8:start], 'little')
    end = start + length
    require(0 < length <= 4096 and end <= len(content) and end % 16 == 0, 'Invalid or truncated NPY header bound/alignment.')
    header = content[start:end]
    require(header.endswith(b'\n'), 'NPY header must end with a newline.')
    try:
        expression = ast.parse(header.decode('ascii').strip(), mode='eval')
        nodes = list(ast.walk(expression))
        require(len(nodes) <= 64 and isinstance(expression.body, ast.Dict), 'NPY header is not a bounded literal dictionary.')
        allowed = (ast.Expression, ast.Dict, ast.Tuple, ast.Constant, ast.Load)
        require(all(isinstance(node, allowed) for node in nodes), 'NPY header contains unsupported expressions.')
        keys = [key.value for key in expression.body.keys if isinstance(key, ast.Constant) and type(key.value) is str]
        require(len(keys) == len(expression.body.keys) == len(set(keys)), 'Duplicate or malformed NPY header keys.')
        metadata = ast.literal_eval(expression)
    except (SyntaxError, UnicodeError, ValueError, RecursionError, TypeError):
        raise OracleError('Malformed NPY literal header.') from None
    closed(metadata, ('descr', 'fortran_order', 'shape'), 'NPY header')
    require(metadata['descr'] == '<f8', 'Only explicit little-endian float64 arrays are accepted.')
    require(metadata['fortran_order'] is False, 'Only C-order arrays are accepted.')
    shape = metadata['shape']
    require(type(shape) is tuple and all(type(size) is int and 0 < size <= 64 for size in shape)
            and shape == expected_shape, 'NPY shape differs from the selected artifact contract.')
    count = math.prod(shape)
    require(len(content) == end + count * 8, 'Truncated or trailing NPY payload.')
    values = struct.unpack('<' + str(count) + 'd', content[end:])
    require(all(math.isfinite(value) for value in values), 'NPY payload contains nonfinite values.')
    return values


def fixture_values(content, expected_sha256):
    require(expected_sha256 == FIXTURE_SHA256 and sha256(content) == FIXTURE_SHA256, 'Fixture hash differs from the frozen independent selection.')
    value = strict_json(content)
    closed(value, ('format', 'scope', 'shape_zyx', 'dtype', 'order', 'centering', 'coordinate_units',
                   'spacing_zyx', 'field_units', 'timeline', 'mapping', 'fit_member_ids', 'probe_member_id', 'cases'), 'Fixture')
    expected = {'format': 'extension_a_authored_fixture_v1', 'shape_zyx': [4, 4, 4],
                'dtype': '<f8', 'order': 'C', 'centering': 'cell', 'coordinate_units': 'm',
                'spacing_zyx': [1, 1, 1], 'field_units': 'dimensionless', 'timeline': 'not_applicable',
                'mapping': 'target = 0.5 * initial + 0.25', 'fit_member_ids': ['train-0', 'train-1'],
                'probe_member_id': 'validation-0'}
    require(all(value[key] == selected for key, selected in expected.items()), 'Fixture semantics or selected population differs.')
    require(isinstance(value['cases'], list) and len(value['cases']) == 3, 'Fixture requires exactly three frozen members.')
    cases = {}
    for member in value['cases']:
        closed(member, ('id', 'split', 'initial', 'target'), 'Fixture member')
        require(type(member['id']) is str and member['id'] not in cases, 'Fixture member identities must be unique.')
        require(member['id'] in ('train-0', 'train-1', 'validation-0'), 'Unexpected fixture member.')
        require(member['split'] == ('validation' if member['id'] == 'validation-0' else 'train'), 'Fixture split identity differs.')
        for name in ('initial', 'target'):
            require(isinstance(member[name], list) and len(member[name]) == 64, 'Fixture fields require exactly64 points.')
            member[name] = [finite(point, 'Fixture point') for point in member[name]]
        for initial, target in zip(member['initial'], member['target']):
            close(target, 0.5 * initial + 0.25, 'Fixture target equation')
        cases[member['id']] = member
    train = [point for identity in value['fit_member_ids'] for point in cases[identity]['initial']]
    mean = math.fsum(train) / len(train)
    std = math.sqrt(math.fsum((point - mean) ** 2 for point in train) / len(train))
    require(std > 0, 'Train-only population standard deviation must be positive.')
    return value, cases[value['probe_member_id']], mean, std


def qualify(fixture, expected_fixture_sha256, artifacts):
    fixture_raw = read_file(fixture, JSON_LIMIT)
    selected, probe, mean, std = fixture_values(fixture_raw, expected_fixture_sha256)
    directory = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require(set(os.listdir(directory)) == INVENTORY, 'Artifact inventory must contain exactly the six selected output files.')
        retained = {name: read_file(name, JSON_LIMIT if name == 'diagnostics.json' else ARRAY_LIMIT, directory)
                    for name in sorted(INVENTORY)}
        require(set(os.listdir(directory)) == INVENTORY, 'Artifact inventory changed during inspection.')
    finally:
        os.close(directory)
    hashes = {name: sha256(content) for name, content in retained.items()}
    transform = npy(retained['transform.npy'], (2,))
    close(transform[0], mean, 'Retained train mean')
    close(transform[1], std, 'Retained train population standard deviation')
    require(transform[1] > 0, 'Retained standard deviation must be positive.')
    diagnostics = strict_json(retained['diagnostics.json'])
    closed(diagnostics, ('fixture_sha256', 'fit_member_ids', 'probe_member_id', 'learning_rate',
                         'updates', 'observations', 'scope'), 'Diagnostics')
    require(diagnostics['fixture_sha256'] == FIXTURE_SHA256 and diagnostics['scope'] == 'producer-preparation-only', 'Diagnostics fixture identity or scope differs.')
    require(diagnostics['fit_member_ids'] == selected['fit_member_ids'] and diagnostics['probe_member_id'] == selected['probe_member_id'], 'Diagnostics fit/probe population differs.')
    require(finite(diagnostics['learning_rate'], 'Learning rate') == 0.1
            and type(diagnostics['updates']) is int and diagnostics['updates'] == 64, 'Diagnostics optimizer settings differ.')
    observations = diagnostics['observations']
    require(isinstance(observations, list) and len(observations) == 2, 'Exactly two retained observations are required.')
    results = []
    for update, observation in zip(UPDATES, observations):
        closed(observation, ('update', 'weights_sha256', 'prediction_sha256', 'reference_mse'), 'Observation')
        require(type(observation['update']) is int and observation['update'] == update, 'Observation update clock differs or is duplicated.')
        weight_name, prediction_name = 'weights-' + str(update) + '.npy', 'prediction-' + str(update) + '.npy'
        require(observation['weights_sha256'] == hashes[weight_name]
                and observation['prediction_sha256'] == hashes[prediction_name], 'Observation content binding differs from retained bytes.')
        weights = npy(retained[weight_name], (2,))
        prediction = npy(retained[prediction_name], (4, 4, 4))
        factor = 1.0 - 0.8 ** update
        analytic = (0.5 * std * factor, (0.5 * mean + 0.25) * factor)
        weight_error = max(close(actual, expected, 'Analytic gradient-update weight') for actual, expected in zip(weights, analytic))
        reconstruction = [weights[0] * ((point - transform[0]) / transform[1]) + weights[1] for point in probe['initial']]
        prediction_error = max(close(actual, expected, 'Retained-weight probe reconstruction') for actual, expected in zip(prediction, reconstruction))
        analytic_error = max(close(actual, (0.5 * point + 0.25) * factor, 'Independent analytic probe trajectory')
                             for actual, point in zip(prediction, probe['initial']))
        reference_mse = math.fsum((actual - (0.5 * point + 0.25)) ** 2
                                  for actual, point in zip(prediction, probe['initial'])) / 64
        reported_mse = finite(observation['reference_mse'], 'Reported reference MSE')
        require(reported_mse >= 0, 'Reported reference MSE cannot be negative.')
        close(reported_mse, reference_mse, 'Independently retallied reference MSE')
        results.append({'update': update, 'reference_mse': reference_mse,
                        'max_weight_abs_error': weight_error, 'max_reconstruction_abs_error': prediction_error,
                        'max_analytic_prediction_abs_error': analytic_error,
                        'weights_sha256': hashes[weight_name], 'prediction_sha256': hashes[prediction_name]})
    return {'format': 'extension_a_cold_oracle_v1', 'state': 'valid', 'scope': 'producer-preparation-only',
            'fixture_sha256': FIXTURE_SHA256, 'oracle_sha256': sha256(Path(__file__).read_bytes()),
            'artifact_sha256': hashes, 'fit_member_ids': selected['fit_member_ids'],
            'probe_member_id': selected['probe_member_id'], 'population_mean': mean, 'population_std': std,
            'absolute_tolerance': ABS_TOLERANCE, 'relative_tolerance': REL_TOLERANCE,
            'observations': results, 'product_acceptance': 'not_established'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--expected-fixture-sha256', required=True)
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--report', required=True, help='New output file outside the retained artifact directory.')
    args = parser.parse_args(argv)
    try:
        report_path = Path(args.report).resolve()
        artifact_path = Path(args.artifacts).resolve()
        require(report_path != artifact_path and artifact_path not in report_path.parents,
                'Oracle report must be outside the retained artifact directory.')
    except (OracleError, OSError, RuntimeError):
        print(json.dumps({'state': 'invalid', 'reason': 'Select a new report file outside the retained artifact directory.'}))
        return 2
    try:
        result = qualify(args.fixture, args.expected_fixture_sha256, args.artifacts)
    except (OracleError, OSError, RuntimeError) as error:
        result = {'format': 'extension_a_cold_oracle_v1', 'state': 'invalid',
                  'scope': 'producer-preparation-only', 'reason': str(error) if isinstance(error, OracleError)
                  else 'Required input cannot be safely read.', 'product_acceptance': 'not_established'}
    try:
        with open(args.report, 'x', encoding='utf-8') as output:
            output.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    except OSError:
        print(json.dumps({'state': 'invalid', 'reason': 'Cannot create a new oracle report; existing files are never overwritten.'}))
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0 if result['state'] == 'valid' else 1


if __name__ == '__main__':
    sys.exit(main())
