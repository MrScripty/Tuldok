"""Bounded native MAC NumPy consumer of reviewed frozen canonical sequences.

No resampling, split creation, physical target inference or model execution.
Input SHA256 must come from the release owner; validation is not authentication.
"""
import argparse
import copy
import hashlib
import io
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
import zipfile

import numpy as np

from dataset_releases import SPLITS, connected_components
import rheon_sequence_contract as contract
import rheon_sequences
from sequence_assets import MAX_BUNDLE_BYTES, MAX_SELECTED_SEQUENCE_BYTES
from sequence_inspection import interval
from workbench import encode, strings, validate_annotation

MAX_RELEASE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_NPZ_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 64
MAX_CONTEXT = 5000
HASH = re.compile(r'^[a-f0-9]{64}$')
ID = re.compile(r'^[a-f0-9]{32}$')
ROW_KEYS = set('annotation asset asset_sha256 book_id content_hash corner_annotation created_at groups height id kind name parents pixel_hash provenance review revision sequence session_id source_available source_lineage_known source_revision source_sha256 source_split split task text updated_at width'.split())
CONTEXT_KEYS = set('id kind revision source_revision content_hash pixel_hash groups parents source_available source_lineage_known source_split source_sha256 book_id session_id'.split())
MANIFEST_KEYS = set('coordinate_contract limitations records schema_version seed split_report vocabulary'.split())
NPZ_KEYS = set(contract.FIELD_TYPES) | {'frame_indices', 'time_s', 'dt_s', 'range_frame_mask', 'metadata_utf8'}


class NativeSequenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise NativeSequenceError(message)


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, 'Invalid ' + name)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_zip(raw, maximum_entries, logical_cap):
    """Count actual central entries before ZipFile allocates any entry objects."""
    require(len(raw) >= 22 and raw[-22:-18] == b'PK\x05\x06', 'Complete ZIP without comments required')
    _, disk, cd_disk, on_disk, count, size, offset, comment = struct.unpack_from('<4s4H2IH', raw, len(raw) - 22)
    require(disk == cd_disk == comment == 0 and on_disk == count and 0 < count <= maximum_entries,
            'Bounded single-disk ZIP entry count required; ZIP64 unavailable')
    require(size <= maximum_entries * 512 and offset + size == len(raw) - 22, 'Bounded exact central directory required')
    cursor, names, total = offset, set(), 0
    for _ in range(count):
        require(cursor + 46 <= offset + size, 'Truncated central directory')
        fields = struct.unpack_from('<4s6H3I5H2I', raw, cursor)
        signature, needed, flags, method = fields[0], fields[2], fields[3], fields[4]
        compressed, length, name_len, extra_len, comment_len = fields[8:13]
        require(signature == b'PK\x01\x02' and needed < 45 and fields[13] == 0
                and fields[16] != 0xffffffff and extra_len == comment_len == 0,
                'ZIP64, extras and multi-disk entries unavailable')
        require(method == zipfile.ZIP_STORED and not flags & 1 and compressed == length,
                'Only unencrypted stored ZIP members supported')
        require(stat.S_IFMT(fields[15] >> 16) in (0, stat.S_IFREG) and not fields[15] & 0x10,
                'Only regular ZIP members supported')
        end = cursor + 46 + name_len
        require(0 < name_len <= 120 and end <= offset + size, 'Bounded ZIP name required')
        name = raw[cursor + 46:end].decode('ascii')
        require(name not in names and not name.startswith('/') and '\\' not in name
                and all(part not in ('', '.', '..') for part in name.split('/')), 'Unique safe ZIP names required')
        names.add(name); total += length
        require(total <= logical_cap, 'ZIP logical bytes exceed consumer bound')
        cursor = end
    require(cursor == offset + size, 'Central-directory count mismatch')
    archive = zipfile.ZipFile(io.BytesIO(raw))
    require(len(archive.infolist()) == count and set(archive.namelist()) == names, 'ZIP directory mismatch')
    return archive


def source_identity(member):
    """Exact kind-specific source snapshot semantics owned by Workbench._get."""
    kind, available = member['kind'], member['source_available']
    require(kind in ('sequence', 'mesh', 'pointcloud', 'image', 'text') and type(available) is bool
            and member['source_lineage_known'] is True, 'Known source kind/lineage required')
    integer(member['revision'], 1, 2**63 - 1, 'snapshot revision')
    def digest(value): return type(value) is str and bool(HASH.fullmatch(value))
    require(digest(member['content_hash']) or kind == 'image' and member['content_hash'] == '', 'Valid snapshot content hash required')
    require(member['source_split'] in (*SPLITS, 'unassigned'), 'Snapshot source split required')
    if kind == 'image':
        require(digest(member['pixel_hash']) or member['pixel_hash'] == '', 'Valid image pixel hash required')
        require((member['content_hash'] == '') == (member['pixel_hash'] == ''), 'Image content/pixel identity availability mismatch')
        for key in ('book_id', 'session_id'):
            value = member[key]
            require(type(value) is str and len(value) <= 120 and value.strip() == value, 'Canonical image lineage ID required')
        require(bool(member['session_id']), 'Image session lineage required')
        if available:
            integer(member['source_revision'], 1, 2**63 - 1, 'image source revision')
            require(digest(member['source_sha256']), 'Valid image source hash required')
        else:
            require(member['source_revision'] is None and member['source_sha256'] is None, 'Deleted image source identity required')
    else:
        integer(member['source_revision'], 1, 1, 'immutable/text source revision')
        require((kind == 'pointcloud' or member['source_split'] == 'unassigned') and member['pixel_hash'] is None
                and member['book_id'] is None and member['session_id'] is None and digest(member['source_sha256']), 'Canonical immutable/text source identity required')
        if kind == 'text':
            require(available, 'Text owner retains its original available source')
        else:
            require(member['source_sha256'] == member['content_hash'], 'Immutable source/content hash mismatch')


class NativeSequenceDataset:
    """Map-style dataset; explicit split, default whole trajectory, optional windows.

    Samples use fresh arrays with axes [time,x,y,z]. Variable human range counts
    and None constructor/control entries need an explicit downstream collator.
    """
    def __init__(self, release, *, sha256, split, window_frames=9):
        require(type(sha256) is str and HASH.fullmatch(sha256), 'Supply exact release SHA256 from its owner')
        require(type(split) is str and split in SPLITS, 'Supply explicit train/validation/test split')
        integer(window_frames, 1, 9, 'window_frames')
        self._source_path = Path(release).absolute()
        self._source_resolved = self._source_path.resolve()
        with self._source_path.open('rb') as source:
            stat = os.fstat(source.fileno())
            self._source_identity = (stat.st_dev, stat.st_ino)
            self._raw = source.read(MAX_RELEASE_BYTES + 1)
        require(0 < len(self._raw) <= MAX_RELEASE_BYTES, 'Release exceeds 64 MiB physical bound')
        require(sha(self._raw) == sha256, 'Release SHA256 mismatch')
        self._sha, self._split, self._window = sha256, split, window_frames
        try:
            self._admit()
        except NativeSequenceError:
            raise
        except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, RecursionError,
                zipfile.BadZipFile, RuntimeError, struct.error) as error:
            raise NativeSequenceError('Invalid native sequence release: ' + str(error)) from error
        self._samples = [(i, start) for i, row in enumerate(self._records) if row['split'] == split
                         for start in range(10 - window_frames)]

    def _admit(self):
        with bounded_zip(self._raw, MAX_RECORDS + 8, MAX_RELEASE_BYTES) as archive:
            require('manifest.json' in archive.namelist(), 'Canonical manifest required')
            require(archive.getinfo('manifest.json').file_size <= MAX_METADATA_BYTES, 'Manifest exceeds 8 MiB')
            manifest = contract.parse(archive.read('manifest.json'))
            require(type(manifest) is dict and set(manifest) in (MANIFEST_KEYS, MANIFEST_KEYS | {'protected_components'}),
                    'Canonical sequence manifest keys required')
            integer(manifest['schema_version'], 1, 1, 'canonical schema version')
            integer(manifest['seed'], 0, 2**32 - 1, 'split seed')
            require(type(manifest['coordinate_contract']) is str and type(manifest['limitations']) is list
                    and all(type(item) is str for item in manifest['limitations']), 'Canonical scope metadata required')
            require(manifest['vocabulary'] == [], 'No inferred class vocabulary for native fields')
            rows = manifest['records']
            require(type(rows) is list and 1 <= len(rows) <= MAX_RECORDS, 'Supply 1..64 whole sequences')
            closure = 'protected_components' in manifest
            ids, assets, bundle_bytes = set(), set(), 0
            for row in rows:
                require(type(row) is dict and set(row) == ROW_KEYS | ({'export_group'} if closure else set()), 'Canonical sequence record keys required')
                ident = row['id']
                require(type(ident) is str and ID.fullmatch(ident) and ident not in ids, 'Unique native record ID required')
                ids.add(ident)
                require(row['kind'] == 'sequence' and row['task'] == 'sequence_transport'
                        and row['review'] == 'human_reviewed' and row['source_available'] is True
                        and row['source_lineage_known'] is True, 'Available human-reviewed whole sequences required')
                integer(row['revision'], 1, 2**63 - 1, 'record revision')
                integer(row['source_revision'], 1, 2**63 - 1, 'source revision')
                source_identity(row)
                require(all(row[k] is None for k in ('text', 'width', 'height', 'corner_annotation')), 'Native record cannot declare image/text geometry')
                require(type(row['split']) is str and row['split'] in SPLITS and row['source_split'] in (*SPLITS, 'unassigned'), 'Native split required')
                require(row['source_split'] == 'unassigned' or row['source_split'] == row['split'], 'Fixed source split conflict')
                require(strings(row['groups'], 'Native groups') == row['groups']
                        and strings(row['parents'], 'Native parents') == row['parents'], 'Canonical relationships required')
                asset = 'assets/' + ident + '.zip'
                require(row['asset'] == asset and asset in archive.namelist(), 'Exact whole native asset path required')
                assets.add(asset)
                info = archive.getinfo(asset)
                require(0 < info.file_size <= MAX_BUNDLE_BYTES, 'Native bundle exceeds byte bounds')
                bundle_bytes += info.file_size
                require(bundle_bytes <= MAX_SELECTED_SEQUENCE_BYTES, 'Selected raw bundles exceed 40 MiB')
                raw = archive.read(asset)
                require(sha(raw) == row['asset_sha256'] == row['content_hash'] == row['source_sha256'], 'Native bundle hash association mismatch')
                with bounded_zip(raw, 3, MAX_BUNDLE_BYTES) as bundle:
                    names = set(bundle.namelist())
                    require(names in ({'run.json', 'frames.jsonl'}, {'run.json', 'frames.jsonl', 'controls.json'}), 'Exact native bundle members required')
                    for name in names:
                        cap = contract.FRAMES_LIMIT if name == 'frames.jsonl' else contract.MANIFEST_LIMIT
                        require(0 < bundle.getinfo(name).file_size <= cap, 'Native file exceeds byte bounds')
                    verified = rheon_sequences.prepare(bundle.read('run.json'), bundle.read('frames.jsonl'),
                        bundle.read('controls.json') if 'controls.json' in names else None)['metadata']
                require(encode(row['sequence']) == encode(dict(verified, bundle_bytes=len(raw))), 'Native metadata/index differs from verified source')
                require(set(verified['protected_groups']) <= set(row['groups']), 'Raw-derived trajectory/initial-family groups required')
                require(encode(validate_annotation('sequence_transport', row['annotation'], row)) == encode(row['annotation']), 'Canonical human targets required')
            expected_names = assets | {'manifest.json', 'README.txt'} | {s + '/' + n for s in SPLITS for n in ('records.jsonl', 'coco.json')}
            require(set(archive.namelist()) == expected_names, 'Exact canonical sequence release entries required')
            for split in SPLITS:
                filename = split + '/records.jsonl'
                require(archive.getinfo(filename).file_size <= MAX_METADATA_BYTES, 'Split JSONL exceeds 8 MiB')
                raw = archive.read(filename)
                require(not raw or raw.endswith(b'\n'), 'Truncated split JSONL')
                lines = raw.splitlines(keepends=True)
                require(len(lines) <= MAX_RECORDS and all(len(line) <= contract.LINE_LIMIT for line in lines), 'Bounded split records required')
                require(encode([contract.parse(line) for line in lines]) == encode([r for r in rows if r['split'] == split]), 'Manifest/split JSONL record association mismatch')
                require(archive.getinfo(split + '/coco.json').file_size <= 4096, 'Bounded empty COCO required')
                coco = contract.parse(archive.read(split + '/coco.json'))
                require(type(coco) is dict and all(coco.get(k) == [] for k in ('images', 'annotations', 'categories')), 'Sequence-only release required')
            self._records = rows
            self._context = self._verify_families(manifest)
            report = manifest['split_report']
            require(type(report) is dict and set(report) == {'actual_counts', 'requested_percentages', 'independent_components', 'note'}, 'Canonical split report required')
            counts = {s: sum(r['split'] == s for r in rows) for s in SPLITS if any(r['split'] == s for r in rows)}
            require(encode(counts) == encode(report['actual_counts']), 'Split counts disagree with whole records')
            ratios = report['requested_percentages']
            require(type(ratios) is dict and set(ratios) == set(SPLITS), 'Explicit split percentages required')
            for value in ratios.values(): integer(value, 0, 100, 'split percentage')
            require(sum(ratios.values()) == 100 and set(counts) == {s for s in SPLITS if ratios[s]}, 'Requested nonempty splits disagree with records')
            integer(report['independent_components'], 1, len(rows), 'component count')
            if closure:
                require(report['independent_components'] == len({r['export_group'] for r in rows}), 'Component count mismatch')
            self._limitations = list(manifest['limitations']) + [
                'Native arrays and human coverage do not qualify scientific truth, a taxonomy, a trainer or physical independence.',
                'Declared family proof does not authenticate or establish completeness of unknown upstream evidence.']
            if not closure:
                self._limitations.append('Legacy single-split release lacks declared unselected-bridge closure proof.')

    def _verify_families(self, manifest):
        rows = self._records
        if 'protected_components' not in manifest:
            require(len({r['split'] for r in rows}) == 1, 'Legacy release must have exactly one populated split')
            context = [{key: row[key] for key in CONTEXT_KEYS} for row in rows]
        else:
            components = manifest['protected_components']
            require(type(components) is dict and 1 <= len(components) <= len(rows), 'Bounded declared family components required')
            require(all(type(members) is list and members for members in components.values())
                    and sum(len(members) for members in components.values()) <= MAX_CONTEXT, 'Bounded complete family members required')
            context = [member for members in components.values() for member in members]
            seen = {}
            for group, members in components.items():
                for member in members:
                    require(type(member) is dict and set(member) == CONTEXT_KEYS, 'Exact family snapshot required')
                    ident = member['id']
                    require(type(ident) is str and ID.fullmatch(ident) and ident not in seen, 'Unique snapshot IDs required')
                    seen[ident] = member
                    source_identity(member)
                    require(strings(member['groups'], 'Snapshot groups') == member['groups'] and strings(member['parents'], 'Snapshot parents') == member['parents'], 'Canonical snapshot relationships required')
                    require(member['source_split'] in (*SPLITS, 'unassigned'), 'Snapshot source split required')
                expected = 'component:' + sha(encode(sorted(m['id'] for m in members)).encode())
                require(group == expected, 'Declared component identity mismatch')
            require(all(parent in seen for member in context for parent in member['parents']), 'Missing declared parent bridge')
            for row in rows:
                require(row['id'] in seen and encode(seen[row['id']]) == encode({k: row[k] for k in CONTEXT_KEYS}), 'Selected snapshot/revision mismatch')
                require(type(row['export_group']) is str and row['export_group'] in components
                        and row['id'] in {m['id'] for m in components[row['export_group']]}, 'Selected component association mismatch')
            roots = connected_components(context)
            require(len({roots[m['id']] for m in context}) == len(components)
                    and all(len({roots[m['id']] for m in members}) == 1 for members in components.values()), 'Declared connected closure mismatch')
            require({row['export_group'] for row in rows} == set(components), 'Unselected declared component')
        roots = connected_components(context)
        assigned = {}
        for row in rows:
            root, split = roots[row['id']], row['split']
            require(root not in assigned or assigned[root] == split, 'Whole family crosses splits')
            assigned[root] = split
        for member in context:
            fixed = member['source_split']
            require(fixed == 'unassigned' or fixed == assigned[roots[member['id']]], 'Related fixed source split conflict')
        return context

    def __len__(self):
        return len(self._samples)

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def __getitem__(self, index):
        integer(index, 0, len(self) - 1, 'sample index')
        record_index, start = self._samples[index]
        row = self._records[record_index]
        with zipfile.ZipFile(io.BytesIO(self._raw)) as release:
            with zipfile.ZipFile(io.BytesIO(release.read(row['asset']))) as bundle:
                frames = [contract.parse(line) for line in bundle.read('frames.jsonl').splitlines()]
                controls = contract.parse(bundle.read('controls.json')) if 'controls.json' in bundle.namelist() else None
        indices = list(range(start, start + self._window))
        fields = {name: np.stack([np.asarray(frames[k]['fields'][name], dtype='<f4' if kind == 'f32' else '<f8')
                   .reshape(tuple(contract.GEOMETRY['field_shapes'][name]), order='F') for k in indices])
                  for name, kind in contract.FIELD_TYPES.items()}
        ranges = row['annotation'].get('temporal_labels', {}).get('ranges', [])
        coverage = np.asarray([[r['start_frame'] <= k <= r['end_frame'] for k in indices] for r in ranges], dtype=np.bool_).reshape(len(ranges), self._window)
        metadata = {'schema': 'native_mac_sample_v1', 'release_sha256': self._sha, 'split': self._split,
            'array_axes': ['time', 'x', 'y', 'z'], 'window': {'start_frame': start, 'end_frame': indices[-1]},
            'record': copy.deepcopy(row), 'declared_family_context': copy.deepcopy(self._context),
            'frame_index': [copy.deepcopy(row['sequence']['frame_index'][k]) for k in indices],
            'accepted_intervals': [interval(frames, k) for k in indices],
            'declared_controls': {'provenance': controls['provenance'], 'units': controls['units'],
                'intervals': [controls['intervals'][k - 1] if k else None for k in indices]} if controls else None,
            'coverage_semantics': 'inclusive human-defined state coverage; uncovered states are not physical negatives',
            'limitations': copy.deepcopy(self._limitations)}
        return {'fields': fields, 'frame_indices': np.asarray(indices, dtype='<i8'),
            'time_s': np.asarray([frames[k]['time_s'] for k in indices], dtype='<f8'),
            'dt_s': np.asarray([frames[k]['dt_s'] for k in indices], dtype='<f8'),
            'range_frame_mask': coverage, 'metadata': metadata}

    def write_npz(self, path, index=0):
        """Atomic derived sample, closed numeric keys; keep original ZIP separately."""
        path = Path(path).absolute()
        stat = path.stat() if path.exists() else None
        require(path != self._source_path and path.resolve() != self._source_resolved
                and not (stat and (stat.st_dev, stat.st_ino) == self._source_identity), 'NPZ output must not overwrite the input release')
        sample = self[index]
        payload = dict(sample['fields'], **{k: sample[k] for k in ('frame_indices', 'time_s', 'dt_s', 'range_frame_mask')},
                       metadata_utf8=np.frombuffer(encode(sample['metadata']).encode('utf-8'), dtype=np.uint8))
        require(set(payload) == NPZ_KEYS and sum(a.nbytes for a in payload.values()) + len(payload) * 512 <= MAX_NPZ_BYTES,
                'Complete native NPZ exceeds 16 MiB')
        fd, temporary = tempfile.mkstemp(prefix='.native-sample-', suffix='.npz', dir=path.parent)
        try:
            with os.fdopen(fd, 'w+b') as output:
                np.savez(output, **payload)
                require(output.tell() <= MAX_NPZ_BYTES, 'Native NPZ output exceeds 16 MiB')
                output.flush(); os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--split', choices=SPLITS, required=True)
    parser.add_argument('--window-frames', type=int, default=9)
    parser.add_argument('--sample', type=int, default=0)
    parser.add_argument('--npz', type=Path)
    args = parser.parse_args()
    dataset = NativeSequenceDataset(args.release, sha256=args.sha256, split=args.split, window_frames=args.window_frames)
    report = {'release_sha256': args.sha256, 'split': args.split, 'samples': len(dataset), 'limitations': dataset._limitations}
    if len(dataset):
        sample = dataset[args.sample]
        report.update(fields={name: {'shape': list(a.shape), 'dtype': str(a.dtype)} for name, a in sample['fields'].items()},
            frame_indices=sample['frame_indices'].tolist(), time_s=sample['time_s'].tolist(),
            range_frame_mask=sample['range_frame_mask'].tolist(), metadata=sample['metadata'])
        if args.npz: dataset.write_npz(args.npz, args.sample)
    else:
        require(args.npz is None, 'Empty split has no sample to export')
    print(encode(report))


if __name__ == '__main__':
    main()
