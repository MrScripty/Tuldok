"""Synthetic v2 transport refusal/custody proofs; NOT actual-packet acceptance."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error
import unittest
import uuid
import zipfile

from app import Dataset, make_handler
from fixtures.rheon_controls_authored import fixture
from test_sequences import fixture as v1_fixture
from test_mesh_release import rewrite, change_manifest
import rheon_sequences as adapter
import rheon_controls_contract as controls
import sequence_batch_import as batch
import sequence_release
from workbench import WorkbenchError, encode


def body(files, **metadata):
    return dict(files={name: base64.b64encode(raw).decode() for name, raw in
                      zip(('run.json', 'frames.jsonl', 'controls.json'), files)}, **metadata)


class ControlsContract(unittest.TestCase):
    def test_source_pin_and_synthetic_native_transport(self):
        raw = fixture()
        prepared = adapter.prepare(*raw)
        self.assertEqual(prepared['metadata']['controls_sha256'], hashlib.sha256(raw[2]).hexdigest())
        self.assertEqual(prepared['metadata']['controls_summary']['interval_count'], 8)
        self.assertIn('synthetic', prepared['metadata']['controls_summary']['provenance']['source_note'])
        with zipfile.ZipFile(io.BytesIO(prepared['bundle'])) as bundle:
            self.assertEqual(bundle.namelist(), ['run.json', 'frames.jsonl', 'controls.json'])
            self.assertEqual([bundle.read(name) for name in bundle.namelist()], list(raw))
        source = Path(controls.__file__).read_bytes().replace(
            b'import rheon_controls_sequence_contract as v1', b'import import_dense3d_sequence as v1')
        self.assertEqual(hashlib.sha256(source).hexdigest(), adapter.CONTROLS_ADAPTER['validator_sha256'])
        self.assertEqual(hashlib.sha256(Path(controls.v1.__file__).read_bytes()).hexdigest(),
                         '5c41f3a3c848940191d05d9b5b01a2a398b0d2a67f23c603ab8e918897bd3b55')
        with tempfile.TemporaryDirectory() as directory:
            for name, value in zip(('run.json', 'frames.jsonl', 'controls.json'), raw):
                (Path(directory) / name).write_bytes(value)
            self.assertEqual(controls.verify(directory), prepared['metadata']['technical_validation'])

    def test_v1_complete_prepared_identity_is_unchanged(self):
        prepared = adapter.prepare(*v1_fixture())
        self.assertEqual(hashlib.sha256(prepared['bundle']).hexdigest(),
                         '577a8538af3cf63a3715bc44f3bd319ce96a11f3fc0e4aef1022d71b9a961d96')
        self.assertEqual(hashlib.sha256(encode(prepared['metadata']).encode()).hexdigest(),
                         '022599d57015d983eeafd28acb70e7441440d28fa694ad83fc9ef222d902a890')
        self.assertNotIn('controls_summary', prepared['metadata'])
        self.assertEqual(adapter.prepare(*fixture())['metadata']['protected_groups'][1],
                         prepared['metadata']['protected_groups'][1])

    def test_current_v2_build_command_retains_independent_v1_contract(self):
        run, frames, raw = fixture()
        manifest, sidecar = json.loads(run), json.loads(raw)
        manifest['provenance']['build_command'].append('--message-format=json-render-diagnostics')
        sidecar['run_binding']['provenance'] = copy.deepcopy(manifest['provenance'])
        raw = json.dumps(sidecar).encode()
        manifest.update(controls_bytes=len(raw), controls_sha256=hashlib.sha256(raw).hexdigest())
        prepared = adapter.prepare(json.dumps(manifest).encode(), frames, raw)
        self.assertEqual(prepared['metadata']['manifest']['provenance']['build_command'][-1], '--message-format=json-render-diagnostics')
        with self.assertRaises(WorkbenchError):
            adapter.prepare(*v1_fixture(manifest_mutation=lambda m:
                m['provenance']['build_command'].append('--message-format=json-render-diagnostics')))

    def test_explicit_versions_and_file_sets_do_not_downgrade(self):
        v2 = fixture()
        invalid = [v2[:2], (*v1_fixture(), v2[2]), (v2[0], v2[1], b''),
                   (v2[0], v2[1], b'x' * (controls.CONTROLS_LIMIT + 1))]
        for raw in invalid:
            with self.assertRaises(WorkbenchError):
                adapter.prepare(*raw)
        for version in (True, 2.0, 3, None):
            with self.subTest(version=version), self.assertRaises(WorkbenchError):
                adapter.prepare(*fixture(mutate_manifest=lambda value: value.update(version=version)))
        for files in ({}, {'run.json': 'eA=='}, dict(body(v2)['files'], extra='eA==')):
            with self.assertRaises(WorkbenchError):
                adapter.prepare_files(files)

    def test_refuse_controls_types_fields_clock_stamps_units_sign_and_binding(self):
        mutations = [lambda c: c.update(version=True), lambda c: c.update(extra=0),
                     lambda c: c['intervals'].pop(), lambda c: c.update(axis_order=['z', 'y', 'x']),
                     lambda c: c.update(speed_sign='positive inward normal'),
                     lambda c: c['units'].update(outward_speed='cm/s'),
                     lambda c: c['run_binding'].update(version=1),
                     lambda c: c['provenance'].update(origin='authored'),
                     lambda c: c['intervals'][0].update(start_frame=True),
                     lambda c: c['intervals'][0].update(end_time_s=.5),
                     lambda c: c['intervals'][0].update(dt_s=.0625 + 1e-10),
                     lambda c: c['intervals'][0]['carrier_after'].update(version=1),
                     lambda c: c['intervals'][0]['boundary_stamp'].update(id='48'),
                     lambda c: c['intervals'][0].update(outward_speed_m_s=[[.25, .25], [0, 0], [0, 0]]),
                     lambda c: c['intervals'][0].update(source_rate_m3_s=1),
                     lambda c: c['intervals'][0].update(body_acceleration_m_s2=[0, float('nan'), 0])]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(WorkbenchError):
                adapter.prepare(*fixture(mutate_controls=mutate))
        for mutate in (lambda m: m.update(controls_bytes=True), lambda m: m.update(controls_sha256='0' * 64)):
            with self.assertRaises(WorkbenchError):
                adapter.prepare(*fixture(mutate_manifest=mutate))
        run, frames, raw = fixture()
        for changed in (raw + b' ', raw[:-1], b'{}', raw[:-1] + b',"version":2}'):
            manifest = json.loads(run)
            manifest.update(controls_bytes=len(changed), controls_sha256=hashlib.sha256(changed).hexdigest())
            if changed == raw + b' ':
                # Whitespace is legal; original control bytes still alter trajectory custody.
                other = adapter.prepare(json.dumps(manifest).encode(), frames, changed)
                self.assertNotEqual(other['metadata']['protected_groups'][0], adapter.prepare(run, frames, raw)['metadata']['protected_groups'][0])
            else:
                with self.assertRaises(WorkbenchError):
                    adapter.prepare(json.dumps(manifest).encode(), frames, changed)


class ControlsCustody(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())

    def test_batch_import_receipt_review_release_and_reopen_preserve_three_files(self):
        raw = fixture()
        request = body(raw, request_id=uuid.uuid4().hex, batch_name='Authored controls', item_name='Synthetic trajectory',
                       item_index=1, rights='Synthetic fixture; not actual producer evidence.')
        receipt = batch.import_item(self.dataset.workbench, request)
        self.assertEqual(receipt['controls_sha256'], hashlib.sha256(raw[2]).hexdigest())
        row = self.dataset.workbench.get(receipt['record_id'])
        self.assertEqual(row['review'], 'draft')
        row = self.dataset.workbench.save(row['id'], dict(row, review='human_reviewed', annotation={'note': 'Inspected synthetic controls.'}))
        frozen = dict(items=[{key: row[key] for key in ('id', 'revision', 'source_revision')}],
                      ratios=dict(train=100, validation=0, test=0), seed=4)
        preview = self.dataset.releases.preview(frozen)
        self.assertTrue(preview['eligible'], preview)
        release = self.dataset.releases.create(dict(frozen, preview_token=preview['preview_token']))
        path = self.dataset.releases.locate(release['id'])
        summary = sequence_release.validate_release(path, release['id'])
        self.assertEqual(summary['sequences'][0]['controls_summary']['interval_count'], 8)
        self.assertEqual(summary['sequences'][0]['controls_sha256'], receipt['controls_sha256'])
        for field in ('sequence', 'provenance'):
            changed = rewrite(path.read_bytes(), lambda entries: change_manifest(entries,
                lambda manifest: manifest['records'][0][field].update(controls_sha256='0' * 64)))
            with self.assertRaises(WorkbenchError):
                sequence_release.validate_bytes(changed, hashlib.sha256(changed).hexdigest())
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name)
        self.assertEqual(batch.find_result(self.dataset.workbench, request['request_id'])['controls_sha256'], receipt['controls_sha256'])
        bundle, _ = self.dataset.workbench.asset(row['id'])
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertEqual([archive.read(name) for name in archive.namelist()], list(raw))
        self.assertEqual(sequence_release.validate_release(path, release['id']), summary)

    def test_malformed_controls_refused_before_any_persistence(self):
        for raw in (fixture(mutate_controls=lambda c: c['intervals'][0].update(start_frame=5)), fixture()[:2]):
            with self.assertRaises(WorkbenchError):
                adapter.admit(self.dataset.workbench, body(raw))
        for table in ('workbench_records', 'workbench_sequence_assets', 'workbench_history'):
            self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)

    def test_actual_http_envelopes_fail_before_storage_then_single_v2_imports_draft(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(3))
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port) + '/api/workbench/'
        def request(route, raw):
            value = urllib.request.Request(base + route, raw, headers={'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(value, timeout=5) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as response:
                return response.code, json.load(response)
        for route in ('sequence-import', 'sequence-import-item'):
            for raw in (b'{"files":{},"files":{}}', b'[' * 1500, b'{"item_index":Infinity}'):
                with self.subTest(route=route, raw=raw[:50]):
                    self.assertEqual(request(route, raw)[0], 400)
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workbench_records').fetchone()[0], 0)
        status, row = request('sequence-import', json.dumps(body(fixture())).encode())
        self.assertEqual(status, 201)
        self.assertEqual(row['review'], 'draft')
        self.assertEqual(row['sequence']['controls_summary']['interval_count'], 8)
