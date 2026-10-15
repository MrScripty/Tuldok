"""Independent analytic B consumer kernel, frozen before B producer inspection.

This module consumes numbers; it never trains, runs a producer, or authorizes
data. A later adapter must supply the exact admitted configuration and proven
train-only population, shapes, field identities and retained bytes. No artifact
names or Run protocol are selected here. Numerical agreement is not physical
quality or product acceptance.
"""
import ast
from dataclasses import dataclass
import hashlib
import math
import struct

ABS_TOLERANCE = REL_TOLERANCE = 1e-10
MAX_POINTS = 65536
MAX_UPDATES = 1000000
ARRAY_LIMIT = 8192


class OracleError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise OracleError(reason)


def finite(value, label):
    require(type(value) in (int, float), label + ' must be numeric without coercion.')
    try:
        result = float(value)
    except OverflowError:
        raise OracleError(label + ' is outside finite float64.') from None
    require(math.isfinite(result), label + ' must be finite.')
    return result


def numbers(values, label):
    require(type(values) in (tuple, list) and 1 <= len(values) <= MAX_POINTS,
            label + ' must be a bounded nonempty flat sequence.')
    return tuple(finite(value, label) for value in values)


def checked_shape(shape, count):
    require(type(shape) is tuple and 1 <= len(shape) <= 3 and
            all(type(n) is int and 1 <= n <= 129 for n in shape) and
            math.prod(shape) == count <= MAX_POINTS,
            'Exact shape and flat field length must agree.')
    return shape


def close(actual, expected, label):
    actual, expected = finite(actual, label), finite(expected, label)
    difference = abs(actual - expected)
    require(math.isfinite(difference) and
            difference <= ABS_TOLERANCE + REL_TOLERANCE * abs(expected),
            label + ' differs beyond the frozen tolerance.')
    return difference


@dataclass(frozen=True)
class Population:
    mean_initial: float
    std_initial: float
    mean_source: float
    std_source: float
    correlation: float
    count: int


def validate_population(population):
    require(type(population) is Population, 'An explicit train-only population is required.')
    for label in ('mean_initial', 'std_initial', 'mean_source', 'std_source', 'correlation'):
        finite(getattr(population, label), label)
    require(population.std_initial > 0 and population.std_source > 0 and
            -1 <= population.correlation <= 1 and type(population.count) is int and
            2 <= population.count <= MAX_POINTS, 'Population variance/correlation/count differs.')
    return population


def training_population(initial, source):
    """Compute population statistics from *only* caller-authenticated fit cells.

    Membership authority belongs to the future retained-data adapter. This pure
    function cannot prove a split from an array or detect moment-preserving data
    substitution; the adapter must check exact ordered fit identities separately.
    """
    initial, source = numbers(initial, 'Training initial'), numbers(source, 'Training source')
    require(len(initial) == len(source) and len(initial) >= 2, 'Training feature populations differ.')
    try:
        n = len(initial)
        mx, ms = math.fsum(initial) / n, math.fsum(source) / n
        sx = math.sqrt(math.fsum((value-mx)**2 for value in initial) / n)
        ss = math.sqrt(math.fsum((value-ms)**2 for value in source) / n)
        require(sx > 0 and ss > 0, 'Both train-only population variances must be positive.')
        r = math.fsum(((x-mx)/sx)*((s-ms)/ss) for x, s in zip(initial, source, strict=True)) / n
    except (OverflowError, ValueError):
        raise OracleError('Training statistics exceed finite arithmetic.') from None
    require(math.isfinite(r) and abs(r) <= 1 + 1e-12, 'Derived covariance is outside its domain.')
    # Only absorb floating roundoff at a singular covariance edge, never an
    # arbitrary caller-supplied out-of-domain correlation.
    return validate_population(Population(mx, sx, ms, ss, max(-1.0, min(1.0, r)), n))


def verify_population(observed, training_initial, training_source):
    """Reject retained normalization inconsistent with the exact fit population."""
    validate_population(observed)
    expected = training_population(training_initial, training_source)
    require(observed.count == expected.count, 'Normalization fit population count differs.')
    for key in ('mean_initial', 'std_initial', 'mean_source', 'std_source', 'correlation'):
        close(getattr(observed, key), getattr(expected, key), 'Train-only ' + key)
    return expected


def closed_form_state(population, learning_rate, updates, initial_state=(0.0, 0.0, 0.0)):
    """Return [a,b,c] after full-batch raw-target MSE updates, without an optimizer.

    Standardized covariance is [[1,r],[r,1]]. Its two feature-error
    eigenmodes decay by (1-2*lr*(1+r))**t and (1-2*lr*(1-r))**t.
    The intercept decays independently by (1-2*lr)**t. At r=+/-1 the
    unidentified null mode is preserved; no unique coefficient claim is made.
    """
    p = validate_population(population)
    rate = finite(learning_rate, 'Learning rate')
    require(0 < rate <= 0.5, 'Learning rate must lie in (0, 0.5].')
    require(type(updates) is int and 0 <= updates <= MAX_UPDATES, 'Update count must be a bounded exact integer.')
    state = numbers(initial_state, 'Initial model state')
    require(len(state) == 3, 'Affine state requires exactly three coefficients.')
    if updates == 0:
        return state
    optimum = (0.5*p.std_initial, 0.2*p.std_source,
               0.5*p.mean_initial + 0.2*p.mean_source + 0.25)
    require(all(math.isfinite(value) for value in optimum), 'Affine optimum exceeds finite arithmetic.')
    ea, eb = state[0]-optimum[0], state[1]-optimum[1]
    plus = (ea+eb)*(1-2*rate*(1+p.correlation))**updates
    minus = (ea-eb)*(1-2*rate*(1-p.correlation))**updates
    result = (optimum[0]+0.5*(plus+minus), optimum[1]+0.5*(plus-minus),
              optimum[2]+(state[2]-optimum[2])*(1-2*rate)**updates)
    require(all(math.isfinite(value) for value in result), 'Analytic state exceeds finite arithmetic.')
    return result


@dataclass(frozen=True)
class Fields:
    shape: tuple
    raw: tuple
    corrected: tuple


def _fields(initial, source, boundarymask, shape):
    initial, source = numbers(initial, 'Initial field'), numbers(source, 'Source field')
    require(len(initial) == len(source), 'Initial/source field lengths differ.')
    checked_shape(shape, len(initial))
    require(type(boundarymask) in (tuple, list) and len(boundarymask) == len(initial), 'Boundary mask shape differs.')
    require(all(type(value) in (bool, int, float) and value in (0, 1) for value in boundarymask),
            'Boundary mask must contain exact binary values.')
    return initial, source, tuple(bool(value) for value in boundarymask)


def reference_fields(initial, source, boundarymask, *, shape):
    initial, source, mask = _fields(initial, source, boundarymask, shape)
    raw = tuple(0.5*x + 0.25 + 0.2*s for x, s in zip(initial, source, strict=True))
    require(all(math.isfinite(value) for value in raw), 'Reference field exceeds finite arithmetic.')
    return Fields(shape, raw, tuple(0.0 if selected else value for selected, value in zip(mask, raw, strict=True)))


def reconstruct(initial, source, boundarymask, population, state, *, shape):
    """Reconstruct raw affine output, then exactly zero boundary-mask cells.

    Raw-target training and post-model boundary correction are separate stages.
    Masked values must never replace the raw targets used by closed_form_state.
    """
    initial, source, mask = _fields(initial, source, boundarymask, shape)
    p = validate_population(population); state = numbers(state, 'Retained model state')
    require(len(state) == 3, 'Affine state requires exactly three coefficients.')
    a, b, c = state
    raw = tuple(a*((x-p.mean_initial)/p.std_initial) + b*((s-p.mean_source)/p.std_source) + c
                for x, s in zip(initial, source, strict=True))
    require(all(math.isfinite(value) for value in raw), 'Reconstructed field exceeds finite arithmetic.')
    return Fields(shape, raw, tuple(0.0 if selected else value for selected, value in zip(mask, raw, strict=True)))


def retallied_mse(actual, reference):
    actual, reference = numbers(actual, 'Actual field'), numbers(reference, 'Reference field')
    require(len(actual) == len(reference), 'MSE populations differ.')
    try:
        value = math.fsum((left-right)**2 for left, right in zip(actual, reference, strict=True)) / len(actual)
    except (OverflowError, ValueError):
        raise OracleError('Retallied MSE exceeds finite arithmetic.') from None
    require(math.isfinite(value), 'Retallied MSE must be finite.')
    return value


def verify_values(actual, expected, label='Retained field'):
    actual, expected = numbers(actual, label), numbers(expected, 'Expected field')
    require(len(actual) == len(expected), 'Compared field populations differ.')
    return max(close(left, right, label) for left, right in zip(actual, expected, strict=True))


def closed(value, fields, label):
    require(isinstance(value, dict) and set(value) == set(fields), label + ' fields differ from the frozen contract.')


# The following bounded literal NPY reader is unchanged from the independently
# frozen A oracle 0f6128d7 (also retained in canonical A oracle 573f142d). Its
# selected shape is a caller argument; it does not choose a B artifact layout.
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


def decode_npy(raw, shape_zyx):
    """Bounded data-only NPY decode with exact native payload identity.

    The adapter selects the admitted shape; this wrapper does not infer fields
    or artifact roles. Rank-one state vectors are also supported when explicitly
    selected. The unchanged A parser performs the literal-header checks first.
    """
    require(type(raw) is bytes and type(shape_zyx) in (list, tuple), 'Select exact NPY bytes and shape.')
    shape = tuple(shape_zyx)
    require(1 <= len(shape) <= 3 and all(type(n) is int and 1 <= n <= 64 for n in shape),
            'Selected NPY shape must contain bounded exact dimensions.')
    values = npy(raw, shape)
    start = 10 if raw[6:8] == b'\x01\x00' else 12
    offset = start + int.from_bytes(raw[8:start], 'little')
    return dict(values=values, payload_sha256=hashlib.sha256(raw[offset:]).hexdigest(), shape_zyx=list(shape))
