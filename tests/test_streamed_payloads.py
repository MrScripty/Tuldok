"""Large-file custody, bounded reads and mutation controls; no model execution."""
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from capture_payloads import FilePayload, CHUNK_BYTES, copy_payload, payload_digest
from model_definitions import blob, read_owned_blob
from projects import Projects
import recipe_process
from workbench import WorkbenchError


class StreamedPayloadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root/'input.bin'
        digest = hashlib.sha256()
        chunk = bytes(range(256))*4096
        with self.path.open('wb') as handle:
            for _ in range(41):
                handle.write(chunk)
                digest.update(chunk)
        self.expected = digest.hexdigest()

    def payload(self):
        with self.path.open('rb') as handle:
            raw = FilePayload(handle.fileno(), self.path.stat().st_size, expected_sha256=self.expected)
        self.addCleanup(raw.close)
        return raw

    def test_hash_and_copy_above_old_file_cap_are_bounded_and_exact(self):
        read = os.pread
        sizes = []
        def observed(fd, size, offset):
            sizes.append(size)
            return read(fd, size, offset)
        with patch('capture_payloads.os.pread', side_effect=observed):
            raw = self.payload()
            self.assertEqual(payload_digest(raw), self.expected)
            with (self.root/'copy.bin').open('wb') as destination:
                copy_payload(raw, destination)
        self.assertGreater(len(sizes), 3)
        self.assertLessEqual(max(sizes), CHUNK_BYTES)
        item = blob(raw, 'capture-0000.bin')
        self.assertEqual(item['bytes'], self.path.stat().st_size)
        recipe_process.verify_streamed_capture(dict(path=str(self.root/'copy.bin'),
            bytes=item['bytes'], sha256=self.expected))

    def test_same_size_rewrite_with_restored_mtime_is_rejected(self):
        raw = self.payload()
        before = self.path.stat()
        with self.path.open('r+b') as handle:
            handle.write(b'changed')
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(WorkbenchError): payload_digest(raw)

    def test_truncation_and_wrong_hash_are_rejected(self):
        raw = self.payload()
        with self.path.open('r+b') as handle: handle.truncate(1)
        with self.assertRaises(WorkbenchError): payload_digest(raw)
        with self.path.open('rb') as handle, self.assertRaises(WorkbenchError):
            FilePayload(handle.fileno(), 100, expected_sha256='0'*64)

    def test_project_capture_retains_path_and_allows_unrelated_publication(self):
        projects = Projects(SimpleNamespace(access=None, db=None, lock=None), {'fixture':self.root})
        self.addCleanup(projects.close)
        saved = dict(root='fixture', root_identity=projects.roots['fixture'][1],
            manifest_sha256='a'*64, manifest=dict(data=[dict(id='sample', path='input.bin', sha256=self.expected)]))
        with patch.object(projects, '_snapshot_saved', return_value=(saved,b'')):
            raw, receipt = projects._read_data_reference('b'*32, 'sample', self.expected,
                self.path.stat().st_size, extensions=True, stream=True)
        self.addCleanup(raw.close)
        self.assertIsInstance(raw, FilePayload)
        self.assertEqual(receipt['measured_sha256'], self.expected)
        (self.root/'independent').mkdir()
        self.assertEqual(raw.digest(), self.expected)
        self.path.rename(self.root/'previous.bin')
        self.path.symlink_to(self.root/'previous.bin')
        with self.assertRaises(WorkbenchError): raw.digest()

    def test_owned_blob_streaming_and_replaced_file_are_checked(self):
        owner = self.root/'materials'
        directory = owner/('a'*64)
        directory.mkdir(parents=True)
        target = directory/'capture-0000.bin'
        self.path.rename(target)
        item = dict(name=target.name, bytes=target.stat().st_size, sha256=self.expected,
            media_type='application/octet-stream')
        raw = read_owned_blob(owner,'a'*64,item,item['bytes'],stream=True)
        self.addCleanup(raw.close)
        self.assertIsInstance(raw,FilePayload)
        (owner/('b'*64)).mkdir()
        self.assertEqual(raw.digest(),self.expected)
        target.rename(directory/'previous.bin')
        target.write_bytes(b'x')
        with self.assertRaises(WorkbenchError): raw.digest()

    def test_process_verification_rejects_symlink_parent_and_changed_content(self):
        item = dict(path=str(self.path),bytes=self.path.stat().st_size,sha256=self.expected)
        recipe_process.verify_streamed_capture(item)
        alias = self.root/'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(recipe_process.ProcessError):
            recipe_process.verify_streamed_capture(dict(item,path=str(alias/'input.bin')))
        with self.path.open('r+b') as handle: handle.write(b'changed')
        with self.assertRaises(recipe_process.ProcessError): recipe_process.verify_streamed_capture(item)

    def test_process_verification_honors_cancellation_within_large_file(self):
        calls = []
        class Cancelled(Exception): pass
        def checkpoint():
            calls.append(True)
            if len(calls)==2: raise Cancelled()
        with self.assertRaises(Cancelled):
            recipe_process.verify_streamed_capture(dict(path=str(self.path),
                bytes=self.path.stat().st_size,sha256=self.expected),checkpoint=checkpoint)
        self.assertEqual(len(calls),2)

    def test_small_owned_shards_are_also_file_backed_in_streamed_mode(self):
        owner=self.root/'small-materials';directory=owner/('a'*64)
        directory.mkdir(parents=True)
        target=directory/'capture-0000.bin';target.write_bytes(b'small shard')
        item=blob(b'small shard',target.name)
        raw=read_owned_blob(owner,'a'*64,item,1024,stream=True)
        self.addCleanup(raw.close)
        self.assertIsInstance(raw,FilePayload)
        self.assertEqual(payload_digest(raw),item['sha256'])


if __name__=='__main__': unittest.main()
