"""Exact successful-preparation reporting; synthetic projections are not Runs."""
import copy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import agent_api
import pipeline
from workbench import WorkbenchError


class PreflightReportTests(unittest.TestCase):
    def setUp(self):
        self.graph = {'id': 'a' * 32, 'revision': 2}
        material = {'catalog_id': 'b' * 32, 'graph_execution_sha256': 'f' * 64,
                    'captures': {'input/sample': {'bytes': 3, 'sha256': 'c' * 64}},
                    'host_files': {'pipeline.py': 'd' * 64}, 'runtime': {'profile': 'system_python'},
                    'project': {'measured_sha256': 'e' * 64}, 'inputs': {},
                    'recipe': {'outputs': [{'path': 'result.json', 'max_bytes': 1024, 'required': True,
                                           'role': 'result'}]},
                    'resources': {'wall_seconds': 10, 'max_output_bytes': 1024}}
        self.prepared = {'valid': True, 'status': 'valid', 'material': material, 'material_sha256': pipeline.digest(material),
                         'execution_sha256': 'f' * 64, 'graph_revision': 2}

    def report(self):
        return pipeline._external_preflight_report(self.graph, self.prepared)

    def test_report_binds_exact_material_graph_and_its_own_content(self):
        report = self.report()
        self.assertEqual(report['catalog_id'], 'b' * 32)
        self.assertEqual((report['graph_id'], report['graph_revision']), ('a' * 32, 2))
        self.assertEqual(report['material_sha256'], self.prepared['material_sha256'])
        self.assertEqual(report['execution_sha256'], 'f' * 64)
        body = {key: value for key, value in report.items() if key != 'sha256'}
        self.assertEqual(report['sha256'], hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest())

    def test_report_preserves_prepared_material_and_approval_identity(self):
        original = copy.deepcopy(self.prepared)
        self.report()
        self.assertEqual(self.prepared, original)
        self.assertNotIn('preflight_report', self.prepared['material'])

    def test_clone_or_revision_changes_report_without_claiming_new_execution(self):
        original = self.report()
        for key, value in (('id', '1' * 32), ('revision', 3)):
            graph = dict(self.graph, **{key: value})
            changed = pipeline._external_preflight_report(graph, self.prepared)
            self.assertNotEqual(changed['sha256'], original['sha256'])
            self.assertEqual(changed['material_sha256'], original['material_sha256'])

    def test_mutable_execution_facts_are_explicitly_deferred(self):
        report = self.report()
        checks = {row['code']: row for row in report['checks']}
        for code in ('authority_admission', 'resource_availability', 'runtime_ready_go',
                     'custody_completion', 'output_publication'):
            self.assertEqual(checks[code]['state'], 'deferred', code)
            self.assertEqual(checks[code]['owner'], 'runs')
            self.assertTrue(checks[code]['boundary'])
        self.assertEqual(report['admission'], 'not_reserved')
        self.assertEqual(report['state'], 'prepared')
        self.assertFalse(any(row['state'] == 'ready' for row in checks.values()))

    def test_new_wire_contract_requires_closed_bounded_report_and_old_overlap_survives(self):
        result = dict(self.prepared, preflight_report=self.report())
        for version in (1, 2, 3):
            agent_api.validate_output('graphs.preflight_external', {'status': 200, 'result': result}, version)
        selected = agent_api.negotiate(agent_api.capabilities('b' * 32), 'b' * 32)
        self.assertEqual(selected['graphs.preflight_external'], 4)
        for mutate in (lambda value: value.pop('preflight_report'),
                       lambda value: value.update(valid=False),
                       lambda value: value.update(status='blocked'),
                       lambda value: value['preflight_report'].update(ready=True),
                       lambda value: value['preflight_report']['checks'][0].update(state='ready'),
                       lambda value: value['preflight_report']['checks'].extend(value['preflight_report']['checks'] * 2)):
            bad = copy.deepcopy(result)
            mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(agent_api.AgentAPIError):
                agent_api.validate_output('graphs.preflight_external', {'status': 200, 'result': bad}, 3)

    def test_consumer_refuses_inconsistent_identities_even_with_repaired_report_hash(self):
        result = dict(self.prepared, preflight_report=self.report())
        for change in (lambda value: value['material'].update(catalog_id='1' * 32),
                       lambda value: value['material']['recipe'].update(name='changed'),
                       lambda value: value['preflight_report'].update(material_sha256='2' * 64),
                       lambda value: value['preflight_report'].update(execution_sha256='3' * 64),
                       lambda value: value['preflight_report'].update(graph_revision=3),
                       lambda value: value['preflight_report'].update(sha256='4' * 64)):
            bad = copy.deepcopy(result); change(bad)
            if bad['preflight_report']['sha256'] != '4' * 64:
                body = {key: value for key, value in bad['preflight_report'].items() if key != 'sha256'}
                bad['preflight_report']['sha256'] = pipeline.digest(body)
            with self.subTest(change=change), self.assertRaises(agent_api.AgentAPIError) as caught:
                agent_api.validate_output('graphs.preflight_external', {'status': 200, 'result': bad}, 3)
            self.assertEqual(caught.exception.code, 'transport')
            self.assertEqual(str(caught.exception), 'Exact preflight report identity is inconsistent.')

    def test_utf8_content_identity_is_distinct_from_ascii_wire_encoding(self):
        self.prepared['material']['recipe']['name'] = 'Δοκιμή — neutral fixture'
        self.prepared['material_sha256'] = pipeline.digest(self.prepared['material'])
        result = dict(self.prepared, preflight_report=self.report())
        report = result['preflight_report']; report['checks'][0]['detail'] = 'Verified bytes: λ'
        report['sha256'] = pipeline.digest({key: value for key, value in report.items() if key != 'sha256'})
        decoded = agent_api.decode(agent_api.encoded({'status': 200, 'result': result}))
        self.assertEqual(agent_api.validate_output('graphs.preflight_external', decoded, 3)['result'], result)

    def test_client_correlates_graph_revision_and_catalog_without_retry(self):
        client = agent_api.AgentClient('http://127.0.0.1:12345', 'x' * 32, 'b' * 32)
        client._ready = True; client._selected = {'graphs.preflight_external': 3}
        for arguments, catalog in (({'graph_id': 'a' * 32, 'revision': 3}, 'b' * 32),
                                   ({'graph_id': '1' * 32, 'revision': 2}, 'b' * 32),
                                   ({'graph_id': 'a' * 32, 'revision': 2}, '1' * 32)):
            client.catalog_id = catalog
            client._request = Mock(return_value={'status': 200, 'result':
                dict(self.prepared, preflight_report=self.report())})
            with self.subTest(arguments=arguments), self.assertRaises(agent_api.AgentAPIError):
                client.call('graphs.preflight_external', arguments)
            self.assertEqual(client._request.call_count, 1)
        client.catalog_id = 'b' * 32
        self.prepared['material']['catalog_id'] = '1' * 32
        self.prepared['material_sha256'] = pipeline.digest(self.prepared['material'])
        foreign = {'status': 200, 'result': dict(self.prepared, preflight_report=self.report())}
        agent_api.validate_output('graphs.preflight_external', foreign, 3)
        client._request = Mock(return_value=foreign)
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            client.call('graphs.preflight_external', {'graph_id': 'a' * 32, 'revision': 2})
        self.assertEqual(str(caught.exception), 'Preflight report does not match the requested graph or catalog.')
        self.assertEqual(client._request.call_count, 1)

    def domain_owner(self):
        # Unit substitution only at fresh preparation/storage; no real authority or runtime claim.
        graph = dict(self.graph, schema_version=1, mode='real', recipe='external_recipe',
                     recipe_version=1, nodes=[], edges=[])
        owner = SimpleNamespace(access=Mock(), get=Mock(return_value=graph),
            dataset=SimpleNamespace(projects=object(), releases=object(), runs=object()))
        prepared = dict(self.prepared, execution_sha256=pipeline.execution_digest(graph))
        return graph, owner, prepared

    def test_domain_calls_fresh_preparation_and_only_selected_v3_adds_report(self):
        for version in (None, 1, 2, 3):
            graph, owner, prepared = self.domain_owner()
            with patch.object(pipeline.recipe_contract, 'prepare', return_value=(prepared, {})) as prepare:
                result = pipeline.Pipelines.preflight_external(owner, graph['id'], 2, contract_version=version)
            self.assertEqual(prepare.call_count, 1)
            self.assertEqual(owner.get.call_count, 2)
            self.assertEqual('preflight_report' in result, version == 3)
            self.assertEqual({key: value for key, value in result.items() if key != 'preflight_report'}, prepared)

    def test_graph_drift_or_preparation_failure_cannot_emit_checked_report(self):
        graph, owner, prepared = self.domain_owner()
        owner.get.side_effect = [graph, dict(graph, revision=3)]
        with patch.object(pipeline.recipe_contract, 'prepare', return_value=(prepared, {})), \
                patch.object(pipeline, '_external_preflight_report') as report:
            with self.assertRaises(WorkbenchError) as caught:
                pipeline.Pipelines.preflight_external(owner, graph['id'], 2, contract_version=3)
            self.assertEqual(caught.exception.code, 'stale')
            report.assert_not_called()
        graph, owner, _prepared = self.domain_owner()
        with patch.object(pipeline.recipe_contract, 'prepare', side_effect=WorkbenchError('Runtime changed', 'stale', 409)), \
                patch.object(pipeline, '_external_preflight_report') as report:
            with self.assertRaises(WorkbenchError):
                pipeline.Pipelines.preflight_external(owner, graph['id'], 2, contract_version=3)
            report.assert_not_called()

    def test_unsupported_report_versions_refuse_before_preparation(self):
        for version in (True, 1.0, '3', 5):
            graph, owner, _prepared = self.domain_owner()
            with patch.object(pipeline.recipe_contract, 'prepare') as prepare:
                with self.subTest(version=version), self.assertRaises(WorkbenchError) as caught:
                    pipeline.Pipelines.preflight_external(owner, graph['id'], 2, contract_version=version)
                self.assertEqual(caught.exception.code, 'unsupported')
                prepare.assert_not_called(); owner.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
