"""Native manifest admission traverses actual HTTP, SQLite and original assets."""
import base64
import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image
from app import Dataset, make_handler
from bulk_import import MAX_ROW_BYTES


class BulkImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dataset = Dataset(self.temp.name)
        self.open_server()
        self.addCleanup(self.close)
        stream = io.BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        Image.new('RGB', (24, 18), '#467e9a').save(stream, 'JPEG', exif=exif)
        self.raw = stream.getvalue()

    def open_server(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.dataset.close()

    def request(self, route, body=None):
        request = urllib.request.Request(self.root + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def row(self, kind='text', **extra):
        return dict({'kind': kind, 'groups': ['source-book'], 'rights': 'Authored source'}, **extra)

    def payload(self, row, number=1, **extra):
        body = dict(source_name='assets.jsonl', row_number=number,
                    request_id=uuid.uuid4().hex, line=row if isinstance(row, str) else json.dumps(row))
        if isinstance(row, dict) and row.get('kind') == 'image':
            body.update(image_name=row['file'], image=base64.b64encode(self.raw).decode())
        return dict(body, **extra)

    def admit(self, row, **extra):
        body = self.payload(row, **extra)
        status, result = self.request('/api/workbench/import-row', body)
        self.assertEqual(status, 201, result)
        self.assertEqual(result['row_sha256'], hashlib.sha256(body['line'].encode()).hexdigest())
        record = self.dataset.workbench.get(result['record_id'])
        self.assertEqual((result['revision'], result['source_revision']),
                         (record['revision'], record['source_revision']))
        return body, result

    def test_mixed_sources_keep_originals_provenance_and_draft_review_after_restart(self):
        text_body, text = self.admit(self.row(text='cafe\u0301\r\n', name='Real note'))
        image_body, image = self.admit(self.row('image', file='oriented.jpg', parents=[text['record_id']]), number=2)
        original = self.dataset.db.execute('SELECT original_text FROM workbench_records WHERE id=?', (text['record_id'],)).fetchone()[0]
        self.assertEqual(original, 'cafe\u0301\r\n')
        self.assertEqual(self.dataset.workbench.get(text['record_id'])['text'], 'café\n')
        source = Path(self.temp.name) / 'images' / image['record_id'] / 'source'
        self.assertEqual(source.read_bytes(), self.raw)
        record = self.dataset.workbench.get(image['record_id'])
        self.assertEqual((record['width'], record['height']), (18, 24))
        self.assertEqual(record['parents'], [text['record_id']])
        self.assertEqual(record['provenance']['source_sha256'], hashlib.sha256(self.raw).hexdigest())
        before = [self.dataset.workbench.get(result['record_id']) for result in (text, image)]
        self.close()
        self.dataset = Dataset(self.temp.name)
        self.open_server()
        for body, result, old in zip((text_body, image_body), (text, image), before):
            status, found = self.request('/api/workbench/import-result/' + body['request_id'])
            self.assertEqual(status, 200)
            self.assertEqual(found, dict(found=True, **result))
            record = self.dataset.workbench.get(result['record_id'])
            self.assertEqual(record, old)
            self.assertEqual(record['review'], 'draft')
            self.assertIsNone(record['annotation'])
            context = record['provenance']['acquisition']
            self.assertEqual(context['format'], 'tuldok_assets_jsonl_v1')
            self.assertEqual(context['row_sha256'], hashlib.sha256(body['line'].encode()).hexdigest())
            self.assertEqual(context['declared']['manifest_name'], 'assets.jsonl')
            self.assertEqual(context['declared']['row_number'], body['row_number'])
            self.assertEqual(record['groups'], ['source-book'])
            self.assertEqual(record['provenance']['rights'], 'Authored source')

    def test_partial_invalid_rows_and_duplicates_leave_prior_rows_unchanged(self):
        source, created = self.admit(self.row(text='first real source'))
        saved = self.dataset.workbench.get(created['record_id'])
        bad = ['{broken', self.row(), self.row(text='forged', review='human_reviewed'),
               self.row(text='forged', annotation={'label': 'accepted'}),
               self.row(text='forged', provenance={'source_sha256': 'forged'}),
               self.row('image', file='photo.jpg')]
        for number, row in enumerate(bad, 2):
            body = self.payload(row, number=number)
            if isinstance(row, dict) and row.get('kind') == 'image':
                del body['image']
            status, error = self.request('/api/workbench/import-row', body)
            self.assertEqual(status, 400, error)
        _, image = self.admit(self.row('image', file='photo.jpg'), number=8)
        for number, row in enumerate((self.row(text='first real source'), self.row('image', file='photo.jpg')), 9):
            status, error = self.request('/api/workbench/import-row', self.payload(row, number=number))
            self.assertEqual(status, 409, error)
        self.admit(self.row(text='last valid source', parents=[created['record_id']]), number=11)
        self.assertEqual(self.dataset.workbench.get(created['record_id']), saved)
        self.assertEqual(self.dataset.workbench.query({})['total'], 3)
        self.assertEqual(len(self.dataset.rows()), 1)
        self.assertEqual(len(list((Path(self.temp.name) / 'images').iterdir())), 1)
        self.assertEqual(self.dataset.db.execute('SELECT COUNT(*) FROM workbench_history').fetchone()[0], 3)
        self.assertNotEqual(image['record_id'], created['record_id'])

    def test_duplicate_keys_unknown_fields_and_bad_references_are_rejected(self):
        cases = ['[]', 'null', '{"kind":"text","kind":"image"}',
                 '{"kind":"text","groups":["s"],"text":"x","rights":NaN}',
                 '{\n"kind":"text","groups":["s"],"text":"x"}',
                 self.row(text='x', groups=[]), self.row(text='x', parents=['missing']),
                 self.row(text='x', name='x'*201), self.row(text='x', task='text_classification')]
        for reference in ('../image.jpg', 'folder/image.jpg', 'folder\\image.jpg', 'https://example.com/image.jpg',
                          '.', '..', ' image.jpg', 'image.jpg ', 'image\x00.jpg'):
            cases.append(self.row('image', file=reference))
        for row in cases:
            with self.subTest(row=row):
                status, error = self.request('/api/workbench/import-row', self.payload(row))
                self.assertEqual(status, 400, error)
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)
        self.assertEqual(self.dataset.rows(), [])

    def test_transport_and_row_bounds_do_not_admit_partial_records(self):
        valid = self.payload(self.row(text='bounded source'))
        overrides = ({'row_number': n} for n in (0, 1001, True, 1.5, '1'))
        cases = [dict(valid, **change) for change in overrides]
        cases.extend(dict(valid, request_id=marker) for marker in ('', 'x'*32, True, None))
        cases.extend((dict(valid, source_name='../assets.jsonl'), dict(valid, line=' '*(MAX_ROW_BYTES+1)),
                      dict(valid, line='\ud800'), dict(valid, image='unexpected'), dict(valid, unknown='field')))
        for body in cases:
            status, error = self.request('/api/workbench/import-row', body)
            self.assertEqual(status, 400, error)
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)

    def test_image_binding_and_damage_errors_do_not_write_assets(self):
        body = self.payload(self.row('image', file='selected.jpg'))
        for extra in ({'image_name': 'different.jpg'}, {'image': 'not-base64'},
                      {'image': base64.b64encode(b'not an image').decode()}):
            status, error = self.request('/api/workbench/import-row', dict(body, **extra))
            self.assertEqual(status, 400, error)
        self.assertEqual(self.dataset.rows(), [])
        self.assertEqual(list((Path(self.temp.name) / 'images').iterdir()), [])

    def test_repeated_marker_and_content_cannot_replace_review_or_provenance(self):
        body, result = self.admit(self.row(text='stable source'))
        record = self.dataset.workbench.get(result['record_id'])
        reviewed = self.dataset.workbench.save(record['id'], dict(revision=record['revision'], source_revision=record['source_revision'],
            task='text_classification', annotation={'label': 'human decision'}, review='human_reviewed', groups=record['groups']))
        repeated = dict(body, line=json.dumps(self.row(text='different asset', groups=['other'])))
        for retry in (repeated, self.payload(self.row(text='stable source', groups=['other']))):
            status, error = self.request('/api/workbench/import-row', retry)
            self.assertEqual(status, 409, error)
        self.assertEqual(self.dataset.workbench.get(record['id']), reviewed)
        status, found = self.request('/api/workbench/import-result/' + body['request_id'])
        self.assertEqual(status, 200)
        self.assertEqual(found['review'], 'human_reviewed')
        self.assertEqual(found['record_id'], record['id'])
        self.assertEqual((found['revision'], found['source_revision']),
                         (reviewed['revision'], reviewed['source_revision']))
        self.assertEqual(self.dataset.workbench.query({})['total'], 1)

    def test_confirmed_pairs_save_exact_sets_and_later_changes_conflict(self):
        body, receipt = self.admit(self.row(text='Batch selected source'))
        pair = dict(id=receipt['record_id'], revision=receipt['revision'],
                    source_revision=receipt['source_revision'])
        original = self.dataset.workbench.get(pair['id'])
        status, saved = self.request('/api/workbench/selections', {'name': 'Imported batch', 'items': [pair]})
        self.assertEqual(status, 201, saved)
        self.assertEqual(saved['items'][0]['revision'], pair['revision'])
        self.assertEqual(self.dataset.workbench.get(pair['id']), original)
        reviewed = self.dataset.workbench.save(pair['id'], dict(pair, task='text_classification',
            annotation={'label': 'Human target'}, review='human_reviewed', groups=original['groups']))
        self.assertEqual(self.request('/api/workbench/selections', {'name': 'Stale batch', 'items': [pair]})[0], 409)
        before = list(self.dataset.db.iterdump())
        for _ in range(2):
            status, current = self.request('/api/workbench/import-result/' + body['request_id'])
            self.assertEqual(status, 200)
            self.assertEqual(current['revision'], reviewed['revision'])
            self.assertEqual(current['source_revision'], reviewed['source_revision'])
        self.assertEqual(list(self.dataset.db.iterdump()), before)
        status, loaded = self.request('/api/workbench/selections/' + saved['id'])
        self.assertEqual(status, 200)
        self.assertEqual(loaded['members'][0]['status'], 'stale')
        self.assertEqual(loaded['selection']['items'][0]['revision'], receipt['revision'])

    def test_storage_failure_is_fatal_and_atomic_not_a_bad_user_row(self):
        with self.dataset.db:
            self.dataset.db.execute('''CREATE TRIGGER reject_bulk_metadata BEFORE UPDATE OF groups_json ON workbench_records
                BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END''')
        body = self.payload(self.row('image', file='photo.jpg'))
        status, error = self.request('/api/workbench/import-row', body)
        self.assertEqual(status, 500)
        self.assertEqual(error['code'], 'storage')
        self.assertEqual(self.dataset.rows(), [])
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)
        self.assertEqual(list((Path(self.temp.name) / 'images').iterdir()), [])
        self.assertEqual(self.request('/api/workbench/import-result/' + body['request_id']), (200, {'found': False}))

    def test_result_lookup_is_read_only_and_absence_is_not_completion(self):
        marker = uuid.uuid4().hex
        before = list(self.dataset.db.iterdump())
        self.assertEqual(self.request('/api/workbench/import-result/' + marker), (200, {'found': False}))
        self.assertEqual(list(self.dataset.db.iterdump()), before)
        self.assertEqual(self.request('/api/workbench/import-result/not-a-marker')[0], 400)
        body, result = self.admit(self.row(text='confirmed row'))
        before = list(self.dataset.db.iterdump())
        for _ in range(2):
            self.assertEqual(self.request('/api/workbench/import-result/' + body['request_id']), (200, dict(found=True, **result)))
        self.assertEqual(list(self.dataset.db.iterdump()), before)

    def test_post_commit_read_failure_returns_error_but_saved_result_confirms_admission(self):
        body = self.payload(self.row('image', file='photo.jpg'))
        original = self.dataset.workbench._get
        def fail_after_commit(record_id):
            if not self.dataset.db.in_transaction:
                # Actual SQLite read failure at the existing post-commit return
                # boundary, after original bytes and enrollment have committed.
                self.dataset.db.execute('SELECT missing_response_column FROM samples')
            return original(record_id)
        with patch.object(self.dataset.workbench, '_get', side_effect=fail_after_commit):
            status, error = self.request('/api/workbench/import-row', body)
        self.assertEqual(status, 500)
        self.assertEqual(error['code'], 'storage')
        self.assertEqual(len(self.dataset.rows()), 1)
        status, found = self.request('/api/workbench/import-result/' + body['request_id'])
        self.assertEqual(status, 200)
        self.assertTrue(found['found'])
        self.assertEqual(found['row_sha256'], hashlib.sha256(body['line'].encode()).hexdigest())
        record = self.dataset.workbench.get(found['record_id'])
        self.assertEqual(record['review'], 'draft')
        self.assertIsNone(record['annotation'])
        self.assertEqual(record['provenance']['rights'], 'Authored source')
        self.assertEqual((Path(self.temp.name) / 'images' / record['id'] / 'source').read_bytes(), self.raw)
