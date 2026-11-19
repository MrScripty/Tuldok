"""The adapter Tuldok runs in a project's environment to serve its model (docs/plans/training-and-curation/spec-t6.md).

Run as a file by the environment's interpreter with -I, never imported by
Tuldok's server: `python -I serve_adapter.py --requests FD --answers FD --code
DIR --module FILE --function NAME [--load NAME] --product DIR`. It moves the
process's standard output to standard error before anything of the project is
imported, so a stray print goes to the log and never into the protocol; it
imports the project's module from its file, calls load(product) once, writes
the ready line, then answers one request line at a time on the private pipes
until the request pipe closes (section 2). Arrays are decoded to NumPy float32
arrays when NumPy is importable, else to nested lists, and NumPy values in the
outputs are encoded. Standard library only; Python 3.8 or later.
"""
import argparse
import base64
import importlib.util
import json
import math
import os
import platform
import struct
import sys
import time

ANSWER_LIMIT = 16 * 1024 * 1024     # bytes of one answer line (serve_protocol.ANSWER_LIMIT)
REQUEST_LIMIT = 9 * 1024 * 1024     # bytes of one request line, with room around an 8 MiB body
ERROR_CHARACTERS = 2000
ARRAY_KEYS = ('array', 'base64', 'shape')
_LITTLE = sys.byteorder == 'little'

try:
    import numpy  # noqa: F401  (only when the environment has it)
except ImportError:                  # pragma: no cover - depends on the environment
    numpy = None


def _one_line(error):
    text = f'{type(error).__name__}: {error}'.replace('\r', ' ').replace('\n', ' ')
    return text[:ERROR_CHARACTERS]


# ------------------------------------------------------------------ arrays

def _is_array(value):
    return isinstance(value, dict) and tuple(sorted(value)) == ARRAY_KEYS and value.get('array') == 'float32'


def _nest(flat, shape):
    if not shape:
        return flat[0]
    if len(shape) == 1:
        return list(flat)
    step = len(flat) // shape[0] if shape[0] else 0
    return [_nest(flat[i * step:(i + 1) * step], shape[1:]) for i in range(shape[0])]


def decode_array(value, *, use_numpy=True):
    """An encoded array (already checked by Tuldok) as a NumPy float32 array, or nested lists of floats."""
    shape = [int(n) for n in value['shape']]
    raw = base64.b64decode(value['base64'], validate=True)
    count = 1
    for n in shape:
        count *= n
    if len(raw) != 4 * count:
        raise ValueError(f'the array of shape {shape} needs {4 * count} bytes, not {len(raw)}')
    if numpy is not None and use_numpy:
        return numpy.frombuffer(raw, dtype='<f4').reshape(shape).astype(numpy.float32)
    flat = list(struct.unpack('<%df' % count, raw))
    return _nest(flat, shape)


def decode(value, *, use_numpy=True):
    """The inputs as predict sees them: every encoded array decoded."""
    if _is_array(value):
        return decode_array(value, use_numpy=use_numpy)
    if isinstance(value, dict):
        return {key: decode(item, use_numpy=use_numpy) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item, use_numpy=use_numpy) for item in value]
    return value


def encode_array(shape, values):
    """{array, shape, base64} of float32 values (a flat sequence of numbers) in C order."""
    raw = struct.pack('<%df' % len(values), *values)
    return {'array': 'float32', 'shape': list(shape), 'base64': base64.b64encode(raw).decode('ascii')}


def encode(value):
    """The outputs as JSON: NumPy arrays encoded as float32, NumPy scalars as numbers, tuples as lists."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('an output is not a finite number')
        return value
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f'an output key is {type(key).__name__}, not a string')
            out[key] = encode(item)
        return out
    if isinstance(value, (list, tuple)):
        return [encode(item) for item in value]
    if hasattr(value, 'shape') and hasattr(value, 'dtype') and hasattr(value, 'tobytes'):
        if numpy is not None and getattr(value, 'ndim', None) == 0:
            return encode(value.item())
        array = value.astype('<f4')
        raw = array.tobytes(order='C')
        return {'array': 'float32', 'shape': [int(n) for n in value.shape],
                'base64': base64.b64encode(raw).decode('ascii')}
    if hasattr(value, 'item') and callable(value.item):   # a NumPy scalar
        return encode(value.item())
    raise ValueError(f'an output of type {type(value).__name__} is not JSON')


# ---------------------------------------------------------------- the loop

def _write(handle, message):
    data = json.dumps(message, allow_nan=False, separators=(',', ':')).encode('utf-8') + b'\n'
    if len(data) > ANSWER_LIMIT:
        raise ValueError(f'the answer is {len(data)} bytes, more than {ANSWER_LIMIT}')
    handle.write(data)
    handle.flush()


def _load_module(code, module_file):
    path = os.path.join(code, module_file)
    name = '_tuldok_served_' + os.path.splitext(os.path.basename(module_file))[0].replace('-', '_')
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'{module_file} cannot be imported')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _function(module, name, module_file):
    found = getattr(module, name, None)
    if not callable(found):
        raise AttributeError(f'{module_file} has no function {name}')
    return found


def answer(predict, model, line):
    """The answer to one request line (bytes): {id, ok, outputs | error, model_seconds}."""
    started = time.perf_counter()
    try:
        request = json.loads(line)
        number = request.get('id')
    except ValueError as error:
        return {'id': None, 'ok': False, 'error': _one_line(error), 'model_seconds': 0.0}
    try:
        outputs = encode(predict(model, decode(request.get('inputs', {}))))
        return {'id': number, 'ok': True, 'outputs': outputs, 'model_seconds': time.perf_counter() - started}
    except Exception as error:   # the model's failure is the request's, not the process's
        return {'id': number, 'ok': False, 'error': _one_line(error),
                'model_seconds': time.perf_counter() - started}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--requests', type=int, required=True)
    parser.add_argument('--answers', type=int, required=True)
    parser.add_argument('--code', required=True)
    parser.add_argument('--module', required=True)
    parser.add_argument('--function', required=True)
    parser.add_argument('--load', default='')
    parser.add_argument('--product', required=True)
    arguments = parser.parse_args(argv)
    sys.dont_write_bytecode = True
    requests = os.fdopen(arguments.requests, 'rb', buffering=0)
    answers = os.fdopen(arguments.answers, 'wb')
    os.dup2(2, 1)   # standard output joins the log from here on; the protocol is on the private pipes only
    sys.stdout = sys.stderr
    code = os.path.abspath(arguments.code)
    sys.path.insert(0, code)
    started = time.perf_counter()
    try:
        module = _load_module(code, arguments.module)
        predict = _function(module, arguments.function, arguments.module)
        model = (_function(module, arguments.load, arguments.module)(arguments.product)
                 if arguments.load else arguments.product)
    except BaseException as error:
        import traceback
        traceback.print_exc()
        _write(answers, {'ready': False, 'error': _one_line(error)})
        return 1
    _write(answers, {'ready': True, 'load_seconds': time.perf_counter() - started, 'numpy': numpy is not None,
                     'python': platform.python_version()})
    reader = requests
    pending = b''
    while True:
        chunk = reader.read(1 << 20)
        if not chunk:
            return 0
        pending += chunk
        if len(pending) > REQUEST_LIMIT and b'\n' not in pending:
            print('A request line was longer than the adapter accepts; stopping.', file=sys.stderr)
            return 2
        while b'\n' in pending:
            line, pending = pending.split(b'\n', 1)
            reply = answer(predict, model, line)
            try:
                _write(answers, reply)
            except ValueError as error:
                _write(answers, {'id': reply.get('id'), 'ok': False, 'error': _one_line(error),
                                 'model_seconds': reply.get('model_seconds')})


if __name__ == '__main__':
    sys.exit(main())
