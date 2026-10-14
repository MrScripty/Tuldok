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


COLD_READER_FILES = (
    'access.py', 'audio_assets.py', 'audio_classification_export.py', 'audio_export.py',
    'bulk_import.py', 'canonical_release.py', 'caption_import.py', 'dataset_releases.py',
    'image_classification_export.py', 'immutable_assets.py', 'meshes.py', 'native_text_import.py',
    'recipe_process.py', 'scientific_fields.py', 'scientific_release.py',
    'text_classification_export.py', 'text_corpus_export.py', 'workbench.py',
)


def captured_cold_reader(raw):
    """Exact declared closure in a fresh stdlib-only interpreter; no live checkout."""
    import shutil
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);closure=root/'cold';closure.mkdir()
        repository=Path(__file__).resolve().parents[1]
        for name in COLD_READER_FILES:shutil.copyfile(repository/name,closure/name)
        archive=root/'release.zip';archive.write_bytes(raw)
        program = r"""
import sys, json, importlib.abc
from pathlib import Path
class RefuseServerDependencies(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.split('.')[0] in ('PIL','psycopg','app','metadata'):
   raise ImportError('Server dependency forbidden in cold reader: '+fullname)
sys.meta_path.insert(0,RefuseServerDependencies())
closure=Path(sys.argv[1]);sys.path.insert(0,str(closure))
import scientific_release
value=scientific_release.validate_release(sys.argv[2],expected_sha256=sys.argv[3])
for name in sys.argv[4:]:
 module=sys.modules.get(name)
 if module is not None:
  assert Path(module.__file__).resolve().parent==closure
assert all('site-packages' not in path for path in sys.path)
print(json.dumps(value))
"""
        result=subprocess.run(['/usr/bin/python3','-I','-S','-B','-c',program,str(closure),str(archive),
                               hashlib.sha256(raw).hexdigest(),*[Path(name).stem for name in COLD_READER_FILES]],
                              cwd=root,capture_output=True,text=True,timeout=30)
        if result.returncode:raise AssertionError(result.stderr)
        return json.loads(result.stdout)


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

    def test_captured_project_reader_has_no_server_dependencies(self):
        raw,_rows=self.freeze()
        self.assertEqual(captured_cold_reader(raw),scientific_release.validate_bytes(raw))

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
            (lambda m: m['records'][0]['provenance']['project_source'].update(measured_sha256='0'*64), 'source receipt'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(project_id='invalid'), 'project source ID'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(manifest_sha256='invalid'), 'project source hash'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(extra='unexpected'), 'Project source fields'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(reference_id=''), 'Project reference'),
            (lambda m: m['records'][0]['provenance']['project_source'].update(path='bad\npath'), 'Project source path'),
            (lambda m: m['records'][0]['provenance'].update(run_source={}), 'mixed'),
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


class RunScientificRelease(unittest.TestCase):
    """Actual neutral Run provenance; no native solver or physics acceptance."""
    setUp = ScientificRelease.setUp

    def generate(self, *, import_record=True):
        import time
        self.source, self.manifest, self.arrays = authored_bundle()
        program = (b'import pathlib,sys\n'
                   b'pathlib.Path(sys.argv[2],"fields.zip").write_bytes(pathlib.Path(sys.argv[1]).read_bytes())\n')
        definition = dict(schema_version=1, format='external_recipe_v1', id='copy-fields',
            name='Neutral scientific byte custody', version=1, runtime='system_python',
            sources=[dict(path='copy.py', sha256=hashlib.sha256(program).hexdigest())], entrypoint='copy.py',
            arguments=[{'input':'fields'},{'output_dir':True}], parameters={},
            inputs={'fields':{'max_bytes':40 * 1024 * 1024}},
            outputs=[dict(path='fields.zip',role='field_sequence',max_bytes=40 * 1024 * 1024,required=True)],
            environment={}, resources=dict(wall_seconds=10,max_output_bytes=40 * 1024 * 1024))
        definition_raw = encode(definition).encode()
        project = dict(schema_version=1, id=uuid.uuid4().hex, name='Authored Run source fixture',
            data=[dict(id='fields',label='Authored fields',path='input.zip',sha256=hashlib.sha256(self.source).hexdigest())],
            recipes=[dict(id='copy-fields',label='Neutral byte copy',path='copy.json',sha256=hashlib.sha256(definition_raw).hexdigest())],
            evidence=[],requirements=[])
        for name, raw in {'copy.py':program,'input.zip':self.source,'copy.json':definition_raw,
                          'run-project.json':encode(project).encode()}.items():
            (self.project_root / name).write_bytes(raw)
        self.dataset.projects.open(dict(root='fixture',manifest_path='run-project.json'))
        graph = self.dataset.pipelines.create_external(dict(name='Authored field custody',project_id=project['id'],
            recipe_id='copy-fields',expected_sha256=hashlib.sha256(definition_raw).hexdigest(),
            inputs={'fields':{'reference_id':'fields','expected_sha256':hashlib.sha256(self.source).hexdigest()}}))
        preflight = self.dataset.pipelines.preflight_external(graph['id'],graph['revision'])
        run = self.dataset.runs.submit_external(dict(request_key='scientific-' + uuid.uuid4().hex,
            graph_id=graph['id'],graph_revision=graph['revision'],expected_digest=preflight['material_sha256']))
        deadline = time.monotonic() + 30
        while run['state'] in ('queued','running') and time.monotonic() < deadline:
            time.sleep(.05)
            run = self.dataset.runs.get(run['id'])
        self.assertEqual(run['state'], 'completed', run.get('error'))
        self.run = run
        if not import_record:
            return run
        row = self.workbench.scientific.admit_run_artifact(run['id'], 'fields.zip', hashlib.sha256(self.source).hexdigest(),
            dict(name='Neutral Run fields',rights='Authored numerical fixture; no scientific acceptance',groups=[],parents=[]))
        self.assertEqual(row['review'], 'draft')
        self.assertEqual(row['provenance']['method'], 'run_artifact_import')
        self.assertNotIn('project_source',row['provenance'])
        row = self.workbench.save(row['id'],dict(row,review='human_reviewed',annotation={'note':'Inspected original authored arrays.'}))
        self.run, self.row = run, row
        return row

    def freeze_run(self):
        row = self.generate()
        request = dict(items=[{key:row[key] for key in ('id','revision','source_revision')}],
                       ratios=dict(train=100,validation=0,test=0),seed=7)
        preview = self.dataset.releases.preview(request)
        result = self.dataset.releases.create(dict(request,preview_token=preview['preview_token']))
        self.path = self.dataset.releases.locate(result['id'])
        return self.path.read_bytes()

    def test_captured_run_reader_validates_receipt_without_server_dependencies(self):
        raw=self.freeze_run()
        self.assertEqual(captured_cold_reader(raw),scientific_release.validate_bytes(raw))

    def test_actual_run_source_freeze_cold_cli_preserves_exact_receipt_and_arrays(self):
        import base64
        raw = self.freeze_run()
        before = database_snapshot(self.dataset.db)
        summary = scientific_release.validate_bytes(raw)
        self.assertEqual(database_snapshot(self.dataset.db), before)
        source = self.row['provenance']['run_source']
        custody = base64.b64decode(source['custody_receipt_base64'],validate=True)
        self.assertEqual(hashlib.sha256(custody).hexdigest(),source['custody_receipt_sha256'])
        self.assertEqual(custody,(self.dataset.runs.path / self.run['id'] / 'custody-receipt.json').read_bytes())
        with zipfile.ZipFile(io.BytesIO(raw)) as release:
            frozen = json.loads(release.read('manifest.json'))['records'][0]
            self.assertEqual(frozen['provenance'],self.row['provenance'])
            self.assertEqual(release.read(frozen['asset']),self.source)
        child = subprocess.run([sys.executable,'-O','scientific_release.py',str(self.path)],
                               capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(child.stdout),summary)

    def test_run_source_tampering_and_mixed_provenance_fail_closed(self):
        import base64
        raw = self.freeze_run()
        def receipt_change(source, change):
            receipt = json.loads(base64.b64decode(source['custody_receipt_base64']))
            change(receipt)
            encoded = encode(receipt).encode()
            source['custody_receipt_base64'] = base64.b64encode(encoded).decode()
            source['custody_receipt_sha256'] = hashlib.sha256(encoded).hexdigest()
        def invalid_json(source):
            encoded = b'{"schema_version":1,"schema_version":1}'
            source['custody_receipt_base64'] = base64.b64encode(encoded).decode()
            source['custody_receipt_sha256'] = hashlib.sha256(encoded).hexdigest()
        cases = [lambda source:source.update(extra='unexpected'),
                 lambda source:source.update(schema_version=True),
                 lambda source:source.update(artifact_bytes=True),
                 lambda source:source.update(artifact_bytes=source['artifact_bytes']+1),
                 lambda source:source.update(measured_sha256='0'*64),
                 lambda source:source.update(custody_receipt_sha256='0'*64),
                 lambda source:source.update(custody_receipt_base64=source['custody_receipt_base64']+'\n'),
                 lambda source:source.update(custody_receipt_base64=base64.b64encode(b'x'*16385).decode()),
                 lambda source:source.update(request_sha256='0'*64),
                 lambda source:source.update(attempt_id='0'*32),
                 lambda source:source['custody_identity']['helper'].update(pid=True),
                 lambda source:receipt_change(source,lambda receipt:receipt.update(outcome='cancelled')),
                 lambda source:receipt_change(source,lambda receipt:receipt.update(drained=False,echild=False,outcome='unknown')),
                 invalid_json]
        for index, change in enumerate(cases):
            with self.subTest(case=index),self.assertRaises(WorkbenchError):
                scientific_release.validate_bytes(rewrite(raw,lambda entries:change_manifest(entries,
                    lambda manifest:change(manifest['records'][0]['provenance']['run_source']))))
        with self.assertRaisesRegex(WorkbenchError,'mixed'):
            scientific_release.validate_bytes(rewrite(raw,lambda entries:change_manifest(entries,
                lambda manifest:manifest['records'][0]['provenance'].update(project_source={}))))

    def test_backup_restore_preserves_project_and_run_source_bytes_review_and_history(self):
        from backup_metadata import backup_catalog, restore_catalog, summaries, read_catalog, tree_manifest
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        project_release, old_rows = ScientificRelease.freeze(self)
        project_path = self.path
        # Distinct authored source identity avoids the intentional duplicate-content refusal.
        original_source = self.source
        original_builder = authored_bundle
        from unittest.mock import patch
        with patch(__name__ + '.authored_bundle', side_effect=lambda:original_builder('run-storage-custody')):
            run_release = self.freeze_run()
        run_path = self.path
        rows = [*old_rows,self.row]
        histories = {row['id']:self.workbench.history(row['id']) for row in rows}
        bundles = {row['id']:self.workbench.asset(row['id'])[0] for row in rows}
        self.assertEqual(bundles[old_rows[0]['id']],original_source)
        expected = summaries(read_catalog(self.dataset.db))
        catalog, identity = self.dataset.path,self.dataset.db.dataset_id
        self.dataset.close()
        backup = catalog.parent / 'backup'
        backup_catalog(catalog,backup,quiesced=True)
        backup_files = tree_manifest(backup)
        with psycopg.connect(connection_info(),autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier('catalog_'+identity)))
        restore_catalog(backup,catalog.parent/'restored')
        restored = Dataset(catalog.parent/'restored')
        self.addCleanup(restored.close)
        bind_owner(self,restored)
        self.assertEqual(summaries(read_catalog(restored.db)),expected)
        for row in rows:
            self.assertEqual(restored.workbench.get(row['id']),row)
            self.assertEqual(restored.workbench.history(row['id']),histories[row['id']])
            self.assertEqual(restored.workbench.asset(row['id'])[0],bundles[row['id']])
        captured, receipt = restored.runs.capture_artifact(self.run['id'], 'fields.zip', hashlib.sha256(self.source).hexdigest())
        self.assertEqual(captured, self.source)
        self.assertEqual(receipt, self.row['provenance']['run_source'])
        for path, raw in ((project_path,project_release),(run_path,run_release)):
            saved = restored.path / path.relative_to(catalog)
            self.assertEqual(saved.read_bytes(),raw)
            self.assertEqual(scientific_release.validate_release(saved),scientific_release.validate_bytes(raw))
        self.assertEqual(tree_manifest(backup),backup_files)
