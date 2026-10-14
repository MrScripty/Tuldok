"""Stateless segment contract; authored neutral processes, no model qualification.

These tests are authored during P6 source preparation. Execution is deferred
until the integration owner releases the active numerical benchmark gate.
"""
import base64
import hashlib
import json
import os
import uuid
from unittest.mock import patch

from access import AccessError
from test_external_runs import ExternalCase
from workbench import WorkbenchError


class ArtifactSegmentTests(ExternalCase):
    def complete(self, *, empty=False):
        if empty:
            source = b'import pathlib,sys\npathlib.Path(sys.argv[3],"result.txt").write_bytes(b"")\n'
            self.definition['sources'][0]['sha256'] = hashlib.sha256(source).hexdigest()
            self.definition_raw = json.dumps(self.definition).encode()
            self.manifest['id'] = uuid.uuid4().hex
            self.manifest['recipes'][0]['sha256'] = hashlib.sha256(self.definition_raw).hexdigest()
            for name, raw in {'recipe.py':source,'recipe.json':self.definition_raw,
                              'project.json':json.dumps(self.manifest).encode()}.items():
                (self.project_path/name).write_bytes(raw)
            with self.owner.bound(self.dataset):
                self.dataset.projects.open({'root':'fixture','manifest_path':'project.json'})
                self.graph = self.dataset.pipelines.create_external(self.graph_body())
                self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])
        with self.owner.bound(self.dataset):
            run = self.dataset.runs.submit_external(self.body())
        self.await_state(run['id'], {'completed'})
        with self.owner.bound(self.dataset):
            run = self.dataset.runs._load(run['id'])
        return run, run['artifacts'][0]

    def segment(self, run, item, offset=0, maximum=7):
        with self.owner.bound(self.dataset):
            return self.dataset.runs.artifact_segment(run['id'], item['name'], {
                'expected_sha256':item['sha256'],'offset':offset,'max_bytes':maximum})

    def test_reassembly_hash_offsets_exact_fields_and_no_whole_payload_scan(self):
        run, item = self.complete()
        offset, whole = 0, hashlib.sha256()
        target = (self.dataset.runs.path/run['id']/item['name']).stat()
        payload_reads = []
        original = os.pread
        def bounded(fd, count, position):
            info = os.fstat(fd)
            if (info.st_dev,info.st_ino) == (target.st_dev,target.st_ino):
                payload_reads.append(count)
            return original(fd, count, position)
        with patch.object(self.dataset.runs, '_copy_verified', side_effect=AssertionError('Whole-file verification forbidden for segments')), patch('runs.os.pread', side_effect=bounded):
            while True:
                value = self.segment(run,item,offset)
                self.assertEqual(set(value), {'run_id','name','expected_sha256','total_bytes','media_type',
                    'offset','bytes','next_offset','eof','segment_sha256','data_base64','verification'})
                raw = base64.b64decode(value['data_base64'],validate=True)
                self.assertEqual(value['segment_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(value['verification'],'segment_read_whole_hash_unverified')
                self.assertEqual(value['offset'],offset)
                self.assertEqual(value['bytes'],len(raw))
                self.assertEqual(value['next_offset'],offset+len(raw))
                self.assertEqual(value['expected_sha256'],item['sha256'])
                self.assertEqual(value['total_bytes'],item['bytes'])
                whole.update(raw); offset=value['next_offset']
                if value['eof']:
                    break
        self.assertEqual(offset,item['bytes'])
        self.assertEqual(whole.hexdigest(),item['sha256'])
        self.assertLessEqual(max(payload_reads),7)
        self.assertEqual(sum(payload_reads),item['bytes'])
        eof=self.segment(run,item,item['bytes'])
        self.assertTrue(eof['eof']); self.assertEqual(eof['bytes'],0)
        self.assertEqual(eof['segment_sha256'],hashlib.sha256(b'').hexdigest())

    def test_empty_artifact_and_request_refusals(self):
        run,item=self.complete(empty=True)
        value=self.segment(run,item)
        self.assertEqual(value['data_base64'],'')
        self.assertEqual(value['next_offset'],0); self.assertTrue(value['eof'])
        good={'expected_sha256':item['sha256'],'offset':0,'max_bytes':8*1024*1024}
        invalid=[dict(good,offset=True),dict(good,offset=-1),dict(good,offset=1),
                 dict(good,max_bytes=False),dict(good,max_bytes=0),dict(good,max_bytes=8*1024*1024+1),
                 dict(good,expected_sha256='A'*64),dict(good,extra='ignored'),{}]
        with self.owner.bound(self.dataset):
            for body in invalid:
                with self.subTest(body=body),self.assertRaises(WorkbenchError):
                    self.dataset.runs.artifact_segment(run['id'],item['name'],body)
            for name in ('../result.txt','/etc/passwd','custody-receipt.json','unknown.bin'):
                with self.subTest(name=name),self.assertRaises(WorkbenchError):
                    self.dataset.runs.artifact_segment(run['id'],name,good)
            with self.assertRaises(WorkbenchError) as error:
                self.dataset.runs.artifact_segment(run['id'],item['name'],dict(good,expected_sha256='0'*64))
            self.assertEqual(error.exception.code,'conflict')

    def test_same_size_mutation_is_explicitly_unverified_and_whole_digest_fails(self):
        run,item=self.complete()
        first=self.segment(run,item,0,1)
        path=self.dataset.runs.path/run['id']/item['name']
        original=path.read_bytes()
        self.assertGreater(len(original),1)
        path.write_bytes(original[:1]+bytes(byte^255 for byte in original[1:]))
        remainder=self.segment(run,item,1,8*1024*1024)
        received=base64.b64decode(first['data_base64'])+base64.b64decode(remainder['data_base64'])
        self.assertNotEqual(hashlib.sha256(received).hexdigest(),item['sha256'])
        self.assertEqual(remainder['segment_sha256'],hashlib.sha256(received[1:]).hexdigest())
        with self.owner.bound(self.dataset):
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.artifact(run['id'],item['name'])
            with self.assertRaises(WorkbenchError):
                with self.dataset.runs.open_artifact(run['id'],item['name']):
                    pass

    def test_revocation_between_calls_and_cross_catalog_cannot_read(self):
        run,item=self.complete()
        body={'expected_sha256':item['sha256'],'offset':0,'max_bytes':1}
        with self.assertRaises(AccessError):
            self.dataset.runs.artifact_segment(run['id'],item['name'],body)
        with self.dataset.access.bind(self.agent['token']):
            first=self.dataset.runs.artifact_segment(run['id'],item['name'],body)
        with self.owner.bound(self.dataset):
            self.dataset.access.revoke(self.agent['identity']['credential_id'])
        with self.assertRaises(AccessError):
            with self.dataset.access.bind(self.agent['token']):
                self.dataset.runs.artifact_segment(run['id'],item['name'],dict(body,offset=first['next_offset']))
        # A session from another real catalog cannot authorize this owner.
        from app import Dataset
        from auth_helpers import ExplicitOwnerFixture
        other=Dataset(self.path/'other-catalog')
        try:
            actor=ExplicitOwnerFixture.bootstrap(other)
            with actor.bound(other), self.assertRaises(AccessError):
                self.dataset.runs.artifact_segment(run['id'],item['name'],body)
        finally:
            other.close()

    def test_in_read_mutation_nonregular_growth_and_incomplete_run_refused(self):
        run,item=self.complete()
        path=self.dataset.runs.path/run['id']/item['name']
        original=path.read_bytes(); info=path.stat(); pread=os.pread
        def mutate(fd,count,offset):
            raw=pread(fd,count,offset)
            current=os.fstat(fd)
            if (current.st_dev,current.st_ino)==(info.st_dev,info.st_ino):
                path.write_bytes(b'x'*len(original))
            return raw
        with patch('runs.os.pread',side_effect=mutate), self.assertRaises(WorkbenchError):
            self.segment(run,item)
        path.write_bytes(original+b'x')
        with self.assertRaises(WorkbenchError): self.segment(run,item)
        path.unlink(); path.symlink_to('/dev/zero')
        with self.assertRaises(WorkbenchError): self.segment(run,item)
        path.unlink(); os.mkfifo(path)
        with self.assertRaises(WorkbenchError): self.segment(run,item)
        path.unlink(); path.write_bytes(original)
        queued=self.queued(self.body(approval=self.approve()))
        with self.owner.bound(self.dataset), self.assertRaises(WorkbenchError):
            self.dataset.runs.artifact_segment(queued['id'],item['name'],{
                'expected_sha256':item['sha256'],'offset':0,'max_bytes':1})
