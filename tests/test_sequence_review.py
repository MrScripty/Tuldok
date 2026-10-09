"""Recorded fee7b4a native oracle; separate synthetic v2 controls, no simulation."""
import copy
import hashlib
import io
import json
import struct
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from app import make_handler
import test_sequence_inspection as existing_probe_tests
from test_producer_v2_controls import body as v2_body
from test_sequences import fixture as synthetic_fixture, body as import_body
from fixtures.rheon_source_derived import synthetic_frames
from fixtures.rheon_synthetic_v2 import fixture as v2_fixture
import rheon_sequences
import sequence_inspection as projection
from workbench import WorkbenchError, encode


class TrajectoryReview(unittest.TestCase):
    setUp = existing_probe_tests.Inspection.setUp
    state = existing_probe_tests.Inspection.state

    def body(self, **changes):
        return dict(revision=1, source_revision=1, field='velocity_y', index=[0, 1, 0], plane_axis='z', **changes)

    def test_recorded_all_fields_axes_frames_independent_native_index_oracle_and_read_only(self):
        before=self.state(); bundle=self.w.asset(self.row['id'])[0]
        for name, shape in projection.contract.GEOMETRY['field_shapes'].items():
            index=[n-1 for n in shape]
            for normal,axis in enumerate('xyz'):
                request=self.body();request.update(field=name,index=index,plane_axis=axis)
                result=projection.review(self.w,self.row['id'],request)
                axes=[j for j in range(3) if j!=normal]
                self.assertEqual(result['plane']['axes'],['xyz'[j] for j in axes])
                self.assertEqual(result['plane']['index'],index[normal])
                self.assertEqual(result['field']['shape'],shape)
                self.assertLessEqual(len(json.dumps(result).encode()),projection.REVIEW_MAX_RESPONSE)
                for k,frame in enumerate(result['frames']):
                    native=self.frames[k]['fields'][name]
                    if result['field']['dtype']=='f32':native=[struct.unpack('<f',struct.pack('<f',v))[0] for v in native]
                    expected=[]
                    for v in range(shape[axes[1]]):
                        for u in range(shape[axes[0]]):
                            p=index[:];p[axes[0]]=u;p[axes[1]]=v
                            expected.append(native[p[2]*shape[1]*shape[0]+p[1]*shape[0]+p[0]])
                    self.assertEqual(frame['plane_values'],expected)
                    self.assertEqual(frame['value'],native[-1])
                    self.assertEqual((frame['minimum'],frame['maximum']),(min(native),max(native)))
                    self.assertEqual(frame['metadata'],self.row['sequence']['frame_index'][k])
                    self.assertIsNone(frame['emitted_control'])
                    if k:
                        self.assertEqual(frame['accepted_interval']['end_frame'],k)
                        self.assertEqual(frame['accepted_interval']['carrier_before'],self.frames[k-1]['carrier_stamp'])
                    else:
                        self.assertIsNone(frame['accepted_interval']);self.assertIsNone(frame['metadata']['diagnostics'])
                self.assertEqual(result['pressure_semantics'],projection.contract.PRESSURE_SEMANTICS)
                self.assertEqual(result['controls']['scope'],'interval_controls_emitted_unavailable')
        self.assertEqual(self.state(),before);self.assertEqual(self.w.asset(self.row['id'])[0],bundle)
        self.assertEqual(self.w._get(self.row['id'])['review'],'draft')

    def test_native_f32_bits_trace_and_plane_agree_at_known_decimal_difference(self):
        result=projection.review(self.w,self.row['id'],self.body())
        decimal=self.frames[1]['fields']['velocity_y'][16]
        value=struct.unpack('<f',struct.pack('<f',decimal))[0]
        self.assertNotEqual(decimal,value)
        self.assertEqual(result['frames'][1]['value'],value)
        self.assertEqual(result['frames'][1]['plane_values'][16],value)

    def test_synthetic_v2_original_eight_hash_bound_controls_not_authenticity(self):
        files=v2_fixture();row=rheon_sequences.admit(self.w,v2_body(files));before=self.state()
        result=projection.review(self.w,row['id'],self.body())
        self.assertEqual(result['controls']['sha256'],hashlib.sha256(files[2]).hexdigest())
        self.assertEqual(result['controls']['interval_count'],8)
        self.assertIn('does not authenticate',result['controls']['limitation'])
        controls=json.loads(files[2])
        self.assertIsNone(result['frames'][0]['emitted_control'])
        for k in range(1,9):self.assertEqual(result['frames'][k]['emitted_control'],controls['intervals'][k-1])
        self.assertEqual(self.state(),before)

    def test_labelled_synthetic_native_negative_zero_and_subnormal_display_payload(self):
        # Numeric stress fixture, not recorded producer or physical qualification.
        frames=synthetic_frames();frames[8]['fields']['pressure'][0]=-0.0
        frames[8]['fields']['pressure'][1]=5e-324
        frames[8]['fields']['velocity_y'][0]=-0.0
        run,raw=synthetic_fixture(frames=frames)
        row=rheon_sequences.admit(self.w,import_body(run,raw))
        request=self.body();request.update(field='pressure',index=[0,0,0])
        result=projection.review(self.w,row['id'],request)
        self.assertEqual(struct.pack('<d',result['frames'][8]['value']),struct.pack('<d',-0.0))
        self.assertEqual(result['frames'][8]['plane_values'][1],5e-324)
        self.assertIn('-0.0',json.dumps(result));self.assertIn('5e-324',json.dumps(result))
        request['field']='velocity_y'
        result=projection.review(self.w,row['id'],request)
        self.assertEqual(struct.pack('<f',result['frames'][8]['value']),struct.pack('<f',-0.0))

    def test_closed_request_revision_axis_index_and_kind_preflight_before_blob(self):
        for key,value in [('revision',2),('source_revision',True),('plane_axis','yx'),('field','velocity'),('index',[16,0,0]),('index',[0,9,0]),('index',[0,0,True]),('extra',0)]:
            request=self.body();request[key]=value
            with patch.object(self.w.sequences,'asset',side_effect=AssertionError('must not load')):
                with self.assertRaises(WorkbenchError):projection.review(self.w,self.row['id'],request)
        text=self.w.import_asset({'kind':'text','text':'unrelated','groups':['unrelated-source']})
        with patch.object(self.w.sequences,'asset',side_effect=AssertionError('must not load')):
            with self.assertRaises(WorkbenchError):projection.review(self.w,text['id'],self.body())
        self.d.db.execute('UPDATE workbench_sequence_assets SET bundle_bytes=1');self.d.db.commit()
        with patch.object(self.w.sequences,'asset',side_effect=AssertionError('must not load')):
            with self.assertRaises(WorkbenchError):projection.review(self.w,self.row['id'],self.body())

    def test_shared_verification_corrupt_hash_truncation_zip_metadata_and_output_cap_atomic(self):
        with patch.object(projection,'REVIEW_MAX_RESPONSE',100):
            before=self.state()
            with self.assertRaises(WorkbenchError):projection.review(self.w,self.row['id'],self.body())
            self.assertEqual(self.state(),before)
        original=copy.deepcopy(self.row['sequence']);original.pop('bundle_bytes')
        metadata=copy.deepcopy(original);metadata['frame_index'][1]['carrier_stamp']['version']='01'
        self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(metadata),));self.d.db.commit()
        before=self.state()
        with self.assertRaises(WorkbenchError):projection.review(self.w,self.row['id'],self.body())
        self.assertEqual(self.state(),before)
        self.d.db.execute('UPDATE workbench_sequence_assets SET metadata_json=?',(encode(original),));self.d.db.commit()
        for mode in ('hash','truncated','compressed','axis','stamp','nonfinite'):
            raw=self.raw;run=self.run
            if mode in ('axis','stamp','nonfinite'):
                frames=copy.deepcopy(self.frames)
                if mode=='axis':frames[1]['fields']['velocity_y']=frames[1]['fields']['velocity_y'][:-1]
                if mode=='stamp':frames[1]['carrier_stamp']['version']='01'
                if mode=='nonfinite':frames[1]['fields']['velocity_y'][0]=float('inf')
                raw=b''.join(json.dumps(f,allow_nan=True).encode()+b'\n' for f in frames)
                manifest=json.loads(run);manifest.update(frames_bytes=len(raw),frames_sha256=hashlib.sha256(raw).hexdigest());run=json.dumps(manifest).encode()
            if mode=='truncated':raw=raw[:-9]
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED if mode=='compressed' else zipfile.ZIP_STORED) as z:z.writestr('run.json',run);z.writestr('frames.jsonl',raw)
            data=output.getvalue()
            self.d.db.execute('UPDATE workbench_sequence_assets SET bundle=?,bundle_bytes=?',(data,len(data)))
            self.d.db.execute('UPDATE workbench_records SET content_hash=? WHERE id=?',('0'*64 if mode=='hash' else hashlib.sha256(data).hexdigest(),self.row['id']));self.d.db.commit()
            before=self.state()
            with self.assertRaises(WorkbenchError):projection.review(self.w,self.row['id'],self.body())
            self.assertEqual(self.state(),before)

    def test_readonly_rollback_on_lazy_owner_mutation_success_and_failure(self):
        original=self.w.sequences.asset;before=self.state()
        def lazy(row):
            self.d.db.execute("UPDATE workbench_records SET name='must roll back'")
            return original(row)
        with patch.object(self.w.sequences,'asset',side_effect=lazy):projection.review(self.w,self.row['id'],self.body())
        self.assertEqual(self.state(),before)
        with patch.object(self.w.sequences,'asset',side_effect=lazy),patch.object(projection,'REVIEW_MAX_RESPONSE',1):
            with self.assertRaises(WorkbenchError):projection.review(self.w,self.row['id'],self.body())
        self.assertEqual(self.state(),before)

    def test_actual_http_strict_four_kib_request_and_128_kib_raw_response(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.d));self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.shutdown)
        url=f'http://127.0.0.1:{server.server_port}/api/workbench/sequence-review/{self.row["id"]}'
        before=self.state()
        for raw in (b'{',b'{}',b'{"revision":1,"revision":1}',b'x'*4097,b'{"revision":NaN}'):
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json'}))
            self.assertEqual(error.exception.code,400)
        with urllib.request.urlopen(urllib.request.Request(url,data=encode(self.body()).encode(),headers={'Content-Type':'application/json'})) as response:
            raw=response.read();self.assertLessEqual(len(raw),projection.REVIEW_MAX_RESPONSE);self.assertEqual(len(json.loads(raw)['frames']),9)
        self.assertEqual(self.state(),before)
