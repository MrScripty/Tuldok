"""Whole-cloud consumer controls using tiny authored actual PLY sources."""
import copy
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from app import Dataset
from fixtures.native_pointcloud_fixture import populate, freeze, pair, admit, review
from native_sequence_dataset import CONTEXT_KEYS
import native_pointcloud_dataset as native
from workbench import encode


def packet(folder):
    dataset = Dataset(str(folder))
    try:
        rows, bridge = populate(dataset)
        return freeze(dataset, rows)[0]
    finally:
        dataset.close()


def entries(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def pack(values, compression=zipfile.ZIP_STORED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=compression) as archive:
        for name, value in values.items():
            archive.writestr(name, value)
    return stream.getvalue()


def rewrite(raw, change, synchronize=True):
    values = entries(raw); manifest = json.loads(values['manifest.json'])
    change(manifest, values)
    values['manifest.json'] = encode(manifest).encode()
    if synchronize:
        for split in native.SPLITS:
            values[split + '/records.jsonl'] = b''.join((encode(row) + '\n').encode() for row in manifest['records'] if row['split'] == split)
    return pack(values)


class NativePointCloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.raw = packet(self.root / 'owner')
        self.path = self.root / 'release.zip'; self.path.write_bytes(self.raw)

    def load(self, raw=None, **options):
        if raw is not None:
            self.path.write_bytes(raw)
        request = {'sha256': native.sha(self.path.read_bytes()), 'split': 'train'}
        request.update(options)
        return native.NativePointCloudDataset(self.path, **request)

    def refuse(self, raw):
        with self.assertRaises(native.NativePointCloudError):
            self.load(raw)

    def test_actual_native_whole_clouds_mixed_types_signed_zero_optional_attributes(self):
        dataset = self.load(); self.assertEqual(len(dataset), 2)
        sample = dataset[0]; fields = sample['fields']; metadata = sample['metadata']
        self.assertEqual(list(fields), ['x', 'y', 'z', 'nx', 'ny', 'nz', 'red', 'green', 'blue'])
        self.assertEqual({name: array.shape for name, array in fields.items()}, {name: (4,) for name in fields})
        self.assertEqual((fields['x'].dtype.str, fields['y'].dtype.str, fields['red'].dtype.str), ('<f4', '<f8', '|u1'))
        self.assertEqual(fields['x'][0].tobytes(), struct.pack('<I', 0x80000000))
        self.assertEqual(fields['x'][3].tobytes(), struct.pack('<I', 0x3dcccccd))
        self.assertEqual(fields['nz'].tolist(), [2., 2., 2., 2.])
        self.assertEqual(fields['red'].tolist(), [255, 0, 0, 127])
        self.assertEqual(metadata['array_axes'], ['point'])
        self.assertEqual(metadata['record']['review'], 'human_reviewed')
        self.assertEqual(metadata['record']['provenance']['rights'], 'unknown')
        self.assertEqual(metadata['release_sha256'], native.sha(self.raw))
        validation = self.load(split='validation'); self.assertEqual(len(validation), 1)
        xyz = validation[0]; self.assertEqual(list(xyz['fields']), ['x', 'y', 'z'])
        self.assertEqual(xyz['fields']['x'].tolist(), [10., 11., 11.])
        self.assertEqual(xyz['fields']['z'][0].tobytes(), struct.pack('<Q', 0x8000000000000000))
        self.assertEqual(xyz['metadata']['units'], 'mm')

    def test_fresh_arrays_deep_metadata_and_captured_immutable_source(self):
        dataset = self.load(); expected = dataset[0]
        altered = dataset[0]; altered['fields']['x'][:] = 77
        altered['metadata']['record']['annotation']['note'] = 'mutated'
        altered['metadata']['declared_family_context'][0]['groups'].append('mutated')
        self.path.write_bytes(b'Replaced path after admission; captured bytes remain authoritative.')
        repeated = dataset[0]
        for name in expected['fields']:
            self.assertEqual(expected['fields'][name].tobytes(), repeated['fields'][name].tobytes())
        self.assertEqual(expected['metadata'], repeated['metadata'])

    def test_empty_split_iteration_and_strict_sample_indices(self):
        dataset = self.load(); self.assertEqual(len(list(dataset)), 2)
        for index in (True, False, -1, 2, 0.0, '0'):
            with self.assertRaises(native.NativePointCloudError):
                dataset[index]
        empty = self.load(split='test'); self.assertEqual(len(empty), 0); self.assertEqual(list(empty), [])
        with self.assertRaises(native.NativePointCloudError):
            empty.write_npz(self.root / 'empty.npz')
        self.assertFalse((self.root / 'empty.npz').exists())

    def test_pickle_free_npz_preserves_native_bytes_and_metadata(self):
        dataset = self.load(); sample = dataset[0]; output = self.root / 'sample.npz'
        dataset.write_npz(output)
        with np.load(output, allow_pickle=False) as archive:
            self.assertEqual(set(archive.files), set(sample['fields']) | {'metadata_utf8'})
            for name, values in sample['fields'].items():
                self.assertEqual(archive[name].dtype, values.dtype)
                self.assertEqual(archive[name].tobytes(), values.tobytes())
            self.assertEqual(archive['metadata_utf8'].dtype, np.uint8)
            self.assertEqual(json.loads(archive['metadata_utf8'].tobytes()), sample['metadata'])
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_output_aliases_and_atomic_write_failures_preserve_existing_bytes(self):
        dataset = self.load(); hard = self.root / 'hard.npz'; sym = self.root / 'sym.npz'
        os.link(self.path, hard); sym.symlink_to(self.path)
        for output in (self.path, hard, sym):
            with self.assertRaisesRegex(native.NativePointCloudError, 'overwrite'):
                dataset.write_npz(output)
            self.assertEqual(self.path.read_bytes(), self.raw)
        output = self.root / 'prior.npz'; output.write_bytes(b'Prior complete destination')
        def failed_writer(stream, **values):
            stream.write(b'Incomplete temporary output')
            raise OSError('Controlled disk write failure')
        for target, failure in [('native_pointcloud_dataset.np.savez', failed_writer), ('native_pointcloud_dataset.os.replace', OSError('Controlled replace failure'))]:
            with patch(target, side_effect=failure):
                with self.assertRaises(OSError):
                    dataset.write_npz(output)
            self.assertEqual(output.read_bytes(), b'Prior complete destination')
            self.assertEqual(list(self.root.glob('.native-points-*')), [])
        with patch.object(native, 'MAX_NPZ_BYTES', 32):
            with self.assertRaises(native.NativePointCloudError):
                dataset.write_npz(output)
        self.assertEqual(output.read_bytes(), b'Prior complete destination')

    def test_known_deleted_unselected_cross_kind_bridge_is_preserved(self):
        dataset = self.load(); context = dataset[0]['metadata']['declared_family_context']
        self.assertEqual(len(context), 4)
        deleted = [row for row in context if not row['source_available']]
        self.assertEqual(len(deleted), 1); self.assertEqual(deleted[0]['kind'], 'text')
        self.assertIs(deleted[0]['source_lineage_known'], True)
        self.assertTrue(all(set(row) == CONTEXT_KEYS for row in context))
        train = [sample['metadata']['record'] for sample in dataset]
        self.assertEqual(len({row['export_group'] for row in train}), 1)
        self.assertTrue(all(deleted[0]['id'] in row['parents'] for row in train))

    def test_missing_proof_snapshot_association_or_unknown_deleted_lineage_refused(self):
        def legacy(manifest, values):
            manifest.pop('protected_components')
            for row in manifest['records']:
                row.pop('export_group')
        self.refuse(rewrite(self.raw, legacy))
        mutations = [
            lambda m, v: m['records'][0].update(export_group='component:' + '0' * 64),
            lambda m, v: m['records'][0].update(revision=m['records'][0]['revision'] + 1),
            lambda m, v: next(item for items in m['protected_components'].values() for item in items if not item['source_available']).update(source_lineage_known=False),
            lambda m, v: next(item for items in m['protected_components'].values() for item in items if not item['source_available']).update(parents=['f' * 32]),
            lambda m, v: next(iter(m['protected_components'].values())).append(copy.deepcopy(next(iter(m['protected_components'].values()))[0])),
        ]
        for change in mutations:
            with self.subTest(change=change):
                self.refuse(rewrite(self.raw, change))

    def test_refuses_fixed_split_crossing_and_report_bool_or_assignment_tampering(self):
        changes = [
            lambda m, v: m['records'][0].update(split='test'),
            lambda m, v: m['split_report']['actual_counts'].update(train=True),
            lambda m, v: m['split_report']['requested_percentages'].update(train=True),
            lambda m, v: m['split_report'].update(independent_components=True),
            lambda m, v: m['split_report'].update(note='Invented allocation proof'),
            lambda m, v: next(item for items in m['protected_components'].values() for item in items if not item['source_available']).update(source_split='validation'),
        ]
        for change in changes:
            self.refuse(rewrite(self.raw, change))

    def test_raw_hash_schema_review_and_projection_associations_refused_before_reader(self):
        changes = [
            lambda m, v: m.update(schema_version=True),
            lambda m, v: m.update(schema_version=2),
            lambda m, v: m.update(vocabulary=['Invented class']),
            lambda m, v: m['records'][0].update(review='draft'),
            lambda m, v: m['records'][0].update(source_available=False),
            lambda m, v: m['records'][0].update(kind='mesh'),
            lambda m, v: m['records'][0].update(annotation={'note': ''}),
            lambda m, v: m['records'][0].update(annotation={'note': 'QA', 'grade': 1}),
            lambda m, v: m['records'][0].update(asset_sha256='0' * 64),
            lambda m, v: m['records'][0]['pointcloud'].update(point_count=True),
            lambda m, v: m['records'][0].update(groups=m['records'][0]['groups'][1:]),
            lambda m, v: v.update({'README.txt': b'Wrong canonical scope'}),
            lambda m, v: v.update({'test/coco.json': b'{"images":[1],"annotations":[],"categories":[]}'}),
            lambda m, v: v.update({'unknown.txt': b'Unexpected member'}),
        ]
        for change in changes:
            with patch.object(native.NativePointCloudDataset, '_reader_pins', side_effect=AssertionError('Malformed packet reached external reader')):
                self.refuse(rewrite(self.raw, change))
        raw = rewrite(self.raw, lambda m, v: v.update({'train/records.jsonl': b''}), synchronize=False)
        self.refuse(raw)

    def test_hash_truncation_compression_duplicate_names_and_local_header_controls(self):
        with self.assertRaisesRegex(native.NativePointCloudError, 'SHA256'):
            self.load(sha256='0' * 64)
        for raw in (self.raw[:-1], self.raw[:100], b'prefix' + self.raw, self.raw + b'trailing', pack(entries(self.raw), zipfile.ZIP_DEFLATED)):
            self.refuse(raw)
        changed = bytearray(self.raw); struct.pack_into('<H', changed, 6, 8); self.refuse(bytes(changed))
        changed = bytearray(self.raw); struct.pack_into('<I', changed, 14, 0); self.refuse(bytes(changed))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, value in entries(self.raw).items():
                archive.writestr(name, value)
            archive.writestr('manifest.json', b'{}')
        self.refuse(stream.getvalue())

    def test_json_duplicate_nonfinite_surrogate_depth_and_truncated_line_controls(self):
        for body in (b'{"schema_version":1,"schema_version":1}', b'{"number":NaN}', b'{"number":1e999}',
                     b'{"number":1e-999}', b'{"text":"\\ud800"}', b'[' * 65 + b'0' + b']' * 65, b'\xff'):
            values = entries(self.raw); values['manifest.json'] = body; self.refuse(pack(values))
        values = entries(self.raw); values['train/records.jsonl'] = values['train/records.jsonl'][:-1]; self.refuse(pack(values))

    def test_wrong_axis_nonfinite_truncated_raw_and_metadata_hash_controls(self):
        raw, sidecar = pair(); side = json.loads(sidecar)
        for geometry, message in ((raw.replace(b'property float x', b'property float q'), 'property axes'),
                                  (raw.replace(b'1 2 0 ', b'NaN 2 0 '), 'finite decimal'), (raw[:-1], 'final newline')):
            changed = dict(side, geometry_bytes=len(geometry), geometry_sha256=native.sha(geometry))
            bundle = pack({'points.ply': geometry, 'points.json': encode(changed).encode()})
            def replace_bundle(manifest, values):
                row = next(row for row in manifest['records'] if row['split'] == 'train')
                values[row['asset']] = bundle
                row.update(content_hash=native.sha(bundle), source_sha256=native.sha(bundle), asset_sha256=native.sha(bundle))
                for member in manifest['protected_components'][row['export_group']]:
                    if member['id'] == row['id']:
                        member.update(content_hash=row['content_hash'], source_sha256=row['source_sha256'])
            with self.assertRaisesRegex(native.NativePointCloudError, message):
                self.load(rewrite(self.raw, replace_bundle))

    def test_optional_normals_only_and_rgb_only_stay_native_and_absent(self):
        dataset = Dataset(str(self.root / 'optional-owner'))
        try:
            source, sidecar = pair(); original = source.decode().splitlines(); end = original.index('end_header')
            rows = []
            for mode in ('normals-only', 'rgb-only'):
                keep = [0, 1, 2] + ([3, 4, 5] if mode == 'normals-only' else [6, 7, 8])
                headers = [line for line in original[:end] if not line.startswith('property ')]
                properties = [line for line in original[:end] if line.startswith('property ')]
                raw = ('\n'.join(headers + [properties[index] for index in keep] + ['end_header']
                    + [' '.join(line.split()[index] for index in keep) for line in original[end + 1:]]) + '\n').encode()
                manifest = json.loads(sidecar)
                manifest.update(geometry_bytes=len(raw), geometry_sha256=native.sha(raw))
                manifest['provenance']['revision'] = mode
                row = admit(dataset.workbench, raw, encode(manifest).encode())
                row = dataset.workbench.save(row['id'], dict(row, provenance=row['provenance'], annotation={'note': 'QA optional attributes'}, review='human_reviewed'))
                rows.append(row)
            request = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows], ratios=dict(train=100, validation=0, test=0), seed=4)
            preview = dataset.releases.preview(request); self.assertTrue(preview['eligible'])
            release = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
            consumed = native.NativePointCloudDataset(dataset.releases.locate(release['id']), sha256=release['id'], split='train')
            samples = list(consumed); self.assertEqual(len(samples), 2)
            self.assertEqual({tuple(sample['fields']) for sample in samples}, {('x', 'y', 'z', 'nx', 'ny', 'nz'), ('x', 'y', 'z', 'red', 'green', 'blue')})
            for sample in samples:
                self.assertEqual(sample['fields']['x'][0].tobytes(), struct.pack('<I', 0x80000000))
                self.assertEqual(sample['fields']['x'].shape, (4,))
        finally:
            dataset.close()

    def test_bounded_resources_and_actual_reader_native_mismatch_refuse(self):
        for name, value in [('MAX_RELEASE_BYTES', 64), ('MAX_RECORDS', 2), ('MAX_METADATA_BYTES', 32), ('MAX_LINE_BYTES', 16), ('MAX_SELECTED_ASSET_BYTES', 32), ('MAX_CONTEXT', 3)]:
            with patch.object(native, name, value):
                self.refuse(self.raw)
        with patch('native_sequence_dataset.MAX_CONTEXT', 3):
            self.refuse(self.raw)
        import plyfile
        original = plyfile.PlyData.read
        def changed_reader(*args, **options):
            value = original(*args, **options); value['vertex'].data['x'][0] = 88
            return value
        with patch.object(plyfile.PlyData, 'read', side_effect=changed_reader):
            with self.assertRaisesRegex(native.NativePointCloudError, 'native property dtype/bytes'):
                self.load()
        with patch.object(native, 'PLYFILE_MODULE_SHA256', '0' * 64):
            with self.assertRaisesRegex(native.NativePointCloudError, 'module hash'):
                self.load()

    def test_cli_exports_actual_whole_sample_without_training(self):
        output = self.root / 'cli.npz'
        result = subprocess.run([sys.executable, str(Path(native.__file__)), str(self.path), '--sha256', native.sha(self.raw), '--split', 'train', '--npz', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout); self.assertEqual(report['samples'], 2)
        self.assertEqual(report['metadata']['schema'], 'native_pointcloud_sample_v1')
        self.assertEqual(report['properties'][0]['shape'], [4])
        with np.load(output, allow_pickle=False) as archive:
            self.assertEqual(archive['x'][0].tobytes(), struct.pack('<I', 0x80000000))
