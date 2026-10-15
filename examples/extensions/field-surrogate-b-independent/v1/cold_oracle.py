"""Frozen independent stdlib B oracle: arrays, gradient trajectory, replay and targets.

No producer, SDK, NumPy or application import is allowed in this consumer.
Numerical acceptance is distinct from host conformance and physical qualification.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import struct

ATOL = RTOL = 1e-10
POINTS = (32, 64)


class OracleError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise OracleError(reason)


def close(actual, expected, reason):
    require(type(actual) in (int, float) and math.isfinite(actual)
            and abs(actual-expected) <= ATOL+RTOL*abs(expected), reason)
    return abs(actual-expected)


def npy(raw, shape):
    require(type(raw) is bytes and raw[:8] == b'\x93NUMPY\x01\x00', 'Expected NPY v1')
    require(10 <= len(raw) <= 8192, 'NPY exceeds bound')
    size = struct.unpack('<H', raw[8:10])[0]
    require(0 < size <= 1024 and 10+size <= len(raw), 'Invalid NPY header bound')
    try:
        expression = ast.parse(raw[10:10+size].decode('ascii').strip(), mode='eval')
        nodes = list(ast.walk(expression))
        require(len(nodes) <= 64 and all(isinstance(node, (ast.Expression, ast.Dict, ast.Tuple, ast.Constant, ast.Load)) for node in nodes), 'Unsupported NPY literal')
        keys = [key.value for key in expression.body.keys]
        require(len(keys) == len(set(keys)), 'Duplicate NPY metadata')
        metadata = ast.literal_eval(expression)
    except (SyntaxError, AttributeError, UnicodeError, TypeError, ValueError):
        raise OracleError('Malformed NPY header') from None
    require(type(metadata) is dict and set(metadata) == {'descr', 'fortran_order', 'shape'} and metadata['descr'] == '<f8' and metadata['fortran_order'] is False and type(metadata['shape']) is tuple and all(type(value) is int for value in metadata['shape']) and metadata['shape'] == shape, 'Expected exact little-endian float64 C-order shape')
    count = math.prod(shape)
    require(len(raw) == 10+size+8*count, 'Truncated or trailing NPY payload')
    values = struct.unpack('<'+str(count)+'d', raw[10+size:])
    require(all(math.isfinite(value) for value in values), 'Nonfinite NPY payload')
    return values


def trajectory(fixture, rate=.1):
    """Derive population transforms and 64 gradient steps directly from B equations."""
    rows = {row['id']: row for row in fixture['cases']}
    fit_ids = fixture['fit_member_ids']
    require(fit_ids == ['train-0', 'train-1'] and all(rows[key]['split'] == 'train' for key in fit_ids), 'Train membership differs')
    features = [[rows[key][field][i] for key in fit_ids for i in range(64)] for field in ('initial', 'source')]
    means = [math.fsum(values)/128 for values in features]
    stds = [math.sqrt(math.fsum((value-mean)**2 for value in values)/128) for mean, values in zip(means, features)]
    require(all(value > 0 and math.isfinite(value) for value in stds), 'Train variance differs')
    normalized = [[(value-means[j])/stds[j] for value in features[j]] for j in range(2)]
    targets = [.5*x+.25+.2*s for x, s in zip(*features)]
    weights = [0., 0., 0.]
    states = {}
    for step in range(1, 65):
        residuals = [weights[0]*normalized[0][i]+weights[1]*normalized[1][i]+weights[2]-targets[i] for i in range(128)]
        gradients = [2*math.fsum(residuals[i]*normalized[j][i] for i in range(128))/128 for j in range(2)]
        gradients.append(2*math.fsum(residuals)/128)
        weights = [value-rate*gradient for value, gradient in zip(weights, gradients)]
        if step in POINTS:
            states[step] = tuple(weights)
    return means+stds, states


def reconstruct(inputs, transform, weights):
    require(len(transform) == 4 and len(weights) == 3 and len(inputs) == 3, 'B state requires 2 features and 3 weights')
    initial, source, mask = inputs
    require(len(initial) == len(source) == len(mask) == 64 and all(value in (0., 1.) for value in mask), 'B input/mask differs')
    raw = [weights[0]*((x-transform[0])/transform[2])+weights[1]*((s-transform[1])/transform[3])+weights[2] for x, s in zip(initial, source)]
    corrected = [0. if boundary else value for boundary, value in zip(mask, raw)]
    return raw, corrected


def qualify(fixture_path, artifacts, expected_context_sha256):
    root = Path(artifacts)
    fixture_raw = Path(fixture_path).read_bytes()
    fixture = json.loads(fixture_raw)
    frozen = json.loads((Path(__file__).parent/'oracle-freeze.json').read_text())
    require(hashlib.sha256(fixture_raw).hexdigest() == frozen['fixture_sha256'], 'Frozen fixture differs')
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == frozen['oracle_sha256'], 'Frozen oracle differs')
    context_raw = (root/'execution-context.json').read_bytes()
    require(hashlib.sha256(context_raw).hexdigest() == expected_context_sha256, 'Independent context identity differs')
    context = json.loads(context_raw)
    policy = context['static']['policy']
    require([row['member_id'] for row in policy['fit_members']] == fixture['fit_member_ids'], 'Retained fit population differs')
    require(context['static']['parameters']['updates'] == 64, 'Update count differs')
    transform, expected_states = trajectory(fixture, context['static']['parameters']['learning_rate'])
    actual_transform = npy((root/'transform.npy').read_bytes(), (2, 2))
    for actual, expected in zip(actual_transform, transform):
        close(actual, expected, 'Train-only transform differs')
    case = next(row for row in fixture['cases'] if row['id'] == 'validation-0')
    inputs = [npy((root/('input-'+field+'.npy')).read_bytes(), (4, 4, 4)) for field in ('initial', 'source', 'boundary_mask')]
    for field, values in zip(('initial', 'source', 'boundary_mask'), inputs):
        for actual, expected in zip(values, case[field]):
            close(actual, expected, 'Retained B input differs: '+field)
    references = {'raw': [.5*x+.25+.2*s for x, s in zip(inputs[0], inputs[1])]}
    references['corrected'] = [0. if mask else value for mask, value in zip(inputs[2], references['raw'])]
    for field, expected in references.items():
        for actual, target in zip(npy((root/('reference-'+field+'.npy')).read_bytes(), (4, 4, 4)), expected):
            close(actual, target, 'Reference target differs: '+field)
    index = json.loads((root/'checkpoints.json').read_text())
    observations = json.loads((root/'observations.json').read_text())
    require(len(index['entries']) == 2, 'Checkpoint coverage differs')
    results = []
    for point, entry in zip(POINTS, index['entries']):
        require(entry['clocks']['optimizer_update'] == point and entry['clocks']['physical_time'] is None, 'Actual standalone clock differs')
        descriptor_raw = (root/f'checkpoint-{point}.json').read_bytes()
        require(hashlib.sha256(descriptor_raw).hexdigest() == entry['checkpoint']['sha256'], 'Checkpoint hash differs')
        descriptor = json.loads(descriptor_raw)
        weight_raw = (root/f'weights-{point}.npy').read_bytes()
        require(descriptor['weights']['sha256'] == hashlib.sha256(weight_raw).hexdigest() and descriptor['clocks'] == entry['clocks'], 'Retained weight/clock binding differs')
        weights = npy(weight_raw, (3,))
        state_error = max(close(a, b, 'Independent B gradient trajectory differs') for a, b in zip(weights, expected_states[point]))
        reconstruction = reconstruct(inputs, actual_transform, weights)
        for field, expected in zip(('raw', 'corrected'), reconstruction):
            actual = npy((root/f'{field}-{point}.npy').read_bytes(), (4, 4, 4))
            replay_error = max(close(a, b, 'Retained-state reconstruction differs: '+field) for a, b in zip(actual, expected))
            mse = math.fsum((a-b)**2 for a, b in zip(actual, references[field]))/64
            matching = [row for row in observations if row['checkpoint_sha256'] == entry['checkpoint']['sha256'] and row['metric_id'] == field+'_reference_mse']
            require(len(matching) == 1, 'Stage-specific metric coverage differs')
            close(matching[0]['value'], mse, 'Reference-target MSE differs: '+field)
            results.append(dict(optimizer_update=point, field=field, reference_target_mse=mse,
                                reconstruction_maximum_error=replay_error, gradient_state_maximum_error=state_error))
    return dict(format='independent_b_numerical_oracle_v1', state='valid', observations=results,
                absolute_tolerance=ATOL, relative_tolerance=RTOL, product_conformance='not_established', physical_qualification='not_established')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--artifacts', required=True)
    parser.add_argument('--expected-context-sha256', required=True)
    parser.add_argument('--report', required=True)
    arguments = parser.parse_args()
    result = qualify(arguments.fixture, arguments.artifacts, arguments.expected_context_sha256)
    with Path(arguments.report).open('x') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(result, allow_nan=False))
