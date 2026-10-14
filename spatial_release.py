"""Read-only frozen point-cloud/volume custody, using their native parser owners."""
from pathlib import Path

import canonical_release
from canonical_release import MAX_RELEASE_BYTES, SPLITS, archive, require, sha
from caption_import import SNAPSHOT_KEYS, snapshot
from native_text_import import RECORD_KEYS
import pointclouds
import volume_assets
from workbench import IDENTIFIER, WorkbenchError, encode, text_value, validate_annotation

LIMITATIONS = [
    'Family checks cover selected records only. Canonical v1 does not retain every omitted ancestor or bridge.',
    'Review, rights, units, spatial coordinates and source lineage are frozen declarations, not independently certified claims.',
    'Native integrity does not establish physical independence, medical interpretation, segmentation or training suitability.',
]


def validate_row(row, release, used_ids):
    kind = row['kind']
    require(type(row) is dict and set(row) == RECORD_KEYS | {kind}, 'unexpected canonical spatial record fields.')
    task = 'pointcloud_geometry' if kind == 'pointcloud' else 'volume_grid'
    require(row['task'] == task, 'spatial task differs from its record kind.')
    require(type(row['id']) is str and IDENTIFIER.fullmatch(row['id']) and row['id'] not in used_ids,
            'spatial record IDs must be unique.')
    used_ids.add(row['id'])
    snapshot({key: row[key] for key in SNAPSHOT_KEYS})
    require(row['source_available'] is True and row['source_lineage_known'] is True
            and row['review'] == 'human_reviewed', 'available, human-reviewed spatial snapshots are required.')
    require(all(row[key] is None for key in ('text', 'width', 'height', 'corner_annotation')),
            'spatial record contains another modality.')
    require(row['split'] in SPLITS, 'invalid frozen split.')
    for field, cap in (('name', 200), ('created_at', 120), ('updated_at', 120)):
        text_value(row[field], field, cap)
    require(validate_annotation(task, row['annotation'], row) == row['annotation'], 'canonical inspection annotation required.')
    require(type(row['provenance']) is dict, 'record provenance must be an object.')
    text_value(row['provenance'].get('rights'), 'Rights note', 1000)
    if kind == 'pointcloud':
        parser, names, caps = pointclouds, ('points.ply', 'points.json'), (pointclouds.PLY_LIMIT, pointclouds.MANIFEST_LIMIT)
    else:
        parser, names, caps = volume_assets, ('volume.npy', 'volume.json'), (volume_assets.NPY_LIMIT, volume_assets.MANIFEST_LIMIT)
    filename = 'assets/' + row['id'] + '.zip'
    require(row['asset'] == filename and filename in release.namelist(), 'exact whole-spatial asset path required.')
    require(0 < release.getinfo(filename).file_size <= parser.BUNDLE_LIMIT, 'spatial bundle exceeds its bound.')
    raw = release.read(filename)
    require(sha(raw) == row['asset_sha256'] == row['content_hash'] == row['source_sha256'], 'whole-spatial asset hash mismatch.')
    with archive(raw, 2, parser.BUNDLE_LIMIT) as bundle:
        require(bundle.namelist() == list(names), 'spatial bundle must retain the exact native file and sidecar.')
        require(all(0 < bundle.getinfo(name).file_size <= cap for name, cap in zip(names, caps)),
                'spatial source member exceeds its bound.')
        prepared = parser.prepare(*(bundle.read(name) for name in names))
    metadata = prepared['metadata']
    require(type(row[kind]) is dict and encode(row[kind]) == encode(dict(metadata, bundle_bytes=len(raw))),
            'spatial metadata differs from exact source.')
    require(set(metadata['protected_groups']) <= set(row['groups']), 'protected spatial family is missing.')
    manifest = metadata['manifest']
    result = {key: row[key] for key in ('id', 'name', 'revision', 'source_revision', 'split', 'review')}
    result.update(asset_sha256=sha(raw), manifest_sha256=metadata['manifest_sha256'],
                  units=manifest['units'], provenance=manifest['provenance'], rights=row['provenance']['rights'])
    if kind == 'pointcloud':
        result.update({key: metadata[key] for key in ('properties', 'point_count', 'bounds', 'provided_normals', 'provided_colors')})
        result.update(geometry_sha256=manifest['geometry_sha256'], coordinate_system=manifest['coordinate_system'],
                      lineage=manifest['lineage'])
    else:
        result.update({key: metadata[key] for key in ('shape', 'dtype', 'order', 'voxel_count', 'spacing_xyz')})
        result.update(volume_sha256=manifest['volume_sha256'], affine=manifest['affine'],
                      value_semantics=manifest['value_semantics'], array_axes=['z', 'y', 'x'],
                      coordinate_contract='Affine maps voxel-center [x,y,z,1] to physical coordinates in declared units.')
    return result


def validate_bytes(raw, expected_sha256=None, *, kind):
    """Return native evidence for one closed spatial subtype, without catalog writes."""
    if kind not in ('pointcloud', 'volume'):
        raise WorkbenchError('Unsupported spatial release kind.', 'unsupported')
    result = canonical_release.validate_bytes(raw, expected_sha256, kind=kind, validate_row=validate_row)
    summaries = result['summaries']
    report = {'schema_version': 1, 'validation': kind + '_release_integrity',
              'release_sha256': result['release_sha256'], 'split_counts': result['split_counts'],
              'family_scope': 'selected_records_only', 'limitations': list(LIMITATIONS),
              kind + '_count': len(summaries), kind + 's': summaries}
    if kind == 'pointcloud':
        report['point_count'] = sum(row['point_count'] for row in summaries)
    else:
        report['voxel_count'] = sum(row['voxel_count'] for row in summaries)
    return report


def validate_release(path, expected_sha256=None, *, kind):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_RELEASE_BYTES + 1)
    except OSError as error:
        raise WorkbenchError('Spatial release file is unavailable.', 'unavailable', 404) from error
    return validate_bytes(raw, expected_sha256, kind=kind)
