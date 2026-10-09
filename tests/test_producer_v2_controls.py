"""Explicitly SYNTHETIC contract/UI-owner evidence, never actual producer acceptance."""
import base64,copy,hashlib,io,json,tempfile,threading,unittest,urllib.request,urllib.error,zipfile
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from PIL import Image
from app import Dataset,make_handler
from fixtures.rheon_synthetic_v2 import fixture,pack
from fixtures.rheon_authored_controls import authored_controls
import rheon_sequences as r
import sequence_inspection as inspector
import rheon_controls_contract as v2
from workbench import WorkbenchError,encode


def body(files):return {'files':{n:base64.b64encode(b).decode() for n,b in zip(('run.json','frames.jsonl','controls.json'),files)},'name':'SYNTHETIC v2 trajectory','groups':['synthetic-family'],'rights':'Explicit synthetic fixture'}


class ProducerV2(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Dataset(self.tmp.name);self.addCleanup(self.d.close);self.w=self.d.workbench
        self.files=fixture();self.manifest=json.loads(self.files[0]);self.controls=json.loads(self.files[2])

    def state(self):return tuple(self.d.db.iterdump())
    def admit(self):return r.admit(self.w,body(self.files))
    def probe(self,row,k=8,**changes):return inspector.inspect(self.w,row['id'],dict(revision=row['revision'],source_revision=1,frame=k,field='velocity_x',index=[16,7,3],**changes))
    def changed(self,path,value):
        c=copy.deepcopy(self.controls);target=c
        for k in path[:-1]:target=target[k]
        target[path[-1]]=value
        return pack(self.manifest,self.files[1],c)

    def test_synthetic_roundtrip_raw_three_files_native_probe_zero_and_authored_separate(self):
        row=self.admit();before=self.state();bundle=self.w.asset(row['id'])[0]
        self.assertEqual((row['review'],row['annotation'],row['revision'],row['source_revision']),('draft',None,1,1))
        self.assertEqual(row['sequence']['adapter'],r.CONTROLS_ADAPTER)
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:
            self.assertEqual(set(z.namelist()),set(body(self.files)['files']))
            for name,raw in zip(('run.json','frames.jsonl','controls.json'),self.files):self.assertEqual(z.read(name),raw)
        result=self.probe(row);emitted=result['interval_controls_emitted']
        self.assertEqual(emitted['scope'],'producer_controls_validated');self.assertEqual(emitted['selected_interval'],self.controls['intervals'][7])
        self.assertIn('declaration',emitted['origin_status']);self.assertEqual(result['field']['shape'],[17,8,4]);self.assertEqual(result['field']['dtype'],'f32')
        zero=self.probe(row,0);self.assertIsNone(zero['accepted_interval']);self.assertIsNone(zero['interval_controls_emitted']['selected_interval'])
        authored=base64.b64encode(encode(authored_controls(self.files[0],self.files[1])).encode()).decode()
        combined=self.probe(row,controls=authored);self.assertEqual(combined['authored_controls_preview']['scope'],'authored_controls_preview')
        self.assertEqual(combined['interval_controls_emitted'],emitted);self.assertEqual(self.state(),before)

    def test_rehashed_closed_binding_axis_stamp_interval_source_numeric_rejections_atomic(self):
        cases=[(['run_binding','version'],2.0),(['run_binding','config','steps'],True),
            (['frames_sha256'],'0'*64),(['axis_order'],['y','x','z']),(['side_order'],['high','low']),
            (['units','source_rate'],'m/s'),(['intervals'],self.controls['intervals'][:7]),
            (['intervals',0,'start_frame'],True),(['intervals',0,'dt_s'],0),
            (['intervals',0,'start_time_s'],0), # frame time is float0.0: strict typed association
            (['intervals',0,'carrier_after','version'],'01'),(['intervals',0,'liquid_before','id'],'42'),
            (['intervals',0,'source_mode'],'zero'),(['intervals',0,'source_mode'],False),
            (['intervals',0,'source_rate_m3_s'],False),(['intervals',0,'source_rate_m3_s'],'0'),
            (['intervals',0,'source_rate_m3_s'],.01),(['intervals',0,'source_rate_m3_s'],float('inf')),
            (['intervals',0,'body_acceleration_m_s2'],[0,1,0]),(['provenance','origin'],'independently_authored_contract_fixture'),
            (['provenance','author'],'\u0085')]
        before=self.state()
        for path,value in cases:
            with self.subTest(path=path,value=value):
                with self.assertRaises(WorkbenchError):r.admit(self.w,body(self.changed(path,value)))
                self.assertEqual(self.state(),before)
        for raw in [b'{',b'{}',b'{"version":2,"version":2}',b'x'*65537]:
            with self.assertRaises(WorkbenchError):r.admit(self.w,body(pack(self.manifest,self.files[1],raw)))
            self.assertEqual(self.state(),before)

    def test_numeric_zero_float_allowed_but_typed_binding_remains_exact(self):
        files=self.changed(['intervals',0,'source_rate_m3_s'],0.0)
        row=r.admit(self.w,body(files));self.assertEqual(self.probe(row,1)['interval_controls_emitted']['selected_interval']['source_rate_m3_s'],0.0)
        with self.assertRaises(WorkbenchError):r.prepare(*self.changed(['run_binding','geometry','counts',0],16.0))

    def test_complete_hash_caps_version_and_file_rosters_reject_before_publication(self):
        before=self.state()
        for files in [(self.files[0],self.files[1],self.files[2][:-1]),(self.files[0],self.files[1][:-1],self.files[2]),(self.files[0],self.files[1],None)]:
            with self.assertRaises(WorkbenchError):r.prepare(*files)
            self.assertEqual(self.state(),before)
        for value in [True,2.0,3]:
            m=dict(self.manifest,version=value)
            with self.assertRaises(WorkbenchError):r.prepare(json.dumps(m).encode(),self.files[1],self.files[2])
        for extra in ['intervals.json','bogus']:
            b=body(self.files);b['files'][extra]='e30='
            with self.assertRaises(WorkbenchError):r.admit(self.w,b)

    def test_old_v1_byte_contract_and_cross_version_family_deleted_bridge(self):
        old=v2.downgraded_manifest(self.manifest);old_raw=encode(old).encode()
        first=r.admit(self.w,{'files':{'run.json':base64.b64encode(old_raw).decode(),'frames.jsonl':base64.b64encode(self.files[1]).decode()},'groups':['old-family']})
        second=self.admit();self.assertEqual(first['sequence']['adapter'],r.ADAPTER)
        self.assertEqual(first['sequence']['protected_groups'][1],second['sequence']['protected_groups'][1])
        with self.assertRaises(WorkbenchError):r.prepare(old_raw,self.files[1],self.files[2])
        img=io.BytesIO();Image.new('RGB',(2,2),'orange').save(img,'PNG')
        bridge=self.w.import_asset({'kind':'image','image':base64.b64encode(img.getvalue()).decode(),'groups':['synthetic-family','related']})
        related=self.w.import_asset({'kind':'text','text':'Related unselected source','groups':['related']})
        self.d.delete(bridge['id'],{'revision':bridge['source_revision']})
        lineage=self.probe(second)['lineage'][0];self.assertEqual(set(lineage['member_ids']),{first['id'],second['id'],bridge['id'],related['id']})
        self.assertEqual(lineage['deleted_ids'],[bridge['id']])
        second=self.w.save(second['id'],dict(revision=1,source_revision=1,task='sequence_transport',annotation={'note':'Synthetic transport review'},review='human_reviewed',groups=second['groups']))
        ref={k:second[k] for k in ('id','revision','source_revision')}
        self.assertFalse(self.d.releases.preview(dict(items=[ref],ratios={'train':80,'validation':10,'test':10},seed=42))['eligible'])
        release=self.d.releases.create(dict(items=[ref],ratios={'train':100,'validation':0,'test':0},seed=42))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as z:
            manifest=json.loads(z.read('manifest.json'));path=next(x['asset'] for x in manifest['records'] if x['id']==second['id'])
            self.assertEqual(z.read(path),self.w.asset(second['id'])[0])

    def test_corrupt_stored_controls_metadata_hash_and_zip_entry_sets_readonly(self):
        row=self.admit();original=self.w.asset(row['id'])[0]
        metadata=copy.deepcopy(row['sequence']);metadata.pop('bundle_bytes');metadata['controls']['interval_count']=True
        self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(metadata),));self.d.db.commit();before=self.state()
        with self.assertRaises(WorkbenchError):self.probe(row)
        self.assertEqual(self.state(),before)
        metadata=copy.deepcopy(row['sequence']);metadata.pop('bundle_bytes')
        self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(metadata),));self.d.db.commit()
        for mode in ['missing','duplicate','compressed','extra']:
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED if mode=='compressed' else zipfile.ZIP_STORED) as z:
                for name,raw in zip(('run.json','frames.jsonl','controls.json'),self.files):
                    if mode!='missing' or name!='controls.json':z.writestr(name,raw)
                if mode=='duplicate':z.writestr('controls.json',self.files[2])
                if mode=='extra':z.writestr('intervals.json',b'[]')
            data=stream.getvalue();self.d.db.execute('UPDATE workbench_sequence_assets SET bundle=?,bundle_bytes=?',(data,len(data)));self.d.db.execute('UPDATE workbench_records SET content_hash=? WHERE id=?',(hashlib.sha256(data).hexdigest(),row['id']));self.d.db.commit()
            with self.assertRaises(WorkbenchError):self.probe(row)

    def test_exact_validator_source_alias_and_v2_rehashed_native_malformed_frames(self):
        original=Path(v2.__file__).read_bytes().replace(b'import rheon_sequence_contract as v1',b'import import_dense3d_sequence as v1')
        self.assertEqual(hashlib.sha256(original).hexdigest(),'215f98241e01a6fb099b5b1b8789e00c951988e1382438afbd45cfbb7e1c4c43')
        self.assertEqual(hashlib.sha256(Path(r.contract.__file__).read_bytes()).hexdigest(),'063d17a3bbc92a27c26c0f5dd4588a9478091ebbf53ce0ccb818cee6a9393b98')
        frames=[json.loads(line) for line in self.files[1].splitlines()]
        before=self.state()
        # Recompute declared bindings to exercise native validation beyond raw SHA rejection.
        for path,value in [(['fields','velocity_x',0],float('nan')),(['carrier_stamp','version'],'01'),(['dt_s'],-1),(['fields','velocity_y'],[0])]:
            altered=copy.deepcopy(frames);target=altered[1]
            for k in path[:-1]:target=target[k]
            target[path[-1]]=value
            raw=b''.join((json.dumps(f,separators=(',',':'),allow_nan=True)+'\n').encode() for f in altered)
            m=copy.deepcopy(self.manifest);m.update(frames_bytes=len(raw),frames_sha256=hashlib.sha256(raw).hexdigest())
            c=copy.deepcopy(self.controls);c['frames_sha256']=m['frames_sha256']
            with self.assertRaises(WorkbenchError):r.admit(self.w,body(pack(m,raw,c)))
            self.assertEqual(self.state(),before)

    def test_owner_storage_failure_is_atomic(self):
        before=self.state()
        # Admission transaction rolls back if history publication fails after asset insertion.
        with patch.object(self.w,'_history',side_effect=RuntimeError('controlled history failure')):
            with self.assertRaises(RuntimeError):self.admit()
        self.assertEqual(self.state(),before)

    def test_synthetic_real_http_import_probe_and_malformed_atomic(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)+'/api/workbench/'
        def post(path,b):return urllib.request.urlopen(urllib.request.Request(url+path,data=encode(b).encode(),headers={'Content-Type':'application/json'}))
        before=self.state()
        for raw in [b'{\"files\":{},\"files\":{}}', b'{\"files\":{\"run.json\":\"e30=\",\"run.json\":\"e30=\"}}', b'{\"name\":NaN}', b'{\"name\":'+b'['*1200+b'0'+b']'*1200+b'}']:
            request=urllib.request.Request(url+'sequence-import',data=raw,headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,400);self.assertEqual(self.state(),before)
        with self.assertRaises(urllib.error.HTTPError):post('sequence-import',body(self.changed(['intervals',0,'source_rate_m3_s'],True)))
        self.assertEqual(self.state(),before)
        with post('sequence-import',body(self.files)) as response:row=json.load(response);self.assertEqual(response.status,201)
        with post('sequence-inspection/'+row['id'],dict(revision=1,source_revision=1,frame=0,field='velocity_x',index=[0,0,0])) as response:self.assertIsNone(json.load(response)['interval_controls_emitted']['selected_interval'])
