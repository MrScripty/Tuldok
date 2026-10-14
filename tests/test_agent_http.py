"""Authenticated public discovery and bounded artifact HTTP integration.

Neutral fixture execution proves process/byte custody, never model acceptance.
No authentication injection or production owner mutation is mocked.
"""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Dataset, make_handler
from test_external_runs import ExternalCase


class AgentHTTPCase(ExternalCase):
    """Shared real server fixture; contains no test methods of its own."""
    def setUp(self):
        super().setUp()
        self.server = None
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server_thread.join(timeout=5)
            self.server = None

    def reopen_http(self):
        self.stop_server()
        self.dataset.close()
        self.dataset = Dataset(self.path / 'catalog', project_roots={'fixture': self.project_path})
        self.start_server()

    def http(self, path, body=None, token=None, *, binary=False, headers=None):
        headers = {'Content-Type': 'application/json', **(headers or {})}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        request = Request(self.root + path, data=None if body is None else json.dumps(body).encode(),
                          headers=headers)
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, raw if binary else json.loads(raw)

    def issue_http(self, scopes):
        status, value = self.http('/api/access/credentials',
                                  {'label': 'Explicit agent integration fixture', 'scopes': scopes},
                                  self.owner.token)
        self.assertEqual(status, 201, value)
        return value

    def complete_http(self):
        approval_body = {'graph_id': self.graph['id'], 'graph_revision': self.graph['revision'],
                         'expected_digest': self.preflight['material_sha256'],
                         'consumer_actor_id': self.agent['identity']['actor_id']}
        status, approval = self.http('/api/workspace/runs/approve-external', approval_body, self.owner.token)
        self.assertEqual(status, 201, approval)
        status, run = self.http('/api/workspace/runs/submit-external',
                                self.body(approval=approval), self.agent['token'])
        self.assertEqual(status, 201, run)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            status, run = self.http('/api/workspace/runs/' + run['id'], token=self.agent['token'])
            self.assertEqual(status, 200, run)
            if run['state'] in ('completed', 'failed', 'cancelled', 'unknown', 'interrupted'):
                break
            time.sleep(.05)
        self.assertEqual(run['state'], 'completed', {key: run.get(key) for key in ('id', 'state', 'error')})
        self.assertEqual(run['custody_phase'], 'drained')
        return run


class AgentHTTPTests(AgentHTTPCase):
    def test_discovery_is_authenticated_canonical_and_secret_free(self):
        import agent_api
        path = '/api/agent/operations'
        self.assertEqual(self.http(path)[0], 401)
        status, _ = self.http('/api/access/credentials',
                              {'label': 'Invalid missing inspect', 'scopes': ['edit']}, self.owner.token)
        self.assertEqual(status, 400)  # Production issuance never admits a no-inspect agent.
        status, discovery = self.http(path, token=self.agent['token'])
        self.assertEqual(status, 200, discovery)
        self.assertEqual(discovery, agent_api.discovery())
        serialized = json.dumps(discovery)
        for credential in (self.owner.token, self.agent['token']):
            self.assertNotIn(credential, serialized)
        status, _ = self.http('/api/access/credentials/' + self.agent['identity']['credential_id'] + '/revoke',
                              {}, self.owner.token)
        self.assertEqual(status, 200)
        self.assertEqual(self.http(path, token=self.agent['token'])[0], 401)

    def test_real_segment_reconstruction_bounds_restart_and_revocation(self):
        run = self.complete_http()
        artifact = next(item for item in run['artifacts'] if item['name'] == 'result.txt')
        route = '/api/workspace/runs/' + run['id'] + '/artifact-segment/result.txt'
        body = {'expected_sha256': artifact['sha256'], 'offset': 0, 'max_bytes': 7}
        self.assertEqual(self.http(route, body)[0], 401)
        chunks, offset = [], 0
        while True:
            status, part = self.http(route, dict(body, offset=offset), self.agent['token'])
            self.assertEqual(status, 200, part)
            self.assertEqual(part['verification'], 'segment_read_whole_hash_unverified')
            self.assertEqual((part['run_id'], part['name'], part['offset']), (run['id'], 'result.txt', offset))
            raw = base64.b64decode(part['data_base64'], validate=True)
            self.assertEqual(part['segment_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual((part['bytes'], part['next_offset']), (len(raw), offset + len(raw)))
            self.assertEqual(part['total_bytes'], len(self.input))
            chunks.append(raw)
            offset = part['next_offset']
            if part['eof']:
                break
            self.assertGreater(len(raw), 0)
        assembled = b''.join(chunks)
        self.assertEqual(assembled, self.input)
        self.assertEqual(hashlib.sha256(assembled).hexdigest(), artifact['sha256'])
        for changed in (dict(body, offset=True), dict(body, offset=-1),
                        dict(body, offset=len(self.input) + 1), dict(body, max_bytes=0),
                        dict(body, max_bytes=8 * 1024 * 1024 + 1), dict(body, extra='not allowed')):
            with self.subTest(changed=changed):
                self.assertEqual(self.http(route, changed, self.agent['token'])[0], 400)
        self.assertEqual(self.http(route, dict(body, expected_sha256='0' * 64), self.agent['token'])[0], 409)
        status, end = self.http(route, dict(body, offset=len(self.input)), self.agent['token'])
        self.assertEqual(status, 200, end)
        self.assertEqual((end['bytes'], end['data_base64'], end['eof']), (0, '', True))
        self.reopen_http()
        status, again = self.http(route, body, self.agent['token'])
        self.assertEqual(status, 200, again)
        self.assertEqual(base64.b64decode(again['data_base64']), self.input[:7])
        self.assertEqual(self.http('/api/access/credentials/' + self.agent['identity']['credential_id'] + '/revoke',
                                  {}, self.owner.token)[0], 200)
        self.assertEqual(self.http(route, dict(body, offset=7), self.agent['token'])[0], 401)

    def test_holdout_scope_does_not_invent_external_classification_results(self):
        run = self.complete_http()
        path = '/api/workspace/runs/' + run['id'] + '/expose-test'
        self.assertEqual(self.http(path, {'reason': 'Explicit fixture scope check'}, self.agent['token'])[0], 403)
        scoped = self.issue_http(['inspect', 'expose-holdout'])
        status, error = self.http(path, {'reason': 'Explicit fixture scope check'}, scoped['token'])
        self.assertEqual((status, error['code']), (409, 'unsupported'))
        status, after = self.http('/api/workspace/runs/' + run['id'], token=scoped['token'])
        self.assertEqual(status, 200, after)
        self.assertEqual(after['state'], 'completed')
        self.assertNotIn('test_exposure', after)
