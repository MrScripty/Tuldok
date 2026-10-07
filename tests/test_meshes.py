"""Actual authored ASCII PLY inputs; analytic oracles, no Rheon execution."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import urllib.error
import urllib.request
import zipfile

from PIL import Image
from app import Dataset, make_handler
from caption_import import snapshot, SNAPSHOT_KEYS
from dataset_releases import allocate, connected_components
from immutable_assets import migrate_records
import meshes
import rheon_sequences
from test_sequences import fixture as sequence_fixture, body as sequence_body
import test_sequences
from types import SimpleNamespace
from workbench import Workbench
from workbench import WorkbenchError, encode

FIXTURES = Path(__file__).parent / 'fixtures' / 'meshes'


def fixture(name='tetrahedron', raw=None, change=None):
    geometry = (FIXTURES / (name + '.ply')).read_bytes() if raw is None else raw
    sidecar = json.loads((FIXTURES / (name + '.json')).read_bytes())
    if raw is not None:
        sidecar.update(geometry_bytes=len(geometry), geometry_sha256=hashlib.sha256(geometry).hexdigest())
    if change:
        change(sidecar)
    return geometry, (FIXTURES / (name + '.json')).read_bytes() if raw is None and not change else encode(sidecar).encode()


def body(raw, sidecar, **options):
    return dict(files={'mesh.ply': base64.b64encode(raw).decode(), 'mesh.json': base64.b64encode(sidecar).decode()}, **options)


class Meshes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = Dataset(self.tmp.name); self.addCleanup(lambda: self.d.close()); self.w = self.d.workbench

    def add(self, name='tetrahedron', **options):
        return meshes.admit(self.w, body(*fixture(name), **options))

    def review(self, row, **options):
        request = dict(revision=row['revision'], source_revision=1, task='mesh_geometry',
                       annotation={'note': 'Inspected native geometry and declared units/frame.'}, groups=row['groups'], review='human_reviewed')
        request.update(options); return self.w.save(row['id'], request)

    def selection(self, rows):
        return [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows]

    def state(self):
        return {table: [tuple(row) for row in self.d.db.execute('SELECT * FROM ' + table)]
                for table in ('workbench_mesh_assets', 'workbench_records', 'workbench_history', 'workbench_rights_notes')}

    def test_actual_authored_fixture_raw_native_roundtrip_bounds_normals_review_rights_history_reopen(self):
        row = self.add()
        self.assertEqual((row['kind'], row['task'], row['review'], row['annotation']), ('mesh', 'mesh_geometry', 'draft', None))
        self.assertEqual(row['provenance']['rights'], 'unknown')
        self.assertEqual(row['mesh']['bounds'], {'min': [0., 0., 0.], 'max': [1., 1., 1.]})
        self.assertEqual((row['mesh']['vertex_count'], row['mesh']['triangle_count']), (4, 4))
        raw, sidecar = fixture(); bundle, mime = self.w.asset(row['id']); self.assertEqual(mime, 'application/zip')
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertEqual(archive.namelist(), ['mesh.ply', 'mesh.json'])
            self.assertEqual((archive.read('mesh.ply'), archive.read('mesh.json')), (raw, sidecar))
        normal = self.add('open-surface'); parsed = meshes.prepare(*fixture('open-surface'))
        self.assertEqual(parsed['geometry']['vertices'][0], [0., 0., 0., 0., 0., 2.])
        self.assertEqual(normal['mesh']['properties'][0]['dtype'], 'double')
        self.assertEqual(normal['mesh']['properties'][-1], {'name': 'nz', 'dtype': 'float'})
        self.assertTrue(normal['mesh']['provided_normals'])
        preview = self.w.meshes.inspect(normal['id'])
        self.assertEqual(preview['triangles'], [[[0.,0.,0.],[2.,0.,0.],[2.,2.,0.]], [[0.,0.,0.],[2.,2.,0.],[0.,2.,0.]]])
        reads = []; self.d.db.set_trace_callback(reads.append)
        self.assertEqual(self.w.query({'kind': 'mesh', 'task': 'mesh_geometry'})['total'], 2)
        self.assertFalse(any('SELECT bundle' in sql for sql in reads)); self.d.db.set_trace_callback(None)
        reviewed = self.review(row)
        corrected = self.w.correct_rights_note(row['id'], dict(revision=2, source_revision=1, note='Authored fixture; inspect project terms.'))['record']
        self.assertEqual(corrected['review'], 'human_reviewed'); self.assertEqual(len(self.w.history(row['id'])), 3)
        with self.assertRaisesRegex(WorkbenchError, 'changed'): self.review(row)
        self.d.close(); self.d = Dataset(self.tmp.name); self.w = self.d.workbench
        self.assertEqual(self.w.get(row['id']), corrected); self.assertEqual(self.w.asset(row['id'])[0], bundle)

    def test_float_native_interpretation_and_equivalent_family_keeps_exact_raw(self):
        raw, _ = fixture(); raw = raw.replace(b'1 0 0\n', b'0.1000000015 0 0\n')
        prepared = meshes.prepare(*fixture(raw=raw))
        self.assertEqual(prepared['geometry']['vertices'][1][0], struct.unpack('<f', struct.pack('<f', .1000000015))[0])
        first = self.add()
        raw, sidecar = fixture(raw=fixture()[0].replace(b'0 0 0\n', b'-0.0 0.000 0e4\n'), change=lambda m:m['provenance'].update(revision='other'))
        second = meshes.admit(self.w, body(raw, sidecar))
        self.assertNotEqual(first['groups'][0], second['groups'][0]); self.assertEqual(first['groups'][1], second['groups'][1])
        raw = fixture()[0].replace(b'property float', b'property double')
        third = meshes.admit(self.w, body(*fixture(raw=raw)))
        self.assertEqual(first['groups'][1], third['groups'][1])
        raw = fixture()[0].replace(b'\n', b'\r\n')
        fourth = meshes.admit(self.w, body(*fixture(raw=raw)))
        self.assertEqual(first['groups'][1], fourth['groups'][1])

    def test_malformed_geometry_targeted_rejections_publish_nothing(self):
        original, _ = fixture(); before = self.state()
        cases = [
            (original[:-1], 'final newline'),
            (b'\n'*(meshes.VERTEX_LIMIT+meshes.FACE_LIMIT+meshes.HEADER_LIMIT+1), 'line count cap'),
            (original.replace(b'3 1 2 3\n', b''), 'counts mismatch'),
            (original+b'\n', 'counts mismatch'),
            (original.replace(b'property float x', b'property float y'), 'property axes'),
            (original.replace(b'property float x', b'property int x'), 'property dtype'),
            (original.replace(b'property float z', b'property float z\nproperty float nx'), 'property axes'),
            (original.replace(b'property list uchar int', b'property list uint int'), 'face property'),
            (original.replace(b'0 0 0\n', b'NaN 0 0\n'), 'finite decimal'),
            (original.replace(b'0 0 0\n', b'1e999 0 0\n'), 'magnitude bound'),
            (original.replace(b'0 0 0\n', b'1000000000001 0 0\n'), 'magnitude bound'),
            (original.replace(b'0 0 0\n', b'1e-999 0 0\n'), 'nonzero underflow'),
            (original.replace(b'0 0 0\n', b'1e-50 0 0\n'), 'float vertex scalar has nonzero underflow'),
            (original.replace(b'3 0 2 1', b'3 0 2 4'), 'within vertex count'),
            (original.replace(b'3 0 2 1', b'3 0 2 2'), 'distinct'),
            (original.replace(b'3 0 2 1', b'3 0 2 -1'), 'three integer indices'),
            (original.replace(b'3 0 2 1', b'4 0 2 1 3'), 'three integer indices'),
            (original.replace(b'3 1 2 3', b'3 1 2 0'), 'duplicate unordered face'),
            (original.replace(b'1 0 0\n', b'0 0 0\n'), 'zero representable cross product'),
            (original.replace(b'element vertex 4', b'element vertex 20001'), 'vertex count cap'),
            (original.replace(b'element face 4', b'element face 40001'), 'face count cap'),
            (original.replace(b'0 0 0\n', b'\xff 0 0\n'), 'ASCII'),
            (original.replace(b'0 0 0\n', b'0 0 0\v\n'), 'control characters'),
            (original.replace(b'0 0 0\n', b'0 0 0'+b' '*1024+b'\n'), 'line byte cap'),
            (original.replace(b'end_header\n', b''.join(b'comment '+b'x'*990+b'\n' for _ in range(18))+b'end_header\n'), 'header byte cap'),
        ]
        for raw, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(WorkbenchError, diagnostic) as error: meshes.admit(self.w, body(*fixture(raw=raw)))
                self.assertEqual(error.exception.code, 'invalid'); self.assertEqual(self.state(), before)
        with self.assertRaises(WorkbenchError) as error: meshes.prepare(*fixture(raw=original.replace(b'format ascii 1.0',b'format binary_little_endian 1.0')))
        self.assertEqual(error.exception.code, 'unsupported')

    def test_manifest_envelope_integrity_and_bounds_before_parse(self):
        before = self.state()
        changes = [(lambda m:m.update(geometry_sha256='0'*64), 'SHA256 mismatch'),
            (lambda m:m.update(geometry_sha256='A'*64), 'lowercase hex'),
            (lambda m:m.update(geometry_bytes=True), 'byte count'),
            (lambda m:m.update(geometry_bytes=1), 'byte count'),
            (lambda m:m.update(geometry_file='../mesh.ply'), 'filename'),
            (lambda m:m.update(units='inches'), 'units'),
            (lambda m:m['coordinate_system'].update(up_axis='yz'), 'up axis'),
            (lambda m:m['coordinate_system'].update(handedness='unknown'), 'handedness'),
            (lambda m:m['coordinate_system'].update(axis_order=['y','x','z']), 'coordinate system fields'),
            (lambda m:m['provenance'].update(license=''), 'Declared provenance'),
            (lambda m:m['provenance'].update(source='x'*1001), 'Declared provenance'),
            (lambda m:m.update(extra=1), 'sidecar fields')]
        for change, diagnostic in changes:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(WorkbenchError, diagnostic): meshes.admit(self.w, body(*fixture(change=change)))
                self.assertEqual(self.state(), before)
        raw, sidecar = fixture()
        for malformed, diagnostic in [(sidecar.replace(b'"format":',b'"format":"tuldok_mesh_v1","format":',1),'duplicate'),
            (sidecar.replace(b'"geometry_bytes":',b'"geometry_bytes":NaN,"x":',1),'nonfinite'),(b'\xff','UTF-8'),(b'['*1500,'UTF-8')]:
            with self.assertRaisesRegex(WorkbenchError, diagnostic): meshes.prepare(raw, malformed)
        with self.assertRaisesRegex(WorkbenchError, 'SHA256 mismatch'): meshes.prepare(raw.replace(b'0 0 0',b'bad!!'),sidecar)
        with self.assertRaisesRegex(WorkbenchError, 'PLY byte cap'): meshes.prepare(b'x'*(meshes.PLY_LIMIT+1),sidecar)
        with self.assertRaisesRegex(WorkbenchError, 'sidecar byte cap'): meshes.prepare(raw,b'x'*(meshes.MANIFEST_LIMIT+1))
        for request in ({'directory':'/tmp'},dict(body(raw,sidecar),extra=True),{'files':{'mesh.ply':'???','mesh.json':'???'}}, {'files':{'mesh.ply':'','mesh.json':''}}):
            with self.assertRaises(WorkbenchError): meshes.admit(self.w,request)
        self.assertEqual(self.state(), before)

    def test_atomic_failures_duplicate_invalid_parent_preserve_all_state(self):
        before = self.state()
        for table in ('workbench_mesh_assets','workbench_records','workbench_history'):
            self.d.db.execute(f"CREATE TRIGGER fail BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'controlled failure'); END");self.d.db.commit()
            with self.assertRaises(sqlite3.IntegrityError): self.add()
            self.assertEqual(self.state(),before)
            self.d.db.execute('DROP TRIGGER fail');self.d.db.commit()
        row=self.add();before=self.state()
        with self.assertRaisesRegex(WorkbenchError,'already exists'):self.add()
        with self.assertRaisesRegex(WorkbenchError,'not found'):self.add('open-surface',parents=['0'*32])
        self.assertEqual(self.state(),before);self.assertEqual(self.w.history(row['id']),[row])

    def test_human_review_family_sequence_parent_whole_mixed_release_and_tamper(self):
        seq = rheon_sequences.admit(self.w, sequence_body(*sequence_fixture()))
        mesh = self.add(parents=[seq['id']]); other = self.add('open-surface')
        roots = connected_components(self.w._all()); self.assertEqual(roots[seq['id']],roots[mesh['id']])
        with self.assertRaisesRegex(WorkbenchError,'protected groups'):self.review(mesh,groups=['other'])
        with self.assertRaisesRegex(WorkbenchError,'human review'):self.review(mesh,review='programmatically_verified')
        with self.assertRaisesRegex(WorkbenchError,'human review'):self.w.save(mesh['id'],dict(mesh,annotation={'note':''}),verified_provenance={'method':'verifier'})
        request=dict(items=self.selection([mesh]),ratios=dict(train=100,validation=0,test=0),seed=4)
        self.assertFalse(self.d.releases.preview(request)['eligible'])
        mesh=self.review(mesh);other=self.review(other)
        seq=self.w.save(seq['id'],dict(seq,annotation={'note':'Inspected transport'},review='human_reviewed'))
        text=self.w.import_asset(dict(kind='text',name='Authored classification',text='Static geometry fixture.',groups=['text-fixture']))
        text=self.w.save(text['id'],dict(text,annotation={'label':'fixture'},review='human_reviewed'))
        assigned,report=allocate([mesh,seq,other],self.w._all(),dict(train=50,validation=50,test=0),4)
        self.assertEqual(assigned[mesh['id']],assigned[seq['id']]);self.assertEqual(report['independent_components'],2)
        request['items']=self.selection([mesh,seq,text]);preview=self.d.releases.preview(request);self.assertTrue(preview['eligible'])
        release=self.d.releases.create(dict(request,preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as archive:
            records=json.loads(archive.read('manifest.json'))['records'];self.assertEqual({r['kind'] for r in records},{'mesh','sequence','text'})
            entry=next(r for r in records if r['kind']=='mesh');self.assertEqual(archive.read(entry['asset']),self.w.asset(mesh['id'])[0])
            with zipfile.ZipFile(io.BytesIO(archive.read(entry['asset']))) as asset:
                self.assertEqual((asset.read('mesh.ply'),asset.read('mesh.json')),fixture())
            self.assertEqual(len(archive.read('train/records.jsonl').splitlines()),3)
        imported=self.d.native_text_imports.prepare(dict(source_name='mixed.zip',archive=base64.b64encode(self.d.releases.locate(release['id']).read_bytes()).decode()))
        self.assertEqual(sum('token' in r for r in imported['rows']),1)
        with self.d.db:self.d.db.execute('UPDATE workbench_mesh_assets SET metadata_json=? WHERE id=?',(encode(dict(mesh['mesh'],triangle_count=8)),mesh['id']))
        with self.assertRaisesRegex(WorkbenchError,'metadata changed'):self.w.asset(mesh['id'])
        self.assertFalse(self.d.releases.preview(dict(request,items=self.selection([mesh])))['eligible'])
        frozen=self.d.releases.locate(release['id']).read_bytes();self.assertTrue(frozen.startswith(b'PK'))

    def test_mesh_caption_ancestry_exports_reimports_and_rejects_bad_source_association(self):
        images=[]
        for index,color in enumerate(('red','blue','green')):
            stream=io.BytesIO();Image.new('RGB',(512,512),color).save(stream,'PNG')
            row=self.w.import_asset(dict(kind='image',name=color+'.png',image=base64.b64encode(stream.getvalue()).decode(),groups=['image-'+color]))
            images.append(self.w.save(row['id'],dict(row,task='image_caption',annotation={'caption':'A '+color+' square.'},review='human_reviewed')))
        mesh=self.add(parents=[images[0]['id']])
        request=dict(items=self.selection(images),format='image_caption_v1',ratios=dict(train=34,validation=33,test=33),seed=3)
        preview=self.d.releases.preview(request);self.assertTrue(preview['eligible'])
        release=self.d.releases.create(dict(request,preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as archive:
            manifest=json.loads(archive.read('manifest.json'))
            self.assertIn(mesh['id'],[r['id'] for family in manifest['protected_components'].values() for r in family])
            prepared=self.d.caption_imports.prepare(dict(manifest=archive.read('manifest.json').decode(),metadata={split:archive.read(split+'/metadata.jsonl').decode() for split in ('train','val','test')}))
            self.assertEqual(len(prepared['rows']),3)
            bad={key:mesh[key] for key in SNAPSHOT_KEYS};bad['source_sha256']='0'*64
            with self.assertRaisesRegex(WorkbenchError,'mesh source snapshot'):snapshot(bad)

    def test_reopen_prior_sequence_database_preserves_all_bytes_history_rights_and_indexes(self):
        seq=rheon_sequences.admit(self.w,sequence_body(*sequence_fixture()))
        seq=self.w.save(seq['id'],dict(seq,annotation={'note':'Human transport check'},review='human_reviewed'))
        corrected=self.w.correct_rights_note(seq['id'],dict(revision=2,source_revision=1,note='Declared fixture permission'))['record']
        bundle=self.w.asset(seq['id'])[0];history=self.w.history(seq['id'])
        with self.d.db:
            sql=self.d.db.execute("SELECT sql FROM sqlite_master WHERE name='workbench_records'").fetchone()[0]
            indexes=[r[0] for r in self.d.db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='workbench_records' AND sql IS NOT NULL")]
            self.d.db.execute(sql.replace('workbench_records','previous_records',1).replace("'sequence','mesh'","'sequence'"))
            self.d.db.execute('INSERT INTO previous_records SELECT * FROM workbench_records')
            self.d.db.execute('DROP TABLE workbench_records');self.d.db.execute('ALTER TABLE previous_records RENAME TO workbench_records')
            for statement in indexes:self.d.db.execute(statement)
            self.d.db.execute('DROP TABLE workbench_mesh_assets')
        self.d.close();self.d=Dataset(self.tmp.name);self.w=self.d.workbench
        self.assertEqual(self.w.get(seq['id']),corrected);self.assertEqual(self.w.history(seq['id']),history)
        self.assertEqual(self.w.asset(seq['id'])[0],bundle);self.assertEqual(self.add()['review'],'draft')

    def test_shared_mesh_sequence_saved_release_cap_precedes_blob_reads(self):
        mesh=self.review(self.add());seq=rheon_sequences.admit(self.w,sequence_body(*sequence_fixture()))
        seq=self.w.save(seq['id'],dict(seq,annotation={'note':'Human review'},review='human_reviewed'))
        with self.d.db:
            for table,row in (('workbench_mesh_assets',mesh),('workbench_sequence_assets',seq)):
                self.d.db.execute('UPDATE '+table+' SET bundle_bytes=? WHERE id=?',(21*1024*1024,row['id']))
        items=self.selection([mesh,seq]);request=dict(items=items,ratios=dict(train=100,validation=0,test=0),seed=1)
        with patch.object(self.w,'asset',side_effect=AssertionError('no BLOB reads')):
            self.assertFalse(self.d.releases.preview(request)['eligible'])
            with self.assertRaisesRegex(WorkbenchError,'40 MiB'):self.d.selections.create(dict(name='Over bound',items=items))

    def test_http_real_import_inspection_duplicate_json_and_request_bound(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}/api/workbench/'
        request=urllib.request.Request(base+'mesh-import',json.dumps(body(*fixture())).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:self.assertEqual(response.status,201);row=json.load(response)
        with urllib.request.urlopen(base+'mesh-inspection/'+row['id']) as response:self.assertEqual(json.load(response)['sample_count'],4)
        request=urllib.request.Request(base+'mesh-import',b'{"files":{},"files":{}}',{'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,400);self.assertIn('duplicate',error.exception.read().decode())
        request=urllib.request.Request(base+'mesh-import',b'{}',{'Content-Type':'application/json','Content-Length':str(meshes.MAX_REQUEST+1)})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,400);self.assertEqual(self.w.query({})['total'],1)

    def test_inspection_cap_geometry_bounds_cover_unsampled_faces(self):
        # Authored disjoint triangles, deterministic analytic bounds; no mesh library oracle.
        count=513;lines=['ply','format ascii 1.0',f'element vertex {count*3}','property double x','property double y','property double z',f'element face {count}','property list uchar int vertex_indices','end_header']
        for i in range(count):lines += [f'{i*2} 0 0',f'{i*2+1} 0 0',f'{i*2} 1 0']
        lines += [f'3 {i*3} {i*3+1} {i*3+2}' for i in range(count)]
        row=meshes.admit(self.w,body(*fixture(raw=('\n'.join(lines)+'\n').encode())));preview=self.w.meshes.inspect(row['id'])
        self.assertEqual((preview['sample_count'],preview['triangle_count']),(512,513));self.assertEqual(preview['bounds']['max'],[1025.,1.,0.])
        self.assertEqual(preview['triangles'][-1][1][0],1023.)


class MeshMigration(unittest.TestCase):
    def test_original_and_sequence_schema_rows_indexes_atomic_idempotence_and_setup_rollback(self):
        for old in ("('image','text')","('image','text','sequence')"):
            with self.subTest(old=old):
                db=sqlite3.connect(':memory:');self.addCleanup(db.close);test_sequences.SchemaMigration().legacy(db)
                sql=db.execute("SELECT sql FROM sqlite_master WHERE name='workbench_records'").fetchone()[0]
                if 'sequence' in old:
                    db.execute('ALTER TABLE workbench_records RENAME TO old_records');db.execute(sql.replace("('image','text')",old));db.execute('INSERT INTO workbench_records SELECT * FROM old_records');db.execute('DROP TABLE old_records');db.execute('CREATE INDEX custom_name ON workbench_records(name)');db.commit()
                before=db.execute('SELECT * FROM workbench_records').fetchall();schema=db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()
                db.set_authorizer(lambda action,a,b,*rest:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_DROP_TABLE and a=='workbench_records' else sqlite3.SQLITE_OK)
                with self.assertRaises(sqlite3.DatabaseError):migrate_records(db)
                db.set_authorizer(None);self.assertEqual(db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall(),schema)
                migrate_records(db);migrate_records(db);self.assertEqual(db.execute('SELECT * FROM workbench_records').fetchall(),before)
                self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='custom_name'").fetchone())
        # Existing target schema still verifies columns and migration-time triggers.
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);test_sequences.SchemaMigration().legacy(db);migrate_records(db)
        db.execute('ALTER TABLE workbench_records ADD COLUMN surprise TEXT')
        with self.assertRaisesRegex(WorkbenchError,'columns'):migrate_records(db)
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);test_sequences.SchemaMigration().legacy(db)
        before=db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()
        rows=db.execute('SELECT * FROM workbench_records').fetchall()
        with patch('meshes.MeshAssets',side_effect=RuntimeError('controlled setup failure')):
            with self.assertRaisesRegex(RuntimeError,'controlled setup failure'):
                Workbench(SimpleNamespace(db=db,lock=threading.RLock()))
        self.assertEqual(db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall(),before)
        self.assertEqual(db.execute('SELECT * FROM workbench_records').fetchall(),rows)
