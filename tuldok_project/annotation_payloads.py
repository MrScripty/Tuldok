"""The payloads of annotations too large for a line: masks (PNG or runs) and arrays (.npy), read and written.

Owns the byte formats of section 1 and 2 of
docs/plans/training-and-curation/spec-t4.md: a sidecar PNG (8- or 16-bit
greyscale, not interlaced), a mask's runs ([value, count] row by row), and a
sidecar .npy (a 1-D or 2-D array of floats or whole numbers, C order). It is
pure and uses the standard library alone (the step process imports it): it
opens no file, never unpickles, and bounds what it decodes. Every reader
raises PayloadError with a sentence when the bytes are not what is wanted.
"""
from array import array
import ast
import hashlib
import struct
import sys
import zlib

PIXEL_LIMIT = 16 * 1024 * 1024        # pixels of a mask or a depth map
NPY_HEADER_LIMIT = 64 * 1024
SIDECAR_LIMIT = 64 * 1024 * 1024      # bytes of one sidecar
NAME_LENGTH = 16                      # hexadecimal characters of a kept sidecar's name
_PNG = b'\x89PNG\r\n\x1a\n'
_NPY = b'\x93NUMPY'
_LITTLE = sys.byteorder == 'little'
_CODES = {('f', 4): 'f', ('f', 8): 'd', ('i', 1): 'b', ('i', 2): 'h', ('i', 4): 'i', ('i', 8): 'q',
          ('u', 1): 'B', ('u', 2): 'H', ('u', 4): 'I', ('u', 8): 'Q'}


class PayloadError(ValueError):
    """Bytes that are not the payload wanted; the message is a sentence."""


def kept_name(data, extension):
    """The name of a sidecar in annotations/<task>/: the first 16 hex of its SHA-256 and its extension."""
    return hashlib.sha256(data).hexdigest()[:NAME_LENGTH] + extension


def is_kept_name(name):
    stem, _, extension = name.partition('.')
    return (len(stem) == NAME_LENGTH and all(char in '0123456789abcdef' for char in stem)
            and extension in ('png', 'npy'))


# ------------------------------------------------------------------- PNG

def png_size(data):
    """(width, height, bit depth, colour type, interlace) from a PNG's header; PayloadError when it is not one."""
    if len(data) < 33 or data[:8] != _PNG or data[12:16] != b'IHDR':
        raise PayloadError('The file is not a PNG.')
    width, height, depth, colour, _compression, _filter, interlace = struct.unpack('>IIBBBBB', data[16:29])
    return width, height, depth, colour, interlace


def read_png(data):
    """(width, height, values) of an 8- or 16-bit greyscale PNG that is not interlaced; values row by row."""
    width, height, depth, colour, interlace = png_size(data)
    if colour != 0 or depth not in (8, 16) or interlace != 0:
        raise PayloadError('A mask PNG must be 8- or 16-bit greyscale and not interlaced.')
    if width * height > PIXEL_LIMIT or not width or not height:
        raise PayloadError(f'A mask of {width} by {height} pixels is empty or over {PIXEL_LIMIT:,} pixels.')
    at, chunks = 8, []
    while at + 8 <= len(data):
        length, kind = struct.unpack('>I4s', data[at:at + 8])
        if kind == b'IDAT':
            chunks.append(data[at + 8:at + 8 + length])
        elif kind == b'IEND':
            break
        at += 12 + length
    size = depth // 8
    stride = width * size
    try:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(b''.join(chunks), (stride + 1) * height + 1)
    except zlib.error:
        raise PayloadError('The PNG cannot be decompressed.') from None
    if len(raw) < (stride + 1) * height:
        raise PayloadError('The PNG holds fewer rows than its size says.')
    out, previous = bytearray(), bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride if kind else 0):
            left = line[i - size] if i >= size else 0
            up = previous[i]
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + ((left + up) >> 1)) & 255
            elif kind == 4:
                corner = previous[i - size] if i >= size else 0
                guess = left + up - corner
                a, b, c = abs(guess - left), abs(guess - up), abs(guess - corner)
                line[i] = (line[i] + (left if a <= b and a <= c else up if b <= c else corner)) & 255
            else:
                raise PayloadError(f'The PNG uses the unknown row filter {kind}.')
        out += line
        previous = line
    if size == 1:
        values = array('H')
        values.extend(out)
        return width, height, values
    values = array('H', bytes(out))
    if _LITTLE:
        values.byteswap()
    return width, height, values


def write_png(width, height, values):
    """An 8-bit (all values below 256) or 16-bit greyscale PNG of values row by row."""
    wide = any(value > 255 for value in values)
    rows = bytearray()
    for row in range(height):
        rows.append(0)
        chunk = values[row * width:(row + 1) * width]
        rows += struct.pack(f'>{width}H', *chunk) if wide else bytes(chunk)

    def part(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
    return (_PNG + part(b'IHDR', struct.pack('>IIBBBBB', width, height, 16 if wide else 8, 0, 0, 0, 0))
            + part(b'IDAT', zlib.compress(bytes(rows), 9)) + part(b'IEND', b''))


# ------------------------------------------------------------------ runs

def runs_total(runs):
    """The pixels runs cover; PayloadError when they are not [value, count] pairs of whole numbers."""
    total = 0
    for run in runs:
        if (not isinstance(run, list) or len(run) != 2 or not all(type(item) is int for item in run)
                or not 0 <= run[0] <= 65535 or run[1] < 1):
            raise PayloadError('A run must be [value, count]: a value from 0 to 65,535 and a count above zero.')
        total += run[1]
    return total


def decode_runs(runs, width, height):
    """The values of a mask given as runs, row by row."""
    if runs_total(runs) != width * height:
        raise PayloadError(f'The runs cover {runs_total(runs):,} pixels; the image has {width * height:,}.')
    out = array('H')
    for value, count in runs:
        out.extend([value]) if count == 1 else out.extend(array('H', [value]) * count)
    return out


def encode_runs(values):
    """values as runs [[value, count], ...]."""
    runs, last, count = [], None, 0
    for value in values:
        if value == last:
            count += 1
        else:
            if count:
                runs.append([last, count])
            last, count = value, 1
    if count:
        runs.append([last, count])
    return runs


# ------------------------------------------------------------------- NPY

def npy_header(data):
    """(shape, kind, itemsize, little, offset) of an NPY array in C order of floats or whole numbers."""
    if len(data) < 10 or data[:6] != _NPY:
        raise PayloadError('The file is not an NPY array.')
    major = data[6]
    if major == 1:
        start, end = 10, 10 + struct.unpack_from('<H', data, 8)[0]
    elif major in (2, 3) and len(data) >= 12:
        start, end = 12, 12 + struct.unpack_from('<I', data, 8)[0]
    else:
        raise PayloadError(f'NPY version {major} is not read.')
    if end - start > NPY_HEADER_LIMIT or len(data) < end:
        raise PayloadError('The NPY header is too long or cut short.')
    try:
        header = ast.literal_eval(data[start:end].decode('latin-1').strip())
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        raise PayloadError('The NPY header is not a literal Tuldok reads.') from None
    if (not isinstance(header, dict) or set(header) != {'descr', 'fortran_order', 'shape'}
            or not isinstance(header['shape'], tuple) or not all(type(n) is int and n >= 0 for n in header['shape'])):
        raise PayloadError('The NPY header must hold descr, fortran_order and a shape of whole numbers.')
    descr = header['descr']
    if not isinstance(descr, str) or len(descr) < 3 or descr[0] not in '<>|=' or not descr[2:].isdigit():
        raise PayloadError('The NPY array must be of floats or whole numbers.')
    kind, itemsize = descr[1], int(descr[2:])
    if (kind, itemsize) not in _CODES:
        raise PayloadError(f'The NPY type {descr} is not read; use float32, float64 or whole numbers.')
    if header['fortran_order'] and len(header['shape']) > 1:
        raise PayloadError('The NPY array must be in C order.')
    little = _LITTLE if descr[0] in '=|' else descr[0] == '<'
    return list(header['shape']), kind, itemsize, little, end


def read_npy(data, most=PIXEL_LIMIT):
    """(shape, kind, values) of an NPY array of at most most values."""
    shape, kind, itemsize, little, offset = npy_header(data)
    count = 1
    for n in shape:
        count *= n
    if count > most:
        raise PayloadError(f'The array holds {count:,} values; at most {most:,} are read.')
    raw = data[offset:offset + count * itemsize]
    if len(raw) < count * itemsize:
        raise PayloadError('The NPY array is shorter than its shape says.')
    values = array(_CODES[(kind, itemsize)])
    values.frombytes(raw)
    if itemsize > 1 and little != _LITTLE:
        values.byteswap()
    return shape, kind, values


def write_npy(shape, values, descr):
    """The bytes of an NPY array (version 1) of values in C order; descr such as '<f4' or '<i4'."""
    header = "{'descr': '%s', 'fortran_order': False, 'shape': (%s), }" % (
        descr, ''.join(f'{n}, ' for n in shape) if len(shape) == 1 else ', '.join(str(n) for n in shape))
    pad = 64 - (10 + len(header) + 1) % 64
    text = (header + ' ' * pad + '\n').encode('latin-1')
    kind, itemsize = descr[1], int(descr[2:])
    packed = array(_CODES[(kind, itemsize)], values)
    if not _LITTLE:
        packed.byteswap()
    return _NPY + b'\x01\x00' + struct.pack('<H', len(text)) + text + packed.tobytes()


# --------------------------------------------------------------- sidecars

def sidecar_problem(task, data, *, size=None, points=None):
    """A sentence when data is not a sidecar task's value may name (spec-t4.md section 1), else None.

    size is (width, height) of the image a mask or depth map covers, points
    the count of the cloud a point-id file covers; each is checked when given.
    """
    if len(data) > SIDECAR_LIMIT:
        return f'The sidecar is over {SIDECAR_LIMIT:,} bytes.'
    try:
        if task == 'mask':
            width, height, depth, colour, interlace = png_size(data)
            if colour != 0 or depth not in (8, 16) or interlace:
                return 'A mask PNG must be 8- or 16-bit greyscale and not interlaced.'
            if size is not None and (width, height) != tuple(size):
                return f'The mask is {width} by {height} pixels; the image is {size[0]} by {size[1]}.'
            return None
        shape, kind, _itemsize, _little, _offset = npy_header(data)
        if task == 'depth':
            if len(shape) != 2:
                return f'A depth map must be a 2-D array; this one has shape {tuple(shape)}.'
            if size is not None and (shape[1], shape[0]) != tuple(size):
                return f'The depth map is {shape[1]} by {shape[0]}; the image is {size[0]} by {size[1]}.'
            if shape[0] * shape[1] > PIXEL_LIMIT:
                return f'The depth map is over {PIXEL_LIMIT:,} values.'
            return None
        if len(shape) != 1 or kind == 'f':
            return 'A point-id file must be a 1-D array of whole numbers.'
        if points is not None and shape[0] != points:
            return f'The point-id file has {shape[0]} values; the cloud has {points} points.'
        return None
    except PayloadError as exc:
        return str(exc)
