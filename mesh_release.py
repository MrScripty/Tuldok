"""Read-only integrity validation of bounded canonical releases of static meshes.

The existing mesh parser owns native numeric semantics. This reader validates
the frozen archive boundary; it neither acquires data nor grants human review.
"""
import argparse
import json
from pathlib import Path
import sys

import meshes
from caption_import import SNAPSHOT_KEYS, snapshot
from native_text_import import RECORD_KEYS
from workbench import IDENTIFIER, WorkbenchError, encode, text_value, validate_annotation

from canonical_release import (MAX_RELEASE_BYTES, MAX_METADATA_BYTES, MAX_ROW_BYTES,
                               MAX_BUNDLE_BYTES, MAX_RECORDS, SPLITS, archive, decode,
                               require, sha)
import canonical_release

MAX_MESHES = MAX_RECORDS
LIMITATIONS = [
    'Family checks cover selected records only. Canonical v1 does not retain every omitted ancestor or bridge.',
    'Review, rights, units, coordinate frame and source provenance are frozen declarations, not independently certified claims.',
    'Native geometry integrity does not prove watertightness, normal correctness, physics, training suitability or generic third-party ASCII reader compatibility.',
]


def validate_row(row, release, used_ids):
    require(type(row) is dict and set(row) == RECORD_KEYS | {'mesh'}, 'unexpected canonical mesh record fields.')
    require(row['kind'] == 'mesh' and row['task'] == 'mesh_geometry', 'only mesh-only canonical v1 releases are supported.', 'unsupported')
    require(type(row['id']) is str and IDENTIFIER.fullmatch(row['id']) and row['id'] not in used_ids, 'mesh record IDs must be unique.')
    used_ids.add(row['id'])
    snapshot({key: row[key] for key in SNAPSHOT_KEYS})
    require(row['source_available'] is True and row['source_lineage_known'] is True
            and row['review'] == 'human_reviewed', 'available, human-reviewed mesh snapshots are required.')
    require(all(row[key] is None for key in ('text', 'width', 'height', 'corner_annotation')), 'mesh record contains another modality.')
    require(row['split'] in SPLITS, 'invalid frozen split.')
    for field, cap in (('name', 200), ('created_at', 120), ('updated_at', 120)):
        text_value(row[field], field, cap)
    require(validate_annotation('mesh_geometry', row['annotation'], row) == row['annotation'],
            'canonical human inspection annotation required.')
    require(type(row['provenance']) is dict, 'record provenance must be an object.')
    text_value(row['provenance'].get('rights'), 'Rights note', 1000)
    filename = 'assets/' + row['id'] + '.zip'
    require(row['asset'] == filename and filename in release.namelist(), 'exact whole-mesh asset path required.')
    require(0 < release.getinfo(filename).file_size <= meshes.BUNDLE_LIMIT, 'mesh bundle exceeds its bound.')
    raw = release.read(filename)
    require(sha(raw) == row['asset_sha256'] == row['content_hash'] == row['source_sha256'], 'whole-mesh asset hash mismatch.')
    with archive(raw, 2, meshes.BUNDLE_LIMIT) as bundle:
        require(bundle.namelist() == ['mesh.ply', 'mesh.json'], 'mesh bundle must retain exactly mesh.ply and mesh.json.')
        require(bundle.getinfo('mesh.ply').file_size <= meshes.PLY_LIMIT
                and bundle.getinfo('mesh.json').file_size <= meshes.MANIFEST_LIMIT, 'mesh source member exceeds its bound.')
        prepared = meshes.prepare(bundle.read('mesh.ply'), bundle.read('mesh.json'))
    metadata = prepared['metadata']
    require(type(row['mesh']) is dict and encode(row['mesh']) == encode(dict(metadata, bundle_bytes=len(raw))), 'mesh metadata differs from exact source.')
    require(set(metadata['protected_groups']) <= set(row['groups']), 'protected original-source or geometry family is missing.')
    manifest = metadata['manifest']
    return {
        'id': row['id'], 'name': row['name'], 'revision': row['revision'], 'source_revision': row['source_revision'],
        'split': row['split'], 'asset_sha256': sha(raw), 'geometry_sha256': manifest['geometry_sha256'],
        'manifest_sha256': metadata['manifest_sha256'], 'vertex_count': metadata['vertex_count'],
        'triangle_count': metadata['triangle_count'], 'properties': metadata['properties'], 'bounds': metadata['bounds'],
        'units': manifest['units'], 'coordinate_system': manifest['coordinate_system'], 'provenance': manifest['provenance'],
        'review': row['review'], 'rights': row['provenance']['rights'],
    }


def validate_bytes(raw, expected_sha256=None):
    """Validate captured immutable bytes; returned summaries contain no geometry arrays."""
    result = canonical_release.validate_bytes(raw, expected_sha256, kind='mesh', validate_row=validate_row)
    summaries = result['summaries']
    return {'schema_version': 1, 'validation': 'mesh_release_integrity',
            'release_sha256': result['release_sha256'], 'mesh_count': len(summaries),
            'triangle_count': sum(row['triangle_count'] for row in summaries),
            'vertex_count': sum(row['vertex_count'] for row in summaries),
            'split_counts': result['split_counts'], 'family_scope': 'selected_records_only',
            'limitations': list(LIMITATIONS), 'meshes': summaries}


def validate_release(path, expected_sha256=None):
    """Read at most the supported bound without extraction, catalog writes or mutation."""
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_RELEASE_BYTES + 1)
    except OSError as error:
        raise WorkbenchError('Mesh release validation: release file is unavailable.', 'unavailable', 404) from error
    return validate_bytes(raw, expected_sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    args = parser.parse_args()
    try:
        print(encode(validate_release(args.release)))
    except WorkbenchError as error:
        print(json.dumps({'error': str(error), 'code': error.code}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
