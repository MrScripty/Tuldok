"""Authored actual vertex-only PLY inputs; no scanned assets, simulation or models."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
import urllib.request
import urllib.error
import unittest
import zipfile

from app import Dataset, make_handler
from immutable_assets import migrate_records
from workbench import Workbench
import test_sequences
from caption_import import snapshot, SNAPSHOT_KEYS
from dataset_releases import connected_components
from native_sequence_dataset import source_identity
from workbench import WorkbenchError, encode
import meshes
import pointclouds
from test_meshes import fixture as mesh_fixture, body as mesh_body

FIXTURES = Path(__file__).parent / 'fixtures' / 'pointclouds'


def fixture(name='colored', raw=None, change=None):
    geometry = (FIXTURES / (name + '.ply')).read_bytes() if raw is None else raw
    sidecar = json.loads((FIXTURES / (name + '.json')).read_bytes())
    if raw is not None:
        sidecar.update(geometry_bytes=len(geometry), geometry_sha256=hashlib.sha256(geometry).hexdigest())
    if change:
        change(sidecar)
    return geometry, (FIXTURES / (name + '.json')).read_bytes() if raw is None and not change else encode(sidecar).encode()


def body(raw, sidecar, **options):
    return dict(files={'points.ply': base64.b64encode(raw).decode(), 'points.json': base64.b64encode(sidecar).decode()}, **options)


def review(w, row, **options):
    request = dict(revision=row['revision'], source_revision=1, task='pointcloud_geometry',
                   annotation={'note': 'QA authored points inspected; not training qualification.'}, groups=row['groups'], review='human_reviewed')
    request.update(options)
    return w.save(row['id'], request)


def selection(rows):
    return [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows]


class PointClouds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = Dataset(self.tmp.name); self.addCleanup(lambda: self.d.close()); self.w = self.d.workbench

    def add(self, name='colored', **options):
        return pointclouds.admit(self.w, body(*fixture(name), **options))

    def state(self):
        return {table: [tuple(row) for row in self.d.db.execute('SELECT * FROM ' + table)]
                for table in ('workbench_pointcloud_assets', 'workbench_records', 'workbench_history', 'workbench_rights_notes')}

    def test_actual_raw_native_attributes_signedzero_metadata_review_rights_history_reopen(self):
        row = self.add(); raw, sidecar = fixture()
        self.assertEqual((row['kind'], row['task'], row['review'], row['annotation']), ('pointcloud', 'pointcloud_geometry', 'draft', None))
        self.assertEqual(row['provenance']['rights'], 'unknown'); self.assertEqual(row['source_split'], 'train')
        self.assertEqual(row['provenance']['lineage'], row['pointcloud']['manifest']['lineage'])
        self.assertEqual(len(row['pointcloud']['protected_groups']), 4)
        self.assertEqual(row['pointcloud']['bounds'], {'min': [-0., 0., 0.], 'max': [2., 2., 3.]})
        geometry = pointclouds.prepare(raw, sidecar)['geometry']
        self.assertEqual(struct.pack('<f', geometry['points'][0][0]), b'\x00\x00\x00\x80')
        self.assertEqual(geometry['points'][3][3:], [0., 0., 2., 127, 128, 255])
        self.assertEqual(geometry['properties'][1], {'name': 'y', 'dtype': 'double'})
        bundle, mime = self.w.asset(row['id']); self.assertEqual(mime, 'application/zip')
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertEqual(archive.namelist(), ['points.ply', 'points.json'])
            self.assertEqual((archive.read('points.ply'), archive.read('points.json')), (raw, sidecar))
        row = review(self.w, row, review='draft'); row = self.w.get(row['id']); self.assertEqual(row['review'], 'draft')
        row = review(self.w, row)
        row = self.w.correct_rights_note(row['id'], dict(revision=3, source_revision=1, note='QA rights note; original declaration retained.'))['record']
        self.assertEqual(len(self.w.history(row['id'])), 4)
        self.assertEqual(row['pointcloud']['manifest']['lineage']['split'], 'train')
        self.d.close(); self.d = Dataset(self.tmp.name); self.w = self.d.workbench
        self.assertEqual(self.w.get(row['id']), row); self.assertEqual(self.w.asset(row['id'])[0], bundle)

    def test_float32_midpoint_neighbors_rejected_atomically_ties_accepted_legacy_mesh_unchanged(self):
        raw, _ = fixture(); before = self.state()
        for token in ('1.0000000596046448', '1.0000001788139343', '-1.0000000596046448', '-1.0000001788139343'):
            altered = raw.replace(b'1 2 0 ', token.encode() + b' 2 0 ')
            with self.assertRaisesRegex(WorkbenchError, 'incompatible with the pinned parser'):
                pointclouds.admit(self.w, body(*fixture(raw=altered)))
            self.assertEqual(self.state(), before)
            mesh = mesh_fixture(raw=mesh_fixture()[0].replace(b'1 0 0\n', token.encode() + b' 0 0\n'))
            self.assertEqual(struct.unpack('<I', struct.pack('<f', meshes.prepare(*mesh)['geometry']['vertices'][1][0]))[0],
                             0xbf800001 if token.startswith('-') else 0x3f800001)
        for token, bits in [('1.000000059604644775390625', 0x3f800000), ('1.000000178813934326171875', 0x3f800002), ('-1.000000059604644775390625', 0xbf800000), ('-1.000000178813934326171875', 0xbf800002),
                            ('1.401298464324817070923729583289916131280e-45', 1)]:
            value = pointclouds.scalar(token, 'float')
            self.assertEqual(struct.unpack('<I', struct.pack('<f', value))[0], bits)
        # Every floating attribute uses the same compatibility policy, not only XYZ.
        altered = raw.replace(b'0 0 2 255', b'1.0000000596046448 0 2 255')
        with self.assertRaisesRegex(WorkbenchError, 'incompatible'): pointclouds.prepare(*fixture(raw=altered))

    def test_malformed_geometry_integrity_counts_axes_attributes_before_publication(self):
        raw, sidecar = fixture(); before = self.state()
        cases = [(raw[:-1], 'final newline'), (raw+b'\n', 'counts mismatch'),
            (raw.replace(b'element vertex 4', b'element vertex 20001'), 'point count cap'),
            (raw.replace(b'property float x', b'property float y'), 'property axes'),
            (raw.replace(b'property uchar red', b'property float red'), 'property dtype'),
            (raw.replace(b'property double ny\n', b''), 'property axes'),
            (raw.replace(b'property uchar blue\n', b''), 'property axes'),
            (raw.replace(b'end_header', b'element face 0\nproperty list uchar int vertex_indices\nend_header'), 'no faces'),
            (raw.replace(b'255 0 0', b'256 0 0'), 'RGB scalar'), (raw.replace(b'255 0 0', b'-1 0 0'), 'RGB scalar'),
            (raw.replace(b'255 0 0', b'0.5 0 0'), 'RGB scalar'),
            (raw.replace(b'1 2 0 ', b'NaN 2 0 '), 'finite decimal'),
            (raw.replace(b'1 2 0 ', b'1e999 2 0 '), 'magnitude bound'),
            (raw.replace(b'1 2 0 ', b'1e-50 2 0 '), 'nonzero underflow'),
            (raw.replace(b'1 2 0 ', b'1 2\x00 0 '), 'control characters'),
            (raw.replace(b'1 2 0 ', b'\xff 2 0 '), 'ASCII'),
            (raw.replace(b'1 2 0 ', b'1'+b' '*1025+b'2 0 '), 'line byte cap'),
            (raw.replace(b'end_header', b''.join(b'comment '+b'a'*980+b'\n' for _ in range(18))+b'end_header'), 'header byte cap')]
        for altered, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(WorkbenchError, diagnostic): pointclouds.admit(self.w, body(*fixture(raw=altered)))
                self.assertEqual(self.state(), before)
        with self.assertRaisesRegex(WorkbenchError, 'SHA256 mismatch'): pointclouds.admit(self.w, body(raw.replace(b'1 2 0 ', b'bad!!!'), sidecar))
        with self.assertRaisesRegex(WorkbenchError, 'PLY byte cap'): pointclouds.prepare(b'x'*(pointclouds.PLY_LIMIT+1), sidecar)

    def test_sidecar_lineage_dtype_units_axes_hash_bounds_and_envelope(self):
        before = self.state()
        cases = [(lambda m:m.update(geometry_sha256='0'*64), 'SHA256 mismatch'),
            (lambda m:m.update(geometry_bytes=True), 'byte count'),
            (lambda m:m.update(units='inches'), 'units'),
            (lambda m:m['coordinate_system'].update(up_axis='yz'), 'up axis'),
            (lambda m:m['lineage'].update(split='val'), 'lineage split'),
            (lambda m:m['lineage'].update(source_id=' source '), 'canonical'),
            (lambda m:m['lineage'].update(namespace='n'*121), 'Lineage namespace'),
            (lambda m:m['lineage'].update(family_id=''), 'Lineage family_id'),
            (lambda m:m['lineage'].update(extra='x'), 'lineage fields')]
        for change, diagnostic in cases:
            with self.assertRaisesRegex(WorkbenchError, diagnostic): pointclouds.admit(self.w, body(*fixture(change=change)))
            self.assertEqual(self.state(), before)
        raw, sidecar = fixture()
        for altered in (sidecar.replace(b'"format":', b'"format":"x","format":', 1), b'\xff', b'{"a":NaN}'):
            with self.assertRaises(WorkbenchError): pointclouds.prepare(raw, altered)
        for request in ({'directory':'/tmp'}, {'files':{'points.ply':'???','points.json':'???'}}, body(raw, sidecar, groups=['g']*27)):
            with self.assertRaises(WorkbenchError): pointclouds.admit(self.w, request)
        row = pointclouds.admit(self.w, body(raw, sidecar, groups=['g'+str(i) for i in range(26)])); self.assertEqual(len(row['groups']),30)
        with self.assertRaisesRegex(WorkbenchError,'26'): pointclouds.admit(self.w, body(*fixture('xyz'), groups=['g'+str(i) for i in range(27)]))

    def test_atomic_failures_duplicate_invalid_parent_preserve_all_tables(self):
        before = self.state()
        for table in ('workbench_pointcloud_assets','workbench_records','workbench_history'):
            self.d.db.execute('CREATE TRIGGER fail BEFORE INSERT ON '+table+" BEGIN SELECT RAISE(ABORT,'controlled failure'); END"); self.d.db.commit()
            with self.assertRaises(sqlite3.IntegrityError): self.add()
            self.assertEqual(self.state(),before);self.d.db.execute('DROP TRIGGER fail');self.d.db.commit()
        row=self.add();before=self.state()
        with self.assertRaisesRegex(WorkbenchError,'already exists'):self.add()
        with self.assertRaisesRegex(WorkbenchError,'not found'):self.add('xyz',parents=['0'*32])
        self.assertEqual(self.state(),before)

    def test_human_review_cannot_bypass_note_groups_or_owned_verifier(self):
        row=self.add()
        for options in ({'annotation':{'note':''}}, {'annotation':{'note':' \n '}}, {'groups':[]}, {'review':'programmatically_verified'}):
            with self.assertRaises(WorkbenchError):review(self.w,row,**options)
        with self.assertRaisesRegex(WorkbenchError,'human review'):
            self.w.save(row['id'],dict(row,annotation={'note':'x'},review='human_reviewed'),verified_provenance={'method':'unrelated verifier'})
        request=dict(items=selection([row]),ratios=dict(train=100,validation=0,test=0),seed=4)
        self.assertFalse(self.d.releases.preview(request)['eligible'])

    def test_native_family_ignores_attributes_and_zero_lexemes_declared_identity_is_structured(self):
        raw, _ = fixture(); first=self.add()
        altered=raw.replace(b'-0.0 0 0 ',b'0 0 0 ').replace(b'255 0 0',b'254 0 0')
        second=pointclouds.admit(self.w,body(*fixture(raw=altered,change=lambda m:m['lineage'].update(source_id='other-scan'))))
        native=lambda r:next(g for g in r['groups'] if g.startswith('pointcloud-native:'))
        self.assertEqual(native(first),native(second));self.assertNotEqual(first['content_hash'],second['content_hash'])
        a=pointclouds.prepare(*fixture(change=lambda m:m['lineage'].update(namespace='a:b',family_id='c')))
        b=pointclouds.prepare(*fixture(change=lambda m:m['lineage'].update(namespace='a',family_id='b:c')))
        self.assertNotEqual(a['metadata']['protected_groups'][-1],b['metadata']['protected_groups'][-1])

    def test_whole_family_fixed_splits_second_owner_exact_raw_and_new_drafts(self):
        first=review(self.w,self.add()); second=review(self.w,self.add('xyz'))
        raw,sidecar=fixture(change=lambda m:m['provenance'].update(revision='attribute-proof'))
        variant=review(self.w,pointclouds.admit(self.w,body(raw,sidecar)))
        request=dict(items=selection([first,second,variant]),ratios=dict(train=50,validation=50,test=0),seed=8)
        preview=self.d.releases.preview(request);self.assertTrue(preview['eligible']);self.assertEqual(preview['assignments'][first['id']],preview['assignments'][variant['id']])
        frozen=self.d.releases.create(dict(request,preview_token=preview['preview_token']))
        original=self.d.releases.locate(frozen['id']).read_bytes()
        with tempfile.TemporaryDirectory() as target:
            other=Dataset(target)
            try:
                transferred=[]
                with zipfile.ZipFile(io.BytesIO(original)) as archive:
                    manifest=json.loads(archive.read('manifest.json'))
                    for record in manifest['records']:
                        with zipfile.ZipFile(io.BytesIO(archive.read(record['asset']))) as pair:
                            admitted=pointclouds.admit(other.workbench,body(pair.read('points.ply'),pair.read('points.json')))
                            self.assertEqual(admitted['review'],'draft');self.assertEqual(admitted['provenance']['rights'],'unknown')
                            self.assertNotEqual(admitted['id'],record['id']);self.assertEqual(admitted['source_split'],record['split'])
                            self.assertEqual(admitted['pointcloud'],record['pointcloud'])
                            self.assertEqual(other.workbench.asset(admitted['id'])[0],archive.read(record['asset']))
                            transferred.append(admitted)
                self.assertFalse(other.releases.preview(dict(request,items=selection(transferred)))['eligible'])
            finally:other.close()
        edited=review(self.w,first,review='draft');self.assertEqual(edited['review'],'draft')
        self.assertEqual(self.d.releases.locate(frozen['id']).read_bytes(),original)
        self.assertFalse(self.d.releases.preview(request)['eligible'])

    def test_source_and_family_fixed_conflicts_and_unselected_bridge_refuse_export(self):
        first=review(self.w,self.add());other=review(self.w,self.add('xyz'))
        # Same declared source, new family and geometry: protected origin still joins.
        raw,sidecar=fixture('xyz',change=lambda m:m['lineage'].update(source_id='colored-scan',family_id='changed-family'))
        conflict=pointclouds.admit(self.w,body(raw,sidecar))
        roots=connected_components(self.w._all());self.assertEqual(roots[first['id']],roots[conflict['id']])
        request=dict(items=selection([first,other]),ratios=dict(train=50,validation=50,test=0),seed=4)
        self.assertFalse(self.d.releases.preview(request)['eligible'])

    def test_missing_point_metadata_bridge_cannot_forget_fixed_split(self):
        cloud=self.add();mesh=meshes.admit(self.w,mesh_body(*mesh_fixture(),parents=[cloud['id']]))
        mesh=self.w.save(mesh['id'],dict(mesh,annotation={'note':'QA'},review='human_reviewed'))
        with self.d.db:self.d.db.execute('DELETE FROM workbench_pointcloud_assets WHERE id=?',(cloud['id'],))
        self.assertFalse(self.w.get(cloud['id'])['source_lineage_known'])
        request=dict(items=selection([mesh]),ratios=dict(train=100,validation=0,test=0),seed=4)
        self.assertFalse(self.d.releases.preview(request)['eligible'])

    def test_snapshot_consumers_accept_point_fixed_split_ancestry(self):
        row=self.add();member={key:row[key] for key in SNAPSHOT_KEYS}
        snapshot(member);source_identity(member)
        mesh=meshes.admit(self.w,mesh_body(*mesh_fixture(),parents=[row['id']]))
        mesh=self.w.save(mesh['id'],dict(mesh,annotation={'note':'QA'},review='human_reviewed'))
        request=dict(items=selection([mesh]),ratios=dict(train=100,validation=0,test=0),seed=4)
        preview=self.d.releases.preview(request);self.assertTrue(preview['eligible'])
        self.assertEqual(preview['assignments'][mesh['id']],'train')

    def test_inspection_cap_all_bounds_and_shared_budget_precedes_blob_reads(self):
        raw=(b'ply\nformat ascii 1.0\nelement vertex 513\nproperty double x\nproperty double y\nproperty double z\nend_header\n'+b'0 0 0\n'*512+b'99 1 2\n')
        row=pointclouds.admit(self.w,body(*fixture(raw=raw)))
        preview=self.w.pointclouds.inspect(row['id']);self.assertEqual(preview['sample_count'],512)
        self.assertEqual(len(preview['points']),512);self.assertEqual(preview['bounds']['max'],[99.,1.,2.])
        row=review(self.w,row)
        with self.d.db:self.d.db.execute('UPDATE workbench_pointcloud_assets SET bundle_bytes=? WHERE id=?',(40*1024*1024+1,row['id']))
        statements=[];self.d.db.set_trace_callback(statements.append)
        request=dict(items=selection([row]),ratios=dict(train=100,validation=0,test=0),seed=4)
        self.assertFalse(self.d.releases.preview(request)['eligible']);self.d.db.set_trace_callback(None)
        self.assertFalse(any('SELECT bundle,' in q for q in statements))

    def test_asset_metadata_tamper_refuses_raw_and_release(self):
        row=review(self.w,self.add());metadata=dict(row['pointcloud'],point_count=9);metadata.pop('bundle_bytes')
        with self.d.db:self.d.db.execute('UPDATE workbench_pointcloud_assets SET metadata_json=? WHERE id=?',(encode(metadata),row['id']))
        with self.assertRaisesRegex(WorkbenchError,'metadata changed'):self.w.asset(row['id'])
        request=dict(items=selection([row]),ratios=dict(train=100,validation=0,test=0),seed=4)
        self.assertFalse(self.d.releases.preview(request)['eligible'])


    def test_http_actual_routes_duplicate_json_wrong_kind_and_request_limit(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}/api/workbench/'
        request=urllib.request.Request(base+'pointcloud-import',json.dumps(body(*fixture())).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:self.assertEqual(response.status,201);row=json.load(response)
        with urllib.request.urlopen(base+'pointcloud-inspection/'+row['id']) as response:self.assertEqual(json.load(response)['sample_count'],4)
        mesh=meshes.admit(self.w,mesh_body(*mesh_fixture()))
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'pointcloud-inspection/'+mesh['id'])
        self.assertEqual(error.exception.code,400);error.exception.read();error.exception.close()
        for payload in (b'{"files":{},"files":{}}',b'{"bad":NaN}'):
            request=urllib.request.Request(base+'pointcloud-import',payload,{'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,400);error.exception.read();error.exception.close()
        request=urllib.request.Request(base+'pointcloud-import',b'{}',{'Content-Type':'application/json','Content-Length':str(pointclouds.MAX_REQUEST+1)})
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
        self.assertEqual(error.exception.code,400);self.assertIn('too large',error.exception.read().decode());error.exception.close()

    def test_prior_mesh_schema_setup_migrates_atomically_and_preserves_custom_indexes(self):
        db=sqlite3.connect(':memory:');self.addCleanup(db.close);test_sequences.SchemaMigration().legacy(db)
        sql=db.execute("SELECT sql FROM sqlite_master WHERE name='workbench_records'").fetchone()[0]
        db.execute('ALTER TABLE workbench_records RENAME TO old_records')
        db.execute(sql.replace("('image','text')","('image','text','sequence','mesh')"))
        db.execute('INSERT INTO workbench_records SELECT * FROM old_records');db.execute('DROP TABLE old_records')
        db.execute('CREATE INDEX custom_name ON workbench_records(name)');db.commit()
        schema=db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall();rows=db.execute('SELECT * FROM workbench_records').fetchall()
        with patch('pointclouds.PointCloudAssets',side_effect=RuntimeError('controlled point setup failure')):
            with self.assertRaisesRegex(RuntimeError,'controlled point setup failure'):Workbench(SimpleNamespace(db=db,lock=threading.RLock()))
        self.assertEqual(db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall(),schema)
        self.assertEqual(db.execute('SELECT * FROM workbench_records').fetchall(),rows)
        migrate_records(db);migrate_records(db)
        self.assertEqual(db.execute('SELECT * FROM workbench_records').fetchall(),rows)
        self.assertTrue(db.execute("SELECT 1 FROM sqlite_master WHERE name='custom_name'").fetchone())

    def test_unassigned_raw_pair_does_not_transfer_allocated_split_or_local_lineage(self):
        rows=[pointclouds.admit(self.w,body(*fixture(name,change=lambda m:m['lineage'].update(split='unassigned')),groups=['local-'+name])) for name in ('colored','xyz')]
        rows=[review(self.w,row) for row in rows]
        request=dict(items=selection(rows),ratios=dict(train=50,validation=50,test=0),seed=2)
        preview=self.d.releases.preview(request);self.assertTrue(preview['eligible'])
        frozen=self.d.releases.create(dict(request,preview_token=preview['preview_token']))
        with tempfile.TemporaryDirectory() as target:
            other=Dataset(target)
            try:
                with zipfile.ZipFile(self.d.releases.locate(frozen['id'])) as archive:
                    for original in json.loads(archive.read('manifest.json'))['records']:
                        self.assertIn(original['split'],('train','validation'))
                        with zipfile.ZipFile(io.BytesIO(archive.read(original['asset']))) as pair:
                            row=pointclouds.admit(other.workbench,body(pair.read('points.ply'),pair.read('points.json')))
                        self.assertEqual(row['source_split'],'unassigned');self.assertEqual(row['review'],'draft')
                        self.assertEqual(row['parents'],[]);self.assertEqual(row['annotation'],None)
                        self.assertFalse(any(group.startswith('local-') for group in row['groups']))
            finally:other.close()
