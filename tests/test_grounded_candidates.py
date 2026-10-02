import json
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
import zipfile
from unittest.mock import patch

from app import Dataset, make_handler
from fake_grounded import start
from grounded_candidates import decode, catalog
from workbench import WorkbenchError


class GroundedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data=Dataset(self.tmp.name);self.addCleanup(lambda:self.data.close())
        self.server,self.url,self.requests=start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.source=self.data.workbench.import_asset(dict(kind='text',text='Please cancel the café meeting 😀.',name='Request',groups=['customer-1'],rights='User-owned fixture'))
        self.source=self.review(self.source)

    def review(self,row):
        return self.data.workbench.save(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],
            task='text_classification',annotation={'label':'cancel'},groups=row['groups'],review='human_reviewed'))

    def config(self,**extra):
        return dict(source_id=self.source['id'],revision=self.source['revision'],source_revision=self.source['source_revision'],
                    server_url=self.url,model='grounded-text-test',instruction='Rewrite clearly',count=2,seed=42,**extra)

    def generate(self,mode='Rewrite clearly',**changes):
        config=self.config();config.update(instruction=mode,**changes)
        job=self.data.grounded.start(config);self.data.grounded.worker.join(5)
        self.assertFalse(self.data.grounded.worker.is_alive())
        return self.data.grounded.get(job['id'])

    def decision(self,job,index=0,decision='admit_draft'):
        return dict(revision=job['revision'],candidate_id=job['candidates'][index]['id'],decision=decision,note='Inspected source and proposed wording; importing for separate annotation review.')

    def release(self,rows,ratios=None):
        return self.data.releases.create(dict(items=[{k:r[k] for k in ('id','revision','source_revision')} for r in rows],seed=42,
            ratios=ratios or dict(train=100,validation=0,test=0)))

    def test_actual_supported_http_paths_provenance_draft_review_release(self):
        self.assertEqual(catalog(self.url),['grounded-text-test'])
        job=self.generate();self.assertEqual(job['status'],'completed');self.assertEqual(len(job['candidates']),2)
        request=self.requests[0];self.assertEqual(request['path'],'/v1/chat/completions')
        self.assertEqual(request['body']['seed'],42)
        self.assertEqual(json.loads(request['body']['messages'][1]['content'])['source'],self.source['text'])
        result=self.data.grounded.review(job['id'],self.decision(job));record=result['record']
        self.assertEqual(record['review'],'draft');self.assertEqual(record['parents'],[self.source['id']]);self.assertEqual(record['groups'],self.source['groups'])
        self.assertEqual(record['provenance']['response_sha256'],job['response_sha256'])
        self.assertEqual(record['provenance']['source']['text'],self.source['text'])
        self.assertEqual(record['provenance']['evidence'][0]['quote'],self.source['text'])
        with self.assertRaises(WorkbenchError):self.release([record])
        record=self.review(record);release=self.release([self.source,record])
        with zipfile.ZipFile(self.data.releases.locate(release['id'])) as archive:
            rows=json.loads(archive.read('manifest.json'))['records'];self.assertEqual({r['split'] for r in rows},{'train'})
            self.assertIn(record['text'],archive.read('train/records.jsonl').decode())
        with self.assertRaises(WorkbenchError):self.release([self.source,record],dict(train=50,validation=0,test=50))
        self.assertEqual(self.data.grounded.review(job['id'],self.decision(job))['record']['id'],record['id'])

    def test_malformed_grounding_truncation_and_oversize_never_admitted(self):
        for mode in ('invalid_quote','wrong_label','duplicate','truncated','oversized','provider_error'):
            with self.subTest(mode=mode):
                job=self.generate(mode);self.assertEqual(job['status'],'failed');self.assertEqual(job['candidates'],[])
                self.assertEqual(self.data.workbench.query({})['total'],1)
                self.assertTrue(job['error'])

    def test_unavailable_or_image_model_rejected_before_inference(self):
        for model in ('image-only','missing'):
            job=self.generate(model=model);self.assertEqual(job['status'],'failed')
        self.assertEqual(self.requests,[])

    def test_source_revisions_and_review_required(self):
        config=self.config();config['revision']-=1
        with self.assertRaises(WorkbenchError):self.data.grounded.start(config)
        job=self.generate();self.source=self.review(self.source)
        with self.assertRaises(WorkbenchError):self.data.grounded.review(job['id'],self.decision(job))
        row=self.data.workbench.import_asset(dict(kind='text',text='draft source',groups=['draft']))
        config=self.config();config.update(source_id=row['id'],revision=row['revision'],source_revision=row['source_revision'])
        with self.assertRaises(WorkbenchError):self.data.grounded.start(config)

    def test_atomic_admission_and_rejection_revision(self):
        job=self.generate();before=self.data.workbench.query({})['total']
        with patch.object(self.data.grounded,'_save',side_effect=RuntimeError('simulated commit failure')):
            with self.assertRaises(RuntimeError):self.data.grounded.review(job['id'],self.decision(job))
        self.assertEqual(self.data.workbench.query({})['total'],before)
        self.assertEqual(self.data.grounded.get(job['id'])['candidates'][0]['status'],'pending_review')
        rejected=self.data.grounded.review(job['id'],self.decision(job,decision='reject'))['job']
        self.assertEqual(rejected['candidates'][0]['status'],'rejected')
        with self.assertRaises(WorkbenchError):self.data.grounded.review(job['id'],self.decision(job,index=1))
        with self.assertRaises(WorkbenchError):self.data.grounded.review(job['id'],self.decision(rejected))

    def test_cancel_transport_late_output_and_reopen(self):
        config=self.config();config['instruction']='slow';job=self.data.grounded.start(config)
        deadline=time.monotonic()+3
        while not self.requests and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(self.requests)
        with self.assertRaises(WorkbenchError):self.data.grounded.start(self.config())
        stopping=self.data.grounded.cancel(job['id']);self.assertTrue(stopping['cancelled'])
        self.data.grounded.worker.join(3);self.assertFalse(self.data.grounded.worker.is_alive())
        final=self.data.grounded.get(job['id']);self.assertEqual(final['status'],'cancelled');self.assertGreater(final['revision'],stopping['job']['revision'])
        self.assertEqual(final['candidates'],[])
        self.data.close();self.data=Dataset(self.tmp.name)
        self.assertEqual(self.data.grounded.get(job['id'])['status'],'cancelled')
        with self.data.lock,self.data.db:
            final['status']='generating';self.data.grounded._save(final)
        self.data.close();self.data=Dataset(self.tmp.name)
        self.assertEqual(self.data.grounded.get(job['id'])['status'],'interrupted')
        self.assertIsNone(self.data.grounded.worker)

    def test_admitted_identity_and_pending_candidates_survive_reopen(self):
        job=self.generate();record=self.data.grounded.review(job['id'],self.decision(job))['record']
        self.data.close();self.data=Dataset(self.tmp.name)
        restored=self.data.grounded.get(job['id'])
        self.assertEqual(restored['candidates'][0]['record_id'],record['id'])
        self.assertEqual(restored['candidates'][1]['status'],'pending_review')
        self.assertEqual(self.data.grounded.review(job['id'],self.decision(job))['record']['id'],record['id'])

    def test_source_changes_while_provider_runs_are_not_published(self):
        entered,release=threading.Event(),threading.Event()
        source=self.source
        def delayed(job,stop):
            entered.set();release.wait(3)
            return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'candidates':[
                {'text':source['text']+' rewrite '+str(i),'label':'cancel','evidence':[{'start':0,'end':len(source['text']),'quote':source['text']}]} for i in range(2)]})}}]}).encode()
        with patch('grounded_candidates.complete',side_effect=delayed):
            job=self.data.grounded.start(self.config());self.assertTrue(entered.wait(3));self.source=self.review(self.source);release.set();self.data.grounded.worker.join(3)
        final=self.data.grounded.get(job['id']);self.assertEqual(final['status'],'failed');self.assertEqual(final['candidates'],[])
        self.assertIsNotNone(final['response_sha256'])
        self.assertIn('Source changed',final['error'])

    def test_http_models_jobs_review_and_release_boundary(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.data))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        root=f'http://127.0.0.1:{server.server_port}/api/workbench/'
        def api(path,body=None):
            request=urllib.request.Request((f'http://127.0.0.1:{server.server_port}'+path if path.startswith('/') else root+path),data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:return json.load(response)
        self.assertEqual(api('/api/generation/prompt-models',{'server_url':self.url})['models'],[{'id':'grounded-text-test','name':'grounded-text-test'}])
        started=api('grounded/jobs',self.config());self.data.grounded.worker.join(3)
        job=api('grounded/jobs/'+started['id']);self.assertEqual(job['status'],'completed')
        self.assertNotIn('raw_response',api('grounded/jobs')['jobs'][0])
        result=api('grounded/review/'+job['id'],self.decision(job));self.assertEqual(result['record']['review'],'draft')
        self.assertEqual(len(api('records')['items']),2)
        self.assertFalse(api('grounded/cancel',{'job_id':job['id']})['cancelled'])

    def test_invalid_ids_and_unicode_fail_without_background_work(self):
        for value in (None,{},[],1,'not-a-job'):
            with self.assertRaises(WorkbenchError):self.data.grounded.cancel(value)
        config=self.config();config['model']='bad\ud800'
        with self.assertRaises(ValueError):self.data.grounded.start(config)
        self.assertIsNone(self.data.grounded.worker)
