"""Real frozen exports with independent authored geometry and archive mutations."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from app import Dataset
import mesh_release
import meshes
from test_meshes import body, fixture
from workbench import WorkbenchError, encode


def rewrite(raw, change):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    change(entries)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


def change_manifest(entries, change, synchronize=True):
    manifest = json.loads(entries['manifest.json'])
    change(manifest)
    entries['manifest.json'] = encode(manifest).encode()
    if synchronize:
        for split in mesh_release.SPLITS:
            entries[split + '/records.jsonl'] = ''.join(encode(row) + '\n' for row in manifest['records'] if row['split'] == split).encode()


class MeshRelease(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.dataset = Dataset(self.temporary.name)
        self.addCleanup(self.dataset.close)
        self.workbench = self.dataset.workbench

    def freeze(self, names=('asymmetric-prism',), note='Inspected authored geometry and source declarations.'):
        rows = []
        for name in names:
            row = meshes.admit(self.workbench, body(*fixture(name), name=name, rights='Project-authored fixture'))
            row = self.workbench.save(row['id'], dict(row, annotation={'note': note}, review='human_reviewed'))
            rows.append(row)
        request = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows], ratios=dict(train=100, validation=0, test=0), seed=4)
        preview = self.dataset.releases.preview(request)
        release = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        self.path = self.dataset.releases.locate(release['id'])
        return self.path.read_bytes(), rows

    def test_actual_export_native_values_source_bytes_and_readonly_report(self):
        raw, rows = self.freeze(('asymmetric-prism', 'open-surface'))
        before = [self.workbench.get(row['id']) for row in rows]
        result = mesh_release.validate_release(self.path, expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['family_scope'], 'selected_records_only')
        self.assertEqual(result['mesh_count'], 2)
        self.assertEqual(result['split_counts'], {'train': 2, 'validation': 0, 'test': 0})
        prism = next(row for row in result['meshes'] if row['name'] == 'asymmetric-prism')
        self.assertEqual((prism['vertex_count'], prism['triangle_count']), (6, 8))
        self.assertEqual(prism['bounds'], {'min': [0, 0, 0], 'max': [3, 2, 1.5]})
        self.assertEqual(prism['properties'], [{'name': 'x', 'dtype': 'float'}, {'name': 'y', 'dtype': 'double'}, {'name': 'z', 'dtype': 'float'}])
        self.assertEqual(prism['units'], 'cm')
        self.assertEqual(prism['coordinate_system'], {'frame': 'authored-prism', 'handedness': 'right', 'up_axis': 'z'})
        geometry = meshes.parse_ply(fixture('asymmetric-prism')[0])
        # Analytic construction is independent of both exporter and reader.
        self.assertEqual(geometry['vertices'], [[0, 0, 0], [3, 0, 0], [0, 0, 1.5], [0, 2, 0], [3, 2, 0], [0, 2, 1.5]])
        self.assertEqual(geometry['faces'], [[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4], [2, 0, 3], [2, 3, 5]])
        for token, bits in [('1.0000000596046448', 0x3f800001), ('-1.0000000596046448', 0xbf800001)]:
            self.assertEqual(struct.unpack('<I', struct.pack('<f', meshes.native(token, 'float')))[0], bits)
        self.assertEqual([self.workbench.get(row['id']) for row in rows], before)
        self.assertEqual(self.path.read_bytes(), raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as release:
            for row in json.loads(release.read('manifest.json'))['records']:
                with zipfile.ZipFile(io.BytesIO(release.read(row['asset']))) as bundle:
                    self.assertEqual((bundle.read('mesh.ply'), bundle.read('mesh.json')), fixture(row['name']))

    def test_reject_hash_revision_review_metadata_and_projection_mutations(self):
        raw, _ = self.freeze()
        cases = [
            (lambda m: m['records'][0].update(asset_sha256='0' * 64), 'hash mismatch'),
            (lambda m: m['records'][0].update(revision=True), 'revision'),
            (lambda m: m['records'][0].update(review='draft'), 'human-reviewed'),
            (lambda m: m['records'][0]['mesh']['bounds']['max'].__setitem__(0, 99), 'metadata differs'),
            (lambda m: m['records'][0].update(groups=['claimed']), 'family is missing'),
            (lambda m: m['split_report']['actual_counts'].update(train=2), 'counts disagree'),
            (lambda m: m['records'][0].update(asset='../source.zip'), 'archive paths'),
        ]
        for change, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(WorkbenchError, message):
                mesh_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, change)))
        with self.assertRaisesRegex(WorkbenchError, 'JSONL differs'):
            mesh_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, lambda m: m['records'][0].update(name='Changed'), False)))
        with self.assertRaisesRegex(WorkbenchError, 'SHA256 differs'):
            mesh_release.validate_bytes(raw, '0' * 64)

    def test_existing_human_review_with_empty_optional_note_remains_valid(self):
        raw, rows = self.freeze(note='')
        self.assertEqual(rows[0]['annotation'], {'note': ''})
        report = mesh_release.validate_bytes(raw)
        self.assertEqual(report['meshes'][0]['review'], 'human_reviewed')
        self.assertEqual(self.workbench.get(rows[0]['id'])['annotation'], {'note': ''})

    def test_actual_unicode_codepoint_boundaries_roundtrip(self):
        raw, sidecar = fixture('asymmetric-prism')
        manifest = json.loads(sidecar)
        manifest['coordinate_system']['frame'] = '\U0001f600' * 120
        for key in manifest['provenance']:
            manifest['provenance'][key] = '\U0001f600' * 1000
        row = meshes.admit(self.workbench, body(raw, encode(manifest).encode(), name='\U0001f600' * 200, rights='\U0001f600' * 1000))
        row = self.workbench.save(row['id'], dict(row, annotation={'note': ''}, review='human_reviewed'))
        request = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')}], ratios=dict(train=100, validation=0, test=0), seed=4)
        preview = self.dataset.releases.preview(request)
        release = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        report = mesh_release.validate_release(self.dataset.releases.locate(release['id']))
        self.assertEqual(report['meshes'][0]['coordinate_system']['frame'], '\U0001f600' * 120)
        self.assertEqual(report['meshes'][0]['name'], '\U0001f600' * 200)
        self.assertEqual(report['meshes'][0]['rights'], '\U0001f600' * 1000)

    def test_mixed_unknown_archive_and_unavailable_outcomes(self):
        raw, _ = self.freeze()
        for change in (lambda m: m['records'][0].update(kind='sequence'), lambda m: m.update(format='future_mesh')):
            with self.assertRaises(WorkbenchError) as error:
                mesh_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, change)))
            self.assertEqual(error.exception.code, 'unsupported')
        for malformed in (raw[:-8], raw + b'trailing', b'prefix' + raw):
            with self.assertRaises(WorkbenchError):
                mesh_release.validate_bytes(malformed)
        with self.assertRaisesRegex(WorkbenchError, 'duplicate JSON'):
            mesh_release.validate_bytes(rewrite(raw, lambda entries: entries.update({'manifest.json': b'{"schema_version":1,"schema_version":1}'})))
        with self.assertRaisesRegex(WorkbenchError, 'archive paths'):
            mesh_release.validate_bytes(rewrite(raw, lambda entries: entries.update({'../extra': b'no extraction'})))
        with self.assertRaises(WorkbenchError) as error:
            mesh_release.validate_release(Path(self.temporary.name) / 'missing.zip')
        self.assertEqual(error.exception.code, 'unavailable')

    def test_related_selected_meshes_cannot_cross_splits(self):
        raw, _ = self.freeze(('asymmetric-prism', 'open-surface'))
        def changed(manifest):
            first, second = manifest['records']
            second['parents'] = [first['id']]
            second['split'] = 'test'
            manifest['split_report']['actual_counts'] = {'train': 1, 'validation': 0, 'test': 1}
        with self.assertRaisesRegex(WorkbenchError, 'cross frozen splits'):
            mesh_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, changed)))


if __name__ == '__main__':
    unittest.main()
