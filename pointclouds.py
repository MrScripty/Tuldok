"""Bounded vertex-only PLY adapter, with explicit float32 parser compatibility."""
import hashlib
import io
import math
import struct
import zipfile

from immutable_assets import ImmutableAssets
from workbench import WorkbenchError, encode, text_value
from ply_geometry import (PLY_LIMIT, MANIFEST_LIMIT, MAX_REQUEST, BUNDLE_LIMIT,
    INTEGER, parse_json, exact, manifest, native, decode_file, ply_header)

POINT_LIMIT = 20_000
PREVIEW_LIMIT = 512
FORMAT = 'tuldok_pointcloud_v1'
FILES = ('points.ply', 'points.json')


def invalid(message):
    raise WorkbenchError('Invalid point cloud: ' + message)


def scalar(token, dtype):
    if dtype == 'uchar':
        if not INTEGER.fullmatch(token) or int(token) > 255:
            invalid('RGB scalar must be an integer from 0 through 255.')
        return int(token)
    value = native(token, dtype)
    # The common mesh decoder canonicalizes zero. Point attributes retain its sign.
    if value == 0:
        value = math.copysign(0.0, float(token))
    if dtype == 'float' and struct.pack('<f', value) != struct.pack('<f', float(token)):
        invalid('float32 decimal is incompatible with the pinned parser; no rounded replacement is admitted.')
    return value


def parse_ply(raw):
    lines, end, header = ply_header(raw, POINT_LIMIT)
    if not header or len(header[0]) != 3 or header[0][:2] != ['element', 'vertex'] or not INTEGER.fullmatch(header[0][2]):
        invalid('expected one bounded vertex element.')
    count = int(header[0][2])
    if not 0 < count <= POINT_LIMIT:
        invalid('point count cap exceeded.')
    properties = []
    for item in header[1:]:
        if len(item) != 3 or item[0] != 'property':
            invalid('only scalar vertex properties are supported; no faces or other elements.')
        properties.append({'name': item[2], 'dtype': item[1]})
    names = [p['name'] for p in properties]
    xyz, normals, colors = ['x', 'y', 'z'], ['nx', 'ny', 'nz'], ['red', 'green', 'blue']
    if names not in (xyz, xyz + normals, xyz + colors, xyz + normals + colors):
        invalid('property axes must be xyz with optional complete normals and RGB, in profile order.')
    for prop in properties:
        if prop['dtype'] not in (('uchar',) if prop['name'] in colors else ('float', 'double')):
            invalid('property dtype is outside the point-cloud profile.')
    data = lines[end + 1:]
    if len(data) != count:
        invalid('truncated or trailing point data; counts mismatch.')
    points = []
    for line in data:
        tokens = line.split()
        if len(tokens) != len(properties):
            invalid('point property count mismatch.')
        points.append([scalar(token, prop['dtype']) for token, prop in zip(tokens, properties)])
    return {'properties': properties, 'points': points,
        'bounds': {'min': [min(p[i] for p in points) for i in range(3)],
                   'max': [max(p[i] for p in points) for i in range(3)]}}


def prepare(raw, sidecar_raw):
    if not 0 < len(raw) <= PLY_LIMIT:
        invalid('PLY byte cap exceeded.')
    sidecar = manifest(sidecar_raw, raw, format_name=FORMAT, filename=FILES[0], extra=('lineage',))
    lineage = sidecar['lineage']
    exact(lineage, ('namespace', 'source_id', 'family_id', 'split'), 'lineage')
    for key in ('namespace', 'source_id', 'family_id'):
        if text_value(lineage[key], 'Lineage ' + key, 120) != lineage[key]:
            invalid('lineage identifiers must be canonical without surrounding whitespace.')
    if lineage['split'] not in ('train', 'validation', 'test', 'unassigned'):
        invalid('lineage split is outside the profile.')
    geometry = parse_ply(raw)
    # Geometry-family zero canonicalization never changes raw or native attributes.
    family = hashlib.sha256(encode({'points': [[0.0 if n == 0 else n for n in p[:3]] for p in geometry['points']],
        'units': sidecar['units'], 'coordinate_system': sidecar['coordinate_system']}).encode()).hexdigest()
    link = lambda domain, key: hashlib.sha256(encode([domain, lineage['namespace'], lineage[key]]).encode()).hexdigest()
    metadata = {'manifest': sidecar, 'manifest_sha256': hashlib.sha256(sidecar_raw).hexdigest(),
        'properties': geometry['properties'], 'point_count': len(geometry['points']), 'bounds': geometry['bounds'],
        'provided_normals': any(p['name'] == 'nx' for p in geometry['properties']),
        'provided_colors': any(p['name'] == 'red' for p in geometry['properties']),
        'protected_groups': ['pointcloud-source:' + sidecar['geometry_sha256'], 'pointcloud-native:' + family,
                             'pointcloud-origin:' + link('pointcloud-source-v1', 'source_id'),
                             'pointcloud-family:' + link('pointcloud-family-v1', 'family_id')],
        'scope': 'whole point cloud; geometry transport and inspection; no inference or training qualification'}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        archive.writestr(zipfile.ZipInfo(FILES[0]), raw)
        archive.writestr(zipfile.ZipInfo(FILES[1]), sidecar_raw)
    return {'bundle': stream.getvalue(), 'metadata': metadata, 'geometry': geometry}


def admit(workbench, body):
    if type(body) is not dict or set(body) - {'files', 'name', 'groups', 'parents', 'rights'}:
        invalid('import envelope fields do not match the profile.')
    exact(body.get('files'), FILES, 'selected files')
    prepared = prepare(decode_file(body['files'][FILES[0]], PLY_LIMIT, FILES[0]),
                       decode_file(body['files'][FILES[1]], MANIFEST_LIMIT, FILES[1]))
    return workbench.pointclouds.admit(prepared, body)


class PointCloudAssets(ImmutableAssets):
    def __init__(self, workbench):
        super().__init__(workbench, kind='pointcloud', task='pointcloud_geometry', maximum=BUNDLE_LIMIT, default_name='Point cloud')

    def admit(self, prepared, body):
        value = prepared['metadata']
        return super().admit(prepared, body, {'method': 'pointcloud_import', 'format': FORMAT,
            'geometry_sha256': value['manifest']['geometry_sha256'], 'manifest_sha256': value['manifest_sha256'],
            'lineage': value['manifest']['lineage']})

    def validated(self, record, bundle):
        try:
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                if archive.namelist() != list(FILES) or any(item.compress_type != zipfile.ZIP_STORED or not 0 < item.file_size <= cap
                        for item, cap in zip(archive.infolist(), (PLY_LIMIT, MANIFEST_LIMIT))):
                    invalid('stored point-cloud bundle profile changed.')
                prepared = prepare(archive.read(FILES[0]), archive.read(FILES[1]))
            if prepared['metadata'] != {key: value for key, value in record['pointcloud'].items() if key != 'bundle_bytes'}:
                invalid('stored metadata differs from immutable source.')
            return prepared['geometry']
        except (WorkbenchError, zipfile.BadZipFile, KeyError, RuntimeError, UnicodeError) as error:
            raise WorkbenchError('Point-cloud source or metadata changed outside Tuldok.', 'conflict', 409) from error

    def asset(self, record):
        bundle, mime = super().asset(record)
        self.validated(record, bundle)
        return bundle, mime

    def inspect(self, record_id):
        with self.workbench.lock:
            record = self.workbench._get(record_id)
            if record['kind'] != 'pointcloud':
                raise WorkbenchError('Point-cloud inspection requires a pointcloud record.')
            bundle, _ = super().asset(record)
        geometry = self.validated(record, bundle)
        return {'id': record_id, 'content_hash': record['content_hash'], 'bounds': geometry['bounds'],
            'units': record['pointcloud']['manifest']['units'], 'coordinate_system': record['pointcloud']['manifest']['coordinate_system'],
            'point_count': len(geometry['points']), 'sample_count': min(PREVIEW_LIMIT, len(geometry['points'])),
            'properties': geometry['properties'], 'points': geometry['points'][:PREVIEW_LIMIT]}
