"""The paired benchmark cannot count partial/corrupt replies as improvements."""
import base64
import copy
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from benchmark_artifact_segments import collect_batch
from test_run_artifact_segments import item, segment


class PairedCollectionReportingTests(unittest.TestCase):
    def fixture(self):
        request=item();expected=[{'name':request['name'],'bytes':7,'sha256':request['expected_sha256']}]
        response={'status':200,'result':{'format':'artifact_segments_v1','items':[
            {'key':'0','source':request['source'],'status':200,'result':segment(request)}]}}
        return expected,response

    def test_only_exact_whole_hash_receipts_are_comparable(self):
        expected,response=self.fixture();client=SimpleNamespace(call=Mock(return_value=response))
        self.assertEqual(collect_batch(client,item()['source'],expected),expected)
        self.assertEqual(client.call.call_count,1)
        bad=copy.deepcopy(response);raw=b'changed'
        bad['result']['items'][0]['result'].update(data_base64=base64.b64encode(raw).decode(),
            segment_sha256=hashlib.sha256(raw).hexdigest())
        client.call.return_value=bad
        with self.assertRaisesRegex(AssertionError,'whole artifact'):
            collect_batch(client,item()['source'],expected)

    def test_partial_failure_or_service_error_does_not_fallback(self):
        expected,response=self.fixture()
        response['result']['items'][0]={'key':'0','source':item()['source'],'status':409,
            'error':{'code':'stale','message':'Authored exact identity refusal'}}
        client=SimpleNamespace(call=Mock(return_value=response))
        with self.assertRaisesRegex(AssertionError,'item refusal'):collect_batch(client,item()['source'],expected)
        self.assertEqual(client.call.call_count,1)
        client.call.reset_mock();client.call.return_value={'status':503,'result':{'error':'Unavailable'}}
        with self.assertRaisesRegex(AssertionError,'service refused'):collect_batch(client,item()['source'],expected)
        self.assertEqual(client.call.call_count,1)
