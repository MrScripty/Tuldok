"""Real HTTP authority for external execution; no injected request actors.

Execution acceptance lives in test_external_runs with a real neutral recipe.
These transport checks also retain the owner-only legacy execution boundary.
"""
import json
from http.server import ThreadingHTTPServer
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Dataset, make_handler
from auth_helpers import ExplicitOwnerFixture
from test_external_runs import ExternalCase


class ExternalHTTPTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dataset = Dataset(directory.name)
        self.addCleanup(self.dataset.close)
        self.owner = ExplicitOwnerFixture.bootstrap(self.dataset)
        with self.owner.bound(self.dataset):
            self.agent = self.dataset.access.issue({
                'label': 'External submitter', 'scopes': ['inspect', 'edit', 'execute']})
            self.reader = self.dataset.access.issue({
                'label': 'Inspection only', 'scopes': ['inspect']})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def request(self, path, body=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(self.root + path,
                          data=None if body is None else json.dumps(body).encode(),
                          headers=headers)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_external_routes_require_real_credentials(self):
        for route in ('/api/workspace/graphs/external',
                      '/api/workspace/runs/approve-external',
                      '/api/workspace/runs/submit-external',
                      '/api/access/execution-grants/' + 'a' * 32 + '/revoke'):
            with self.subTest(route=route):
                self.assertEqual(self.request(route, {})[0], 401)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])

    def test_agent_cannot_approve_or_revoke_and_reader_cannot_submit(self):
        for route in ('/api/workspace/runs/approve-external',
                      '/api/access/execution-grants/' + 'a' * 32 + '/revoke'):
            with self.subTest(route=route):
                status, _ = self.request(route, {}, self.agent['token'])
                self.assertEqual(status, 403)
        self.assertEqual(self.request('/api/workspace/runs/submit-external',
                                      {}, self.reader['token'])[0], 403)
        # Approved external submission does not broaden historical execution.
        self.assertEqual(self.request('/api/workspace/runs', {}, self.agent['token'])[0], 403)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])
            self.assertEqual(self.dataset.db.execute(
                'SELECT count(*) FROM access_execution_grants').fetchone()[0], 0)


class ExternalWorkflowHTTPTests(ExternalCase):
    """Actual HTTP review, agent admission and real neutral process output."""
    request = ExternalHTTPTests.request

    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def test_review_approval_submission_and_exact_artifact_through_http(self):
        status, graph = self.request('/api/workspace/graphs/external', self.graph_body(), self.owner.token)
        self.assertEqual(status, 201, graph)
        status, preflight = self.request(
            '/api/workspace/graphs/' + graph['id'] + '/preflight-external',
            {'revision': graph['revision']}, self.owner.token)
        self.assertEqual(status, 200, preflight)
        body = {'graph_id': graph['id'], 'graph_revision': graph['revision'],
                'expected_digest': preflight['material_sha256']}
        status, approval = self.request('/api/workspace/runs/approve-external',
            dict(body, consumer_actor_id=self.agent['identity']['actor_id']), self.owner.token)
        self.assertEqual(status, 201, approval)
        submission = dict(body, request_key='http-real-neutral-run', approval_id=approval['id'])
        status, run = self.request('/api/workspace/runs/submit-external', submission, self.agent['token'])
        self.assertEqual(status, 201, run)
        status, replay = self.request('/api/workspace/runs/submit-external', submission, self.agent['token'])
        self.assertEqual((status, replay['id']), (201, run['id']))
        complete = self.await_state(run['id'], {'completed', 'failed', 'unknown'})
        self.assertEqual(complete['state'], 'completed', complete)
        artifact = next(item for item in complete['artifacts'] if item['name'] == 'result.txt')
        with urlopen(self.owner.request(self.root + artifact['url']), timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), self.input)
        status, _ = self.request('/api/workspace/runs/submit-external', submission, self.other['token'])
        self.assertEqual(status, 409)

    def test_http_revocation_is_terminal_for_unused_approval(self):
        grant = self.approve()
        status, revoked = self.request('/api/access/execution-grants/' + grant['id'] + '/revoke',
                                       {}, self.owner.token)
        self.assertEqual(status, 200, revoked)
        self.assertIsNotNone(revoked['revoked_at'])
        status, body = self.request('/api/workspace/runs/submit-external',
                                    self.body(approval=grant), self.agent['token'])
        self.assertEqual(status, 409, body)
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])


if __name__ == '__main__':
    unittest.main()
