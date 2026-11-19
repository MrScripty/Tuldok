"""What Tuldok's server checks of a served model's requests and answers, and the summary of their times.

Owns sections 2 to 4 of docs/plans/training-and-curation/spec-t6.md on
Tuldok's side; serve_adapter.py is the other side, in the project's
environment. check_request takes a predict body (the decoded JSON) and
returns its inputs, or raises ServeError invalid: an object of exactly
`inputs`, an object; JSON nested at most DEPTH deep; every encoded array of
the right keys, shape and base64 length, within ARRAY_ELEMENTS. Arrays are
checked, never decoded into numbers here: the server passes the inputs on as
they came. check_answer does the same for an answer line from the adapter.
summary computes a session's timing summary from its request lines. Standard
library only.
"""
import base64
import binascii
import json
import math

REQUEST_LIMIT = 8 * 1024 * 1024          # bytes of a predict body over HTTP
ANSWER_LIMIT = 16 * 1024 * 1024          # bytes of one answer line from the adapter
DEPTH = 64
ARRAY_ELEMENTS = 1 << 24
ARRAY_DIMENSIONS = 8
ARRAY_KEYS = ('array', 'base64', 'shape')
TIMES = ('queue_ms', 'model_ms', 'total_ms')
MEASURES = ('total_ms', 'model_ms', 'queue_ms', 'total_s', 'model_s', 'queue_s')
# The HTTP status of each refusal of a predict (spec-t6.md section 3).
STATUS = {'invalid': 400, 'forbidden': 403, 'not-found': 404, 'not-served': 404, 'not-ready': 409,
          'too-large': 413, 'predict-failed': 422, 'serve-failed': 502, 'busy': 503, 'timed-out': 504}


class ServeError(Exception):
    """A refusal of a serving call; code is a key of STATUS or a ProjectError code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def is_array(value):
    """Whether value is written as an encoded array: an object of exactly array, shape and base64."""
    return isinstance(value, dict) and tuple(sorted(value)) == ARRAY_KEYS


def check_array(value, where='inputs'):
    """Raise ServeError invalid unless value is a well-formed float32 array; return its element count."""
    if value.get('array') != 'float32':
        raise ServeError(f'{where}: an array must say "array": "float32"; no other type is encoded.', 'invalid')
    shape = value.get('shape')
    if (not isinstance(shape, list) or len(shape) > ARRAY_DIMENSIONS
            or not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in shape)):
        raise ServeError(f'{where}: an array\'s shape must be 0 to {ARRAY_DIMENSIONS} integers of 0 or more.',
                         'invalid')
    count = 1
    for n in shape:
        count *= n
    if count > ARRAY_ELEMENTS:
        raise ServeError(f'{where}: an array may hold at most {ARRAY_ELEMENTS} values; this one {count}.', 'invalid')
    text = value.get('base64')
    if not isinstance(text, str):
        raise ServeError(f'{where}: an array\'s base64 must be a string.', 'invalid')
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ServeError(f'{where}: an array\'s base64 is not standard base64.', 'invalid') from None
    if len(raw) != 4 * count:
        raise ServeError(f'{where}: an array of shape {shape} needs {4 * count} bytes; its base64 holds {len(raw)}.',
                         'invalid')
    return count


def _walk(value, where, depth):
    if depth > DEPTH:
        raise ServeError(f'{where}: the JSON is nested more than {DEPTH} deep.', 'invalid')
    if is_array(value):
        check_array(value, where)
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk(item, f'{where}.{key}', depth + 1)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk(item, f'{where}[{index}]', depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ServeError(f'{where}: a number is not finite.', 'invalid')


def check_request(body):
    """The inputs of a predict body (the decoded JSON object), or ServeError invalid."""
    if not isinstance(body, dict) or set(body) != {'inputs'} or not isinstance(body['inputs'], dict):
        raise ServeError('Send a JSON object {"inputs": {...}} and nothing else.', 'invalid')
    _walk(body['inputs'], 'inputs', 1)
    return body['inputs']


def check_answer(line, number):
    """An answer line (bytes, its newline removed) for request number, as an object; ServeError serve-failed."""
    try:
        answer = json.loads(line.decode('utf-8'), parse_constant=_no_constant)
    except (UnicodeDecodeError, ValueError):
        raise ServeError('The served process answered with a line that is not JSON.', 'serve-failed') from None
    if not isinstance(answer, dict) or answer.get('id') != number or not isinstance(answer.get('ok'), bool):
        raise ServeError('The served process answered with something other than the answer to the request.',
                         'serve-failed')
    seconds = answer.get('model_seconds')
    if not (isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds)
            and seconds >= 0):
        raise ServeError('The served process did not say how long the model took.', 'serve-failed')
    if answer['ok']:
        if 'outputs' not in answer:
            raise ServeError('The served process answered without outputs.', 'serve-failed')
        try:
            _walk(answer['outputs'], 'outputs', 1)
        except ServeError as error:
            raise ServeError(f'The served process answered with outputs Tuldok cannot pass on ({error}).',
                             'serve-failed') from None
    elif not isinstance(answer.get('error'), str):
        raise ServeError('The served process failed a request without saying why.', 'serve-failed')
    return answer


def check_ready(line):
    """The ready line (bytes) as an object {ready, ...}; ServeError serve-failed when it is not one."""
    try:
        ready = json.loads(line.decode('utf-8'), parse_constant=_no_constant)
    except (UnicodeDecodeError, ValueError):
        ready = None
    if not isinstance(ready, dict) or not isinstance(ready.get('ready'), bool):
        raise ServeError('The served process did not start with the ready line.', 'serve-failed')
    return ready


def _no_constant(name):
    raise ValueError(f'{name} is not JSON')


# ---------------------------------------------------------------- summary

def percentile(ordered, p):
    """The value at position p × (n − 1) of ordered values, interpolated linearly (results.summarise)."""
    if not ordered:
        return None
    position = p * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def summary(lines):
    """The timing summary of a session's request lines (spec-t6.md section 4)."""
    answered = [line for line in lines if line.get('ok')]
    result = {'count': len(lines), 'answered': len(answered), 'failed': len(lines) - len(answered),
              'span_seconds': None, 'throughput_per_second': None}
    stamps = sorted(line['at'] for line in answered if isinstance(line.get('at'), (int, float)))
    if len(stamps) >= 2:
        span = stamps[-1] - stamps[0]
        result['span_seconds'] = span
        result['throughput_per_second'] = (len(stamps) - 1) / span if span > 0 else None
    for name in TIMES:
        values = sorted(line[name] for line in answered if isinstance(line.get(name), (int, float)))
        result[name] = None if not values else {
            'mean': math.fsum(values) / len(values), 'p50': percentile(values, 0.5), 'p95': percentile(values, 0.95),
            'p99': percentile(values, 0.99), 'max': values[-1]}
    return result


def measure(line, name):
    """One request line's value of a measure of MEASURES (milliseconds or seconds)."""
    base, unit = name.rsplit('_', 1)
    value = line.get(base + '_ms')
    if not isinstance(value, (int, float)):
        return None
    return value if unit == 'ms' else value / 1000.0
