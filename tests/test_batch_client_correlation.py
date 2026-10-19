"""Selected batch response correlation beyond the closed transport schema."""
import copy
import unittest
from unittest.mock import patch

import agent_api
from test_run_artifact_segments import item, segment


class BatchClientCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.request = {'items': [item()]}
        selected = self.request['items'][0]
        self.envelope = {'status': 200, 'result': {'format': 'artifact_segments_v1', 'items': [
            {'key': selected['key'], 'source': copy.deepcopy(selected['source']),
             'status': 200, 'result': segment(selected)}]}}
        self.client = agent_api.AgentClient('http://127.0.0.1:12345', 'x' * 32, '2' * 32)
        self.client._ready = True
        self.client._selected = {'runs.artifact_segments': 1}

    def call(self, request=None, envelope=None):
        value = copy.deepcopy(self.envelope if envelope is None else envelope)
        agent_api.validate_output('runs.artifact_segments', value)
        with patch.object(self.client, '_request', return_value=value) as transport:
            try:
                return self.client.call('runs.artifact_segments', self.request if request is None else request)
            finally:
                self.assertEqual(transport.call_count, 1)

    def test_exact_reply_is_accepted_once(self):
        self.assertEqual(self.call(), self.envelope)

    def test_schema_valid_unrequested_segments_are_refused(self):
        mutations = [
            (lambda row: row.update(key='different'), ('transport', 502)),
            (lambda row: row['result'].update(name='other.bin'), ('artifact_mismatch', 409)),
            (lambda row: row['result'].update(expected_sha256='f' * 64), ('artifact_mismatch', 409)),
            (lambda row: row['result'].update(offset=1, total_bytes=8, next_offset=8), ('artifact_mismatch', 409)),
            (lambda row: (row['source'].update(run_id='3' * 32), row['result'].update(run_id='3' * 32)), ('transport', 502)),
        ]
        for mutate, expected_error in mutations:
            value = copy.deepcopy(self.envelope)
            mutate(value['result']['items'][0])
            with self.subTest(mutation=mutate):
                with self.assertRaises(agent_api.AgentAPIError) as caught:
                    self.call(envelope=value)
                self.assertEqual((caught.exception.code, caught.exception.status), expected_error)

    def test_publication_catalog_is_checked_even_when_ref_echo_matches(self):
        selected = self.request['items'][0]
        ref = {'kind': 'recovered_publication_result', 'schema_version': 1,
               'catalog_id': self.client.catalog_id, 'run_id': selected['source']['run_id'],
               **{key: 'a' * 64 for key in ('material_sha256', 'inventory_sha256',
                                           'custody_receipt_sha256', 'sha256')}}
        selected['source'] = {'kind': 'publication', 'ref': ref}
        row = self.envelope['result']['items'][0]
        row['source'] = copy.deepcopy(selected['source'])
        row['result']['result_ref'] = copy.deepcopy(ref)
        self.assertEqual(self.call(), self.envelope)
        selected['source']['ref']['catalog_id'] = '4' * 32
        row['source'] = copy.deepcopy(selected['source'])
        row['result']['result_ref'] = copy.deepcopy(selected['source']['ref'])
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            self.call()
        self.assertEqual((caught.exception.code, caught.exception.status), ('transport', 502))

    def test_item_failure_is_returned_without_retry_or_fallback(self):
        self.envelope['result']['items'][0] = {
            'key': self.request['items'][0]['key'], 'source': self.request['items'][0]['source'],
            'status': 409, 'error': {'code': 'stale', 'message': 'Exact artifact differs.'}}
        self.assertEqual(self.call(), self.envelope)
