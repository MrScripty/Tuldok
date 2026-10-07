"""Independent bounded review probe. Only temporary SQLite and synthetic localhost HTTP."""
import base64
import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from app import Dataset, make_handler
from fake_classification_model import start
from text_classification_proposals import decode, payload
from workbench import WorkbenchError, encode


class BackendReview(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.data.close())
        self.model, self.url, self.requests = start()
        self.addCleanup(self.model.server_close)
        self.addCleanup(self.model.shutdown)
        self.row = self.data.workbench.import_asset(dict(kind='text', name='Independent café',
            text='Keep the café meeting.\r\n雪 😀', groups=['author-fixture'], rights='Synthetic author source'))
        self.owner = self.data.text_classification_proposals

    def body(self, **changes):
        result = dict(request_id=uuid.uuid4().hex, source_id=self.row['id'], revision=self.row['revision'],
            source_revision=self.row['source_revision'], server_url=self.url, model='classification-fixture',
            instruction='  exact author guidance\n', seed=4, labels=['Keep', 'keep', 'café', 'cafe\u0301', '雪'])
        result.update(changes)
        return result

    def generate(self, **changes):
        body = self.body(**changes)
        job = self.owner.start(body)
        self.owner.worker.join(4)
        self.assertFalse(self.owner.worker.is_alive())
        return self.owner.get(job['id']), body

    def decide(self, job, **changes):
        body = dict(revision=job['revision'], decision='apply_draft', labels=job['config']['labels'])
        body.update(changes)
        return self.owner.decide(job['id'], body)

    def db_state(self):
        return {name: [tuple(row) for row in self.data.db.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
            for name in ('workbench_records', 'workbench_history', 'workbench_target_proposals', 'text_classification_proposals')}

    def test_decode_exact_membership_and_exclusive_abstention(self):
        def envelope(content):
            return json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]}).encode()
        for content in ('{"label":"Keep"}', '{"label":"keep"}', '{"label":"café"}', '{"label":"cafe\\u0301"}', '{"label":"雪"}'):
            self.assertEqual(decode(envelope(content), self.body()['labels'])[0], json.loads(content))
        self.assertIsNone(decode(envelope('{"abstain":true}'), self.body()['labels'])[0])
        for content in ('{"label":"KEEP"}', '{"label":" Keep"}', '{"label":"unknown"}',
                '{"label":true}', '{"label":null}', '{"label":[]}', '{"abstain":1}',
                '{"abstain":"true"}', '{"abstain":false}', '{"abstain":true,"label":"Keep"}',
                '{"label":"Keep","label":"keep"}', '{"label":"Keep","reason":"yes"}', '[]', '{}', '{'):
            with self.subTest(content=content), self.assertRaises(WorkbenchError):
                decode(envelope(content), self.body()['labels'])

    def test_http_admission_recovery_freeze_apply_and_replay(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.data))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port) + '/api/workbench/text-classification-proposals'
        body = self.body()
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + '/' + body['request_id'])
        self.assertEqual(error.exception.code, 404)
        def post(url, value):
            request = urllib.request.Request(url, data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        status, admitted = post(base, body)
        self.assertEqual(status, 202)
        self.owner.worker.join(4)
        job = json.load(urllib.request.urlopen(base + '/' + body['request_id']))
        self.assertEqual(job['status'], 'completed', job['error'])
        post(base, body)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.data.workbench.get(self.row['id']), self.row)
        self.assertEqual(job['config']['instruction'], body['instruction'])
        self.assertEqual(job['config']['labels'], body['labels'])
        self.assertEqual(job['source']['text'], self.row['text'])
        self.assertEqual(self.requests[0]['body'], payload(job))
        self.assertEqual(job['canonical_request_sha256'], hashlib.sha256(encode(payload(job)).encode()).hexdigest())
        self.assertEqual(job['response_sha256'], hashlib.sha256(base64.b64decode(job['raw_response_base64'])).hexdigest())
        result = self.decide(job)
        row = result['record']
        self.assertEqual((row['annotation'], row['review'], row['revision']), ({'label': 'Keep'}, 'draft', self.row['revision'] + 1))
        for key in ('provenance', 'parents', 'groups', 'text', 'content_hash', 'source_sha256', 'source_revision'):
            self.assertEqual(row[key], self.row[key], key)
        self.assertEqual(self.data.workbench.history(row['id'])[0]['target_proposal'], row['target_proposal'])
        state = self.db_state()
        self.assertFalse(self.decide(job)['changed'])
        self.assertEqual(state, self.db_state())
        self.data.close(); self.data = Dataset(self.tmp.name)
        self.owner = self.data.text_classification_proposals
        self.assertFalse(self.decide(job)['changed'])
        self.assertEqual(self.data.workbench.get(row['id'])['target_proposal'], row['target_proposal'])
        self.assertEqual(len(self.requests), 1)

    def test_labels_change_rejection_and_frozen_request_identity(self):
        job, body = self.generate()
        state = self.db_state()
        for labels in (list(reversed(body['labels'])), ['Keep'], body['labels'] + ['other'], None):
            with self.assertRaises(WorkbenchError): self.decide(job, labels=labels)
            self.assertEqual(self.db_state(), state)
        with self.assertRaises(WorkbenchError): self.owner.start(dict(body, labels=list(reversed(body['labels']))))
        self.assertEqual(self.db_state(), state)
        rejected = self.decide(job, decision='reject', labels=['unrelated-current-form'])
        self.assertEqual(rejected['job']['status'], 'rejected')
        self.assertEqual(self.data.workbench.get(self.row['id']), self.row)

    def test_exact_requested_provider_and_model_survive_transport_normalization(self):
        requested_url = '  ' + self.url + '/v1/  '
        requested_model = '  classification-fixture  '
        job, body = self.generate(server_url=requested_url, model=requested_model)
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['config']['requested_server_url'], requested_url)
        self.assertEqual(job['config']['requested_model'], requested_model)
        self.assertEqual(job['config']['server_url'], self.url)
        self.assertEqual(job['config']['model'], 'classification-fixture')
        self.assertEqual(self.owner.start(body)['id'], job['id'])
        row = self.decide(job)['record']
        self.assertEqual(row['target_proposal']['config']['requested_server_url'], requested_url)
        self.assertEqual(row['target_proposal']['config']['requested_model'], requested_model)

    def test_apply_atomic_rollback(self):
        job, _ = self.generate()
        state = self.db_state()
        with patch.object(self.owner, '_save', side_effect=RuntimeError('independent commit fault')):
            with self.assertRaises(RuntimeError): self.decide(job)
        self.assertEqual(self.db_state(), state)
        self.assertTrue(self.decide(job)['changed'])

    def test_source_bytes_hash_origin_and_deletion_conflicts(self):
        for mutation in ('bytes', 'consistent-hash', 'origin', 'delete', 'label'):
            with self.subTest(mutation=mutation):
                job, _ = self.generate()
                with self.data.lock, self.data.db:
                    if mutation == 'delete':
                        self.data.db.execute('DELETE FROM workbench_records WHERE id=?', (self.row['id'],))
                    elif mutation == 'label':
                        self.data.db.execute('UPDATE workbench_records SET annotation_json=? WHERE id=?', ('{"label":"author"}', self.row['id']))
                    elif mutation == 'origin':
                        self.data.db.execute('UPDATE workbench_records SET original_text=? WHERE id=?', ('changed acquisition bytes', self.row['id']))
                    else:
                        text = 'Externally changed text'
                        self.data.db.execute('UPDATE workbench_records SET text=?,content_hash=? WHERE id=?',
                            (text, hashlib.sha256(text.encode()).hexdigest() if mutation == 'consistent-hash' else self.row['content_hash'], self.row['id']))
                state = self.db_state()
                with self.assertRaises(WorkbenchError): self.decide(job)
                self.assertEqual(self.db_state(), state)
                with self.data.lock, self.data.db:
                    # Restore this one fixture directly without granting target review.
                    original = json.loads(self.data.db.execute('SELECT snapshot FROM workbench_history WHERE id=? AND revision=1', (self.row['id'],)).fetchone()[0])
                    if mutation == 'delete':
                        self.row = self.data.workbench.import_asset(dict(kind='text', text='Replacement fixture ' + mutation,
                            groups=['author-fixture'], rights='Synthetic author source'))
                    else:
                        self.data.db.execute('UPDATE workbench_records SET text=?,original_text=?,content_hash=?,annotation_json=NULL WHERE id=?',
                            (original['text'], 'Keep the café meeting.\r\n雪 😀', original['content_hash'], self.row['id']))

    def test_completion_detects_source_change_even_with_recomputed_hash(self):
        entered, release = threading.Event(), threading.Event()
        def held_complete(job, stop):
            entered.set()
            self.assertTrue(release.wait(3))
            return b'{"choices":[{"finish_reason":"stop","message":{"content":"{\\"label\\":\\"Keep\\"}"}}]}'
        with patch('text_classification_proposals.complete', side_effect=held_complete):
            job = self.owner.start(self.body())
            self.assertTrue(entered.wait(3))
            with self.data.lock, self.data.db:
                text = 'Changed before completion'
                self.data.db.execute('UPDATE workbench_records SET text=?,content_hash=? WHERE id=?',
                    (text, hashlib.sha256(text.encode()).hexdigest(), self.row['id']))
            release.set(); self.owner.worker.join(3)
        result = self.owner.get(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(result['annotation'])
        self.assertIsNotNone(result['raw_response_base64'])

    def test_abstention_never_applies(self):
        job, _ = self.generate(instruction='abstain')
        self.assertEqual(job['status'], 'abstained')
        state = self.db_state()
        with self.assertRaises(WorkbenchError): self.decide(job)
        self.assertEqual(self.db_state(), state)
        self.assertEqual(self.decide(job, decision='reject')['job']['status'], 'rejected')
        self.assertEqual(self.data.workbench.get(self.row['id']), self.row)

    def test_cancel_release_then_restart_without_automatic_inference(self):
        job = self.owner.start(self.body(instruction='slow'))
        end = time.monotonic() + 3
        while not self.requests and time.monotonic() < end: time.sleep(.01)
        self.assertTrue(self.requests)
        self.owner.cancel({'job_id': job['id']}); self.owner.worker.join(3)
        self.assertFalse(self.owner.worker.is_alive())
        self.assertEqual(self.owner.get(job['id'])['status'], 'cancelled')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.generate()[0]['status'], 'completed')

    def test_summary_projects_before_decode_and_retains_bounded_order(self):
        job, _ = self.generate()
        with self.owner.lock, self.owner.db:
            ids = []
            for index in range(51):
                copy = dict(job, id=uuid.uuid4().hex, source=dict(job['source'], text='雪' * 200000),
                    raw_response_base64=base64.b64encode(b'R' * 256000).decode(), extension={'note': str(index)})
                self.owner._save(copy); ids.append(copy['id'])
        state = self.db_state()
        original_loads = json.loads
        lengths = []
        def projected(value, *args, **kwargs):
            self.assertNotIn('"raw_response_base64":', value)
            self.assertNotIn('"text":', value)
            lengths.append(len(value))
            return original_loads(value, *args, **kwargs)
        with patch('text_classification_proposals.json.loads', side_effect=projected):
            summary = self.owner.snapshot()
        self.assertEqual([row['id'] for row in summary['jobs']], list(reversed(ids[-50:])))
        self.assertEqual(len(lengths), 50)
        self.assertLess(max(lengths), 10000)
        self.assertEqual(state, self.db_state())
        retained = self.owner.get(ids[-1])
        self.assertEqual(retained['source']['text'], '雪' * 200000)
        self.assertIsNotNone(retained['raw_response_base64'])

    def test_persisted_active_restart_marks_interrupted_without_retry(self):
        job, body = self.generate()
        with self.owner.lock, self.owner.db:
            job['status'] = 'generating'
            self.owner._save(job)
        self.data.close(); self.data = Dataset(self.tmp.name)
        self.owner = self.data.text_classification_proposals
        interrupted = self.owner.get(job['id'])
        self.assertEqual(interrupted['status'], 'interrupted')
        self.assertEqual(interrupted['source'], job['source'])
        self.assertEqual(interrupted['config'], job['config'])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.owner.start(body)['status'], 'interrupted')
        self.assertEqual(len(self.requests), 1)
        with self.assertRaises(WorkbenchError): self.decide(interrupted)

    def test_apply_stales_frozen_selection_and_draft_export_remains_blocked(self):
        refs = [{key: self.row[key] for key in ('id', 'revision', 'source_revision')}]
        saved = self.data.selections.create({'name': 'Independent frozen selection', 'items': refs})
        job, _ = self.generate()
        changed = self.decide(job)['record']
        loaded = self.data.selections.load(saved['id'])
        self.assertFalse(loaded['current'])
        self.assertEqual(loaded['members'][0]['status'], 'stale')
        self.assertEqual(loaded['selection']['items'], saved['items'])
        old_request = {'items': refs, 'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 5}
        with self.assertRaises(WorkbenchError): self.data.releases.create(old_request)
        current_request = dict(old_request, items=[{key: changed[key] for key in ('id', 'revision', 'source_revision')}])
        self.assertFalse(self.data.releases.preview(current_request)['eligible'])
        with self.assertRaises(WorkbenchError): self.data.releases.create(current_request)
        self.assertEqual(list(self.data.releases.path.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
