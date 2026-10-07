"""Actual native ZIP -> HTTP admission -> review/selection/preview/frozen export."""
import base64
import hashlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import zipfile

from app import Dataset, make_handler
from workbench import encode


def native_fixture(path, texts=('Cafe\u0301\r\nSource one.', 'Source two.', 'Source three.'), name_prefix='Source'):
    source = Dataset(str(path))
    rows = []
    for number, text in enumerate(texts):
        row = source.workbench.import_asset({'kind': 'text', 'text': text, 'name': f'{name_prefix} {number+1}',
            'groups': [f'native-family-{number+1}'], 'rights': 'Owned upstream'})
        rows.append(source.workbench.save(row['id'], dict(row, annotation={'label': f'class-{number+1}'}, review='human_reviewed')))
    body = {'items': [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows],
        'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 7, 'format': 'canonical_v1'}
    preview = source.releases.preview(body)
    release = source.releases.create(dict(body, preview_token=preview['preview_token']))
    raw = source.releases.locate(release['id']).read_bytes()
    source.close()
    return raw


def rewrite(raw, change):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    change(entries)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return stream.getvalue()


class NativeTextImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.raw = native_fixture(self.path/'source')
        self.dataset = Dataset(str(self.path/'destination'))
        self.open_server()
        self.addCleanup(self.close)

    def open_server(self):
        self.handler = make_handler(self.dataset)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.dataset.close()

    def request(self, route, body=None):
        request = urllib.request.Request(self.root+'/api/workbench/'+route,
            data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def prepare(self, raw=None):
        status, prepared = self.request('native-text-import/prepare',
            {'source_name': 'classification.zip', 'archive': base64.b64encode(raw or self.raw).decode()})
        self.assertEqual(status, 200, prepared)
        return prepared

    def admit(self, row, expected=201, request_id=None):
        body = {'token': row['token'], 'request_id': request_id or uuid.uuid4().hex}
        status, receipt = self.request('native-text-import/row', body)
        self.assertEqual(status, expected, receipt)
        return body, receipt

    def selection(self, rows):
        return {'items': [{k: row[k] for k in ('id', 'revision', 'source_revision')} for row in rows],
            'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 7, 'format': 'canonical_v1'}

    def test_real_roundtrip_provenance_restart_review_selection_preview_export(self):
        before = list(self.dataset.db.iterdump())
        prepared = self.prepare()
        self.assertEqual(list(self.dataset.db.iterdump()), before, 'Preparation is read-only')
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            native_rows = [json.loads(line) for line in archive.read('train/records.jsonl').splitlines()]
            manifest_hash = hashlib.sha256(archive.read('manifest.json')).hexdigest()
            metadata_hash = hashlib.sha256(archive.read('train/records.jsonl')).hexdigest()
        admitted = [self.admit(row) for row in prepared['rows']]
        records = [self.dataset.workbench.get(receipt['record_id']) for _, receipt in admitted]
        for row, origin, (_, receipt), record in zip(prepared['rows'], native_rows, admitted, records):
            self.assertNotEqual(record['id'], origin['id'])
            self.assertEqual((record['revision'], record['review'], record['task']), (1, 'draft', 'text_classification'))
            self.assertEqual(record['annotation'], origin['annotation'])
            self.assertEqual(record['text'], origin['text'])
            original = self.dataset.db.execute('SELECT original_text FROM workbench_records WHERE id=?', (record['id'],)).fetchone()[0]
            self.assertEqual(original, origin['text'])
            self.assertEqual(record['source_sha256'], hashlib.sha256(original.encode()).hexdigest())
            self.assertEqual(record['provenance']['rights'], 'unknown')
            self.assertEqual(record['source_split'], 'unassigned')
            self.assertEqual(record['parents'], [])
            self.assertTrue(set(origin['groups']) <= set(record['groups']))
            context = record['provenance']['acquisition']
            self.assertEqual(context['input_sha256'], record['source_sha256'])
            self.assertEqual(context['input_basis'], 'consumed_exported_text')
            self.assertEqual(context['archive_sha256'], hashlib.sha256(self.raw).hexdigest())
            self.assertEqual(context['manifest_sha256'], manifest_hash)
            self.assertEqual(context['metadata_sha256'], metadata_hash)
            self.assertEqual(context['row_sha256'], receipt['row_sha256'])
            self.assertEqual(context['declared']['upstream'], {'record': origin, 'original_status': 'unavailable'})
            self.assertEqual(context['declared']['asset'], origin['asset'])
            self.assertEqual(self.dataset.workbench.history(record['id']), [record])
        differing = [record['source_sha256'] != native['source_sha256'] for record, native in zip(records, native_rows)]
        self.assertTrue(any(differing), 'Never assign omitted upstream original hash to new input')
        self.assertFalse(self.dataset.releases.preview(self.selection(records))['eligible'])
        self.close(); self.dataset = Dataset(str(self.path/'destination')); self.open_server()
        for (body, receipt), old in zip(admitted, records):
            self.assertEqual(self.request('import-result/'+body['request_id']), (200, dict(found=True, **receipt)))
            self.assertEqual(self.dataset.workbench.get(old['id']), old)
        self.admit(prepared['rows'][0], expected=400)  # Process-local preparation expired.
        reviewed = []
        for old in records:
            status, row = self.request('records/'+old['id'], dict(old, review='human_reviewed'))
            self.assertEqual(status, 200, row); reviewed.append(row)
        status, saved = self.request('selections', dict(name='Imported native labels', items=self.selection(reviewed)['items']))
        self.assertEqual(status, 201, saved)
        status, reopened = self.request('selections/'+saved['id'])
        self.assertEqual(status, 200, reopened)
        self.assertEqual(reopened['selection']['items'], saved['items'])
        self.assertTrue(reopened['current'])
        self.assertTrue(all(member['status'] == 'ok' for member in reopened['members']), reopened)
        body = self.selection(reviewed)
        status, preview = self.request('releases/preview', body)
        self.assertEqual(status, 200); self.assertTrue(preview['eligible'], preview)
        status, release = self.request('releases', dict(body, preview_token=preview['preview_token']))
        self.assertEqual(status, 201, release)
        with zipfile.ZipFile(self.dataset.releases.locate(release['id'])) as archive:
            rows = json.loads(archive.read('manifest.json'))['records']
            for row in rows:
                origin = next(r for r in reviewed if r['id'] == row['id'])
                self.assertEqual(archive.read(row['asset']), origin['text'].encode())
                self.assertEqual(row['annotation'], origin['annotation'])
                self.assertEqual(row['groups'], origin['groups'])
                self.assertEqual(row['provenance'], origin['provenance'])

    def test_partial_malformed_missing_asset_mismatched_binding_then_valid(self):
        def corrupt(entries):
            lines = entries['train/records.jsonl'].splitlines()
            first = json.loads(lines[0]); entries.pop(first['asset'])
            lines[1] = b'{broken'
            entries['train/records.jsonl'] = b'\n'.join(lines)+b'\n'
        prepared = self.prepare(rewrite(self.raw, corrupt))
        self.assertEqual(len(prepared['rows']), 4)  # Malformed line and unmatched origin both reported.
        self.assertTrue(all('error' in row for row in prepared['rows'][:2]))
        self.admit(prepared['rows'][2])
        self.assertEqual(self.dataset.workbench.query({})['total'], 1)

    def test_duplicate_text_marker_and_history_are_never_overwritten(self):
        prepared = self.prepare()
        body, receipt = self.admit(prepared['rows'][0])
        row = self.dataset.workbench.get(receipt['record_id'])
        row = self.dataset.workbench.save(row['id'], dict(row, annotation={'label': 'human change'}, review='human_reviewed'))
        before = list(self.dataset.db.iterdump())
        self.admit(prepared['rows'][0], 409, body['request_id'])
        self.admit(prepared['rows'][0], 409)
        self.assertEqual(list(self.dataset.db.iterdump()), before)
        self.admit(prepared['rows'][1])

    def test_atomic_history_failure_rolls_back_record_and_marker(self):
        prepared = self.prepare(); marker = uuid.uuid4().hex
        with patch.object(self.dataset.workbench, '_history', side_effect=sqlite3.OperationalError('injected history failure')):
            self.admit(prepared['rows'][0], 500, marker)
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)
        self.assertEqual(self.request('import-result/'+marker), (200, {'found': False}))
        self.admit(prepared['rows'][0], request_id=marker)

    def test_lost_response_after_commit_can_be_confirmed_without_replay(self):
        prepared = self.prepare(); marker = uuid.uuid4().hex
        reply = self.handler.reply
        def lose_ack(handler, body, status=200):
            if handler.path.endswith('/native-text-import/row') and status == 201:
                handler.connection.shutdown(socket.SHUT_RDWR)
                handler.connection.close()
                return
            return reply(handler, body, status)
        with patch.object(self.handler, 'reply', lose_ack):
            with self.assertRaises(http.client.RemoteDisconnected):
                self.admit(prepared['rows'][0], request_id=marker)
        status, found = self.request('import-result/'+marker)
        self.assertEqual(status, 200); self.assertTrue(found['found'])
        self.assertEqual(found['row_sha256'], prepared['rows'][0]['row_sha256'])
        self.assertEqual(self.dataset.workbench.query({})['total'], 1)
        self.admit(prepared['rows'][0], 409, marker)

    def test_unknown_version_tampering_and_bad_archive_do_not_write(self):
        def version(entries):
            manifest = json.loads(entries['manifest.json']); manifest['schema_version'] = 2
            entries['manifest.json'] = encode(manifest).encode()
        for raw in (b'not ZIP', rewrite(self.raw, version)):
            status, result = self.request('native-text-import/prepare', {'source_name': 'source.zip', 'archive': base64.b64encode(raw).decode()})
            self.assertEqual(status, 400, result)
        prepared = self.prepare(); row = dict(prepared['rows'][0]); row['token'] += 'x'
        self.admit(row, 400)
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)

    def test_exact_row_and_asset_bindings_unsupported_tasks_and_targets_are_partial(self):
        for mutation in ('text', 'task', 'annotation', 'unknown', 'id'):
            def corrupt(entries):
                manifest = json.loads(entries['manifest.json'])
                lines = entries['train/records.jsonl'].splitlines()
                row = json.loads(lines[0])
                if mutation == 'text': row['text'] += ' changed without asset change'
                if mutation == 'task': row['task'] = 'text_entities'; row['annotation'] = {'spans': []}
                if mutation == 'annotation': row['annotation'] = {'label': 'class-1', 'approved': True}
                if mutation == 'unknown': row['original_text'] = 'Invented alias'
                if mutation == 'id': row['id'] = []
                if mutation != 'id':
                    manifest['records'] = [row if r['id'] == row['id'] else r for r in manifest['records']]
                    entries['manifest.json'] = encode(manifest).encode()
                lines[0] = encode(row).encode(); entries['train/records.jsonl'] = b'\n'.join(lines)+b'\n'
            prepared = self.prepare(rewrite(self.raw, corrupt))
            self.assertIn('error', prepared['rows'][0], mutation)
            self.assertEqual(sum('token' in row for row in prepared['rows']), 2, mutation)
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)

    def test_missing_manifest_member_is_reported_without_replacement(self):
        def remove(entries):
            entries['train/records.jsonl'] = b'\n'.join(entries['train/records.jsonl'].splitlines()[1:])+b'\n'
        prepared = self.prepare(rewrite(self.raw, remove))
        self.assertEqual(sum('token' in row for row in prepared['rows']), 2)
        missing = [row for row in prepared['rows'] if 'error' in row]
        self.assertEqual(len(missing), 1); self.assertIn('no matching metadata row', missing[0]['error'])

    def test_declared_parent_relationships_preserve_groups_without_local_parent_or_split_authority(self):
        def parents(entries):
            manifest = json.loads(entries['manifest.json']); rows = manifest['records']
            rows[1]['parents'] = [rows[0]['id']]
            entries['manifest.json'] = encode(manifest).encode()
            entries['train/records.jsonl'] = ''.join(encode(row)+'\n' for row in rows).encode()
        prepared = self.prepare(rewrite(self.raw, parents))
        records = [self.dataset.workbench.get(self.admit(row)[1]['record_id']) for row in prepared['rows']]
        self.assertTrue(set(records[0]['groups']) & set(records[1]['groups']))
        self.assertEqual(records[1]['parents'], [])
        self.assertEqual(records[1]['source_split'], 'unassigned')
        self.assertEqual(records[1]['review'], 'draft')

    def test_duplicate_paths_compressed_entries_and_manifest_aliases_are_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in entries.items(): archive.writestr(name, value)
        compressed = stream.getvalue()
        def alias(entries):
            manifest = json.loads(entries['manifest.json']); manifest['format'] = 'canonical_v1'
            entries['manifest.json'] = encode(manifest).encode()
        for raw in (compressed, rewrite(self.raw, lambda e:e.update({'../source.txt': b'unsafe'})), rewrite(self.raw, alias)):
            status, error = self.request('native-text-import/prepare', {'source_name': 'native.zip', 'archive': base64.b64encode(raw).decode()})
            self.assertEqual(status, 400, error)
        self.assertEqual(self.dataset.workbench.query({})['total'], 0)


if __name__ == '__main__':
    unittest.main()
