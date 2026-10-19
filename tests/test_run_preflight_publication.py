"""Pre-compute field capacity proofs; no publication recovery or science claim."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import extension_evidence
import recipe_contract
from workbench import WorkbenchError


PACKAGE = Path(__file__).resolve().parents[1] / 'examples/extensions/field-surrogate/v2'


class FieldOutputPreflightTests(unittest.TestCase):
    def setUp(self):
        self.definition = json.loads((PACKAGE / 'recipe.json').read_bytes())

    def decode(self):
        with patch('subprocess.Popen', side_effect=AssertionError('Preflight must not launch a process')):
            return recipe_contract.decode_definition(json.dumps(self.definition).encode())

    def refuse(self, reason):
        with self.assertRaises(WorkbenchError) as caught:
            self.decode()
        self.assertEqual(caught.exception.code, 'unsupported')
        self.assertEqual(str(caught.exception), 'Extension evidence: ' + reason)

    def output(self, name):
        return next(item for item in self.definition['outputs'] if item['path'] == name)

    def test_existing_valid_definition_is_unchanged_and_executes_nothing(self):
        self.assertEqual(self.decode(), self.definition)

    def test_prediction_payload_must_fit_its_own_file_bound(self):
        self.output('prediction-16.npy')['max_bytes'] = 511  # 4*4*4 float64 values need 512 bytes before headers.
        self.refuse('Required field artifact prediction-16.npy cannot fit its declared output bound.')

    def test_reference_payload_must_fit_its_own_file_bound(self):
        self.output('reference.npy')['max_bytes'] = 511
        self.refuse('Required field artifact reference.npy cannot fit its declared output bound.')

    def test_probe_input_payload_must_fit_its_own_file_bound(self):
        self.output('input-initial.npy')['max_bytes'] = 511
        self.refuse('Required field artifact input-initial.npy cannot fit its declared output bound.')

    def test_aggregate_counts_unique_required_arrays(self):
        # One input, one shared reference, four predictions: six payloads, not nine.
        self.definition['model_evidence']['profile']['limits']['total_output_bytes'] = 6 * 512 - 1
        self.refuse('Required field payloads cannot fit the admitted aggregate output bound.')

    def test_shared_reference_is_not_charged_once_per_checkpoint(self):
        self.definition['model_evidence']['profile']['limits']['total_output_bytes'] = 6 * 512
        self.assertEqual(self.decode(), self.definition)

    def test_declared_maxima_are_not_claimed_as_required_output_sizes(self):
        self.definition['model_evidence']['profile']['limits']['total_output_bytes'] = 8192
        self.assertGreater(sum(item['max_bytes'] for item in self.definition['outputs']), 8192)
        self.assertEqual(self.decode(), self.definition)

    def test_probe_face_array_must_fit_the_profile_shard_bound(self):
        field = self.definition['model_evidence']['fields'][0]
        field['geometry']['shape_xyz'] = [1, 64, 64]
        field['contract']['output']['shape_zyx'] = [64, 64, 1]
        field['contract']['inputs'][0].update(centering='face_x', shape_zyx=[64, 64, 2])
        for item in self.definition['outputs']:
            item['max_bytes'] = 65536
        self.definition['model_evidence']['profile']['limits']['shard_bytes'] = 36864
        self.refuse('Required field artifact input-initial.npy cannot fit the admitted shard bound.')

    def test_existing_writer_verifier_and_cold_read_still_round_trip(self):
        from test_extension_field_evidence import authored_fixture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _definition, _model, _composition, run, _writer = authored_fixture(root)
            verified = extension_evidence.verify(root, run, run['extension_context'])
            self.assertEqual(extension_evidence.query(verified)['state'], 'verified')
            # Reopen through the actual retained-byte reader, without the writer instance.
            cold = extension_evidence.verify(Path(directory), copy.deepcopy(run), copy.deepcopy(run['extension_context']))
            self.assertEqual(extension_evidence.query(cold), extension_evidence.query(verified))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the extension validator')
class BoundOutputPreflightIntegrationTests(unittest.TestCase):
    def test_impossible_declaration_refuses_before_graph_run_or_grant_effect(self):
        import test_extension_bindings as fixtures
        fixture = fixtures.BoundExtensionRecipeTests('runTest')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.recipe['outputs'][next(i for i, row in enumerate(fixture.recipe['outputs'])
                                      if row['path'] == 'prediction-16.npy')]['max_bytes'] = 511
        fixture._rebind_definitions()
        dataset = fixture.dataset
        before = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                  for table in ('workspace_graphs', 'workspace_runs', 'access_execution_grants',
                                'access_execution_consumptions', 'model_attempt_reservations')}
        body = {'name': 'Impossible field output', **fixture.selector, 'inputs': {
            'fixture': {'reference_id': 'fixture', 'expected_sha256':
                        fixture.recipe['model_evidence']['probe']['candidates'][0]['input_sha256']}}}
        with patch('subprocess.Popen', side_effect=AssertionError('Rejected declaration launched compute')):
            with self.assertRaises(WorkbenchError) as caught:
                dataset.pipelines.create_external(body)
        self.assertEqual(caught.exception.code, 'unsupported')
        self.assertEqual(str(caught.exception),
                         'Extension evidence: Required field artifact prediction-16.npy cannot fit its declared output bound.')
        after = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in before}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
