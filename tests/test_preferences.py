"""Real owner/persistence/HTTP/frozen release behavior for explicit comparisons."""
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
from preferences import SELECTION_FIELDS
from workbench import WorkbenchError


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.d = Dataset(Path(self.temp.name)); self.addCleanup(lambda: self.d.close())
        self.w, self.p, self.r = self.d.workbench, self.d.workbench.preferences, self.d.releases

    def prompt(self, name='first', **options):
        return self.w.import_asset(dict(kind='text', name=name, text='Prompt ' + name + '\r\ne\u0301 😀 ',
                                       groups=options.get('groups', [name]), parents=options.get('parents', [])))

    def answer(self, parent, text=' exact\r\ne\u0301 😀\ufeff ', response=None, review='draft'):
        return self.w.save_response(dict(id=response['id'] if response else uuid.uuid4().hex,
            revision=response['revision'] if response else 0, prompt_id=parent['id'], parent_revision=parent['revision'],
            source_revision=parent['source_revision'], completion=text, review=review))['response']

    def body(self, parent, left, right, judgment=None, **options):
        return dict(id=judgment['id'] if judgment else uuid.uuid4().hex, revision=judgment['revision'] if judgment else 0,
                    prompt_id=parent['id'], parent_revision=parent['revision'], source_revision=parent['source_revision'],
                    left_id=left['id'], left_revision=left['revision'], right_id=right['id'], right_revision=right['revision'],
                    outcome=options.get('outcome', 'right'), rationale=options.get('rationale', ' Explicit comparison '),
                    review=options.get('review', 'human_reviewed'))

    def fixture(self):
        parent = self.prompt(); left = self.answer(parent); right = self.answer(parent, 'Alternative answer')
        body = self.body(parent, left, right); judgment = self.p.save(body)['judgment']
        return parent, left, right, body, judgment

    def ref(self, row):
        return {key: row[key] for key in SELECTION_FIELDS}

    def release(self, *judgments):
        return dict(format='text_preference_v1', items=[self.ref(row) for row in judgments],
                    ratios=dict(train=100, validation=0, test=0), seed=42)

    def export(self, body):
        preview = self.r.preview(body); self.assertTrue(preview['eligible'], preview)
        return self.r.create(dict(body, preview_token=preview['preview_token']))

    def test_independent_ownership_exact_evidence_history_reopen(self):
        parent, left, right, body, row = self.fixture()
        self.assertEqual(self.w.get(parent['id']), parent)
        self.assertEqual(self.w.responses(parent['id'])['responses'], [left, right])
        history = self.p.history(row['id'])['history']; self.assertEqual(len(history), 1)
        self.assertEqual(history[0], dict(judgment=row, parent=parent, left=left, right=right))
        same = self.p.save(dict(body, revision=row['revision'])); self.assertFalse(same['changed'])
        self.assertEqual(len(self.p.history(row['id'])['history']), 1)
        row2 = self.p.save(dict(body, revision=1, outcome='left', review='draft'))['judgment']
        self.assertEqual(row2['revision'], 2); self.assertEqual(row2['review'], 'draft')
        with self.assertRaises(WorkbenchError): self.p.save(body)
        self.assertEqual(self.w._response(left['id']), left)
        reopened = Dataset(Path(self.temp.name)); self.addCleanup(reopened.close)
        if reopened:
            self.assertEqual(reopened.workbench.preferences._get(row['id']), row2)
            self.assertEqual(len(reopened.workbench.preferences.history(row['id'])['history']), 2)

    def test_strict_boundary_same_prompt_distinct_shape_review(self):
        parent, left, right, body, row = self.fixture()
        other = self.prompt('other'); alien = self.answer(other)
        invalid = [dict(body, id=uuid.uuid4().hex, right_id=left['id']), dict(body, id=uuid.uuid4().hex, right_id=alien['id']),
                   dict(body, id=True), dict(body, revision=True), dict(body, left_revision=True),
                   dict(body, outcome='chosen'), dict(body, review='programmatically_verified'),
                   dict(body, rationale='\ud800'), dict(body, rationale='x'*4001), dict(body, model_score=1)]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorkbenchError): self.p.save(value)
        self.assertEqual(len(self.p.list(parent['id'])['judgments']), 1)
        self.assertFalse(self.r.preview(self.release(dict(row, revision=True)))['eligible'])

    def test_stale_answers_rejudge_review_and_delete_retains_audit(self):
        parent, left, right, body, row = self.fixture()
        changed = self.answer(parent, 'Edited answer', left)
        self.assertIn('Stale', self.p.list(parent['id'])['judgments'][0]['stale_warning'])
        with self.assertRaises(WorkbenchError): self.p.save(dict(body, revision=row['revision']))
        self.assertEqual(self.r.preview(self.release(row))['blockers'][0]['code'], 'conflict')
        rejudged = self.p.save(self.body(parent, changed, right, row, review='draft'))['judgment']
        self.assertFalse(self.r.preview(self.release(rejudged))['eligible'])
        rejudged = self.p.save(self.body(parent, changed, right, rejudged))['judgment']
        frozen = self.export(self.release(rejudged)); before = self.r.locate(frozen['id']).read_bytes()
        self.answer(parent, 'Changed again', changed)
        deleted = self.p.delete(self.ref(rejudged))['judgment']; self.assertTrue(deleted['deleted'])
        self.assertEqual(len(self.p.history(row['id'])['history']), 4)
        self.assertEqual(self.p.history(row['id'])['history'][-1]['left']['completion'], 'Edited answer')
        for mutation in (lambda: self.p.delete(self.ref(rejudged)), lambda: self.p.save(body),
                         lambda: self.p.save(self.body(parent, left, right, deleted))):
            with self.assertRaises(WorkbenchError): mutation()
        self.assertFalse(self.r.preview(self.release(deleted))['eligible'])
        self.assertEqual(self.r.locate(frozen['id']).read_bytes(), before)

    def test_concurrent_cas_and_answer_save_blocks_stale_judgment(self):
        parent, left, right, body, row = self.fixture()
        def update(outcome):
            try: return self.p.save(dict(body, revision=1, outcome=outcome, rationale=outcome))['changed']
            except WorkbenchError as error: return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, ['left', 'tie']))
        self.assertEqual(sorted(outcomes, key=str), sorted([True, 409], key=str))
        self.assertEqual(len(self.p.history(row['id'])['history']), 2)
        self.answer(parent, 'Concurrent answer revision', left)
        current = self.p._get(row['id'])
        with self.assertRaises(WorkbenchError): self.p.save(dict(body, revision=current['revision']))
        self.assertEqual(len(self.p.history(row['id'])['history']), 2)

    def test_tie_abstain_exclusion_order_and_independent_review(self):
        parent, left, right, body, directional = self.fixture()
        tie = self.p.save(self.body(parent, left, right, outcome='tie'))['judgment']
        abstain = self.p.save(self.body(parent, left, right, outcome='abstain'))['judgment']
        self.assertFalse(self.r.preview(self.release(tie, abstain))['eligible'])
        request = self.release(directional, tie, abstain); preview = self.r.preview(request)
        self.assertTrue(preview['eligible']); self.assertEqual(preview['example_count'], 1)
        self.assertEqual({item['reason'] for item in preview['excluded']}, {'tie', 'abstain'})
        frozen = self.export(request)
        with zipfile.ZipFile(self.r.locate(frozen['id'])) as archive:
            values = [json.loads(line) for line in archive.read('train/data.jsonl').splitlines()]
            self.assertEqual(values, [dict(prompt=parent['text'], chosen=right['completion'], rejected=left['completion'])])
            manifest = json.loads(archive.read('manifest.json')); self.assertEqual(len(manifest['judgments']), 3)
            self.assertTrue(all(answer['review'] == 'draft' for answer in manifest['responses']))
            self.assertEqual(manifest['excluded'], preview['excluded'])
        draft = self.p.save(self.body(parent, left, right, directional, review='draft'))['judgment']
        self.assertFalse(self.r.preview(self.release(draft, tie))['eligible'])

    def test_live_unselected_conflicts_bind_preview_but_unrelated_changes_do_not(self):
        parent, left, right, body, row = self.fixture(); request = self.release(row)
        proof = self.r.preview(request)['preview_token']
        self.answer(parent, 'Unselected answer'); self.assertEqual(self.r.preview(request)['preview_token'], proof)
        opposite = self.p.save(self.body(parent, right, left, outcome='right'))['judgment']
        self.assertEqual(self.r.preview(request)['blockers'][0]['code'], 'conflict')
        self.p.delete(self.ref(opposite)); self.assertEqual(self.r.preview(request)['preview_token'], proof)
        agreeing = self.p.save(self.body(parent, left, right))['judgment']
        with self.assertRaises(WorkbenchError): self.r.create(dict(request, preview_token=proof))
        self.assertTrue(self.r.preview(request)['eligible'])
        self.p.delete(self.ref(agreeing))
        changed = self.answer(parent, 'Different bound evidence', left)
        current = self.p.save(self.body(parent, changed, right, row))['judgment']
        self.assertTrue(self.r.preview(self.release(current))['eligible'])

    def test_rights_full_lineage_family_weights_and_frozen_manifest(self):
        parent, left, right, body, row = self.fixture()
        bridge = self.prompt('bridge', groups=['first', 'family'])
        sibling = self.prompt('sibling', groups=['family'])
        others = [self.prompt('other'+str(i)) for i in range(2)]
        selected = [row]
        for prompt in [sibling, *others]:
            a, b = self.answer(prompt), self.answer(prompt, 'short')
            selected.append(self.p.save(self.body(prompt, a, b))['judgment'])
        request = self.release(*selected); request['ratios'] = dict(train=50, validation=25, test=25)
        preview = self.r.preview(request); self.assertTrue(preview['eligible'], preview)
        self.assertEqual(preview['assignments'][row['id']], preview['assignments'][selected[1]['id']])
        self.assertEqual(preview['split_report']['actual_counts'], dict(train=2, validation=1, test=1))
        self.assertTrue(any('unknown rights' in x for x in preview['warnings']))
        frozen = self.export(request); blob = self.r.locate(frozen['id']).read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), frozen['id'])
        with zipfile.ZipFile(self.r.locate(frozen['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json')); mapping = [json.loads(x) for x in archive.read('rows.jsonl').splitlines()]
            family = next(x['family'] for x in mapping if x['id'] == row['id'])
            self.assertIn(bridge['id'], [x['id'] for x in manifest['protected_components'][family]])
        self.w.correct_rights_note(bridge['id'], dict(revision=bridge['revision'], source_revision=1, note='Authored'))
        with self.assertRaises(WorkbenchError): self.r.create(dict(request, preview_token=preview['preview_token']))
        changed = self.w.correct_rights_note(parent['id'], dict(revision=parent['revision'], source_revision=1, note='Authored'))['record']
        self.assertEqual(self.r.preview(request)['blockers'][0]['code'], 'conflict')
        self.assertEqual(self.w._response(left['id']), left)
        self.assertEqual(self.r.locate(frozen['id']).read_bytes(), blob)
        rejudged = self.p.save(self.body(changed, left, right, row))['judgment']
        self.assertTrue(self.r.preview(self.release(rejudged))['eligible'])

    def test_identical_strings_warning_resource_bound_and_atomic_failure(self):
        parent, left, right, body, row = self.fixture(); right = self.answer(parent, left['completion'], right)
        row = self.p.save(self.body(parent, left, right, row))['judgment']; request = self.release(row)
        self.assertTrue(any('identical strings' in x for x in self.r.preview(request)['warnings']))
        with patch('dataset_releases.MAX_SELECTED_TEXT_BYTES', 1): self.assertFalse(self.r.preview(request)['eligible'])
        self.w.db.execute("CREATE TRIGGER reject_preference_history BEFORE INSERT ON workbench_preference_history BEGIN SELECT RAISE(FAIL, 'history failure'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError): self.p.save(dict(self.body(parent, left, right, row), outcome='tie'))
        self.w.db.execute('DROP TRIGGER reject_preference_history')
        self.assertEqual(self.p._get(row['id']), row)
        with patch('preferences.MAX_SELECTED_TEXT_BYTES', 1):
            with self.assertRaises(WorkbenchError): self.p.competing([row])
        frozen = self.export(request); before = self.r.locate(frozen['id']).read_bytes(); proof = self.r.preview(request)
        with patch('dataset_releases.os.replace', side_effect=OSError('publication failure')):
            with self.assertRaises(OSError): self.r.create(dict(request, preview_token=proof['preview_token']))
        self.assertFalse(list(self.r.path.glob('.building-*')))
        self.assertEqual(self.r.locate(frozen['id']).read_bytes(), before)

    def test_deleted_legacy_ancestry_fixed_splits_and_missing_lineage(self):
        import base64
        import io
        from PIL import Image
        images = []
        for color in ('red', 'green'):
            buffer = io.BytesIO(); Image.new('RGB', (16, 16), color).save(buffer, 'PNG')
            image = self.w.import_asset(dict(kind='image', image=base64.b64encode(buffer.getvalue()).decode(),
                                            name=color, groups=[color]))
            sample = self.d.sample(image['id'])
            self.d.save(image['id'], dict(revision=sample['revision'], book_id='retained-book',
                session_id=sample['session_id'], split='test',
                annotation={'book_present': False, 'crop_suitable': False, 'corners': []}))
            images.append(image)
        parent = self.prompt('descendant', parents=[images[0]['id']])
        other = self.prompt('other')
        rows = [self.p.save(self.body(prompt, self.answer(prompt), self.answer(prompt, 'short')))['judgment']
                for prompt in (parent, other)]
        request = self.release(*rows); request['ratios'] = dict(train=50, validation=0, test=50)
        self.d.delete(images[0]['id'], dict(revision=self.d.sample(images[0]['id'])['revision']))
        reopened = Dataset(Path(self.temp.name)); self.addCleanup(reopened.close)
        preview = reopened.releases.preview(request); self.assertTrue(preview['eligible'], preview)
        self.assertEqual(preview['assignments'][rows[0]['id']], 'test')
        release = reopened.releases.create(dict(request, preview_token=preview['preview_token']))
        with zipfile.ZipFile(reopened.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json')); mapping = [json.loads(line) for line in archive.read('rows.jsonl').splitlines()]
            family = next(row['family'] for row in mapping if row['id'] == rows[0]['id'])
            members = {row['id']: row for row in manifest['protected_components'][family]}
            self.assertEqual(set(members), {parent['id'], images[0]['id'], images[1]['id']})
            self.assertFalse(members[images[0]['id']]['source_available'])
            self.assertEqual(members[images[0]['id']]['source_split'], 'test')
        self.assertFalse(reopened.releases.preview(dict(request, ratios=dict(train=100, validation=0, test=0)))['eligible'])
        with reopened.lock, reopened.db:
            reopened.db.execute('DELETE FROM workbench_deleted_sources WHERE id=?', (images[0]['id'],))
        self.assertFalse(reopened.releases.preview(request)['eligible'])

    def test_impossible_family_split_and_readonly_preview(self):
        parent, left, right, body, row = self.fixture()
        second = self.p.save(self.body(parent, left, self.answer(parent, 'Third answer')))['judgment']
        request = self.release(row, second); request['ratios'] = dict(train=50, validation=0, test=50)
        self.assertFalse(self.r.preview(request)['eligible'])
        before = [tuple(item) for item in self.w.db.execute('SELECT * FROM workbench_preference_history')]
        self.assertTrue(self.r.preview(self.release(row, second))['eligible'])
        self.assertEqual(before, [tuple(item) for item in self.w.db.execute('SELECT * FROM workbench_preference_history')])
        self.assertEqual(list(self.r.path.iterdir()), [])
        for changed in [dict(self.release(row), items=[self.ref(row), self.ref(row)]),
                        dict(self.release(row), items=[]), dict(self.release(row), extra=True)]:
            self.assertFalse(self.r.preview(changed)['eligible'])
        with self.assertRaises(WorkbenchError): self.r.create(self.release(row))

    def test_http_admission_list_history_repeat_and_deleted_source(self):
        parent, left, right, body, row = self.fixture()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.d)); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join()))
        url = 'http://127.0.0.1:' + str(server.server_port) + '/api/workbench/'
        def call(route, payload=None):
            request = urllib.request.Request(url+route, data=json.dumps(payload).encode() if payload is not None else None,
                                            headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as reply: return json.load(reply)
        self.assertEqual(call('records/'+parent['id']+'/preferences')['judgments'][0]['id'], row['id'])
        self.assertEqual(len(call('preference-history/'+row['id'])['history']), 1)
        with self.assertRaises(urllib.error.HTTPError) as failure: call('preferences', body)
        self.assertEqual(failure.exception.code, 409)
        deleted = call('preferences/delete', self.ref(row))['judgment']; self.assertTrue(deleted['deleted'])
        self.assertEqual(len(call('preference-history/'+row['id'])['history']), 2)
        # Source owner unavailable rather than silently dropping the selected unit.
        with self.w.lock, self.w.db: self.w.db.execute('DELETE FROM workbench_records WHERE id=?', (parent['id'],))
        self.assertFalse(self.r.preview(self.release(row))['eligible'])


if __name__ == '__main__': unittest.main()
