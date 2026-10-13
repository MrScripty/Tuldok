"""Bounded NPY volume decoding and voxel-center projections; originals are authority."""
import ast
from decimal import Decimal
import hashlib
import io
import json
import math
import struct
import zipfile

from workbench import WorkbenchError, encode, text_value

HEADER_LIMIT = 4096
DIMENSION_LIMIT = 128
VOXEL_LIMIT = 2097152
NPY_LIMIT = VOXEL_LIMIT + HEADER_LIMIT + 10
MANIFEST_LIMIT = 32768
BUNDLE_LIMIT = NPY_LIMIT + MANIFEST_LIMIT + 1024
ORTHOGONAL_TOLERANCE = 1e-12


def invalid(message):
    raise WorkbenchError('Invalid volume: ' + message)


def parse_npy(raw):
    """Decode only NPY 1.0 uint8 C-order; never execute or unpickle input."""
    if type(raw) is not bytes or not 10 <= len(raw) <= NPY_LIMIT:
        invalid('NPY byte bound exceeded or header missing.')
    if raw[:8] != b'\x93NUMPY\x01\x00':
        invalid('only NPY version 1.0 is supported.')
    size = struct.unpack_from('<H', raw, 8)[0]
    end = 10 + size
    if not 0 < size <= HEADER_LIMIT or end > len(raw) or end % 16:
        invalid('NPY header length or alignment is invalid.')
    header = raw[10:end]
    if not header.endswith(b'\n'):
        invalid('NPY header must end in a newline.')
    try:
        tree = ast.parse(header.decode('ascii').strip(), mode='eval').body
        if not isinstance(tree, ast.Dict) or len(tree.keys) != 3:
            invalid('NPY header must contain exactly three unique fields.')
        keys = [ast.literal_eval(key) for key in tree.keys]
        if len(set(keys)) != 3:
            invalid('duplicate NPY header field.')
        value = ast.literal_eval(tree)
    except (SyntaxError, ValueError, TypeError, UnicodeError, RecursionError):
        invalid('malformed literal NPY header.')
    if set(value) != {'descr', 'fortran_order', 'shape'} or value['descr'] != '|u1' or value['fortran_order'] is not False:
        invalid('NPY requires uint8 |u1 dtype and C order.')
    shape = value['shape']
    if type(shape) is not tuple or len(shape) != 3 or any(type(n) is not int or not 0 < n <= DIMENSION_LIMIT for n in shape):
        invalid('shape must be three positive integer dimensions no greater than 128.')
    count = math.prod(shape)
    if count > VOXEL_LIMIT or len(raw) - end != count:
        invalid('voxel count exceeds its bound or data is truncated/trailing.')
    return {'shape': list(shape), 'data': raw[end:]}


def _exact(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        invalid(label + ' fields differ from the profile.')


def parse_json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                invalid('duplicate sidecar key.')
            value[key] = item
        return value
    def constant(value):
        invalid('nonfinite sidecar number.')
    def number(token):
        value = float(token)
        if not math.isfinite(value) or (value == 0 and Decimal(token) != 0):
            invalid('sidecar number overflows or underflows binary64.')
        return value
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant, parse_float=number)
    except (ValueError, UnicodeError, RecursionError):
        invalid('malformed UTF-8 sidecar JSON.')


def _affine(value, shape):
    if type(value) is not list or len(value) != 4 or any(type(row) is not list or len(row) != 4 for row in value):
        invalid('affine must be a 4 by 4 matrix.')
    try:
        if any(type(n) not in (int, float) or not math.isfinite(n) for row in value for n in row):
            invalid('affine values must be finite numbers.')
        if value[3] != [0, 0, 0, 1]:
            invalid('affine last row must be [0,0,0,1].')
        columns = [[value[row][column] for row in range(3)] for column in range(3)]
        lengths = [math.hypot(*axis) for axis in columns]
        if any(length == 0 or not math.isfinite(length) for length in lengths):
            invalid('affine axes must have finite nonzero spacing.')
        normalized = [[n / length for n in axis] for axis, length in zip(columns, lengths)]
        for left, right in ((0, 1), (0, 2), (1, 2)):
            if abs(math.fsum(a * b for a, b in zip(normalized[left], normalized[right]))) > ORTHOGONAL_TOLERANCE:
                invalid('affine axes must be orthogonal; shear is unsupported.')
        # All corners must remain finite, not just individual matrix coefficients.
        for z in (0, shape[0] - 1):
            for y in (0, shape[1] - 1):
                for x in (0, shape[2] - 1):
                    if any(not math.isfinite(sum(row[i] * n for i, n in enumerate((x, y, z, 1)))) for row in value[:3]):
                        invalid('physical voxel coordinates overflow.')
    except OverflowError:
        invalid('affine exceeds finite numerical bounds.')
    return lengths


def manifest(raw, source, volume):
    if type(raw) is not bytes or not 0 < len(raw) <= MANIFEST_LIMIT:
        invalid('sidecar exceeds its byte bound.')
    value = parse_json(raw)
    _exact(value, ('format', 'volume_file', 'volume_bytes', 'volume_sha256', 'shape', 'dtype', 'order',
                   'value_semantics', 'units', 'affine', 'provenance'), 'sidecar')
    if value['format'] != 'tuldok_volume_v1' or value['volume_file'] != 'volume.npy':
        invalid('unsupported sidecar version or filename.')
    if type(value['volume_bytes']) is not int or value['volume_bytes'] != len(source) or value['volume_sha256'] != hashlib.sha256(source).hexdigest():
        invalid('source length or SHA256 mismatch.')
    shape = value['shape']
    if type(shape) is not list or any(type(n) is not int for n in shape) or shape != volume['shape'] or value['dtype'] != 'uint8' or value['order'] != 'C':
        invalid('sidecar shape/dtype/order differs from source.')
    text_value(value['value_semantics'], 'Value semantics', 1000)
    if value['units'] not in ('m', 'cm', 'mm'):
        invalid('units must be m, cm or mm.')
    _exact(value['provenance'], ('source', 'revision', 'license', 'description'), 'provenance')
    for key, item in value['provenance'].items():
        text_value(item, 'Provenance ' + key, 1000)
    _affine(value['affine'], shape)
    return value


def prepare(volume_raw, manifest_raw):
    volume = parse_npy(volume_raw)
    sidecar = manifest(manifest_raw, volume_raw, volume)
    # Header/sidecar text variations cannot split identical voxel content into families.
    family = hashlib.sha256(encode(volume['shape']).encode() + volume['data']).hexdigest()
    metadata = {'manifest': sidecar, 'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
                'source_sha256': sidecar['volume_sha256'], 'shape': volume['shape'], 'dtype': 'uint8', 'order': 'C',
                'voxel_count': len(volume['data']), 'spacing_xyz': _affine(sidecar['affine'], volume['shape']),
                'protected_groups': ['volume-source:' + sidecar['volume_sha256'], 'volume-family:' + family],
                'scope': 'whole uint8 volume inspection; no medical, segmentation or training qualification'}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('volume.npy'), volume_raw)
        archive.writestr(zipfile.ZipInfo('volume.json'), manifest_raw)
    return {'bundle': stream.getvalue(), 'metadata': metadata, 'volume': volume}


def project_slice(prepared, axis, index):
    """Project an index plane, preserving native orientation without resampling.

    Rows/columns are y/x for z, z/x for y, and z/y for x. Physical vectors
    describe source voxel centers, not anatomical or world-axis slices.
    """
    volume = prepared['volume']
    dimensions = dict(zip(('z', 'y', 'x'), volume['shape']))
    if axis not in dimensions or type(index) is not int or not 0 <= index < dimensions[axis]:
        invalid('slice axis/index is outside the source volume.')
    row_axis, column_axis = {'z': ('y', 'x'), 'y': ('z', 'x'), 'x': ('z', 'y')}[axis]
    affine = prepared['metadata']['manifest']['affine']
    values = []
    coordinates = dict(x=0, y=0, z=0)
    coordinates[axis] = index
    for row in range(dimensions[row_axis]):
        line = []
        coordinates[row_axis] = row
        for column in range(dimensions[column_axis]):
            coordinates[column_axis] = column
            offset = (coordinates['z'] * dimensions['y'] + coordinates['y']) * dimensions['x'] + coordinates['x']
            line.append(volume['data'][offset])
        values.append(line)
    axis_column = {'x': 0, 'y': 1, 'z': 2}
    return {'axis': axis, 'index': index, 'row_axis': row_axis, 'column_axis': column_axis,
            'values': values, 'units': prepared['metadata']['manifest']['units'],
            'physical_origin': [row[3] + row[axis_column[axis]] * index for row in affine[:3]],
            'physical_row_step': [row[axis_column[row_axis]] for row in affine[:3]],
            'physical_column_step': [row[axis_column[column_axis]] for row in affine[:3]]}
