"""Local author numerical/closed-package evidence only. No host or actual Run."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import unittest

import numpy as np
import cold_oracle as oracle
import producer

ROOT = Path(__file__).parent


class IndependentBNumericalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads((ROOT/'fixture.json').read_text())

    def test_numpy_updates_match_independent_stdlib_gradient_and_replay(self):
        transform, states = producer.fit(self.fixture)
        expected_transform, expected_states = oracle.trajectory(self.fixture)
        for actual, expected in zip(transform.flat, expected_transform):
            oracle.close(float(actual), expected, 'Train-only transform differs')
        case = self.fixture['cases'][-1]
        for point, weights in states:
            self.assertIn(point, (32, 64))
            for actual, expected in zip(weights, expected_states[point]):
                oracle.close(float(actual), expected, 'Independent gradient differs')
            raw, corrected = producer.infer(case['initial'], case['source'], case['boundary_mask'], transform, weights)
            expected = oracle.reconstruct([case[key] for key in ('initial', 'source', 'boundary_mask')], list(transform.flat), list(weights))
            for actual_field, expected_field in zip((raw, corrected), expected):
                for actual, target in zip(actual_field, expected_field):
                    oracle.close(float(actual), target, 'Independent reconstruction differs')
            self.assertTrue(np.all(corrected[np.asarray(case['boundary_mask'], dtype=bool)] == 0.))
            self.assertGreater(float(np.max(np.abs(raw-corrected))), .01)
            metrics = producer.evaluate(raw, corrected, case)
            self.assertEqual(set(metrics), {'raw_reference_mse', 'corrected_reference_mse'})

    def test_validation_values_never_fit_transform_or_weights(self):
        transform, states = producer.fit(self.fixture)
        changed = copy.deepcopy(self.fixture)
        case = changed['cases'][-1]
        case['initial'] = [x+1000 for x in case['initial']]
        case['source'] = [x-600 for x in case['source']]
        case['raw_target'] = [.5*x+.25+.2*s for x, s in zip(case['initial'], case['source'])]
        case['corrected_target'] = [0. if m else x for m, x in zip(case['boundary_mask'], case['raw_target'])]
        after_transform, after_states = producer.fit(changed)
        np.testing.assert_array_equal(transform, after_transform)
        for before, after in zip(states, after_states):
            self.assertEqual(before[0], after[0])
            np.testing.assert_array_equal(before[1], after[1])

    def test_missing_source_mask_and_nonbinary_mask_refuse_at_author_boundary(self):
        for field in ('source', 'boundary_mask'):
            changed = copy.deepcopy(self.fixture)
            del changed['cases'][0][field]
            with self.assertRaises(KeyError) as caught:
                producer.fit(changed)
            self.assertEqual(caught.exception.args, (field,))
        changed = copy.deepcopy(self.fixture)
        changed['cases'][0]['boundary_mask'][0] = .5
        with self.assertRaisesRegex(ValueError, '^B boundary_mask requires exact binary values$'):
            producer.fit(changed)

    def test_oracle_native_arrays_reject_wrong_dtype_order_shape_and_nonfinite(self):
        values = np.asarray(self.fixture['cases'][-1]['initial'], dtype='<f8').reshape(4, 4, 4)
        def encode(value):
            output = io.BytesIO()
            np.save(output, value, allow_pickle=False)
            return output.getvalue()
        self.assertEqual(tuple(values.flat), oracle.npy(encode(values), (4, 4, 4)))
        for changed in (values.astype('<f4'), np.asfortranarray(values), values.reshape(8, 8)):
            with self.assertRaisesRegex(oracle.OracleError, '^Expected exact little-endian float64 C-order shape$'):
                oracle.npy(encode(changed), (4, 4, 4))
        changed = values.copy()
        changed[0, 0, 0] = np.nan
        with self.assertRaisesRegex(oracle.OracleError, '^Nonfinite NPY payload$'):
            oracle.npy(encode(changed), (4, 4, 4))
        with self.assertRaisesRegex(oracle.OracleError, '^Truncated or trailing NPY payload$'):
            oracle.npy(encode(values)+struct.pack('<d', 0), (4, 4, 4))

    def test_source_closure_exact_five_roles_ports_stage_dataflow_and_frozen_oracle(self):
        extension = json.loads((ROOT/'extension.json').read_text())
        recipe = json.loads((ROOT/'recipe.json').read_text())
        project = json.loads((ROOT/'project.json').read_text())
        freeze = json.loads((ROOT/'oracle-freeze.json').read_text())
        sha = lambda name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for key, name in (('fixture_sha256', 'fixture.json'), ('oracle_sha256', 'cold_oracle.py')):
            self.assertEqual(freeze[key], sha(name))
        self.assertEqual(recipe['schema_version'], 3)
        self.assertEqual(recipe['format'], 'external_model_evidence_recipe_v2')
        self.assertNotIn('project_sha256', recipe['extension_selection'])
        self.assertEqual(len(recipe['outputs']), 26)
        self.assertEqual(recipe['runtime_snapshot_sha256'], extension['runtime']['snapshot_sha256'])
        self.assertLessEqual(sum(row['max_bytes'] for row in recipe['outputs']), extension['resources']['output_bytes'])
        for row in recipe['sources']:
            self.assertEqual(row['sha256'], sha(row['path']))
        for row in extension['sources']+extension['license']['notices']+extension['contributions']:
            self.assertEqual(row['sha256'], sha(row['path']))
            self.assertEqual(row['bytes'], (ROOT/row['path']).stat().st_size)
        for group in ('data', 'recipes', 'extensions'):
            for row in project[group]:
                self.assertEqual(row['sha256'], sha(row['path']))
        self.assertEqual(set(recipe['extension_selection']['selections']), {'task','model','trainer','evaluator','view'})
        task = json.loads((ROOT/'task.json').read_text())
        for role in ('model', 'trainer', 'evaluator'):
            definition = json.loads((ROOT/(role+'.json')).read_text())
            self.assertEqual(definition['ports'], task['ports'])
        trainer = json.loads((ROOT/'trainer.json').read_text())
        self.assertEqual(trainer['stages'], task['stages'])
        available = {port['id'] for port in task['ports'] if port['direction'] in ('input', 'target')}
        output_ports = {port['id'] for port in task['ports'] if port['direction'] == 'output'}
        for stage in task['stages']:
            self.assertLessEqual(set(stage['inputs']), available)
            self.assertLessEqual(set(stage['outputs']), output_ports)
            available.update(stage['outputs'])
        for field in recipe['model_evidence']['fields']:
            self.assertEqual({row['field_id'] for row in field['contract']['inputs']}, {'initial','source','boundary_mask'})
            output = field['contract']['output']
            self.assertTrue(any(stage['id'] == output['stage'] and output['field_id'] in stage['outputs'] for stage in task['stages']))


if __name__ == '__main__':
    unittest.main()
