"""Representative host-context construction; no admitted or numerically accepted Run."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tuldok_extension_sdk import evidence as sdk
import extension_evidence as host
from test_extension_field_evidence import authored_fixture, npy

ROOT = Path(__file__).resolve().parents[1]


class SDKEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); original = self.root / 'original'; original.mkdir()
        self.definition, self.model, self.composition, self.run, self.original_writer = authored_fixture(original)
        self.context_raw = host.canonical(self.run['extension_context'])
        self.output = self.root / 'sdk'; self.output.mkdir()
        self.original = original

    def produce(self):
        writer = sdk.Evidence(self.output, self.context_raw)
        for name in ('transform.npy', 'input-initial.npy', 'reference.npy'):
            shutil.copyfile(self.original/name, self.output/name)
        writer.transform('transform.npy')
        for point in (16, 32, 48, 64):
            for prefix in ('weights', 'prediction'):
                shutil.copyfile(self.original/f'{prefix}-{point}.npy', self.output/f'{prefix}-{point}.npy')
            writer.checkpoint(point, dict(optimizer_update=point, epoch=None, fit_pass=None, physical_time=None, wall_elapsed_ms=point), f'weights-{point}.npy', {'reference_mse': 0})
        writer.finish()
        writer.write('diagnostics.json', {'scope': 'synthetic structural state, no training'})
        return writer

    def test_used_a_interface_emits_exact_existing_d2_bytes_and_host_accepts_structure(self):
        writer = self.produce()
        for original in self.original.iterdir():
            self.assertEqual((self.output/original.name).read_bytes(), original.read_bytes(), original.name)
        verified = host.verify(self.output, self.run, self.run['extension_context'])
        self.assertEqual(verified['state'], 'verified')
        self.assertIn('numerical_acceptance_is_separate', verified['validation'])
        public = host.query(verified)
        blobs = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assertEqual(sdk.validate_projection(public, self.context_raw, blobs)['numerical'], 'not_evaluated')
        blobs['weights-16.npy'] += b'X'
        with self.assertRaises(sdk.EvidenceError): sdk.validate_projection(public, self.context_raw, blobs)
        self.assertEqual(len(writer.entries), 4)
        self.assertTrue(writer.inventory())
        for blob in writer.inventory():
            raw = (self.output/blob['name']).read_bytes()
            self.assertEqual((blob['bytes'], blob['sha256']), (len(raw), hashlib.sha256(raw).hexdigest()))

    def test_context_is_exact_bounded_identity_projection_with_typed_failures(self):
        self.assertEqual(sdk.load_context(self.context_raw), self.run['extension_context'])
        for raw in (self.context_raw+b'\n', b'{"x":1,"x":2}', b'{}', b'[]', b'{"x":NaN}', b' '*(sdk.CONTEXT_LIMIT+1)):
            with self.subTest(raw=raw[:30]), self.assertRaises(sdk.EvidenceError):
                sdk.load_context(raw)
        for mutation in (lambda c:c['static']['task'].update(sha256='f'*64),
                         lambda c:c['static']['profile'].update(model_sha256='f'*64),
                         lambda c:c['composition'].update(catalog_id='a'*32),
                         lambda c:c['static']['probe'].update(split='test'),
                         lambda c:c['static']['profile']['capture'].update(interval=True)):
            value = copy.deepcopy(self.run['extension_context']); mutation(value)
            with self.subTest(mutation=mutation), self.assertRaises(sdk.EvidenceError):
                sdk.load_context(sdk.canonical(value))

    def test_cadence_bool_clocks_missing_metric_and_changed_blob_fail(self):
        writer = sdk.Evidence(self.output, self.context_raw)
        (self.output/'transform.npy').write_bytes(npy([0, 1], [2])); writer.transform('transform.npy')
        (self.output/'weights-16.npy').write_bytes(npy([0, 0], [2]))
        observed = dict(optimizer_update=16, epoch=None, fit_pass=None, physical_time=None, wall_elapsed_ms=1)
        for point, clocks, metrics in ((32, observed, {'reference_mse': 0}), (16, dict(observed, wall_elapsed_ms=True), {'reference_mse': 0}), (16, observed, {})):
            with self.assertRaises(sdk.EvidenceError):
                writer.checkpoint(point, clocks, 'weights-16.npy', metrics)
        with self.assertRaises(sdk.EvidenceError): writer.finish()
        writer.blob('weights-16.npy'); (self.output/'weights-16.npy').write_bytes(npy([1, 0], [2]))
        with self.assertRaisesRegex(sdk.EvidenceError, 'changed'): writer.blob('weights-16.npy')
        for name in ('../escape', '/absolute', 'custody-receipt.json'):
            with self.assertRaises(sdk.EvidenceError): writer.write(name, {})

    def test_existing_stdout_progress_is_bounded_and_contains_no_inferred_clock(self):
        value = json.loads(sdk.progress('fit', 16, 64, {'reference_mse': .2}))
        self.assertEqual(value, dict(format='tuldok_progress_v1', stage='fit', completed=16, total=64, metrics={'reference_mse': .2}))
        for args in [('fit', True, 64), ('fit', 65, 64), ('fit', 1, 1000001), ('bad stage', 1, 1), ('fit', 1, 1, {'x': float('nan')})]:
            with self.subTest(args=args), self.assertRaises(sdk.EvidenceError): sdk.progress(*args)

    def test_copied_helper_uses_only_stdlib_and_never_starts_host_or_runtime(self):
        kit = self.root/'kit'; (kit/'tuldok_extension_sdk').mkdir(parents=True)
        for name in ('__init__.py', 'evidence.py'):
            shutil.copyfile(ROOT/'tuldok_extension_sdk'/name, kit/'tuldok_extension_sdk'/name)
        (kit/'context.json').write_bytes(self.context_raw)
        code = """import sys
from pathlib import Path
from tuldok_extension_sdk.evidence import load_context,progress
load_context(Path('context.json').read_bytes());progress('fit',1,2)
assert not any(name in sys.modules for name in ('app','metadata','psycopg','torch','numpy','extension_evidence','extension_contract'))
print('stdlib-only copied helper')
"""
        completed = subprocess.run([sys.executable, '-E', '-B', '-c', code], cwd=kit, capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), 'stdlib-only copied helper')
