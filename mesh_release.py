"""Read-only integrity validation of bounded canonical releases of static meshes.

The existing mesh parser owns native numeric semantics. This reader validates
the frozen archive boundary; it neither acquires data nor grants human review.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import meshes
from caption_import import SNAPSHOT_KEYS, snapshot
from dataset_releases import connected_components
from native_text_import import MANIFEST_KEYS, RECORD_KEYS
from workbench import IDENTIFIER, WorkbenchError, encode, text_value, validate_annotation

MAX_RELEASE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_ROW_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 40 * 1024 * 1024
MAX_MESHES = 64
SPLITS = ('train', 'validation', 'test')
LIMITATIONS = [
    'Family checks cover selected records only. Canonical v1 does not retain every omitted ancestor or bridge.',
    'Review, rights, units, coordinate frame and source provenance are frozen declarations, not independently certified claims.',
    'Native geometry integrity does not prove watertightness, normal correctness, physics, training suitability or generic third-party ASCII reader compatibility.',
]


def require(condition, message, code='invalid'):
    if not condition:
        raise WorkbenchError('Mesh release validation: ' + message, code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    require(len(raw) <= MAX_METADATA_BYTES, 'metadata exceeds 8 MiB.')
    value = meshes.parse_json(raw)
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        require(depth <= 64, 'JSON nesting exceeds 64 levels.')
        if isinstance(item, str):
            try:
                item.encode('utf-8')
            except UnicodeError:
                require(False, 'JSON strings must contain valid Unicode.')
        elif isinstance(item, dict):
            stack.extend((child, depth + 1) for pair in item.items() for child in pair)
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return value


def archive(raw, maximum_entries, maximum_bytes):
    require(0 < len(raw) <= maximum_bytes, 'archive exceeds its byte bound.')
    value = zipfile.ZipFile(io.BytesIO(raw))
    try:
        entries = value.infolist()
        names = value.namelist()
        require(len(entries) <= maximum_entries and len(names) == len(set(names)), 'archive has too many or duplicate entries.')
        require(entries and entries[0].header_offset == 0 and not value.comment and raw[:4] == b'PK\x03\x04'
                and raw[-22:-18] == b'PK\x05\x06', 'archive must have no preamble, comment or trailing bytes.')
        require(all(entry.compress_type == zipfile.ZIP_STORED and not entry.flag_bits & 1
                    and entry.file_size == entry.compress_size for entry in entries),
                'only unencrypted stored ZIP entries are supported.')
        require(sum(entry.file_size for entry in entries) <= maximum_bytes, 'logical archive exceeds its byte bound.')
        return value
    except Exception:
        value.close()
        raise


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
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RELEASE_BYTES, 'select a release of at most 64 MiB.')
    digest = sha(raw)
    if expected_sha256 is not None:
        require(type(expected_sha256) is str and meshes.HASH.fullmatch(expected_sha256)
                and digest == expected_sha256, 'release SHA256 differs from the selected frozen release.')
    try:
        with archive(raw, MAX_MESHES + 8, MAX_RELEASE_BYTES) as release:
            require('manifest.json' in release.namelist(), 'canonical manifest is missing.')
            require(release.getinfo('manifest.json').file_size <= MAX_METADATA_BYTES, 'manifest exceeds 8 MiB.')
            manifest = decode(release.read('manifest.json'))
            require(type(manifest) is dict, 'manifest must be an object.')
            require('format' not in manifest and manifest.get('schema_version') == 1,
                    'only mesh-only canonical v1 releases are supported.', 'unsupported')
            require(set(manifest) == MANIFEST_KEYS and type(manifest['schema_version']) is int, 'unexpected canonical manifest fields.')
            require(type(manifest['seed']) is int and 0 <= manifest['seed'] <= 2**32 - 1, 'invalid split seed.')
            rows = manifest['records']
            require(type(rows) is list and 1 <= len(rows) <= MAX_MESHES, 'select 1 to 64 whole meshes.')
            require(all(type(row) is dict and row.get('kind') == 'mesh' for row in rows),
                    'only mesh-only canonical v1 releases are supported; preserve the existing mixed release download.', 'unsupported')
            require(manifest['vocabulary'] == [] and type(manifest['coordinate_contract']) is str
                    and type(manifest['limitations']) is list and all(type(v) is str for v in manifest['limitations']), 'invalid canonical metadata.')
            required = {'manifest.json', 'README.txt'} | {f'{split}/{name}' for split in SPLITS for name in ('records.jsonl', 'coco.json')}
            assets = {row.get('asset') for row in rows if type(row.get('asset')) is str}
            require(set(release.namelist()) == required | assets, 'missing, extra or unsupported archive paths.')
            require(all(release.getinfo(name).file_size <= MAX_METADATA_BYTES for name in required), 'metadata member exceeds 8 MiB.')
            release.read('README.txt')  # Observe CRC for the one otherwise opaque member too.
            require(sum(release.getinfo(name).file_size for name in assets) <= MAX_BUNDLE_BYTES, 'selected raw mesh bundles exceed 40 MiB.')
            used_ids = set()
            summaries = [validate_row(row, release, used_ids) for row in rows]
            counts = {split: sum(row['split'] == split for row in rows) for split in SPLITS}
            report = manifest['split_report']
            require(type(report) is dict and type(report.get('actual_counts')) is dict
                    and set(report['actual_counts']) <= set(SPLITS)
                    and all(type(n) is int and n >= 0 for n in report['actual_counts'].values())
                    and {split: report['actual_counts'].get(split, 0) for split in SPLITS} == counts, 'split report counts disagree with records.')
            for split in SPLITS:
                raw_rows = release.read(split + '/records.jsonl')
                require(not raw_rows or raw_rows.endswith(b'\n'), 'split JSONL must end with a newline.')
                lines = raw_rows.splitlines()
                require(all(0 < len(line) <= MAX_ROW_BYTES for line in lines), 'split JSONL row exceeds 256 KiB or is empty.')
                require([encode(decode(line)) for line in lines] == [encode(row) for row in rows if row['split'] == split], 'split JSONL differs from frozen manifest records.')
                coco = decode(release.read(split + '/coco.json'))
                require(type(coco) is dict and set(coco) == {'info', 'licenses', 'images', 'annotations', 'categories'}
                        and all(coco[key] == [] for key in ('licenses', 'images', 'annotations', 'categories')),
                        'mesh-only release cannot contain COCO samples.')
            # Only selected rows are available. Do not reconstruct or certify absent bridges.
            roots = connected_components(rows)
            assignments = {}
            for row in rows:
                component = roots[row['id']]
                require(component not in assignments or assignments[component] == row['split'], 'connected selected meshes cross frozen splits.')
                assignments[component] = row['split']
            return {'schema_version': 1, 'validation': 'mesh_release_integrity', 'release_sha256': digest,
                    'mesh_count': len(summaries), 'triangle_count': sum(row['triangle_count'] for row in summaries),
                    'vertex_count': sum(row['vertex_count'] for row in summaries), 'split_counts': counts,
                    'family_scope': 'selected_records_only', 'limitations': list(LIMITATIONS), 'meshes': summaries}
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, OverflowError, RuntimeError, UnicodeError) as error:
        if isinstance(error, WorkbenchError):
            raise
        raise WorkbenchError('Mesh release validation: malformed or inconsistent frozen archive.') from error


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
