"""Synthetic HTTP classification contracts; no model downloads or inference."""
import base64
import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Dataset, make_handler
from fake_classification_model import start
from workbench import WorkbenchError


class TextClassificationProposalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.data = Dataset(self.tmp.name); self.addCleanup(lambda: self.data.close())
        self.server, self.url, self.requests = start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.row = self.data.workbench.import_asset(dict(kind='text', name='Request', text='Please cancel the café meeting 😀.\nKeep exact source.', groups=['authored-1'], rights='Authored synthetic fixture'))
        self.labels = ['cancel', 'keep', 'café 😀']

    @property
    def owner(self): return self.data.text_classification_proposals

    def config(self, **changes):
        body = dict(request_id=uuid.uuid4().hex, source_id=self.row['id'], revision=self.row['revision'], source_revision=self.row['source_revision'],
                    server_url=self.url, model='classification-fixture', instruction='Classify the exact request', seed=42, labels=list(self.labels))
        body.update(changes); return body

    def generate(self, **changes):
        job = self.owner.start(self.config(**changes)); self.owner.worker.join(5)
        self.assertFalse(self.owner.worker.is_alive())
        return self.owner.get(job['id'])

    def decide(self, job, decision='apply_draft', **changes):
        body = dict(revision=job['revision'], decision=decision)
        if decision == 'apply_draft': body['labels'] = list(self.labels)
        body.update(changes)
        return self.owner.decide(job['id'], body)

    def state(self):
        return [list(self.data.db.execute('SELECT * FROM '+name+' ORDER BY rowid')) for name in
                ('workbench_records', 'workbench_history', 'workbench_target_proposals', 'text_classification_proposals')]

    def wait(self, predicate):
        end = time.monotonic() + 3
        while not predicate():
            if time.monotonic() > end: self.fail('Timed out waiting for bounded synthetic worker')
            time.sleep(.01)

    def test_exact_http_frozen_evidence_and_atomic_idempotent_draft(self):
        before = self.data.workbench.get(self.row['id']); job = self.generate()
        self.assertEqual(job['status'], 'completed', job['error']); self.assertEqual(job['annotation'], {'label': 'cancel'})
        self.assertEqual(self.data.workbench.get(self.row['id']), before)
        observed = self.requests[0]; self.assertEqual(observed['path'], '/v1/chat/completions')
        wire = observed['body']; brief = json.loads(wire['messages'][1]['content'])
        self.assertEqual(brief, dict(instruction=job['config']['instruction'], labels=self.labels, text=before['text']))
        self.assertEqual((wire['model'], wire['seed']), ('classification-fixture', 42))
        self.assertEqual(wire['messages'][0]['content'], job['system_prompt'])
        self.assertEqual(job['source'], before)
        self.assertEqual(hashlib.sha256(json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(), job['canonical_request_sha256'])
        raw = base64.b64decode(job['raw_response_base64'], validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), job['response_sha256'])
        self.assertNotIn('raw_response_base64', self.owner.snapshot()['jobs'][0])
        result = self.decide(job); row = result['record']
        self.assertEqual((row['task'], row['annotation'], row['review']), ('text_classification', {'label': 'cancel'}, 'draft'))
        self.assertEqual(row['revision'], before['revision']+1)
        for key in ('id', 'text', 'content_hash', 'source_sha256', 'groups', 'parents', 'provenance', 'source_revision'):
            self.assertEqual(row[key], before[key], key)
        self.assertEqual(row['target_proposal']['job_id'], job['id'])
        state = self.state(); again = self.decide(job)
        self.assertFalse(again['changed']); self.assertEqual(self.state(), state)
        self.data.close(); self.data = Dataset(self.tmp.name)
        self.assertEqual(self.owner.get(job['id'])['application']['revision'], row['revision'])
        self.assertEqual(self.data.workbench.get(row['id'])['target_proposal'], row['target_proposal'])
        self.assertFalse(self.decide(job)['changed'])

    def test_provider_transport_normalization_preserves_exact_author_configuration(self):
        guidance = '  exact guidance\n'
        job = self.generate(server_url=self.url+'/v1/', instruction=guidance)
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['config']['requested_server_url'], self.url+'/v1/')
        self.assertEqual(job['config']['server_url'], self.url)
        self.assertEqual(job['config']['requested_model'], 'classification-fixture')
        self.assertEqual(job['config']['instruction'], guidance)
        self.assertEqual(json.loads(self.requests[0]['body']['messages'][1]['content'])['instruction'], guidance)
        self.assertEqual(self.decide(job)['record']['review'], 'draft')

    def test_admission_id_reconciles_and_rejects_changed_request(self):
        body = self.config(); job = self.owner.start(body); self.owner.worker.join(3)
        count = len(self.requests); self.assertEqual(self.owner.start(body)['id'], job['id']); self.assertEqual(len(self.requests), count)
        for key, value in [('labels', ['keep', 'cancel']), ('instruction', 'changed'), ('model', 'other')]:
            with self.assertRaises(WorkbenchError): self.owner.start(dict(body, **{key: value}))

    def test_unknown_malformed_partial_labels_never_guess_or_mutate(self):
        before = self.data.workbench.get(self.row['id']); history = list(self.data.db.execute('SELECT * FROM workbench_history'))
        for mode in ('unknown', 'empty', 'number', 'list', 'null', 'extra', 'false-abstain', 'mixed', 'string-abstain', 'unicode', 'duplicate', 'malformed', 'oversized', 'truncated', 'tools', 'short-body', 'provider_error'):
            with self.subTest(mode=mode):
                job = self.generate(instruction=mode); self.assertEqual(job['status'], 'failed', job); self.assertIsNone(job['annotation'])
                self.assertEqual(self.data.workbench.get(self.row['id']), before)
                self.assertEqual(list(self.data.db.execute('SELECT * FROM workbench_history')), history)
                with self.assertRaises(WorkbenchError): self.decide(job)

    def test_missing_and_image_generation_models_fail_before_chat(self):
        for model in ('missing', 'image-only'):
            job = self.generate(model=model)
            self.assertEqual(job['status'], 'failed', job)
            self.assertIsNone(job['annotation'])
        self.assertEqual(self.requests, [])
        self.assertIsNone(self.data.workbench.get(self.row['id'])['annotation'])

    def test_explicit_abstention_retains_evidence_unappliable_and_rejectable(self):
        before = self.data.workbench.get(self.row['id']); job = self.generate(instruction='abstain')
        self.assertEqual(job['status'], 'abstained', job); self.assertIsNone(job['annotation']); self.assertTrue(job['response_sha256'])
        with self.assertRaises(WorkbenchError): self.decide(job)
        self.assertEqual(self.data.workbench.get(self.row['id']), before)
        self.assertTrue(self.decide(job, 'reject')['changed']); self.assertFalse(self.decide(job, 'reject')['changed'])
        self.data.close(); self.data = Dataset(self.tmp.name)
        self.assertEqual(self.owner.get(job['id'])['status'], 'rejected'); self.assertEqual(self.data.workbench.get(self.row['id']), before)

    def test_exact_labels_are_validated_before_admission_and_apply(self):
        for labels in (None, [], ['cancel']*2, [1], [True], [''], [' cancel'], ['cancel '], ['x'*81], ['\ud800'], ['x'+str(i) for i in range(31)]):
            with self.subTest(labels=repr(labels)):
                with self.assertRaises((WorkbenchError, ValueError)): self.owner.start(self.config(labels=labels))
        self.assertEqual(self.requests, [])
        job = self.generate(); state = self.state()
        for labels in (['keep', 'cancel', 'café 😀'], ['cancel', 'keep'], ['cancel', 'keep', 'cafe 😀']):
            with self.assertRaises(WorkbenchError): self.decide(job, labels=labels)
            self.assertEqual(self.state(), state)
        self.assertTrue(self.decide(job)['changed'])

    def test_annotated_record_and_stale_revision_rejected(self):
        with self.assertRaises(WorkbenchError): self.owner.start(self.config(revision=self.row['revision']+1))
        self.row = self.data.workbench.save(self.row['id'], dict(self.row, annotation={'label': 'keep'}, review='draft'))
        with self.assertRaises(WorkbenchError): self.owner.start(self.config())
        self.assertEqual(self.requests, [])

    def test_source_same_revision_text_change_deletion_and_target_change_block_apply(self):
        for action in ('text', 'original_text', 'target', 'delete'):
            with self.subTest(action=action):
                self.row = self.data.workbench.import_asset(dict(kind='text', text='unique '+action, groups=[action]))
                job = self.generate()
                if action in ('text', 'original_text'):
                    with self.data.lock, self.data.db:
                        self.data.db.execute('UPDATE workbench_records SET '+action+'=? WHERE id=?', ('changed exact source', self.row['id']))
                elif action == 'target':
                    self.data.workbench.save(self.row['id'], dict(self.row, annotation={'label': 'keep'}, review='draft'))
                else:
                    with self.data.lock, self.data.db: self.data.db.execute('DELETE FROM workbench_records WHERE id=?', (self.row['id'],))
                state = self.state()
                with self.assertRaises(WorkbenchError): self.decide(job)
                self.assertEqual(self.state(), state)

    def test_inflight_source_change_never_publishes_completed_proposal(self):
        entered, release = threading.Event(), threading.Event()
        from text_classification_proposals import complete
        def held(job, stop):
            raw = complete(job, stop); entered.set(); release.wait(3); return raw
        with patch('text_classification_proposals.complete', side_effect=held):
            job = self.owner.start(self.config()); self.assertTrue(entered.wait(3))
            with self.data.lock, self.data.db: self.data.db.execute('UPDATE workbench_records SET text=? WHERE id=?', ('changed', self.row['id']))
            release.set(); self.owner.worker.join(3)
        final = self.owner.get(job['id']); self.assertEqual(final['status'], 'failed'); self.assertIsNone(final['annotation']); self.assertTrue(final['response_sha256'])

    def test_atomic_failure_and_concurrent_apply_commit_once(self):
        job = self.generate(); state = self.state()
        with patch.object(self.owner, '_save', side_effect=RuntimeError('synthetic linkage failure')):
            with self.assertRaises(RuntimeError): self.decide(job)
        self.assertEqual(self.state(), state)
        results, errors = [], []
        def apply():
            try: results.append(self.decide(job))
            except Exception as error: errors.append(error)
        workers = [threading.Thread(target=apply) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(3); self.assertFalse(worker.is_alive())
        self.assertEqual(errors, []); self.assertEqual(sum(result['changed'] for result in results), 1)
        self.assertEqual(self.data.workbench.get(self.row['id'])['revision'], self.row['revision']+1)

    def test_cancel_catalog_body_late_output_and_restart_without_retry(self):
        for mode in ('slow', 'slow-body'):
            count = len(self.requests); job = self.owner.start(self.config(instruction=mode)); self.wait(lambda:len(self.requests)>count)
            with self.assertRaises(WorkbenchError): self.owner.start(self.config())
            self.assertTrue(self.owner.cancel({'job_id':job['id']})['cancelled']); self.owner.worker.join(3)
            self.assertFalse(self.owner.worker.is_alive()); self.assertEqual(self.owner.get(job['id'])['status'], 'cancelled')
        entered = threading.Event(); server, url, requests = start(entered)
        try:
            job = self.owner.start(self.config(server_url=url)); self.assertTrue(entered.wait(3)); self.owner.cancel({'job_id':job['id']}); self.owner.worker.join(3)
            self.assertFalse(self.owner.worker.is_alive()); self.assertEqual(requests, [])
        finally: server.shutdown(); server.server_close()
        entered, release = threading.Event(), threading.Event()
        from text_classification_proposals import complete
        def held(job, stop):
            raw = complete(job, stop); entered.set(); release.wait(3); return raw
        with patch('text_classification_proposals.complete', side_effect=held):
            job = self.owner.start(self.config()); self.assertTrue(entered.wait(3)); self.owner.cancel({'job_id':job['id']}); release.set(); self.owner.worker.join(3)
        self.assertEqual(self.owner.get(job['id'])['status'], 'cancelled')
        with self.data.lock, self.data.db:
            interrupted = self.owner.get(job['id']); interrupted['status']='generating'; self.owner._save(interrupted)
        count = len(self.requests); self.data.close(); self.data = Dataset(self.tmp.name)
        self.assertEqual(self.owner.get(job['id'])['status'], 'interrupted'); self.assertEqual(len(self.requests), count)
        self.assertEqual(self.generate()['status'], 'completed')

    def test_fixed_export_selection_stale_draft_requires_review_and_receipt_survives(self):
        ref = lambda row: {key:row[key] for key in ('id', 'revision', 'source_revision')}
        fixed = self.data.selections.create({'name':'Fixed text set', 'items':[ref(self.row)]})
        job = self.generate(); row = self.decide(job)['record']
        self.assertFalse(self.data.selections.load(fixed['id'])['current'])
        self.assertEqual(self.data.selections.load(fixed['id'])['members'][0]['status'], 'stale')
        body = lambda row: dict(items=[ref(row)], seed=42, ratios=dict(train=100, validation=0, test=0))
        self.assertFalse(self.data.releases.preview(body(row))['eligible'])
        with self.assertRaises(WorkbenchError): self.data.releases.create(body(row))
        row = self.data.workbench.save(row['id'], dict(row, review='human_reviewed'))
        release = self.data.releases.create(body(row))
        with zipfile.ZipFile(self.data.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json')); frozen = manifest['records'][0]
            self.assertEqual(frozen['target_proposal']['job_id'], job['id']); self.assertEqual(frozen['annotation'], {'label':'cancel'})
            self.assertEqual(json.loads(archive.read('train/records.jsonl'))['text'], row['text'])

    def test_summary_projects_large_evidence_and_source_without_decoding_retained_payloads(self):
        owner = self.owner; original = self.generate(); full_text = 'S' * 200000
        response = base64.b64encode(b'R' * (256 * 1024)).decode()
        ids = []
        with owner.lock, owner.db:
            for index in range(51):
                job = dict(original, id=uuid.uuid4().hex, source=dict(original['source'], text=full_text), raw_response_base64=response)
                owner._save(job); ids.append(job['id'])
        before = self.state(); decode = json.loads; sizes = []
        def projected(data, *args, **kwargs):
            self.assertNotIn('"raw_response_base64"', data)
            self.assertNotIn(full_text[:1000], data)
            sizes.append(len(data)); return decode(data, *args, **kwargs)
        with patch('text_classification_proposals.json.loads', side_effect=projected):
            summary = owner.snapshot()['jobs']
        self.assertEqual([job['id'] for job in summary], list(reversed(ids[-50:])))
        self.assertEqual(len(sizes), 50); self.assertLess(max(sizes), 10000)
        self.assertEqual(self.state(), before)
        self.assertEqual(owner.get(ids[-1])['source']['text'], full_text)
        self.assertEqual(owner.get(ids[-1])['raw_response_base64'], response)
        self.assertEqual(len(self.requests), 1)

    def test_unicode_labels_have_exact_no_normalization_identity(self):
        self.labels = ['cafe\u0301', 'café', '雪 😀']
        job = self.generate()
        self.assertEqual(job['annotation'], {'label': 'cafe\u0301'})
        self.assertEqual(job['config']['labels'], self.labels)
        self.assertEqual(self.decide(job)['record']['annotation'], {'label': 'cafe\u0301'})

    def test_http_routes_and_exact_admission_id_404_before_start(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.data)); threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        root = f'http://127.0.0.1:{server.server_port}/api/workbench/text-classification-proposals'
        def api(path='', body=None):
            request = urllib.request.Request(root+path, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response: return json.load(response)
        body = self.config()
        with self.assertRaises(urllib.error.HTTPError) as early: api('/'+body['request_id'])
        self.assertEqual(early.exception.code, 404)
        started = api(body=body); self.owner.worker.join(3); job = api('/'+started['id'])
        self.assertEqual(job['id'], body['request_id']); self.assertEqual(api(body=body)['id'], job['id']); self.assertEqual(len(self.requests), 1)
        self.assertNotIn('raw_response_base64', api()['jobs'][0])
        applied = api('/decide/'+job['id'], dict(revision=job['revision'], decision='apply_draft', labels=self.labels))
        self.assertEqual(applied['record']['review'], 'draft')
        self.assertFalse(api('/cancel', {'job_id':job['id']})['cancelled'])
