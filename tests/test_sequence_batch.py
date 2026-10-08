"""Actual frozen fee7b4a pair + explicitly source-derived synthetic controls."""
import base64
import hashlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import uuid
import zipfile

from app import Dataset, make_handler
import bulk_import
from dataset_releases import allocate, connected_components
from fixtures.rheon_source_derived import synthetic_frames, synthetic_manifest
import sequence_batch_import as batch
from workbench import WorkbenchError

ACTUAL = Path(__file__).parent / 'fixtures/rheon_actual_fee7b4a'


def synthetic(mutator=None, manifest_mutator=None):
    frames = synthetic_frames()
    if mutator:
        mutator(frames)
    raw = b''.join(json.dumps(row, separators=(',', ':')).encode() + b'\n' for row in frames)
    manifest = synthetic_manifest(raw)
    if manifest_mutator:
        manifest_mutator(manifest)
    return json.dumps(manifest).encode(), raw


def body(run=None, frames=None, **changes):
    if run is None:
        run, frames = (ACTUAL / 'run.json').read_bytes(), (ACTUAL / 'frames.jsonl').read_bytes()
    value = dict(files={'run.json': base64.b64encode(run).decode(), 'frames.jsonl': base64.b64encode(frames).decode()},
                 request_id=uuid.uuid4().hex, batch_name='selected-corpus', item_name='actual-fee7b4a', item_index=1)
    value.update(changes)
    return value


class SequenceBatch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.d = Dataset(self.temp.name)
        self.addCleanup(lambda: self.d.close())
        self.w = self.d.workbench

    def snapshot(self):
        return {table: [tuple(row) for row in self.d.db.execute('SELECT * FROM ' + table)]
                for table in ('workbench_sequence_assets', 'workbench_records', 'workbench_history', 'workbench_rights_notes')}

    def review(self, row):
        return self.w.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
            task='sequence_transport', annotation={'note': 'Human inspected native fields and transport limitations.'},
            groups=row['groups'], review='human_reviewed'))

    def test_actual_bytes_admission_receipt_reopen_and_no_blob_lookup(self):
        request = body()
        result = batch.import_item(self.w, request)
        row = self.w.get(result['record_id'])
        self.assertEqual((row['kind'], row['review'], row['annotation']), ('sequence', 'draft', None))
        self.assertEqual(row['provenance']['rights'], 'unknown')
        self.assertNotIn('acquisition', row['provenance'])
        self.assertEqual(row['sequence']['adapter']['contract_commit'], 'fee7b4a139574f87b259796b1ba8698a41d31ac1')
        self.assertEqual(len(row['sequence']['frame_index']), 9)
        self.assertEqual(row['sequence']['manifest']['geometry']['field_shapes']['velocity_x'], [17, 8, 4])
        raw, _ = self.w.asset(row['id'])
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            self.assertEqual(bundle.namelist(), ['run.json', 'frames.jsonl'])
            for name in bundle.namelist():
                self.assertEqual(bundle.read(name), (ACTUAL / name).read_bytes())
        for name, key in [('run.json', 'run_sha256'), ('frames.jsonl', 'frames_sha256')]:
            self.assertEqual(result[key], hashlib.sha256((ACTUAL / name).read_bytes()).hexdigest())
        statements = []
        self.d.db.set_trace_callback(statements.append)
        self.assertEqual(batch.find_result(self.w, request['request_id']), dict(found=True, **result))
        self.d.db.set_trace_callback(None)
        self.assertFalse(any('SELECT bundle' in sql for sql in statements))
        self.assertNotIn('sequence', result)
        self.assertNotIn('review', result)
        self.d.close(); self.d = Dataset(self.temp.name); self.w = self.d.workbench
        self.assertEqual(batch.find_result(self.w, request['request_id']), dict(found=True, **result))
        self.assertEqual(self.w.asset(row['id'])[0], raw)

    def test_repeat_marker_and_reviewed_bundle_never_update_existing(self):
        request = body()
        result = batch.import_item(self.w, request)
        row = self.review(self.w.get(result['record_id']))
        before = self.snapshot()
        for repeated in (request, body(), body(*synthetic(), request_id=request['request_id'])):
            with self.assertRaises(WorkbenchError) as error:
                batch.import_item(self.w, repeated)
            self.assertEqual(error.exception.status, 409)
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.w.get(row['id']), row)
        self.assertEqual(batch.find_result(self.w, request['request_id']), dict(found=True, **result))

    def test_marker_race_and_raw_namespace_are_distinct(self):
        marker = uuid.uuid4().hex
        raw_body = dict(source_name='raw.jsonl', row_number=1, request_id=marker,
                        line=json.dumps(dict(kind='text', text='Raw namespace sample.', groups=['raw-source'])))
        raw_result = bulk_import.import_row(self.w, raw_body)
        self.assertEqual(batch.find_result(self.w, marker), {'found': False})
        barrier = threading.Barrier(2)
        outcomes = []
        original = batch.rheon.prepare
        def prepared(*args):
            value = original(*args); barrier.wait(timeout=5); return value
        def worker(request):
            try: outcomes.append(batch.import_item(self.w, request))
            except WorkbenchError as error: outcomes.append(error.status)
        with patch.object(batch.rheon, 'prepare', side_effect=prepared):
            workers = [threading.Thread(target=worker, args=(request,)) for request in
                       (body(request_id=marker), body(*synthetic(), request_id=marker, item_name='source-derived'))]
            for worker_thread in workers: worker_thread.start()
            for worker_thread in workers: worker_thread.join(8); self.assertFalse(worker_thread.is_alive())
        self.assertEqual(len([value for value in outcomes if isinstance(value, dict)]), 1)
        self.assertIn(409, outcomes)
        self.assertTrue(batch.find_result(self.w, marker)['found'])
        self.assertEqual(bulk_import.find_result(self.w, marker), dict(found=True, **raw_result))
        self.assertEqual(self.w.query({'kind': 'sequence'})['total'], 1)

    def test_asset_record_history_failures_rollback_marker_and_keep_prior_items(self):
        prior = batch.import_item(self.w, body())
        before = self.snapshot()
        for table in ('workbench_sequence_assets', 'workbench_records', 'workbench_history'):
            request = body(*synthetic(), item_index=2, item_name='synthetic')
            self.d.db.execute(f"CREATE TRIGGER fail_batch BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected batch failure'); END")
            self.d.db.commit()
            try:
                with self.assertRaises(WorkbenchError) as error: batch.import_item(self.w, request)
                self.assertEqual(error.exception.status, 500)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(batch.find_result(self.w, request['request_id']), {'found': False})
            finally:
                self.d.db.execute('DROP TRIGGER fail_batch'); self.d.db.commit()
        with patch.object(batch.rheon, 'prepare', side_effect=OSError('injected storage failure')):
            with self.assertRaises(WorkbenchError) as error: batch.import_item(self.w, body())
            self.assertEqual(error.exception.status, 500)
        self.assertEqual(self.w.get(prior['record_id'])['review'], 'draft')

    def test_malformed_producer_pairs_are_atomic_and_newer_contract_is_not_accepted(self):
        before = self.snapshot()
        cases = [synthetic(manifest_mutator=lambda m: m.__setitem__('frames_sha256', '0' * 64)),
                 synthetic(mutator=lambda f: f[2]['fields']['velocity_x'].pop()),
                 synthetic(mutator=lambda f: f[2]['carrier_stamp'].__setitem__('version', '9')),
                 synthetic(mutator=lambda f: f[2]['fields']['pressure'].__setitem__(0, float('nan'))),
                 synthetic(manifest_mutator=lambda m: m['geometry']['axis_order'].__setitem__(0, 'z')),
                 synthetic(manifest_mutator=lambda m: m['provenance']['build_command'].append('--message-format=json-render-diagnostics'))]
        run, frames = synthetic(); cases.append((run, frames[:-10]))
        short = b'\n'.join(frames.splitlines()[:-1]) + b'\n'
        # Hash-valid truncation must still fail frame-count/completion validation.
        cases.append((json.dumps(synthetic_manifest(short)).encode(), short))
        for pair in cases:
            with self.subTest(run=hashlib.sha256(pair[0]).hexdigest()):
                with self.assertRaises(WorkbenchError): batch.import_item(self.w, body(*pair))
                self.assertEqual(self.snapshot(), before)

    def test_envelope_bounds_forgery_parent_and_lookup_ambiguity(self):
        before = self.snapshot()
        for change in [dict(item_index=True), dict(item_index=33), dict(item_index=0), dict(batch_name='../path'),
                       dict(item_name=' space'), dict(item_name='\ud800'), dict(request_id='fake'),
                       dict(review='human_reviewed'), dict(provenance={}), dict(run_sha256='f' * 64),
                       dict(parents=['0' * 32]), dict(files={}), dict(rights='x' * 1001)]:
            with self.subTest(change=repr(change)), self.assertRaises(WorkbenchError):
                batch.import_item(self.w, body(**change))
            self.assertEqual(self.snapshot(), before)
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff', b'{' , b'[' * 1500]:
            with self.assertRaises(WorkbenchError): batch.parse_request(raw)
        request = body(); result = batch.import_item(self.w, request)
        second = batch.import_item(self.w, body(*synthetic(), item_name='synthetic'))
        context = self.w.get(result['record_id'])['provenance']
        self.d.db.execute('UPDATE workbench_records SET provenance_json=? WHERE id=?', (json.dumps(context), second['record_id']))
        self.d.db.commit()
        with self.assertRaises(WorkbenchError) as error: batch.find_result(self.w, request['request_id'])
        self.assertEqual(error.exception.status, 409)

    def test_whole_family_human_review_saved_fixed_set_and_raw_release(self):
        results = [batch.import_item(self.w, body()), batch.import_item(self.w, body(*synthetic(), item_index=2, item_name='source-derived'))]
        rows = [self.w.get(result['record_id']) for result in results]
        components = connected_components(self.w._all())
        self.assertEqual(components[rows[0]['id']], components[rows[1]['id']])
        self.assertNotIn('selected-corpus', rows[0]['groups'])
        pairs = lambda: [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows]
        saved = self.d.selections.create(dict(name='Imported trajectories', items=pairs()))
        self.assertTrue(self.d.selections.load(saved['id'])['current'])
        export = dict(items=pairs(), ratios=dict(train=100, validation=0, test=0), seed=42)
        self.assertFalse(self.d.releases.preview(export)['eligible'])
        rows = [self.review(row) for row in rows]
        self.assertFalse(self.d.selections.load(saved['id'])['current'])
        with self.assertRaises(WorkbenchError): allocate(rows, self.w._all(), dict(train=50, validation=50, test=0), 42)
        export['items'] = pairs(); preview = self.d.releases.preview(export)
        release = self.d.releases.create(dict(export, preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest['records']), 2)
            for entry in manifest['records']:
                self.assertEqual(archive.read(entry['asset']), self.w.asset(entry['id'])[0])
                self.assertEqual(len(entry['sequence']['frame_index']), 9)

    def test_http_strict_envelope_limits_storage_failure_and_lookup(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.d))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(lambda: thread.join(3)); self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port) + '/api/workbench/'
        def request(route, raw=None):
            value = urllib.request.Request(base + route, raw, headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(value, timeout=5) as response: return response.status, json.load(response)
            except urllib.error.HTTPError as response: return response.code, json.load(response)
        for raw in [b'{"request_id":"a","request_id":"b"}', b'{"item_index":Infinity}', b'\xff', b'[' * 1500]:
            self.assertEqual(request('sequence-import-item', raw)[0], 400)
        # The size gate rejects headers before reading any oversized request body.
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        connection.putrequest('POST', '/api/workbench/sequence-import-item')
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('Content-Length', str(batch.rheon.MAX_REQUEST + 1))
        connection.endheaders()
        self.assertEqual(connection.getresponse().status, 400)
        connection.close()
        item = body(); status, result = request('sequence-import-item', json.dumps(item).encode())
        self.assertEqual(status, 201)
        self.assertEqual(request('sequence-import-result/' + item['request_id'])[1], dict(found=True, **result))
        with patch.object(self.w, '_history', side_effect=sqlite3.OperationalError('injected')):
            next_item = body(*synthetic(), item_name='source-derived')
            self.assertEqual(request('sequence-import-item', json.dumps(next_item).encode())[0], 500)
        self.assertEqual(request('sequence-import-result/' + next_item['request_id'])[1], {'found': False})
        self.assertEqual(self.w.query({'kind': 'sequence'})['total'], 1)


if __name__ == '__main__':
    unittest.main()
