"""Image-caption producer fixtures and the pinned book consumer contract.

The independent consumer is executed as its real Python CLI, not reimplemented
in this test. tests/fixtures/diffusion_check_image_data.py is an unchanged copy
of model-training-book/examples/diffusion/check_image_data.py at the recorded
SHA-256. Set TULDOK_CAPTION_CONSUMER to execute a separate checkout; its bytes
must match the same pin. All generated datasets and images live in /tmp.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
from workbench import WorkbenchError, validate_annotation


CONSUMER_SHA256 = '6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94'
CONSUMER_PATH = Path(os.environ.get(
    'TULDOK_CAPTION_CONSUMER',
    str(Path(__file__).resolve().parent / 'fixtures' / 'diffusion_check_image_data.py'),
))
CAPTION_FORMAT = 'image_caption_v1'
RATIOS = {'train': 34, 'validation': 33, 'test': 33}
OUTPUT_SPLITS = ('train', 'val', 'test')


def image_bytes(color, size=(512, 512), compress_level=6, orientation=None):
    stream = io.BytesIO()
    options = {'compress_level': compress_level}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        options['exif'] = exif
    Image.new('RGB', size, color).save(stream, 'PNG', **options)
    return stream.getvalue()


def run_consumer(test, root):
    test.assertTrue(CONSUMER_PATH.is_file(),
                    'Pinned book consumer unavailable; restore the fixture or set TULDOK_CAPTION_CONSUMER.')
    test.assertEqual(hashlib.sha256(CONSUMER_PATH.read_bytes()).hexdigest(), CONSUMER_SHA256,
                     'The consumer checkout changed; do not silently test another contract.')
    return subprocess.run([sys.executable, str(CONSUMER_PATH), str(root)],
                          capture_output=True, text=True, timeout=20, check=False)


class PinnedCaptionConsumerTests(unittest.TestCase):
    """Positive and negative trees reach the unchanged authoritative consumer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='caption-consumer-', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rows = {}
        for split, color in zip(OUTPUT_SPLITS, ('red', 'green', 'blue')):
            (self.root / split).mkdir()
            (self.root / split / 'image.png').write_bytes(image_bytes(color))
            self.rows[split] = [{'file_name': 'image.png', 'text': f'A {color} panel.',
                                 'group': f'independent-{split}'}]
        self.write_metadata()

    def write_metadata(self):
        for split, rows in self.rows.items():
            (self.root / split / 'metadata.jsonl').write_text(
                ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows),
                encoding='utf-8')

    def assert_rejected(self, message):
        self.write_metadata()
        result = run_consumer(self, self.root)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(message, result.stdout + result.stderr)

    def test_valid_three_split_tree(self):
        result = run_consumer(self, self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: 3 records', result.stdout)
        self.assertNotIn('WARNING small image', result.stdout)

    def test_each_empty_split_is_rejected(self):
        for split in OUTPUT_SPLITS:
            with self.subTest(split=split):
                original = self.rows[split]
                self.rows[split] = []
                self.assert_rejected(f'Empty {split}')
                self.rows[split] = original

    def test_empty_or_whitespace_caption_is_rejected(self):
        for caption in ('', ' \t\n'):
            with self.subTest(caption=repr(caption)):
                self.rows['train'][0]['text'] = caption
                self.assert_rejected('Empty caption')

    def test_empty_or_whitespace_group_is_rejected(self):
        for group in ('', ' \t\n'):
            with self.subTest(group=repr(group)):
                self.rows['train'][0]['group'] = group
                self.assert_rejected('Missing group')

    def test_cross_split_group_reuse_is_rejected(self):
        self.rows['val'][0]['group'] = self.rows['train'][0]['group']
        self.assert_rejected('Group crosses split')

    def test_decoded_duplicates_ignore_different_png_encoding(self):
        original = (self.root / 'train' / 'image.png').read_bytes()
        alternate = image_bytes('red', compress_level=0)
        self.assertNotEqual(hashlib.sha256(original).digest(), hashlib.sha256(alternate).digest())
        (self.root / 'val' / 'image.png').write_bytes(alternate)
        self.assert_rejected('Exact duplicate')

    def test_decoded_duplicates_in_one_split_are_also_rejected(self):
        (self.root / 'train' / 'second.png').write_bytes(image_bytes('red', compress_level=0))
        self.rows['train'].append({'file_name': 'second.png', 'text': 'Another red panel.',
                                   'group': 'different-source-same-pixels'})
        self.assert_rejected('Exact duplicate')

    def test_unnormalized_exif_is_rejected(self):
        (self.root / 'train' / 'image.png').write_bytes(image_bytes('red', orientation=6))
        self.assert_rejected('Normalize EXIF orientation')

    def test_small_image_is_a_warning_not_failure(self):
        (self.root / 'train' / 'image.png').write_bytes(image_bytes('red', size=(64, 32)))
        result = run_consumer(self, self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WARNING small image', result.stdout)
        self.assertIn('PASS: 3 records', result.stdout)


class CaptionAnnotationTests(unittest.TestCase):
    def test_exact_caption_shape_and_unicode_code_point_bound(self):
        record = {'kind': 'image', 'width': 512, 'height': 512}
        caption = '😀' * 4000
        self.assertEqual(validate_annotation('image_caption', {'caption': caption}, record),
                         {'caption': caption})
        for annotation in ({}, {'text': 'caption'}, {'caption': 'ok', 'prompt': 'hidden'},
                           {'caption': ''}, {'caption': ' \n\t'}, {'caption': None},
                           {'caption': 42}, {'caption': ['not text']},
                           {'caption': '😀' * 4001}, {'caption': '\ud800'}, []):
            with self.subTest(annotation=repr(annotation)[:100]), self.assertRaises(WorkbenchError):
                validate_annotation('image_caption', annotation, record)

    def test_caption_cannot_be_saved_on_text(self):
        with self.assertRaises(WorkbenchError):
            validate_annotation('image_caption', {'caption': 'A panel.'}, {'kind': 'text', 'text': 'panel'})


class CaptionReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='caption-release-', dir='/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.workbench = self.dataset.workbench

    def reopen(self):
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name)
        self.workbench = self.dataset.workbench

    def image(self, color, groups=None, parents=None, size=(512, 512),
              compress_level=6, orientation=None, review=True):
        row = self.workbench.import_asset({
            'kind': 'image', 'image': base64.b64encode(image_bytes(
                color, size, compress_level, orientation)).decode('ascii'),
            'name': f'{color}.png', 'groups': groups or [f'source-{color}'],
            'parents': parents or [], 'rights': 'User-owned deterministic test image',
        })
        return self.caption(row, f'A {color} panel.') if review else row

    def caption(self, row, caption='A reviewed panel.', review='human_reviewed', **extra):
        body = dict(revision=row['revision'], source_revision=row['source_revision'],
                    task='image_caption', annotation={'caption': caption},
                    groups=row['groups'], review=review)
        body.update(extra)
        kwargs = {'verified_provenance': {'method': 'fixture_verifier'}} if review == 'programmatically_verified' else {}
        return self.workbench.save(row['id'], body, **kwargs)

    def three(self):
        return [self.image(color) for color in ('red', 'green', 'blue')]

    def release(self, rows, ratios=None, format=CAPTION_FORMAT):
        body = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')}
                           for row in rows], ratios=ratios or dict(RATIOS), seed=42)
        if format is not None:
            body['format'] = format
        return self.dataset.releases.create(body)

    def extract(self, release):
        root = Path(self.tmp.name) / ('consumer-' + release['id'])
        root.mkdir(exist_ok=True)
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            archive.extractall(root)
            manifest = json.loads(archive.read('manifest.json'))
            metadata = {split: [json.loads(line) for line in archive.read(
                split + '/metadata.jsonl').decode('utf-8').splitlines() if line.strip()]
                        for split in OUTPUT_SPLITS}
        return root, manifest, metadata

    def assert_no_partial_releases(self):
        self.assertEqual(list((Path(self.tmp.name) / 'releases').glob('.building-*')), [])

    def groups_by_record(self, manifest, metadata):
        result = {}
        for record in manifest['records']:
            split = 'val' if record['split'] == 'validation' else record['split']
            projection = next(row for row in metadata[split]
                              if row['file_name'] == Path(record['asset']).name)
            result[record['id']] = projection['group']
        return result

    def assert_component(self, manifest, group, rows):
        ids = sorted(row['id'] for row in rows)
        expected_group = 'component:' + hashlib.sha256(
            json.dumps(ids, separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(group, expected_group)
        snapshots = manifest['protected_components'][group]
        self.assertEqual([row['id'] for row in snapshots], ids)
        expected = {row['id']: row for row in rows}
        keys = ('id', 'kind', 'revision', 'source_revision', 'content_hash', 'pixel_hash',
                'groups', 'parents', 'source_available', 'source_lineage_known',
                'source_split', 'source_sha256', 'book_id', 'session_id')
        for snapshot in snapshots:
            self.assertEqual(snapshot, {key: expected[snapshot['id']][key] for key in keys})

    def test_export_is_consumed_by_real_pinned_validator(self):
        rows = self.three()
        release = self.release(rows)
        root, manifest, metadata = self.extract(release)
        self.assertEqual(release['records'], 3)
        self.assertEqual(hashlib.sha256(self.dataset.releases.locate(release['id']).read_bytes()).hexdigest(),
                         release['id'])
        self.assertEqual(self.release(rows)['id'], release['id'], 'Identical frozen input should reproduce the archive.')
        self.assertEqual(len(manifest['records']), 3)
        self.assertEqual(manifest['format'], CAPTION_FORMAT)
        self.assertEqual(manifest['consumer'], {
            'path': 'examples/diffusion/check_image_data.py', 'sha256': CONSUMER_SHA256})
        self.assertEqual(manifest['split_mapping'], {'train': 'train', 'validation': 'val', 'test': 'test'})
        self.assertEqual(manifest['warnings'], [])
        expected = {row['id']: row for row in rows}
        for split, projections in metadata.items():
            self.assertEqual(len(projections), 1)
            for projection in projections:
                self.assertEqual(set(projection), {'file_name', 'text', 'group'})
                self.assertEqual(Path(projection['file_name']).name, projection['file_name'])
                self.assertEqual(Path(projection['file_name']).suffix, '.png')
                self.assertTrue(projection['group'].strip())
                self.assertEqual(projection['text'], expected[Path(projection['file_name']).stem]['annotation']['caption'])
                with Image.open(root / split / projection['file_name']) as image:
                    self.assertEqual(image.mode, 'RGB')
                    self.assertEqual(image.getexif().get(274, 1), 1)
        for record in manifest['records']:
            source = expected[record['id']]
            for key in ('revision', 'source_revision', 'content_hash', 'pixel_hash',
                        'source_sha256', 'groups', 'parents', 'provenance', 'annotation', 'review'):
                self.assertEqual(record[key], source[key], key)
            self.assertEqual(hashlib.sha256((root / record['asset']).read_bytes()).hexdigest(),
                             record['asset_sha256'])
            self.assertEqual(record['export_split'], 'val' if record['split'] == 'validation' else record['split'])
            self.assertEqual(record['exported_pixel_sha256'], record['pixel_hash'])
            projection = next(row for row in metadata[record['export_split']]
                              if row['file_name'] == Path(record['asset']).name)
            self.assertEqual(record['export_group'], projection['group'])
            self.assert_component(manifest, record['export_group'], [source])
        self.assertEqual(set(manifest['protected_components']),
                         {record['export_group'] for record in manifest['records']})
        self.assertFalse((root / 'validation').exists(), 'The consumer calls validation val.')
        result = run_consumer(self, root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: 3 records', result.stdout)

    def test_caption_text_task_and_review_filters_select_distinct_records(self):
        accepted = self.image('red')
        draft = self.caption(self.image('green'), 'A crimson panel.', review='draft')
        other = self.image('blue')
        other = self.workbench.save(other['id'], dict(revision=other['revision'], source_revision=other['source_revision'],
            task='image_classification', annotation={'label': 'red panel'}, groups=other['groups'], review='human_reviewed'))
        self.assertEqual([row['id'] for row in self.workbench.query({'q': 'red panel', 'task': 'image_caption'})['items']],
                         [accepted['id']])
        self.assertEqual({row['id'] for row in self.workbench.query({'task': 'image_caption'})['items']},
                         {accepted['id'], draft['id']})
        self.assertEqual([row['id'] for row in self.workbench.query({'task': 'image_caption', 'review': 'draft'})['items']],
                         [draft['id']])
        self.assertEqual([row['id'] for row in self.workbench.query({'task': 'image_caption', 'review': 'human_reviewed'})['items']],
                         [accepted['id']])
        with self.assertRaises(WorkbenchError):
            self.workbench.query({'task': 'unknown_caption_task'})

    def test_default_generic_release_stays_available(self):
        row = self.image('red', review=False)
        row = self.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_detection', annotation={'boxes': []}, groups=row['groups'], review='human_reviewed'))
        release = self.release([row], ratios={'train': 100, 'validation': 0, 'test': 0}, format=None)
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            self.assertIn('train/coco.json', archive.namelist())
            self.assertIn('train/records.jsonl', archive.namelist())
            self.assertNotIn('train/metadata.jsonl', archive.namelist())

    def test_draft_missing_annotation_wrong_task_and_programmatic_review_rejected(self):
        rows = self.three()
        row = self.caption(rows[0], review='draft')
        with self.assertRaises(WorkbenchError):
            self.release([row, *rows[1:]])
        row = self.caption(row, review='programmatically_verified')
        with self.assertRaises(WorkbenchError):
            self.release([row, *rows[1:]])
        row = self.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='image_classification', annotation={'label': 'panel'}, groups=row['groups'], review='human_reviewed'))
        with self.assertRaises(WorkbenchError):
            self.release([row, *rows[1:]])
        missing = self.image('yellow', review=False)
        with self.assertRaises(WorkbenchError):
            self.release([missing, *rows[1:]])
        self.assert_no_partial_releases()

    def test_text_and_unknown_release_format_rejected(self):
        text = self.workbench.import_asset(dict(kind='text', text='A plain note.', name='note', groups=['note']))
        text = self.workbench.save(text['id'], dict(revision=text['revision'], source_revision=text['source_revision'],
            task='text_classification', annotation={'label': 'note'}, groups=text['groups'], review='human_reviewed'))
        rows = self.three()
        with self.assertRaises(WorkbenchError):
            self.release([text, *rows])
        with self.assertRaises(WorkbenchError):
            self.release(rows, format='image_caption_v2')
        self.assert_no_partial_releases()

    def test_all_three_consumer_splits_must_be_nonempty(self):
        rows = self.three()
        for ratios in ({'train': 100, 'validation': 0, 'test': 0},
                       {'train': 50, 'validation': 50, 'test': 0},
                       {'train': 0, 'validation': 50, 'test': 50}):
            with self.subTest(ratios=ratios), self.assertRaises(WorkbenchError):
                self.release(rows, ratios=ratios)
        with self.assertRaises(WorkbenchError):
            self.release(rows[:2])
        self.assert_no_partial_releases()

    def test_normalized_pixels_are_exported_and_small_images_warn(self):
        rows = [self.image('red', size=(64, 32), orientation=6),
                self.image('green'), self.image('blue')]
        self.assertEqual((rows[0]['width'], rows[0]['height']), (32, 64))
        original = (Path(self.tmp.name) / 'images' / rows[0]['id'] / 'source').read_bytes()
        with Image.open(io.BytesIO(original)) as source:
            self.assertEqual(source.getexif().get(274), 6)
        release = self.release(rows)
        root, manifest, _ = self.extract(release)
        self.assertTrue(manifest['warnings'])
        self.assertEqual(release['warnings'], manifest['warnings'])
        result = run_consumer(self, root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WARNING small image', result.stdout)

    def test_source_tampering_and_stale_selection_rejected_atomically(self):
        rows = self.three()
        changed = self.caption(rows[0], 'An edited caption.')
        with self.assertRaises(WorkbenchError) as stale:
            self.release(rows)
        self.assertEqual(stale.exception.status, 409)
        rows[0] = changed
        (Path(self.tmp.name) / 'images' / rows[1]['id'] / 'image.png').write_bytes(image_bytes('purple'))
        with self.assertRaises(WorkbenchError) as tamper:
            self.release(rows)
        self.assertEqual(tamper.exception.status, 409)
        self.assertEqual(list((Path(self.tmp.name) / 'releases').glob('*.zip')), [])
        self.assert_no_partial_releases()

    def test_stale_source_revision_rejected(self):
        rows = self.three()
        sample = self.dataset.sample(rows[0]['id'])
        self.dataset.save(sample['id'], dict(revision=sample['revision'], book_id='', session_id=sample['session_id'],
            split='unassigned', annotation={'book_present': False, 'crop_suitable': False, 'corners': []}))
        with self.assertRaises(WorkbenchError) as stale:
            self.release(rows)
        self.assertEqual(stale.exception.status, 409)

    def test_same_pixels_with_changed_source_bytes_rejected(self):
        rows = self.three()
        asset = Path(self.tmp.name) / 'images' / rows[0]['id'] / 'image.png'
        alternate = image_bytes('red', compress_level=0)
        self.assertNotEqual(hashlib.sha256(alternate).hexdigest(), rows[0]['content_hash'])
        asset.write_bytes(alternate)
        with self.assertRaises(WorkbenchError) as tamper:
            self.release(rows)
        self.assertEqual(tamper.exception.status, 409)
        self.assertEqual(list((Path(self.tmp.name) / 'releases').glob('*.zip')), [])
        self.assert_no_partial_releases()

    def test_invalid_caption_save_keeps_current_revision_and_history(self):
        row = self.image('red')
        before = self.workbench.history(row['id'])
        with self.assertRaises(WorkbenchError):
            self.caption(row, caption=' ', groups=['would-change-group'])
        self.assertEqual(self.workbench.get(row['id']), row)
        self.assertEqual(self.workbench.history(row['id']), before)

    def test_decoded_duplicate_selection_is_rejected_even_with_distinct_groups(self):
        first = self.image('red', groups=['red-first'])
        duplicate = self.image('red', groups=['red-second'], compress_level=0)
        self.assertNotEqual(first['source_sha256'], duplicate['source_sha256'])
        self.assertEqual(first['pixel_hash'], duplicate['pixel_hash'])
        with self.assertRaises(WorkbenchError):
            self.release([first, duplicate, self.image('green'), self.image('blue')])
        self.assert_no_partial_releases()

    def test_multi_group_and_unselected_parent_bridge_share_one_consumer_group(self):
        first = self.image('red', groups=['first', 'shared'])
        second = self.image('green', groups=['second', 'shared'])
        third = self.image('blue', groups=['third'])
        bridge = self.workbench.import_asset(dict(kind='text', text='unselected parent bridge', name='bridge',
            groups=['bridge'], parents=[second['id'], third['id']]))
        rows = [first, second, third, self.image('yellow'), self.image('purple')]
        root, manifest, metadata = self.extract(self.release(rows))
        groups = self.groups_by_record(manifest, metadata)
        self.assertEqual(groups[first['id']], groups[second['id']])
        self.assertEqual(groups[first['id']], groups[third['id']])
        self.assertEqual(len(set(groups.values())), 3)
        self.assert_component(manifest, groups[first['id']], [first, second, third, bridge])
        splits = {row['id']: row['split'] for row in manifest['records']}
        self.assertEqual(splits[first['id']], splits[third['id']])
        result = run_consumer(self, root)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_deleted_duplicate_bridge_retains_component_group_after_reopen(self):
        first = self.image('red', groups=['first'])
        bridge = self.image('red', groups=['bridge', 'second-link'], compress_level=0, review=False)
        second = self.image('green', groups=['second', 'second-link'])
        sample = self.dataset.sample(bridge['id'])
        self.dataset.delete(bridge['id'], {'revision': sample['revision']})
        self.reopen()
        retained = self.workbench.get(bridge['id'])
        self.assertFalse(retained['source_available'])
        self.assertTrue(retained['source_lineage_known'])
        rows = [self.workbench.get(first['id']), self.workbench.get(second['id']),
                self.image('blue'), self.image('yellow')]
        _, manifest, metadata = self.extract(self.release(rows))
        groups = self.groups_by_record(manifest, metadata)
        self.assertEqual(groups[first['id']], groups[second['id']])
        self.assertEqual(len(set(groups.values())), 3)
        self.assert_component(manifest, groups[first['id']], [rows[0], rows[1], retained])
        with self.dataset.db:
            self.dataset.db.execute('DELETE FROM workbench_deleted_sources WHERE id=?', (bridge['id'],))
        with self.assertRaises(WorkbenchError):
            self.release(rows)

    def test_legacy_book_assignments_preserved_in_consumer_groups(self):
        first, second = self.image('red'), self.image('green')
        for row in (first, second):
            sample = self.dataset.sample(row['id'])
            self.dataset.save(row['id'], dict(revision=sample['revision'], book_id='one-shared-book',
                session_id=sample['session_id'], split='test',
                annotation={'book_present': False, 'crop_suitable': False, 'corners': []}))
        rows = [self.workbench.get(first['id']), self.workbench.get(second['id']),
                self.image('blue'), self.image('yellow')]
        _, manifest, metadata = self.extract(self.release(rows))
        groups = self.groups_by_record(manifest, metadata)
        self.assertEqual(groups[first['id']], groups[second['id']])
        self.assert_component(manifest, groups[first['id']], rows[:2])
        for record in manifest['records']:
            if record['id'] in (first['id'], second['id']):
                self.assertEqual(record['split'], 'test')
                self.assertEqual(record['book_id'], 'one-shared-book')

    def test_deleted_parent_preserves_legacy_book_split_in_caption_projection(self):
        parent, sibling = self.image('red'), self.image('green')
        child = self.image('blue', parents=[parent['id']])
        for row in (parent, sibling):
            sample = self.dataset.sample(row['id'])
            self.dataset.save(row['id'], dict(revision=sample['revision'], book_id='retained-book',
                session_id=sample['session_id'], split='test',
                annotation={'book_present': False, 'crop_suitable': False, 'corners': []}))
        sample = self.dataset.sample(parent['id'])
        self.dataset.delete(parent['id'], {'revision': sample['revision']})
        self.reopen()
        retained = self.workbench.get(parent['id'])
        sibling, child = self.workbench.get(sibling['id']), self.workbench.get(child['id'])
        root, manifest, metadata = self.extract(self.release([
            sibling, child, self.image('yellow'), self.image('purple')]))
        groups = self.groups_by_record(manifest, metadata)
        self.assertEqual(groups[sibling['id']], groups[child['id']])
        self.assert_component(manifest, groups[child['id']], [retained, sibling, child])
        for record in manifest['records']:
            if record['id'] in (sibling['id'], child['id']):
                self.assertEqual(record['split'], 'test')
                self.assertEqual(record['export_split'], 'test')
        self.assertEqual(len(metadata['test']), 2)
        result = run_consumer(self, root)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_frozen_release_survives_annotation_edit_delete_and_reopen(self):
        rows = self.three()
        release = self.release(rows)
        path = self.dataset.releases.locate(release['id'])
        frozen = path.read_bytes()
        self.caption(rows[0], 'A later description.')
        sample = self.dataset.sample(rows[1]['id'])
        self.dataset.delete(rows[1]['id'], {'revision': sample['revision']})
        self.reopen()
        self.assertEqual(self.dataset.releases.locate(release['id']).read_bytes(), frozen)
        root, manifest, metadata = self.extract(release)
        expected = {row['id']: row['annotation'] for row in rows}
        self.assertEqual({row['id']: row['annotation'] for row in manifest['records']}, expected)
        self.assertEqual(sum(map(len, metadata.values())), 3)
        result = run_consumer(self, root)
        self.assertEqual(result.returncode, 0, result.stderr)
        current = [self.workbench.get(row['id']) for row in rows]
        with self.assertRaises(WorkbenchError):
            self.release(current)

    def test_generation_prompt_remains_provenance_not_caption(self):
        prompt = 'Generate a dramatic blue panel; this is not its caption.'
        result = {'image': base64.b64encode(image_bytes('blue')).decode('ascii'), 'metadata': {'seed': 7}}
        with patch.object(self.dataset.image_requests, 'generate', return_value=result):
            self.dataset.generation_jobs.start(dict(server_url='http://localhost:1234', model='fixture-image-model',
                prompt=prompt, size='512x512', count=1, strategy='repeat', session_id='generated-panel', seed=7))
            self.dataset.generation_jobs.worker.join(10)
            self.assertFalse(self.dataset.generation_jobs.worker.is_alive())
        state = self.dataset.generation_jobs.snapshot()
        self.assertEqual(state['jobs'][0]['status'], 'completed')
        generated = self.workbench.get(state['entries'][0]['sample_id'])
        self.assertIsNone(generated['annotation'])
        self.assertEqual(generated['review'], 'draft')
        self.assertEqual(generated['provenance']['generation']['prompt'], prompt)
        caption = 'A plain blue square.'
        generated = self.caption(generated, caption)
        _, manifest, metadata = self.extract(self.release([generated, self.image('red'), self.image('green')]))
        record = next(record for record in manifest['records'] if record['id'] == generated['id'])
        self.assertEqual(record['provenance']['generation']['prompt'], prompt)
        projection = next(row for rows in metadata.values() for row in rows
                          if row['file_name'] == Path(record['asset']).name)
        self.assertEqual(projection['text'], caption)
        self.assertNotEqual(projection['text'], prompt)


if __name__ == '__main__':
    unittest.main()
