"""Native caption admission through real HTTP/SQLite/Pillow/frozen consumer."""
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
import zipfile

from PIL import Image, PngImagePlugin
from app import Dataset, make_handler
from caption_import import MAX_SOURCE, origin_groups
from dataset_releases import CAPTION_CONSUMER

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/native-caption-release'
CONSUMER = Path(__file__).parent / 'fixtures/diffusion_check_image_data.py'


class CaptionImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='caption-import-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.dataset = Dataset(self.path / 'dataset')
        self.open_server()
        self.addCleanup(self.close)
        self.source = dict(manifest=(FIXTURE / 'manifest.json').read_text(), metadata={
            split: (FIXTURE / split / 'metadata.jsonl').read_text() for split in ('train', 'val', 'test')})
        self.manifest = json.loads(self.source['manifest'])

    def open_server(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.dataset.close()

    def request(self, route, body=None):
        request = urllib.request.Request(self.root + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error: return error.code, json.load(error)

    def prepare(self, source=None):
        status, result = self.request('/api/workbench/caption-import/prepare', source or self.source)
        self.assertEqual(status, 200, result)
        return result['rows']

    def payload(self, row):
        return dict(token=row['token'], asset=row['asset'], request_id=uuid.uuid4().hex,
                    image=base64.b64encode((FIXTURE / row['asset']).read_bytes()).decode())

    def count(self):
        return self.dataset.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0]

    def source_for(self, manifest):
        result = copy.deepcopy(self.source); result['manifest'] = json.dumps(manifest)
        return result

    def empty_storage(self):
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workbench_history').fetchone()[0], 0)
        self.assertEqual(list((self.dataset.path / 'images').iterdir()), [])

    def test_native_roundtrip_persists_draft_identity_history_splits_and_requires_new_review(self):
        rows = self.prepare(); self.empty_storage()
        admitted = []
        for row in rows:
            body = self.payload(row)
            status, result = self.request('/api/workbench/caption-import/row', body)
            self.assertEqual(status, 201, result)
            origin = next(r for r in self.manifest['records'] if r['asset'] == row['asset'])
            record = self.dataset.workbench.get(result['record_id'])
            self.assertNotEqual(record['id'], origin['id'])
            self.assertEqual((record['task'], record['review'], record['revision'], record['parents']), ('image_caption', 'draft', 1, []))
            self.assertEqual(record['annotation'], origin['annotation'])
            self.assertEqual(record['source_sha256'], hashlib.sha256((FIXTURE / row['asset']).read_bytes()).hexdigest())
            self.assertEqual(record['pixel_hash'], origin['exported_pixel_sha256'])
            self.assertEqual(record['source_split'], origin['split'])
            self.assertEqual(record['provenance']['rights'], 'unknown')
            self.assertEqual(record['provenance']['acquisition']['declared']['origin_record'], origin)
            self.assertEqual(self.dataset.workbench.history(record['id']), [record])
            admitted.append((body, record, origin))
        self.assertTrue(any(r['source_sha256'] != origin['source_sha256'] for _, r, origin in admitted))
        before = self.dataset.workbench._all()
        self.close(); self.dataset = Dataset(self.path / 'dataset'); self.open_server()
        self.assertEqual(self.dataset.workbench._all(), before)
        for body, record, _ in admitted:
            status, saved = self.request('/api/workbench/import-result/' + body['request_id'])
            self.assertEqual(status, 200); self.assertTrue(saved['found']); self.assertEqual(saved['record_id'], record['id'])
        stale = self.payload(rows[0]); status, _ = self.request('/api/workbench/caption-import/row', stale)
        self.assertEqual(status, 400, 'Preparation expires on restart')
        release_body = dict(format='image_caption_v1', seed=42,
            ratios={'train': 34, 'validation': 33, 'test': 33},
            items=[{key: r[key] for key in ('id', 'revision', 'source_revision')} for _, r, _ in admitted])
        status, blocked = self.request('/api/workbench/releases', release_body)
        self.assertEqual(status, 400); self.assertIn('human-reviewed', blocked['error'])
        for _, record, _ in admitted:
            status, reviewed = self.request('/api/workbench/records/' + record['id'], dict(
                revision=record['revision'], source_revision=record['source_revision'],
                task=record['task'], annotation=record['annotation'], groups=record['groups'], review='human_reviewed'))
            self.assertEqual(status, 200)
            next(item for item in release_body['items'] if item['id'] == record['id'])['revision'] = reviewed['revision']
        status, release = self.request('/api/workbench/releases', release_body)
        self.assertEqual(status, 201, release)
        with urllib.request.urlopen(self.root + release['url']) as response: archive_bytes = response.read()
        self.assertEqual(hashlib.sha256(archive_bytes).hexdigest(), release['id'])
        destination = self.path / 'consumer'; destination.mkdir()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive: archive.extractall(destination)
        self.assertEqual(hashlib.sha256(CONSUMER.read_bytes()).hexdigest(), CAPTION_CONSUMER['sha256'])
        consumer = subprocess.run([sys.executable, str(CONSUMER), str(destination)], capture_output=True, text=True, timeout=20)
        self.assertEqual(consumer.returncode, 0, consumer.stderr)
        self.assertIn('PASS: 4 records', consumer.stdout)
        frozen = json.loads((destination / 'manifest.json').read_text())
        compare = lambda records: sorted((r['exported_pixel_sha256'], r['annotation']['caption'], r['split']) for r in records)
        self.assertEqual(compare(frozen['records']), compare(self.manifest['records']))
        # A second native round-trip retains previous origin tokens verbatim.
        second = dict(manifest=(destination / 'manifest.json').read_text(), metadata={
            split: (destination / split / 'metadata.jsonl').read_text() for split in ('train', 'val', 'test')})
        self.assertEqual(self.request('/api/workbench/caption-import/prepare', second)[0], 200)
        for family in frozen['protected_components'].values():
            tokens = origin_groups(family)
            for member in family: self.assertTrue(set(member['groups']) <= set(tokens))

    def test_metadata_format_label_paths_and_exact_sets_are_strict_without_mutation(self):
        split = self.manifest['records'][0]['export_split']
        def rows_change(source, change):
            lines = [json.loads(line) for line in source['metadata'][split].splitlines()]
            change(lines)
            source['metadata'][split] = '\n'.join(json.dumps(line) for line in lines) + '\n'
        cases = [lambda s: rows_change(s, lambda rows: rows[0].update(text='changed')),
                 lambda s: rows_change(s, lambda rows: rows[0].update(file_name='../escape.png')),
                 lambda s: rows_change(s, lambda rows: rows[0].update(file_name='https://example.com/a.png')),
                 lambda s: rows_change(s, lambda rows: rows[0].update(review='human_reviewed')),
                 lambda s: rows_change(s, lambda rows: rows.append(rows[0])),
                 lambda s: s['metadata'].update(train=''),
                 lambda s: s.update(manifest='{"schema_version":1,"schema_version":1}'),
                 lambda s: s.update(manifest='NaN'),
                 lambda s: s.update(manifest=' ' * (MAX_SOURCE + 1)),
                 lambda s: s['metadata'].update(train='\ud800'),
                 lambda s: s['metadata'].update(train='\n' * 1001)]
        for index, change in enumerate(cases):
            with self.subTest(index=index):
                source = copy.deepcopy(self.source); change(source)
                status, result = self.request('/api/workbench/caption-import/prepare', source)
                self.assertEqual(status, 400, result); self.empty_storage()

    def test_native_manifest_hashes_snapshots_geometry_and_family_validation(self):
        cases = [lambda m: m.update(format='canonical_v1'), lambda m: m.update(schema_version=True),
                 lambda m: m['consumer'].update(sha256='0' * 64),
                 lambda m: m['records'][0].update(annotation={'caption': 'x' * 4001}),
                 lambda m: m['records'][0].update(annotation={'caption': 'ok', 'prompt': 'forged'}),
                 lambda m: m['records'][0].update(asset_sha256='0' * 64),
                 lambda m: m['records'][0].update(exported_pixel_sha256='0' * 64),
                 lambda m: m['records'][0].update(export_group=[]),
                 lambda m: m['records'][0].update(parents=[{}]),
                 lambda m: m['records'][0].update(width=True),
                 lambda m: m['records'][0].update(source_lineage_known=False),
                 lambda m: m['protected_components'].clear(),
                 lambda m: m['records'].append(m['records'][0])]
        for index, change in enumerate(cases):
            with self.subTest(index=index):
                manifest = copy.deepcopy(self.manifest); change(manifest)
                status, result = self.request('/api/workbench/caption-import/prepare', self.source_for(manifest))
                self.assertEqual(status, 400, result); self.empty_storage()

    def test_assets_cannot_substitute_bytes_or_tamper_preparation(self):
        row = self.prepare()[0]
        for change in (lambda b: b.update(image='not base64'), lambda b: b.update(image=None),
                       lambda b: b.update(asset='../wrong.png'), lambda b: b.update(request_id='invalid'),
                       lambda b: b.update(token=b['token'][:-1] + ('0' if b['token'][-1] != '0' else '1')),
                       lambda b: b.update(token=b['token'].split('.')[0]+'.'+'😀'*64),
                       lambda b: b.update(review='human_reviewed')):
            body = self.payload(row); change(body)
            self.assertEqual(self.request('/api/workbench/caption-import/row', body)[0], 400); self.empty_storage()
        for mode, orientation, damaged in (('RGBA', 1, False), ('RGB', 6, False), ('RGB', 1, True)):
            manifest = copy.deepcopy(self.manifest); record = manifest['records'][0]
            buffer = io.BytesIO(); exif = Image.Exif(); exif[274] = orientation
            Image.new(mode, (record['width'], record['height']), 'red').save(buffer, 'PNG', exif=exif)
            raw = b'damaged PNG' if damaged else buffer.getvalue()
            record['content_hash'] = record['asset_sha256'] = hashlib.sha256(raw).hexdigest()
            member = next(r for r in manifest['protected_components'][record['export_group']] if r['id'] == record['id'])
            member['content_hash'] = record['content_hash']
            prepared = self.prepare(self.source_for(manifest))
            body = self.payload(next(r for r in prepared if r['asset'] == record['asset']))
            body['image'] = base64.b64encode(raw).decode()
            self.assertEqual(self.request('/api/workbench/caption-import/row', body)[0], 400); self.empty_storage()

    def test_caption_update_and_initial_history_failures_rollback_files_and_source(self):
        row = self.prepare()[0]
        triggers = ["BEFORE UPDATE OF annotation_json ON workbench_records BEGIN SELECT RAISE(ABORT,'caption failed'); END",
                    "BEFORE INSERT ON workbench_history WHEN json_extract(NEW.snapshot,'$.task')='image_caption' BEGIN SELECT RAISE(ABORT,'history failed'); END"]
        for trigger in triggers:
            with self.dataset.db: self.dataset.db.execute('CREATE TRIGGER fail_caption ' + trigger)
            status, result = self.request('/api/workbench/caption-import/row', self.payload(row))
            self.assertEqual(status, 500, result); self.empty_storage()
            with self.dataset.db: self.dataset.db.execute('DROP TRIGGER fail_caption')
        self.assertEqual(self.request('/api/workbench/caption-import/row', self.payload(row))[0], 201)

    def test_concurrent_duplicate_bytes_pixels_and_markers_do_not_modify_records(self):
        row = self.prepare()[0]
        for same_marker in (True, False):
            # Each iteration uses a distinct source image but races actual HTTP.
            row = self.prepare()[int(not same_marker)]
            first = self.payload(row); second = copy.deepcopy(first)
            if not same_marker: second['request_id'] = uuid.uuid4().hex
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda body: self.request('/api/workbench/caption-import/row', body), (first, second)))
            self.assertEqual(sorted(status for status, _ in responses), [201, 409], responses)
            before = self.dataset.workbench._all()
            self.assertEqual(self.request('/api/workbench/caption-import/row', self.payload(row))[0], 409)
            self.assertEqual(self.dataset.workbench._all(), before)

    def test_post_commit_receipt_failure_can_be_resolved_without_replay(self):
        body = self.payload(self.prepare()[0]); original = self.dataset.workbench.import_asset
        def commit_then_fail(*args, **kwargs):
            original(*args, **kwargs); raise OSError('lost receipt after committed source and target')
        with patch.object(self.dataset.workbench, 'import_asset', side_effect=commit_then_fail):
            self.assertEqual(self.request('/api/workbench/caption-import/row', body)[0], 500)
        self.assertEqual(self.count(), 1)
        status, result = self.request('/api/workbench/import-result/' + body['request_id'])
        self.assertEqual(status, 200); self.assertTrue(result['found'])
        record = self.dataset.workbench.get(result['record_id'])
        self.assertEqual(record['review'], 'draft'); self.assertEqual(self.dataset.workbench.history(record['id']), [record])
        self.assertEqual(self.request('/api/workbench/caption-import/row', body)[0], 409)

    def test_existing_related_split_conflicts_are_atomic_and_unchanged(self):
        row = self.prepare()[0]
        payload = self.dataset.caption_imports._open(row['token'])
        groups = payload['groups']; original_split = payload['context']['declared']['origin_record']['split']
        raw = io.BytesIO(); Image.new('RGB', (23, 17), 'yellow').save(raw, 'PNG')
        sample = self.dataset.add(dict(image=base64.b64encode(raw.getvalue()).decode(), filename='other.png',
            session_id=groups[0], book_id='', split=next(split for split in ('train','validation','test') if split != original_split)),
            enrollment=(groups, [], 'unknown'))
        before = self.dataset.workbench._all()
        self.assertEqual(self.request('/api/workbench/caption-import/row', self.payload(row))[0], 409)
        self.assertEqual(self.dataset.workbench._all(), before)
        self.assertEqual(len(list((self.dataset.path / 'images').iterdir())), 1)

    def test_new_source_partition_does_not_reassign_existing_unassigned_legacy_assets(self):
        row = self.prepare()[0]; payload = self.dataset.caption_imports._open(row['token'])
        groups = payload['groups']
        raw = io.BytesIO(); Image.new('RGB', (23, 17), 'yellow').save(raw, 'PNG')
        prior = self.dataset.add(dict(image=base64.b64encode(raw.getvalue()).decode(), filename='existing.png',
            session_id=groups[0], book_id='', split='unassigned'), enrollment=(groups, [], 'unknown'))
        before = self.dataset.workbench.get(prior['id']); source_before = self.dataset.sample(prior['id'])
        status, result = self.request('/api/workbench/caption-import/row', self.payload(row))
        self.assertEqual(status, 201, result)
        self.assertEqual(self.dataset.workbench.get(prior['id']), before)
        self.assertEqual(self.dataset.sample(prior['id']), source_before)
        current = self.dataset.workbench.get(result['record_id'])
        self.assertEqual(current['source_split'], payload['context']['declared']['origin_record']['split'])
        self.assertNotEqual(current['session_id'], before['session_id'])

    def test_native_export_with_unselected_text_ancestor_preserves_foreign_lineage(self):
        producer = Dataset(self.path / 'producer')
        try:
            ancestor = producer.workbench.import_asset(dict(kind='text', text='Authored source notes.',
                groups=['caption-source-notes'], rights='Authored'))
            rows = []
            for index, record in enumerate(self.manifest['records'][:3]):
                row = producer.workbench.import_asset(dict(kind='image',
                    image=base64.b64encode((FIXTURE / record['asset']).read_bytes()).decode(),
                    groups=['producer-image-' + str(index)], parents=[ancestor['id']] if index == 0 else []))
                rows.append(producer.workbench.save(row['id'], dict(revision=row['revision'],
                    source_revision=row['source_revision'], task='image_caption', annotation=record['annotation'],
                    groups=row['groups'], review='human_reviewed')))
            release = producer.releases.create(dict(format='image_caption_v1', seed=42,
                ratios={'train':34,'validation':33,'test':33},
                items=[{key:row[key] for key in ('id','revision','source_revision')} for row in rows]))
            with zipfile.ZipFile(producer.releases.locate(release['id'])) as archive:
                source = dict(manifest=archive.read('manifest.json').decode(), metadata={
                    split:archive.read(split+'/metadata.jsonl').decode() for split in ('train','val','test')})
                prepared = self.prepare(source)
                selected = next(item for item in prepared if item['asset'].endswith(rows[0]['id'] + '.png'))
                body = dict(token=selected['token'], asset=selected['asset'], request_id=uuid.uuid4().hex,
                            image=base64.b64encode(archive.read(selected['asset'])).decode())
            status, receipt = self.request('/api/workbench/caption-import/row', body)
            self.assertEqual(status,201,receipt)
            imported = self.dataset.workbench.get(receipt['record_id'])
            self.assertEqual(imported['parents'],[])
            declared = imported['provenance']['acquisition']['declared']['protected_component']
            self.assertIn(ancestor['id'], [member['id'] for member in declared])
            self.assertIn('caption-origin:' + hashlib.sha256(('id:'+ancestor['id']).encode()).hexdigest(), imported['groups'])
        finally: producer.close()

    def test_unselected_lineage_and_context_bounds_fail_before_admission(self):
        family_key = next(key for key, family in self.manifest['protected_components'].items() if len(family)>1)
        for case in ('unknown-deleted-lineage','too-many-origin-links','oversized-origin-context'):
            manifest=copy.deepcopy(self.manifest)
            if case=='unknown-deleted-lineage':
                next(member for member in manifest['protected_components'][family_key] if not member['source_available'])['source_lineage_known']=False
            elif case=='too-many-origin-links':
                manifest['protected_components'][family_key][0]['groups']=['origin-'+str(i) for i in range(30)]
            else: manifest['records'][0]['provenance']['declared_large_source_note']='x'*(256*1024)
            status,result=self.request('/api/workbench/caption-import/prepare',self.source_for(manifest))
            self.assertEqual(status,400,result); self.empty_storage()

    def assert_unenrolled_pixel_duplicate_rejected(self, later):
        origin=self.manifest['records'][0]
        original=(FIXTURE/origin['asset']).read_bytes()
        alternate=io.BytesIO(); info=PngImagePlugin.PngInfo(); info.add_text('fixture','different bytes, identical pixels')
        with Image.open(io.BytesIO(original)) as image: image.save(alternate,'PNG',pnginfo=info)
        alternate=alternate.getvalue()
        self.assertNotEqual(hashlib.sha256(original).digest(),hashlib.sha256(alternate).digest())
        if later:
            self.dataset.workbench.import_asset(dict(kind='text',text='Workbench already open.',groups=['initial-page']))
            self.dataset.workbench.query({})
        existing=self.dataset.add(dict(image=base64.b64encode(alternate).decode(),filename='corner-import.png',
            session_id='legacy-session',book_id='',split='unassigned'))
        # Inspect SQL directly; get/query/_all here would hide the regression.
        self.assertEqual(self.dataset.db.execute("SELECT count(*) FROM workbench_records WHERE kind='image'").fetchone()[0],0)
        table_snapshot=lambda: {table:[tuple(row) for row in self.dataset.db.execute('SELECT * FROM '+table)]
            for table in ('samples','workbench_records','workbench_history','workbench_deleted_sources')}
        before=table_snapshot()
        files_before={str(path.relative_to(self.dataset.path)):path.read_bytes()
            for path in (self.dataset.path/'images').rglob('*') if path.is_file()}
        row=next(row for row in self.prepare() if row['asset']==origin['asset'])
        self.assertEqual(table_snapshot(),before,'Preparation must not enroll the legacy source')
        body=self.payload(row)
        status,result=self.request('/api/workbench/caption-import/row',body)
        self.assertEqual(status,409,result)
        self.assertIn('exact image pixels',result['error'])
        self.assertEqual(table_snapshot(),before,'Duplicate rejection rolls lazy enrollment/history back')
        self.assertEqual({str(path.relative_to(self.dataset.path)):path.read_bytes()
            for path in (self.dataset.path/'images').rglob('*') if path.is_file()},files_before)
        self.assertEqual(self.request('/api/workbench/import-result/'+body['request_id']), (200,{'found':False}))
        self.assertEqual(self.dataset.sample(existing['id']),existing)

    def test_unenrolled_legacy_reencoding_cannot_bypass_pixel_duplicate_admission(self):
        self.assert_unenrolled_pixel_duplicate_rejected(False)

    def test_later_corner_import_after_workbench_open_cannot_bypass_pixel_duplicate_admission(self):
        self.assert_unenrolled_pixel_duplicate_rejected(True)

    def test_failed_caption_history_rolls_back_lazy_enrollment_and_new_source_files(self):
        raw=io.BytesIO(); Image.new('RGB',(23,17),'yellow').save(raw,'PNG')
        prior=self.dataset.add(dict(image=base64.b64encode(raw.getvalue()).decode(),filename='older.png',
            session_id='older-unenrolled',book_id='',split='unassigned'))
        self.assertEqual(self.count(),0)
        files_before={str(path.relative_to(self.dataset.path)):path.read_bytes()
            for path in (self.dataset.path/'images').rglob('*') if path.is_file()}
        row=self.prepare()[0]
        with self.dataset.db:
            self.dataset.db.execute("CREATE TRIGGER fail_final_caption BEFORE INSERT ON workbench_history WHEN json_extract(NEW.snapshot,'$.task')='image_caption' BEGIN SELECT RAISE(ABORT,'caption history failed'); END")
        body=self.payload(row)
        status,result=self.request('/api/workbench/caption-import/row',body)
        self.assertEqual(status,500,result)
        self.assertEqual(self.count(),0)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workbench_history').fetchone()[0],0)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM samples').fetchone()[0],1)
        self.assertEqual(self.dataset.sample(prior['id']),prior)
        self.assertEqual({str(path.relative_to(self.dataset.path)):path.read_bytes()
            for path in (self.dataset.path/'images').rglob('*') if path.is_file()},files_before)
        self.assertEqual(self.request('/api/workbench/import-result/'+body['request_id']), (200,{'found':False}))
        with self.dataset.db: self.dataset.db.execute('DROP TRIGGER fail_final_caption')
        self.assertEqual(self.request('/api/workbench/caption-import/row',body)[0],201)

    def test_split_rejection_rolls_back_lazy_enrollment_without_pending_or_durable_writes(self):
        row=self.prepare()[0]; payload=self.dataset.caption_imports._open(row['token'])
        groups=payload['groups']; split=payload['context']['declared']['origin_record']['split']
        def picture(color):
            buffer=io.BytesIO(); Image.new('RGB',(23,17),color).save(buffer,'PNG')
            return base64.b64encode(buffer.getvalue()).decode()
        prior=self.dataset.add(dict(image=picture('yellow'),filename='related.png',session_id=groups[0],
            book_id='',split=next(value for value in ('train','validation','test') if value!=split)),
            enrollment=(groups,[],'unknown'))
        legacy=self.dataset.add(dict(image=picture('purple'),filename='unenrolled.png',session_id='unrelated-unenrolled',
            book_id='',split='unassigned'))
        tables=('samples','workbench_records','workbench_history','workbench_deleted_sources')
        def snapshot(connection):
            return {table:[tuple(record) for record in connection.execute('SELECT * FROM '+table)] for table in tables}
        before=snapshot(self.dataset.db)
        self.assertFalse(self.dataset.db.in_transaction)
        self.assertEqual(len(before['workbench_records']),1)
        files_before={str(path.relative_to(self.dataset.path)):path.read_bytes()
            for path in (self.dataset.path/'images').rglob('*') if path.is_file()}
        with sqlite3.connect(self.dataset.path/'dataset.sqlite3') as reader:
            self.assertEqual(snapshot(reader),before)
            body=self.payload(row)
            status,result=self.request('/api/workbench/caption-import/row',body)
            self.assertEqual(status,409,result)
            self.assertIn('conflicting source split',result['error'])
            self.assertFalse(self.dataset.db.in_transaction,'A rejection must leave no pending lazy-enrollment transaction')
            self.assertEqual(snapshot(self.dataset.db),before)
            self.assertEqual(snapshot(reader),before,'Durable source/record/history state is unchanged')
            self.assertEqual({str(path.relative_to(self.dataset.path)):path.read_bytes()
                for path in (self.dataset.path/'images').rglob('*') if path.is_file()},files_before)
            self.assertEqual(self.request('/api/workbench/import-result/'+body['request_id']), (200,{'found':False}))
            self.assertEqual(self.dataset.sample(prior['id']),prior)
            self.assertEqual(self.dataset.sample(legacy['id']),legacy)
            # Ordinary browsing can later enroll that retained original in its
            # own transaction; it does not commit leftovers from the rejection.
            self.dataset.workbench.query({})
            self.assertFalse(self.dataset.db.in_transaction)
            self.assertEqual(len(snapshot(reader)['workbench_records']),2)
            self.assertEqual(len(snapshot(reader)['workbench_history']),2)


if __name__ == '__main__': unittest.main()
