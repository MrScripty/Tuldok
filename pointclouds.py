"""Bounded point-cloud decoding and byte-preserving immutable preparation."""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import io
import json
import math
import re
import struct
import zipfile

from workbench import WorkbenchError, text_value

PLY_LIMIT = 2 * 1024 * 1024
MANIFEST_LIMIT = 32 * 1024
HEADER_LIMIT = 16 * 1024
LINE_LIMIT = 1024
POINT_LIMIT = 20_000
PREVIEW_LIMIT = 512
BUNDLE_LIMIT = PLY_LIMIT + MANIFEST_LIMIT + 1024
NUMBER = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
INTEGER = re.compile(r'^(?:0|[1-9][0-9]*)$')
HASH = re.compile(r'^[a-f0-9]{64}$')
SOURCE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$')


def invalid(message):
    raise WorkbenchError('Invalid point cloud: ' + message)


def exact(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        invalid(name + ' fields do not match the profile.')


def manifest(raw, geometry):
    if not 0 < len(raw) <= MANIFEST_LIMIT:
        invalid('sidecar byte cap exceeded.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                invalid('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        invalid('nonfinite JSON value: ' + value)
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, WorkbenchError):
            raise
        invalid('malformed UTF-8 JSON.')
    exact(value, ('format', 'geometry_file', 'geometry_bytes', 'geometry_sha256', 'units',
                  'coordinate_system', 'provenance', 'lineage'), 'sidecar')
    if value['format'] != 'tuldok_pointcloud_v1':
        raise WorkbenchError('Unsupported point-cloud sidecar version.', 'unsupported')
    if value['geometry_file'] != 'points.ply' or type(value['geometry_bytes']) is not int or value['geometry_bytes'] != len(geometry):
        invalid('geometry filename or byte count mismatch.')
    digest = value['geometry_sha256']
    if type(digest) is not str or not HASH.fullmatch(digest) or hashlib.sha256(geometry).hexdigest() != digest:
        invalid('geometry SHA256 mismatch or invalid lowercase hex.')
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
    lineage = value['lineage']
    exact(lineage, ('source_id', 'source_sha256'), 'lineage')
    if type(lineage['source_id']) is not str or not SOURCE_ID.fullmatch(lineage['source_id']):
        invalid('lineage source ID must be a bounded identifier, not a path.')
    if type(lineage['source_sha256']) is not str or not HASH.fullmatch(lineage['source_sha256']):
        invalid('lineage source SHA256 must be lowercase hex.')
    return value


def native(token, dtype):
    if dtype == 'uchar':
        if not INTEGER.fullmatch(token) or int(token) > 255:
            invalid('RGB must be integers from 0 to 255.')
        return int(token)
    if not NUMBER.fullmatch(token):
        invalid('point scalar must be finite decimal text.')
    try:
        value = float(token)
        if not math.isfinite(value) or abs(value) > 1e12:
            invalid('point scalar exceeds finite magnitude bound.')
        if value == 0 and Decimal(token) != 0:
            invalid('point scalar has nonzero underflow.')
        if dtype == 'float':
            # Direct decimal-to-float32 rounding avoids float64 midpoint double rounding.
            bits = struct.unpack('<I', struct.pack('<f', abs(value)))[0]
            target = Fraction(Decimal(token).copy_abs())
            def binary(word):
                return struct.unpack('<f', struct.pack('<I', word))[0]
            center = Fraction.from_float(binary(bits))
            if bits:
                midpoint = (Fraction.from_float(binary(bits - 1)) + center) / 2
                if target < midpoint or (target == midpoint and bits % 2):
                    bits -= 1
            upper = (Fraction.from_float(binary(bits + 1)) + Fraction.from_float(binary(bits))) / 2
            if target > upper or (target == upper and bits % 2):
                bits += 1
            rounded = math.copysign(binary(bits), value)
            if value != 0 and rounded == 0:
                invalid('float point scalar has nonzero underflow.')
            value = rounded
        return value
    except (OverflowError, InvalidOperation, ValueError) as error:
        if isinstance(error, WorkbenchError):
            raise
        invalid('point scalar is not natively representable.')


def parse_ply(raw):
    if not 0 < len(raw) <= PLY_LIMIT:
        invalid('PLY byte cap exceeded.')
    if not raw.endswith(b'\n'):
        invalid('truncated PLY: final newline required.')
    if any(byte < 32 and byte not in (9, 10, 13) for byte in raw) or b'\r' in raw.replace(b'\r\n', b''):
        invalid('unsupported PLY control character.')
    if raw.count(b'\n') > POINT_LIMIT + HEADER_LIMIT:
        invalid('PLY line count cap exceeded.')
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError:
        invalid('PLY must be ASCII.')
    if any(len(line) > LINE_LIMIT for line in lines):
        invalid('PLY line byte cap exceeded.')
    if lines[:2] != ['ply', 'format ascii 1.0']:
        raise WorkbenchError('Unsupported PLY header; use ASCII 1.0.', 'unsupported')
    try:
        end = lines.index('end_header')
    except ValueError:
        invalid('truncated PLY header.')
    if sum(len(line) for line in raw.splitlines(keepends=True)[:end + 1]) > HEADER_LIMIT:
        invalid('PLY header byte cap exceeded.')
    header = [line.split() for line in lines[2:end] if not line.startswith('comment ')]
    if not header or len(header[0]) != 3 or header[0][:2] != ['element', 'vertex'] or not INTEGER.fullmatch(header[0][2]):
        invalid('expected bounded vertex element.')
    count = int(header[0][2])
    if not 0 < count <= POINT_LIMIT:
        invalid('point count cap exceeded.')
    properties = []
    for item in header[1:]:
        if len(item) != 3 or item[0] != 'property':
            invalid('only vertex scalar properties are supported.')
        properties.append({'name': item[2], 'dtype': item[1]})
    names = [item['name'] for item in properties]
    xyz, normals, colors = ['x', 'y', 'z'], ['nx', 'ny', 'nz'], ['red', 'green', 'blue']
    if names not in (xyz, xyz + normals, xyz + colors, xyz + normals + colors):
        invalid('properties require ordered XYZ, optional complete normals and RGB.')
    for item in properties:
        if item['dtype'] not in (('uchar',) if item['name'] in colors else ('float', 'double')):
            invalid('unsupported point property dtype.')
    if len(lines[end + 1:]) != count:
        invalid('truncated or trailing point data; counts mismatch.')
    points = []
    for line in lines[end + 1:]:
        tokens = line.split()
        if len(tokens) != len(properties):
            invalid('point property count mismatch.')
        points.append([native(token, item['dtype']) for token, item in zip(tokens, properties)])
    return {'properties': properties, 'points': points,
            'bounds': {'min': [min(point[i] for point in points) for i in range(3)],
                       'max': [max(point[i] for point in points) for i in range(3)]}}


def prepare(geometry_raw, manifest_raw):
    if not 0 < len(geometry_raw) <= PLY_LIMIT:
        invalid('PLY byte cap exceeded.')
    sidecar = manifest(manifest_raw, geometry_raw)
    geometry = parse_ply(geometry_raw)
    names = [item['name'] for item in geometry['properties']]
    metadata = {'manifest': sidecar, 'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
                'properties': geometry['properties'], 'point_count': len(geometry['points']),
                'bounds': geometry['bounds'], 'provided_normals': 'nx' in names, 'provided_colors': 'red' in names,
                'protected_groups': ['pointcloud-source:' + sidecar['lineage']['source_sha256'],
                                     'pointcloud-bytes:' + sidecar['geometry_sha256']],
                'scope': 'whole point cloud; declared source lineage; no training qualification'}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('points.ply'), geometry_raw)
        archive.writestr(zipfile.ZipInfo('points.json'), manifest_raw)
    return {'bundle': stream.getvalue(), 'metadata': metadata, 'geometry': geometry}
