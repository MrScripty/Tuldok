"""Exact current-field filtering through real storage and HTTP, without permission inference."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
from workbench import WorkbenchError, encode


class MetadataFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name); self.addCleanup(lambda: self.dataset.close())
        self.w = self.dataset.workbench

    def text(self, name, label=None, groups=None, rights='unknown', parents=None):
        row = self.w.import_asset({'kind': 'text', 'name': name, 'text': 'Shared text '+name,
            'groups': groups or [name], 'parents': parents or [], 'rights': rights})
        if label is not None:
            row = self.w.save(row['id'], dict(row, task='text_classification',
                annotation={'label': label}, review='human_reviewed'))
        return row

    def image(self, name, color, task, annotation):
        out = io.BytesIO(); Image.new('RGB', (16, 16), color).save(out, 'PNG')
        row = self.w.import_asset({'kind': 'image', 'name': name, 'groups': [name], 'rights': 'fixture note',
                                  'image': base64.b64encode(out.getvalue()).decode()})
        return self.w.save(row['id'], dict(row, task=task, annotation=annotation, review='human_reviewed'))

    def ids(self, **options):
        return {row['id'] for row in self.w.query(options)['items']}

    @staticmethod
    def ref(row):
        return {key: row[key] for key in ('id', 'revision', 'source_revision')}

    def test_label_matches_current_targets_across_tasks_not_source_words_or_substrings(self):
        classification = self.text('classification', 'cat')
        entities = self.text('entities')
        entities = self.w.save(entities['id'], dict(entities, task='text_entities', annotation={
            'spans': [{'label': 'cat', 'start': 0, 'end': 6}, {'label': 'other', 'start': 7, 'end': 11}]}, review='human_reviewed'))
        detection = self.image('detection', 'red', 'image_detection', {'boxes': [
            {'label': 'cat', 'x': 0, 'y': 0, 'width': 4, 'height': 4},
            {'label': 'other', 'x': 8, 'y': 8, 'width': 4, 'height': 4}]})
        image_class = self.image('class', 'blue', 'image_classification', {'label': 'cat'})
        self.image('caption', 'green', 'image_caption', {'caption': 'A cat in a caption.'})
        self.image('negative', 'yellow', 'image_detection', {'boxes': []})
        self.text('cat in name/source')
        self.text('substring', 'catfish'); self.text('uppercase', 'Cat')
        self.assertEqual(self.ids(label='cat'), {r['id'] for r in (classification, entities, detection, image_class)})
        self.assertEqual(self.ids(label='other'), {entities['id'], detection['id']})
        self.assertEqual(self.ids(label='cat', task='image_caption'), set())
        changed = self.w.save(classification['id'], dict(classification, annotation={'label': 'new'}, review='draft'))
        self.assertNotIn(classification['id'], self.ids(label='cat'))
        self.assertEqual(self.ids(label='new'), {changed['id']})

    def test_groups_match_direct_stored_membership_and_not_parent_lineage(self):
        parent = self.text('parent', groups=['source-a', 'shared'])
        child = self.text('child', groups=['source-b'], parents=[parent['id']])
        multi = self.text('multi', groups=['source-c', 'source-a'])
        self.text('substring source-a', groups=['source-a-extra'])
        self.assertEqual(self.ids(group='source-a'), {parent['id'], multi['id']})
        self.assertEqual(self.ids(group='shared'), {parent['id']})
        self.assertNotIn(child['id'], self.ids(group='source-a'))
        self.assertEqual(self.ids(group='SOURCE-A'), set())

    def test_unknown_rights_include_absent_null_blank_and_literal_unknown_without_mutation(self):
        rows = [self.text(name) for name in ('absent', 'null', 'blank', 'literal')]
        for row, value in zip(rows[:3], ({}, {'rights': None}, {'rights': '   '})):
            origin = dict(row['provenance']); origin.pop('rights'); origin.update(value)
            with self.w.lock, self.w.db:
                self.w.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?', (encode(origin), row['id']))
        self.text('uppercase note', rights='UNKNOWN')
        note = self.text('present', rights='Permission not established; check with owner.')
        before = list(self.w.db.iterdump())
        result = self.w.query({'rights': 'unknown'})
        self.assertEqual({r['id'] for r in result['items']}, {r['id'] for r in rows})
        self.assertEqual(result['analysis']['unknown_rights'], 4)
        self.assertEqual({r['rights_note'] for r in result['items']}, {'unknown'})
        self.assertEqual(self.ids(rights='UNKNOWN'), self.ids(q='uppercase note'))
        self.assertEqual(self.ids(rights='Permission not established; check with owner.'), {note['id']})
        self.assertEqual(self.w.get(note['id'])['review'], 'draft')
        self.assertEqual(list(self.w.db.iterdump()), before)

    def test_combined_filters_apply_before_full_analysis_sort_and_pagination(self):
        alpha = self.text('Alpha', 'target', ['source-a'], 'Fixture note')
        beta = self.text('Beta', 'target', ['source-a'], 'Fixture note')
        self.text('Other label', 'different', ['source-a'], 'Fixture note')
        self.text('Other note', 'target', ['source-a'], 'Other note')
        self.text('Other group', 'target', ['source-b'], 'Fixture note')
        self.text('Unannotated', groups=['source-a'], rights='Fixture note')
        options = dict(q='SHARED', kind='text', task='text_classification', review='human_reviewed',
                       label='target', group='source-a', rights='Fixture note', sort='name', limit=1)
        first = self.w.query(options); second = self.w.query(dict(options, offset=1))
        self.assertEqual(first['total'], 2); self.assertEqual(second['total'], 2)
        self.assertEqual(first['items'][0]['id'], alpha['id']); self.assertEqual(second['items'][0]['id'], beta['id'])
        self.assertEqual(first['analysis']['labels'], {'target': 2})
        self.assertEqual(first['analysis']['records'], 2)
        self.assertEqual(first['analysis'], second['analysis'])
        self.assertEqual(self.ids(label=' target ', group=' source-a ', rights=' Fixture note '), {alpha['id'], beta['id']})
        self.assertEqual(self.w.query({'rights': 'fixture note'})['total'], 0)

    def test_dynamic_results_do_not_modify_saved_pairs_review_or_preview_proof(self):
        first = self.text('selected one', 'target', ['selected-one'], 'Saved note')
        second = self.text('selected two', 'target', ['selected-two'], 'Saved note')
        items = [self.ref(first), self.ref(second)]
        saved = self.dataset.selections.create({'name': 'Fixed set', 'items': items})
        body = {'items': items, 'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 7}
        preview = self.dataset.releases.preview(body); self.assertTrue(preview['eligible'])
        self.text('filtered one', 'other', ['filtered'], 'Other note')
        options = {'label': 'other', 'group': 'filtered', 'rights': 'Other note'}
        self.assertEqual(self.w.query(options)['total'], 1)
        self.text('filtered two', 'other', ['filtered'], 'Other note')
        self.assertEqual(self.w.query(options)['total'], 2)
        self.assertEqual(self.dataset.selections.load(saved['id'])['selection'], saved)
        self.assertEqual(self.dataset.releases.preview(body)['preview_token'], preview['preview_token'])
        self.assertEqual(self.w.get(first['id'])['review'], 'human_reviewed')

    def test_validation_uses_existing_field_limits_and_rejects_bad_input(self):
        label, group, note = 'l'*80, 'g'*120, 'n'*1000
        row = self.text('maximum', label, [group], note)
        self.assertEqual(self.ids(label=label, group=group, rights=note), {row['id']})
        emoji = self.text('Unicode maximum', '😀'*80, ['😀'*120], '😀'*1000)
        self.assertEqual(self.ids(label='😀'*80, group='😀'*120, rights='😀'*1000), {emoji['id']})
        for key, maximum in (('label', 80), ('group', 120), ('rights', 1000)):
            for value in (None, [], 3, 'x'*(maximum+1), '\ud800'):
                with self.subTest(key=key, value=repr(value)), self.assertRaises(WorkbenchError):
                    self.w.query({key: value})
        self.assertEqual(self.w.query({'label': '', 'group': '', 'rights': ''})['total'], 2)
        self.assertEqual(self.w.query({'label': 'missing'})['analysis']['records'], 0)

    def test_current_metadata_queries_survive_reopen_without_schema_or_state_changes(self):
        row = self.text('reopen', 'é😀', ['case-sensitive'], 'Fixture rights note')
        tables = [r[0] for r in self.w.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        self.dataset.close(); self.dataset = Dataset(self.tmp.name); self.w = self.dataset.workbench
        before = list(self.w.db.iterdump())
        self.assertEqual(self.ids(label='é😀', group='case-sensitive', rights='Fixture rights note'), {row['id']})
        self.assertEqual(list(self.w.db.iterdump()), before)
        self.assertEqual([r[0] for r in self.w.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")], tables)

    def test_real_http_percent_encoded_filters_and_invalid_field_diagnostics(self):
        row = self.text('http', 'cat & café +😀', ['group &😀'], 'Owner note: ? & + permission unverified')
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join); self.addCleanup(server.shutdown)
        options = dict(label='cat & café +😀', group='group &😀', rights='Owner note: ? & + permission unverified')
        url = f'http://127.0.0.1:{server.server_port}/api/workbench/records?'
        with urllib.request.urlopen(url+urllib.parse.urlencode(options)) as response:
            result = json.load(response)
        self.assertEqual(result['total'], 1); self.assertEqual(result['items'][0]['id'], row['id'])
        self.assertEqual(result['items'][0]['rights_note'], options['rights'])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(url+urllib.parse.urlencode({'label': 'x'*81}))
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)['code'], 'invalid')

    def test_internal_line_endings_are_distinct_exact_values_through_storage_and_http(self):
        values = ['ordinary', 'left\nright', 'left\rright', 'left\r\nright', r'left\nright']
        rows = [self.text('ending '+str(i), value, [value], value) for i, value in enumerate(values)]
        before = list(self.w.db.iterdump())
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join); self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/api/workbench/records?'
        for row, value in zip(rows, values):
            with self.subTest(codepoints=[ord(c) for c in value]):
                criteria = dict(label=value, group=value, rights=value)
                self.assertEqual(self.ids(**criteria), {row['id']})
                with urllib.request.urlopen(url+urllib.parse.urlencode(criteria)) as response:
                    result = json.load(response)
                self.assertEqual([r['id'] for r in result['items']], [row['id']])
                self.assertEqual(result['items'][0]['rights_note'], value)
                stored = self.w.get(row['id'])
                self.assertEqual(stored['annotation']['label'], value)
                self.assertEqual(stored['groups'], [value])
                self.assertEqual(stored['provenance']['rights'], value)
        self.assertEqual(self.ids(label='leftright', group='leftright', rights='leftright'), set())
        self.assertEqual(list(self.w.db.iterdump()), before)


if __name__ == '__main__': unittest.main()
