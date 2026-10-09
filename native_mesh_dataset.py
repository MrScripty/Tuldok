"""Bounded whole-mesh NumPy consumer of existing reviewed canonical releases.

Exact native-value binary PLY derivation, no geometry changes, split creation, targets, inference or training. The
owner-supplied release hash and declared family graph are evidence, not identity
authentication or proof of physical independence. plyfile is an optional pinned
consumer dependency; the application import/inspection path does not import it.
"""
import argparse
import base64
import copy
import hashlib
import importlib.metadata
import io
import os
from pathlib import Path
import struct
import tempfile
import zipfile

import numpy as np

from dataset_releases import SPLITS, allocate, canonical_payloads, family_context
from immutable_assets import MAX_SELECTED_ASSET_BYTES
from native_sequence_dataset import (declared_family_context,
    source_identity, NativeSequenceError, HASH, ID, MANIFEST_KEYS, ROW_KEYS)
import meshes
from native_pointcloud_dataset import strict_json, stored_zip, NativePointCloudError
from workbench import WorkbenchError, encode, strings, text_value, validate_annotation

MAX_RELEASE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_NPZ_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 64
MAX_CONTEXT = 5000
MESH_ROW_KEYS = (ROW_KEYS - {'sequence'}) | {'mesh', 'export_group'}
DTYPES = {'float': '<f4', 'double': '<f8'}
MAX_BINARY_HEADER_BYTES = 64 * 1024
MAX_BINARY_BYTES = 4 * 1024 * 1024
PROPERTY_NAMES = {'x', 'y', 'z', 'nx', 'ny', 'nz', 'vertex_indices'}
PLYFILE_VERSION = '1.1.3'
PLYFILE_MODULE_SHA256 = 'b8ac8908306945b4313a53d84665d7affcd467e5be7d03c82bec986220166f45'
NUMPY_VERSION = '2.5.3'


class NativeMeshError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise NativeMeshError(message)


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, 'Invalid ' + name)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NativeMeshDataset:
    """Map-style dataset: one complete mesh per item, separate native properties.

    All packet evidence and actual external native arrays are checked at admission.
    Arrays are materialized transiently per mesh, not cached as an aggregate.
    Item access reparses captured immutable bytes and returns fresh arrays and deep
    metadata. Variable vertex/triangle counts and optional normals need an explicit collator.
    """
    BUNDLE_LIMIT = meshes.BUNDLE_LIMIT

    def __init__(self, release, *, sha256, split):
        require(type(sha256) is str and HASH.fullmatch(sha256), 'Supply exact release SHA256 from its owner')
        require(type(split) is str and split in SPLITS, 'Supply explicit train/validation/test split')
        self._source_path = Path(release).absolute()
        self._source_resolved = self._source_path.resolve()
        with self._source_path.open('rb') as source:
            identity = os.fstat(source.fileno())
            self._source_identity = identity.st_dev, identity.st_ino
            self._raw = source.read(MAX_RELEASE_BYTES + 1)
        require(0 < len(self._raw) <= MAX_RELEASE_BYTES, 'Release exceeds 64 MiB physical bound')
        require(sha(self._raw) == sha256, 'Release SHA256 mismatch')
        self._sha, self._split = sha256, split
        try:
            self._admit()
        except NativeMeshError:
            raise
        except (NativePointCloudError, NativeSequenceError, WorkbenchError, ValueError, KeyError, TypeError,
                UnicodeError, OverflowError, RecursionError, zipfile.BadZipFile,
                RuntimeError, struct.error) as error:
            raise NativeMeshError('Invalid native mesh release: ' + str(error)) from error
        self._samples = [index for index, row in enumerate(self._records) if row['split'] == split]

    def _admit(self):
        with stored_zip(self._raw, MAX_RECORDS + 8, MAX_RELEASE_BYTES) as archive:
            require('manifest.json' in archive.namelist(), 'Canonical manifest required')
            require(archive.getinfo('manifest.json').file_size <= MAX_METADATA_BYTES, 'Manifest exceeds 8 MiB')
            manifest = strict_json(archive.read('manifest.json'))
            require(type(manifest) is dict and set(manifest) == MANIFEST_KEYS | {'protected_components'},
                'Exact mesh canonical manifest with complete family proof required')
            integer(manifest['schema_version'], 1, 1, 'canonical schema version')
            integer(manifest['seed'], 0, 2**32 - 1, 'split seed')
            rows = manifest['records']
            require(type(rows) is list and 1 <= len(rows) <= MAX_RECORDS, 'Supply 1..64 whole meshes')
            ids, assets, bundle_bytes = set(), set(), 0
            for row in rows:
                require(type(row) is dict and set(row) == MESH_ROW_KEYS, 'Exact canonical mesh record keys required')
                ident = row['id']
                require(type(ident) is str and ID.fullmatch(ident) and ident not in ids, 'Unique native record ID required')
                ids.add(ident)
                require(row['kind'] == 'mesh' and row['task'] == 'mesh_geometry'
                    and row['review'] == 'human_reviewed' and row['source_available'] is True
                    and row['source_lineage_known'] is True, 'Available human-reviewed whole meshes required')
                source_identity(row)
                require(all(row[key] is None for key in ('text', 'width', 'height', 'corner_annotation')), 'Mesh record cannot declare image/text geometry')
                require(type(row['split']) is str and row['split'] in SPLITS, 'Native split required')
                require(row['source_split'] == 'unassigned' or row['source_split'] == row['split'], 'Fixed source split conflict')
                require(strings(row['groups'], 'Native groups') == row['groups']
                    and strings(row['parents'], 'Native parents') == row['parents'], 'Canonical relationships required')
                for key in ('name', 'created_at', 'updated_at'):
                    text_value(row[key], 'Native ' + key, 200 if key == 'name' else 120)
                require(type(row['provenance']) is dict, 'Existing rights provenance required')
                text_value(row['provenance'].get('rights'), 'Rights / permission note', 1000)
                require(encode(validate_annotation('mesh_geometry', row['annotation'], row)) == encode(row['annotation'])
                    and bool(row['annotation']['note'].strip()), 'Canonical nonempty human inspection note required')
                asset = 'assets/' + ident + '.zip'
                require(row['asset'] == asset and asset in archive.namelist(), 'Exact whole-mesh asset path required')
                assets.add(asset)
                info = archive.getinfo(asset)
                require(0 < info.file_size <= self.BUNDLE_LIMIT, 'Mesh bundle exceeds byte bounds')
                bundle_bytes += info.file_size
                require(bundle_bytes <= MAX_SELECTED_ASSET_BYTES, 'Selected raw bundles exceed 40 MiB')
                raw = archive.read(asset)
                require(sha(raw) == row['asset_sha256'] == row['content_hash'] == row['source_sha256'], 'Whole-mesh asset hash association mismatch')
                prepared, _ = self._prepare_bundle(raw)
                require(encode(row['mesh']) == encode(dict(prepared['metadata'], bundle_bytes=len(raw))), 'Mesh metadata differs from exact immutable source')
                require(row['source_split'] == 'unassigned', 'Mesh source split must be unassigned')
                require(set(prepared['metadata']['protected_groups']) <= set(row['groups']), 'Both raw-derived mesh family groups required')
            names = assets | {'manifest.json', 'README.txt'} | {split + '/' + name for split in SPLITS for name in ('records.jsonl', 'coco.json')}
            require(set(archive.namelist()) == names, 'Exact canonical mesh release members required')
            for split in SPLITS:
                filename = split + '/records.jsonl'
                require(archive.getinfo(filename).file_size <= MAX_METADATA_BYTES, 'Split JSONL exceeds 8 MiB')
                raw = archive.read(filename)
                require(not raw or raw.endswith(b'\n'), 'Truncated split JSONL')
                lines = raw.splitlines(keepends=True)
                require(len(lines) <= MAX_RECORDS and all(len(line) <= MAX_LINE_BYTES for line in lines), 'Bounded split records required')
                require(encode([strict_json(line) for line in lines]) == encode([row for row in rows if row['split'] == split]), 'Manifest/split JSONL association mismatch')
                require(archive.getinfo(split + '/coco.json').file_size <= 4096, 'Bounded empty COCO required')
                strict_json(archive.read(split + '/coco.json'))
            require(archive.getinfo('README.txt').file_size <= 4096, 'Bounded canonical README required')
            context = declared_family_context(manifest, rows)
            require(len(context) <= MAX_CONTEXT, 'Declared mesh family context exceeds 5,000 snapshots')
            ratios = manifest['split_report']['requested_percentages']
            assignments, report = allocate(rows, context, ratios, manifest['seed'])
            require(assignments == {row['id']: row['split'] for row in rows}
                and encode(report) == encode(manifest['split_report']), 'Deterministic whole-family allocation/report mismatch')
            roots, groups, snapshots, _ = family_context(rows, context)
            plain = [{key: value for key, value in row.items() if key not in ('asset', 'asset_sha256', 'split', 'export_group')} for row in rows]
            _, payloads = canonical_payloads(plain, assignments, report, manifest['seed'], roots, groups, snapshots)
            for name, expected in payloads.items():
                actual = archive.read(name)
                if name.endswith('.json') or name.endswith('.jsonl'):
                    # Finite duplicate-free parse precedes exact canonical byte proof.
                    if name.endswith('.json'):
                        strict_json(actual)
                require(actual == expected, 'Canonical metadata/projection bytes differ: ' + name)
            self._records, self._context = rows, context
            self._limitations = list(manifest['limitations']) + [
                'Native geometry and authored review do not qualify simulation boundaries, physical independence, labels, inference or training.',
                'Declared family proof does not authenticate or establish completeness of unknown upstream evidence.',
                'Each complete mesh is a sample; variable vertex/triangle counts and optional normals require an explicit collator.',
                'Derived binary PLY preserves declared native values, not original ASCII bytes; mesh-native zero is canonical positive zero.',
                'Standalone binary embeds original source provenance, not complete owner review, corrected rights or family proof; retain original release and NPZ metadata.']
            self._reader_pins()
            for row in rows:
                self._materialize(archive.read(row['asset']), row)

    def _prepare_bundle(self, raw):
        with stored_zip(raw, 2, meshes.BUNDLE_LIMIT) as bundle:
            require(bundle.namelist() == ['mesh.ply', 'mesh.json'], 'Exact ordered whole mesh raw-pair members required')
            for name, cap in zip(('mesh.ply', 'mesh.json'), (meshes.PLY_LIMIT, meshes.MANIFEST_LIMIT)):
                require(0 < bundle.getinfo(name).file_size <= cap, 'Mesh source file exceeds byte bounds')
            geometry, sidecar = (bundle.read(name) for name in ('mesh.ply', 'mesh.json'))
        strict_json(sidecar)
        return meshes.prepare(geometry, sidecar), sidecar

    def _reader_pins(self):
        try:
            import plyfile
        except ImportError as error:
            raise NativeMeshError('Optional pinned plyfile1.1.3 consumer dependency required; no automatic install') from error
        try:
            version = importlib.metadata.version('plyfile')
        except importlib.metadata.PackageNotFoundError as error:
            raise NativeMeshError('Pinned installed plyfile distribution metadata required; no automatic install') from error
        require(np.__version__ == NUMPY_VERSION and version == PLYFILE_VERSION,
            'Pinned NumPy2.5.3 and plyfile1.1.3 required; consumer never installs dependencies')
        require(sha(Path(plyfile.__file__).read_bytes()) == PLYFILE_MODULE_SHA256, 'Pinned actual plyfile module hash required')
        self._plyfile = plyfile
        self._consumer = {'plyfile': PLYFILE_VERSION, 'plyfile_module_sha256': PLYFILE_MODULE_SHA256, 'numpy': NUMPY_VERSION}

    def _materialize(self, raw, row):
        prepared, sidecar = self._prepare_bundle(raw)
        parsed = prepared['geometry']
        provenance = {
            'representation': 'derived native-value exact binary PLY; original ASCII remains authoritative',
            'release_sha256': self._sha, 'bundle_sha256': sha(raw),
            'original_geometry_sha256': prepared['metadata']['manifest']['geometry_sha256'],
            'original_manifest_sha256': sha(sidecar), 'record_id': row['id'],
            'revision': row['revision'], 'source_revision': row['source_revision'], 'split': row['split']}
        header = ['ply', 'format binary_little_endian 1.0']
        header += ['comment tuldok_' + key + ' ' + str(value) for key, value in provenance.items()]
        # The exact ORIGINAL sidecar names/hashes the original ASCII, not this derivative.
        header += ['comment tuldok_original_mesh_json_base64 ' + base64.b64encode(sidecar).decode('ascii'),
                   'element vertex ' + str(len(parsed['vertices']))]
        header += ['property ' + prop['dtype'] + ' ' + prop['name'] for prop in parsed['properties']]
        header += ['element face ' + str(len(parsed['faces'])), 'property list uchar int vertex_indices', 'end_header']
        header = ('\n'.join(header) + '\n').encode('ascii')
        require(len(header) <= MAX_BINARY_HEADER_BYTES, 'Derived binary PLY header exceeds 64 KiB')
        vertex_struct = struct.Struct('<' + ''.join('f' if prop['dtype'] == 'float' else 'd' for prop in parsed['properties']))
        triangle_struct = struct.Struct('<Biii')
        size = len(header) + vertex_struct.size * len(parsed['vertices']) + triangle_struct.size * len(parsed['faces'])
        require(size <= MAX_BINARY_BYTES, 'Derived binary PLY exceeds 4 MiB')
        stream = io.BytesIO(); stream.write(header)
        for vertex in parsed['vertices']:
            stream.write(vertex_struct.pack(*vertex))
        for face in parsed['faces']:
            stream.write(triangle_struct.pack(3, *face))
        binary = stream.getvalue()
        actual = self._plyfile.PlyData.read(io.BytesIO(binary), mmap=False)
        require(not actual.text and actual.byte_order == '<'
            and [element.name for element in actual.elements] == ['vertex', 'face'], 'Actual reader binary elements/order mismatch')
        vertices = actual['vertex'].data
        require(vertices.dtype.names == tuple(prop['name'] for prop in parsed['properties'])
            and len(vertices) == len(parsed['vertices']), 'Actual native property names/count mismatch')
        fields = {}
        for index, prop in enumerate(parsed['properties']):
            dtype = np.dtype(DTYPES[prop['dtype']])
            oracle = np.asarray([vertex[index] for vertex in parsed['vertices']], dtype=dtype)
            observed = vertices[prop['name']]
            require(observed.dtype == dtype and observed.tobytes() == oracle.tobytes(), 'Actual native property dtype/bytes mismatch: ' + prop['name'])
            fields[prop['name']] = observed.copy()
        require(actual['face'].data.dtype.names == ('vertex_indices',)
            and len(actual['face'].data) == len(parsed['faces']), 'Actual topology element/count mismatch')
        observed_faces = actual['face'].data['vertex_indices']
        require(all(face.dtype == np.dtype('<i4') and face.shape == (3,) for face in observed_faces), 'Actual topology native dtype/list length mismatch')
        faces = np.stack(observed_faces)
        require(faces.dtype == np.dtype('<i4') and faces.tobytes() == np.asarray(parsed['faces'], dtype='<i4').tobytes(), 'Actual ordered triangle indices mismatch')
        fields['vertex_indices'] = faces.copy()
        derivation = dict(provenance, format='binary_little_endian PLY 1.0', sha256=sha(binary), bytes=len(binary),
            zero_semantics='existing mesh decoder canonicalizes native zero to positive zero',
            original_mesh_json_base64=base64.b64encode(sidecar).decode('ascii'))
        return fields, binary, derivation

    def __len__(self):
        return len(self._samples)

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def _sample(self, index):
        integer(index, 0, len(self) - 1, 'sample index')
        row = self._records[self._samples[index]]
        with zipfile.ZipFile(io.BytesIO(self._raw)) as archive:
            fields, binary, derivation = self._materialize(archive.read(row['asset']), row)
        sample = {'fields': fields, 'metadata': {
            'schema': 'native_mesh_sample_v1', 'release_sha256': self._sha, 'split': self._split,
            'array_axes': {'vertex_properties': ['vertex'], 'vertex_indices': ['triangle', 'corner']},
            'properties': [{'name': name, 'shape': list(array.shape), 'dtype': array.dtype.str} for name, array in fields.items()],
            'record': copy.deepcopy(row), 'declared_family_context': copy.deepcopy(self._context),
            'units': row['mesh']['manifest']['units'], 'coordinate_system': copy.deepcopy(row['mesh']['manifest']['coordinate_system']),
            'attribute_semantics': {'coordinates': 'xyz retain declared native units and frame',
                'normals': 'dimensionless provided native values; magnitude is retained',
                'topology': 'ordered zero-based triangle corners; no reindexing or winding changes'},
            'derivation': derivation, 'consumer': dict(self._consumer), 'limitations': list(self._limitations)}}
        return sample, binary

    def __getitem__(self, index):
        return self._sample(index)[0]

    def _output_path(self, path):
        path = Path(path).absolute()
        identity = path.stat() if path.exists() else None
        require(path != self._source_path and path.resolve() != self._source_resolved
            and not (identity and (identity.st_dev, identity.st_ino) == self._source_identity), 'Derived output must not overwrite the input release')
        return path

    def _publish(self, path, writer):
        path = self._output_path(path)
        fd, temporary = tempfile.mkstemp(prefix='.native-mesh-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w+b') as output:
                writer(output)
                output.flush(); os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def write_npz(self, path, index=0):
        """Atomic pickle-free native arrays and complete sample metadata."""
        self._output_path(path)
        sample = self[index]
        payload = dict(sample['fields'], metadata_utf8=np.frombuffer(encode(sample['metadata']).encode('utf-8'), dtype=np.uint8))
        require({'x', 'y', 'z', 'vertex_indices', 'metadata_utf8'} <= set(payload) <= PROPERTY_NAMES | {'metadata_utf8'}
            and all(array.dtype.kind in 'fui' for array in payload.values())
            and sum(array.nbytes for array in payload.values()) + len(payload) * 512 <= MAX_NPZ_BYTES,
            'Complete pickle-free native NPZ exceeds 16 MiB or has unsupported arrays')
        def writer(output):
            np.savez(output, **payload)
            require(output.tell() <= MAX_NPZ_BYTES, 'Complete native NPZ output exceeds 16 MiB')
        self._publish(path, writer)

    def write_ply(self, path, index=0):
        """Atomic standard binary derivative including ORIGINAL source provenance."""
        self._output_path(path)
        _, binary = self._sample(index)
        self._publish(path, lambda output: output.write(binary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--split', choices=SPLITS, required=True)
    parser.add_argument('--sample', type=int, default=0)
    parser.add_argument('--npz', type=Path)
    parser.add_argument('--ply', type=Path)
    args = parser.parse_args()
    dataset = NativeMeshDataset(args.release, sha256=args.sha256, split=args.split)
    report = {'release_sha256': args.sha256, 'split': args.split, 'samples': len(dataset), 'limitations': dataset._limitations}
    if len(dataset):
        sample = dataset[args.sample]
        report.update(properties=sample['metadata']['properties'], metadata=sample['metadata'])
        if args.npz:
            dataset.write_npz(args.npz, args.sample)
        if args.ply:
            dataset.write_ply(args.ply, args.sample)
    else:
        require(args.npz is None and args.ply is None, 'Empty split has no sample to export')
    print(encode(report))


if __name__ == '__main__':
    main()
