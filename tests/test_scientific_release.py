"""Frozen generic fields: independent numerical oracle and immutable custody."""
from auth_helpers import bind_owner
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid
import zipfile

from app import Dataset
from postgres_helpers import database_snapshot
import scientific_release
from test_mesh_release import change_manifest, rewrite
from workbench import WorkbenchError, encode


def authored_bundle(source_id='authored-rotation'):
    """Independent tiny NPY writer; no production parser or producer format."""
    arrays = {}
    fields = [dict(id='temperature', label='Temperature', dtype='<f8', centering='cell', units='K', stage='observed'),
              dict(id='flux', label='X flux', dtype='<f4', centering='face_x', units='m/s', stage='after correction')]
    frames = []
    for index, time in enumerate(('0.1250', '0.2500')):
        references = []
        for field, shape, values in ((fields[0], (1,2,2), [1+index,2+index,3+index,4+index]),
                                     (fields[1], (1,2,3), [index+i/4 for i in range(6)])):
            header = repr(dict(descr=field['dtype'], fortran_order=False, shape=shape)).encode('ascii')
            header += b' ' * (-(10 + len(header) + 1) % 64) + b'\n'
            payload = struct.pack('<' + ('d' if field['dtype'] == '<f8' else 'f') * len(values), *values)
            raw = b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + payload
            name = f'arrays/{index}-{field["id"]}.npy'
            arrays[name] = raw
            references.append(dict(field=field['id'], path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        frames.append(dict(time=time, arrays=references))
    manifest = dict(format='scientific_field_sequence_v1', schema_version=1,
        grid=dict(shape_xyz=[2,2,1], origin_xyz=[10,-20,30], spacing_xyz=[2,3,5],
                  orientation=[[0,-1,0],[1,0,0],[0,0,1]], units='m'),
        time_units='s', fields=fields, frames=frames, family=dict(namespace='authored-tests', id='one-family'),
        sources=[], provenance=dict(producer='generic authored numeric fixture', source_id=source_id))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as bundle:
        bundle.writestr('manifest.json', encode(manifest))
        for name, raw in arrays.items():
            bundle.writestr(name, raw)
    return output.getvalue(), manifest, arrays


def large_authored_bundle():
    _, manifest, original = authored_bundle()
    template = next(raw for name, raw in original.items() if 'temperature' in name)
    manifest['fields'] = [dict(manifest['fields'][0], id=f'field-{index:02d}', label=f'Quantity {index}') for index in range(16)]
    manifest['frames'], arrays = [], {}
    for index in range(128):
        references = []
        for field in manifest['fields']:
            name = f'arrays/frame-{index:03d}/{field["id"]}.npy'
            arrays[name] = template
            references.append(dict(field=field['id'], path=name, bytes=len(template), sha256=hashlib.sha256(template).hexdigest()))
        manifest['frames'].append(dict(time=str(index), arrays=references))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as bundle:
        bundle.writestr('manifest.json', encode(manifest))
        for name, raw in arrays.items():
            bundle.writestr(name, raw)
    return output.getvalue(), manifest, arrays


class ScientificRelease(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project_root = Path(self.temporary.name) / 'project'
        self.project_root.mkdir()
        self.dataset = Dataset(Path(self.temporary.name) / 'catalog', project_roots={'fixture': self.project_root}); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        self.workbench = self.dataset.workbench

    def freeze(self, related=False, large=False):
        self.source, self.manifest, self.arrays = large_authored_bundle() if large else authored_bundle()
        sources = [self.source]
        if related:
            sources.append(authored_bundle('alternate-declaration')[0])
        project = dict(schema_version=1, id=uuid.uuid4().hex, name='Independent fields fixture',
                       data=[], recipes=[], evidence=[], requirements=[])
        for index, raw in enumerate(sources):
            name = f'fields-{index}.zip'
            (self.project_root / name).write_bytes(raw)
            project['data'].append(dict(id=f'fields-{index}', label=f'Fields {index}', path=name,
                                        sha256=hashlib.sha256(raw).hexdigest()))
        (self.project_root / 'project.json').write_text(encode(project))
        self.dataset.projects.open(dict(root='fixture', manifest_path='project.json'))
        rows = []
        for index, raw in enumerate(sources):
            captured, source = self.dataset.projects.read_data_reference(project['id'], f'fields-{index}',
                hashlib.sha256(raw).hexdigest(), 40 * 1024 * 1024)
            row = self.workbench.scientific.admit(raw, dict(name=f'Fields {index}', rights='Authored fixture',
                groups=[], parents=[]), source)
            self.assertEqual(captured, raw)
            row = self.workbench.save(row['id'], dict(row, annotation={'note': 'Inspected authored fields.'}, review='human_reviewed'))
            rows.append(row)
        request = dict(items=[{key: row[key] for key in ('id','revision','source_revision')} for row in rows],
                       ratios=dict(train=100,validation=0,test=0), seed=9)
        preview = self.dataset.releases.preview(request)
        result = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        self.path = self.dataset.releases.locate(result['id'])
        return self.path.read_bytes(), rows

    def test_frozen_original_bytes_metadata_readonly_and_cold_cli(self):
        raw, rows = self.freeze()
        before = database_snapshot(self.dataset.db)
        summary = scientific_release.validate_release(self.path, hashlib.sha256(raw).hexdigest())
        self.assertEqual(database_snapshot(self.dataset.db), before)
        self.assertEqual((summary['field_sequence_count'], summary['frame_count']), (1,2))
        self.assertEqual(summary['family_scope'], 'selected_records_only')
        self.assertEqual(summary['field_sequences'][0]['manifest'], self.manifest)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            row = json.loads(archive.read('manifest.json'))['records'][0]
            self.assertEqual(archive.read(row['asset']), self.source)
        self.workbench.save(rows[0]['id'], dict(rows[0], annotation={'note': 'Later catalog edit'}, review='human_reviewed'))
        self.assertEqual(scientific_release.validate_bytes(raw), summary)
        child = subprocess.run([sys.executable, '-O', 'scientific_release.py', str(self.path)],
                               capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(child.stdout), summary)

    def test_metadata_review_projection_identity_and_source_hash_fail_closed(self):
        raw, _ = self.freeze()
        cases = [
            (lambda m: m['records'][0].update(review='draft'), 'human-reviewed'),
            (lambda m: m['records'][0].update(asset_sha256='0'*64), 'hash mismatch'),
            (lambda m: m['records'][0].update(revision=True), 'revision'),
            (lambda m: m['records'][0].update(groups=['unrelated']), 'family is missing'),
            (lambda m: m['records'][0]['field_sequence']['manifest']['frames'][0].update(time='0.125'), 'metadata differs'),
            (lambda m: m['records'][0]['field_sequence']['manifest']['grid'].update(units='mm'), 'metadata differs'),
            (lambda m: m['records'][0]['field_sequence']['manifest']['fields'][0].update(stage='different'), 'metadata differs'),
            (lambda m: m['records'][0]['provenance']['field_sequence']['manifest']['frames'][0].update(time='9'), 'provenance differs'),
            (lambda m: m['records'][0]['provenance'].update(source_sha256='0'*64), 'provenance differs'),
            (lambda m: m['records'][0]['provenance'].update(method='invented'), 'provenance differs'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(measured_sha256='0'*64), 'identity differs'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(project_id='invalid'), 'identity differs'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(manifest_sha256='invalid'), 'identity differs'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(extra='unexpected'), 'source receipt'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(reference_id=''), 'Project reference'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(path='bad\npath'), 'Project source path'),
        ]
        for change, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(WorkbenchError, message):
                scientific_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, change)))
        with self.assertRaisesRegex(WorkbenchError, 'JSONL differs'):
            scientific_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries,
                lambda m: m['records'][0].update(name='Different projection'), False)))
        with self.assertRaisesRegex(WorkbenchError, 'SHA256 differs'):
            scientific_release.validate_bytes(raw, '0'*64)

    def test_related_sources_cannot_cross_selected_splits(self):
        raw, _ = self.freeze(related=True)
        def split(manifest):
            manifest['records'][1]['split'] = 'validation'
            manifest['split_report']['actual_counts'] = {'train':1,'validation':1}
        with self.assertRaisesRegex(WorkbenchError, 'cross frozen splits'):
            scientific_release.validate_bytes(rewrite(raw, lambda entries: change_manifest(entries, split)))

    def test_rehashed_payload_corruption_still_refuses(self):
        raw, _ = self.freeze()
        def corrupt(entries):
            row = json.loads(entries['manifest.json'])['records'][0]
            def bad_array(members):
                name = next(name for name in members if name.endswith('.npy'))
                members[name] = members[name][:-1] + bytes([members[name][-1] ^ 1])
            damaged = rewrite(entries[row['asset']], bad_array)
            entries[row['asset']] = damaged
            digest = hashlib.sha256(damaged).hexdigest()
            change_manifest(entries, lambda m: m['records'][0].update(asset_sha256=digest,content_hash=digest,source_sha256=digest))
        with self.assertRaises(WorkbenchError):
            scientific_release.validate_bytes(rewrite(raw, corrupt))

    def test_legal_scientific_metadata_larger_than_legacy_row_bound(self):
        raw, _ = self.freeze(large=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertGreater(len(archive.read('train/records.jsonl')), 256 * 1024)
        report = scientific_release.validate_bytes(raw)
        self.assertEqual(report['frame_count'], 128)
        self.assertEqual(report['field_sequences'][0]['field_count'], 16)
        self.assertEqual(report['field_sequences'][0]['manifest'], self.manifest)

    def test_external_numpy_reads_exact_frozen_npy_values_and_staggering(self):
        self.freeze()
        python = os.environ.get('TULDOK_NATIVE_READER_PYTHON', sys.executable)
        probe = subprocess.run([python, '-c', 'import numpy'], capture_output=True)
        if probe.returncode:
            self.skipTest('External NumPy interpreter unavailable; set TULDOK_NATIVE_READER_PYTHON.')
        script = '''
import io,json,sys,zipfile
import numpy as np
with zipfile.ZipFile(sys.argv[1]) as release:
 row=json.loads(release.read('manifest.json'))['records'][0]
 with zipfile.ZipFile(io.BytesIO(release.read(row['asset']))) as bundle:
  result={}
  for name in bundle.namelist():
   if name.endswith('.npy'):
    a=np.load(io.BytesIO(bundle.read(name)),allow_pickle=False)
    result[name]={'dtype':a.dtype.str,'shape':list(a.shape),'values':a.ravel(order='C').tolist()}
print(json.dumps(result))
'''
        child = subprocess.run([python, '-c', script, str(self.path)], capture_output=True, text=True, check=True)
        observed = json.loads(child.stdout)
        for index in range(2):
            self.assertEqual(observed[f'arrays/{index}-temperature.npy'],
                dict(dtype='<f8',shape=[1,2,2],values=[1+index,2+index,3+index,4+index]))
            self.assertEqual(observed[f'arrays/{index}-flux.npy'],
                dict(dtype='<f4',shape=[1,2,3],values=[index+i/4 for i in range(6)]))
