"""Arrays in a product: NPY headers, the arrays of an NPZ, a two-axis slice and a summary, without numpy.

Owns the "Arrays" paragraph and the array_slice and array_summary rows of
section 3 of docs/plans/definition-first-projects/spec-d1.md. A header is
parsed with ast.literal_eval from at most HEADER_BYTES; versions 1, 2 and 3,
C and Fortran order, either byte order; floats of 2, 4 and 8 bytes, integers
of 1 to 8 bytes and booleans are read, and anything else (objects, complex,
strings, structured types) is refused unsupported. Nothing is unpickled. The
values a slice or a summary needs are gathered from the array's bytes (a
Blob of inside_archive, mapped or decompressed) at the strides they lie at,
byte column by byte column, so only those bytes are touched and no Python
loop runs per value; they are decoded with the array module (struct for
half floats). A summary reads at most SUMMARY_VALUES values, every n-th in
storage order beyond that.
"""
import ast
from array import array
import base64
import collections
import math
import operator
import struct
import sys
from itertools import repeat

from .store import ProjectError

HEADER_BYTES = 64 * 1024        # an NPY header
SUMMARY_VALUES = 4_000_000      # values read for one summary
DRAWN_MOST = 512                # rows and columns of a slice
_MAGIC = b'\x93NUMPY'
_NATIVE_LITTLE = sys.byteorder == 'little'
_SIGNED = {1: 'b', 2: 'h', 4: 'i', 8: 'q'}
_UNSIGNED = {1: 'B', 2: 'H', 4: 'I', 8: 'Q'}
_FLOATS = {4: 'f', 8: 'd'}
_NAMES = {'f': 'float', 'i': 'int', 'u': 'uint'}
assert all(array(code).itemsize == size for table in (_SIGNED, _UNSIGNED, _FLOATS) for size, code in table.items())


def _refuse(message, code='unsupported'):
    raise ProjectError(message, code)


class Header:
    """One NPY header: shape, descr, fortran, offset (of the data), and, when its type is read, kind ('f', 'i',
    'u' or 'b'), itemsize and little; problem says why it is not read otherwise."""

    def __init__(self, shape, descr, fortran, offset):
        self.shape, self.descr, self.fortran, self.offset = shape, descr, fortran, offset
        self.kind = self.itemsize = self.little = None
        self.problem = None
        if not isinstance(descr, str):
            self.problem = 'a structured type'
            return
        order, code, size = (descr[0], descr[1:2], descr[2:]) if descr[:1] in '<>|=' else ('=', descr[:1], descr[1:])
        if code == 'O':
            self.problem = 'an object array (it is never unpickled)'
            return
        if not size.isdigit():
            self.problem = f'the type {descr}'
            return
        size = int(size)
        if (code == 'f' and size in (2, 4, 8)) or (code in 'iu' and size in (1, 2, 4, 8)) or (code == 'b'
                                                                                                and size == 1):
            self.kind, self.itemsize = code, size
            self.little = _NATIVE_LITTLE if order in '=|' else order == '<'
        elif code == 'c':
            self.problem = 'a complex array'
        else:
            self.problem = f'the type {descr}'

    @property
    def dtype(self):
        """The type's name: float32, int16, uint8, bool, ...; the descr when it is not read."""
        if self.kind is None:
            return self.descr if isinstance(self.descr, str) else 'structured'
        if self.kind == 'b':
            return 'bool'
        return f'{_NAMES[self.kind]}{self.itemsize * 8}'

    @property
    def count(self):
        return math.prod(self.shape)

    def require(self, name):
        if self.problem is not None:
            _refuse(f'{name} is {self.problem}; Tuldok reads floats, integers and booleans.')

    def strides(self):
        """Bytes between neighbours along each axis."""
        steps, step = [0] * len(self.shape), self.itemsize
        axes = range(len(self.shape)) if self.fortran else reversed(range(len(self.shape)))
        for axis in axes:
            steps[axis] = step
            step *= self.shape[axis]
        return steps


def header_length(head):
    """The number of bytes before an NPY array's data, from at least its first 12 bytes; refused when not NPY."""
    if len(head) < 10 or bytes(head[:6]) != _MAGIC:
        _refuse('This is not an NPY array.')
    major = head[6]
    if major == 1:
        return 10 + struct.unpack_from('<H', head, 8)[0]
    if major in (2, 3) and len(head) >= 12:
        return 12 + struct.unpack_from('<I', head, 8)[0]
    _refuse(f'NPY version {major} is not read.')


def parse_header(head):
    """The Header of an NPY array from its first bytes (at least header_length of them)."""
    end = header_length(head)
    major = head[6]
    start = 10 if major == 1 else 12
    if end - start > HEADER_BYTES:
        _refuse(f'The NPY header is more than {HEADER_BYTES} bytes.')
    if len(head) < end:
        _refuse('The NPY header is cut short.')
    try:
        text = bytes(head[start:end]).decode('utf-8' if major == 3 else 'latin-1')
        value = ast.literal_eval(text.strip())
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError, UnicodeError):
        _refuse('The NPY header is not a literal Tuldok can read.')
    if (not isinstance(value, dict) or set(value) != {'descr', 'fortran_order', 'shape'}
            or not isinstance(value['fortran_order'], bool) or not isinstance(value['shape'], tuple)
            or not all(type(item) is int and item >= 0 for item in value['shape'])):
        _refuse('The NPY header must hold descr, fortran_order and a shape of whole numbers.')
    return Header(list(value['shape']), value['descr'], value['fortran_order'], end)


def read_header(place):
    """The Header of the NPY array a Place holds, reading only its first bytes."""
    head = place.head(12)
    return parse_header(place.head(header_length(head)))


# ------------------------------------------------------------------- reading

def gather(view, start, step, count, itemsize):
    """The bytes of count values of itemsize, the first at start and each step bytes after the one before."""
    if count <= 0:
        return b''
    if step == itemsize:
        return bytes(view[start:start + count * itemsize])
    out = bytearray(count * itemsize)
    last = start + (count - 1) * step
    for byte in range(itemsize):
        out[byte::itemsize] = view[start + byte:last + byte + 1:step]
    return out


def decode(raw, header):
    """The values in raw (a whole number of header's items) as an array, or a tuple for half floats."""
    if header.kind == 'f' and header.itemsize == 2:
        return struct.unpack(('<' if header.little else '>') + f'{len(raw) // 2}e', raw)
    if header.kind == 'f':
        values = array(_FLOATS[header.itemsize])
    elif header.kind == 'i':
        values = array(_SIGNED[header.itemsize])
    else:
        values = array(_UNSIGNED[header.itemsize])
    values.frombytes(raw)
    if header.little != _NATIVE_LITTLE and header.itemsize > 1:
        values.byteswap()
    if header.kind == 'b':
        values = array('B', (1 if value else 0 for value in values))
    return values


def _check_length(blob, header, name):
    if header.offset + header.count * header.itemsize > len(blob.view):
        _refuse(f'{name} is shorter than its shape says.')


def float32_base64(values):
    """values as base64 of little-endian 32-bit floats."""
    packed = array('f', values)
    if not _NATIVE_LITTLE:
        packed.byteswap()
    return base64.b64encode(packed.tobytes()).decode('ascii')


def _finite_range(values):
    """(minimum, maximum, count of non-finite) of numbers; the minimum and maximum of the finite ones."""
    try:
        total = sum(values)
        finite = values if isinstance(total, int) or math.isfinite(total) else None
    except OverflowError:
        finite = None
    if finite is None:
        finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return None, None, len(values)
    return min(finite), max(finite), len(values) - len(finite)


def array_slice(blob, header, name, *, axes=None, index=None, most=256):
    """Two axes of an array, at index on the others, at most most rows and columns (one stride for both)."""
    header.require(name)
    _check_length(blob, header, name)
    shape, ndim = header.shape, len(header.shape)
    if axes is None:
        axes = list(range(max(0, ndim - 2), ndim))
    if ndim >= 2 and (len(axes) != 2 or axes[0] == axes[1] or not all(0 <= axis < ndim for axis in axes)):
        _refuse(f'axes must be two different axes of the {ndim} of {name}.', 'invalid')
    if ndim < 2 and list(axes) != list(range(ndim)):
        _refuse(f'{name} has {ndim} axes; leave axes out.', 'invalid')
    if index is None:
        index = [size // 2 for size in shape]
    if len(index) != ndim:
        _refuse(f'index must give one position for each of the {ndim} axes of {name}.', 'invalid')
    for axis, (position, size) in enumerate(zip(index, shape)):
        if axis not in axes and not 0 <= position < size:
            _refuse(f'Position {position} is outside axis {axis} of {name}, which has {size}.', 'invalid')
    steps = header.strides()
    base = header.offset + sum(position * steps[axis] for axis, position in enumerate(index) if axis not in axes)
    if ndim >= 2:
        full_rows, full_columns = shape[axes[0]], shape[axes[1]]
        row_step, column_step = steps[axes[0]], steps[axes[1]]
    else:
        full_rows, full_columns = 1, (shape[0] if ndim else 1)
        row_step, column_step = 0, (steps[0] if ndim else header.itemsize)
    stride = max(1, math.ceil(full_rows / most), math.ceil(full_columns / most))
    rows, columns = math.ceil(full_rows / stride), math.ceil(full_columns / stride)
    values = []
    if rows and columns:
        if row_step == header.itemsize and column_step != header.itemsize and rows > 1:
            # Rows lie next to each other: read each column whole, then turn them into rows.
            by_column = [decode(gather(blob.view, base + column * stride * column_step, stride * row_step, rows,
                                        header.itemsize), header) for column in range(columns)]
            for row in range(rows):
                values.extend(column[row] for column in by_column)
        else:
            for row in range(rows):
                values.extend(decode(gather(blob.view, base + row * stride * row_step, stride * column_step,
                                             columns, header.itemsize), header))
    low, high, nonfinite = _finite_range(values)
    return {'shape': shape, 'dtype': header.dtype, 'axes': list(axes), 'index': list(index), 'rows': rows,
            'columns': columns, 'stride': stride, 'values_f32': float32_base64(values), 'min': low, 'max': high,
            'nonfinite': nonfinite}


def array_summary(blob, header, name, *, bins=64):
    """Count, range, mean, deviation, zeros, non-finite and a histogram of an array, every stride-th value."""
    header.require(name)
    _check_length(blob, header, name)
    count = header.count
    stride = max(1, math.ceil(count / SUMMARY_VALUES))
    read = math.ceil(count / stride)
    size = header.itemsize
    values = array('d')
    chunk = max(1, (1 << 20) // stride) * stride   # values of the array per piece, a multiple of the stride
    for first in range(0, count, chunk):
        taken = math.ceil(min(chunk, count - first) / stride)
        piece = decode(gather(blob.view, header.offset + first * size, stride * size, taken, size), header)
        values.extend(piece.tolist() if isinstance(piece, array) else piece)
    assert len(values) == read
    result = {'shape': header.shape, 'dtype': header.dtype, 'count': count, 'stride': stride}
    try:
        total = math.fsum(values)
    except (OverflowError, ValueError):
        total = math.nan
    finite = values if math.isfinite(total) else array('d', filter(math.isfinite, values))
    result['nonfinite'] = len(values) - len(finite)
    if not finite:
        return {**result, 'min': None, 'max': None, 'mean': None, 'std': None, 'zeros': 0,
                'histogram': {'low': None, 'high': None, 'counts': [0] * bins}}
    try:
        mean = (total if finite is values else math.fsum(finite)) / len(finite)
    except OverflowError:
        mean = math.inf
    deviations = array('d', map(operator.sub, finite, repeat(mean)))
    std = math.sqrt(math.fsum(map(operator.mul, deviations, deviations)) / len(finite))
    low, high = min(finite), max(finite)
    counts = [0] * bins
    if high > low:
        scale = bins / (high - low)
        for position, many in collections.Counter(map(int, map(operator.mul, map(operator.sub, finite, repeat(low)),
                                                             repeat(scale)))).items():
            counts[min(position, bins - 1)] += many
    else:
        counts[0] = len(finite)
    integral = header.kind != 'f'
    return {**result, 'min': int(low) if integral else low, 'max': int(high) if integral else high, 'mean': mean,
            'std': std, 'zeros': finite.count(0), 'histogram': {'low': low, 'high': high, 'counts': counts}}


def columns(blob, header, name, wanted, most):
    """The first wanted columns of a two-axis array (N, at least wanted), every stride-th row, at most most rows.

    Returns (rows in all, stride, [values of each column]).
    """
    header.require(name)
    _check_length(blob, header, name)
    if len(header.shape) != 2 or header.shape[1] < wanted:
        _refuse(f'{name} must have the shape (N, {wanted} or more).')
    total = header.shape[0]
    stride = max(1, math.ceil(total / most))
    taken = math.ceil(total / stride)
    row_step, column_step = header.strides()
    return total, stride, [decode(gather(blob.view, header.offset + column * column_step, stride * row_step, taken,
                                          header.itemsize), header) for column in range(wanted)]
