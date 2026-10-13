"""Frozen canonical archive custody shared by whole-asset readers.

Subtype readers retain native semantics and row policy. This owner checks the
one existing canonical v1 envelope, projection and selected-family contract.
"""
import hashlib
import io
import zipfile

import meshes
from dataset_releases import connected_components
from native_text_import import MANIFEST_KEYS
from workbench import WorkbenchError, encode

MAX_RELEASE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_ROW_BYTES = 256 * 1024
MAX_BUNDLE_BYTES = 40 * 1024 * 1024
MAX_RECORDS = 64
SPLITS = ('train', 'validation', 'test')


def require(condition, message, code='invalid'):
    if not condition:
        raise WorkbenchError('Canonical release validation: ' + message, code)


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


def validate_bytes(raw, expected_sha256, *, kind, validate_row):
    """Return custody and subtype summaries for one supported whole-asset kind."""
    if kind not in ('mesh', 'sequence', 'pointcloud', 'volume'):
        raise ValueError('Unsupported canonical release reader.')
    require(type(raw) is bytes and 0 < len(raw) <= MAX_RELEASE_BYTES, 'select a release of at most 64 MiB.')
    digest = sha(raw)
    if expected_sha256 is not None:
        require(type(expected_sha256) is str and meshes.HASH.fullmatch(expected_sha256)
                and digest == expected_sha256, 'release SHA256 differs from the selected frozen release.')
    try:
        with archive(raw, MAX_RECORDS + 8, MAX_RELEASE_BYTES) as release:
            require('manifest.json' in release.namelist(), 'canonical manifest is missing.')
            require(release.getinfo('manifest.json').file_size <= MAX_METADATA_BYTES, 'manifest exceeds 8 MiB.')
            manifest = decode(release.read('manifest.json'))
            require(type(manifest) is dict, 'manifest must be an object.')
            require('format' not in manifest and manifest.get('schema_version') == 1,
                    f'only {kind}-only canonical v1 releases are supported.', 'unsupported')
            require(set(manifest) == MANIFEST_KEYS and type(manifest['schema_version']) is int, 'unexpected canonical manifest fields.')
            require(type(manifest['seed']) is int and 0 <= manifest['seed'] <= 2**32 - 1, 'invalid split seed.')
            rows = manifest['records']
            require(type(rows) is list and 1 <= len(rows) <= MAX_RECORDS, 'select 1 to 64 whole assets.')
            require(all(type(row) is dict and row.get('kind') == kind for row in rows),
                    f'only {kind}-only canonical v1 releases are supported; preserve the existing mixed release download.', 'unsupported')
            require(manifest['vocabulary'] == [] and type(manifest['coordinate_contract']) is str
                    and type(manifest['limitations']) is list and all(type(v) is str for v in manifest['limitations']), 'invalid canonical metadata.')
            required = {'manifest.json', 'README.txt'} | {f'{split}/{name}' for split in SPLITS for name in ('records.jsonl', 'coco.json')}
            assets = {row.get('asset') for row in rows if type(row.get('asset')) is str}
            require(set(release.namelist()) == required | assets, 'missing, extra or unsupported archive paths.')
            require(all(release.getinfo(name).file_size <= MAX_METADATA_BYTES for name in required), 'metadata member exceeds 8 MiB.')
            release.read('README.txt')  # Observe CRC for the one otherwise opaque member too.
            require(sum(release.getinfo(name).file_size for name in assets) <= MAX_BUNDLE_BYTES, 'selected raw asset bundles exceed 40 MiB.')
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
                        f'{kind}-only release cannot contain COCO samples.')
            # Only selected rows are available. Do not reconstruct or certify absent bridges.
            roots = connected_components(rows)
            assignments = {}
            for row in rows:
                component = roots[row['id']]
                require(component not in assignments or assignments[component] == row['split'], 'connected selected assets cross frozen splits.')
                assignments[component] = row['split']
            return {'release_sha256': digest, 'split_counts': counts, 'summaries': summaries}
    except (zipfile.BadZipFile, KeyError, TypeError, ValueError, OverflowError, RuntimeError, UnicodeError) as error:
        if isinstance(error, WorkbenchError):
            raise
        raise WorkbenchError('Canonical release validation: malformed or inconsistent frozen archive.') from error
