"""Pure authoring nomination tests; no runtime probe, catalog or actual Run."""
import ast
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import prepare_extension_runtime_project as prepare

PROJECT = prepare.ROOT/'examples/extensions/field-surrogate/v2'
INFERENCE = prepare.ROOT/'examples/extensions/field-surrogate/inference-v1'


class RuntimeNominationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.destination = self.root/'new-runtime-qa'
        self.options = dict(expected_runtime_sha256=prepare.NOMINATED_RUNTIME,
            package_version='2.0.1', recipe_id='scalar-a-local-runtime-qa', recipe_version=1, inference_revision=2)

    def compile(self, **options):
        return prepare.prepare(PROJECT, INFERENCE, self.destination, **dict(self.options, **options))

    def read(self, path):
        return json.loads(path.read_bytes())

    def test_explicit_new_identity_and_all_source_hashes_compile_without_execution(self):
        before_project = prepare.pinned_files(PROJECT, prepare.PROJECT_FILES)
        before_inference = prepare.pinned_files(INFERENCE, prepare.INFERENCE_FILES)
        with patch('subprocess.Popen', side_effect=AssertionError('No runtime process')), \
                patch('psycopg.connect', side_effect=AssertionError('No catalog/database')):
            receipt = self.compile()
        self.assertEqual(prepare.pinned_files(PROJECT, prepare.PROJECT_FILES), before_project)
        self.assertEqual(prepare.pinned_files(INFERENCE, prepare.INFERENCE_FILES), before_inference)
        project = self.destination/'project'
        recipe = self.read(project/'recipe.json'); original = self.read(PROJECT/'recipe.json')
        extension = self.read(project/'extension.json')
        self.assertEqual(extension['package'], {'id': 'example.scalar-a', 'version': '2.0.1'})
        self.assertEqual(extension['runtime']['snapshot_sha256'], prepare.NOMINATED_RUNTIME)
        self.assertNotEqual(self.read(project/'project.json')['id'], self.read(PROJECT/'project.json')['id'])
        self.assertEqual((recipe['id'], recipe['version'], recipe['runtime_snapshot_sha256']),
                         ('scalar-a-local-runtime-qa', 1, prepare.NOMINATED_RUNTIME))
        for name in ('fixture.json', 'cold_oracle.py', 'producer.py', 'evidence_writer.py', 'task.json', 'NOTICE.txt'):
            self.assertEqual((project/name).read_bytes(), (PROJECT/name).read_bytes())
        policy = recipe['model_evidence']; old_policy = original['model_evidence']
        for key in ('model_specification', 'preprocessing_policy', 'output_policy', 'task', 'profile', 'fit_members', 'probe'):
            self.assertEqual(policy[key], old_policy[key])
        self.assertEqual(policy['profile']['revision'], 2)
        self.assertEqual(policy['fields'][0]['geometry'], old_policy['fields'][0]['geometry'])
        self.assertEqual(policy['fields'][0]['gauge_policy'], old_policy['fields'][0]['gauge_policy'])
        adapter = prepare.recipe_contract.digest(sorted(recipe['sources'], key=lambda item: item['path']))
        self.assertNotEqual(adapter, old_policy['adapter_sha256'])
        self.assertEqual(policy['adapter_sha256'], adapter)
        self.assertTrue(all(field['contract']['source_sha256'] == adapter for field in policy['fields']))
        self.assertTrue(all(metric['evaluator_sha256'] == adapter for metric in policy['metric_definitions']))
        self.assertEqual(receipt['qualification'], 'pending_actual_run_and_independent_oracle')
        self.assertIs(receipt['run_admitted'], False)
        self.assertIs(receipt['runtime_probe_performed'], False)
        self.assertEqual(receipt['original_runtime_snapshot_sha256'], prepare.ORIGINAL_RUNTIME)

    def test_new_inference_strictly_pins_nomination_and_preserves_original(self):
        receipt = self.compile()
        root = self.destination/'inference'
        original = self.destination/'original-inference-v1'
        for name, raw in prepare.pinned_files(INFERENCE, prepare.INFERENCE_FILES).items():
            self.assertEqual((original/name).read_bytes(), raw)
        module = prepare.inference_owner(root); contract = self.read(root/'contract.json')
        module['validate_contract'](contract)
        self.assertEqual(contract['adapter']['revision'], 2)
        self.assertNotEqual(prepare.sha((root/'contract.json').read_bytes()), prepare.INFERENCE_FILES['contract.json'])
        self.assertEqual(receipt['inference_contract_sha256'], prepare.sha((root/'contract.json').read_bytes()))
        authority = contract['source_authority']
        self.assertEqual(authority['recipe_sha256'], prepare.sha((self.destination/'project/recipe.json').read_bytes()))
        self.assertEqual(authority['extension_sha256'], prepare.sha((self.destination/'project/extension.json').read_bytes()))
        self.assertEqual(authority['runtime_nomination']['expected_runtime_snapshot_sha256'], prepare.NOMINATED_RUNTIME)
        with self.assertRaises(module['InferenceError']):
            module['validate_contract'](self.read(original/'contract.json'))
        wrong = copy.deepcopy(contract)
        wrong['source_authority']['runtime_nomination']['expected_runtime_snapshot_sha256'] = prepare.ORIGINAL_RUNTIME
        with self.assertRaisesRegex(module['InferenceError'], 'source_authority contract differs'):
            module['validate_contract'](wrong)
        # Formatting may change; numerical/reconstruction and parser ASTs cannot.
        def functions(path):
            return {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(path.read_bytes()).body
                    if isinstance(node, ast.FunctionDef)}
        old, new = functions(INFERENCE/'infer.py'), functions(root/'infer.py')
        for name in ('predict', 'read_npy', '_prediction_npy', 'read_file', 'decode_json'):
            self.assertEqual(new[name], old[name])

    def test_runtime_nomination_is_required_and_never_falls_back(self):
        for value in (None, prepare.ORIGINAL_RUNTIME, '0'*64, prepare.NOMINATED_RUNTIME.upper()):
            with self.subTest(runtime=value), self.assertRaisesRegex(prepare.PreparationError, 'Explicitly nominate'):
                self.compile(expected_runtime_sha256=value)
            self.assertFalse(self.destination.exists())

    def test_distinct_versions_and_new_output_are_required(self):
        for changes in ({'package_version': '2.0.0'}, {'recipe_id': 'scalar-a-evidence-v2'},
                        {'recipe_version': True}, {'recipe_version': 2}, {'inference_revision': 1}):
            with self.subTest(changes=changes), self.assertRaises(prepare.PreparationError):
                self.compile(**changes)
        self.destination.mkdir(); (self.destination/'keep').write_bytes(b'author data')
        with self.assertRaisesRegex(prepare.PreparationError, 'Destination must be new'):
            self.compile()
        self.assertEqual((self.destination/'keep').read_bytes(), b'author data')

    def test_modified_template_or_oracle_is_not_reinterpreted(self):
        project = self.root/'project-template'; shutil.copytree(PROJECT, project)
        for name in ('producer.py', 'cold_oracle.py', 'extension.json'):
            before = (project/name).read_bytes()
            (project/name).write_bytes(before+b'\n')
            with self.subTest(name=name), self.assertRaisesRegex(prepare.PreparationError, 'exact frozen'):
                prepare.prepare(project, INFERENCE, self.destination, **self.options)
            self.assertFalse(self.destination.exists())
            (project/name).write_bytes(before)
        inference = self.root/'inference-template'; shutil.copytree(INFERENCE, inference)
        (inference/'infer.py').write_bytes((inference/'infer.py').read_bytes()+b'\n')
        with self.assertRaisesRegex(prepare.PreparationError, 'exact frozen'):
            prepare.prepare(PROJECT, inference, self.destination, **self.options)

    def test_failed_owner_validation_never_publishes_partial_nomination(self):
        with patch.object(prepare, 'validate', return_value={'packages': [{'state': 'invalid'}]}):
            with self.assertRaisesRegex(prepare.PreparationError, 'declaration closure'):
                self.compile()
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
