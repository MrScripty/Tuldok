"""Explicit synthetic v2 folder compatibility; no actual producer-v2 acceptance."""
import base64,copy,hashlib,io,json,tempfile,threading,unittest,uuid,zipfile
from unittest.mock import patch
from app import Dataset
from fixtures.rheon_synthetic_v2 import fixture
from test_sequence_batch import body as old_body,synthetic
import sequence_batch_import as b
from workbench import WorkbenchError

def request(files=None,**changes):
    files=files or fixture()
    value={'files':{n:base64.b64encode(raw).decode() for n,raw in zip(('run.json','frames.jsonl','controls.json'),files)},'request_id':uuid.uuid4().hex,'batch_name':'synthetic-corpus','item_name':'synthetic-v2','item_index':1}
    value.update(changes);return value

class MixedFolder(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=Dataset(self.tmp.name);self.addCleanup(self.d.close);self.w=self.d.workbench
    def state(self):return tuple(self.d.db.iterdump())
    def test_synthetic_v2_context_hashes_historical_lookup_and_v1_context_unchanged(self):
        q=request();receipt=b.import_item(self.w,q);self.assertEqual(receipt['format'],b.CONTROLS_FORMAT);self.assertEqual(receipt['sequence_version'],2)
        self.assertEqual(receipt['controls_sha256'],hashlib.sha256(fixture()[2]).hexdigest());self.assertEqual(b.find_result(self.w,q['request_id']),dict(found=True,**receipt))
        row=self.w.get(receipt['record_id']);self.assertEqual((row['review'],row['annotation']),('draft',None));self.assertEqual(self.w.asset(row['id'])[1],'application/zip')
        with zipfile.ZipFile(io.BytesIO(self.w.asset(row['id'])[0])) as z:
            self.assertEqual(z.namelist(),['run.json','frames.jsonl','controls.json'])
            for name,raw in zip(z.namelist(),fixture()):self.assertEqual(z.read(name),raw)
        prior=b.import_item(self.w,old_body(*synthetic(),item_name='v1'))
        self.assertEqual(prior['format'],b.FORMAT);self.assertNotIn('sequence_version',prior);self.assertNotIn('controls_sha256',prior)
        self.assertEqual(set(prior),{'format','request_id','batch_name','item_name','item_index','run_sha256','frames_sha256','record_id','kind','name'})
        self.assertEqual(row['sequence']['protected_groups'][1],self.w.get(prior['record_id'])['sequence']['protected_groups'][1])
        before=dict(receipt);reviewed=self.w.save(row['id'],dict(revision=1,source_revision=1,task='sequence_transport',annotation={'note':'Synthetic transport review'},review='human_reviewed',groups=row['groups']))
        self.assertEqual(b.find_result(self.w,q['request_id']),dict(found=True,**before))
        ref={k:reviewed[k] for k in ('id','revision','source_revision')};release=self.d.releases.create(dict(items=[ref],ratios={'train':100,'validation':0,'test':0},seed=42))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as z:
            m=json.loads(z.read('manifest.json'));self.assertEqual(z.read(m['records'][0]['asset']),self.w.asset(row['id'])[0])
        self.d.close();self.d=Dataset(self.tmp.name);self.w=self.d.workbench;self.assertEqual(b.find_result(self.w,q['request_id']),dict(found=True,**before))
    def test_missing_extra_mismatched_hashed_controls_fail_atomically_prior_survives(self):
        prior=b.import_item(self.w,old_body(*synthetic()));before=self.state()
        files=fixture();cases=[]
        q=request();del q['files']['controls.json'];cases.append(q)
        q=old_body(*synthetic());q['files']['controls.json']=base64.b64encode(files[2]).decode();cases.append(q)
        for raw in [files[2][:-1],b'x'*65537,b'{}']:
            q=request();q['files']['controls.json']=base64.b64encode(raw).decode();cases.append(q)
        q=request();q['files']['intervals.json']='e30=';cases.append(q)
        q=request();q['sequence_version']=2;cases.append(q)
        for q in cases:
            with self.assertRaises(WorkbenchError):b.import_item(self.w,q)
            self.assertEqual(self.state(),before);self.assertEqual(b.find_result(self.w,q['request_id']),{'found':False})
        self.assertEqual(self.w.get(prior['record_id'])['review'],'draft')
    def test_cross_version_same_marker_atomic_concurrency_and_ambiguity(self):
        marker=uuid.uuid4().hex;gate=threading.Barrier(2);outcomes=[];original=b.rheon.prepare
        def prepare(*args):v=original(*args);gate.wait(timeout=5);return v
        def worker(q):
            try:outcomes.append(b.import_item(self.w,q))
            except WorkbenchError as e:outcomes.append(e.status)
        with patch.object(b.rheon,'prepare',side_effect=prepare):
            workers=[threading.Thread(target=worker,args=(q,)) for q in (request(request_id=marker),old_body(*synthetic(),request_id=marker))]
            for t in workers:t.start()
            for t in workers:t.join(8);self.assertFalse(t.is_alive())
        self.assertEqual(len([x for x in outcomes if type(x) is dict]),1);self.assertIn(409,outcomes);self.assertTrue(b.find_result(self.w,marker)['found']);self.assertEqual(self.w.query({'kind':'sequence'})['total'],1)
        first=next(x for x in outcomes if type(x) is dict);other=b.import_item(self.w,request() if first['format']==b.FORMAT else old_body(*synthetic()))
        provenance=self.w.get(other['record_id'])['provenance'];provenance['sequence_acquisition']['request_id']=marker
        self.d.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?',(json.dumps(provenance),other['record_id']));self.d.db.commit()
        with self.assertRaises(WorkbenchError) as caught:b.find_result(self.w,marker)
        self.assertEqual(caught.exception.status,409)
    def test_v2_item_history_failure_rolls_back_marker_and_raw_asset(self):
        prior=b.import_item(self.w,old_body(*synthetic()));before=self.state();q=request()
        self.d.db.execute("CREATE TRIGGER fail_v2 BEFORE INSERT ON workbench_history BEGIN SELECT RAISE(ABORT,'controlled history failure');END");self.d.db.commit()
        with self.assertRaises(WorkbenchError) as caught:b.import_item(self.w,q)
        self.assertEqual(caught.exception.status,500);self.d.db.execute('DROP TRIGGER fail_v2');self.d.db.commit();self.assertEqual(self.state(),before);self.assertEqual(b.find_result(self.w,q['request_id']),{'found':False});self.assertEqual(self.w.get(prior['record_id'])['review'],'draft')
