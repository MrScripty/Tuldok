"""PR54 exact contract fixtures, HTTP failure boundaries and existing owners."""
import copy
import hashlib
import json
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from app import Dataset
import pumas_operations as pumas
import image_generation
from fake_pumas_typed import FIXTURES, start
from workbench import WorkbenchError, encode


class TypedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.data = Dataset(self.tmp.name); self.addCleanup(self.data.close)
        self.server, self.url, self.state = start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.row = self.data.workbench.import_asset({'kind':'text','name':'Positive','text':'The meeting is confirmed.',
            'groups':['authored-family'],'rights':'Authored controlled fixture'})
    def body(self, **changes):
        body = dict(request_id=uuid.uuid4().hex,source_id=self.row['id'],revision=self.row['revision'],source_revision=self.row['source_revision'],
            server_url=self.url,model='controlled-text',instruction='Classify exactly.',labels=['positive','negative'],seed=None,protocol=pumas.PROTOCOL,profile=None)
        body.update(changes); return body
    def generate(self, body=None):
        owner = self.data.text_classification_proposals
        job = owner.start(body or self.body()); owner.worker.join(4)
        self.assertFalse(owner.worker.is_alive())
        return owner.get(job['id'])
    def image(self, **changes):
        body = dict(server_url=self.url,request_id=uuid.uuid4().hex,model='controlled-image',prompt='Literal blue fixture.',
            width=16,height=12,seed=7,protocol=pumas.PROTOCOL,profile=None)
        body.update(changes); return body
    def test_selected_profile_exact_request_evidence_local_dedup_draft_history(self):
        body=self.body(); job=self.generate(body)
        self.assertEqual(job['status'],'completed',job['error'])
        request=self.state['requests'][0]
        self.assertEqual(request['profile'],'controlled-text-cpu')
        self.assertEqual(request['model'],'controlled-text'); self.assertFalse(request['stream'])
        self.assertEqual(set(request['options']),{'kind','max_tokens'})
        self.assertNotIn('seed',request); self.assertNotIn('response_format',request)
        self.assertEqual(job['canonical_request'],request)
        self.assertEqual(job['canonical_request_sha256'],hashlib.sha256(encode(request).encode()).hexdigest())
        self.assertEqual(self.data.workbench.get(self.row['id']),self.row)
        self.data.text_classification_proposals.start(body)
        self.assertEqual(len(self.state['requests']),1)
        with self.assertRaises(WorkbenchError): self.data.text_classification_proposals.start(dict(body,profile='foreign'))
        result=self.data.text_classification_proposals.decide(job['id'],{'revision':job['revision'],'decision':'apply_draft','labels':body['labels']})
        row=result['record']; self.assertEqual(row['review'],'draft'); self.assertEqual(row['groups'],self.row['groups'])
        self.assertEqual(row['target_proposal']['capability_observation'],job['capability_observation'])
        self.assertEqual(row['provenance'],self.row['provenance'])
        self.assertEqual(row['source_revision'],self.row['source_revision'])
    def test_unavailable_and_wrong_profile_have_no_provider_effects(self):
        for mode in ('unavailable','wrong_profile'):
            with self.subTest(mode=mode):
                self.state['mode']=mode; job=self.generate(self.body(profile='controlled-text-cpu'))
                self.assertEqual(job['status'],'failed'); self.assertEqual(job['provider_outcome'],'not_admitted')
                self.assertFalse(self.state['requests'])
    def test_malformed_transport_and_uncertain_failures_are_never_replayed(self):
        for mode in ('loss','truncated','wrong_id','wrong_kind','length','nonfinite','oversized','not_admitted','unknown'):
            with self.subTest(mode=mode):
                self.state['mode']=mode; body=self.body(); before=len(self.state['requests']); job=self.generate(body)
                self.assertEqual(job['status'],'failed'); self.assertEqual(job['provider_outcome'],'not_admitted' if mode=='not_admitted' else 'unknown')
                self.data.text_classification_proposals.start(body)
                self.assertEqual(len(self.state['requests']),before+1)
                self.assertIsNone(self.data.workbench.get(self.row['id'])['annotation'])
    def test_finite_generation_has_no_discovery_elapsed_deadline_and_cancel_drains(self):
        self.state['mode']='delay'
        with patch('pumas_operations.time.monotonic',return_value=0):
            self.assertEqual(self.generate()['status'],'completed')
        self.state['mode']='hold'; self.state['entered'].clear()
        owner=self.data.text_classification_proposals; job=owner.start(self.body())
        self.assertTrue(self.state['entered'].wait(2)); owner.cancel({'job_id':job['id']}); owner.worker.join(2)
        self.assertFalse(owner.worker.is_alive()); self.assertIsNone(owner.active_id)
        self.assertEqual(owner.get(job['id'])['provider_outcome'],'unknown'); self.state['release'].set()
    def test_typed_image_native_png_existing_batch_owner_provenance(self):
        result=self.data.image_requests.generate(self.image())
        self.assertEqual((result['width'],result['height']),(16,12))
        self.assertEqual(result['metadata']['canonical_request']['profile'],'controlled-image-cpu')
        batch=self.data.generation_jobs.start(dict(self.image(),count=1,strategy='repeat',session_id='fixture-family',split='unassigned'))
        self.data.generation_jobs.worker.join(3)
        job=self.data.generation_jobs.snapshot()['jobs'][0]; self.assertEqual(job['status'],'completed',job['error'])
        row=self.data.workbench.query({})['items'][0]
        if row['kind']!='image': row=next(r for r in self.data.workbench.query({})['items'] if r['kind']=='image')
        row=self.data.workbench.get(row['id']); self.assertEqual(row['review'],'draft')
        self.assertEqual(row['provenance']['generation']['metadata']['protocol'],pumas.PROTOCOL)
        entry=self.data.generation_jobs.snapshot()['entries'][0]
        self.assertEqual(entry['attempt_evidence']['canonical_request']['profile'],'controlled-image-cpu')
    def test_image_bounds_and_unsupported_options_reject_before_post(self):
        for changes in ({'width':2049},{'width':True},{'height':0},{'profile':'bad/profile'},{'seed':float('nan')}):
            with self.subTest(changes=changes),self.assertRaises(ValueError): self.data.image_requests.generate(self.image(**changes))
        with self.assertRaises(ValueError): self.data.generation_jobs.start(dict(self.image(),count=1,strategy='varied'))
        with self.assertRaises(ValueError): self.data.text_classification_proposals.start(self.body(seed=7))
        self.assertFalse(self.state['requests'])
    def test_malformed_png_returns_http400_without_admission_or_replay(self):
        from http.server import ThreadingHTTPServer
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        from app import make_handler
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.data))
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:' + str(server.server_port) + '/api/generation/generate'
        before = list(self.data.db.iterdump())
        self.state['mode'] = 'malformed_png'
        body = self.image()
        request = Request(url, encode(body).encode(), {'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as rejected:
            urlopen(request, timeout=3)
        self.assertEqual(rejected.exception.code, 400)
        error = json.loads(rejected.exception.read())
        self.assertIn('invalid PNG', error['error'])
        self.assertEqual(list(self.data.db.iterdump()), before)
        self.assertEqual(len(self.state['requests']), 1)
        self.assertFalse(self.data.image_requests.active)
        self.assertFalse(self.data.db.execute('SELECT id FROM samples').fetchall())
        self.state['mode'] = 'success'
        request = Request(url, encode(self.image()).encode(), {'Content-Type': 'application/json'})
        with urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['width'], 16)
        self.assertEqual(len(self.state['requests']), 2)
    def test_uncertain_image_batch_cannot_resume_provider_attempt(self):
        self.state['mode']='unknown'
        job=self.data.generation_jobs.start(dict(self.image(),count=1,strategy='repeat',session_id='fixture-family',split='unassigned'))
        self.data.generation_jobs.worker.join(3)
        with self.assertRaises(ValueError): self.data.generation_jobs.resume(job['id'])
        self.assertEqual(len(self.state['requests']),1)
        retained=self.data.generation_jobs.snapshot()['jobs'][0]
        self.assertEqual(retained['canonical_request']['profile'],'controlled-image-cpu')
    def test_restart_preserves_unresolved_image_attempt_and_prevents_replay(self):
        owner=self.data.generation_jobs
        config=dict(self.image(),count=1,strategy='repeat',session_id='fixture-family',split='unassigned')
        import synthetic
        job=dict(id=uuid.uuid4().hex,config=synthetic.validate(config),meta={},status='generating',error='',completed=0)
        entry=owner._new_entry(job,0,config['prompt']); entry.update(status='generating',request_id='retained-attempt')
        with self.data.lock,self.data.db: owner._save(job); owner._entry(entry)
        self.data.close(); self.data=Dataset(self.tmp.name); self.addCleanup(self.data.close)
        saved=self.data.generation_jobs.snapshot()['entries'][0]
        self.assertEqual(saved['request_id'],'retained-attempt'); self.assertEqual(saved['provider_outcome'],'unknown')
        with self.assertRaises(ValueError): self.data.generation_jobs.resume(job['id'])
        self.assertFalse(self.state['requests'])
    def test_cancel_before_sample_commit_admits_no_image(self):
        owner=self.data.generation_jobs
        image=self.data.image_requests.generate(self.image())
        def cancelled_generate(*args,**kwargs):
            active=next(job for job in owner.snapshot()['jobs'] if job['status']=='generating')
            self.assertTrue(owner.cancel(active['id'])['cancelled'])
            return image
        with patch.object(self.data.image_requests,'generate',side_effect=cancelled_generate):
            job=owner.start(dict(self.image(),count=1,strategy='repeat',session_id='fixture-family',split='unassigned'))
            owner.worker.join(3)
        self.assertEqual(owner.snapshot()['jobs'][0]['status'],'cancelled')
        self.assertFalse(self.data.db.execute('SELECT id FROM samples').fetchall())
        with self.assertRaises(ValueError):owner.resume(job['id'])
    def test_image_actor_start_failure_retires_admission_slot(self):
        owner=self.data.image_requests
        with patch('image_generation.threading.Thread.start',side_effect=RuntimeError('actor start unavailable')):
            with self.assertRaises(RuntimeError):owner.generate(self.image(),cancel_event=threading.Event())
        self.assertFalse(owner.active);self.assertFalse(self.state['requests'])
        self.assertEqual(owner.generate(self.image())['width'],16)
    def test_grounded_rewrite_stays_in_source_family_and_draft(self):
        row=self.data.workbench.save(self.row['id'],dict(revision=self.row['revision'],source_revision=self.row['source_revision'],
            task='text_classification',annotation={'label':'positive'},groups=self.row['groups'],review='human_reviewed'))
        self.state['content']=json.dumps({'candidates':[{'text':'The confirmed meeting will take place.','label':'positive',
            'evidence':[{'start':0,'end':25,'quote':row['text']}]}]})
        body=self.body(); body={k:v for k,v in body.items() if k not in ('request_id','labels')}; body.update(revision=row['revision'],count=1)
        job=self.data.grounded.start(body); self.data.grounded.worker.join(3); job=self.data.grounded.get(job['id'])
        self.assertEqual(job['status'],'completed',job['error'])
        record=self.data.grounded.review(job['id'],{'revision':job['revision'],'candidate_id':job['candidates'][0]['id'],
            'decision':'admit_draft','note':'Authored control inspected.'})['record']
        self.assertEqual(record['review'],'draft'); self.assertEqual(record['parents'],[row['id']])
        self.assertEqual(record['groups'],row['groups']); self.assertEqual(record['provenance']['rights'],row['provenance']['rights'])
        self.assertEqual(record['provenance']['canonical_request']['profile'],'controlled-text-cpu')
    def test_manifest_hash_closed_semantics_nonfinite_intervals(self):
        raw=(FIXTURES/'controlled-text-capabilities.json').read_bytes(); observed=pumas.validate_manifest(raw)
        self.assertEqual(observed['observed_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(pumas.models(self.url)['models'][0]['id'],'controlled-text')
        self.state['duplicate_alias']=True
        self.assertEqual(len(pumas.models(self.url)['models']),2)
        for mutate in (lambda v:v.update(extra=1),lambda v:v['capabilities'][0].update(capability={}),
                       lambda v:v['capabilities'][0]['option_bounds'][0].update(minimum=10**500),
                       lambda v:v['capabilities'][0]['option_bounds'][0].update(minimum=10,maximum=1),
                       lambda v:v['capabilities'][0].update(availability={'state':'unavailable','reason':{}})):
            value=copy.deepcopy(observed['capabilities']); mutate(value)
            with self.assertRaises(ValueError): pumas.validate_manifest(json.dumps(value).encode())
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{','{"x":1}'.encode('utf-16')):
            with self.assertRaises(ValueError): pumas.strict_json(raw)


if __name__=='__main__': unittest.main()
