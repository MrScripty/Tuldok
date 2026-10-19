"""Controlled transport correlation; retained science is not reinterpreted here."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_api
import extension_evidence
from test_scientific_comparison import retained_pair, choices


class ScientificComparisonClientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        pair = retained_pair(Path(temporary.name))
        catalog = '2' * 32
        self.arguments = {
            'operands': [{'kind': 'completed_run', 'catalog_id': catalog, 'run_id': row[1]['id']}
                         for row in pair],
            'selection': choices(pair),
            'point': {'field_id': pair[0][2]['fields'][0]['field_id'], 'x': 1, 'y': 2, 'z': 3},
        }
        result = extension_evidence.compare_scientific(
            [row[2] for row in pair], [row[1]['extension_context'] for row in pair],
            self.arguments['selection'], self.arguments['point'])
        result['operands'] = [{
            'operand': copy.deepcopy(operand), 'original_run_state': 'completed',
            'model': {}, 'material': {}, 'study_membership': None, 'configuration': {},
            'timings': {}, 'memory': {'state': 'unknown', 'reason': 'not retained'},
            'artifacts': [], 'custody': 'managed_run_artifacts',
        } for operand in self.arguments['operands']]
        self.envelope = {'status': 200, 'result': result}
        self.client = agent_api.AgentClient('http://127.0.0.1:12345', 'x' * 32, catalog)
        self.client._ready = True
        self.client._selected = {'runs.compare_scientific_evidence': 1}

    def call(self, arguments=None, envelope=None):
        value = copy.deepcopy(self.envelope if envelope is None else envelope)
        # The mismatched reply must remain valid under the selected closed
        # schema: this tests request identity beyond structural validation.
        agent_api.validate_output('runs.compare_scientific_evidence', value)
        with patch.object(self.client, '_request', return_value=value) as request:
            result = self.client.call('runs.compare_scientific_evidence',
                                      self.arguments if arguments is None else arguments)
        self.assertEqual(request.call_count, 1)
        return result

    def test_exact_reply_is_accepted_without_transport_retry(self):
        self.assertEqual(self.call(), self.envelope)

    def test_mixed_publication_operand_keeps_its_exact_ref(self):
        operand = self.arguments['operands'][1]
        ref = {'kind': 'recovered_publication_result', 'schema_version': 1,
               'catalog_id': operand['catalog_id'], 'run_id': operand['run_id'],
               **{key: 'a' * 64 for key in ('material_sha256', 'inventory_sha256',
                                           'custody_receipt_sha256', 'sha256')}}
        self.arguments['operands'][1] = {'kind': 'publication_result', 'ref': ref}
        self.envelope['result']['operands'][1]['operand'] = copy.deepcopy(self.arguments['operands'][1])
        self.assertEqual(self.call(), self.envelope)
        self.envelope['result']['operands'][1]['operand']['ref']['sha256'] = 'b' * 64
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            self.call()
        self.assertEqual((caught.exception.code, caught.exception.status), ('transport', 502))

    def test_schema_valid_other_selection_reply_is_refused(self):
        mutations = [
            lambda result: result['point'].update(x=2),
            lambda result: result['operands'].reverse(),
            lambda result: result['scalar'].update(mode='side_by_side', delta=None),
            lambda result: result['scalar']['sides'][0].update(checkpoint_sha256='f' * 64),
            lambda result: result['scalar']['sides'][1].update(evaluation_sha256='e' * 64),
            lambda result: result['scalar']['sides'][0].update(metric_definition_sha256='d' * 64),
            lambda result: result['scalar']['sides'][1].update(metric_id='different'),
            lambda result: result['scalar']['sides'][0].update(run_id='4' * 32),
        ]
        for mutate in mutations:
            value = copy.deepcopy(self.envelope)
            mutate(value['result'])
            with self.subTest(mutation=mutate):
                with self.assertRaises(agent_api.AgentAPIError) as caught:
                    self.call(envelope=value)
                self.assertEqual((caught.exception.code, caught.exception.status), ('transport', 502))

    def test_matching_foreign_catalog_echo_is_refused(self):
        arguments, envelope = copy.deepcopy(self.arguments), copy.deepcopy(self.envelope)
        arguments['operands'][0]['catalog_id'] = '5' * 32
        envelope['result']['operands'][0]['operand'] = copy.deepcopy(arguments['operands'][0])
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            self.call(arguments, envelope)
        self.assertEqual((caught.exception.code, caught.exception.status), ('transport', 502))

    def test_ordinary_exact_v2_comparison_correlates_each_side(self):
        arguments = dict(self.arguments['selection'],
                         run_id=self.arguments['operands'][0]['run_id'],
                         other_run_id=self.arguments['operands'][1]['run_id'])
        envelope = {'status': 200, 'result': copy.deepcopy(self.envelope['result']['scalar'])}
        self.client._selected = {'runs.compare_model_evidence': 2}
        with patch.object(self.client, '_request', return_value=copy.deepcopy(envelope)) as request:
            self.assertEqual(self.client.call('runs.compare_model_evidence', arguments), envelope)
        self.assertEqual(request.call_count, 1)
        mutations = [
            lambda value: value.update(mode='side_by_side', delta=None),
            lambda value: value['sides'].reverse(),
            lambda value: value['sides'][0].update(checkpoint_sha256='f' * 64),
            lambda value: value['sides'][1].update(evaluation_sha256='e' * 64),
            lambda value: value['sides'][0].update(metric_definition_sha256='d' * 64),
            lambda value: value['sides'][1].update(metric_id='different'),
        ]
        for mutate in mutations:
            value = copy.deepcopy(envelope)
            mutate(value['result'])
            agent_api.validate_output('runs.compare_model_evidence', value, 2)
            with self.subTest(mutation=mutate):
                with patch.object(self.client, '_request', return_value=value) as request:
                    with self.assertRaises(agent_api.AgentAPIError) as caught:
                        self.client.call('runs.compare_model_evidence', arguments)
                self.assertEqual(request.call_count, 1)
                self.assertEqual((caught.exception.code, caught.exception.status), ('transport', 502))
