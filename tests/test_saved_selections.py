"""Real SQLite/HTTP fixed-membership contracts and release consumer checks."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
from workbench import WorkbenchError


class SavedSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.w, self.s = self.dataset.workbench, self.dataset.selections

    def text(self, name='one', reviewed=False):
        row = self.w.import_asset({'kind': 'text', 'name': name, 'text': 'Source '+name,
                                   'groups': [name], 'rights': 'owned'})
        if reviewed:
            row = self.w.save(row['id'], dict(row, annotation={'label': 'target'}, review='human_reviewed'))
        return row

    def image(self):
        out = io.BytesIO(); Image.new('RGB', (16, 16), 'red').save(out, 'PNG')
        return self.w.import_asset({'kind': 'image', 'name': 'image', 'groups': ['image'], 'rights': 'owned',
                                    'image': base64.b64encode(out.getvalue()).decode()})

    def save(self, *rows, name='My fixed set'):
        return self.s.create({'name': name, 'items': [self.ref(row) for row in rows]})

    @staticmethod
    def ref(row):
        return {key: row[key] for key in ('id', 'revision', 'source_revision')}

    def test_repeat_save_load_and_process_reopen_preserve_fixed_membership(self):
        text, image = self.text(), self.image()
        before = {row['id']: self.w.get(row['id']) for row in (text, image)}
        saved = self.save(image, text)
        self.assertEqual(saved['mode'], 'fixed')
        self.assertEqual(saved['schema_version'], 1)
        self.assertEqual([r['id'] for r in saved['items']], sorted(before))
        for _ in range(3):
            result = self.s.load(saved['id'])
            self.assertTrue(result['current'])
            self.assertEqual(result['selection'], saved)
            self.assertEqual([m['status'] for m in result['members']], ['ok', 'ok'])
        self.save(text, name='Another set')
        self.assertEqual(len(self.s.list()['selections']), 2)
        self.dataset.close(); self.dataset = Dataset(self.tmp.name)
        self.w, self.s = self.dataset.workbench, self.dataset.selections
        self.assertEqual(self.s.load(saved['id'])['selection'], saved)
        self.assertEqual({rid: self.w.get(rid) for rid in before}, before)

    def test_changed_filters_and_new_matching_records_do_not_change_saved_members(self):
        row = self.text('needle')
        saved = self.save(row)
        self.text('needle newer')
        self.assertEqual(self.w.query({'q': 'needle'})['total'], 2)
        self.assertEqual(self.w.query({'review': 'human_reviewed'})['total'], 0)
        self.assertEqual(self.s.load(saved['id'])['selection']['items'], saved['items'])
        self.assertEqual(self.s.load(saved['id'])['selection']['member_count'], 1)

    def test_save_load_does_not_approve_draft_or_make_a_release(self):
        row = self.text()
        saved = self.save(row); loaded = self.s.load(saved['id'])
        self.assertTrue(loaded['current'])  # Currency is not release eligibility.
        body = {'items': [self.ref(r) for r in loaded['selection']['items']],
                'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 7}
        self.assertFalse(self.dataset.releases.preview(body)['eligible'])
        self.assertEqual(self.w.get(row['id'])['review'], 'draft')
        self.assertEqual(self.w.history(row['id']), [row])
        self.assertEqual(list(self.dataset.releases.path.iterdir()), [])

    def test_stale_annotation_keeps_saved_revision_and_blocks_release(self):
        row = self.text(reviewed=True); saved = self.save(row)
        changed = self.w.save(row['id'], dict(row, annotation={'label': 'later'}, review='draft'))
        result = self.s.load(saved['id'])
        self.assertEqual(result['members'][0]['status'], 'stale')
        self.assertEqual(result['members'][0]['current']['revision'], changed['revision'])
        self.assertEqual(result['selection']['items'], saved['items'])
        self.assertFalse(result['current'])
        with self.assertRaisesRegex(WorkbenchError, 'Selection changed'):
            self.save(row)
        self.assertEqual(len(self.s.list()['selections']), 1)

    def test_stale_image_source_revision_is_reported(self):
        row = self.image(); saved = self.save(row)
        source = self.dataset.sample(row['id'])
        self.dataset.save(row['id'], {**source, 'annotation': {'book_present': False,
                           'crop_suitable': False, 'corners': []}})
        loaded = self.s.load(saved['id'])
        self.assertEqual(loaded['members'][0]['status'], 'stale')
        self.assertEqual(loaded['selection']['items'], saved['items'])

    def test_missing_record_and_deleted_source_are_distinct_and_not_substituted(self):
        text, image = self.text(), self.image(); saved = self.save(text, image)
        with self.w.lock, self.w.db:
            self.w.db.execute('DELETE FROM workbench_records WHERE id=?', (text['id'],))
        self.dataset.delete(image['id'], {'revision': image['source_revision']})
        loaded = self.s.load(saved['id'])
        states = {m['item']['id']: m['status'] for m in loaded['members']}
        self.assertEqual(states, {text['id']: 'missing_record', image['id']: 'deleted_source'})
        self.assertEqual(loaded['selection']['items'], saved['items'])
        replacement = self.image()
        self.assertNotEqual(replacement['id'], image['id'])
        self.assertEqual(self.s.load(saved['id'])['selection']['items'], saved['items'])

    def test_missing_and_changed_source_bytes_are_reported_without_refreshing(self):
        row = self.image(); saved = self.save(row)
        asset, _ = self.w.asset(row['id']); original = asset.read_bytes()
        asset.unlink()
        self.assertEqual(self.s.load(saved['id'])['members'][0]['status'], 'missing_source')
        asset.write_bytes(original+b'changed')
        self.assertEqual(self.s.load(saved['id'])['members'][0]['status'], 'changed_source')
        with self.assertRaisesRegex(WorkbenchError, 'Source bytes changed'):
            self.save(row)
        asset.write_bytes(original)
        self.assertTrue(self.s.load(saved['id'])['current'])
        self.assertEqual(self.s.load(saved['id'])['selection'], saved)

    def test_rename_delete_revision_conflicts_and_record_preservation(self):
        row = self.text(); saved = self.save(row)
        renamed = self.s.mutate(saved['id'], 'rename', {'revision': 1, 'name': 'Renamed 📝'})
        self.assertEqual(renamed['name'], 'Renamed 📝')
        self.assertEqual(renamed['revision'], 2)
        self.assertEqual(renamed['items'], saved['items'])
        for action, body in [('rename', {'revision': 1, 'name': 'overwrite'}), ('delete', {'revision': 1})]:
            with self.assertRaises(WorkbenchError) as caught:
                self.s.mutate(saved['id'], action, body)
            self.assertEqual(caught.exception.status, 409)
        self.s.mutate(saved['id'], 'delete', {'revision': 2})
        self.assertEqual(self.s.list()['selections'], [])
        self.assertEqual(self.w.get(row['id']), row)
        with self.assertRaises(WorkbenchError) as caught: self.s.load(saved['id'])
        self.assertEqual(caught.exception.status, 404)

    def test_invalid_inputs_and_partial_selection_fail_atomically(self):
        row = self.text(); item = self.ref(row)
        for body in ({'name': '', 'items': [item]}, {'name': 'set', 'items': []},
                     {'name': 'set', 'items': [item, item]}, {'name': 'set', 'items': [dict(item, revision=True)]},
                     {'name': 'set', 'items': [dict(item, id='../file')]},
                     {'name': 'set', 'items': [dict(item, q='query')]},
                     {'name': 'set', 'items': [item], 'q': 'query'},
                     {'name': 'set', 'items': [item, dict(item, id='a'*32)]}):
            with self.subTest(body=body), self.assertRaises(WorkbenchError): self.s.create(body)
        self.assertEqual(self.s.list()['selections'], [])
        self.assertEqual(self.w.get(row['id']), row)

    def test_loaded_exact_references_feed_preview_and_frozen_export(self):
        row = self.text(reviewed=True); saved = self.save(row)
        items = [self.ref(r) for r in self.s.load(saved['id'])['selection']['items']]
        body = {'items': items, 'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 7}
        preview = self.dataset.releases.preview(body)
        self.assertTrue(preview['eligible'])
        release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            rows = json.loads(archive.read('manifest.json'))['records']
        self.assertEqual([self.ref(r) for r in rows], items)
        self.assertEqual(self.s.load(saved['id'])['selection'], saved)

    def test_real_http_contract_lists_opens_renames_deletes_and_checks_revisions(self):
        row = self.text()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join); self.addCleanup(server.shutdown)
        def request(path='', body=None):
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/workbench/selections'+path,
                data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req) as response: return response.status, json.load(response)
        status, saved = request(body={'name': 'HTTP set', 'items': [self.ref(row)]})
        self.assertEqual(status, 201)
        self.assertEqual(request()[1]['selections'][0]['id'], saved['id'])
        self.assertTrue(request('/'+saved['id'])[1]['current'])
        _, renamed = request('/'+saved['id']+'/rename', {'name': 'new', 'revision': 1})
        self.assertEqual(renamed['revision'], 2)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request('/'+saved['id']+'/delete', {'revision': 1})
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(json.load(caught.exception)['code'], 'conflict')
        self.assertEqual(request('/'+saved['id']+'/delete', {'revision': 2})[1], {'deleted': saved['id']})
        with self.assertRaises(urllib.error.HTTPError) as caught: request('/'+saved['id'])
        self.assertEqual(caught.exception.code, 404)


if __name__ == '__main__': unittest.main()
