"""Exact-selection preflight, read-only snapshots, and freshness-bound exports."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
from workbench import WorkbenchError


class ReleasePreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(self.dataset.close)
        self.w = self.dataset.workbench
        self.r = self.dataset.releases

    def text(self, name, groups=None, parents=None, review='human_reviewed'):
        row = self.w.import_asset({'kind': 'text', 'name': name, 'text': 'Text for '+name,
                                   'groups': groups or [name], 'parents': parents or [], 'rights': 'owned'})
        return self.w.save(row['id'], dict(row, task='text_classification',
                           annotation={'label': 'class-'+name}, review=review))

    def image(self, name, color='red', parents=None, caption=True, compress_level=6):
        stream = io.BytesIO()
        Image.new('RGB', (32, 24), color).save(stream, 'PNG', compress_level=compress_level)
        row = self.w.import_asset({'kind': 'image', 'name': name,
                                  'image': base64.b64encode(stream.getvalue()).decode(),
                                  'groups': [name], 'parents': parents or [], 'rights': 'owned'})
        return self.w.save(row['id'], dict(row, task='image_caption' if caption else 'image_detection',
            annotation={'caption': 'A '+color+' panel.'} if caption else {'boxes': []}, review='human_reviewed'))

    def body(self, rows, **options):
        return {'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 7,
                'format': 'canonical_v1', **options}

    def blocked(self, body, code, message):
        result = self.r.preview(body)
        self.assertFalse(result['eligible'])
        self.assertIsNone(result['preview_token'])
        self.assertTrue(any(item['code'] == code and message in item['message'] for item in result['blockers']), result)
        return result

    def test_exact_selection_counts_and_allocation_match_frozen_release(self):
        first, second = self.text('first'), self.text('second')
        self.text('unselected', review='draft')
        body = self.body([first, second])
        preview = self.r.preview(body)
        self.assertTrue(preview['eligible'], preview)
        self.assertEqual(preview['selected_count'], 2)
        self.assertEqual(preview['analysis']['reviews'], {'human_reviewed': 2})
        self.assertEqual(preview['analysis']['labels'], {'class-first': 1, 'class-second': 1})
        self.assertEqual(preview['analysis']['tasks'], {'text_classification': 2})
        self.assertEqual(len(preview['lineage']), 2)
        self.assertEqual(preview, self.r.preview(self.body([second, first])))
        release = self.r.create(dict(body, preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.r.locate(release['id'])) as archive:
            records = json.loads(archive.read('manifest.json'))['records']
        self.assertEqual({row['id']: row['split'] for row in records}, preview['assignments'])
        self.assertEqual(release['split_report'], preview['split_report'])

    def test_preview_is_read_only_even_with_lazy_legacy_enrollment(self):
        row = self.text('selected')
        stream = io.BytesIO(); Image.new('RGB', (16, 16), 'blue').save(stream, 'PNG')
        self.dataset.add({'image': base64.b64encode(stream.getvalue()).decode(), 'filename': 'legacy.png',
                          'session_id': 'legacy', 'book_id': '', 'split': 'unassigned'})
        before = list(self.w.db.iterdump())
        source = {str(p.relative_to(self.dataset.path)): p.read_bytes() for p in self.dataset.path.rglob('*')
                  if p.is_file() and p.suffix != '.db' and '-wal' not in p.name and '-shm' not in p.name}
        with patch('dataset_releases.tempfile.mkstemp', side_effect=AssertionError('Preview must not stage ZIP')):
            self.assertTrue(self.r.preview(self.body([row]))['eligible'])
        self.assertEqual(list(self.w.db.iterdump()), before)
        self.assertEqual(list(self.r.path.iterdir()), [])
        for name, data in source.items(): self.assertEqual((self.dataset.path/name).read_bytes(), data)

    def test_stale_selected_revision_and_deleted_selection_block(self):
        row = self.text('one')
        self.w.save(row['id'], dict(row, review='human_reviewed'))
        result = self.blocked(self.body([row]), 'conflict', 'Selection changed')
        self.assertIsNone(result['analysis'])
        image = self.image('image')
        self.dataset.delete(image['id'], {'revision': image['source_revision']})
        self.blocked(self.body([image]), 'conflict', 'Selection changed')

    def test_collects_multiple_record_blockers(self):
        first, second = self.text('first', review='draft'), self.text('second', review='draft')
        preview = self.blocked(self.body([first, second]), 'invalid', 'reviewed')
        self.assertEqual({item['record_id'] for item in preview['blockers']}, {first['id'], second['id']})
        self.assertEqual(preview['analysis']['reviews'], {'draft': 2})

    def test_impossible_splits_are_reported_without_assignments(self):
        row = self.text('one')
        result = self.blocked(self.body([row], ratios={'train': 80, 'validation': 10, 'test': 10}),
                              'invalid', 'Too few independent source groups')
        self.assertIsNone(result['split_report'])
        self.assertEqual(result['assignments'], {})
        self.assertEqual(len(result['lineage']), 1)

    def test_unselected_bridge_and_deleted_ancestry_stay_in_lineage(self):
        ancestor = self.image('ancestor', caption=False)
        first = self.text('first', parents=[ancestor['id']])
        bridge = self.text('bridge', groups=['first', 'second'])
        second = self.text('second')
        self.dataset.delete(ancestor['id'], {'revision': ancestor['source_revision']})
        result = self.r.preview(self.body([first, second]))
        self.assertTrue(result['eligible'], result)
        self.assertEqual(len(result['lineage']), 1)
        family = result['lineage'][0]
        self.assertEqual(set(family['member_ids']), {ancestor['id'], first['id'], bridge['id'], second['id']})
        self.assertEqual(family['deleted_ids'], [ancestor['id']])
        self.assertEqual(set(family['selected_ids']), {first['id'], second['id']})
        self.blocked(self.body([first, second], ratios={'train': 50, 'validation': 50, 'test': 0}),
                     'invalid', 'Too few independent source groups')
        with self.w.db:
            self.w.db.execute('DELETE FROM workbench_deleted_sources WHERE id=?', (ancestor['id'],))
        self.blocked(self.body([first, second]), 'invalid', 'no retained source lineage')

    def test_new_bridge_invalidates_preview_but_unrelated_changes_do_not(self):
        first, second = self.text('first'), self.text('second')
        body = self.body([first, second]); token = self.r.preview(body)['preview_token']
        self.text('unrelated', review='draft')
        self.assertEqual(self.r.preview(body)['preview_token'], token)
        self.text('bridge', groups=['first', 'second'])
        self.assertNotEqual(self.r.preview(body)['preview_token'], token)
        with self.assertRaisesRegex(WorkbenchError, 'Release preview changed'):
            self.r.create(dict(body, preview_token=token))
        self.assertEqual(list(self.r.path.iterdir()), [])

    def test_related_source_split_edit_invalidates_token(self):
        source = self.image('source')
        row = self.text('child', parents=[source['id']])
        body = self.body([row]); token = self.r.preview(body)['preview_token']
        with self.w.db:
            self.w.db.execute("UPDATE samples SET split='train', revision=revision+1 WHERE id=?", (source['id'],))
        preview = self.r.preview(body)
        self.assertTrue(preview['eligible'])
        self.assertEqual(preview['lineage'][0]['fixed_splits'], ['train'])
        with self.assertRaisesRegex(WorkbenchError, 'Release preview changed'):
            self.r.create(dict(body, preview_token=token))

    def test_missing_tampered_and_pixel_mismatch_assets_block_preview(self):
        row = self.image('image')
        body = self.body([row]); token = self.r.preview(body)['preview_token']
        asset, _ = self.w.asset(row['id']); data = asset.read_bytes()
        asset.unlink()
        self.blocked(body, 'unavailable', 'Source image unavailable')
        asset.write_bytes(data+b'tampered')
        self.blocked(body, 'conflict', 'Source bytes changed')
        with self.assertRaisesRegex(WorkbenchError, 'Source bytes changed'):
            self.r.create(dict(body, preview_token=token))
        asset.write_bytes(data)
        with self.w.db:
            self.w.db.execute("UPDATE workbench_records SET pixel_hash='wrong' WHERE id=?", (row['id'],))
        self.blocked(body, 'conflict', 'Source pixels changed')
        self.assertEqual(list(self.r.path.iterdir()), [])

    def test_caption_format_warnings_mixed_tasks_and_nonempty_splits(self):
        rows = [self.image('image-'+c, c) for c in ('red', 'green', 'blue')]
        body = self.body(rows, format='image_caption_v1', ratios={'train': 34, 'validation': 33, 'test': 33})
        preview = self.r.preview(body)
        self.assertTrue(preview['eligible'], preview)
        self.assertEqual(sum(w.startswith('Small image:') for w in preview['warnings']), 3)
        self.assertEqual(set(preview['split_report']['actual_counts']), {'train', 'validation', 'test'})
        canonical = self.r.preview(self.body(rows))
        self.assertTrue(any('Canonical captions' in w for w in canonical['warnings']))
        mixed = self.body(rows+[self.text('text')], format='image_caption_v1', ratios=body['ratios'])
        self.blocked(mixed, 'invalid', 'human-reviewed image-caption')
        self.blocked(self.body(rows, format='image_caption_v1'), 'invalid', 'nonempty train')
        release = self.r.create(dict(body, preview_token=preview['preview_token']))
        self.assertEqual(release['split_report'], preview['split_report'])

    def test_changed_controls_and_invalid_explicit_token_reject(self):
        row = self.text('one'); body = self.body([row]); token = self.r.preview(body)['preview_token']
        for value in (None, '', 'bad', 1, {}, []):
            with self.subTest(value=value), self.assertRaisesRegex(WorkbenchError, 'Release preview changed'):
                self.r.create(dict(body, preview_token=value))
        with self.assertRaisesRegex(WorkbenchError, 'Release preview changed'):
            self.r.create(dict(body, seed=8, preview_token=token))
        self.assertEqual(list(self.r.path.iterdir()), [])
        self.assertTrue(self.r.create(body)['id'])  # Existing tokenless clients still revalidate.

    def test_caption_pixel_duplicates_block_even_with_different_source_encodings(self):
        first = self.image('first')
        duplicate = self.image('duplicate', compress_level=0)
        green, blue = self.image('green', 'green'), self.image('blue', 'blue')
        self.assertNotEqual(first['source_sha256'], duplicate['source_sha256'])
        body = self.body([first, duplicate, green, blue], format='image_caption_v1',
                         ratios={'train': 34, 'validation': 33, 'test': 33})
        self.blocked(body, 'invalid', 'forbids exact decoded-pixel duplicates')

    def test_source_deletion_changes_relevant_freshness_but_unrelated_deletion_does_not(self):
        parent = self.image('parent'); selected = self.text('child', parents=[parent['id']])
        unrelated = self.image('unrelated', 'green')
        body = self.body([selected]); token = self.r.preview(body)['preview_token']
        self.dataset.delete(unrelated['id'], {'revision': unrelated['source_revision']})
        with self.w.db:
            self.w.db.execute('DELETE FROM workbench_deleted_sources WHERE id=?', (unrelated['id'],))
        self.assertEqual(self.r.preview(body)['preview_token'], token)
        self.dataset.delete(parent['id'], {'revision': parent['source_revision']})
        self.assertTrue(self.r.preview(body)['eligible'])
        with self.assertRaisesRegex(WorkbenchError, 'Release preview changed'):
            self.r.create(dict(body, preview_token=token))

    def test_related_fixed_split_conflicts_and_zero_weight_block(self):
        first, second = self.image('first'), self.image('second', 'green')
        selected = self.text('child', parents=[first['id'], second['id']])
        with self.w.db:
            self.w.db.execute("UPDATE samples SET split='train' WHERE id=?", (first['id'],))
            self.w.db.execute("UPDATE samples SET split='test' WHERE id=?", (second['id'],))
        other = self.text('independent')
        self.blocked(self.body([selected, other], ratios={'train': 50, 'validation': 0, 'test': 50}),
                     'invalid', 'conflicting existing splits')
        with self.w.db:
            self.w.db.execute("UPDATE samples SET split='test' WHERE id=?", (first['id'],))
        self.blocked(self.body([selected]), 'invalid', 'zero requested weight')

    def test_archive_still_verifies_bytes_after_preview_and_preflight(self):
        row = self.image('image'); body = self.body([row]); token = self.r.preview(body)['preview_token']
        checked = self.r._checked
        def change_after_check(body):
            prepared = checked(body)
            asset, _ = self.w.asset(row['id'])
            asset.write_bytes(asset.read_bytes()+b'external edit during build')
            return prepared
        with patch.object(self.r, '_checked', side_effect=change_after_check):
            with self.assertRaisesRegex(WorkbenchError, 'Source bytes changed'):
                self.r.create(dict(body, preview_token=token))
        self.assertEqual(list(self.r.path.iterdir()), [])

    def test_preview_preserves_outer_transaction(self):
        row = self.text('one')
        self.w.db.execute('BEGIN')
        self.w.db.execute("UPDATE workbench_records SET name='pending rename' WHERE id=?", (row['id'],))
        self.assertTrue(self.r.preview(self.body([row]))['eligible'])
        self.assertTrue(self.w.db.in_transaction)
        self.assertEqual(self.w._get(row['id'])['name'], 'pending rename')
        self.w.db.rollback()
        self.assertEqual(self.w._get(row['id'])['name'], 'one')

    def test_invalid_selection_controls_and_format_have_typed_blockers(self):
        row = self.text('one'); body = self.body([row])
        cases = [({'format': 'unknown'}, 'Unknown release format'),
                 ({'items': []}, 'Select 1–5,000'),
                 ({'items': body['items']*2}, 'invalid or repeated'),
                 ({'ratios': {'train': 50, 'validation': 0, 'test': 0}}, 'totaling 100'),
                 ({'seed': True}, '32-bit integer')]
        for update, message in cases:
            with self.subTest(update=update): self.blocked(dict(body, **update), 'invalid', message)

    def test_http_preview_export_and_stale_token_contract(self):
        row = self.text('http'); body = self.body([row])
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        root = f'http://127.0.0.1:{server.server_port}'
        def post(route, payload):
            request = urllib.request.Request(root+route, data=json.dumps(payload).encode(),
                                             headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        status, preview = post('/api/workbench/releases/preview', body)
        self.assertEqual(status, 200); self.assertTrue(preview['eligible'])
        self.assertEqual(list(self.r.path.iterdir()), [])
        status, release = post('/api/workbench/releases', dict(body, preview_token=preview['preview_token']))
        self.assertEqual(status, 201)
        with urllib.request.urlopen(root+release['url']) as response:
            self.assertEqual(response.status, 200); self.assertTrue(response.read().startswith(b'PK'))
        with self.assertRaises(urllib.error.HTTPError) as stale:
            post('/api/workbench/releases', dict(body, seed=8, preview_token=preview['preview_token']))
        self.assertEqual(stale.exception.code, 409)
        self.assertEqual(json.load(stale.exception)['code'], 'conflict')
        status, blocked = post('/api/workbench/releases/preview', dict(body, items=[]))
        self.assertEqual(status, 200); self.assertFalse(blocked['eligible'])
        self.assertEqual(blocked['blockers'][0]['code'], 'invalid')
        self.assertEqual(len(list(self.r.path.iterdir())), 1)

    def test_preview_savepoint_cleanup_on_unexpected_failure(self):
        row = self.text('one'); before = list(self.w.db.iterdump())
        with patch.object(self.r, '_prepare', side_effect=RuntimeError('fixture')):
            with self.assertRaisesRegex(RuntimeError, 'fixture'): self.r.preview(self.body([row]))
        self.assertEqual(list(self.w.db.iterdump()), before)
        self.assertFalse(self.w.db.in_transaction)


if __name__ == '__main__': unittest.main()
