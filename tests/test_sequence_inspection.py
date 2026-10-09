"""Recorded actual native fields plus independently authored controls; no execution."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import urllib.request
import urllib.error
import zipfile
from PIL import Image

from app import Dataset, make_handler
from fixtures.rheon_authored_controls import authored_controls
from test_sequences import body as import_body
from dataset_releases import allocate
import rheon_sequences
import sequence_inspection as probe
from workbench import WorkbenchError, encode

ACTUAL = Path(__file__).parent / 'fixtures/rheon_actual_fee7b4a'


class Inspection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.d = Dataset(self.tmp.name); self.addCleanup(self.d.close); self.w = self.d.workbench
        self.run = (ACTUAL / 'run.json').read_bytes(); self.raw = (ACTUAL / 'frames.jsonl').read_bytes()
        self.row = rheon_sequences.admit(self.w, import_body(self.run, self.raw, groups=['fixture-family']))
        self.frames = [json.loads(line) for line in self.raw.splitlines()]

    def body(self, **changes):
        return dict(revision=1, source_revision=1, frame=8, field='velocity_x', index=[16, 7, 3], **changes)

    def state(self):
        return tuple(self.d.db.iterdump())

    def controls(self, value=None):
        return base64.b64encode(encode(value or authored_controls(self.run, self.raw)).encode()).decode()

    def test_actual_native_every_field_edge_location_value_and_whole_family_read_only(self):
        before = self.state(); bundle = self.w.asset(self.row['id'])[0]
        for name, shape in probe.contract.GEOMETRY['field_shapes'].items():
            request = self.body(); request.update(field=name, index=[s - 1 for s in shape])
            result = probe.inspect(self.w, self.row['id'], request); field = result['field']
            value = self.frames[8]['fields'][name][-1]
            if field['dtype'] == 'f32': value = struct.unpack('<f', struct.pack('<f', value))[0]
            self.assertEqual(field['value'], value); self.assertEqual(field['shape'], shape)
            self.assertEqual(field['flat_index'], len(self.frames[8]['fields'][name]) - 1)
            self.assertEqual(field['position_m'], [(request['index'][j] + field['location_offset'][j]) * probe.contract.GEOMETRY['spacing_m'][j] for j in range(3)])
            self.assertEqual(result['accepted_interval']['carrier_before'], self.frames[7]['carrier_stamp'])
            self.assertEqual(result['accepted_interval']['liquid_after'], self.frames[8]['liquid_stamp'])
            self.assertEqual(result['interval_controls_emitted']['scope'], 'interval_controls_emitted_unavailable')
            self.assertIsNone(result['authored_controls_preview']); self.assertEqual(result['review'], 'draft')
        self.assertEqual(self.state(), before); self.assertEqual(self.w.asset(self.row['id'])[0], bundle)
        with self.assertRaises(WorkbenchError): allocate([self.row], self.w._all(), {'train': 80, 'validation': 10, 'test': 10}, 42)

    def test_constructor_and_authored_controls_separate_emitted_evidence(self):
        request = self.body(); request.update(frame=0, controls=self.controls())
        result = probe.inspect(self.w, self.row['id'], request)
        self.assertIsNone(result['accepted_interval']); self.assertIsNone(result['frame']['diagnostics'])
        self.assertIsNone(result['authored_controls_preview']['selected_interval'])
        request['frame'] = 8; result = probe.inspect(self.w, self.row['id'], request)
        self.assertEqual(result['authored_controls_preview']['selected_interval']['end_frame'], 8)
        self.assertEqual(result['authored_controls_preview']['scope'], 'authored_controls_preview')
        self.assertEqual(result['interval_controls_emitted']['scope'], 'interval_controls_emitted_unavailable')

    def test_actual_f32_probe_preserves_native_bits_instead_of_decimal_widening(self):
        request = self.body(); request.update(frame=1, field='velocity_y', index=[0,1,0])
        decimal = self.frames[1]['fields']['velocity_y'][16]
        native = struct.unpack('<f', struct.pack('<f', decimal))[0]
        self.assertNotEqual(decimal, native)
        result = probe.inspect(self.w, self.row['id'], request)
        self.assertEqual(result['field']['flat_index'],16)
        self.assertEqual(result['field']['value'],native)
        self.assertEqual(result['field']['shape'],[16,9,4])

    def test_other_asset_kind_and_oversize_blob_rejected_before_owner_load(self):
        from test_meshes import fixture as mesh_fixture, body as mesh_body
        import meshes
        mesh = meshes.admit(self.w, mesh_body(*mesh_fixture()))
        before = self.state()
        with self.assertRaises(WorkbenchError): probe.inspect(self.w, mesh['id'], self.body())
        self.assertEqual(self.state(),before)
        data = b'x' * (probe.MAX_BUNDLE_BYTES + 1)
        self.d.db.execute('UPDATE workbench_sequence_assets SET bundle=?,bundle_bytes=?', (data,len(data)));self.d.db.commit()
        with patch.object(self.w.sequences,'asset',side_effect=AssertionError('oversize BLOB must not load')):
            with self.assertRaises(WorkbenchError):probe.inspect(self.w,self.row['id'],self.body())

    def test_closed_controls_reject_malformed_hash_truncated_axis_stamp_units_nonfinite(self):
        original = authored_controls(self.run, self.raw); before = self.state()
        def changed(path, value):
            obj = copy.deepcopy(original); target = obj
            for part in path[:-1]: target = target[part]
            target[path[-1]] = value
            return obj
        cases = [(['run_sha256'], '0' * 64), (['frames_sha256'], '0' * 64), (['version'], 2),
            (['axis_order'], ['y','x','z']), (['side_order'], ['high','low']), (['speed_sign'], 'positive x'),
            (['units','body_acceleration'], 'm/s'), (['intervals'], original['intervals'][:7]),
            (['intervals',0,'carrier_after','version'], '02'), (['intervals',0,'liquid_before','id'], '42'),
            (['intervals',0,'dt_s'], 0), (['intervals',0,'end_frame'], True),
            (['intervals',0,'source_mode'], 'net-zero'), (['intervals',0,'source_rate_m3_s'], float('nan')),
            (['intervals',0,'body_acceleration_m_s2'], [0,1,0]),
            (['provenance','origin'], 'producer_emitted'), (['provenance','author'], ''),
            (['provenance','author'], '\ud800'),
            (['intervals',0,'outward_speed_m_s'], [[.25,-.25],[0,0],[0,0]])]
        for path, value in cases:
            with self.subTest(path=path):
                request = self.body(); request['controls'] = base64.b64encode(json.dumps(changed(path, value), allow_nan=True).encode()).decode()
                with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], request)
                self.assertEqual(self.state(), before)
        for raw in (b'{', b'x' * 65537, b'{"schema":1,"schema":2}', b'{}'):
            request = self.body(); request['controls'] = base64.b64encode(raw).decode()
            with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], request)
        unknown = copy.deepcopy(original); unknown['extra'] = True
        request = self.body(); request['controls'] = self.controls(unknown)
        with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], request)

    def test_request_bounds_cas_precede_blob_and_metadata_is_revalidated(self):
        before = self.state()
        for key,value in [('revision',2), ('source_revision',2), ('frame',9), ('frame',True), ('field','velocity'), ('index',[17,0,0]), ('index',[0,8,0]), ('index',[0,0,4])]:
            request = self.body(); request[key] = value
            with patch.object(self.w.sequences, 'asset', side_effect=AssertionError('must not read BLOB')):
                with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], request)
        self.assertEqual(self.state(), before)
        self.d.db.execute('UPDATE workbench_sequence_assets SET bundle_bytes=1'); self.d.db.commit()
        with patch.object(self.w.sequences, 'asset', side_effect=AssertionError('must preflight BLOB')):
            with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], self.body())

    def test_tampered_index_hash_zip_and_truncation_never_publish(self):
        bundle = self.w.asset(self.row['id'])[0]; metadata = dict(self.row['sequence']); metadata.pop('bundle_bytes')
        metadata['frame_index'][8]['byte_offset'] = 0
        self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?', (encode(metadata),)); self.d.db.commit()
        with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], self.body())
        for mode in ('truncated','compressed','extra','duplicate','bad-hash'):
            output = io.BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED if mode=='compressed' else zipfile.ZIP_STORED) as z:
                z.writestr('run.json',self.run); z.writestr('frames.jsonl',self.raw[:-9] if mode=='truncated' else self.raw)
                if mode in ('extra','duplicate'): z.writestr('extra' if mode=='extra' else 'run.json', self.run)
            data = output.getvalue()
            self.d.db.execute('UPDATE workbench_sequence_assets SET bundle=?,bundle_bytes=?', (data,len(data)))
            self.d.db.execute('UPDATE workbench_records SET content_hash=? WHERE id=?', (hashlib.sha256(data).hexdigest() if mode!='bad-hash' else '0'*64,self.row['id'])); self.d.db.commit()
            before = self.state()
            with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], self.body())
            self.assertEqual(self.state(), before)

    def test_stored_metadata_boolean_numeric_substitution_rejected_atomically(self):
        original = copy.deepcopy(self.row['sequence']); original.pop('bundle_bytes')
        for path, value in [(['frame_index',0,'dt_s'],False), (['manifest','version'],True),
                            (['frame_index',0,'frame'],0.0)]:
            metadata = copy.deepcopy(original); target = metadata
            for part in path[:-1]: target = target[part]
            target[path[-1]] = value
            self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?', (encode(metadata),)); self.d.db.commit()
            before = self.state(); bundle = self.w.asset(self.row['id'])[0]
            with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], self.body())
            self.assertEqual(self.state(), before); self.assertEqual(self.w.asset(self.row['id'])[0], bundle)

    def test_readonly_rollback_even_lazy_enrollment_and_error(self):
        original = self.w._all; before = self.state()
        def lazy():
            self.d.db.execute("UPDATE workbench_records SET name='would mutate'")
            return original()
        with patch.object(self.w, '_all', side_effect=lazy): probe.inspect(self.w, self.row['id'], self.body())
        self.assertEqual(self.state(), before)
        request = self.body(); request['controls'] = base64.b64encode(b'{}').decode()
        with patch.object(self.w, '_all', side_effect=lazy):
            with self.assertRaises(WorkbenchError): probe.inspect(self.w, self.row['id'], request)
        self.assertEqual(self.state(), before)

    def test_unselected_deleted_bridge_keeps_source_family(self):
        image = io.BytesIO(); Image.new('RGB', (2,2), 'orange').save(image,format='PNG')
        bridge = self.w.import_asset({'kind':'image','image':base64.b64encode(image.getvalue()).decode(),
                                     'groups':['fixture-family','linked-source']})
        related = self.w.import_asset({'kind':'text','text':'related','groups':['linked-source']})
        self.d.delete(bridge['id'], {'revision': bridge['source_revision']})
        before = self.state()
        result = probe.inspect(self.w, self.row['id'], self.body())
        self.assertEqual(set(result['lineage'][0]['member_ids']), {self.row['id'],bridge['id'],related['id']})
        self.assertEqual(result['lineage'][0]['selected_ids'], [self.row['id']])
        self.assertEqual(result['lineage'][0]['deleted_ids'], [bridge['id']])
        self.assertEqual(self.state(), before)

    def test_http_duplicate_caps_error_then_valid_read_preserves_record(self):
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.d)); self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start(); self.addCleanup(server.shutdown)
        url = 'http://127.0.0.1:%s/api/workbench/sequence-inspection/%s' % (server.server_port,self.row['id'])
        before = self.state()
        for raw in (b'{"frame":0,"frame":1}', b'x'*(probe.MAX_REQUEST+1), b'{'):
            req = urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as context: urllib.request.urlopen(req)
            self.assertEqual(context.exception.code,400)
        with urllib.request.urlopen(urllib.request.Request(url,data=encode(self.body()).encode(),headers={'Content-Type':'application/json'})) as response:
            self.assertEqual(json.load(response)['field']['shape'], [17,8,4])
        self.assertEqual(self.state(), before)
