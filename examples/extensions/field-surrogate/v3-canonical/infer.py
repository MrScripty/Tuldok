"""Frozen canonical scalar A inference only: bytes + exact request -> native prediction NPY.

The caller owns current access and binds request hashes to a selected checkpoint,
its fitted transform and permitted input. This module never selects a checkpoint,
fits statistics, trains, reads a fixture/provider or judges numerical quality.
"""
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
MAX_NPY_BYTES = 8192
MAX_JSON_BYTES = 65536
POLICY_SHA256 = '3cc4504e183bde779876b7549273185adc0e2820f55e0dcfc75090a3d392f3be'
NOTICE_SHA256 = '8bdadd8f6a5163591c4485653678f5184ae1caaf7f4a45dae2f901fe44d1c12d'
ORACLE_SHA256 = '573f142de868d13649dcdb6cc109fd629385b8ce48a1968399c0f86cb77feed9'
IMPORTS = ['argparse', 'ast', 'hashlib', 'json', 'math', 'os', 'pathlib', 'stat', 'struct', 'sys']
SOURCE_AUTHORITY = {'format': 'canonical_scalar_a_numerical_authority_v1', 'numerical_sources': {'producer.py': 'bcd801264bf05675cc6b2c5207848f723a38090b5bee6211543040831b801922', 'cold_oracle.py': '573f142de868d13649dcdb6cc109fd629385b8ce48a1968399c0f86cb77feed9', 'authored-source.json': '3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f', 'NOTICE.txt': '8bdadd8f6a5163591c4485653678f5184ae1caaf7f4a45dae2f901fe44d1c12d'}, 'sdk_sources': {'tuldok_extension_sdk/evidence.py': '94e17b5f0e21bdfddf24771e223e85fced6561f73da1fac55250906cf8d4de23', 'tuldok_extension_sdk/__init__.py': 'b7e0b3167de54dd1ce8bf5209af92ee0bcab9ba6eb6fc9f8c7db4e3fea96fc18'}, 'role_declarations': {'task': {'format': 'tuldok_contribution_v1', 'id': 'example.scalar-a:task', 'version': '3.0.0', 'kind': 'task', 'label': 'Canonical private QA standalone scalar mapping', 'requires': [], 'ports': [{'id': 'initial', 'direction': 'input', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}, {'id': 'target', 'direction': 'target', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}, {'id': 'prediction', 'direction': 'output', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}], 'stages': [{'id': 'train', 'version': '3.0.0', 'inputs': ['initial', 'target'], 'outputs': ['prediction'], 'clock': 'optimizer_update', 'failure_policy': 'fail'}]}, 'model': {'format': 'tuldok_contribution_v1', 'id': 'example.scalar-a:model', 'version': '3.0.0', 'kind': 'model', 'label': 'Canonical scalar A model', 'requires': [], 'ports': [{'id': 'initial', 'direction': 'input', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}, {'id': 'prediction', 'direction': 'output', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}], 'implementation': {'source': 'producer.py', 'entrypoint': 'main'}, 'parameters': {'type': 'object', 'properties': {'initial_scale': {'type': 'number', 'minimum': -1, 'maximum': 1}, 'initial_offset': {'type': 'number', 'minimum': -1, 'maximum': 1}}, 'required': ['initial_scale', 'initial_offset'], 'additionalProperties': False}, 'defaults': {'initial_scale': 0.0, 'initial_offset': 0.0}}, 'trainer': {'format': 'tuldok_contribution_v1', 'id': 'example.scalar-a:trainer', 'version': '3.0.0', 'kind': 'trainer', 'label': 'Canonical scalar A trainer', 'requires': [], 'ports': [{'id': 'initial', 'direction': 'input', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}, {'id': 'target', 'direction': 'target', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}, {'id': 'prediction', 'direction': 'output', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}], 'implementation': {'source': 'producer.py', 'entrypoint': 'main'}, 'parameters': {'type': 'object', 'properties': {'learning_rate': {'type': 'number', 'minimum': 0.001, 'maximum': 0.5}, 'updates': {'type': 'integer', 'minimum': 64, 'maximum': 64}}, 'required': ['learning_rate', 'updates'], 'additionalProperties': False}, 'defaults': {'learning_rate': 0.1, 'updates': 64}, 'stages': [{'id': 'train', 'version': '3.0.0', 'inputs': ['initial', 'target'], 'outputs': ['prediction'], 'clock': 'optimizer_update', 'failure_policy': 'fail'}]}, 'evaluator': {'format': 'tuldok_contribution_v1', 'id': 'example.scalar-a:evaluator', 'version': '3.0.0', 'kind': 'evaluator', 'label': 'Canonical scalar A evaluator', 'requires': [], 'ports': [{'id': 'target', 'direction': 'target', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}, {'id': 'prediction', 'direction': 'output', 'contract': {'id': 'example.scalar-a:scalar-field', 'version': '3.0.0'}, 'encoding': 'npy', 'axes': ['z', 'y', 'x'], 'units': 'dimensionless'}], 'implementation': {'source': 'producer.py', 'entrypoint': 'main'}}, 'view': {'format': 'tuldok_contribution_v1', 'id': 'example.scalar-a:view', 'version': '3.0.0', 'kind': 'view', 'label': 'Canonical scalar native field view', 'requires': [], 'view': {'primitive': 'orthogonal_slices', 'query': {'id': 'tuldok:runs.model_evidence', 'version': '2.0.0'}, 'label': 'Fixed canonical validation fields'}}}, 'outer_closure': 'Exact published Model/composition/package binds all source/role/provider/recipe/inference contract bytes; provider and recipe hashes are intentionally absent here.'}
RECONSTRUCTION = {'absolute_tolerance': 1e-10, 'relative_tolerance': 1e-10, 'independent_oracle_sha256': ORACLE_SHA256, 'scope': 'retained_fixed_probe_reconstruction_only', 'quality_acceptance': 'not_established', 'physical_acceptance': 'not_established'}
RIGHTS = {'scope': 'private_qa_only', 'redistribution': 'not_granted', 'runtime_notices': 'separate_package_owner'}
INTERFACE = {'function': 'predict(initial_npy: bytes, weights_npy: bytes, transform_npy: bytes, request: dict) -> bytes', 'cli_arguments': ['--contract', '--request', '--input', '--weights', '--transform', '--output'], 'cli_exit_status': {'written': 0, 'invalid': 2}, 'request_format': 'scalar_affine_inference_request_v1', 'request_keys': ['format', 'policy', 'sha256'], 'hash_roles': ['initial', 'weights', 'transform'], 'encoding': {'format': 'npy', 'versions': ['1.0', '2.0'], 'dtype': '<f8', 'order': 'C'}, 'initial_shape_zyx': [4, 4, 4], 'weights_shape': [2], 'weights_order': ['scale', 'offset'], 'transform_shape': [2], 'transform_order': ['train_mean', 'train_population_std'], 'output_shape_zyx': [4, 4, 4], 'output_encoding_version': '1.0', 'formula': 'scale * ((initial - train_mean) / train_population_std) + offset'}

class InferenceError(ValueError):
    """An invalid input or contract never produces a successful inference."""

def require(condition, message):
    if not condition:
        raise InferenceError(message)

def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise InferenceError('Contract requires finite JSON data.') from None

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def _check_json(value, depth=0, budget=None):
    budget = [4096] if budget is None else budget
    budget[0] -= 1
    require(budget[0] >= 0 and depth <= 16, 'JSON exceeds the node/depth bound.')
    require(value is None or type(value) in (str, int, float, bool, list, dict), 'JSON contains an unsupported value.')
    if type(value) in (int, float):
        require(type(value) is int and abs(value) <= 2 ** 53 - 1 or (type(value) is float and math.isfinite(value)), 'JSON number is invalid.')
    if type(value) is str:
        require(len(value) <= 4096 and (not any((ord(c) < 32 or 127 <= ord(c) <= 159 or 55296 <= ord(c) <= 57343 for c in value))), 'JSON text is invalid.')
    if type(value) is dict:
        for key, child in value.items():
            require(type(key) is str, 'JSON keys must be strings.')
            _check_json(key, depth + 1, budget)
            _check_json(child, depth + 1, budget)
    elif type(value) is list:
        for child in value:
            _check_json(child, depth + 1, budget)

def decode_json(raw):
    require(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES, 'JSON exceeds its byte bound.')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field.')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(InferenceError('Nonfinite JSON number.')))
    except (ValueError, UnicodeError, RecursionError):
        raise InferenceError('Invalid strict UTF-8 JSON.') from None
    _check_json(value)
    return value

def read_npy(raw, shape):
    """Read only finite, explicit float64 C arrays; never execute a deserializer."""
    require(type(raw) is bytes and 10 <= len(raw) <= MAX_NPY_BYTES and (raw[:6] == b'\x93NUMPY'), 'Invalid or oversized NPY.')
    version = raw[6:8]
    require(version in (b'\x01\x00', b'\x02\x00'), 'Unsupported NPY version.')
    width = 2 if version == b'\x01\x00' else 4
    start = 8 + width
    length = int.from_bytes(raw[8:start], 'little')
    end = start + length
    require(0 < length <= 4096 and end <= len(raw) and (end % 16 == 0) and (raw[end - 1:end] == b'\n'), 'Invalid NPY header bound/alignment.')
    try:
        expression = ast.parse(raw[start:end].decode('ascii').strip(), mode='eval')
        nodes = list(ast.walk(expression))
        require(len(nodes) <= 64 and isinstance(expression.body, ast.Dict), 'Invalid NPY literal header.')
        require(all((isinstance(node, (ast.Expression, ast.Dict, ast.Tuple, ast.Constant, ast.Load)) for node in nodes)), 'Unsupported NPY header expression.')
        keys = [key.value for key in expression.body.keys if isinstance(key, ast.Constant) and type(key.value) is str]
        require(len(keys) == len(expression.body.keys) == len(set(keys)), 'Duplicate or malformed NPY keys.')
        header = ast.literal_eval(expression)
    except (SyntaxError, UnicodeError, ValueError, TypeError, RecursionError):
        raise InferenceError('Invalid NPY literal header.') from None
    require(type(header) is dict and set(header) == {'descr', 'fortran_order', 'shape'}, 'NPY header fields differ.')
    require(header['descr'] == '<f8' and header['fortran_order'] is False, 'NPY requires explicit <f8 C order.')
    actual = header['shape']
    require(type(actual) is tuple and all((type(n) is int and n > 0 for n in actual)) and (actual == shape), 'NPY shape differs.')
    count = math.prod(shape)
    require(len(raw) == end + 8 * count, 'NPY payload is truncated or has trailing bytes.')
    values = struct.unpack('<' + str(count) + 'd', raw[end:])
    require(all((math.isfinite(value) for value in values)), 'NPY values must be finite.')
    return values

def _prediction_npy(values):
    header = repr({'descr': '<f8', 'fortran_order': False, 'shape': (4, 4, 4)}).encode('ascii')
    header += b' ' * (-(10 + len(header) + 1) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + struct.pack('<64d', *values)

def predict(initial_npy: bytes, weights_npy: bytes, transform_npy: bytes, request: dict) -> bytes:
    """Reconstruct the frozen affine formula with caller-bound exact state bytes."""
    require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12), 'Select an explicit compatible CPython 3.12 runtime.')
    _check_json(request)
    require(type(request) is dict and set(request) == {'format', 'policy', 'sha256'} and (request['format'] == INTERFACE['request_format']), 'Inference request fields/format differ.')
    require(digest(canonical(request['policy'])) == POLICY_SHA256, 'Canonical field/task/profile/gauge policy differs from frozen inference.')
    hashes = request['sha256']
    require(type(hashes) is dict and set(hashes) == {'initial', 'weights', 'transform'}, 'Exact input/state hashes are required.')
    for role, raw in (('initial', initial_npy), ('weights', weights_npy), ('transform', transform_npy)):
        expected = hashes[role]
        require(type(expected) is str and len(expected) == 64 and all((c in '0123456789abcdef' for c in expected)), 'Invalid SHA256 binding.')
        require(type(raw) is bytes and len(raw) <= MAX_NPY_BYTES and (digest(raw) == expected), role + ' bytes differ from the selected binding.')
    initial = read_npy(initial_npy, (4, 4, 4))
    scale, offset = read_npy(weights_npy, (2,))
    mean, std = read_npy(transform_npy, (2,))
    require(std > 0, 'Training population standard deviation must be positive.')
    result = [scale * ((value - mean) / std) + offset for value in initial]
    require(all((math.isfinite(value) for value in result)), 'Prediction arithmetic is nonfinite.')
    return _prediction_npy(result)

def read_file(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and (before.st_size <= maximum), 'Input must be a bounded single-link regular file.')
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    require(identity(before) == identity(after) and len(raw) == after.st_size and (len(raw) <= maximum), 'Input changed while reading.')
    return raw

def validate_contract(value):
    _check_json(value)
    require(type(value) is dict and set(value) == {'format', 'adapter', 'entrypoint', 'imports', 'sources', 'notices', 'policy', 'interface', 'runtime', 'reconstruction', 'source_authority', 'rights'}, 'Inference contract fields differ.')
    require(value['format'] == 'canonical_scalar_affine_inference_contract_v1' and canonical(value['adapter']) == canonical({'id': 'example.scalar-a.canonical:inference', 'revision': 1}), 'Unsupported inference contract.')
    require(canonical(value['interface']) == canonical(INTERFACE) and value['entrypoint'] == {'path': 'infer.py', 'function': 'predict'} and (value['imports'] == IMPORTS), 'Inference entrypoint/interface/import closure differs.')
    require(digest(canonical(value['policy'])) == POLICY_SHA256, 'Frozen canonical scalar A policy differs.')
    root = Path(__file__).resolve().parent
    for key, filename in (('sources', 'infer.py'), ('notices', 'NOTICE.txt')):
        raw = read_file(root / filename, MAX_JSON_BYTES)
        require(canonical(value[key]) == canonical([{'path': filename, 'sha256': digest(raw), 'bytes': len(raw)}]), 'Inference source/notice inventory differs.')
        if key == 'notices':
            require(digest(raw) == NOTICE_SHA256, 'Private QA notice differs.')
    require(value['runtime'] == {'implementation': 'cpython', 'version': '3.12', 'dependencies': [], 'selection': 'explicit_caller_owned_compatible_runtime', 'installation': 'none'}, 'Inference runtime contract differs.')
    require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12), 'Select an explicit compatible CPython 3.12 runtime.')
    for key, expected in (('reconstruction', RECONSTRUCTION), ('source_authority', SOURCE_AUTHORITY), ('rights', RIGHTS)):
        require(canonical(value[key]) == canonical(expected), key + ' contract differs.')
    return value

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('contract', 'request', 'input', 'weights', 'transform', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        contract = validate_contract(decode_json(read_file(args.contract, MAX_JSON_BYTES)))
        request = decode_json(read_file(args.request, MAX_JSON_BYTES))
        require(type(request) is dict, 'Inference request must be an object.')
        require(canonical(request.get('policy')) == canonical(contract['policy']), 'Request differs from the frozen contract policy.')
        result = predict(read_file(args.input, MAX_NPY_BYTES), read_file(args.weights, MAX_NPY_BYTES), read_file(args.transform, MAX_NPY_BYTES), request)
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 384)
        with os.fdopen(descriptor, 'wb') as output:
            output.write(result)
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps({'state': 'written', 'bytes': len(result), 'sha256': digest(result)}, sort_keys=True))
        return 0
    except (InferenceError, OSError) as error:
        reason = str(error) if isinstance(error, InferenceError) else 'Required input or exclusive output is unavailable.'
        print(json.dumps({'state': 'invalid', 'reason': reason}), file=sys.stderr)
        return 2
if __name__ == '__main__':
    sys.exit(main())
