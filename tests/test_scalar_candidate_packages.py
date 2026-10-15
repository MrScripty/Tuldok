"""Authored scalar package boundary tests; no admitted producer/consumer claim."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import candidate_packages as p
import extension_evidence as evidence
import recipe_contract
from test_extension_field_evidence import npy
from test_candidate_packages import fixture as classifier_fixture
import test_candidate_packages as classifier_tests

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples/extensions/field-surrogate/v2'


def fixture():
    """Only the author's JSON writer runs; every numeric state is authored test data."""
    definition = recipe_contract.decode_definition((SOURCE / 'recipe.json').read_bytes()); policy = definition['model_evidence']
    catalog = 'd' * 32; run_id = 'a' * 32
    task = {'kind': 'task', 'catalog_id': catalog, 'id': policy['task']['id'], 'revision': policy['task']['revision'],
            'sha256': evidence.digest(policy['task']['definition'])}
    sources = {name: (SOURCE / name).read_bytes() for name in ('producer.py', 'evidence_writer.py', 'task.json', 'extension.json', 'NOTICE.txt', 'recipe.json')}
    published = {'material': {'format': 'model_material_v1', 'catalog_id': catalog, 'task': task,
        'source_closure': [{'import_path': name, 'blob': p.blob('source-' + str(i), raw)} for i, (name, raw) in enumerate(sources.items())]}}
    for name, key in (('specification', 'model_specification'), ('preprocessing_policy', 'preprocessing_policy'), ('output_policy', 'output_policy')):
        published[name] = evidence.canonical(policy[key]); published['material'][name] = p.blob(name + '.json', published[name])
    model = {'ref': {'kind': 'model', 'catalog_id': catalog, 'id': 'b' * 32, 'revision': 1, 'sha256': p.sha(p.encoded(published['material']))},
             'material': published['material']}
    raw_fixture = (SOURCE / 'fixture.json').read_bytes(); authored = p.decode(raw_fixture)
    execution = {'catalog_id': catalog, 'recipe': definition, 'inputs': {'fixture': {'project_id': 'c' * 32,
        'manifest_sha256': 'e' * 64, 'reference_id': 'fixture', 'path': 'fixture.json', 'measured_sha256': p.sha(raw_fixture)}},
        'parameters': recipe_contract.validate_parameters(definition, {})}
    static = evidence.resolve(policy, model, execution)
    context = evidence.context(static, {'kind': 'recipe_material', 'catalog_id': catalog, 'id': 'f' * 64, 'sha256': 'f' * 64}, run_id, '1' * 64)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        spec = importlib.util.spec_from_file_location('scalar_package_authored_json_writer', SOURCE / 'evidence_writer.py')
        writer = importlib.util.module_from_spec(spec); spec.loader.exec_module(writer)
        instance = writer.Evidence(root, evidence.canonical(context))
        (root / 'transform.npy').write_bytes(npy([3, 2], [2])); instance.transform('transform.npy')
        member = next(row for row in authored['cases'] if row['id'] == authored['probe_member_id'])
        (root / 'input-initial.npy').write_bytes(npy(member['initial'], [4, 4, 4]))
        (root / 'reference.npy').write_bytes(npy(member['target'], [4, 4, 4]))
        for point in (16, 32, 48, 64):
            (root / f'weights-{point}.npy').write_bytes(npy([2, -.5], [2]))
            # Independently authored exact arithmetic: 2*((x-3)/2)-.5 == x-3.5.
            (root / f'prediction-{point}.npy').write_bytes(npy([x - 3.5 for x in member['initial']], [4, 4, 4]))
            instance.checkpoint(point, {'optimizer_update': point, 'epoch': None, 'fit_pass': None, 'physical_time': None, 'wall_elapsed_ms': point},
                f'weights-{point}.npy', {'reference_mse': 0})
        instance.finish()
        artifacts = {path.name: path.read_bytes() for path in root.iterdir()}
    checkpoint = instance.entries[-1]['checkpoint']
    decision = {'format': 'candidate_v1', 'id': '2' * 32, 'study_id': '3' * 32, 'trial_id': '4' * 32,
        'run_id': run_id, 'checkpoint_sha256': checkpoint['sha256'], 'evaluation_sha256': p.sha(artifacts['model-evidence.json']),
        'policy': {}, 'decision': 'diagnostic', 'limitations': ['Authored contract fixture only.']}
    candidate = {'ref': {'kind': 'candidate', 'catalog_id': catalog, 'id': decision['id'], 'sha256': p.sha(p.encoded(decision))},
        'candidate': decision, 'run_id': run_id, 'checkpoint': checkpoint}
    runtime = p.decode(classifier_fixture()[1]['runtime.json']); runtime['snapshot']['catalog_id'] = catalog
    return p.scalar_a_closure(candidate, artifacts, sources, runtime, published)


class ScalarCandidatePackageTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.files = fixture()

    def test_exact_field_closure_inspection_does_not_import_author_source(self):
        with patch('importlib.util.spec_from_file_location', side_effect=AssertionError('No captured code during inspection')):
            raw = p.create_package(self.manifest, self.files)
            manifest, files = p.inspect_package(raw, p.sha(raw))
        self.assertEqual(set(manifest), p.MANIFEST_FIELDS)
        self.assertNotIn('metrics.json', files)
        self.assertEqual(p.decode(files['candidate-decision.json'])['evaluation_sha256'], p.sha(files['model-evidence.json']))
        self.assertEqual({item['name'] for item in manifest['sources']},
            {'producer.py', 'evidence_writer.py', 'task.json', 'extension.json', 'NOTICE.txt', 'recipe.json', 'infer.py', 'recipe_process.py'})

    def test_authored_exact_adapter_reconstruction_uses_bound_native_files(self):
        member = p.decode(self.files['probe.json'])['members'][0]
        self.assertNotEqual(member['input_sha256'], p.sha(self.files['input-initial.npy']))
        receipt = p._infer_scalar_a(self.manifest, self.files, '5' * 64, '6' * 64)
        self.assertTrue(receipt['verified']); self.assertEqual(receipt['format'], 'fresh_field_inference_verification_v1')
        self.assertLessEqual(receipt['outputs'][0]['max_absolute_difference'], 1e-10)
        self.assertEqual(receipt['numerical_acceptance'], 'not_evaluated')

    def test_missing_weights_transform_source_contract_or_notice_refuses(self):
        for name in ('weights-64.npy', 'transform.npy', 'input-initial.npy', 'reference.npy',
                     'producer.py', 'recipe.json', 'infer.py', 'inference-contract.json', 'inference-NOTICE.txt'):
            with self.subTest(name=name), self.assertRaises(p.PackageError):
                p.create_package(self.manifest, {key: value for key, value in self.files.items() if key != name})

    def test_wrong_selected_weights_or_expected_prediction_never_verifies(self):
        for name in ('weights-64.npy', 'prediction-64.npy'):
            files = dict(self.files)
            files[name] = npy([0, 0], [2]) if name.startswith('weights') else npy([0] * 64, [4, 4, 4])
            with self.subTest(name=name), self.assertRaises(p.PackageError):
                p._infer_scalar_a(self.manifest, files, '5' * 64, '6' * 64)

    def test_native_dtype_shape_boolean_dimensions_and_nonfinite_refuse(self):
        for raw, shape in ((npy([0, 1], [True, 2]), (1, 2)), (npy([float('inf'), 1], [2]), (2,)),
                           (npy([0, 1], [2]) + b'x', (2,))):
            with self.subTest(raw=raw[:80]), self.assertRaises(p.PackageError):
                p._scalar_npy(raw, shape)

    def test_unknown_rights_deny_redistribution(self):
        raw = p.create_package(self.manifest, self.files)
        with self.assertRaises(p.PackageError) as error:
            p.inspect_package(raw, p.sha(raw), distribution='redistribution')
        self.assertEqual(error.exception.code, 'unsupported')

    def test_rehashed_context_cannot_change_gauge_geometry_stage_or_profile(self):
        for key in ('geometry', 'gauge', 'stage', 'profile'):
            manifest = copy.deepcopy(self.manifest); files = dict(self.files)
            context = p.decode(files['execution-context.json'])
            if key == 'geometry':
                # Python False ==0 must not weaken the frozen typed geometry.
                context['static']['policy']['fields'][0]['geometry']['origin_xyz'][0] = False
            elif key == 'gauge':
                context['static']['policy']['fields'][0]['gauge_policy']['operation'] = 'subtract_mean'
            elif key == 'stage':
                context['static']['policy']['fields'][0]['contract']['output']['stage'] = 'before_training'
            else:
                context['static']['profile']['definition']['revision'] = True
            raw = p.encoded(context)
            replacement = p.blob('execution-context.json', raw)
            classifier_tests.PackageTests.replace_blob(self, manifest, files, 'execution-context.json', raw)
            task = p.decode(files[manifest['task']['name']]); task['context'] = replacement
            classifier_tests.PackageTests.replace_blob(self, manifest, files, manifest['task']['name'], p.encoded(task))
            lineage = p.decode(files['lineage.json'])
            for source in lineage['sources']:
                if source['artifact_name'] == 'execution-context.json':
                    source['sha256'] = replacement['sha256']
            classifier_tests.PackageTests.replace_blob(self, manifest, files, 'lineage.json', p.encoded(lineage))
            with self.subTest(key=key), self.assertRaises(p.PackageError):
                p.create_package(manifest, files)

    def test_unregistered_task_profile_refuses_with_typed_unsupported(self):
        manifest = copy.deepcopy(self.manifest); files = dict(self.files)
        task = p.decode(files[manifest['task']['name']]); task['format'] = 'generic_untrusted_model'
        classifier_tests.PackageTests.replace_blob(self, manifest, files, manifest['task']['name'], p.encoded(task))
        with self.assertRaises(p.PackageError) as error:
            p.create_package(manifest, files)
        self.assertEqual(error.exception.code, 'unsupported')


if __name__ == '__main__':
    unittest.main()
