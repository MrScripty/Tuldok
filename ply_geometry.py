"""Shared bounded ASCII PLY file mechanics for two concrete geometry profiles."""
import base64
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import math
import re
import struct
from workbench import WorkbenchError, text_value

PLY_LIMIT = 2 * 1024 * 1024
MANIFEST_LIMIT = 32 * 1024
HEADER_LIMIT = 16 * 1024
LINE_LIMIT = 1024
MAX_REQUEST = 3 * 1024 * 1024
BUNDLE_LIMIT = PLY_LIMIT + MANIFEST_LIMIT + 1024
NUMBER = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
INTEGER = re.compile(r'^(?:0|[1-9][0-9]*)$')
HASH = re.compile(r'^[a-f0-9]{64}$')


def invalid(message):
    raise WorkbenchError('Invalid geometry: ' + message)


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        invalid('nonfinite JSON value: ' + value)
    def number(value):
        result = float(value)
        if not math.isfinite(result) or (result == 0 and Decimal(value) != 0):
            invalid('JSON number is not finite representable data.')
        return result
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (UnicodeError, ValueError, RecursionError, InvalidOperation) as error:
        if isinstance(error, WorkbenchError):
            raise
        invalid('malformed UTF-8 JSON.')


def exact(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        invalid(name + ' fields do not match the profile.')


def manifest(raw, geometry, *, format_name='tuldok_mesh_v1', filename='mesh.ply', extra=()):
    if not 0 < len(raw) <= MANIFEST_LIMIT:
        invalid('sidecar byte cap exceeded.')
    value = parse_json(raw)
    exact(value, ('format', 'geometry_file', 'geometry_bytes', 'geometry_sha256', 'units', 'coordinate_system', 'provenance') + tuple(extra), 'sidecar')
    if type(value['format']) is not str:
        invalid('format must be a string.')
    if value['format'] != format_name:
        raise WorkbenchError('Unsupported geometry sidecar version.', 'unsupported')
    if value['geometry_file'] != filename or type(value['geometry_bytes']) is not int or value['geometry_bytes'] != len(geometry):
        invalid('geometry filename or byte count mismatch.')
    digest = value['geometry_sha256']
    if type(digest) is not str or not HASH.fullmatch(digest):
        invalid('geometry SHA256 must be lowercase hex.')
    if hashlib.sha256(geometry).hexdigest() != digest:
        invalid('geometry SHA256 mismatch.')
    if value['units'] not in ('m', 'cm', 'mm'):
        invalid('units must be m, cm or mm.')
    frame = value['coordinate_system']
    exact(frame, ('frame', 'handedness', 'up_axis'), 'coordinate system')
    text_value(frame['frame'], 'Coordinate frame', 120)
    if frame['handedness'] not in ('right', 'left') or frame['up_axis'] not in ('x', 'y', 'z'):
        invalid('handedness or up axis is outside the profile.')
    exact(value['provenance'], ('source', 'revision', 'license', 'description'), 'provenance')
    for key, item in value['provenance'].items():
        text_value(item, 'Declared provenance ' + key, 1000)
    return value


def native(token, dtype):
    if not NUMBER.fullmatch(token):
        invalid('vertex scalar must be finite decimal text.')
    try:
        value = float(token)
        if not math.isfinite(value) or abs(value) > 1e12:
            invalid('vertex scalar exceeds finite magnitude bound.')
        if value == 0 and Decimal(token) != 0:
            invalid('vertex scalar has nonzero underflow.')
        if dtype == 'float':
            # float64 -> float32 can double-round near decimal midpoint neighbors.
            # Compare exact decimal against adjacent IEEE values; ties select even bits.
            bits = struct.unpack('<I', struct.pack('<f', abs(value)))[0]
            exact_value = Fraction(Decimal(token).copy_abs())
            def binary(word):
                return struct.unpack('<f', struct.pack('<I', word))[0]
            center = Fraction.from_float(binary(bits))
            if bits > 0:
                midpoint = (Fraction.from_float(binary(bits - 1)) + center) / 2
                if exact_value < midpoint or (exact_value == midpoint and bits % 2):
                    bits -= 1
            upper = (Fraction.from_float(binary(bits + 1)) + Fraction.from_float(binary(bits))) / 2
            if exact_value > upper or (exact_value == upper and bits % 2):
                bits += 1
            rounded = math.copysign(binary(bits), value)
            if value != 0 and rounded == 0:
                invalid('float vertex scalar has nonzero underflow.')
            value = rounded
        return 0.0 if value == 0 else value
    except (OverflowError, InvalidOperation):
        invalid('vertex scalar is not natively representable.')


def ply_header(raw, vertex_limit, face_limit=0):
    if not 0 < len(raw) <= PLY_LIMIT:
        invalid('PLY byte cap exceeded.')
    if raw.count(b'\n') > vertex_limit + face_limit + HEADER_LIMIT:
        invalid('PLY line count cap exceeded.')
    if not raw.endswith(b'\n'):
        invalid('truncated PLY: final newline required.')
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError:
        invalid('PLY must be ASCII.')
    if any(len(line.encode('ascii')) > LINE_LIMIT for line in lines):
        invalid('PLY line byte cap exceeded.')
    # ASCII profile permits only tabs/spaces and LF/CRLF; splitlines must not hide controls.
    if any(byte < 32 and byte not in (9, 10, 13) for byte in raw) or b'\r' in raw.replace(b'\r\n', b''):
        invalid('PLY contains unsupported control characters.')
    if lines[:2] != ['ply', 'format ascii 1.0']:
        raise WorkbenchError('Unsupported PLY header; use ASCII 1.0.', 'unsupported')
    try:
        end = lines.index('end_header')
    except ValueError:
        invalid('truncated PLY header.')
    header_bytes = sum(len(line) for line in raw.splitlines(keepends=True)[:end + 1])
    if header_bytes > HEADER_LIMIT:
        invalid('PLY header byte cap exceeded.')
    header = [line.split() for line in lines[2:end] if not line.startswith('comment ')]
    return lines, end, header


def decode_file(value, cap, name):
    try:
        if type(value) is not str or len(value) > ((cap + 2) // 3) * 4:
            raise ValueError()
        raw = base64.b64decode(value, validate=True)
        if not 0 < len(raw) <= cap:
            raise ValueError()
        return raw
    except ValueError:
        invalid(name + ' must be a bounded complete base64 file.')


