"""Strict native custody and real PostgreSQL project-to-field inspection."""
from auth_helpers import bind_owner
import copy
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import math
import os
import struct
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid
import warnings
import zipfile

from app import Dataset, make_handler
import scientific_fields as science
from workbench import WorkbenchError
from qualify_scientific_fields import neutral_bundle, bundle
import test_workspace_metadata


def fixture():
    return neutral_bundle()


def unpack(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        members = {name: archive.read(name) for name in archive.namelist() if name != 'manifest.json'}
    return manifest, members


def receipt(raw):
    return dict(project_id='a'*32, manifest_sha256='b'*64, reference_id='source',
                path='source.zip', measured_sha256=hashlib.sha256(raw).hexdigest())


class ScientificParser(unittest.TestCase):
    def test_lossless_placement_time_and_protected_identity(self):
        raw = fixture(); parsed = science.parse_bundle(raw)
        self.assertEqual((parsed['frame_count'], parsed['field_count']), (2, 4))
        self.assertEqual(parsed['manifest']['frames'][0]['time'], '0.12500')
        value, members = unpack(raw)
        value['fields'][0]['label'] = 'Renamed only'
        value['family']['id'] = 'other declaration'
        value['frames'][0]['time'] = '0.125'
        renamed = science.parse_bundle(bundle(value, members))
        self.assertEqual(parsed['first_observed_state_sha256'], renamed['first_observed_state_sha256'])
        self.assertNotEqual(parsed['protected_groups'][-1], renamed['protected_groups'][-1])
        value['grid']['origin_xyz'][0] += 1
        self.assertNotEqual(parsed['first_observed_state_sha256'], science.parse_bundle(bundle(value, members))['first_observed_state_sha256'])

    def test_strict_manifest_and_inventory(self):
        original, members = unpack(fixture())
        changes = [lambda m: m.update(extra=1), lambda m: m.update(schema_version=True),
                   lambda m: m['grid']['origin_xyz'].__setitem__(0, 10**400),
                   lambda m: m['grid']['orientation'][0].__setitem__(0, .1),
                   lambda m: m['frames'][1].update(time='0.125000'),
                   lambda m: m['frames'][0].update(time='NaN'),
                   lambda m: m['fields'][0].update(dtype='>f8'),
                   lambda m: m['fields'][0].update(label='bad\ud800'),
                   lambda m: m['frames'][0]['arrays'][0].update(path='../outside'),
                   lambda m: m['frames'][0]['arrays'][0].update(bytes=True),
                   lambda m: m['frames'][0]['arrays'][0].update(sha256='0'*64)]
        for change in changes:
            value = copy.deepcopy(original); change(value)
            with self.subTest(value=str(value)[:100]), self.assertRaises((WorkbenchError, UnicodeEncodeError)):
                science.parse_bundle(bundle(value, members))
        with self.assertRaises(WorkbenchError):
            science.parse_bundle(bundle(original, dict(members, extra=b'x')))
        with self.assertRaises(WorkbenchError):
            science.text('bad\ud800', 160, 'Label')
        with self.assertRaises(WorkbenchError):
            science.decode(b'{"a":1,"a":2}')
        with self.assertRaises(WorkbenchError):
            science.decode(b'['*2000+b']'*2000)

    def test_npy_finite_shape_endian_and_header_boundaries(self):
        value, members = unpack(fixture())
        field = value['fields'][0]; raw = next(iter(members.values()))
        payload, shape = science.npy_payload(raw, field, value['grid'])
        self.assertEqual(shape, [4,2,3])
        self.assertEqual(struct.unpack_from('<d', payload)[0], -0.0)
        self.assertEqual(math.copysign(1, struct.unpack_from('<d', payload)[0]), -1)
        bad = [raw+b'x', raw[:-1], raw[:6]+b'\x02\x00'+raw[8:], raw.replace(b"'<f8'", b"'>f8'"),
               raw[:-8]+struct.pack('<d',float('nan')),
               raw.replace(b'(4, 2, 3)', b'(4, 2, 4)'), raw[:8]+struct.pack('<H',4097)+raw[10:]]
        for item in bad:
            with self.subTest(size=len(item)), self.assertRaises(WorkbenchError):
                science.npy_payload(item, field, value['grid'])

    def test_zip_refuses_compression_duplicate_special_and_trailing(self):
        value, members = unpack(fixture())
        for mode in ('compressed','duplicate','symlink'):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(value), compress_type=zipfile.ZIP_DEFLATED if mode=='compressed' else zipfile.ZIP_STORED)
                for name, raw in members.items():
                    info = zipfile.ZipInfo(name)
                    if mode=='symlink': info.external_attr = 0o120777 << 16
                    archive.writestr(info,raw)
                if mode=='duplicate':
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore', UserWarning)
                        archive.writestr('manifest.json', b'{}')
            with self.subTest(mode=mode), self.assertRaises(WorkbenchError): science.parse_bundle(stream.getvalue())
        with self.assertRaises(WorkbenchError): science.parse_bundle(fixture()+b'extra')


class ScientificStorage(unittest.TestCase):
    setUp = test_workspace_metadata.WorkspaceMetadata.setUp
    cleanup_schemas = test_workspace_metadata.WorkspaceMetadata.cleanup_schemas

    def dataset(self, roots=None):
        result = Dataset(self.root/'catalog', project_roots=roots)
        self.actor = bind_owner(self, result)
        self.addCleanup(result.close)
        return result

    def test_real_import_slice_review_reopen_and_exact_download(self):
        dataset = self.dataset(); owner = dataset.workbench.scientific; raw = fixture()
        row = owner.admit(raw, {}, receipt(raw))
        self.assertTrue(row['source_available'])
        self.assertEqual(owner.asset(row), (raw,'application/zip'))
        for axis in 'xyz':
            result = owner.inspect(row['id'], 1, 'scalar', axis, 1)
            self.assertEqual(result['time'], '0.250000')
            self.assertEqual(result['stage'], 'observed scalar stage')
        result = owner.inspect(row['id'], 0, 'scalar', 'z', 0)
        self.assertEqual(result['physical_origin'], [9,-3.75,8.5])
        self.assertEqual(result['physical_row_step'], [-2,0,0])
        self.assertEqual(result['physical_column_step'], [0,.5,0])
        self.assertEqual(result['values'][1][2], 12+2**-45)
        face = owner.inspect(row['id'], 0, 'face_x', 'z', 0)
        self.assertEqual(face['physical_origin'], [9,-4,8.5])
        with self.assertRaises(WorkbenchError): owner.admit(raw, {}, receipt(raw))
        with self.assertRaises(WorkbenchError): dataset.workbench.save(row['id'],dict(row,groups=[]))
        row = dataset.workbench.save(row['id'],dict(row,review='human_reviewed',annotation={'note':'Reviewed whole sequence, no physical validity claim.'}))
        self.assertEqual(row['revision'],2)
        dataset.close(); reopened = self.dataset()
        self.assertEqual(reopened.workbench.asset(row['id'])[0],raw)

    def test_atomic_failure_changed_source_and_special_file(self):
        dataset = self.dataset(); owner = dataset.workbench.scientific; raw = fixture()
        with patch.object(dataset.workbench, '_history', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError): owner.admit(raw, {}, receipt(raw))
        self.assertFalse(list(owner.path.glob('*/source.zip')))
        self.assertEqual(dataset.db.execute("SELECT count(*) FROM workbench_records WHERE kind='field_sequence'").fetchone()[0],0)
        row = owner.admit(raw, {}, receipt(raw)); path = owner.path/row['id']/'source.zip'
        path.write_bytes(raw[:-1]+b'x')
        self.assertFalse(dataset.workbench._get(row['id'])['source_available'])
        with self.assertRaises(WorkbenchError): owner.asset(row)
        path.unlink(); os.mkfifo(path)
        self.assertFalse(owner.metadata(row['id'],row['provenance'])[1])
        path.unlink()

    def test_http_selected_project_import_and_inspection(self):
        external = self.root/'external'; external.mkdir(); raw=fixture()
        (external/'source.zip').write_bytes(raw)
        project_id=uuid.uuid4().hex
        manifest=dict(schema_version=1,id=project_id,name='Observed fields',data=[dict(id='fields',label='Captured bundle',path='source.zip')],recipes=[],evidence=[],requirements=[])
        (external/'project.json').write_text(json.dumps(manifest))
        dataset=self.dataset({'fixture':external})
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(dataset)); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_address[1])
        def request(path,body=None):
            req=self.actor.request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response: return json.load(response)
        request('/api/workspace/projects',dict(root='fixture',manifest_path='project.json'))
        route=f'/api/workspace/projects/{project_id}/import-data/fields'
        with self.assertRaises(urllib.error.HTTPError) as error: request(route,dict(expected_sha256='0'*64))
        self.assertEqual(error.exception.code,409)
        row=request(route,dict(expected_sha256=hashlib.sha256(raw).hexdigest()))
        result=request(f"/api/workbench/records/{row['id']}/scientific?frame=1&field=face_y&axis=x&index=2")
        self.assertEqual(result['shape_zyx'],[4,3,3]); self.assertEqual(result['time'],'0.250000')
        with self.assertRaises(urllib.error.HTTPError): request(f"/api/workbench/records/{row['id']}/scientific?frame=0&frame=1")
        self.assertEqual((external/'source.zip').read_bytes(),raw)
