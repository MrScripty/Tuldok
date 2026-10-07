"""Real HTTP/SQLite/ZIP interactions across the composed feature owners."""
import base64
import io
import json
import unittest
import urllib.request
import uuid
import zipfile

from tests import test_native_text_import as native_tests
from tests import test_curation as curation_tests


class CombinedWorkbenchTests(unittest.TestCase):
    open_server = native_tests.NativeTextImportTests.open_server
    close = native_tests.NativeTextImportTests.close
    request = native_tests.NativeTextImportTests.request
    prepare = native_tests.NativeTextImportTests.prepare
    admit = native_tests.NativeTextImportTests.admit
    state = curation_tests.CurationTests.state
    image = curation_tests.CurationTests.image

    def setUp(self):
        native_tests.NativeTextImportTests.setUp(self)
        self.w = self.dataset.workbench

    @staticmethod
    def ref(row):
        return {key: row[key] for key in ('id', 'revision', 'source_revision')}

    def call(self, route, body=None):
        status, result = self.request(route, body)
        self.assertIn(status, (200, 201), result)
        return result

    def answer(self, parent, completion):
        return self.call('responses', dict(id=uuid.uuid4().hex, prompt_id=parent['id'], revision=0,
            parent_revision=parent['revision'], source_revision=parent['source_revision'],
            completion=completion, review='human_reviewed'))['response']

    def answer_pair(self, parent, answer):
        return dict(id=answer['id'], revision=answer['revision'], prompt_id=parent['id'],
                    parent_revision=parent['revision'], source_revision=parent['source_revision'])

    def test_owned_verifier_projection_then_later_note_and_instruction_warning(self):
        parent = self.call('import', dict(kind='text', text='Authored verifier prompt', name='Verifier prompt',
                          rights='Original local declaration', groups=['verifier-source']))
        origin = json.loads(self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (parent['id'],)).fetchone()[0])
        corrected = self.call('rights/'+parent['id'], dict(revision=parent['revision'], source_revision=parent['source_revision'], note='First note'))['record']
        projected = dict(corrected['provenance'], verification='Owned fixture verifier')
        verified = self.w.save(parent['id'], dict(corrected, task='text_classification', annotation={'label':'fixture'},
                               review='programmatically_verified'), verified_provenance=projected)
        stored = json.loads(self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (parent['id'],)).fetchone()[0])
        self.assertNotIn('rights_note_correction', stored, 'Verifier projection must never enter origin')
        self.assertEqual(stored, dict(origin, verification='Owned fixture verifier'))
        self.assertEqual(verified['provenance']['rights_note_correction'], corrected['provenance']['rights_note_correction'])
        later = self.call('rights/'+parent['id'], dict(revision=verified['revision'], source_revision=verified['source_revision'], note='unknown'))['record']
        self.assertEqual(later['review'], 'programmatically_verified')
        self.assertEqual(later['provenance']['verification'], 'Owned fixture verifier')
        self.assertEqual(json.loads(self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (parent['id'],)).fetchone()[0]), stored)
        answer = self.answer(later, 'Exact independent answer\r\ne\u0301 😀')
        body = self.release_body([self.answer_pair(later, answer)], 'text_instruction_v1')
        before = self.state(); preview = self.call('releases/preview', body)
        self.assertTrue(preview['eligible']);self.assertTrue(any('unknown rights' in warning for warning in preview['warnings']), preview)
        self.assertEqual(self.state(), before, 'Preview warnings cannot grant review or write any owner')
        explicit = self.call('rights/'+parent['id'], dict(revision=later['revision'], source_revision=later['source_revision'], note='Reviewed local declaration'))['record']
        fresh = self.release_body([self.answer_pair(explicit, answer)], 'text_instruction_v1')
        known = self.call('releases/preview', fresh);self.assertTrue(known['eligible']);self.assertFalse(any('unknown rights' in warning for warning in known['warnings']))
        self.assertFalse(self.call('releases/preview', body)['eligible'], 'Old fixed pairs remain stale')

    def test_answer_list_does_not_authorize_stale_creation_then_explicit_reload_retry(self):
        parent = self.call('import', dict(kind='text', text='Authored prompt', name='CAS prompt', rights='Local', groups=['cas-source']))
        body = dict(id=uuid.uuid4().hex, prompt_id=parent['id'], revision=0,
                    parent_revision=parent['revision'], source_revision=parent['source_revision'],
                    completion='Retained exact\r\ne\u0301 😀\ufeff', review='draft')
        corrected = self.call('rights/'+parent['id'], dict(revision=parent['revision'],
                              source_revision=parent['source_revision'], note='Updated local note'))['record']
        latest_list = self.call('records/'+parent['id']+'/responses')
        self.assertEqual(latest_list['parent']['revision'], corrected['revision'])
        self.assertEqual(latest_list['responses'], [])
        before = self.state()
        self.assertEqual(self.request('responses', body)[0], 409)
        self.assertEqual(self.state(), before, 'A latest list read cannot authorize a stale create or write history')
        reloaded = self.call('records/'+parent['id'])
        retry = dict(body, parent_revision=reloaded['revision'], source_revision=reloaded['source_revision'])
        saved = self.call('responses', retry)['response']
        self.assertEqual(saved['completion'], body['completion'])
        self.assertEqual(saved['review'], 'draft')
        self.assertEqual(self.call('records/'+parent['id'])['review'], 'draft')
        self.assertEqual(self.call('records/'+parent['id']+'/responses')['responses'], [saved])

    def release_body(self, items, format_name):
        return dict(format=format_name, items=items, ratios=dict(train=100, validation=0, test=0), seed=7)

    def freeze(self, body):
        preview = self.call('releases/preview', body)
        self.assertTrue(preview['eligible'], preview)
        release = self.call('releases', dict(body, preview_token=preview['preview_token']))
        self.last_release_url = release['url']
        with urllib.request.urlopen(self.root+release['url']) as response:
            return response.read()

    def test_native_draft_rights_answers_fixed_pairs_and_both_actual_exports(self):
        _, receipt = self.admit(self.prepare()['rows'][0])
        parent = self.call('records/'+receipt['record_id'])
        self.assertEqual(parent['review'], 'draft')
        original = self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (parent['id'],)).fetchone()[0]
        fixed = self.call('selections', dict(name='Imported exact pair', items=[self.ref(parent)]))
        completions = [' exact answer\r\ne\u0301 😀\ufeff ', 'Independent sibling']
        answers = [self.answer(parent, value) for value in completions]
        old_body = self.release_body([self.answer_pair(parent, a) for a in answers], 'text_instruction_v1')
        old_preview = self.call('releases/preview', old_body)
        self.assertTrue(old_preview['eligible'])
        corrected = self.call('rights/'+parent['id'], dict(revision=parent['revision'], source_revision=parent['source_revision'], note='Local note'))['record']
        self.assertEqual(corrected['review'], 'draft', 'A note and reviewed answers never approve the imported label')
        self.assertEqual(corrected['source_sha256'], parent['source_sha256'])
        self.assertEqual(corrected['content_hash'], parent['content_hash'])
        self.assertEqual(corrected['annotation'], parent['annotation'])
        self.assertEqual(self.w.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (parent['id'],)).fetchone()[0], original)
        self.assertEqual(self.request('releases', dict(old_body, preview_token=old_preview['preview_token']))[0], 409)
        before_stale_answer = self.state()
        self.assertEqual(self.request('responses', dict(id=answers[0]['id'], prompt_id=parent['id'],
            revision=answers[0]['revision'], parent_revision=parent['revision'], source_revision=parent['source_revision'],
            completion='Stale parent edit', review='draft'))[0], 409)
        self.assertEqual(self.state(), before_stale_answer, 'A stale answer mutation changes no owner/history')
        loaded = self.call('selections/'+fixed['id'])
        self.assertEqual(loaded['selection'], fixed)
        self.assertEqual(loaded['members'][0]['status'], 'stale')
        report = self.call('curation', dict(scope='selected', items=[self.ref(parent)], category='references'))
        self.assertEqual(report['reference_counts']['stale'], 1)
        current_body = self.release_body([self.answer_pair(corrected, a) for a in answers], 'text_instruction_v1')
        instruction = self.freeze(current_body)
        instruction_url = self.last_release_url
        with zipfile.ZipFile(io.BytesIO(instruction)) as archive:
            rows = [json.loads(line) for line in archive.read('train/data.jsonl').splitlines()]
            self.assertEqual({row['completion'] for row in rows}, set(completions))
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['prompts'][0]['review'], 'draft')
            self.assertEqual(manifest['prompts'][0]['provenance']['rights_note_correction']['note'], 'Local note')
        before = self.state()
        self.assertEqual(self.request('native-text-import/prepare', dict(source_name='answers.zip', archive=base64.b64encode(instruction).decode()))[0], 400)
        self.assertEqual(self.state(), before, 'Instruction ZIP is not a classification import')
        canonical = self.release_body([self.ref(corrected)], 'canonical_v1')
        self.assertFalse(self.call('releases/preview', canonical)['eligible'])
        reviewed = self.call('records/'+parent['id'], dict(corrected, review='human_reviewed'))
        exported = self.freeze(self.release_body([self.ref(reviewed)], 'canonical_v1'))
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            self.assertEqual(archive.read('assets/'+parent['id']+'.txt'), parent['text'].encode())
            row = json.loads(archive.read('train/records.jsonl').splitlines()[0])
            self.assertEqual(row['annotation'], parent['annotation'])
            self.assertEqual(row['provenance']['rights_note_correction']['note'], 'Local note')
        self.assertEqual(self.call('records/'+parent['id']+'/responses')['responses'], answers)
        with urllib.request.urlopen(self.root+instruction_url) as response:
            self.assertEqual(response.read(), instruction, 'The older frozen answer archive remains immutable')

    def test_response_review_is_not_parent_annotation_and_legacy_reports_roll_back_all_tables(self):
        parent = self.call('import', dict(kind='text', name='Unlabeled prompt', text='No generic target', groups=['g']))
        self.answer(parent, 'Explicitly reviewed independent answer')
        report = self.call('curation', dict(scope='selected', category='unlabeled', items=[self.ref(parent)]))
        self.assertEqual(report['analysis']['unlabeled'], 1)
        self.assertEqual(report['items'][0]['review'], 'draft')
        legacy = self.image('legacy-combined', legacy=True)
        before = self.state()
        self.call('curation', dict(scope='selected', category='unknown_rights', items=[dict(id=legacy['id'], revision=1, source_revision=legacy['revision'])]))
        self.assertEqual(self.state(), before)
        self.assertFalse(self.w.db.in_transaction)

    def test_rights_change_on_unselected_lineage_invalidates_answer_proof(self):
        parent = self.call('import', dict(kind='text', name='Selected prompt', text='Selected prompt', groups=['shared']))
        bridge = self.call('import', dict(kind='text', name='Unselected bridge', text='Bridge', groups=['shared']))
        answer = self.answer(parent, 'Reviewed answer')
        body = self.release_body([self.answer_pair(parent, answer)], 'text_instruction_v1')
        preview = self.call('releases/preview', body)
        self.call('rights/'+bridge['id'], dict(revision=bridge['revision'], source_revision=bridge['source_revision'], note='Bridge note'))
        self.assertEqual(self.request('releases', dict(body, preview_token=preview['preview_token']))[0], 409)
        self.assertEqual(self.call('records/'+parent['id'])['revision'], parent['revision'])
        self.assertEqual(self.call('records/'+parent['id']+'/responses')['responses'], [answer])
