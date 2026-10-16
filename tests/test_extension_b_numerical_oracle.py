"""Synthetic analytic B witnesses only; no producer, optimizer or Run evidence."""
import ast
from dataclasses import replace
import math
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import unittest

import extension_b_numerical_oracle as oracle


class AnalyticBWitnesses(unittest.TestCase):
    def test_nonorthogonal_features_couple_the_two_weights(self):
        p = oracle.Population(0.0, 1.0, 0.0, 1.0, 0.5, 4)
        for t, expected in [(0, (0, 0, 0)), (1, (.12, .09, .05)), (2, (.207, .15, .09))]:
            oracle.verify_values(oracle.closed_form_state(p, .1, t), expected)
        negative = oracle.Population(0.0, 1.0, 0.0, 1.0, -0.5, 4)
        oracle.verify_values(oracle.closed_form_state(negative, .1, 1), (.08, -.01, .05))
        # Independent hand-derived eigenvector projections, not optimizer replay.
        for t in (32, 64):
            a, b, c = oracle.closed_form_state(p, .1, t)
            oracle.close(a+b-.7, -.7*.7**t, 'Positive covariance eigenmode')
            oracle.close(a-b-.3, -.3*.9**t, 'Negative covariance eigenmode')
            oracle.close(c-.25, -.25*.8**t, 'Intercept mode')

    def test_zero_covariance_matches_separate_feature_decay_with_nonzero_initialization(self):
        p = oracle.Population(2, 3, -1, 2, 0, 4)
        initial = (.125, -.25, .5); optimum = (1.5, .4, 1.05)
        for t in (0, 1, 32, 64):
            expected = tuple(target+(start-target)*.8**t for start, target in zip(initial, optimum, strict=True))
            oracle.verify_values(oracle.closed_form_state(p, .1, t, initial), expected)

    def test_singular_covariance_preserves_null_mode_and_edge_learning_rate_can_oscillate(self):
        initial = (.1, -.3, .2)
        for r, first in [(1, (1, .6, .25)), (-1, (0, -.2, .25))]:
            p = oracle.Population(0, 1, 0, 1, r, 4)
            oracle.verify_values(oracle.closed_form_state(p, .5, 1, initial), first)
            oracle.verify_values(oracle.closed_form_state(p, .5, 2, initial), (*initial[:2], .25))
            a, b, _ = oracle.closed_form_state(p, .1, 64, initial)
            oracle.close(a-r*b, initial[0]-r*initial[1], 'Unidentifiable null mode')

    def test_population_is_train_only_population_std_and_correlated(self):
        x = [-1, -1, 1, 1]; u = [-1, 1, -1, 1]
        s = [.5*a+math.sqrt(.75)*b for a, b in zip(x, u, strict=True)]
        p = oracle.training_population(x, s)
        for value, expected in [(p.mean_initial, 0), (p.std_initial, 1), (p.mean_source, 0), (p.std_source, 1), (p.correlation, .5)]:
            oracle.close(value, expected, 'Train population')
        self.assertEqual(p.count, 4)
        self.assertEqual(oracle.verify_population(p, x, s), p)
        leaked = oracle.training_population(x+[1000], s+[-1000])
        with self.assertRaises(oracle.OracleError):oracle.verify_population(leaked, x, s)
        # Equal count alone must not make normalization from another population pass.
        with self.assertRaises(oracle.OracleError):oracle.verify_population(replace(p, mean_source=.1), x, s)

    def test_raw_and_corrected_fields_have_distinct_semantics_and_retallied_mse(self):
        initial = [-2, 0, 2, 4]; source = [1, -1, 2, 0]; mask = [False, 1.0, 0, True]
        p = oracle.training_population(initial, source)
        target = oracle.reference_fields(initial, source, mask, shape=(1, 2, 2))
        oracle.verify_values(target.raw, [-.55, .05, 1.65, 2.25])
        oracle.verify_values(target.corrected, [-.55, 0, 1.65, 0])
        state = (.5*p.std_initial, .2*p.std_source, .5*p.mean_initial+.2*p.mean_source+.25)
        actual = oracle.reconstruct(initial, source, mask, p, state, shape=(1, 2, 2))
        oracle.verify_values(actual.raw, target.raw);oracle.verify_values(actual.corrected, target.corrected)
        self.assertEqual(oracle.retallied_mse([1, 2], [0, 0]), 2.5)
        self.assertGreater(oracle.retallied_mse(target.corrected, target.raw), 0)
        self.assertEqual(actual.corrected[1], 0.0)

    def test_invalid_numeric_domains_shapes_and_masks_refuse(self):
        p = oracle.Population(0, 1, 0, 1, .5, 4)
        for rate in (0, -.1, .50001, True, float('nan'), float('inf')):
            with self.subTest(rate=rate),self.assertRaises(oracle.OracleError):oracle.closed_form_state(p, rate, 64)
        for updates in (-1, True, 1.0, oracle.MAX_UPDATES+1):
            with self.subTest(updates=updates),self.assertRaises(oracle.OracleError):oracle.closed_form_state(p, .1, updates)
        for bad in (replace(p, correlation=1.01), replace(p, std_source=0), replace(p, mean_initial=float('nan')), replace(p, count=True)):
            with self.assertRaises(oracle.OracleError):oracle.closed_form_state(bad, .1, 64)
        for mask in ([0, .5], [0, float('nan')], [0, float('inf')], [0, '1'], [0]):
            with self.assertRaises(oracle.OracleError):oracle.reference_fields([0, 1], [1, 0], mask, shape=(2,))
        for shape in ((1, 1), (True, 2), (2.0,), [2], (0,), (2, 1, 1, 1)):
            with self.assertRaises(oracle.OracleError):oracle.reference_fields([0, 1], [1, 0], [0, 1], shape=shape)
        for args in (([1, 1], [0, 1]), ([0, 1], [2, 2]), ([0, float('nan')], [0, 1]), ([0], [0, 1])):
            with self.assertRaises(oracle.OracleError):oracle.training_population(*args)
        with self.assertRaises(oracle.OracleError):oracle.retallied_mse([1e308], [-1e308])
        with self.assertRaises(oracle.OracleError):oracle.verify_values([0], [1])

    def test_module_imports_are_standard_library_only(self):
        tree = ast.parse(Path(oracle.__file__).read_text())
        imports = {node.names[0].name if isinstance(node, ast.Import) else node.module
                   for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))}
        self.assertEqual(imports, {'ast', 'dataclasses', 'hashlib', 'math', 'struct'})
        # A full repository suite may already have imported numerical modules.
        # Check the kernel's own cold import in an isolated stdlib subprocess.
        code = "import sys;sys.path.insert(0,sys.argv[1]);import extension_b_numerical_oracle;assert not any(n in sys.modules for n in ('app','projects','psycopg','numpy','torch'))"
        subprocess.run([sys.executable, '-I', '-B', '-c', code, str(Path(oracle.__file__).parent)],
                       check=True, capture_output=True, text=True, timeout=10)


class LiteralNPYWitnesses(unittest.TestCase):
    @staticmethod
    def encode(values, shape=(2,), *, dtype='<f8', fortran=False, version=1):
        header = repr(dict(descr=dtype, fortran_order=fortran, shape=shape)).encode('ascii')
        width = 2 if version==1 else 4
        header += b' ' * (-(8+width+len(header)+1) % 16) + b'\n'
        return b'\x93NUMPY'+bytes([version, 0])+len(header).to_bytes(width,'little')+header+struct.pack('<'+str(len(values))+'d',*values)

    def test_valid_v1_v2_arrays_decode_without_numpy_or_pickle(self):
        for version in (1, 2):
            raw=self.encode([.125, -.25],version=version)
            self.assertEqual(oracle.npy(raw,(2,)),(.125,-.25))
            self.assertEqual(oracle.decode_npy(raw,[2]),dict(values=(.125,-.25),shape_zyx=[2],
                payload_sha256=hashlib.sha256(struct.pack('<2d',.125,-.25)).hexdigest()))
        for shape in ([True,2], [2.0], [], [2,1,1,1]):
            with self.assertRaises(oracle.OracleError):oracle.decode_npy(self.encode([0,1]),shape)

    def test_malformed_object_fortran_oversized_truncated_and_nonfinite_arrays_refuse(self):
        normal = self.encode([0, 1])
        bad = [normal[:-1], normal+b'x', self.encode([0, 1], dtype='|O'), self.encode([0, 1], dtype='<f4'),
               self.encode([0, 1], fortran=True), self.encode([0, 1], shape=(True, 2)),
               self.encode([0, 1], shape=(2.0,)), self.encode([0, 1], shape=(1000000000,)),
               self.encode([0, float('nan')]), normal+b'x'*oracle.ARRAY_LIMIT,
               b'\x93NUMPY\x01\x00'+(65535).to_bytes(2,'little')+b'{}']
        for raw in bad:
            with self.subTest(size=len(raw)),self.assertRaises(oracle.OracleError):oracle.npy(raw,(2,))


if __name__ == '__main__':unittest.main()
