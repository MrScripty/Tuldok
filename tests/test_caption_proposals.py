import base64
import hashlib
import io
import json
import urllib.error
import urllib.request
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from app import Dataset, make_handler
from http.server import ThreadingHTTPServer
from fake_caption_model import start
from workbench import WorkbenchError


class CaptionProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.data = Dataset(self.tmp.name); self.addCleanup(lambda: self.data.close())
        self.server, self.url, self.requests = start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.row = self.image('blue')

    def image(self, color):
        output = io.BytesIO(); Image.new('RGB', (200, 100), color).save(output, 'PNG')
        return self.data.workbench.import_asset(dict(kind='image', name=color, image=base64.b64encode(output.getvalue()).decode(), groups=[color], rights='Authored local fixture'))

    def config(self, **changes):
        body = dict(request_id=uuid.uuid4().hex, source_id=self.row['id'], revision=self.row['revision'], source_revision=self.row['source_revision'],
                    server_url=self.url, model='caption-fixture', instruction='Describe visible pixels', seed=42)
        body.update(changes); return body

    def generate(self, **changes):
        job = self.data.caption_proposals.start(self.config(**changes))
        self.data.caption_proposals.worker.join(5)
        self.assertFalse(self.data.caption_proposals.worker.is_alive())
        return self.data.caption_proposals.get(job['id'])

    def decide(self, job, decision='apply_draft'):
        return self.data.caption_proposals.decide(job['id'], {'revision': job['revision'], 'decision': decision})

    def state(self):
        return [list(self.data.db.execute('SELECT * FROM '+name+' ORDER BY rowid')) for name in
                ('workbench_records', 'workbench_history', 'workbench_target_proposals', 'caption_proposals')]

    def wait(self, predicate):
        end=time.monotonic()+3
        while not predicate():
            if time.monotonic()>end: self.fail('Timed out waiting for controlled worker')
            time.sleep(.01)

    def test_actual_image_http_exact_evidence_draft_and_idempotent_apply(self):
        before=self.data.workbench.get(self.row['id']);job=self.generate()
        self.assertEqual(job['status'],'completed',job['error'])
        self.assertEqual(self.data.workbench.get(self.row['id']),before)
        observed=self.requests[0];self.assertEqual(observed['path'],'/v1/chat/completions')
        image=base64.b64decode(observed['body']['messages'][1]['content'][1]['image_url']['url'].split(',')[1])
        self.assertEqual(image,base64.b64decode(job['input_image_base64']))
        with Image.open(io.BytesIO(image)) as decoded:
            self.assertEqual(decoded.size,(200,100));self.assertEqual(decoded.format,'JPEG')
            self.assertGreater(decoded.getpixel((100,50))[2],240)
        for key, data in [('input_image',image),('response',base64.b64decode(job['raw_response_base64']))]:
            digest=job['input_image']['sha256'] if key=='input_image' else job['response_sha256']
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest)
        self.assertNotIn('input_image_base64',self.data.caption_proposals.snapshot()['jobs'][0])
        result=self.decide(job);row=result['record']
        self.assertEqual((row['task'],row['review']),('image_caption','draft'))
        self.assertEqual(row['revision'],before['revision']+1)
        for key in ('id','content_hash','source_sha256','groups','parents','provenance','source_revision'):
            self.assertEqual(row[key],before[key])
        self.assertEqual(row['target_proposal']['job_id'],job['id'])
        state=self.state();again=self.decide(job)
        self.assertFalse(again['changed']);self.assertEqual(self.state(),state)
        self.assertEqual(json.loads(self.data.db.execute('SELECT snapshot FROM workbench_history WHERE id=? AND revision=?',(row['id'],row['revision'])).fetchone()[0])['target_proposal'],row['target_proposal'])
        self.data.close();self.data=Dataset(self.tmp.name)
        self.assertEqual(self.data.caption_proposals.get(job['id'])['application']['revision'],row['revision'])
        self.assertEqual(self.data.workbench.get(row['id'])['target_proposal'],row['target_proposal'])

    def test_request_id_reconciles_lost_start_without_more_inference(self):
        body=self.config();job=self.data.caption_proposals.start(body);self.data.caption_proposals.worker.join(3)
        count=len(self.requests)
        again=self.data.caption_proposals.start(body)
        self.assertEqual(again['id'],job['id']);self.assertEqual(len(self.requests),count)
        with self.assertRaisesRegex(WorkbenchError,'different request'):
            self.data.caption_proposals.start(dict(body,instruction='changed'))

    def test_failures_preserve_targets_and_do_not_fallback(self):
        target=self.data.workbench.get(self.row['id']);history=self.data.db.execute('SELECT COUNT(*) FROM workbench_history').fetchone()[0]
        for mode in ('empty','unknown','oversized-caption','unicode','duplicate','malformed','oversized','truncated','tools','short-body','provider_error'):
            job=self.generate(instruction=mode)
            self.assertEqual(job['status'],'failed',(mode,job));self.assertIsNone(job['annotation'])
            self.assertEqual(self.data.workbench.get(self.row['id']),target)
            self.assertEqual(self.data.db.execute('SELECT COUNT(*) FROM workbench_history').fetchone()[0],history)
        for model in ('missing','image-only','text-only'):
            count=len(self.requests);job=self.generate(model=model)
            self.assertEqual(job['status'],'failed',job)
            self.assertEqual(len(self.requests)-count,1 if model=='text-only' else 0)
        self.assertIn('unsupported or invalid image input',job['error'])

    def test_atomic_linkage_failure_rolls_back_every_target_write(self):
        job=self.generate();state=self.state()
        with patch.object(self.data.caption_proposals,'_save',side_effect=RuntimeError('injected linkage failure')):
            with self.assertRaisesRegex(RuntimeError,'linkage'): self.decide(job)
        self.assertEqual(self.state(),state)
        self.assertTrue(self.decide(job)['changed'])

    def test_reject_is_terminal_and_idempotent_without_target_mutation(self):
        job=self.generate();before=self.data.workbench.get(self.row['id'])
        self.assertTrue(self.decide(job,'reject')['changed']);self.assertFalse(self.decide(job,'reject')['changed'])
        with self.assertRaisesRegex(WorkbenchError,'not pending'):self.decide(job)
        self.assertEqual(self.data.workbench.get(self.row['id']),before)

    def test_stale_record_and_source_revisions_block_application(self):
        for owner in ('target','source'):
            self.row=self.data.workbench.get(self.row['id']);job=self.generate()
            if owner=='target':
                self.data.workbench.save(self.row['id'],dict(self.row,task='image_caption',annotation={'caption':'Explicit later caption'},review='human_reviewed'))
            else:
                source=self.data.sample(self.row['id']);self.data.save(source['id'],dict(source,annotation={'book_present':False,'crop_suitable':False,'corners':[]}))
            before=self.state()
            with self.assertRaisesRegex(WorkbenchError,'Image or target changed'):self.decide(job)
            self.assertEqual(self.state(),before)

    def test_missing_tampered_and_deleted_source_block_request_and_apply(self):
        folder=Path(self.tmp.name)/'images'/self.row['id'];job=self.generate()
        for name in ('image.png','source'):
            path=folder/name;original=path.read_bytes();path.write_bytes(b'tampered')
            before=self.state()
            with self.assertRaisesRegex(WorkbenchError,'bytes changed'):self.decide(job)
            with self.assertRaisesRegex(WorkbenchError,'bytes changed'):self.data.caption_proposals.start(self.config())
            self.assertEqual(self.state(),before)
            path.unlink()
            with self.assertRaisesRegex(WorkbenchError,'bytes are missing'):self.decide(job)
            path.write_bytes(original)
        self.data.delete(self.row['id'], {'revision':self.row['source_revision']})
        with self.assertRaisesRegex(WorkbenchError,'available image'):self.decide(job)

    def test_inflight_target_change_never_publishes_completed_proposal(self):
        entered=threading.Event();release=threading.Event()
        from caption_proposals import complete
        def held(job,stop):
            data=complete(job,stop);entered.set();release.wait(3);return data
        with patch('caption_proposals.complete',side_effect=held):
            job=self.data.caption_proposals.start(self.config());self.assertTrue(entered.wait(3))
            self.data.workbench.save(self.row['id'],dict(self.row,task='image_caption',annotation={'caption':'Later'},review='draft'))
            release.set();self.data.caption_proposals.worker.join(3)
        result=self.data.caption_proposals.get(job['id']);self.assertEqual(result['status'],'failed');self.assertIn('changed',result['error'])

    def test_cancel_body_and_catalog_then_fresh_request(self):
        for mode in ('slow','slow-body'):
            job=self.data.caption_proposals.start(self.config(instruction=mode));self.wait(lambda:len(self.requests)>0 and self.requests[-1]['body']['messages'][1]['content'][0]['text']==mode)
            with self.assertRaisesRegex(WorkbenchError,'active'):self.data.caption_proposals.start(self.config())
            self.assertTrue(self.data.caption_proposals.cancel({'job_id':job['id']})['cancelled'])
            self.data.caption_proposals.worker.join(2);self.assertFalse(self.data.caption_proposals.worker.is_alive())
            self.assertEqual(self.data.caption_proposals.get(job['id'])['status'],'cancelled')
            self.assertIsNone(self.data.workbench.get(self.row['id'])['annotation'])
        entered=threading.Event();server,url,_=start(entered)
        try:
            job=self.data.caption_proposals.start(self.config(server_url=url));self.assertTrue(entered.wait(3))
            self.data.caption_proposals.cancel({'job_id':job['id']});self.data.caption_proposals.worker.join(2)
            self.assertFalse(self.data.caption_proposals.worker.is_alive());self.assertEqual(self.data.caption_proposals.get(job['id'])['status'],'cancelled')
        finally:server.shutdown();server.server_close()
        self.assertEqual(self.generate()['status'],'completed')

    def test_cancel_fences_late_valid_response_and_shutdown_interrupts(self):
        entered=threading.Event();release=threading.Event()
        from caption_proposals import complete
        def held(job,stop):
            data=complete(job,stop);entered.set();release.wait(3);return data
        with patch('caption_proposals.complete',side_effect=held):
            job=self.data.caption_proposals.start(self.config());self.assertTrue(entered.wait(3))
            self.data.caption_proposals.cancel({'job_id':job['id']});release.set();self.data.caption_proposals.worker.join(3)
        self.assertEqual(self.data.caption_proposals.get(job['id'])['status'],'cancelled')
        job=self.data.caption_proposals.start(self.config(instruction='slow'));self.wait(lambda:len(self.requests)>1)
        self.data.close();self.data=Dataset(self.tmp.name)
        self.assertEqual(self.data.caption_proposals.get(job['id'])['status'],'cancelled')
        # Persist the state a killed process would have left, then exercise startup.
        with self.data.lock,self.data.db:
            interrupted=self.data.caption_proposals.get(job['id']);interrupted['status']='generating';self.data.caption_proposals._save(interrupted)
        self.data.close();count=len(self.requests);self.data=Dataset(self.tmp.name)
        self.assertEqual(self.data.caption_proposals.get(job['id'])['status'],'interrupted');self.assertEqual(len(self.requests),count)

    def test_review_export_consumer_evidence_history_and_fixed_selection(self):
        initial=self.data.workbench.save(self.row['id'],dict(self.row,task='image_caption',annotation={'caption':'Earlier reviewed caption'},review='human_reviewed'))
        self.row=initial
        fixed=self.data.selections.create({'name':'Fixed captions','items':[{k:initial[k] for k in ('id','revision','source_revision')}]})
        job=self.generate();applied=self.decide(job)['record']
        self.assertFalse(self.data.selections.load(fixed['id'])['current'])
        self.assertEqual(self.data.selections.load(fixed['id'])['members'][0]['status'],'stale')
        rows=[applied,self.image('red'),self.image('green')]
        body=lambda values:dict(items=[{k:r[k] for k in ('id','revision','source_revision')} for r in values],format='image_caption_v1',seed=42,ratios=dict(train=34,validation=33,test=33))
        self.assertFalse(self.data.releases.preview(body(rows))['eligible'])
        rows=[self.data.workbench.save(r['id'],dict(r,task='image_caption',annotation=r['annotation'] or {'caption':'A colored rectangle'},review='human_reviewed')) for r in rows]
        self.assertEqual(rows[0]['target_proposal'],applied['target_proposal'])
        release=self.data.releases.create(body(rows))
        folder=Path(self.tmp.name)/'expanded';folder.mkdir()
        with zipfile.ZipFile(self.data.releases.locate(release['id'])) as archive:
            archive.extractall(folder);manifest=json.loads(archive.read('manifest.json'))
        frozen=next(r for r in manifest['records'] if r['id']==applied['id'])
        self.assertEqual(frozen['target_proposal']['job_id'],job['id'])
        result=subprocess.run(['python3',str(Path(__file__).parent/'fixtures/diffusion_check_image_data.py'),str(folder)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('PASS: 3 records',result.stdout)
        edited=self.data.workbench.save(rows[0]['id'],dict(rows[0],annotation={'caption':'Changed by a person'},review='draft'))
        self.assertNotIn('target_proposal',edited)
        self.assertEqual(frozen['annotation'],job['annotation'])

    def test_concurrent_apply_produces_one_revision(self):
        job=self.generate();results=[];errors=[]
        def apply():
            try:results.append(self.decide(job))
            except Exception as error:errors.append(error)
        threads=[threading.Thread(target=apply) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(3)
        self.assertEqual(errors,[]);self.assertEqual(sorted(r['changed'] for r in results),[False,True])
        self.assertEqual(self.data.workbench.get(self.row['id'])['revision'],self.row['revision']+1)

    def test_http_routes_reject_approval_and_return_persisted_receipt(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.data))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}/api/workbench/'
        def request(path,body=None):
            req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
        try:
            body=self.config();job=request('caption-proposals',body);self.data.caption_proposals.worker.join(3)
            job=request('caption-proposals/'+job['id']);self.assertEqual(job['status'],'completed')
            for decision in ('human_reviewed','programmatically_verified'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request('caption-proposals/decide/'+job['id'],{'revision':job['revision'],'decision':decision})
                self.assertEqual(error.exception.code,400)
            result=request('caption-proposals/decide/'+job['id'],{'revision':job['revision'],'decision':'apply_draft'})
            self.assertEqual(result['record']['review'],'draft')
            self.assertEqual(request('caption-proposals/'+job['id'])['application']['revision'],result['record']['revision'])
            self.assertNotIn('input_image_base64',request('caption-proposals')['jobs'][0])
        finally:server.shutdown();server.server_close();thread.join(3)

    def test_oriented_thumbnail_preserves_original_bytes_and_input_identity(self):
        image=Image.new('RGB',(1800,900),'blue');exif=Image.Exif();exif[274]=6
        output=io.BytesIO();image.save(output,'JPEG',exif=exif)
        raw=output.getvalue()
        self.row=self.data.workbench.import_asset(dict(kind='image',name='Oriented',image=base64.b64encode(raw).decode(),groups=['oriented'],rights='Authored'))
        self.assertEqual((self.row['width'],self.row['height']),(900,1800))
        job=self.generate();self.assertEqual(job['status'],'completed',job['error'])
        self.assertEqual(job['input_image']['size'],[800,1600])
        with Image.open(io.BytesIO(base64.b64decode(job['input_image_base64']))) as submitted:
            self.assertEqual(submitted.getexif().get(274,1),1)
        self.assertEqual((Path(self.tmp.name)/'images'/self.row['id']/'source').read_bytes(),raw)
        with patch('caption_proposals.MAX_IMAGE',10):
            with self.assertRaisesRegex(WorkbenchError,'exceeds 2 MiB'):self.data.caption_proposals.start(self.config())

    def test_failed_start_persistence_never_launches_inference(self):
        with patch.object(self.data.caption_proposals,'_save',side_effect=RuntimeError('injected persistence failure')):
            with self.assertRaisesRegex(RuntimeError,'persistence'):self.data.caption_proposals.start(self.config())
        self.assertIsNone(self.data.caption_proposals.worker);self.assertEqual(self.requests,[])
        self.assertEqual(self.data.db.execute('SELECT COUNT(*) FROM caption_proposals').fetchone()[0],0)
