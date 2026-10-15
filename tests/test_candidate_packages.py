"""Package closure/rights/custody negatives; numerical evidence uses the qualifier."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

import candidate_packages as packages


def fixture():
    """Authored byte contracts only; never claims model or inference qualification."""
    run_id = 'a' * 32
    transform = {'name': 'resize_rgb_tensor', 'version': 2, 'size': [32, 32], 'fit_scope': 'none', 'augmentation': False}
    fitted = {'format': 'fitted_transform_v1', 'fit_scope': 'none', 'statistics': []}
    weights = b'authored contract fixture; not Torch weights'
    probe_image = b'authored fixture; not a PNG'
    checkpoint = {'format': 'checkpoint_state_v1', 'run_id': run_id, 'model_sha256': 'b' * 64,
        'weights': packages.blob('weights-epoch-0001.pt', weights, 'application/octet-stream'),
        'fitted_transform_sha256': packages.sha(packages.encoded(fitted)),
        'clocks': {'epoch': 1, 'optimizer_update': 1, 'fit_pass': None, 'physical_time': None, 'wall_elapsed_ms': 1}}
    artifacts = {'checkpoint-epoch-0001.json': packages.encoded(checkpoint), 'weights-epoch-0001.pt': weights,
        'model-definition.json': packages.encoded({'format': 'tinycnn_definition_v2',
            'specification': {'template': 'tinycnn_v2', 'widths': [4, 4, 4], 'input_size': 32, 'head': 'linear'},
            'preprocessing_policy': transform, 'output_policy': {'kind': 'class_probabilities', 'class_order': 'frozen_vocabulary'},
            'parameters': {}}),
        'fitted-transform.json': packages.encoded(fitted),
        'metrics.json': packages.encoded({'class_vocabulary': [{'index': 0, 'label': 'a'}, {'index': 1, 'label': 'b'}],
            'class_to_idx': {'a': 0, 'b': 1}}),
        'probe.json': packages.encoded({'format': 'probe_v1', 'split': 'validation', 'members': [
            {'ordinal': 0, 'frozen_reference': {'id': 'c' * 32}, 'input_sha256': packages.sha(probe_image)}]}),
        'probes-epoch-0001.json': packages.encoded({'run_id': run_id, 'rows': [{'ordinal': 0, 'probabilities': [.25, .75]}],
            'checkpoint_sha256': packages.sha(packages.encoded(checkpoint)), 'probe_sha256': 'd' * 64})}
    source = b'# inert authored source fixture\n'
    model_definition = packages.decode(artifacts['model-definition.json'])
    published = {'material': {'format': 'model_material_v1',
        'source_closure': [{'import_path': 'image_training.py', 'blob': packages.blob('source-0000.bin', source)}]},
        **{key: packages.encoded(model_definition[key]) for key in ('specification', 'preprocessing_policy', 'output_policy')}}
    for key in ('specification', 'preprocessing_policy', 'output_policy'):
        published['material'][key] = packages.blob(key + '.json', published[key])
    checkpoint['model_sha256'] = packages.sha(packages.encoded(published['material']))
    artifacts['checkpoint-epoch-0001.json'] = packages.encoded(checkpoint)
    decision = {'format': 'candidate_v1', 'id': 'f' * 32, 'study_id': '2' * 32, 'trial_id': '3' * 32,
        'run_id': run_id, 'checkpoint_sha256': packages.sha(artifacts['checkpoint-epoch-0001.json']),
        'evaluation_sha256': packages.sha(artifacts['metrics.json']), 'policy': {}, 'decision': 'diagnostic',
        'limitations': ['Authored closure fixture only.']}
    ref = {'kind': 'candidate', 'catalog_id': 'e' * 32, 'id': decision['id'], 'sha256': packages.sha(packages.encoded(decision))}
    candidate = {'ref': ref, 'candidate': decision, 'run_id': run_id,
        'checkpoint': packages.blob('checkpoint-epoch-0001.json', artifacts['checkpoint-epoch-0001.json'])}
    return packages.classifier_closure(candidate, artifacts, {'c' * 32: probe_image},
        {'image_training.py': source}, {'format': 'package_runtime_v1', 'snapshot': {
            'schema_version': 1, 'profile': 'captured_cpu_python_v1', 'catalog_id': 'e' * 32,
            'root': '/authored/runtime-snapshots/' + '4' * 64, 'manifest_sha256': '4' * 64,
            'manifest_bytes': 1, 'file_count': 1, 'total_bytes': 1, 'python_version': '3.12',
            'packages': {}, 'launch': {}}}, published)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.blobs = fixture()

    def test_non_epoch_candidate_profile_is_explicitly_unsupported(self):
        with self.assertRaises(packages.PackageError) as error:
            packages.classifier_closure({'checkpoint': {'name': 'checkpoint-fit.json'}},
                {'checkpoint-fit.json': packages.encoded({'clocks': {'epoch': None}})}, {}, {}, {}, {})
        self.assertEqual(error.exception.code, 'unsupported')

    def test_exact_d2_manifest_whole_hash_and_complete_weight_closure(self):
        raw = packages.create_package(self.manifest, self.blobs)
        manifest, files = packages.inspect_package(raw, packages.sha(raw))
        self.assertEqual(set(manifest), packages.MANIFEST_FIELDS)
        checkpoint = packages.decode(files[manifest['checkpoint']['name']])
        self.assertIn(checkpoint['weights'], manifest['inventory'])
        self.assertIn('weights-epoch-0001.pt', files)
        with self.assertRaises(packages.PackageError):
            packages.inspect_package(raw, '0' * 64)

    def test_missing_or_wrong_weights_transform_runtime_and_source_fail(self):
        for name in ('weights-epoch-0001.pt', 'transform.json', 'runtime.json', 'image_training.py'):
            for replacement in (None, b'wrong bytes'):
                with self.subTest(name=name, replacement=replacement):
                    changed = dict(self.blobs)
                    if replacement is None:
                        del changed[name]
                    else:
                        changed[name] = replacement
                    with self.assertRaises(packages.PackageError):
                        packages.create_package(self.manifest, changed)

    def replace_blob(self, manifest, blobs, name, raw):
        old = next(item for item in manifest['inventory'] if item['name'] == name)
        replacement = packages.blob(name, raw, old['media_type'])
        blobs[name] = raw
        manifest['inventory'] = [replacement if item['name'] == name else item for item in manifest['inventory']]
        for key, value in manifest.items():
            if type(value) is dict and value == old:
                manifest[key] = replacement
            elif type(value) is list:
                manifest[key] = [replacement if item == old else item for item in value]

    def test_self_consistent_checkpoint_replacement_cannot_relabel_selected_candidate(self):
        manifest = copy.deepcopy(self.manifest); blobs = dict(self.blobs)
        descriptor = packages.decode(blobs[manifest['checkpoint']['name']])
        descriptor['run_id'] = '9' * 32
        self.replace_blob(manifest, blobs, manifest['checkpoint']['name'], packages.encoded(descriptor))
        with self.assertRaisesRegex(packages.PackageError, 'Selected candidate'):
            packages.create_package(manifest, blobs)

    def test_rehashed_source_replacement_cannot_escape_published_model_binding(self):
        manifest = copy.deepcopy(self.manifest); blobs = dict(self.blobs)
        self.replace_blob(manifest, blobs, 'image_training.py', b'# substituted source with consistent outer inventory\n')
        with self.assertRaisesRegex(packages.PackageError, 'published model material'):
            packages.create_package(manifest, blobs)

    def test_rehashed_evaluation_replacement_cannot_relabel_candidate(self):
        manifest = copy.deepcopy(self.manifest); blobs = dict(self.blobs)
        self.replace_blob(manifest, blobs, 'metrics.json', packages.encoded({'invented': 'evaluation'}))
        with self.assertRaisesRegex(packages.PackageError, 'Selected candidate'):
            packages.create_package(manifest, blobs)

    def test_rehashed_wrong_class_order_and_transform_are_rejected(self):
        for name in ('task.json', 'transform.json', 'runtime.json'):
            manifest = copy.deepcopy(self.manifest); blobs = dict(self.blobs)
            document = packages.decode(blobs[name])
            if name == 'task.json':
                document['class_vocabulary'].reverse()
            elif name == 'transform.json':
                document['size'] = [64, 64]
            else:
                document['snapshot']['profile'] = 'arbitrary_interpreter'
            self.replace_blob(manifest, blobs, name, packages.encoded(document))
            with self.subTest(name=name), self.assertRaises(packages.PackageError):
                packages.create_package(manifest, blobs)

    def test_unknown_rights_permit_private_inspection_but_deny_redistribution(self):
        raw = packages.create_package(self.manifest, self.blobs)
        packages.inspect_package(raw, packages.sha(raw))
        with self.assertRaises(packages.PackageError) as error:
            packages.inspect_package(raw, packages.sha(raw), distribution='redistribution')
        self.assertEqual(error.exception.code, 'unsupported')
        self.assertIsNone(packages.decode(self.blobs['rights.json'])['terms'])

    def test_no_inferred_rights_for_missing_material_disposition(self):
        changed = dict(self.blobs); rights = packages.decode(changed['rights.json'])
        rights['materials'].remove('weights-epoch-0001.pt'); changed['rights.json'] = packages.encoded(rights)
        manifest = copy.deepcopy(self.manifest)
        item = packages.blob('rights.json', changed['rights.json'])
        manifest['licenses'] = [item]
        manifest['inventory'] = [item if x['name'] == 'rights.json' else x for x in manifest['inventory']]
        with self.assertRaises(packages.PackageError):
            packages.create_package(manifest, changed)

    def test_unknown_or_protected_mixed_population_denies_whole_package(self):
        for population in ('test', 'unknown'):
            manifest = copy.deepcopy(self.manifest); blobs = dict(self.blobs)
            lineage = packages.decode(blobs['lineage.json']); lineage['sources'][0]['population'] = population
            blobs['lineage.json'] = packages.encoded(lineage)
            item = packages.blob('lineage.json', blobs['lineage.json'])
            manifest['lineage'] = item
            manifest['inventory'] = [item if x['name'] == 'lineage.json' else x for x in manifest['inventory']]
            with self.subTest(population=population), self.assertRaises(packages.PackageError) as error:
                packages.create_package(manifest, blobs)
            self.assertEqual(error.exception.code, 'unsupported')

    def test_closure_authorization_visits_every_blob_and_transitive_reference(self):
        checked = []
        packages.create_package(self.manifest, self.blobs, authorize=checked.append)
        self.assertEqual(len(checked), len(self.manifest['inventory']) + len(packages.decode(self.blobs['lineage.json'])['sources']))
        def denied(item):
            if item.get('name') == 'weights-epoch-0001.pt':
                raise PermissionError('revoked')
        with self.assertRaises(PermissionError):
            packages.create_package(self.manifest, self.blobs, authorize=denied)

    def test_duplicate_escaping_symlink_and_extra_zip_files_rejected(self):
        for name, mode in (('../escape', 0o100400), ('duplicate.json', 0o120777)):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                info = zipfile.ZipInfo(name); info.external_attr = mode << 16
                archive.writestr(info, b'{}')
            with self.subTest(name=name), self.assertRaises(packages.PackageError):
                packages.archive_files(buffer.getvalue())
        blobs = dict(self.blobs, undeclared=b'private')
        with self.assertRaises(packages.PackageError):
            packages.create_package(self.manifest, blobs)
        with self.assertRaises(packages.PackageError):
            packages.decode(b'{"x":1,"x":2}')
        for raw in (b'{"x":1e309}', b'{"x":-1e309}', b'{"nested":[{"x":1e999}]}', b'[' * 65 + b'0' + b']' * 65):
            with self.subTest(raw=raw), self.assertRaises(packages.PackageError):
                packages.decode(raw)

    def test_project_pins_all_source_runs_and_does_not_admit_or_grant(self):
        with tempfile.TemporaryDirectory() as directory:
            result = packages.prepare_project(Path(directory) / 'package', self.manifest, self.blobs)
            bindings = [x for x in result['graph']['inputs'].values() if x.get('kind') == 'run_artifact']
            lineage = packages.decode(self.blobs['lineage.json'])['sources']
            self.assertEqual(len(bindings), len(lineage))
            self.assertEqual({(x['artifact_name'], x['expected_sha256']) for x in bindings},
                             {(x['artifact_name'], x['sha256']) for x in lineage})

    def test_verifier_project_declares_exact_package_and_explicit_runtime(self):
        import sys
        with tempfile.TemporaryDirectory() as directory:
            binding = {'kind': 'run_artifact', 'run_id': 'a' * 32, 'artifact_name': 'package.zip', 'expected_sha256': 'b' * 64}
            result = packages.prepare_verifier_project(Path(directory) / 'verify', binding, 'c' * 64)
            self.assertEqual(result['graph']['inputs']['package'], binding)
            definition = json.loads((Path(directory) / 'verify' / 'recipe.json').read_bytes())
            self.assertEqual(definition['runtime'], 'captured_cpu_python_v1')
            self.assertEqual(definition['runtime_snapshot_sha256'], 'c' * 64)
            self.assertEqual(definition['outputs'][0]['role'], 'inference_verification')


class TransitiveAccessTests(unittest.TestCase):
    def test_nested_derivative_checks_current_access_and_test_exposure(self):
        from workbench import WorkbenchError
        source = {'id': 'a' * 32, 'state': 'completed', 'artifacts': [{'name': 'predictions-test.json', 'sha256': 'b' * 64}], 'exposure_events': []}
        middle = {'id': 'c' * 32, 'state': 'completed', 'external': True,
            'material': {'inputs': {'source': {'kind': 'run_artifact', 'source': {'run_id': source['id'],
                'artifact_name': 'predictions-test.json', 'measured_sha256': 'b' * 64}}}},
            'artifacts': [{'name': 'package.zip', 'sha256': 'd' * 64}]}
        leaf = {'id': 'e' * 32, 'external': True, 'material': {'inputs': {'package': {'kind': 'run_artifact',
            'source': {'run_id': middle['id'], 'artifact_name': 'package.zip', 'measured_sha256': 'd' * 64}}}}}
        calls = []
        runs = SimpleNamespace(_external=lambda run: run.get('external', False), _load=lambda key: {source['id']: source, middle['id']: middle}[key],
            access=SimpleNamespace(require=lambda *args: calls.append(args)))
        with self.assertRaises(WorkbenchError):
            packages.authorize_transitive_inputs(runs, leaf)
        source['exposure_events'] = ['explicit-disclosure']
        packages.authorize_transitive_inputs(runs, leaf)
        self.assertEqual({x[2] for x in calls}, {source['id'], middle['id']})
        def revoked(*args):
            raise PermissionError('revoked')
        runs.access.require = revoked
        with self.assertRaises(PermissionError):
            packages.authorize_transitive_inputs(runs, leaf)


class PreparedReceiptAtomicityTests(unittest.TestCase):
    """Real PostgreSQL callback/capture boundary; no numerical claim."""
    def test_publish_failure_rolls_back_trial_receipts_audit_and_owned_directory(self):
        import shutil
        import uuid
        from unittest.mock import patch
        import test_model_definitions as fixtures
        from experiments import Experiments
        case = fixtures.CapturedModelCase(methodName='runTest'); case.setUp()
        try:
            dataset = case.dataset; studies = Experiments(dataset); dataset.models = case.models
            model = case.publish(case.create())
            with case.owner.bound(dataset):
                study = studies.create({'name': 'Atomic callback qualification', 'limits': {name: 10**8 for name in
                    ('attempt_slots', 'admitted_wall_seconds', 'retained_bytes', 'peak_staging_bytes')},
                    'policy': {'format': 'selection_policy_v1', 'metric_definition_sha256': '1' * 64,
                        'checkpoint_rule': 'explicit', 'replicate_reduce': 'individual', 'required_capabilities': [],
                        'numerical_acceptance': 'diagnostic', 'tie_break': 'trial_id'}})
                body = {'request_key': 'prepare-' + uuid.uuid4().hex, 'revision': study['revision'],
                    'graph_id': case.graph['id'], 'graph_revision': case.graph['revision'], 'model': model['ref'], 'replicate': 0}
                baseline = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                    for table in ('model_trials', 'model_operation_receipts', 'access_audit')}
                directory = case.path / 'owned-preparation'; directory.mkdir()
                capture = dataset.pipelines.prepare_external_material; observed = []
                def outside_transaction(*args, **kwargs):
                    observed.append(dataset.db.in_transaction)
                    self.assertFalse(dataset.db.in_transaction)
                    return capture(*args, **kwargs)
                def fail_publication(trial):
                    self.assertTrue(dataset.db.in_transaction)
                    dataset.db.on_rollback(lambda: shutil.rmtree(directory))
                    studies._save_receipt(case.owner.identity['actor_id'], 'studies.prepare_package', 'callback-failure-key',
                        '2' * 64, {'trial': trial})
                    dataset.access.audit('studies.prepare_package', trial['id'], {})
                    raise RuntimeError('Required publication callback failed')
                with patch.object(dataset.pipelines, 'prepare_external_material', side_effect=outside_transaction):
                    with self.assertRaisesRegex(RuntimeError, 'publication callback'):
                        studies.prepare_trial(study['id'], body, _publish=fail_publication)
                self.assertEqual(observed, [False])
                self.assertFalse(directory.exists())
                for table, count in baseline.items():
                    self.assertEqual(dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0], count, table)
                self.assertEqual(studies.get(study['id'])['study']['trial_ids'], [])
                self.assertEqual(studies.get(study['id'])['study']['revision'], study['revision'])
        finally:
            case.doCleanups()


@unittest.skipUnless(os.environ.get('TULDOK_PACKAGE_QUALIFICATION_CATALOG') and
                     os.environ.get('TULDOK_PACKAGE_SNAPSHOT_DESCRIPTOR') and
                     os.environ.get('TULDOK_PACKAGE_QUALIFICATION_OUTPUT') and
                     os.environ.get('TULDOK_TRAINING_PYTHON'),
                     'Explicit disposable catalog, captured snapshot, output and CPU training runtime required.')
class ActualCandidatePackageTests(unittest.TestCase):
    def test_actual_study_training_http_package_and_captured_fresh_verifier(self):
        from qualify_candidate_package import qualify_production
        report = qualify_production(Path(os.environ['TULDOK_PACKAGE_QUALIFICATION_CATALOG']),
            Path(os.environ['TULDOK_PACKAGE_SNAPSHOT_DESCRIPTOR']), Path(os.environ['TULDOK_PACKAGE_QUALIFICATION_OUTPUT']))
        self.assertTrue(report['actual_training'])
        self.assertTrue(report['actual_package_run'])
        self.assertTrue(report['actual_captured_verifier_run'])
        self.assertEqual(report['charged']['attempt_slots'], 3)
        self.assertEqual(report['state']['state'], 'fresh_verified')
        self.assertTrue(report['capture_phases'])
        self.assertTrue(all(item['in_transaction'] is False for item in report['capture_phases']))


if __name__ == '__main__':
    unittest.main()
