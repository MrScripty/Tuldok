"""Tuldok-owned strict ASCII triangle PLY profile; raw bytes remain authoritative."""
import base64
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
import re
import struct
import zipfile

from immutable_assets import ImmutableAssets
from workbench import WorkbenchError, encode, text_value

PLY_LIMIT = 2 * 1024 * 1024
MANIFEST_LIMIT = 32 * 1024
HEADER_LIMIT = 16 * 1024
LINE_LIMIT = 1024
VERTEX_LIMIT = 20_000
FACE_LIMIT = 40_000
PREVIEW_LIMIT = 512
MAX_REQUEST = 3 * 1024 * 1024
BUNDLE_LIMIT = PLY_LIMIT + MANIFEST_LIMIT + 1024
NUMBER = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
INTEGER = re.compile(r'^(?:0|[1-9][0-9]*)$')
HASH = re.compile(r'^[a-f0-9]{64}$')


def invalid(message):
    raise WorkbenchError('Invalid static mesh: ' + message)


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
    except (UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, WorkbenchError):
            raise
        invalid('malformed UTF-8 JSON.')


def exact(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        invalid(name + ' fields do not match the profile.')


def manifest(raw, geometry):
    if not 0 < len(raw) <= MANIFEST_LIMIT:
        invalid('sidecar byte cap exceeded.')
    value = parse_json(raw)
    exact(value, ('format', 'geometry_file', 'geometry_bytes', 'geometry_sha256', 'units', 'coordinate_system', 'provenance'), 'sidecar')
    if type(value['format']) is not str:
        invalid('format must be a string.')
    if value['format'] != 'tuldok_mesh_v1':
        raise WorkbenchError('Unsupported static mesh sidecar version.', 'unsupported')
    if value['geometry_file'] != 'mesh.ply' or type(value['geometry_bytes']) is not int or value['geometry_bytes'] != len(geometry):
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
            rounded = struct.unpack('<f', struct.pack('<f', value))[0]
            if value != 0 and rounded == 0:
                invalid('float vertex scalar has nonzero underflow.')
            value = rounded
        return 0.0 if value == 0 else value
    except (OverflowError, InvalidOperation):
        invalid('vertex scalar is not natively representable.')


def parse_ply(raw):
    if not 0 < len(raw) <= PLY_LIMIT:
        invalid('PLY byte cap exceeded.')
    if raw.count(b'\n') > VERTEX_LIMIT + FACE_LIMIT + HEADER_LIMIT:
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
    def element(position, name, maximum):
        if position >= len(header) or len(header[position]) != 3 or header[position][:2] != ['element', name] or not INTEGER.fullmatch(header[position][2]):
            invalid('expected bounded ' + name + ' element.')
        count = int(header[position][2])
        if not 0 < count <= maximum:
            invalid(name + ' count cap exceeded.')
        return count
    vertices_count = element(0, 'vertex', VERTEX_LIMIT)
    properties = []
    cursor = 1
    while cursor < len(header) and header[cursor][0:1] == ['property']:
        item = header[cursor]
        if len(item) != 3 or item[1] not in ('float', 'double'):
            invalid('unsupported vertex property dtype.')
        properties.append({'name': item[2], 'dtype': item[1]})
        cursor += 1
    names = [item['name'] for item in properties]
    if names not in (['x', 'y', 'z'], ['x', 'y', 'z', 'nx', 'ny', 'nz']):
        invalid('vertex property axes must be xyz with optional complete nx ny nz.')
    faces_count = element(cursor, 'face', FACE_LIMIT)
    if header[cursor + 1:] != [['property', 'list', 'uchar', 'int', 'vertex_indices']]:
        invalid('face property must be list uchar int vertex_indices.')
    data = lines[end + 1:]
    if len(data) != vertices_count + faces_count:
        invalid('truncated or trailing PLY data; counts mismatch.')
    vertices = []
    for line in data[:vertices_count]:
        tokens = line.split()
        if len(tokens) != len(properties):
            invalid('vertex property count mismatch.')
        vertices.append([native(token, item['dtype']) for token, item in zip(tokens, properties)])
    faces, unique = [], set()
    for line in data[vertices_count:]:
        tokens = line.split()
        if len(tokens) != 4 or tokens[0] != '3' or any(not INTEGER.fullmatch(token) for token in tokens[1:]):
            invalid('face must contain exactly three integer indices.')
        indices = [int(token) for token in tokens[1:]]
        if len(set(indices)) != 3 or any(index >= vertices_count for index in indices):
            invalid('face indices must be distinct and within vertex count.')
        key = tuple(sorted(indices))
        if key in unique:
            invalid('duplicate unordered face.')
        unique.add(key)
        a, b, c = (vertices[index][:3] for index in indices)
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        if not any(value != 0 for value in cross):
            invalid('triangle has zero representable cross product.')
        faces.append(indices)
    bounds = {'min': [min(vertex[i] for vertex in vertices) for i in range(3)],
              'max': [max(vertex[i] for vertex in vertices) for i in range(3)]}
    return {'properties': properties, 'vertices': vertices, 'faces': faces, 'bounds': bounds}


def prepare(geometry_raw, manifest_raw):
    if not 0 < len(geometry_raw) <= PLY_LIMIT:
        invalid('PLY byte cap exceeded.')
    sidecar = manifest(manifest_raw, geometry_raw)  # Integrity before geometry interpretation.
    geometry = parse_ply(geometry_raw)
    family = hashlib.sha256(encode({'vertices': [vertex[:3] for vertex in geometry['vertices']],
        'faces': geometry['faces'], 'units': sidecar['units'], 'coordinate_system': sidecar['coordinate_system']}).encode()).hexdigest()
    metadata = {'manifest': sidecar, 'manifest_sha256': hashlib.sha256(manifest_raw).hexdigest(),
        'properties': geometry['properties'], 'vertex_count': len(geometry['vertices']), 'triangle_count': len(geometry['faces']),
        'bounds': geometry['bounds'], 'provided_normals': len(geometry['properties']) == 6,
        'protected_groups': ['mesh-source:' + sidecar['geometry_sha256'], 'mesh-family:' + family],
        'scope': 'whole static mesh; geometry transport and inspection; no simulation or training qualification'}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo('mesh.ply'), geometry_raw)
        archive.writestr(zipfile.ZipInfo('mesh.json'), manifest_raw)
    return {'bundle': stream.getvalue(), 'metadata': metadata, 'geometry': geometry}


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


def admit(workbench, body):
    if type(body) is not dict or set(body) - {'files', 'name', 'groups', 'parents', 'rights'}:
        invalid('import envelope fields do not match the profile.')
    exact(body.get('files'), ('mesh.ply', 'mesh.json'), 'selected files')
    prepared = prepare(decode_file(body['files']['mesh.ply'], PLY_LIMIT, 'mesh.ply'),
                       decode_file(body['files']['mesh.json'], MANIFEST_LIMIT, 'mesh.json'))
    return workbench.meshes.admit(prepared, body)


class MeshAssets(ImmutableAssets):
    def __init__(self, workbench):
        super().__init__(workbench, kind='mesh', task='mesh_geometry', maximum=BUNDLE_LIMIT, default_name='Static triangle mesh')

    def admit(self, prepared, body):
        value = prepared['metadata']
        return super().admit(prepared, body, {'method': 'mesh_import', 'format': 'tuldok_mesh_v1',
            'geometry_sha256': value['manifest']['geometry_sha256'], 'manifest_sha256': value['manifest_sha256']})

    def validated(self, record, bundle):
        try:
            # Never extract. Check stored member sizes before allocation/decode.
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                items = archive.infolist()
                if archive.namelist() != ['mesh.ply', 'mesh.json'] or any(item.compress_type != zipfile.ZIP_STORED or not 0 < item.file_size <= cap
                        for item, cap in zip(items, (PLY_LIMIT, MANIFEST_LIMIT))):
                    invalid('stored mesh bundle profile changed.')
                geometry_raw, manifest_raw = archive.read('mesh.ply'), archive.read('mesh.json')
            prepared = prepare(geometry_raw, manifest_raw)
            if prepared['metadata'] != {key: value for key, value in record['mesh'].items() if key != 'bundle_bytes'}:
                invalid('stored metadata differs from immutable source.')
            return prepared['geometry']
        except (WorkbenchError, zipfile.BadZipFile, KeyError, RuntimeError, UnicodeError) as error:
            raise WorkbenchError('Mesh source or metadata changed outside Tuldok.', 'conflict', 409) from error

    def asset(self, record):
        bundle, mime = super().asset(record)
        self.validated(record, bundle)
        return bundle, mime

    def inspect(self, record_id):
        with self.workbench.lock:
            record = self.workbench._get(record_id)
            if record['kind'] != 'mesh':
                raise WorkbenchError('Mesh inspection requires a mesh record.')
            bundle, _ = super().asset(record)
        geometry = self.validated(record, bundle)
        return {'id': record_id, 'content_hash': record['content_hash'], 'bounds': geometry['bounds'],
            'units': record['mesh']['manifest']['units'], 'coordinate_system': record['mesh']['manifest']['coordinate_system'],
            'triangle_count': len(geometry['faces']), 'sample_count': min(PREVIEW_LIMIT, len(geometry['faces'])),
            'triangles': [[geometry['vertices'][index][:3] for index in face] for face in geometry['faces'][:PREVIEW_LIMIT]]}
