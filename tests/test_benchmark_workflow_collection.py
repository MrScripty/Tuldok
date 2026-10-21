"""The facade cost witness requires actual complete, private, whole-byte outputs."""
import copy
from pathlib import Path
import tempfile
import unittest

from benchmark_lab_workflow import sha
from benchmark_workflow_collection import verify_outputs


class FacadeReportingTests(unittest.TestCase):
    def test_complete_receipt_requires_independent_whole_bytes_and_no_provisional_files(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name); path = directory/'one.bin'
            raw = b'exact neutral output'; path.write_bytes(raw); path.chmod(0o600)
            expected = [{'name': path.name, 'bytes': len(raw), 'sha256': sha(raw)}]
            manifest = {'source': {'run_id': 'a'*32}, 'items': expected}
            receipt = {'state': 'complete', 'manifest': manifest, 'items': [{'name': path.name,
                'state': 'verified', 'receipt': dict(expected[0], run_id='a'*32, output=str(path),
                    verification='whole_sha256_verified')}]}
            self.assertEqual(verify_outputs(receipt, manifest, expected, directory), expected)
            path.write_bytes(b'changed output')
            with self.assertRaisesRegex(AssertionError, 'whole bytes'):
                verify_outputs(receipt, manifest, expected, directory)
            path.write_bytes(raw); (directory/'.provisional').write_bytes(b'')
            with self.assertRaisesRegex(AssertionError, 'provisional'):
                verify_outputs(receipt, manifest, expected, directory)

    def test_partial_receipt_or_wrong_attached_ref_never_counts_as_success(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name); path = directory/'one.bin'; path.write_bytes(b'x'); path.chmod(0o600)
            expected = [{'name': path.name, 'bytes': 1, 'sha256': sha(b'x')}]
            ref = {'run_id': 'a'*32, 'sha256': 'b'*64}
            manifest = {'source': {'ref': ref}, 'items': expected}
            receipt = {'state': 'partial', 'manifest': manifest, 'items': []}
            with self.assertRaisesRegex(AssertionError, 'partial'):
                verify_outputs(receipt, manifest, expected, directory)
            receipt.update(state='complete', items=[{'name': path.name, 'state': 'verified',
                'receipt': dict(expected[0], run_id='a'*32, output=str(path),
                    verification='whole_sha256_verified', result_ref=copy.deepcopy(ref))}])
            self.assertEqual(verify_outputs(receipt, manifest, expected, directory), expected)
            receipt['items'][0]['receipt']['result_ref']['sha256'] = 'c'*64
            with self.assertRaisesRegex(AssertionError, 'whole bytes'):
                verify_outputs(receipt, manifest, expected, directory)
