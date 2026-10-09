"""Source-derived synthetic Rheon fixture, not an actual exporter/physics pilot.

Constructor and accepted-state formula come directly from draft PR 20 fee7b4a's
tools/test_dense3d_sequence_import.py. Provenance placeholders remain synthetic.
"""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import zipfile
import uuid
from PIL import Image

from app import Dataset, make_handler
from dataset_releases import allocate, connected_components
from fixtures.rheon_source_derived import synthetic_frames, synthetic_manifest
import rheon_sequence_contract as contract
import rheon_sequences as adapter
from sequence_assets import migrate_records
from workbench import WorkbenchError, encode


def fixture(frames=None, manifest_mutation=None, raw=None):
    if raw is None:
        raw = b''.join(json.dumps(frame, separators=(',', ':'), allow_nan=True).encode() + b'\n'
                       for frame in (frames if frames is not None else synthetic_frames()))
    manifest = synthetic_manifest(raw)
    if manifest_mutation:
        manifest_mutation(manifest)
    return json.dumps(manifest, allow_nan=True).encode(), raw


def body(run, frames, **metadata):
    return dict(files={'run.json': base64.b64encode(run).decode(),
                       'frames.jsonl': base64.b64encode(frames).decode()}, **metadata)


class Sequences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.d.close())
        self.w = self.d.workbench
        self.run, self.raw = fixture()

    def add(self, **metadata):
        return adapter.admit(self.w, body(self.run, self.raw, **metadata))

    def review(self, row, **changes):
        value = dict(revision=row['revision'], source_revision=row['source_revision'],
                     task='sequence_transport', annotation={'note': 'Human inspected transport scope and fields.'},
                     groups=row['groups'], review='human_reviewed')
        value.update(changes)
        return self.w.save(row['id'], value)

    def selection(self, rows):
        return [{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows]

    def snapshot(self):
        return {table: [tuple(row) for row in self.d.db.execute('SELECT * FROM ' + table)]
                for table in ('workbench_sequence_assets', 'workbench_records', 'workbench_history', 'workbench_rights_notes')}

    def test_raw_roundtrip_native_fields_index_review_history_rights_reopen(self):
        # A decimal f32 is interpreted natively, while raw decimal bytes stay exact.
        frames = synthetic_frames(); frames[2]['fields']['tracer'][0] = 0.1000000015
        self.run, self.raw = fixture(frames)
        row = self.add(name='Synthetic source-derived fixture')
        self.assertEqual((row['kind'], row['task'], row['review'], row['annotation']),
                         ('sequence', 'sequence_transport', 'draft', None))
        self.assertEqual(row['provenance']['rights'], 'unknown')
        self.assertEqual(row['sequence']['adapter']['contract_commit'], adapter.SOURCE_COMMIT)
        self.assertEqual(row['sequence']['manifest']['provenance']['toolchain']['rustc'], 'rustc synthetic')
        bundle, mime = self.w.asset(row['id']); self.assertEqual(mime, 'application/zip')
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertEqual(archive.namelist(), ['run.json', 'frames.jsonl'])
            self.assertEqual(archive.read('run.json'), self.run)
            self.assertEqual(archive.read('frames.jsonl'), self.raw)
        index = row['sequence']['frame_index']; self.assertEqual(len(index), 9)
        self.assertEqual(index[-1]['time_s'], 0.5)
        for entry in index:
            line = self.raw[entry['byte_offset']:entry['byte_offset'] + entry['byte_length']]
            self.assertEqual(hashlib.sha256(line).hexdigest(), entry['sha256'])
            self.assertEqual(json.loads(line)['frame'], entry['frame'])
            self.assertNotIn('fields', entry)
        decoded = contract._fields(json.loads(self.raw.splitlines()[2]))
        self.assertEqual(decoded['tracer'][0], struct.unpack('<f', struct.pack('<f', 0.1000000015))[0])
        reads = []; self.d.db.set_trace_callback(reads.append)
        self.assertEqual(self.w.query({'kind': 'sequence'})['total'], 1)
        self.assertFalse(any('SELECT bundle ' in sql for sql in reads)); self.d.db.set_trace_callback(None)
        reviewed = self.review(row)
        corrected = self.w.correct_rights_note(row['id'], dict(revision=reviewed['revision'], source_revision=1, note='Synthetic fixture authored for tests.'))['record']
        self.assertEqual(corrected['review'], 'human_reviewed')
        self.assertEqual(len(self.w.history(row['id'])), 3)
        self.assertEqual(self.w.history(row['id'])[-1], row)
        with self.assertRaises(WorkbenchError): self.review(row)
        self.d.close(); self.d = Dataset(self.tmp.name); self.w = self.d.workbench
        self.assertEqual(self.w.get(row['id']), corrected)
        self.assertEqual(self.w.asset(row['id'])[0], bundle)

    def test_malformed_hash_truncated_wrong_axis_stamp_interval_nonfinite_associations_atomic(self):
        before = self.snapshot()
        frame_changes = {
            'shape': lambda f: f[2]['fields']['velocity_x'].pop(),
            'stamp_gap': lambda f: f[3]['carrier_stamp'].__setitem__('version', '4'),
            'stamp_overflow': lambda f: f[3]['liquid_stamp'].__setitem__('version', '18446744073709551616'),
            'stamp_leading_zero': lambda f: f[3]['liquid_stamp'].__setitem__('version', '03'),
            'stamp_numeric': lambda f: f[3]['carrier_stamp'].__setitem__('id', 43),
            'wrong_id': lambda f: f[3]['liquid_stamp'].__setitem__('id', '42'),
            'interval': lambda f: f[4].__setitem__('dt_s', 0.1),
            'clock': lambda f: f[4].__setitem__('time_s', 0.3),
            'nan': lambda f: f[2]['fields']['fraction'].__setitem__(0, float('nan')),
            'infinity': lambda f: f[2]['diagnostics'].__setitem__('mass_after_kg', float('inf')),
            'native_overflow': lambda f: f[2]['fields']['tracer'].__setitem__(0, 1e40),
            'native_underflow': lambda f: f[2]['fields']['tracer'].__setitem__(0, 1e-100),
            'boolean': lambda f: f[2]['fields']['pressure'].__setitem__(0, True),
            'volume_association': lambda f: f[2]['diagnostics'].__setitem__('volume_after_m3', 0.1),
            'donor_association': lambda f: f[2]['fields']['fraction'].__setitem__(4, 0.0),
            'pressure_interval': lambda f: f[1]['fields']['pressure'].__setitem__(4, -999),
            'constructor': lambda f: f[0].__setitem__('diagnostics', {}),
        }
        for name, mutate in frame_changes.items():
            with self.subTest(name=name):
                frames = synthetic_frames(); mutate(frames)
                run, raw = fixture(frames)
                with self.assertRaises(WorkbenchError): adapter.admit(self.w, body(run, raw))
                self.assertEqual(self.snapshot(), before)
        manifest_changes = {
            'axis': lambda m: m['geometry'].__setitem__('axis_order', ['y', 'x', 'z']),
            'shape': lambda m: m['geometry']['field_shapes'].__setitem__('velocity_y', [9, 16, 4]),
            'unit': lambda m: m['units'].__setitem__('pressure', 'bar'),
            'dtype': lambda m: m['field_types'].__setitem__('pressure', 'f32'),
            'hash': lambda m: m.__setitem__('frames_sha256', '0' * 64),
            'hash_malformed': lambda m: m.__setitem__('frames_sha256', 'A' * 64),
            'bytes': lambda m: m.__setitem__('frames_bytes', 1),
            'partial': lambda m: m.__setitem__('complete', False),
            'frame_cap': lambda m: m.__setitem__('frame_count', 10),
            'traversal': lambda m: m.__setitem__('frames_file', '../frames.jsonl'),
            'pressure': lambda m: m.__setitem__('pressure_semantics', 'endpoint'),
            'source_hash': lambda m: m['provenance']['source_sha256'].pop('Cargo.lock'),
            'config': lambda m: m['config'].__setitem__('requested_dt_s', 1),
        }
        for name, mutate in manifest_changes.items():
            with self.subTest(name=name):
                run, raw = fixture(manifest_mutation=mutate)
                with self.assertRaises(WorkbenchError): adapter.admit(self.w, body(run, raw))
                self.assertEqual(self.snapshot(), before)
        for raw in (self.raw[:-10], self.raw[:-1], self.raw + b'\n', self.raw + self.raw.splitlines()[0] + b'\n',
                    self.raw.replace(b'"frame":0', b'"frame":]', 1),
                    self.raw.replace(b'"frame":0', b'"frame":0,"frame":0', 1),
                    self.raw.replace(b'"time_s":0.0', b'"time_s":1e9999', 1),
                    self.raw.replace(b'"time_s":0.0', b'"time_s":1e-9999', 1),
                    self.raw.replace(b'"frame"', b'"fra\xffme"', 1)):
            run, raw = fixture(raw=raw)
            with self.assertRaises(WorkbenchError): adapter.admit(self.w, body(run, raw))
            self.assertEqual(self.snapshot(), before)
        # Hash failure must occur before malformed frame parsing.
        with self.assertRaisesRegex(WorkbenchError, 'SHA256 mismatch'):
            adapter.prepare(self.run, self.raw.replace(b'"frame":0', b'"frame":]', 1))

    def test_file_line_envelope_bounds_and_no_client_paths(self):
        for run, raw in ((b' ' * (contract.MANIFEST_LIMIT + 1), self.raw),
                         (self.run, b' ' * (contract.FRAMES_LIMIT + 1))):
            with self.assertRaises(WorkbenchError): adapter.admit(self.w, body(run, raw))
        raw = self.raw.replace(b'\n', b' ' * contract.LINE_LIMIT + b'\n', 1)
        with self.assertRaisesRegex(WorkbenchError, 'line byte cap'):
            adapter.prepare(*fixture(raw=raw))
        for value in ({'directory': '/tmp'}, {'files': {'run.json': '???', 'frames.jsonl': '???'}},
                      {'files': {'run.json': '', 'frames.jsonl': ''}},
                      dict(body(self.run, self.raw), extra=True)):
            with self.assertRaises(WorkbenchError): adapter.admit(self.w, value)
        self.assertEqual(self.w.query({})['total'], 0)

    def test_atomic_insertion_and_history_failures_duplicate_preservation(self):
        before = self.snapshot()
        for table in ('workbench_sequence_assets', 'workbench_records', 'workbench_history'):
            with self.subTest(table=table):
                self.d.db.execute(f"CREATE TRIGGER fail_insert BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'controlled publication failure'); END")
                self.d.db.commit()
                with self.assertRaises(sqlite3.IntegrityError): self.add()
                self.assertEqual(self.snapshot(), before)
                self.d.db.execute('DROP TRIGGER fail_insert'); self.d.db.commit()
        row = self.add(); before = self.snapshot()
        with self.assertRaises(WorkbenchError): self.add()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.w.history(row['id']), [row])
        with self.assertRaises(WorkbenchError):
            adapter.admit(self.w, body(*fixture(manifest_mutation=lambda m: m['provenance']['command'].append('other-run')), parents=['0' * 32]))
        self.assertEqual(self.snapshot(), before)

    def test_immutable_family_human_only_whole_trajectory_release_and_saved_set(self):
        first = self.add(name='First trajectory')
        self.run, self.raw = fixture(manifest_mutation=lambda m: m['provenance']['command'].append('another-synthetic-run'))
        second = self.add(name='Second trajectory')
        self.assertEqual(first['groups'][1], second['groups'][1])
        self.assertNotEqual(first['groups'][0], second['groups'][0])
        self.assertEqual(connected_components(self.w._all())[first['id']], connected_components(self.w._all())[second['id']])
        with self.assertRaises(WorkbenchError): self.review(first, groups=['new-group'])
        with self.assertRaises(WorkbenchError): self.review(first, review='programmatically_verified')
        payload = dict(revision=1, source_revision=1, task='sequence_transport', annotation={'note': ''}, groups=first['groups'], review='programmatically_verified')
        with self.assertRaises(WorkbenchError): self.w.save(first['id'], payload, verified_provenance={'method': 'verifier'})
        export = dict(items=self.selection([first, second]), ratios=dict(train=100, validation=0, test=0), seed=42)
        self.assertFalse(self.d.releases.preview(export)['eligible'])
        first, second = self.review(first), self.review(second)
        with self.assertRaisesRegex(WorkbenchError, 'Too few independent'):
            allocate([first, second], self.w._all(), dict(train=50, validation=50, test=0), 42)
        assigned, report = allocate([first, second], self.w._all(), dict(train=100, validation=0, test=0), 42)
        self.assertEqual(assigned[first['id']], assigned[second['id']]); self.assertEqual(report['independent_components'], 1)
        export['items'] = self.selection([first, second])
        preview = self.d.releases.preview(export); self.assertTrue(preview['eligible'])
        release = self.d.releases.create(dict(export, preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json')); self.assertEqual(len(manifest['records']), 2)
            rows = [json.loads(line) for line in archive.read('train/records.jsonl').splitlines()]
            self.assertEqual(len(rows), 2)
            for row in manifest['records']:
                self.assertTrue(row['asset'].endswith('.zip'))
                self.assertEqual(archive.read(row['asset']), self.w.asset(row['id'])[0])
                with zipfile.ZipFile(io.BytesIO(archive.read(row['asset']))) as bundle:
                    adapter.prepare(bundle.read('run.json'), bundle.read('frames.jsonl'))
                self.assertEqual(len(row['sequence']['frame_index']), 9)
        saved = self.d.selections.create(dict(name='Whole trajectories', items=export['items']))
        self.assertTrue(self.d.selections.load(saved['id'])['current'])
        self.review(first, annotation={'note': 'Re-reviewed'})
        self.assertFalse(self.d.selections.load(saved['id'])['current'])

    def test_release_and_saved_selection_caps_precede_blob_reads(self):
        row = self.review(self.add()); items = self.selection([row])
        # Test cap enforcement without manufacturing huge BLOBs or simulations.
        with self.d.db:
            self.d.db.execute('UPDATE workbench_sequence_assets SET bundle_bytes=? WHERE id=?', (40 * 1024 * 1024 + 1, row['id']))
        with patch.object(self.w, 'asset', side_effect=AssertionError('BLOB must not be loaded')):
            preview = self.d.releases.preview(dict(items=items, ratios=dict(train=100, validation=0, test=0), seed=42))
            self.assertFalse(preview['eligible']); self.assertIn('40 MiB', preview['blockers'][0]['message'])
            with self.assertRaisesRegex(WorkbenchError, '40 MiB'):
                self.d.selections.create(dict(name='Over cap', items=items))

    def test_bundle_integrity_and_optimized_validation(self):
        row = self.add()
        with self.d.db:
            self.d.db.execute('UPDATE workbench_sequence_assets SET bundle=? WHERE id=?', (b'corrupt', row['id']))
        with self.assertRaisesRegex(WorkbenchError, 'changed'): self.w.asset(row['id'])
        frames = synthetic_frames(); frames[3]['carrier_stamp']['version'] = '5'
        run, raw = fixture(frames)
        root = Path(self.tmp.name); (root / 'run.json').write_bytes(run); (root / 'frames.jsonl').write_bytes(raw)
        result = subprocess.run([sys.executable, '-O', '-c', 'import sys; import rheon_sequences as a; from pathlib import Path; p=Path(sys.argv[1]); a.prepare((p/"run.json").read_bytes(),(p/"frames.jsonl").read_bytes())', str(root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0); self.assertIn('stamp continuity', result.stderr)

    def test_sequence_ancestry_preserves_caption_export_reimport(self):
        captions = []
        for index, color in enumerate(('red', 'blue', 'green')):
            stream = io.BytesIO(); Image.new('RGB', (512, 512), color).save(stream, 'PNG')
            row = self.w.import_asset(dict(kind='image', image=base64.b64encode(stream.getvalue()).decode(),
                                          name=f'Fixture {index}.png', groups=[f'caption-fixture-{index}']))
            captions.append(self.w.save(row['id'], dict(row, task='image_caption', annotation={'caption': f'A {color} fixture.'}, review='human_reviewed')))
        sequence = self.add(parents=[captions[0]['id']])
        request = dict(items=self.selection(captions), format='image_caption_v1',
                       ratios=dict(train=34, validation=33, test=33), seed=42)
        preview = self.d.releases.preview(request); self.assertTrue(preview['eligible'])
        release = self.d.releases.create(dict(request, preview_token=preview['preview_token']))
        with zipfile.ZipFile(self.d.releases.locate(release['id'])) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertIn(sequence['id'], [row['id'] for family in manifest['protected_components'].values() for row in family])
            prepared = self.d.caption_imports.prepare(dict(manifest=archive.read('manifest.json').decode(),
                metadata={split: archive.read(split + '/metadata.jsonl').decode() for split in ('train', 'val', 'test')}))
            self.assertEqual(len(prepared['rows']), 3)
            from caption_import import snapshot, SNAPSHOT_KEYS
            invalid = {key: sequence[key] for key in SNAPSHOT_KEYS}; invalid['source_sha256'] = '0' * 64
            with self.assertRaisesRegex(WorkbenchError, 'sequence'): snapshot(invalid)

    def test_mixed_sequence_release_keeps_native_classification_importable(self):
        text = self.w.import_asset(dict(kind='text', text='A reviewed classification fixture.', name='Text fixture', groups=['text-fixture']))
        text = self.w.save(text['id'], dict(text, annotation={'label': 'fixture'}, review='human_reviewed'))
        sequence = self.review(self.add())
        request = dict(items=self.selection([text, sequence]), ratios=dict(train=100, validation=0, test=0), seed=42)
        preview = self.d.releases.preview(request)
        release = self.d.releases.create(dict(request, preview_token=preview['preview_token']))
        prepared = self.d.native_text_imports.prepare(dict(source_name='mixed.zip',
            archive=base64.b64encode(self.d.releases.locate(release['id']).read_bytes()).decode()))
        self.assertEqual(len(prepared['rows']), 2)
        self.assertEqual(sum('token' in row for row in prepared['rows']), 1)
        self.assertEqual(sum('error' in row for row in prepared['rows']), 1)
        destination = Dataset(Path(self.tmp.name) / 'destination'); self.addCleanup(destination.close)
        prepared = destination.native_text_imports.prepare(dict(source_name='mixed.zip',
            archive=base64.b64encode(self.d.releases.locate(release['id']).read_bytes()).decode()))
        token = next(row['token'] for row in prepared['rows'] if 'token' in row)
        destination.native_text_imports.admit(dict(token=token, request_id=uuid.uuid4().hex))
        self.assertEqual(destination.workbench.query({})['total'], 1)
        self.assertEqual(destination.workbench.query({})['items'][0]['kind'], 'text')

    def test_http_admission_and_endpoint_request_bound(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.d))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        url = f'http://127.0.0.1:{server.server_port}/api/workbench/sequence-import'
        request = urllib.request.Request(url, json.dumps(body(self.run, self.raw)).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 201); self.assertEqual(json.load(response)['review'], 'draft')
        oversized = urllib.request.Request(url, b'{}', {'Content-Type': 'application/json', 'Content-Length': str(adapter.MAX_REQUEST + 1)})
        with self.assertRaises(urllib.error.HTTPError) as raised: urllib.request.urlopen(oversized)
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(self.w.query({})['total'], 1)


class SchemaMigration(unittest.TestCase):
    def legacy(self, db):
        db.execute('''CREATE TABLE workbench_records (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('image','text')),
            name TEXT, text TEXT, original_text TEXT, content_hash TEXT NOT NULL, pixel_hash TEXT,
            groups_json TEXT NOT NULL, parents_json TEXT NOT NULL, provenance_json TEXT NOT NULL,
            task TEXT NOT NULL, annotation_json TEXT, review TEXT NOT NULL, revision INTEGER NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        db.execute('CREATE INDEX workbench_content ON workbench_records(content_hash)')
        db.execute('CREATE INDEX custom_name ON workbench_records(name)')
        db.execute('INSERT INTO workbench_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   ('a' * 32, 'text', 'Legacy', 'Original', 'Original', 'b' * 64, None,
                    '["legacy"]', '[]', '{}', 'text_classification', '{"label":"old"}', 'human_reviewed', 7, 'created', 'updated'))
        db.commit()

    def test_exact_legacy_values_indexes_reopen_and_migration_failure_rollback(self):
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close); self.legacy(db)
        before = db.execute('SELECT * FROM workbench_records').fetchall()
        migrate_records(db); migrate_records(db)
        self.assertEqual(db.execute('SELECT * FROM workbench_records').fetchall(), before)
        self.assertEqual({r[1] for r in db.execute('PRAGMA index_list(workbench_records)')}, {'sqlite_autoindex_workbench_records_1', 'workbench_content', 'custom_name'})
        db2 = sqlite3.connect(':memory:'); self.addCleanup(db2.close); self.legacy(db2)
        db2.execute('CREATE TRIGGER refuse BEFORE INSERT ON workbench_records BEGIN SELECT RAISE(ABORT,"no"); END'); db2.commit()
        original_schema = db2.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall()
        with self.assertRaises(WorkbenchError): migrate_records(db2)
        self.assertEqual(db2.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall(), original_schema)
        db2.execute('DROP TRIGGER refuse'); db2.commit()
        # Authorizer fails after replacement-table creation; SAVEPOINT rolls back DDL.
        def authorize(action, arg1, arg2, *args):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_DROP_TABLE and arg1 == 'workbench_records' else sqlite3.SQLITE_OK
        db2.set_authorizer(authorize)
        with self.assertRaises(sqlite3.DatabaseError): migrate_records(db2)
        db2.set_authorizer(None)
        self.assertEqual(db2.execute('SELECT * FROM workbench_records').fetchall(), before)
        self.assertIsNone(db2.execute("SELECT 1 FROM sqlite_master WHERE name='workbench_records_sequence'").fetchone())


if __name__ == '__main__':
    unittest.main()
