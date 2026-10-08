"""Trainer-specific projection, custody, split and immutable release regressions."""
import base64
import hashlib
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
import image_classification_export as projection
from workbench import WorkbenchError, encode


class ClassificationReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='classification-export-')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(self.dataset.close)
        self.workbench = self.dataset.workbench
        self.ordinal = 0

    def image(self, label, split='unassigned', *, color=None, groups=None,
              parents=None, review='human_reviewed', compression=6):
        self.ordinal += 1
        output = io.BytesIO()
        Image.new('RGB', (16, 12), color or (self.ordinal, 50, 100)).save(output, 'PNG', compress_level=compression)
        row = self.workbench.import_asset({'kind': 'image', 'image': base64.b64encode(output.getvalue()).decode(),
            'name': f'image-{self.ordinal}.png', 'groups': groups or [f'independent-{self.ordinal}'],
            'parents': parents or [], 'rights': 'Owned deterministic fixture'}, source_split=split)
        return self.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_classification', annotation={'label': label}, groups=row['groups'], review=review),
            verified_provenance={'method': 'fixture'} if review == 'programmatically_verified' else None)

    def corpus(self, labels=('first', 'second')):
        return [self.image(label, split) for split in projection.SPLIT_MAPPING for label in labels]

    def body(self, rows, **updates):
        result = dict(format=projection.FORMAT, items=[{key: row[key] for key in ('id', 'revision', 'source_revision')}
            for row in rows], ratios={'train': 34, 'validation': 33, 'test': 33}, seed=42)
        result.update(updates)
        return result

    def freeze(self, rows, **updates):
        body = self.body(rows, **updates)
        preview = self.dataset.releases.preview(body)
        self.assertTrue(preview['eligible'], preview['blockers'])
        return self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))

    def manifest(self, release):
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            return json.loads(archive.read('manifest.json'))

    def blocked(self, rows, text, **updates):
        body = self.body(rows, **updates)
        preview = self.dataset.releases.preview(body)
        self.assertFalse(preview['eligible'])
        self.assertIsNone(preview['preview_token'])
        self.assertIn(text, ' '.join(item['message'] for item in preview['blockers']))
        with self.assertRaises(WorkbenchError):
            self.dataset.releases.create(dict(body, preview_token='a' * 64))
        self.assertFalse(list(self.dataset.releases.path.glob('.building-*')))
        return preview

    def test_exact_projection_keeps_every_record_and_evidence(self):
        rows = self.corpus()
        release = self.freeze(rows)
        manifest = self.manifest(release)
        self.assertEqual(release['records'], len(rows))
        self.assertEqual(manifest['format'], projection.FORMAT)
        self.assertEqual(manifest['consumer'], projection.CONSUMER)
        self.assertEqual(manifest['class_to_idx'], {'class_000000': 0, 'class_000001': 1})
        self.assertEqual(manifest['class_vocabulary'], [
            {'label': 'first', 'folder': 'class_000000', 'index': 0},
            {'label': 'second', 'folder': 'class_000001', 'index': 1}])
        originals = {row['id']: row for row in rows}
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            self.assertEqual(len(archive.namelist()), len(rows) + 2)
            for row in manifest['records']:
                self.assertEqual(row['export_split'], projection.SPLIT_MAPPING[row['split']])
                self.assertEqual(row['asset'], f"{row['export_split']}/{row['class_folder']}/{row['id']}.png")
                for key in ('revision', 'source_revision', 'provenance', 'annotation', 'review', 'groups', 'parents', 'pixel_hash'):
                    self.assertEqual(row[key], originals[row['id']][key], key)
                self.assertEqual(hashlib.sha256(archive.read(row['asset'])).hexdigest(), row['asset_sha256'])
                self.assertEqual(row['asset_sha256'], row['content_hash'])
                self.assertEqual(row['exported_pixel_sha256'], row['pixel_hash'])
                self.assertIn(row['export_group'], manifest['protected_components'])

    def test_unsafe_unicode_case_distinct_labels_are_data_not_paths(self):
        labels = ('../../escape', 'CON', 'con', 'a\\b', '/absolute', '<script>🙂</script>', 'e\u0301', 'é')
        rows = self.corpus(labels)
        release = self.freeze(rows)
        manifest = self.manifest(release)
        self.assertEqual([item['label'] for item in manifest['class_vocabulary']], sorted(labels))
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            for name in archive.namelist():
                if name.endswith('.png'):
                    self.assertRegex(name, r'^(train|val|test)/class_[0-9]{6}/[a-f0-9]{32}\.png$')
            self.assertEqual(len({name.casefold() for name in archive.namelist()}), len(archive.namelist()))

    def test_deterministic_order_preview_and_frozen_bytes(self):
        rows = self.corpus()
        before = '\n'.join(self.dataset.db.iterdump())
        preview = self.dataset.releases.preview(self.body(rows))
        self.assertEqual(before, '\n'.join(self.dataset.db.iterdump()), 'Preview is read-only')
        release = self.freeze(rows)
        frozen = self.dataset.releases.locate(release['id']).read_bytes()
        self.assertEqual(self.freeze(list(reversed(rows)))['id'], release['id'])
        self.assertEqual(preview['class_coverage'][0]['counts'], {'train': 1, 'validation': 1, 'test': 1})
        row = rows[0]
        self.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_classification', annotation={'label': 'changed'}, groups=row['groups'], review='draft'))
        self.assertEqual(self.dataset.releases.locate(release['id']).read_bytes(), frozen)

    def test_only_exact_human_reviewed_classification_is_eligible(self):
        for review in ('draft', 'programmatically_verified'):
            with self.subTest(review=review):
                rows = self.corpus()
                rows.append(self.image('first', 'train', review=review))
                self.blocked(rows, 'human-reviewed')

    def test_other_tasks_are_not_reinterpreted(self):
        rows = self.corpus()
        row = rows[0]
        rows[0] = self.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_detection', annotation={'boxes': []}, groups=row['groups'], review='human_reviewed'))
        self.blocked(rows, 'single-class')

    def test_malformed_multiple_and_unnormalized_labels_are_not_silently_repaired(self):
        rows = self.corpus()
        for annotation in ({'label': ['one', 'two']}, {'label': 'one', 'labels': ['two']}, {'labels': ['one']},
                           {'label': ' padded '}, {'label': ''}):
            with self.subTest(annotation=annotation):
                self.dataset.db.execute('UPDATE workbench_records SET annotation_json=? WHERE id=?',
                                        (encode(annotation), rows[0]['id']))
                self.dataset.db.commit()
                preview = self.dataset.releases.preview(self.body(rows))
                self.assertFalse(preview['eligible'])

    def test_prevalidation_identifies_bad_record_before_analytics(self):
        rows = self.corpus()
        invalid = rows[0]
        for task, annotation, review in (
                ('image_classification', {'label': 'first'}, 'draft'),
                ('image_detection', {'boxes': []}, 'human_reviewed'),
                ('image_classification', {'label': ['ambiguous', 'multiple']}, 'human_reviewed')):
            with self.subTest(task=task, review=review, annotation=annotation):
                with self.dataset.db:
                    self.dataset.db.execute('UPDATE workbench_records SET task=?,annotation_json=?,review=? WHERE id=?',
                                            (task, encode(annotation), review, invalid['id']))
                with patch('dataset_releases.analyze', side_effect=AssertionError('Invalid target reached analytics')):
                    preview = self.dataset.releases.preview(self.body(rows))
                self.assertFalse(preview['eligible'])
                self.assertIsNone(preview['analysis'])
                self.assertIsNone(preview['preview_token'])
                self.assertEqual(preview['blockers'][0]['record_id'], invalid['id'])

    def test_single_class_blocks_named_consumer_but_not_canonical(self):
        rows = self.corpus(('only',))
        self.blocked(rows, 'at least two classes')
        self.assertTrue(self.dataset.releases.preview(self.body(rows, format='canonical_v1'))['eligible'])

    def test_missing_class_coverage_is_explicit_and_never_drops_rows(self):
        rows = self.corpus()[:-1]
        preview = self.blocked(rows, 'Missing coverage')
        self.assertEqual(preview['selected_count'], len(rows))
        self.assertEqual(preview['class_coverage'][1]['counts']['test'], 0)
        self.assertEqual(len(preview['assignments']), len(rows))

    def test_same_split_pixel_repeats_preserved_with_warning(self):
        rows = self.corpus()
        # Different raw encodings of the same normalized pixels are separate records.
        duplicate = self.image('first', 'train', color=(1, 50, 100), compression=0)
        rows.append(duplicate)
        release = self.freeze(rows)
        manifest = self.manifest(release)
        self.assertEqual(len(manifest['records']), 7)
        self.assertTrue(any('repeats' in warning for warning in manifest['warnings']))
        groups = {row['id']: row['export_group'] for row in manifest['records']}
        self.assertEqual(groups[rows[0]['id']], groups[duplicate['id']])

    def test_cross_split_pixel_repeats_block(self):
        rows = self.corpus()
        rows.append(self.image('first', 'test', color=(1, 50, 100), compression=0))
        self.blocked(rows, 'conflicting existing splits')

    def test_unselected_bridge_protects_whole_family(self):
        rows = self.corpus()
        self.image('bridge', groups=['unselected-bridge'], parents=[rows[0]['id'], rows[-1]['id']])
        self.blocked(rows, 'conflicting existing splits')

    def test_preview_required_and_stale_token_rejected(self):
        rows = self.corpus()
        body = self.body(rows)
        with self.assertRaisesRegex(WorkbenchError, 'Preview the exact'):
            self.dataset.releases.create(body)
        preview = self.dataset.releases.preview(body)
        self.image('bridge', parents=[rows[0]['id']], groups=['new-relative'])
        with self.assertRaisesRegex(WorkbenchError, 'preview changed'):
            self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))

    def test_changed_selected_revision_blocks(self):
        rows = self.corpus()
        row = rows[0]
        self.workbench.correct_rights_note(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'], note='Updated provenance'))
        self.blocked(rows, 'Selection changed')

    def test_missing_or_changed_assets_block_without_publishing(self):
        rows = self.corpus()
        asset, _ = self.workbench.asset(rows[0]['id'])
        original = asset.read_bytes()
        asset.unlink()
        self.blocked(rows, 'unavailable')
        asset.write_bytes(original + b'changed')
        self.blocked(rows, 'Source bytes changed')
        self.assertEqual(list(self.dataset.releases.path.glob('*.zip')), [])

    def test_unknown_fields_and_invalid_split_settings_fail_closed(self):
        rows = self.corpus()
        self.blocked(rows, 'Unknown classification release fields', labels=['override'])
        self.blocked(rows, 'Split percentages', ratios={'train': True, 'validation': 0, 'test': 0})
        self.blocked(rows, 'Split seed', seed=True)
        self.blocked(rows, 'zero requested weight', ratios={'train': 100, 'validation': 0, 'test': 0})

    def test_actual_http_preview_freeze_download_and_stale_rejection(self):
        rows = self.corpus()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: (server.shutdown(), thread.join()))
        def request(route, body=None):
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + route,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type': 'application/json'})
            try:
                response = urllib.request.urlopen(req)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = response.read()
                return response.status, json.loads(data) if response.headers['Content-Type'].startswith('application/json') else data
        body = self.body(rows)
        self.assertEqual(request('/api/workbench/releases', body)[0], 409)
        status, preview = request('/api/workbench/releases/preview', body)
        self.assertEqual(status, 200)
        self.assertTrue(preview['eligible'])
        status, release = request('/api/workbench/releases', dict(body, preview_token=preview['preview_token']))
        self.assertEqual(status, 201)
        status, content = request(release['url'])
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(content).hexdigest(), release['id'])
        self.workbench.correct_rights_note(rows[0]['id'], dict(revision=rows[0]['revision'],
            source_revision=rows[0]['source_revision'], note='Later correction'))
        self.assertEqual(request('/api/workbench/releases', dict(body, preview_token=preview['preview_token']))[0], 409)
        self.assertEqual(request(release['url'])[1], content)

    def test_archive_hash_failure_cleans_partial_file(self):
        rows = self.corpus()
        body = self.body(rows)
        preview = self.dataset.releases.preview(body)
        with patch('dataset_releases.archive_asset', side_effect=WorkbenchError('Source bytes changed', 'conflict', 409)):
            with self.assertRaisesRegex(WorkbenchError, 'Source bytes changed'):
                self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        self.assertEqual(list(self.dataset.releases.path.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
