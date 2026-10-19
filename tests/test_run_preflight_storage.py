"""Current large-output storage observation; no admission/reservation or execution."""
import copy
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import pipeline
import recipe_contract
from runs import Runs
from workbench import WorkbenchError


class PreflightStorageTests(unittest.TestCase):
    def setUp(self):
        self.owner = SimpleNamespace(path=Path('/bounded-catalog/workspace-runs'))
        self.material = {'resources': {'profile': recipe_contract.LARGE_OUTPUT_PROFILE,
                                     'max_output_bytes': 1024},
                         'captures': {'source/main.py': {'bytes': 33}, 'input/sample': {'bytes': 65}},
                         'recipe': {'schema_version': 1}}
        self.minimum = 2 * 1024 + 1024 ** 3

    def check(self, available, *, pending_capture=False):
        with patch('runs.shutil.disk_usage', return_value=SimpleNamespace(free=available)) as disk:
            result = Runs._check_external_storage(self.owner, self.material, pending_capture=pending_capture)
        disk.assert_called_once_with(self.owner.path)
        return result

    def test_admission_keeps_existing_exact_policy_and_boundary(self):
        original = copy.deepcopy(self.material)
        observed = self.check(self.minimum)
        self.assertEqual(observed['required_bytes'], self.minimum)
        self.assertEqual(observed['available_bytes'], self.minimum)
        self.assertEqual(observed['pending_capture_bytes'], 0)
        self.assertEqual(self.material, original)
        with self.assertRaises(WorkbenchError) as caught:
            self.check(self.minimum - 1)
        self.assertEqual((caught.exception.code, caught.exception.status), ('unavailable', 409))

    def test_preflight_includes_capture_that_admission_already_staged(self):
        with self.assertRaises(WorkbenchError):
            self.check(self.minimum + 97, pending_capture=True)
        observed = self.check(self.minimum + 98, pending_capture=True)
        self.assertEqual(observed['required_bytes'], self.minimum + 98)
        self.assertEqual(observed['pending_capture_bytes'], 98)

    def test_generated_model_context_uses_existing_context_capture_limit(self):
        self.material['recipe'] = {'schema_version': 2, 'format': recipe_contract.EVIDENCE_FORMAT}
        expected = self.minimum + 98 + recipe_contract.EVIDENCE_CONTEXT_LIMIT
        with self.assertRaises(WorkbenchError):
            self.check(expected - 1, pending_capture=True)
        self.assertEqual(self.check(expected, pending_capture=True)['required_bytes'], expected)

    def test_unknown_storage_refuses_and_other_profiles_keep_existing_behavior(self):
        with patch('runs.shutil.disk_usage', side_effect=OSError('injected missing device')):
            with self.assertRaises(WorkbenchError) as caught:
                Runs._check_external_storage(self.owner, self.material, pending_capture=True)
        self.assertEqual(str(caught.exception), 'Execution storage capacity is unavailable.')
        self.assertEqual((caught.exception.code, caught.exception.status), ('unavailable', 409))
        self.material['resources'].pop('profile')
        with patch('runs.shutil.disk_usage') as disk:
            self.assertIsNone(Runs._check_external_storage(self.owner, self.material, pending_capture=True))
        disk.assert_not_called()

    def domain(self):
        graph = {'id': 'a' * 32, 'revision': 1, 'recipe': 'external_recipe',
                 'schema_version': 1, 'mode': 'real', 'recipe_version': 1, 'nodes': [], 'edges': []}
        prepared = {'material': self.material, 'material_sha256': 'b' * 64,
                    'execution_sha256': 'c' * 64}
        storage = Mock(return_value={'required_bytes': self.minimum + 98, 'available_bytes': self.minimum + 100,
                                    'pending_capture_bytes': 98})
        owner = SimpleNamespace(access=Mock(), get=Mock(return_value=graph),
            dataset=SimpleNamespace(projects=object(), releases=object(), runs=SimpleNamespace(_check_external_storage=storage)))
        return graph, prepared, owner, storage

    def test_selected_v3_checks_storage_before_issuing_report_and_rechecks_graph(self):
        graph, prepared, owner, storage = self.domain()
        with patch.object(pipeline.recipe_contract, 'prepare', return_value=(prepared, {})), \
                patch.object(pipeline, '_external_preflight_report', return_value={'state': 'prepared'}) as report:
            result = pipeline.Pipelines.preflight_external(owner, graph['id'], 1, contract_version=3)
        storage.assert_called_once_with(self.material, pending_capture=True)
        report.assert_called_once_with(graph, prepared, storage=storage.return_value)
        self.assertEqual(owner.get.call_count, 2)
        self.assertEqual(result['preflight_report']['state'], 'prepared')

    def test_storage_refusal_cannot_emit_report_or_change_old_projections(self):
        for version in (None, 1, 2, 3):
            graph, prepared, owner, storage = self.domain()
            storage.side_effect = WorkbenchError('Insufficient storage', 'unavailable', 409)
            with patch.object(pipeline.recipe_contract, 'prepare', return_value=(prepared, {})), \
                    patch.object(pipeline, '_external_preflight_report') as report:
                if version == 3:
                    with self.assertRaises(WorkbenchError):
                        pipeline.Pipelines.preflight_external(owner, graph['id'], 1, contract_version=version)
                    storage.assert_called_once()
                else:
                    self.assertEqual(pipeline.Pipelines.preflight_external(owner, graph['id'], 1,
                                     contract_version=version), prepared)
                    storage.assert_not_called()
                report.assert_not_called()

    def test_storage_observation_cannot_hide_graph_drift_or_missing_owner(self):
        graph, prepared, owner, storage = self.domain()
        storage.side_effect = lambda *a, **k: owner.get.configure_mock(return_value=dict(graph, revision=2))
        with patch.object(pipeline.recipe_contract, 'prepare', return_value=(prepared, {})), \
                patch.object(pipeline, '_external_preflight_report') as report:
            with self.assertRaises(WorkbenchError) as caught:
                pipeline.Pipelines.preflight_external(owner, graph['id'], 1, contract_version=3)
            self.assertEqual(caught.exception.code, 'stale')
            report.assert_not_called()
        graph, prepared, owner, _storage = self.domain()
        owner.dataset.runs = None
        with patch.object(pipeline.recipe_contract, 'prepare', return_value=(prepared, {})):
            with self.assertRaises(WorkbenchError) as caught:
                pipeline.Pipelines.preflight_external(owner, graph['id'], 1, contract_version=3)
            self.assertEqual((caught.exception.code, caught.exception.status), ('unavailable', 409))

    def test_report_labels_current_observation_without_claiming_a_reservation(self):
        import agent_api
        import test_run_preflight_report as report_fixtures
        fixture = report_fixtures.PreflightReportTests('runTest'); fixture.setUp()
        observed = self.check(self.minimum + 98, pending_capture=True)
        report = pipeline._external_preflight_report(fixture.graph, fixture.prepared, storage=observed)
        agent_api.validate_output('graphs.preflight_external', {'status': 200,
            'result': dict(fixture.prepared, preflight_report=report)}, 3)
        row = next(row for row in report['checks'] if row['code'] == 'storage_capacity')
        self.assertEqual((row['owner'], row['state']), ('runs', 'checked'))
        self.assertEqual(row['evidence_sha256'], pipeline.digest(observed))
        self.assertIn(str(observed['required_bytes']), row['detail'])
        self.assertIn(str(observed['available_bytes']), row['detail'])
        self.assertEqual(report['admission'], 'not_reserved')
        self.assertEqual(next(row for row in report['checks'] if row['code'] == 'resource_availability')['state'], 'deferred')


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL') and importlib.util.find_spec('jsonschema'),
                     'Requires disposable PostgreSQL and the operation validator')
class PreflightStorageIntegrationTests(unittest.TestCase):
    def test_real_preparation_storage_refusal_has_no_admission_or_staging_effect(self):
        import test_large_recipe_contract as fixtures
        fixture = fixtures.LargeRecipeContract('runTest')
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        fixture.value['resources']['profile'] = recipe_contract.LARGE_OUTPUT_PROFILE
        graph = fixture.cpu_graph()
        dataset = fixture.dataset
        tables = ('workspace_graphs', 'workspace_runs', 'access_execution_grants',
                  'access_execution_consumptions', 'model_attempt_reservations')
        before = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in tables}
        directories = set(dataset.runs.path.iterdir())
        with patch('runtime_snapshots.RuntimeSnapshots.get', return_value=fixture.descriptor()), \
                patch('runs.shutil.disk_usage', return_value=SimpleNamespace(free=0)), \
                patch('subprocess.Popen', side_effect=AssertionError('Preflight launched compute')):
            for version in (None, 1, 2):
                self.assertTrue(dataset.pipelines.preflight_external(graph['id'], 1, contract_version=version)['valid'])
            with self.assertRaises(WorkbenchError) as caught:
                dataset.pipelines.preflight_external(graph['id'], 1, contract_version=3)
            self.assertEqual((caught.exception.code, caught.exception.status), ('unavailable', 409))
        with patch('runtime_snapshots.RuntimeSnapshots.get', return_value=fixture.descriptor()), \
                patch('runs.shutil.disk_usage', return_value=SimpleNamespace(free=1024**4)), \
                patch('subprocess.Popen', side_effect=AssertionError('Preflight launched compute')):
            result = dataset.pipelines.preflight_external(graph['id'], 1, contract_version=3)
        self.assertTrue(any(row['code'] == 'storage_capacity' and row['state'] == 'checked'
                            for row in result['preflight_report']['checks']))
        self.assertEqual(set(dataset.runs.path.iterdir()), directories)
        after = {table: dataset.db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in tables}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
