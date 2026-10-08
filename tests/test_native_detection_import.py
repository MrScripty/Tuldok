"""Actual unchanged native exporter fixtures; no authored COCO stand-in."""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import struct
import zlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from unittest.mock import patch
import zipfile

from PIL import Image
from app import Dataset, make_handler
from native_detection_import import foreign_groups
from workbench import encode
from test_native_text_import import rewrite


def native_fixture(path, count=3, name_prefix='Source', book='', programmatic=False, ratios=None):
    source = Dataset(path)
    rows = []
    salt = hashlib.sha256(name_prefix.encode()).digest()
    for number in range(count):
        image = Image.new('RGB', (12, 8), ((salt[0] + number * 40) % 256, salt[1], salt[2]))
        output = io.BytesIO(); exif = Image.Exif(); exif[274] = 6
        image.save(output, 'PNG', exif=exif)
        sample = source.add(dict(image=base64.b64encode(output.getvalue()).decode(), filename=f'{name_prefix} {number}.png',
            book_id=book, session_id=f'{name_prefix}-session-{number}', split='unassigned'))
        row = source.workbench.get(sample['id'])
        target = {'boxes': [] if number == 0 else [dict(label='Book é', x=1, y=2, width=3.5, height=4)]}
        review = 'programmatically_verified' if programmatic else 'human_reviewed'
        verification = dict(method='authored_geometry_fixture', rights='Authored fixture') if programmatic else None
        rows.append(source.workbench.save(row['id'], dict(row, annotation=target, review=review), verified_provenance=verification))
    body = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
        ratios=ratios or dict(train=100, validation=0, test=0), seed=7, format='canonical_v1')
    preview = source.releases.preview(body)
    assert preview['eligible'], preview
    release = source.releases.create(dict(body, preview_token=preview['preview_token']))
    raw = source.releases.locate(release['id']).read_bytes()
    source.close()
    return raw


class NativeDetectionImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.raw = native_fixture(self.path/'source')
        self.dataset = Dataset(self.path/'destination'); self.open_server(); self.addCleanup(self.close)

    def open_server(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.root = f'http://127.0.0.1:{self.server.server_port}/api/workbench/'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.dataset.close()

    def request(self, route, body=None):
        req = urllib.request.Request(self.root+route, data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def prepare(self, raw=None, expected=200):
        status, value = self.request('native-detection-import/prepare',
            dict(source_name='detection.zip', archive=base64.b64encode(self.raw if raw is None else raw).decode()))
        self.assertEqual(status, expected, value)
        return value

    def admit(self, row, expected=201, marker=None):
        body = dict(token=row['token'], request_id=marker or uuid.uuid4().hex)
        status, value = self.request('native-detection-import/row', body)
        self.assertEqual(status, expected, value)
        return body, value

    def origins(self):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            return json.loads(archive.read('manifest.json'))['records']

    def snapshot(self):
        return list(self.dataset.db.iterdump()), sorted(str(p.relative_to(self.dataset.path)) for p in (self.dataset.path/'images').rglob('*'))

    def selection(self, rows):
        return dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
            ratios=dict(train=100, validation=0, test=0), seed=7, format='canonical_v1')

    def test_actual_export_roundtrip_review_history_restart_and_immutable_release(self):
        before = self.snapshot(); prepared = self.prepare(); self.assertEqual(before, self.snapshot())
        admitted = [self.admit(row) for row in prepared['rows']]
        rows = [self.dataset.workbench.get(receipt['record_id']) for _, receipt in admitted]
        self.assertTrue(any(row['annotation'] == {'boxes': []} for row in rows))
        for row, origin, prepared_row in zip(rows, self.origins(), prepared['rows']):
            self.assertNotEqual(row['id'], origin['id'])
            self.assertEqual((row['revision'], row['source_revision'], row['review'], row['task']), (1, 1, 'draft', 'image_detection'))
            self.assertEqual(row['annotation'], origin['annotation'])
            self.assertEqual((row['width'], row['height']), (8, 12))
            self.assertEqual(row['source_split'], origin['split'])
            self.assertEqual(row['parents'], [])
            self.assertEqual(row['groups'], foreign_groups(origin))
            self.assertEqual(row['provenance']['rights'], 'unknown')
            context = row['provenance']['acquisition']
            self.assertEqual(context['input_sha256'], row['source_sha256'])
            self.assertNotEqual(row['source_sha256'], origin['source_sha256'], 'EXIF originals were omitted by exporter')
            self.assertEqual(context['row_hash_basis'], 'canonical_parsed_manifest_record')
            self.assertEqual(context['row_sha256'], hashlib.sha256(encode(origin).encode()).hexdigest())
            self.assertEqual(context['row_sha256'], prepared_row['row_sha256'])
            self.assertEqual(context['declared']['upstream'], dict(record=origin, original_status='unavailable'))
            self.assertEqual(self.dataset.workbench.history(row['id']), [row])
        self.assertFalse(self.dataset.releases.preview(self.selection(rows))['eligible'])
        self.close(); self.dataset = Dataset(self.path/'destination'); self.open_server()
        for body, receipt in admitted:
            self.assertEqual(self.request('import-result/'+body['request_id']), (200, dict(found=True, **receipt)))
        self.admit(prepared['rows'][0], expected=400)  # Restart expires all preparation.
        reviewed = [self.dataset.workbench.save(row['id'], dict(row, review='human_reviewed')) for row in rows]
        body = self.selection(reviewed); preview = self.dataset.releases.preview(body)
        self.assertTrue(preview['eligible'], preview)
        release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        frozen = self.dataset.releases.locate(release['id']).read_bytes()
        with zipfile.ZipFile(io.BytesIO(frozen)) as archive:
            exported = json.loads(archive.read('manifest.json'))['records']
            for row in exported:
                self.assertEqual(archive.read(row['asset']), (self.dataset.path/'images'/row['id']/'source').read_bytes())
                self.assertEqual(row['annotation'], next(r['annotation'] for r in rows if r['id'] == row['id']))
        self.dataset.workbench.save(reviewed[0]['id'], dict(reviewed[0], annotation={'boxes': []}, review='draft'))
        self.assertFalse(self.dataset.releases.preview(body)['eligible'])
        self.assertEqual(self.dataset.releases.locate(release['id']).read_bytes(), frozen)

    def test_invalid_png_chunk_returns_400_without_mutation(self):
        """Real Pillow SyntaxError during decode, with valid archive/content hashes."""
        def damage(entries):
            manifest = json.loads(entries['manifest.json'])
            row = manifest['records'][0]
            raw = entries[row['asset']]
            offset = 8  # PNG signature; keep IHDR and all metadata intact.
            while raw[offset + 4:offset + 8] != b'IDAT':
                offset += 12 + struct.unpack('>I', raw[offset:offset + 4])[0]
            length = struct.unpack('>I', raw[offset:offset + 4])[0]
            payload = raw[offset + 8:offset + 8 + length]
            def chunk(name, data):
                return (struct.pack('>I', len(data)) + name + data
                        + struct.pack('>I', zlib.crc32(name + data) & 0xffffffff))
            # A valid partial IDAT forces the decoder to read the illegal chunk ID.
            broken = (raw[:offset] + chunk(b'IDAT', payload[:1]) + chunk(b'bad!', b'')
                      + chunk(b'IDAT', payload[1:]) + raw[offset + length + 12:])
            with Image.open(io.BytesIO(broken)) as image:
                self.assertEqual((image.format, image.mode, image.size), ('PNG', 'RGB', (8, 12)))
                with self.assertRaisesRegex(SyntaxError, 'broken PNG file'):
                    image.load()
            row['content_hash'] = row['asset_sha256'] = hashlib.sha256(broken).hexdigest()
            entries[row['asset']] = broken
            entries['manifest.json'] = encode(manifest).encode()
        before = self.snapshot()
        value = self.prepare(rewrite(self.raw, damage), expected=400)
        self.assertEqual(value['error'], 'Native image is damaged or exceeds the geometry bound.')
        self.assertEqual(before, self.snapshot())
        # A failed preparation does not poison the following request.
        self.prepare()

    def test_malformed_bundles_are_read_only_and_typed(self):
        before = self.snapshot()
        def manifest_change(fn):
            def change(entries):
                manifest = json.loads(entries['manifest.json']); fn(manifest)
                entries['manifest.json'] = json.dumps(manifest).encode()
            return change
        def coco_change(fn):
            def change(entries):
                coco = json.loads(entries['train/coco.json']); fn(coco)
                entries['train/coco.json'] = json.dumps(coco).encode()
            return change
        mutations = [
            manifest_change(lambda m: m.update(schema_version=True)),
            manifest_change(lambda m: m.update(coordinate_contract='unoriented xyxy')),
            manifest_change(lambda m: m['split_report']['requested_percentages'].update(train=100.0)),
            manifest_change(lambda m: m['records'][0].update(asset_sha256='0'*64)),
            manifest_change(lambda m: m['records'][0].update(pixel_hash='0'*64)),
            manifest_change(lambda m: m['records'][0].update(width=True)),
            manifest_change(lambda m: m['records'][0].update(task='image_classification')),
            manifest_change(lambda m: m['records'][0].update(asset='../source.png')),
            manifest_change(lambda m: m['records'][0]['provenance'].update(invalid=float('inf'))),
            manifest_change(lambda m: m['records'][0]['provenance'].update(invalid=float('nan'))),
            manifest_change(lambda m: m['records'][0]['provenance'].update(invalid='\ud800')),
            manifest_change(lambda m: m['records'][0].update(annotation={'boxes':[dict(label='X',x=0,y=0,width=12,height=8)]})),
            manifest_change(lambda m: m['records'][0].update(groups=[f'group-{i}' for i in range(30)])),
            coco_change(lambda c: c['images'][0].update(id=True)),
            coco_change(lambda c: c['annotations'][0].update(iscrowd=False)),
            coco_change(lambda c: c['annotations'][0].update(image_id=99)),
            coco_change(lambda c: c['annotations'][0].update(bbox=[2,1,4,3.5])),
            lambda e: e.update({'train/records.jsonl': b'{}\n'}),
            lambda e: e.update({'manifest.json': b'{"schema_version":1,"schema_version":1}'}),
            lambda e: e.update({'manifest.json': b'['*1200+b']'*1200}),
            lambda e: e.update({'manifest.json': b'\xff'}),
            lambda e: e.pop('test/coco.json'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.prepare(rewrite(self.raw, mutate), expected=400)
                self.assertEqual(before, self.snapshot())
        self.prepare(self.raw[:80], expected=400)

    def test_retained_group_parent_and_book_split_conflicts_precede_admission(self):
        before = self.snapshot()
        for relation in ('group', 'parent', 'book', 'generated_id_alias', 'generated_book_alias'):
            def change(entries):
                manifest = json.loads(entries['manifest.json']); first, second = manifest['records'][:2]
                if relation == 'group': second['groups'] = first['groups']
                elif relation == 'parent': second['parents'] = [first['id']]
                elif relation == 'book': first['book_id'] = second['book_id'] = 'shared-book'
                elif relation == 'generated_id_alias': second['groups'] = ['native-text-origin:'+hashlib.sha256(first['id'].encode()).hexdigest()]
                else:
                    first['book_id'] = 'shared-book'
                    second['groups'] = ['native-image-origin:'+hashlib.sha256(b'book:shared-book').hexdigest()]
                second['split'] = 'validation'
                manifest['split_report']['actual_counts'] = {'train':2, 'validation':1}
                entries['manifest.json'] = encode(manifest).encode()
            error = self.prepare(rewrite(self.raw, change), expected=400)
            self.assertIn('family links conflict', error['error'])
            self.assertEqual(before, self.snapshot())

    def test_normalized_png_orientation_and_mode_checked_before_admission(self):
        before = self.snapshot()
        for mode, orientation in [('RGBA', 1), ('RGB', 6)]:
            def change(entries):
                manifest = json.loads(entries['manifest.json']); row = manifest['records'][0]
                image = Image.new(mode, (row['width'], row['height']), 'red')
                buffer = io.BytesIO(); exif = Image.Exif(); exif[274] = orientation
                image.save(buffer, 'PNG', exif=exif)
                entries[row['asset']] = buffer.getvalue()
                row['asset_sha256'] = row['content_hash'] = hashlib.sha256(buffer.getvalue()).hexdigest()
                entries['manifest.json'] = encode(manifest).encode()
            error = self.prepare(rewrite(self.raw, change), expected=400)
            self.assertIn('normalized RGB PNGs', error['error'])
            self.assertEqual(before, self.snapshot())

    def test_pixel_duplicate_marker_and_storage_failure_never_overwrite(self):
        rows = self.prepare()['rows']; body, receipt = self.admit(rows[0]); before = self.snapshot()
        self.admit(rows[0], expected=409); self.admit(rows[1], expected=409, marker=body['request_id'])
        self.assertEqual(before, self.snapshot())
        marker = uuid.uuid4().hex
        with patch.object(self.dataset.workbench, '_history', side_effect=sqlite3.OperationalError('Injected history failure')):
            self.admit(rows[1], expected=500, marker=marker)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.request('import-result/'+marker), (200, {'found':False}))
        self.admit(rows[1]); self.assertEqual(len(self.dataset.workbench.query({})['items']), 2)
        saved = self.dataset.workbench.get(receipt['record_id'])
        self.assertEqual(saved['revision'], 1); self.assertEqual(saved['review'], 'draft')

    def test_prepared_tampering_and_bounded_aggregate_fail_closed(self):
        rows = self.prepare()['rows']; before = self.snapshot()
        self.admit(dict(rows[0], token=rows[0]['token'][:-1]+'x'), expected=400)
        with patch('native_detection_import.MAX_PREPARED', 1):
            self.prepare(expected=400)
        with patch('native_detection_import.MAX_RECORDS', 2):
            self.prepare(expected=400)
        self.assertEqual(before, self.snapshot())

    def test_related_existing_source_split_rejects_without_lazy_enrollment_or_propagation(self):
        origin = self.origins()[0]
        image = Image.new('RGB', (4,4), 'yellow'); data = io.BytesIO(); image.save(data, 'PNG')
        existing = self.dataset.workbench.import_asset(dict(kind='image', image=base64.b64encode(data.getvalue()).decode(),
            groups=[origin['groups'][0]], rights='Owned'))
        self.dataset.db.execute("UPDATE samples SET split='validation' WHERE id=?", (existing['id'],)); self.dataset.db.commit()
        before = self.snapshot(); self.admit(self.prepare()['rows'][0], expected=409); self.assertEqual(before, self.snapshot())
        self.dataset.delete(existing['id'], {'revision':1})
        before = self.snapshot(); self.admit(self.prepare()['rows'][0], expected=409); self.assertEqual(before, self.snapshot())

    def test_declared_parent_links_join_native_text_and_book_dominates_sessions(self):
        origin = self.origins()[0]
        from native_text_import import digest
        text = self.dataset.workbench.import_asset(dict(kind='text', text='Foreign family bridge.', groups=['native-text-origin:'+digest(origin['id'].encode())], rights='unknown'))
        _, receipt = self.admit(self.prepare()['rows'][0])
        from dataset_releases import connected_components
        universe = self.dataset.workbench._all(); roots = connected_components(universe)
        self.assertEqual(roots[text['id']], roots[receipt['record_id']])
        raw = native_fixture(self.path/'book-source', name_prefix='Book sources', book='same-book')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            records = json.loads(archive.read('manifest.json'))['records']
        groups = [foreign_groups(row) for row in records]
        shared = set.intersection(*(set(group) for group in groups))
        self.assertTrue(any(group.startswith('native-image-origin:') for group in shared))
        self.assertEqual(len({row['session_id'] for row in records}), 3)

    def test_matching_unassigned_family_keeps_existing_source_and_exact_record(self):
        origin = self.origins()[0]
        image = Image.new('RGB', (4,4), 'green'); data = io.BytesIO(); image.save(data, 'PNG')
        existing = self.dataset.workbench.import_asset(dict(kind='image', image=base64.b64encode(data.getvalue()).decode(),
            groups=[origin['groups'][0]], rights='Existing permission'))
        existing_source = tuple(self.dataset.db.execute('SELECT * FROM samples WHERE id=?', (existing['id'],)).fetchone())
        _, receipt = self.admit(self.prepare()['rows'][0])
        self.assertEqual(self.dataset.workbench.get(existing['id']), existing)
        self.assertEqual(tuple(self.dataset.db.execute('SELECT * FROM samples WHERE id=?', (existing['id'],)).fetchone()), existing_source)
        self.assertEqual(self.dataset.workbench.get(receipt['record_id'])['source_split'], 'train')

    def test_initial_detection_geometry_is_rechecked_by_atomic_owner(self):
        before = self.snapshot()
        image = Image.new('RGB', (4,4), 'pink'); data = io.BytesIO(); image.save(data, 'PNG')
        from workbench import WorkbenchError
        with self.assertRaises(WorkbenchError):
            self.dataset.workbench.import_asset(dict(kind='image', image=base64.b64encode(data.getvalue()).decode(),
                groups=['initial-owner'], rights='unknown'), annotation_task='image_detection',
                annotation={'boxes':[dict(label='invalid',x=0,y=0,width=5,height=1)]})
        self.assertEqual(before, self.snapshot())

    def test_actual_programmatic_export_is_accepted_as_draft_invented_enum_rejected(self):
        raw = native_fixture(self.path/'verified-source', name_prefix='Verified', programmatic=True)
        prepared = self.prepare(raw)
        _, receipt = self.admit(prepared['rows'][0])
        row = self.dataset.workbench.get(receipt['record_id'])
        self.assertEqual(row['review'], 'draft')
        self.assertEqual(row['provenance']['acquisition']['declared']['upstream']['record']['review'], 'programmatically_verified')
        def change(entries):
            manifest = json.loads(entries['manifest.json']); manifest['records'][0]['review'] = 'verified'
            entries['manifest.json'] = encode(manifest).encode()
        self.prepare(rewrite(raw, change), expected=400)

    def test_outer_requests_require_strict_utf8_unique_finite_bounded_json(self):
        before = self.snapshot()
        for route in ('native-detection-import/prepare', 'native-detection-import/row'):
            for raw in (b'{"source_name":"a","source_name":"b"}', b'{"archive":1e999}',
                    b'{"archive":NaN}', b'{"archive":"\\ud800"}', b'['*1200+b']'*1200,
                    '{}'.encode('utf-16'), b'\xff'):
                req = urllib.request.Request(self.root+route, data=raw, headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req)
                self.assertEqual(caught.exception.code, 400)
                self.assertEqual(before, self.snapshot())

    def test_actual_three_partition_export_global_indices_negatives_and_reexport(self):
        ratios = dict(train=34, validation=33, test=33)
        raw = native_fixture(self.path/'three-splits', name_prefix='Three partitions', ratios=ratios)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            origin = json.loads(archive.read('manifest.json'))['records']
            self.assertEqual({row['split'] for row in origin}, set(ratios))
            image_ids = []
            for split in ratios:
                coco = json.loads(archive.read(split+'/coco.json'))
                self.assertEqual(len(coco['images']), 1)
                image = coco['images'][0]; image_ids.append(image['id'])
                record = next(row for row in origin if row['asset'] == image['file_name'])
                self.assertEqual(image['id'], origin.index(record)+1)
                self.assertEqual(len(coco['annotations']), len(record['annotation']['boxes']))
                for annotation in coco['annotations']:
                    self.assertEqual(annotation['id'], 1)
                    self.assertEqual(annotation['image_id'], image['id'])
            self.assertEqual(set(image_ids), {1,2,3})
        rows = []
        for prepared, upstream in zip(self.prepare(raw)['rows'], origin):
            _, receipt = self.admit(prepared)
            row = self.dataset.workbench.get(receipt['record_id'])
            self.assertEqual(row['source_split'], upstream['split'])
            self.assertEqual(row['annotation'], upstream['annotation'])
            rows.append(self.dataset.workbench.save(row['id'], dict(row, review='human_reviewed')))
        body = dict(self.selection(rows), ratios=ratios)
        preview = self.dataset.releases.preview(body); self.assertTrue(preview['eligible'], preview)
        release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        exported = self.dataset.releases.locate(release['id']).read_bytes()
        reparsed = self.prepare(exported)
        self.assertEqual(len(reparsed['rows']), 3)
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['split_report']['actual_counts'], dict(train=1, validation=1, test=1))
            self.assertTrue(any(not row['annotation']['boxes'] for row in manifest['records']))


if __name__ == '__main__':
    unittest.main()
