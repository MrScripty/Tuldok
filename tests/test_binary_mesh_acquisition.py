"""Source-bound actual representative and authored refusal/atomicity controls."""
import base64
import copy
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from app import Dataset
import binary_mesh_assets as assets
import binary_mesh_core as core
import meshes
from tests.fixtures.binary_mesh_fixture import packets
from workbench import WorkbenchError, encode


def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:return {name:archive.read(name) for name in archive.namelist()}


def repack(files,rehash=True):
    files=dict(files)
    if rehash:
        side=json.loads(files['mesh.json']);side.update(geometry_bytes=len(files['mesh.ply']),geometry_sha256=core.sha(files['mesh.ply']))
        for name in side['source']['files']:side['source']['files'][name]=core.descriptor(files[name])
        files['mesh.json']=encode(side).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_STORED) as archive:
        for name,raw in files.items():archive.writestr(zipfile.ZipInfo(name),raw)
    return stream.getvalue()


def upload(workbench,raw,**options):
    owner=assets.manager(workbench);start=owner.start(dict(bytes=len(raw),sha256=core.sha(raw),**options))
    for offset in range(0,len(raw),assets.CHUNK_BYTES):owner.chunk({'token':start['token'],'offset':offset,'data':base64.b64encode(raw[offset:offset+assets.CHUNK_BYTES]).decode()})
    return owner.finish({'token':start['token']})


class BinaryMeshAcquisition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.small,cls.actual=[raw for _,raw in packets()]

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Dataset(self.tmp.name);self.addCleanup(lambda:self.d.close());self.w=self.d.workbench

    def state(self):
        return {table:[tuple(row) for row in self.d.db.execute('SELECT * FROM '+table)]
            for table in ('workbench_mesh_assets','workbench_records','workbench_history','workbench_rights_notes')}

    def review(self,row):
        return self.w.save(row['id'],dict(revision=row['revision'],source_revision=1,task='mesh_geometry',
            annotation={'note':'Inspected complete source-bound artistic geometry.'},groups=row['groups'],review='human_reviewed'))

    def test_actual_bound_whole_mesh_draft_rights_review_family_freeze_and_reopen(self):
        row=upload(self.w,self.actual,name='Actual fresh neutral bind')
        self.assertEqual((row['review'],row['annotation'],row['source_split']),('draft',None,'unassigned'))
        self.assertEqual(row['provenance']['rights'],'unknown')
        self.assertEqual((row['mesh']['vertex_count'],row['mesh']['triangle_count']),(46728,93452))
        self.assertEqual(row['mesh']['topology_dtype'],'<u4')
        self.assertEqual(self.w.asset(row['id'])[0],self.actual)
        preview=self.w.meshes.inspect(row['id']);self.assertEqual(preview['sample_count'],512)
        self.assertEqual(preview['coordinate_system'],{'frame':'character-local','handedness':'right','up_axis':'y'})
        request={'items':[{'id':row['id'],'revision':1,'source_revision':1}],'ratios':{'train':100,'validation':0,'test':0},'seed':1}
        self.assertFalse(self.d.releases.preview(request)['eligible'])
        row=self.review(row)
        row=self.w.correct_rights_note(row['id'],{'revision':row['revision'],'source_revision':1,'note':'Declared Apache2.0 artistic source, independently inspected.'})['record']
        request['items'][0]['revision']=row['revision'];preview=self.d.releases.preview(request);self.assertTrue(preview['eligible'])
        release=self.d.releases.create(dict(request,preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as archive:
            manifest=json.loads(archive.read('manifest.json'));self.assertIn('protected_components',manifest)
            self.assertEqual(archive.read(manifest['records'][0]['asset']),self.actual)
        self.d.close();self.d=Dataset(self.tmp.name);self.w=self.d.workbench
        self.assertEqual(self.w.get(row['id']),row);self.assertEqual(len(self.w.history(row['id'])),3)

    def test_existing_limits_original_consumer_dispatch_and_unavailable_source_preserved(self):
        self.assertEqual((meshes.VERTEX_LIMIT,meshes.FACE_LIMIT,meshes.PLY_LIMIT,meshes.MAX_REQUEST),(20000,40000,2097152,3145728))
        files=members(self.small)
        with zipfile.ZipFile(io.BytesIO(files['source.zip'])) as archive:
            body={'files':{name:base64.b64encode(archive.read(name)).decode() for name in archive.namelist()}}
        original=meshes.admit(self.w,body);binary=upload(self.w,self.small)
        self.assertEqual(original['groups'][0:2],binary['groups'][0:2]);self.assertEqual(binary['mesh']['topology_dtype'],'<i4')
        self.assertEqual(self.w.asset(original['id'])[0],files['source.zip'])
        self.d.db.execute('DELETE FROM workbench_mesh_assets WHERE id=?',(original['id'],));self.d.db.commit()
        unavailable=self.w.get(original['id']);self.assertIsNone(unavailable['mesh'])
        with self.assertRaises(WorkbenchError) as error:self.w.meshes.asset(unavailable)
        self.assertEqual((error.exception.code,error.exception.status),('unavailable',404))

    def test_global_upload_budget_offsets_cancel_expiry_and_close(self):
        owner=assets.manager(self.w);before=self.state();start=owner.start({'bytes':len(self.small),'sha256':core.sha(self.small)})
        path=owner.session['path']
        other=Dataset(Path(self.tmp.name)/'second');self.addCleanup(other.close)
        with self.assertRaisesRegex(WorkbenchError,'budget is busy'):assets.manager(other.workbench).start({'bytes':1,'sha256':'0'*64})
        with self.assertRaises(core.BinaryMeshError):owner.chunk({'token':start['token'],'offset':1,'data':'YQ=='})
        self.assertFalse(path.exists());self.assertIsNone(owner.session);self.assertEqual(self.state(),before)
        start=owner.start({'bytes':1,'sha256':'0'*64});path=owner.session['path'];owner.cancel({'token':start['token']});self.assertFalse(path.exists())
        start=owner.start({'bytes':1,'sha256':'0'*64});path=owner.session['path'];owner.session['started']-=601
        with self.assertRaises(WorkbenchError) as error:owner.finish({'token':start['token']})
        self.assertEqual(error.exception.status,404);self.assertFalse(path.exists())
        start=owner.start({'bytes':1,'sha256':'0'*64});path=owner.session['path'];assets.close(self.w);self.assertFalse(path.exists())

    def test_bad_hash_truncated_upload_worker_failure_or_transaction_publish_nothing(self):
        owner=assets.manager(self.w);before=self.state()
        for raw,expected in ((self.small,'0'*64),(self.small[:-1],core.sha(self.small[:-1]))):
            start=owner.start({'bytes':len(raw),'sha256':expected})
            for offset in range(0,len(raw),65536):owner.chunk({'token':start['token'],'offset':offset,'data':base64.b64encode(raw[offset:offset+65536]).decode()})
            with self.assertRaises((WorkbenchError,core.BinaryMeshError)):owner.finish({'token':start['token']})
            self.assertIsNone(owner.session);self.assertEqual(self.state(),before)
        with patch('binary_mesh_assets.validate_path',side_effect=WorkbenchError('controlled worker failure')):
            with self.assertRaisesRegex(WorkbenchError,'worker failure'):upload(self.w,self.small)
        self.assertEqual(self.state(),before)
        with patch.object(self.w,'_history',side_effect=RuntimeError('controlled history failure')):
            with self.assertRaisesRegex(RuntimeError,'history failure'):upload(self.w,self.small)
        self.assertEqual(self.state(),before);self.assertIsNone(owner.session)

    def test_source_family_variant_and_whole_family_splits_no_vertex_samples(self):
        first=upload(self.w,self.small)
        files=members(self.small);files['mesh.ply']=files['mesh.ply'].replace(b'format binary_little_endian 1.0\n',b'format binary_little_endian 1.0\ncomment transport variant\n')
        second=upload(self.w,repack(files));self.assertNotEqual(first['content_hash'],second['content_hash'])
        self.assertTrue(set(first['groups'][:2])<=set(second['groups']))
        rows=[self.review(row) for row in (first,second)]
        request={'items':[{'id':r['id'],'revision':r['revision'],'source_revision':1} for r in rows],
            'ratios':{'train':50,'validation':50,'test':0},'seed':2}
        preview=self.d.releases.preview(request);self.assertFalse(preview['eligible'])
        self.assertTrue(any('Too few independent' in item['message'] for item in preview['blockers']))
        request['ratios']={'train':100,'validation':0,'test':0};preview=self.d.releases.preview(request)
        self.assertTrue(preview['eligible']);self.assertEqual(preview['split_report']['independent_components'],1)
        self.assertEqual(len(set(preview['assignments'].values())),1)

    def test_owned_restart_staging_recovery_preserves_active_or_foreign_data(self):
        script='from binary_mesh_assets import Stage; import sys,os; s=Stage(sys.argv[1]); s.path.write_bytes(b"stale"); os._exit(0)'
        subprocess.run([sys.executable,'-c',script,self.tmp.name],check=True,timeout=10)
        root=Path(self.tmp.name)/'.tuldok-binary-mesh-staging-v1';stale=[p for p in root.iterdir() if p.name.startswith('upload-')]
        self.assertEqual(len(stale),1)
        stage=assets.Stage(self.tmp.name);self.assertFalse(stale[0].exists())
        with self.assertRaisesRegex(WorkbenchError,'Another process owns'):assets.Stage(self.tmp.name)
        stage.cleanup();foreign=root/'foreign.txt';foreign.write_text('Keep this file')
        with self.assertRaisesRegex(WorkbenchError,'unexpected staging entry'):assets.Stage(self.tmp.name)
        self.assertEqual(foreign.read_text(),'Keep this file');foreign.unlink()
        import os
        alias=Path(self.tmp.name)/'foreign-lock';os.link(root/'lock',alias)
        with self.assertRaisesRegex(WorkbenchError,'private regular file'):assets.Stage(self.tmp.name)
        self.assertTrue(alias.exists());alias.unlink()
        (root/'lock').unlink();os.mkfifo(root/'lock')
        with self.assertRaisesRegex(WorkbenchError,'private regular file'):assets.Stage(self.tmp.name)
        (root/'lock').unlink()

    def test_binary_layout_native_hash_topology_refusals(self):
        original=members(self.small);before=self.state()
        parsed=core.parse_ply(original['mesh.ply']);offset=parsed['offset']
        variants=[]
        for mutate in (lambda b:b.replace(b'property float x',b'property float y'),
            lambda b:b.replace(b'property list uchar int',b'property list uchar uint'),lambda b:b[:-1],lambda b:b+b'X',
            lambda b:b.replace(b'element vertex 3',b'element vertex 50001'),
            lambda b:b.replace(b'element face 1',b'element face 100001')):
            files=dict(original);files['mesh.ply']=mutate(files['mesh.ply']);variants.append(repack(files))
        for value in (float('nan'),float('inf'),1e13):
            files=dict(original);binary=bytearray(files['mesh.ply']);struct.pack_into('<f',binary,offset,value);files['mesh.ply']=bytes(binary);variants.append(repack(files))
        files=dict(original);binary=bytearray(files['mesh.ply']);struct.pack_into('<f',binary,offset,1.0);files['mesh.ply']=bytes(binary);variants.append(repack(files))
        files=dict(original);side=json.loads(files['mesh.json']);side['geometry_sha256']='0'*64;files['mesh.json']=encode(side).encode();variants.append(repack(files,False))
        for raw in variants:
            with self.subTest(hash=core.sha(raw)):
                with self.assertRaises(WorkbenchError):upload(self.w,raw)
                self.assertEqual(self.state(),before)

    def test_archive_preflight_single_disk_counts_modes_and_local_associations(self):
        for offset,fmt,value in ((len(self.small)-18,'<H',1),(len(self.small)-12,'<H',99)):
            raw=bytearray(self.small);struct.pack_into(fmt,raw,offset,value)
            with self.assertRaises(core.BinaryMeshError):core.validate_bundle(bytes(raw))
        files=members(self.small);raw=repack(files);start=struct.unpack_from('<I',raw,len(raw)-6)[0]
        for change_offset,fmt,value in ((start+34,'<H',1),(start+38,'<I',0o040777<<16),(start+6,'<H',45),(0+8,'<H',8)):
            bad=bytearray(raw);struct.pack_into(fmt,bad,change_offset,value)
            with self.assertRaises(core.BinaryMeshError):core.validate_bundle(bytes(bad))
        with self.assertRaises(core.BinaryMeshError):core.validate_bundle(self.small+b'trailing')

    def test_exact_decimal_signed_zero_and_closed_source_json(self):
        value=core.strict_json(b'1.0000000596046448',100)
        self.assertEqual(struct.unpack('<I',struct.pack('<f',core.f32(value)))[0],0x3f800001)
        value=core.strict_json(b'-0.0',100);self.assertEqual(struct.pack('<f',core.f32(value)),b'\0\0\0\x80')
        for raw in (b'-0',b'{"a":1,"a":2}',b'NaN',b'1e-999',b'['*65+b'0'+b']'*65,b'"\\ud800"'):
            with self.assertRaises(core.BinaryMeshError):core.strict_json(raw,1000)

    def test_source_manifest_bool_version_wrong_wasm_frame_and_response_mismatch(self):
        originals=members(self.actual)
        variants=[]
        for mutate in (lambda p:p.update(fixture_version=True),lambda p:p['wasm'].update(sha256='0'*64),
            lambda p:p['counts'].update(triangles=93451),lambda p:p['coordinate_frame'].update(up='+Z'),
            lambda p:p['options'].update(cell_size=.02),lambda p:p['options']['head'].update(yaw=False)):
            files=dict(originals);producer=json.loads(files['producer.json']);mutate(producer);files['producer.json']=encode(producer).encode();variants.append(repack(files))
        # Source-derived malformed control, not a generated producer fixture.
        files=dict(originals);request=json.loads(files['request.json']);request['operation']['surface_options']={'cell_size':.04}
        files['request.json']=encode(request).encode();producer=json.loads(files['producer.json'])
        producer['request'].update(bytes=len(files['request.json']),sha256=core.sha(files['request.json']))
        producer['options']['cell_size']=.04;files['producer.json']=encode(producer).encode();variants.append(repack(files))
        for raw in variants:
            with self.subTest(hash=core.sha(raw)):
                with self.assertRaises(core.BinaryMeshError):core.validate_bundle(raw)

    def test_cross_block_duplicate_face_is_global(self):
        properties=[{'name':x,'dtype':'float'} for x in ('x','y','z')]
        vertices=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]
        raw=core.binary_from_rows(properties,vertices,[[0,1,2]]*513,'uint')
        with self.assertRaisesRegex(core.BinaryMeshError,'duplicate unordered face'):core.parse_ply(raw)

    def test_successful_actual_worker_measured_below_unchanged_execution_limit(self):
        result=assets.validate_bytes(self.actual);metrics=result['resource_measurement']
        self.assertEqual(metrics['address_space_limit_bytes'],256*1024*1024)
        self.assertLess(metrics['peak_rss_bytes'],metrics['address_space_limit_bytes'])
        self.assertLess(metrics['cpu_seconds'],30);self.assertLess(metrics['wall_seconds'],45)
        self.assertEqual((result['metadata']['vertex_count'],result['metadata']['triangle_count']),(46728,93452))


if __name__=='__main__':unittest.main()
