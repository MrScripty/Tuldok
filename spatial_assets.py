"""Storage/HTTP composition for two bounded spatial types; parsers own meaning."""
from access import authorized
import base64
import io
import json
import re
import zipfile

from immutable_assets import ImmutableAssets
import pointclouds
import volume_assets
from workbench import WorkbenchError

MAX_REQUEST = 3 * 1024 * 1024


def parse_request(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise WorkbenchError('Duplicate spatial request field.')
            result[key] = value
        return result
    def constant(value):
        raise WorkbenchError('Spatial request values must be finite.')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise WorkbenchError('Spatial request must be finite UTF-8 JSON without duplicate fields.') from None


def profile(kind):
    if kind == 'pointcloud':
        return pointclouds, ('points.ply', 'points.json'), (pointclouds.PLY_LIMIT, pointclouds.MANIFEST_LIMIT)
    if kind == 'volume':
        return volume_assets, ('volume.npy', 'volume.json'), (volume_assets.NPY_LIMIT, volume_assets.MANIFEST_LIMIT)
    raise WorkbenchError('Unsupported spatial kind.', 'unsupported')


def admit(workbench, kind, body):
    workbench.access.require('edit', 'spatial_assets.admit')
    parser, names, caps = profile(kind)
    if (type(body) is not dict or set(body) - {'files', 'name', 'rights', 'groups', 'parents'}
            or type(body.get('files')) is not dict or set(body['files']) != set(names)):
        raise WorkbenchError('Select exactly the native spatial file and its matching sidecar.')
    raw = []
    for name, cap in zip(names, caps):
        value = body['files'][name]
        try:
            if type(value) is not str or len(value) > ((cap + 2) // 3) * 4:
                raise ValueError()
            decoded = base64.b64decode(value, validate=True)
            if not 0 < len(decoded) <= cap:
                raise ValueError()
            raw.append(decoded)
        except ValueError:
            raise WorkbenchError(name + ' must be a bounded complete base64 file.') from None
    return workbench.immutable_owners[kind].admit(parser.prepare(*raw), body)


class SpatialAssets(ImmutableAssets):
    def __init__(self, workbench, kind):
        parser, _, _ = profile(kind)
        super().__init__(workbench, kind=kind, task='pointcloud_geometry' if kind == 'pointcloud' else 'volume_grid',
                         maximum=parser.BUNDLE_LIMIT, default_name='Point cloud' if kind == 'pointcloud' else 'Volume grid')

    @authorized('edit', 'spatial_assets.admit')
    def admit(self, prepared, body):
        return super().admit(prepared, body, {'method': self.kind + '_import',
            'format': prepared['metadata']['manifest']['format'],
            'manifest_sha256': prepared['metadata']['manifest_sha256']})

    def validated(self, record, bundle):
        parser, names, caps = profile(self.kind)
        try:
            with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                entries = archive.infolist()
                if archive.namelist() != list(names) or any(entry.compress_type != zipfile.ZIP_STORED or
                        not 0 < entry.file_size <= cap for entry, cap in zip(entries, caps)):
                    raise ValueError('Stored bundle profile changed.')
                prepared = parser.prepare(*(archive.read(name) for name in names))
            expected = {key: value for key, value in record[self.kind].items() if key != 'bundle_bytes'}
            if prepared['metadata'] != expected:
                raise ValueError('Stored native metadata changed.')
            return prepared
        except (ValueError, zipfile.BadZipFile, KeyError, RuntimeError, UnicodeError):
            raise WorkbenchError('Spatial source or metadata changed outside Tuldok.', 'conflict', 409) from None

    def validate_project_source(self, bundle, metadata):
        self.validated({self.kind: metadata}, bundle)

    @staticmethod
    def validate_project_metadata(kind,value):
        import math
        from immutable_assets import validate_project_metadata_fields,validate_project_bounds
        parser,_,_=profile(kind)
        fields={'manifest','manifest_sha256','protected_groups','scope'}
        fields|= {'properties','point_count','bounds','provided_normals','provided_colors'} if kind=='pointcloud' else {'source_sha256','shape','dtype','order','voxel_count','spacing_xyz'}
        validate_project_metadata_fields(value,fields,parser.BUNDLE_LIMIT)
        parser.manifest_declaration(value['manifest'])
        if type(value['manifest_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}',value['manifest_sha256']):raise WorkbenchError('Invalid retained spatial manifest digest.')
        if kind=='pointcloud':
            validate_project_bounds(value['bounds'])
            if type(value['point_count']) is not int or not 1<=value['point_count']<=parser.POINT_LIMIT:raise WorkbenchError('Invalid retained point count.')
            properties=value['properties']
            if type(properties) is not list or any(type(p) is not dict or set(p)!={'name','dtype'} for p in properties):raise WorkbenchError('Invalid retained point properties.')
            names=[p['name'] for p in properties];xyz=['x','y','z'];normals=['nx','ny','nz'];colors=['red','green','blue']
            if names not in (xyz,xyz+normals,xyz+colors,xyz+normals+colors):raise WorkbenchError('Invalid retained point property order.')
            if any(p['dtype'] not in (('uchar',) if p['name'] in colors else ('float','double')) for p in properties):raise WorkbenchError('Invalid retained point property dtype.')
            if type(value['provided_normals']) is not bool or type(value['provided_colors']) is not bool or value['provided_normals']!=('nx' in names) or value['provided_colors']!=('red' in names):raise WorkbenchError('Retained point flags differ.')
        else:
            manifest=value['manifest']
            if value['shape']!=manifest['shape'] or value['source_sha256']!=manifest['volume_sha256'] or value['dtype']!='uint8' or value['order']!='C' or type(value['voxel_count']) is not int or value['voxel_count']!=math.prod(manifest['shape']) or value['spacing_xyz']!=parser._affine(manifest['affine'],manifest['shape']):raise WorkbenchError('Retained volume metadata differs.')

    @authorized('inspect', 'spatial_assets.asset', target=lambda record: record.get('id') if isinstance(record, dict) else None)
    def asset(self, record):
        bundle, mime = super().asset(record)
        self.validated(record, bundle)
        return bundle, mime

    @authorized('inspect', 'spatial_assets.inspect')
    def inspect(self, record_id, *, axis='z', index=0):
        with self.workbench.lock:
            record = self.workbench._get(record_id)
            if record['kind'] != self.kind:
                raise WorkbenchError('Inspection requires the matching spatial kind.')
            bundle, _ = super().asset(record)
        prepared = self.validated(record, bundle)
        if self.kind == 'volume':
            preview = volume_assets.project_slice(prepared, axis, index)
        else:
            geometry = prepared['geometry']
            preview = {'bounds': geometry['bounds'], 'properties': geometry['properties'],
                       'point_count': len(geometry['points']), 'sample_count': min(pointclouds.PREVIEW_LIMIT, len(geometry['points'])),
                       'points': geometry['points'][:pointclouds.PREVIEW_LIMIT],
                       'units': prepared['metadata']['manifest']['units'],
                       'coordinate_system': prepared['metadata']['manifest']['coordinate_system']}
        return dict(preview, id=record_id, content_hash=record['content_hash'])
