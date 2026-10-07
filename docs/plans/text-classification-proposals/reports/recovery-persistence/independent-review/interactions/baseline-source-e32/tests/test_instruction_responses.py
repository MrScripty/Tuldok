"""Independent answers, real persistence/HTTP, exact proof and frozen artifacts."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid
import zipfile

from app import Dataset, make_handler
from workbench import WorkbenchError, MAX_TEXT, MAX_SELECTED_TEXT_BYTES


class InstructionResponsesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.d = Dataset(self.path); self.addCleanup(lambda: self.d.close())
        self.w, self.r = self.d.workbench, self.d.releases

    def prompt(self, name='prompt', groups=None, parents=None):
        return self.w.import_asset({'kind': 'text', 'name': name, 'text': 'Prompt '+name+'\r\ne\u0301 😀 ',
                                   'groups': groups or [name], 'parents': parents or [], 'rights': 'Authored fixture'})

    def payload(self, parent, completion=' exact answer\r\ne\u0301 😀\ufeff ', review='human_reviewed', response=None):
        return {'id': response['id'] if response else uuid.uuid4().hex, 'prompt_id': parent['id'],
                'revision': response['revision'] if response else 0, 'parent_revision': parent['revision'],
                'source_revision': parent['source_revision'], 'completion': completion, 'review': review}

    def answer(self, parent, **options):
        return self.w.save_response(self.payload(parent, **options))['response']

    def pair(self, parent, response):
        return {key: value for key, value in self.payload(parent, response=response).items() if key not in ('completion', 'review')}

    def body(self, examples):
        return {'format': 'text_instruction_v1', 'items': [self.pair(parent, response) for parent, response in examples],
                'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 42}

    def export(self, body):
        preview = self.r.preview(body); self.assertTrue(preview['eligible'], preview)
        return self.r.create(dict(body, preview_token=preview['preview_token']))

    def test_instruction_unknown_rights_warning_uses_selected_prompt_projection(self):
        parent = self.prompt();parent = self.w.correct_rights_note(parent['id'],
            dict(revision=parent['revision'], source_revision=parent['source_revision'], note='unknown'))['record']
        a = self.answer(parent);b = self.answer(parent, completion='Other answer')
        preview = self.r.preview(self.body([(parent,a),(parent,b)]))
        self.assertTrue(preview['eligible']);self.assertEqual(preview['unique_prompt_count'],1)
        self.assertEqual(sum('unknown rights' in warning for warning in preview['warnings']),1)
        self.assertEqual(parent['review'],'draft')
        raw = self.w.import_asset(dict(kind='text', name='Raw unknown', text='Raw unknown prompt', groups=['raw-unknown'], rights='unknown'))
        raw_answer = self.answer(raw)
        self.assertTrue(any('unknown rights' in warning for warning in self.r.preview(self.body([(raw,raw_answer)]))['warnings']))
        known = self.prompt(name='Known selection');known_answer = self.answer(known)
        self.assertFalse(any('unknown rights' in warning for warning in self.r.preview(self.body([(known,known_answer)]))['warnings']),
                         'An unselected unknown-rights prompt cannot become selected permission evidence')

    def test_two_responses_preserve_existing_target_siblings_and_original_source(self):
        parent = self.prompt()
        parent = self.w.save(parent['id'], dict(parent, task='text_entities', annotation={'spans': [{'label': 'word', 'start': 0, 'end': 6}]}, review='human_reviewed'))
        original = dict(self.d.db.execute('SELECT * FROM workbench_records WHERE id=?', (parent['id'],)).fetchone())
        history = self.w.history(parent['id'])
        a, b = self.answer(parent), self.answer(parent, completion='Alternative', review='draft')
        self.assertNotEqual(a['id'], b['id']); self.assertEqual(len(self.w.responses(parent['id'])['responses']), 2)
        changed = self.answer(parent, response=a, completion=' Changed exact \r\n', review='draft')
        self.assertEqual(changed['review'], 'draft'); self.assertEqual(changed['revision'], 2)
        self.assertEqual(self.w._response(b['id']), b)
        self.assertEqual(dict(self.d.db.execute('SELECT * FROM workbench_records WHERE id=?', (parent['id'],)).fetchone()), original)
        self.assertEqual(self.w.history(parent['id']), history)
        snapshots = self.w.response_history(a['id'])['history']; self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0]['response'], a); self.assertEqual(snapshots[1]['parent'], parent)
        self.d.close(); self.d = Dataset(self.path); self.w, self.r = self.d.workbench, self.d.releases
        self.assertEqual(self.w._response(a['id']), changed); self.assertEqual(self.w.get(parent['id']), parent)

    def test_exact_unicode_and_shared_text_bound_no_trimming_or_normalization(self):
        parent = self.prompt(); content = '\ufeff\r\ne\u0301\t 😀  '
        answer = self.answer(parent, completion=content); self.assertEqual(answer['completion'], content)
        self.assertIn('é', parent['text']); self.assertNotIn('\r', parent['text'])
        answer = self.answer(parent, completion='😀' * MAX_TEXT); self.assertEqual(len(answer['completion']), MAX_TEXT)
        for value in ['😀' * (MAX_TEXT+1), ' \r\n\t', '\ud800', None, 1]:
            with self.subTest(value=str(value)[:10]), self.assertRaises(WorkbenchError): self.answer(parent, completion=value)
        self.assertEqual(MAX_SELECTED_TEXT_BYTES, 40 * 1024 * 1024)

    def test_noop_review_transitions_and_explicit_exact_content_review(self):
        parent = self.prompt(); answer = self.answer(parent, review='draft')
        noop = self.w.save_response(self.payload(parent, response=answer, completion=answer['completion'], review='draft'))
        self.assertFalse(noop['changed']); self.assertEqual(noop['response'], answer)
        reviewed = self.answer(parent, response=answer, completion=answer['completion'])
        self.assertEqual(reviewed['review'], 'human_reviewed'); self.assertEqual(reviewed['revision'], 2)
        changed = self.answer(parent, response=reviewed, completion='New', review='draft')
        self.assertEqual(changed['review'], 'draft')
        explicitly_reviewed = self.answer(parent, response=changed, completion='New exact content', review='human_reviewed')
        self.assertEqual(explicitly_reviewed['review'], 'human_reviewed')
        self.assertEqual(len(self.w.response_history(answer['id'])['history']), 4)

    def test_strict_fields_cas_duplicate_creation_and_immutable_prompt(self):
        parent, other = self.prompt(), self.prompt('other'); body = self.payload(parent)
        answer = self.w.save_response(body)['response']
        with self.assertRaises(WorkbenchError) as caught: self.w.save_response(body)
        self.assertEqual(caught.exception.status, 409)
        invalid = [dict(body, id='bad'), dict(body, revision=True), dict(body, parent_revision=True),
                   dict(body, source_revision=True), dict(body, review='programmatically_verified'), dict(body, origin='fake')]
        invalid.append({key: value for key, value in body.items() if key != 'review'})
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorkbenchError): self.w.save_response(value)
        with self.assertRaises(WorkbenchError): self.answer(other, response=answer)
        current = self.w.save(parent['id'], dict(parent, task='text_classification', annotation={'label': 'class'}, review='draft'))
        with self.assertRaises(WorkbenchError): self.answer(parent, response=answer)
        self.assertEqual(self.w._response(answer['id']), answer)
        self.answer(current, response=answer, completion='With current parent')

    def test_history_failure_rolls_back_response_and_review(self):
        parent = self.prompt(); answer = self.answer(parent)
        self.d.db.execute("CREATE TRIGGER reject_response_history BEFORE INSERT ON workbench_response_history BEGIN SELECT RAISE(ABORT,'fixture rollback'); END")
        with self.assertRaises(Exception): self.answer(parent, response=answer, completion='Uncommitted', review='draft')
        self.assertEqual(self.w._response(answer['id']), answer)
        self.assertEqual(len(self.w.response_history(answer['id'])['history']), 1)

    def test_frozen_exact_projection_sidecar_determinism_and_later_edits(self):
        parent = self.prompt(); a, b = self.answer(parent), self.answer(parent, completion=' second answer ')
        self.answer(parent, completion='Unselected draft', review='draft')
        body = self.body([(parent, a), (parent, b)]); preview = self.r.preview(body)
        self.assertEqual(preview['example_count'], 2); self.assertEqual(preview['unique_prompt_count'], 1)
        release = self.export(body); path = self.r.locate(release['id']); original = path.read_bytes()
        self.assertEqual(self.export(dict(body, items=list(reversed(body['items']))))['id'], release['id'])
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            rows = [json.loads(line) for line in archive.read('train/data.jsonl').splitlines()]
            mapping = [json.loads(line) for line in archive.read('rows.jsonl').splitlines()]
            answers = sorted([a,b], key=lambda row: row['id'])
            self.assertEqual(rows, [{'prompt': parent['text'], 'completion': answer['completion']} for answer in answers])
            self.assertEqual(manifest['prompts'], [parent]); self.assertEqual(manifest['responses'], answers)
            self.assertEqual([row['id'] for row in mapping], [answer['id'] for answer in answers])
            self.assertEqual([row['row'] for row in mapping], [0,1]); self.assertEqual({row['family'] for row in mapping}, {preview['lineage'][0]['id']})
            self.assertEqual(archive.read('prompts/'+parent['id']+'.txt'), parent['text'].encode())
            self.assertEqual(archive.read('validation/data.jsonl'), b'')
            self.assertEqual(sum(entry.file_size for entry in archive.infolist()), preview['artifact_bytes'])
        self.answer(parent, response=a, completion='Later', review='draft')
        self.assertFalse(self.r.preview(body)['eligible']); self.assertEqual(path.read_bytes(), original)

    def test_selected_response_parent_and_unselected_lineage_invalidate_proof_not_sibling(self):
        parent = self.prompt(); sibling = self.answer(parent, completion='Sibling'); selected = self.answer(parent)
        bridge = self.prompt('bridge', groups=['bridge'], parents=[parent['id']])
        body = self.body([(parent, selected)]); proof = self.r.preview(body)['preview_token']
        self.answer(parent, response=sibling, completion='New sibling'); self.assertEqual(self.r.preview(body)['preview_token'], proof)
        self.w.save(bridge['id'], dict(bridge, annotation={'label': 'new'}, task='text_classification', review='draft'))
        with self.assertRaises(WorkbenchError) as caught: self.r.create(dict(body, preview_token=proof))
        self.assertEqual(caught.exception.status, 409); self.assertIn('preview changed', str(caught.exception))
        proof = self.r.preview(body)['preview_token']
        self.w.save(parent['id'], dict(parent, annotation={'label': 'parent'}, task='text_classification', review='draft'))
        self.assertFalse(self.r.preview(body)['eligible'])
        with self.assertRaises(WorkbenchError): self.r.create(dict(body, preview_token=proof))

    def test_weighted_examples_and_shared_family_indivisibility(self):
        parents = [self.prompt(name) for name in ['heavy','light1','light2']]
        examples = [(parent,self.answer(parent,completion=f'Answer {index}')) for parent,count in zip(parents,[4,1,1]) for index in range(count)]
        body = self.body(examples); body['ratios'] = {'train': 67, 'validation': 16, 'test': 17}
        preview = self.r.preview(body); self.assertTrue(preview['eligible'],preview)
        self.assertEqual(preview['split_report']['actual_counts'], {'train':4,'test':1,'validation':1})
        self.assertEqual(preview['split_report']['actual_unique_prompt_counts'], {'train':1,'test':1,'validation':1})
        self.assertEqual(len({preview['assignments'][response['id']] for parent,response in examples if parent['id']==parents[0]['id']}),1)
        self.prompt('unselected bridge', parents=[parents[1]['id'],parents[2]['id']])
        self.assertFalse(self.r.preview(body)['eligible'])
        body['ratios']={'train':50,'validation':50,'test':0}; preview=self.r.preview(body);self.assertTrue(preview['eligible'],preview)
        self.assertEqual(preview['assignments'][examples[-1][1]['id']],preview['assignments'][examples[-2][1]['id']])

    def test_drafts_bad_pairs_settings_and_missing_tokens_fail_closed(self):
        parent=self.prompt();answer=self.answer(parent,review='draft');body=self.body([(parent,answer)])
        self.assertFalse(self.r.preview(body)['eligible'])
        reviewed=self.answer(parent,response=answer,completion=answer['completion']);body=self.body([(parent,reviewed)])
        for items in [[],body['items']*2,[dict(body['items'][0],revision=True)],[dict(body['items'][0],extra=1)],[dict(body['items'][0],prompt_id=uuid.uuid4().hex)]]:
            self.assertFalse(self.r.preview(dict(body,items=items))['eligible'])
        self.assertFalse(self.r.preview(dict(body,extra=True))['eligible'])
        with self.assertRaises(WorkbenchError):self.r.create(body)
        proof=self.r.preview(body)['preview_token']
        with self.assertRaises(WorkbenchError):self.r.create(dict(body,seed=43,preview_token=proof))
        self.assertEqual(list(self.r.path.iterdir()),[])

    def test_resource_rejection_precedes_staging_and_preview_is_readonly(self):
        parent=self.prompt();answer=self.answer(parent);body=self.body([(parent,answer)])
        with patch('workbench.MAX_SELECTED_TEXT_BYTES',10):self.assertFalse(self.r.preview(body)['eligible'])
        with patch('dataset_releases.MAX_SELECTED_TEXT_BYTES',10):self.assertFalse(self.r.preview(body)['eligible'])
        self.assertEqual(list(self.r.path.iterdir()),[])
        before=list(self.d.db.execute('SELECT * FROM workbench_response_history'));self.r.preview(body)
        self.assertEqual(list(self.d.db.execute('SELECT * FROM workbench_response_history')),before)

    def test_real_aggregate_consumer_projection_bound_counts_repeated_prompts(self):
        parent=self.w.import_asset({'kind':'text','name':'Large prompt','text':'😀'*MAX_TEXT,'groups':['large'],'rights':'Authored'})
        examples=[(parent,self.answer(parent,completion='Answer '+str(index))) for index in range(55)]
        self.assertLess(len(parent['text'].encode())+sum(len(answer['completion'].encode()) for _,answer in examples),MAX_SELECTED_TEXT_BYTES)
        preview=self.r.preview(self.body(examples));self.assertFalse(preview['eligible'])
        self.assertIn('archive exceeds the 40 MiB',preview['blockers'][0]['message'])
        self.assertEqual(list(self.r.path.iterdir()),[])

    def test_atomic_publication_failure_cleans_staging_preserves_old_release(self):
        parent=self.prompt();answer=self.answer(parent);body=self.body([(parent,answer)]);release=self.export(body)
        original=self.r.locate(release['id']).read_bytes();proof=self.r.preview(body)['preview_token']
        with patch('dataset_releases.os.replace',side_effect=OSError('Fixture failure')):
            with self.assertRaises(OSError):self.r.create(dict(body,preview_token=proof))
        self.assertEqual([path.name for path in self.r.path.iterdir()],[release['id']+'.zip'])
        self.assertEqual(self.r.locate(release['id']).read_bytes(),original)

    def test_http_end_to_end_and_concurrent_cas(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d))
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(route,body=None):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/'+route,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req) as result:return result.status,json.load(result)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        parent=self.prompt();status,result=request('responses',self.payload(parent));self.assertEqual(status,200,result)
        answer=result['response'];body=self.payload(parent,response=answer,completion='Changed',review='draft')
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(lambda _:request('responses',body),range(2)))
        self.assertEqual(sorted(status for status,_ in outcomes),[200,409])
        status,result=request('records/'+parent['id']+'/responses');self.assertEqual(status,200);self.assertEqual(result['responses'][0]['revision'],2)
        self.assertEqual(request('response-history/'+answer['id'])[1]['history'][0]['response'],answer)
        current=result['responses'][0];status,saved=request('responses',self.payload(parent,response=current,completion='Changed',review='human_reviewed'));self.assertEqual(status,200)
        body=self.body([(parent,saved['response'])]);status,preview=request('releases/preview',body);self.assertEqual(status,200);self.assertTrue(preview['eligible'])
        status,release=request('releases',dict(body,preview_token=preview['preview_token']));self.assertEqual(status,201,release)
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}'+release['url']) as download:self.assertEqual(hashlib.sha256(download.read()).hexdigest(),release['id'])
