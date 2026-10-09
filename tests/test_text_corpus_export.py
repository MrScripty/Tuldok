"""Exact corpus bytes, explicit review, whole-family allocation and immutable HTTP releases."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset, make_handler
import dataset_releases
import text_corpus_export as projection
from workbench import WorkbenchError, encode


class CorpusReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='corpus-export-')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(self.dataset.close)
        self.wb = self.dataset.workbench
        self.ordinal = 0

    def fixed_parent(self, split):
        self.ordinal += 1
        out = io.BytesIO()
        Image.new('RGB', (2, 2), (self.ordinal, 40, 80)).save(out, 'PNG')
        return self.wb.import_asset(dict(kind='image', name='split-owner.png', image=base64.b64encode(out.getvalue()).decode(),
            groups=[f'split-owner-{self.ordinal}']), source_split=split)

    def document(self, text=None, split=None, groups=None, parents=None, task='text_corpus', review='human_reviewed'):
        self.ordinal += 1
        parents = list(parents or [])
        if split:
            parents.append(self.fixed_parent(split)['id'])
        row = self.wb.import_asset(dict(kind='text', text=text or (f'Document {self.ordinal} α🙂. ' * 20),
            name=f'Document {self.ordinal}', groups=groups or [f'document-{self.ordinal}'], parents=parents,
            rights='Authored test fixture'))
        annotation = {'note': 'Reviewed for plain-text corpus training.'} if task == 'text_corpus' else {'label': 'old class'} if task == 'text_classification' else {'spans': []}
        return self.wb.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task=task, annotation=annotation, groups=row['groups'], review=review))

    def corpus(self):
        return [self.document(split=split) for split in projection.SPLITS]

    def body(self, rows, **changes):
        value = dict(format=projection.FORMAT, items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
                     ratios=dict(train=34, validation=33, test=33), seed=42)
        value.update(changes)
        return value

    def freeze(self, rows):
        body = self.body(rows)
        preview = self.dataset.releases.preview(body)
        self.assertTrue(preview['eligible'], preview)
        return self.dataset.releases.create(dict(body, preview_token=preview['preview_token'])), preview

    def blocked(self, rows, message, **changes):
        body = self.body(rows, **changes)
        preview = self.dataset.releases.preview(body)
        self.assertFalse(preview['eligible'], preview)
        self.assertIsNone(preview['preview_token'])
        self.assertIn(message, ' '.join(b['message'] for b in preview['blockers']))
        with self.assertRaises(WorkbenchError):
            self.dataset.releases.create(dict(body, preview_token='0' * 64))
        self.assertFalse(list(self.dataset.releases.path.glob('.building-*')))
        return preview

    def test_exact_unicode_offsets_separators_counts_hashes_and_evidence(self):
        rows = self.corpus()
        rows.append(self.document('  Cafe\u0301\r\n🙂山\rending\n\n', split='train'))
        result, preview = self.freeze(rows)
        with zipfile.ZipFile(self.dataset.releases.locate(result['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            mapping = [json.loads(line) for line in archive.read('documents.jsonl').splitlines()]
            self.assertEqual(manifest['format'], projection.FORMAT)
            self.assertEqual(manifest['consumer'], projection.CONSUMER)
            self.assertEqual(preview['artifact_bytes'], sum(item.file_size for item in archive.infolist()))
            originals = {row['id']: row for row in rows}
            self.assertEqual(len(mapping), len(rows))
            for split in projection.SPLITS:
                raw = archive.read(split + '.txt')
                items = [row for row in mapping if row['split'] == split]
                self.assertEqual([r['id'] for r in items], sorted(r['id'] for r in items))
                expected = b''.join(originals[r['id']]['text'].encode('utf-8') + b'\n\n' for r in items)
                self.assertEqual(raw, expected)
                self.assertEqual(manifest['files'][split + '.txt'], dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
                for item in items:
                    source = originals[item['id']]
                    self.assertEqual(raw[item['byte_start']:item['byte_end']], source['text'].encode())
                    self.assertEqual(raw[item['separator_start']:item['separator_end']], b'\n\n')
                    self.assertEqual(item['byte_end'], item['separator_start'])
                    self.assertEqual(item['separator_end'] - item['separator_start'], 2)
                    self.assertEqual(item['source_sha256'], source['source_sha256'])
                    self.assertIn(item['family'], manifest['protected_components'])
            unicode_row = next(r for r in mapping if r['id'] == rows[-1]['id'])
            self.assertEqual(archive.read('assets/' + rows[-1]['id'] + '.txt'), '  Café\n🙂山\nending\n\n'.encode())
            self.assertNotEqual(unicode_row['byte_end'] - unicode_row['byte_start'], len(rows[-1]['text']))
            for record in manifest['records']:
                for key in ('revision', 'source_revision', 'review', 'annotation', 'provenance', 'groups', 'parents', 'source_sha256'):
                    self.assertEqual(record[key], originals[record['id']][key])
                self.assertEqual(hashlib.sha256(archive.read(record['asset'])).hexdigest(), record['content_hash'])
            self.assertEqual(preview['corpus_counts']['train']['documents'], 2)
            self.assertEqual(preview['corpus_counts']['train']['families'], 2)
            self.assertIn('not EOS', archive.read('README.txt').decode())

    def test_deterministic_readonly_preview_and_immutable_reopen(self):
        rows = self.corpus()
        before = '\n'.join(self.dataset.db.iterdump())
        result, preview = self.freeze(rows)
        self.assertEqual(before, '\n'.join(self.dataset.db.iterdump()))
        data = self.dataset.releases.locate(result['id']).read_bytes()
        self.assertEqual(self.freeze(list(reversed(rows)))[0]['id'], result['id'])
        self.wb.correct_rights_note(rows[0]['id'], dict(revision=rows[0]['revision'], source_revision=1, note='Later correction'))
        reopened = Dataset(self.tmp.name)
        try:
            self.assertEqual(reopened.releases.locate(result['id']).read_bytes(), data)
        finally:
            reopened.close()

    def test_wrong_tasks_and_drafts_never_reuse_review(self):
        for task, review in (('text_classification', 'human_reviewed'), ('text_entities', 'human_reviewed'), ('text_corpus', 'draft')):
            rows = self.corpus() + [self.document(task=task, review=review)]
            preview = self.blocked(rows, 'explicit human review')
            self.assertEqual(preview['blockers'][0]['record_id'], rows[-1]['id'])

    def test_programmatic_corpus_review_is_forbidden_even_with_verifier(self):
        row = self.document()
        with self.assertRaisesRegex(WorkbenchError, 'explicit human'):
            self.wb.save(row['id'], dict(revision=row['revision'], source_revision=1, task='text_corpus',
                annotation=row['annotation'], groups=row['groups'], review='programmatically_verified'), verified_provenance={'method': 'verifier'})
        self.dataset.db.execute("UPDATE workbench_records SET review='programmatically_verified' WHERE id=?", (row['id'],))
        self.dataset.db.commit()
        self.blocked(self.corpus() + [row], 'explicit human review')

    def test_note_shape_and_corrupt_records_fail_before_analytics(self):
        rows = self.corpus()
        for note in ({'label': 'not approval'}, {'note': ''}, {'note': ' padded '}, {'note': ['bad']}, {'note': 'ok', 'extra': True}):
            with self.subTest(note=note):
                self.dataset.db.execute('UPDATE workbench_records SET annotation_json=? WHERE id=?', (encode(note), rows[0]['id']))
                self.dataset.db.commit()
                with patch('dataset_releases.analyze', side_effect=AssertionError('Invalid annotation reached analytics')):
                    preview = self.dataset.releases.preview(self.body(rows))
                self.assertFalse(preview['eligible'])
                self.assertEqual(preview['blockers'][0]['record_id'], rows[0]['id'])

    def test_groups_required(self):
        rows = self.corpus()
        self.dataset.db.execute("UPDATE workbench_records SET groups_json='[]' WHERE id=?", (rows[0]['id'],))
        self.dataset.db.commit()
        self.blocked(rows, 'protected group')

    def test_reference_context_threshold_no_quota_or_record_repair(self):
        rows = [self.document('a' * 126, split='train'), self.document('x', split='validation'), self.document('y', split='test')]
        preview = self.blocked(rows, 'more than 128')
        self.assertEqual(preview['corpus_counts']['train']['bytes'], 128)
        self.assertEqual(preview['assignments'][rows[0]['id']], 'train')
        next_row = self.document('b', parents=[rows[0]['id']])
        _, preview = self.freeze(rows + [next_row])
        self.assertEqual(preview['corpus_counts']['train']['bytes'], 131)
        self.assertEqual(preview['corpus_counts']['train']['families'], 1)
        self.assertEqual(preview['corpus_counts']['validation']['bytes'], 3)

    def test_zero_empty_splits_and_too_few_families_block(self):
        rows = [self.document()]
        self.blocked(rows, 'nonempty', ratios=dict(train=100, validation=0, test=0))
        self.blocked(rows, 'Too few independent')

    def test_fixed_splits_and_unselected_bridges_own_leakage(self):
        rows = self.corpus()
        rows.append(self.document(split='validation'))
        self.document(groups=['unselected bridge'], parents=[rows[0]['id'], rows[2]['id']])
        self.blocked(rows, 'conflicting existing splits')

    def test_deleted_fixed_parent_stays_in_family_evidence(self):
        rows = self.corpus()
        parent_id = rows[0]['parents'][0]
        # Use the source owner's retained deletion lineage without deleting unrelated data.
        with self.dataset.lock, self.dataset.db:
            self.wb.preserve_deleted_source(parent_id)
            self.dataset.db.execute('DELETE FROM samples WHERE id=?', (parent_id,))
        result, preview = self.freeze(rows)
        self.assertEqual(preview['assignments'][rows[0]['id']], 'train')
        self.assertTrue(any(parent_id in family['deleted_ids'] for family in preview['lineage']))
        with zipfile.ZipFile(self.dataset.releases.locate(result['id'])) as archive:
            self.assertIn(parent_id, archive.read('manifest.json').decode())

    def test_unknown_deleted_parent_lineage_fails_closed(self):
        rows = self.corpus()
        with self.dataset.db:
            self.dataset.db.execute('DELETE FROM samples WHERE id=?', (rows[0]['parents'][0],))
        self.blocked(rows, 'no retained source lineage')

    def test_exact_duplicates_remain_same_family(self):
        rows = self.corpus()
        # Existing import rejects exact copies. Emulate a retained legacy duplicate.
        duplicate = self.document(split='train')
        with self.dataset.db:
            self.dataset.db.execute('UPDATE workbench_records SET text=?,original_text=?,content_hash=? WHERE id=?',
                (rows[0]['text'], rows[0]['text'], rows[0]['content_hash'], duplicate['id']))
        duplicate = self.wb.get(duplicate['id'])
        result, preview = self.freeze(rows + [duplicate])
        self.assertEqual(preview['corpus_counts']['train']['documents'], 2)
        self.assertEqual(preview['corpus_counts']['train']['families'], 1)
        self.assertTrue(any('repeats' in value for value in preview['warnings']))

    def test_cross_split_duplicate_content_blocks(self):
        rows = self.corpus()
        rows.insert(1, self.document(split='validation'))
        with self.dataset.db:
            self.dataset.db.execute('UPDATE workbench_records SET text=?,original_text=?,content_hash=? WHERE id=?',
                (rows[0]['text'], rows[0]['text'], rows[0]['content_hash'], rows[-1]['id']))
        self.blocked(rows, 'conflicting existing splits')

    def test_preview_required_and_bound_to_settings_selection_and_unselected_family(self):
        rows = self.corpus()
        body = self.body(rows)
        with self.assertRaisesRegex(WorkbenchError, 'Preview the exact'):
            self.dataset.releases.create(body)
        preview = self.dataset.releases.preview(body)
        for updates in ({'seed': 43}, {'ratios': dict(train=40, validation=30, test=30)}, {'preview_token': 'f' * 64}):
            with self.assertRaisesRegex(WorkbenchError, 'preview changed'):
                self.dataset.releases.create(dict(body, preview_token=preview['preview_token']) | updates)
        self.document(parents=[rows[0]['id']])
        with self.assertRaisesRegex(WorkbenchError, 'preview changed'):
            self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        self.wb.correct_rights_note(rows[0]['id'], dict(revision=rows[0]['revision'], source_revision=1, note='New rights'))
        self.blocked(rows, 'Selection changed')

    def test_unknown_fields_bad_ratios_and_record_cap(self):
        rows = self.corpus()
        self.blocked(rows, 'Unknown corpus', context=4)
        self.blocked(rows, 'Split percentages', ratios=dict(train=True, validation=50, test=49))
        self.blocked(rows, 'Split seed', seed=True)
        self.blocked(rows, '1–5,000', items=[self.body(rows)['items'][0]] * 5001)

    def test_complete_logical_bound_includes_all_duplicate_assets_and_metadata(self):
        rows = self.corpus()
        result, preview = self.freeze(rows)
        total = preview['artifact_bytes']
        source_only = sum(len(row['text'].encode()) + 2 for row in rows)
        self.assertGreater(total, 2 * source_only)
        with patch('dataset_releases.MAX_SELECTED_TEXT_BYTES', total - 1):
            self.blocked(rows, 'complete logical archive')
        with patch('dataset_releases.MAX_SELECTED_TEXT_BYTES', total):
            self.assertTrue(self.dataset.releases.preview(self.body(rows))['eligible'])

    def test_selected_snapshot_budget_stops_loading_later_records(self):
        rows = self.corpus()
        with patch.object(self.wb, '_get', wraps=self.wb._get) as get:
            with patch('dataset_releases.MAX_SELECTED_TEXT_BYTES', 1):
                preview = self.dataset.releases.preview(self.body(rows))
        self.assertFalse(preview['eligible'])
        self.assertIn('complete logical archive', preview['blockers'][0]['message'])
        self.assertEqual(get.call_count, 1)

    def test_allocation_is_existing_record_weighted_owner(self):
        rows = [self.document('Long source ' * 10000)] + [self.document() for _ in range(5)]
        with patch('dataset_releases.allocate', wraps=dataset_releases.allocate) as owner:
            preview = self.dataset.releases.preview(self.body(rows))
        self.assertTrue(preview['eligible'], preview)
        self.assertEqual(owner.call_count, 1)
        self.assertEqual(len(owner.call_args.args), 4, 'No byte weights supplied to shared allocator')
        self.assertEqual(owner.call_args.kwargs, {})
        self.assertEqual(sum(preview['split_report']['actual_counts'].values()), len(rows))
        for split, count in preview['corpus_counts'].items():
            self.assertEqual(count['documents'], preview['split_report']['actual_counts'][split])

    def test_changed_bytes_and_publication_failure_leave_no_partial(self):
        rows = self.corpus()
        with self.dataset.db:
            self.dataset.db.execute("UPDATE workbench_records SET text=text||'changed' WHERE id=?", (rows[0]['id'],))
        self.blocked(rows, 'Source bytes changed')
        with self.dataset.db:
            self.dataset.db.execute('UPDATE workbench_records SET text=? WHERE id=?', (rows[0]['text'], rows[0]['id']))
        body = self.body(rows)
        preview = self.dataset.releases.preview(body)
        with patch('dataset_releases.archive_asset', side_effect=OSError('test disk failure')):
            with self.assertRaisesRegex(OSError, 'test disk failure'):
                self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        self.assertEqual(list(self.dataset.releases.path.iterdir()), [])

    def test_actual_http_import_review_preview_freeze_and_reopen(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        def request(route, body=None):
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + route,
                data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
            try:
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = response.read()
                return response.status, json.loads(data) if response.headers['Content-Type'].startswith('application/json') else data
        rows = []
        for index in range(3):
            status, row = request('/api/workbench/import', dict(kind='text', text=f'Document {index} café🙂.\r\n' * 20,
                name=f'HTTP document {index}', groups=[f'http-{index}'], rights='Authored fixture'))
            self.assertEqual(status, 201)
            self.assertEqual(row['review'], 'draft')
            status, row = request('/api/workbench/records/' + row['id'], dict(revision=row['revision'], source_revision=1,
                task='text_corpus', annotation={'note': 'Explicitly reviewed corpus.'}, review='human_reviewed', groups=row['groups']))
            self.assertEqual(status, 200); rows.append(row)
        body = self.body(rows)
        self.assertEqual(request('/api/workbench/releases', body)[0], 409)
        status, preview = request('/api/workbench/releases/preview', body)
        self.assertEqual(status, 200); self.assertTrue(preview['eligible'])
        status, result = request('/api/workbench/releases', dict(body, preview_token=preview['preview_token']))
        self.assertEqual(status, 201)
        status, archive = request(result['url'])
        self.assertEqual(status, 200); self.assertEqual(hashlib.sha256(archive).hexdigest(), result['id'])
        self.wb.correct_rights_note(rows[0]['id'], dict(revision=rows[0]['revision'], source_revision=1, note='Later note'))
        self.assertEqual(request('/api/workbench/releases', dict(body, preview_token=preview['preview_token']))[0], 409)
        self.assertEqual(request(result['url'])[1], archive)


if __name__ == '__main__':
    unittest.main()
