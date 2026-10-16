"""Authored inference contract checks; no real producer/fresh-package acceptance."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PACKAGE = Path(__file__).resolve().parents[1] / 'examples/extensions/field-surrogate/inference-v1'
SPEC = importlib.util.spec_from_file_location('scalar_a_inference_only', PACKAGE / 'infer.py')
INFER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INFER)


def npy(values, shape, *, dtype='<f8', fortran=False, version=1):
    """Author test bytes directly, independently of the adapter writer."""
    start = 10 if version == 1 else 12
    header = repr({'descr': dtype, 'fortran_order': fortran, 'shape': shape}).encode('ascii')
    header += b' '*((-(start+len(header)+1)) % 16) + b'\n'
    width = '<H' if version == 1 else '<I'
    return b'\x93NUMPY' + bytes((version, 0)) + struct.pack(width, len(header)) + header + struct.pack('<' + str(len(values)) + 'd', *values)


def output_values(raw):
    """Independent fixed-output observation, without adapter decoding."""
    assert raw[:8] == b'\x93NUMPY\x01\x00'
    end = 10 + struct.unpack('<H', raw[8:10])[0]
    header = ast.literal_eval(raw[10:end].decode('ascii').strip())
    assert header == {'descr': '<f8', 'fortran_order': False, 'shape': (4, 4, 4)}
    return struct.unpack('<64d', raw[end:])


class ExtensionInferenceContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((PACKAGE / 'contract.json').read_bytes())
        self.initial = npy(list(range(64)), (4, 4, 4))
        self.weights = npy([2, -.5], (2,))
        self.transform = npy([3, 2], (2,))

    def request(self, *, initial=None, weights=None, transform=None):
        values = {'initial': self.initial if initial is None else initial,
                  'weights': self.weights if weights is None else weights,
                  'transform': self.transform if transform is None else transform}
        return {'format': 'scalar_affine_inference_request_v1', 'policy': copy.deepcopy(self.contract['policy']),
                'sha256': {key: hashlib.sha256(raw).hexdigest() for key, raw in values.items()}}

    def test_positive_formula_and_native_order_for_both_npy_versions(self):
        # Independently authored exact arithmetic: 2*((x-3)/2)-.5 == x-3.5.
        for version in (1, 2):
            initial = npy(list(range(64)), (4, 4, 4), version=version)
            raw = INFER.predict(initial, self.weights, self.transform, self.request(initial=initial))
            self.assertEqual(output_values(raw), tuple(value-3.5 for value in range(64)))

    def test_contract_source_notice_imports_and_exact_task_profile_freeze(self):
        INFER.validate_contract(self.contract)
        self.assertEqual(self.contract['policy']['task'], {
            'id': 'example.scalar-a:task', 'revision': 2,
            'definition_sha256': 'a0f932d2416bbbe2606a8ec9a9f72d6ea5b073f54446da897c4b3a2b3b07ed45'})
        self.assertEqual(self.contract['policy']['profile']['revision'], 2)
        self.assertEqual(self.contract['policy']['field_id'], 'raw')
        tree = ast.parse((PACKAGE / 'infer.py').read_bytes())
        actual_imports = sorted({node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} |
                                {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names})
        self.assertEqual(actual_imports, self.contract['imports'])
        self.assertEqual([item['path'] for item in self.contract['sources']], ['infer.py'])
        self.assertEqual([item['path'] for item in self.contract['notices']], ['NOTICE.txt'])
        self.assertNotIn('contract.json', [item['path'] for item in self.contract['sources']])

    def test_missing_or_wrong_selected_state_refuses_before_output(self):
        request = self.request()
        for role in ('initial', 'weights', 'transform'):
            values = {'initial': self.initial, 'weights': self.weights, 'transform': self.transform}
            values[role] = None
            with self.subTest(role=role), self.assertRaisesRegex(INFER.InferenceError, 'selected binding'):
                INFER.predict(values['initial'], values['weights'], values['transform'], request)
        changed_weights = npy([3, -.5], (2,))
        with self.assertRaisesRegex(INFER.InferenceError, 'weights bytes differ'):
            INFER.predict(self.initial, changed_weights, self.transform, request)
        changed_transform = npy([30, 2], (2,))
        with self.assertRaisesRegex(INFER.InferenceError, 'transform bytes differ'):
            INFER.predict(self.initial, self.weights, changed_transform, request)

    def test_invalid_order_dtype_shape_and_pickle_header_refuse_with_valid_hashes(self):
        cases = [npy(list(range(64)), (4, 4, 4), fortran=True),
                 npy(list(range(64)), (4, 4, 4), dtype='<f4'),
                 npy(list(range(64)), (4, 4, 4), dtype='|O'),
                 npy(list(range(64)), (8, 8, 1)),
                 npy(list(range(64)), (True, 8, 8)), self.initial+b'X']
        for raw in cases:
            with self.subTest(header=raw[:100]), self.assertRaises(INFER.InferenceError):
                INFER.predict(raw, self.weights, self.transform, self.request(initial=raw))
        for raw in (npy([2], (1,)), npy([2, -.5], (1, 2))):
            with self.assertRaisesRegex(INFER.InferenceError, 'shape differs'):
                INFER.predict(self.initial, raw, self.transform, self.request(weights=raw))

    def test_nonfinite_and_nonpositive_transform_and_overflow_refuse(self):
        for std in (0, -1, float('nan'), float('inf')):
            raw = npy([3, std], (2,))
            with self.subTest(std=std), self.assertRaises(INFER.InferenceError):
                INFER.predict(self.initial, self.weights, raw, self.request(transform=raw))
        for role in ('initial', 'weights'):
            raw = npy([float('nan')]*64, (4, 4, 4)) if role == 'initial' else npy([float('inf'), 0], (2,))
            values = {'initial': self.initial, 'weights': self.weights, 'transform': self.transform}
            values[role] = raw
            with self.subTest(role=role), self.assertRaisesRegex(INFER.InferenceError, 'finite'):
                INFER.predict(values['initial'], values['weights'], values['transform'], self.request(**{role: raw}))
        raw = npy([1e308, 0], (2,))
        with self.assertRaisesRegex(INFER.InferenceError, 'arithmetic is nonfinite'):
            INFER.predict(self.initial, raw, self.transform, self.request(weights=raw))

    def test_gauge_geometry_stage_units_and_profile_changes_refuse(self):
        changes = [lambda p: p['gauge_policy'].update(operation='subtract_mean'),
                   lambda p: p['geometry'].update(origin_xyz=[1, 0, 0]),
                   lambda p: p['geometry'].update(orientation=[[0, 1, 0], [1, 0, 0], [0, 0, 1]]),
                   lambda p: p['output_policy'].update(stage='other'),
                   lambda p: p['output_policy'].update(units='Pa'),
                   lambda p: p['profile'].update(revision=1),
                   lambda p: p['task'].update(revision=2.0),
                   lambda p: p['preprocessing_policy'].update(fit_scope='validation')]
        for change in changes:
            request = self.request(); change(request['policy'])
            with self.subTest(change=change), self.assertRaisesRegex(INFER.InferenceError, 'policy differs'):
                INFER.predict(self.initial, self.weights, self.transform, request)

    def test_contract_cannot_widen_tolerance_rights_source_or_runtime(self):
        changes = [lambda c: c['reconstruction'].update(absolute_tolerance=1),
                   lambda c: c['rights'].update(redistribution='allowed'),
                   lambda c: c['source_authority'].update(producer_sha256='0'*64),
                   lambda c: c['sources'][0].update(sha256='0'*64),
                   lambda c: c['adapter'].update(revision=True),
                   lambda c: c['runtime'].update(dependencies=['numpy'])]
        for change in changes:
            contract = copy.deepcopy(self.contract); change(contract)
            with self.subTest(change=change), self.assertRaises(INFER.InferenceError):
                INFER.validate_contract(contract)

    def test_strict_request_json_and_hash_roles_have_no_fallback(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":1e309}', b'{"a":NaN}', b'{"a":"\\ud800"}'):
            with self.subTest(raw=raw), self.assertRaises(INFER.InferenceError):
                INFER.decode_json(raw)
        for request in ([], dict(self.request(), extra=True), dict(self.request(), sha256={}),
                        dict(self.request(), sha256=dict(self.request()['sha256'], weights='A'*64))):
            with self.subTest(request=request), self.assertRaises(INFER.InferenceError):
                INFER.predict(self.initial, self.weights, self.transform, request)

    def test_function_cannot_skip_the_declared_runtime_version(self):
        with patch.object(INFER.sys, 'version_info', (3, 11)):
            with self.assertRaisesRegex(INFER.InferenceError, 'compatible CPython 3.12'):
                INFER.predict(self.initial, self.weights, self.transform, self.request())

    def test_cli_isolated_copy_needs_only_frozen_source_notice_contract_and_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('infer.py', 'contract.json', 'NOTICE.txt'):
                shutil.copyfile(PACKAGE/name, root/name)
            for name, raw in (('initial.npy', self.initial), ('weights.npy', self.weights), ('transform.npy', self.transform)):
                (root/name).write_bytes(raw)
            (root/'request.json').write_bytes(INFER.canonical(self.request()))
            command = [sys.executable, '-I', '-S', '-B', str(root/'infer.py'), '--contract', str(root/'contract.json'),
                       '--request', str(root/'request.json'), '--input', str(root/'initial.npy'),
                       '--weights', str(root/'weights.npy'), '--transform', str(root/'transform.npy'),
                       '--output', str(root/'prediction.npy')]
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output_values((root/'prediction.npy').read_bytes()), tuple(value-3.5 for value in range(64)))
            for name, raw in before.items():
                self.assertEqual((root/name).read_bytes(), raw)
            self.assertEqual(set(path.name for path in root.iterdir()), set(before) | {'prediction.npy'})
            repeated = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(repeated.stderr)['state'], 'invalid')
            (root/'prediction.npy').unlink(); (root/'weights.npy').unlink()
            missing = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(missing.returncode, 2)
            self.assertFalse((root/'prediction.npy').exists())

    def test_reader_refuses_links_and_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root/'input.npy'; path.write_bytes(self.initial)
            (root/'alias').symlink_to(path)
            with self.assertRaises(OSError):
                INFER.read_file(root/'alias', INFER.MAX_NPY_BYTES)
            os.link(path, root/'hardlink')
            with self.assertRaises(INFER.InferenceError):
                INFER.read_file(path, INFER.MAX_NPY_BYTES)
            os.mkfifo(root/'pipe')
            with self.assertRaises(INFER.InferenceError):
                INFER.read_file(root/'pipe', INFER.MAX_NPY_BYTES)


if __name__ == '__main__':
    unittest.main()
