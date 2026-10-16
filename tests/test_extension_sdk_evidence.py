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

    def test_canonical_digest_matches_host_utf8_and_preserves_ascii_bytes(self):
        ascii_value = {'field_id': 'initial', 'payload_sha256': 'a'*64}
        ascii_raw = json.dumps(ascii_value, sort_keys=True, separators=(',', ':'),
                               ensure_ascii=True, allow_nan=False).encode()
        self.assertEqual(sdk.canonical(ascii_value), ascii_raw)
        value = {'label': 'café', 'units': 'µm'}
        self.assertEqual(sdk.canonical(value), b'{"label":"caf\xc3\xa9","units":"\xc2\xb5m"}')
        for value in (ascii_value, value):
            self.assertEqual(sdk.canonical(value), host.canonical(value))
            self.assertEqual(sdk.digest(value), host.digest(value))
        for value in ({'number': float('nan')}, {'label': '\ud800'}):
            with self.subTest(value=repr(value)), self.assertRaises(sdk.EvidenceError):
                sdk.canonical(value)

    def test_host_resolved_unicode_task_units_and_blob_projection_agree(self):
        # A new structural declaration exercises real host validation/context
        # construction. This fixture never admits or claims a numerical Run.
        policy = self.definition['model_evidence']
        policy['task']['definition']['label'] = 'Champ café'
        for port in policy['task']['definition']['ports']:
            port['units'] = 'µm'
        for field in policy['fields']:
            field['gauge_policy']['field_units'] = 'µm'
            gauge_sha = host.digest(field['gauge_policy'])
            for descriptor in [*field['contract']['inputs'], field['contract']['output']]:
                descriptor.update(units='µm', gauge_policy_sha256=gauge_sha)
        policy['output_policy'].update(units='µm', gauge_policy_sha256=gauge_sha)
        policy['metric_definitions'][0]['units'] = 'µm²'
        self.model['material']['task']['sha256'] = host.digest(policy['task']['definition'])
        self.model['material']['output_policy']['sha256'] = host.digest(policy['output_policy'])
        execution = self.run['material']
        static = host.resolve(policy, self.model, execution)
        self.composition['material']['executable_sha256'] = host.digest(execution)
        context = host.context(static, self.composition['ref'], self.run['id'], self.run['request_sha256'])
        self.context_raw = host.canonical(context)
        self.run.update(extension_context=context, material_sha256=host.digest(execution))
        self.run['spec']['model_evidence_context'].update(
            bytes=len(self.context_raw), sha256=hashlib.sha256(self.context_raw).hexdigest())
        self.assertEqual(host.validate_context(context, self.run, self.composition, static), context)
        self.assertEqual(sdk.load_context(self.context_raw), context)
        self.assertIn('Champ café'.encode(), self.context_raw)
        self.assertIn('µm'.encode(), self.context_raw)
        self.assertEqual(sdk.digest(policy['task']['definition']), static['task']['sha256'])
        self.produce()
        blobs = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.run['artifacts'] = [dict(name=row['path'], role=row['role'], bytes=len(blobs[row['path']]),
            sha256=hashlib.sha256(blobs[row['path']]).hexdigest(), media_type='application/octet-stream')
            for row in self.definition['outputs']]
        public = host.query(host.verify(self.output, self.run, context))
        self.assertEqual(sdk.validate_projection(public, self.context_raw, blobs)['numerical'], 'not_evaluated')
        ref = public['manifest']['metric_definitions']
        self.assertIn('µm²'.encode(), blobs[ref['name']])
        self.assertEqual(ref['sha256'], hashlib.sha256(blobs[ref['name']]).hexdigest())
        self.assertEqual(ref['bytes'], len(blobs[ref['name']]))
        self.assertEqual(public['metric_definition_hashes'],
                         {item['id']: sdk.digest(item) for item in policy['metric_definitions']})

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
