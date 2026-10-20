"""Prepared real authenticated transport acceptance for the coordinated hooks.

Enable TULDOK_ANALYSIS_HTTP=1 only after the additive operations are registered.
Reuses a prepared actual retained fixture; never patches an application handler
or substitutes query data. No test-only endpoint is installed.
"""
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import Dataset, make_handler
import agent_api
import retained_analysis


@unittest.skipUnless(os.environ.get('TULDOK_ANALYSIS_HTTP') == '1', 'Shared retained-analysis HTTP hooks are not yet integrated.')
class ActualRetainedAnalysisHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(os.environ['TULDOK_ANALYSIS_FIXTURE'])
        cls.receipt = json.loads((fixture / 'fixture.json').read_text())
        cls.token = (fixture / 'owner-token').read_text()
        cls.contracts = {name: agent_api.contract(name, 1) for name in
                         ('runs.retained_analysis', 'runs.export_retained_analysis')}
        cls.dataset = Dataset(cls.receipt['catalog_path'])
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cls.dataset))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.dataset.close()

    def request(self, *, token=None, export=False, body=None, selected=True):
        name = 'runs.export_retained_analysis' if export else 'runs.retained_analysis'
        arguments = dict(self.receipt['request'])
        run_id = arguments.pop('run_id')
        if body is not None:
            arguments.update(body)
        headers = {'Content-Type': 'application/json', 'Origin': self.endpoint,
                   'Authorization': 'Bearer ' + (self.token if token is None else token)}
        if selected:
            headers['Tuldok-Operation-Contract'] = name + '/1/' + self.contracts[name]['sha256']
        target = self.endpoint + '/api/workspace/runs/' + run_id + '/retained-analysis' + ('/export' if export else '')
        request = Request(target, data=json.dumps(arguments).encode(), headers=headers)
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(retained_analysis.MAX_RESPONSE_BYTES + 1)
            self.assertLessEqual(len(raw), retained_analysis.MAX_RESPONSE_BYTES)
            return response.status, json.loads(raw)

    def test_explicit_contract_and_route_bound_run_are_required(self):
        status, value = self.request(selected=False)
        self.assertEqual((status, value['code']), (409, 'contract_mismatch'))
        # Existing selected-contract rules place Run ID in the path only;
        # duplicate body IDs cannot bypass the route's authority even if equal.
        status, value = self.request(body={'run_id': self.receipt['run_id']})
        self.assertEqual((status, value['code']), (409, 'contract_mismatch'))
        self.assertNotIn('curve', value)

    def test_authenticated_http_and_export_equal_real_query(self):
        with self.dataset.access.bind(self.token):
            expected = retained_analysis.query(self.dataset.runs, self.receipt['request'])
        for export in (False, True):
            with self.subTest(export=export):
                status, value = self.request(export=export)
                self.assertEqual(status, 200)
                self.assertEqual(value, expected)
                name = 'runs.export_retained_analysis' if export else 'runs.retained_analysis'
                Draft202012Validator(self.contracts[name]['output_schema']).validate({'status': status, 'result': value})
                self.assertLessEqual(len(value['examples']['rows']), 1)
                self.assertNotIn('probabilities', value['examples']['rows'][0])

    def test_stale_and_foreign_selection_never_returns_dataset(self):
        for body, status, code in (({'evaluation_sha256': '0' * 64}, 409, 'stale'),
                                   ({'metric_definition_sha256': '0' * 64}, 409, 'stale'),
                                   ({'checkpoint_sha256': '0' * 64}, 404, 'not_found')):
            with self.subTest(body=body):
                actual_status, value = self.request(body=body)
                self.assertEqual((actual_status, value['code']), (status, code))
                self.assertNotIn('curve', value)

    def test_closed_request_rejects_sql_and_holdout_without_exposure(self):
        for body in ({'sql': 'SELECT arbitrary_data'}, {'split': 'test'}, {'limit': 101}):
            with self.subTest(body=body):
                status, value = self.request(body=body)
                self.assertEqual((status, value['code']), (400, 'invalid'))
                self.assertNotIn('examples', value)
        with self.dataset.access.bind(self.token):
            self.assertFalse(self.dataset.runs.get(self.receipt['run_id'])['test_exposure']['exposed'])

    def test_actual_revocation_blocks_fresh_http_and_export(self):
        with self.dataset.access.bind(self.token):
            credential = self.dataset.access.issue({'label': 'Retained HTTP revocation fixture', 'scopes': ['inspect']})
        self.assertEqual(self.request(token=credential['token'])[0], 200)
        with self.dataset.access.bind(self.token):
            self.dataset.access.revoke(credential['identity']['credential_id'])
        for export in (False, True):
            with self.subTest(export=export):
                status, value = self.request(token=credential['token'], export=export)
                self.assertEqual((status, value['code']), (401, 'unauthenticated'))
                self.assertNotIn('provenance', value)


if __name__ == '__main__':
    unittest.main()
