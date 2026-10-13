"""Real transport and domain authorization, without injected request actors."""
import json
import tempfile
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from access import AccessError
from app import Dataset, make_handler
from auth_helpers import ExplicitOwnerFixture
from dataset_recipes import generate


class AccessHTTP(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dataset = Dataset(directory.name)
        self.addCleanup(self.dataset.close)
        self.owner = ExplicitOwnerFixture.bootstrap(self.dataset)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def request(self, path, body=None, headers=None):
        request = Request(self.root + path, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            response = urlopen(request)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response), response.headers

    def test_all_legacy_and_current_reads_require_real_credentials(self):
        for route in ('/api/samples', '/api/workbench/records', '/api/workspace/runs', '/api/access/session'):
            with self.subTest(route=route):
                self.assertEqual(self.request(route)[0], 401)
        self.assertEqual(self.request('/api/access/session', headers=self.owner.headers)[0], 200)
        with self.assertRaises(AccessError):
            self.dataset.rows()

    def test_cookie_origin_mixed_transport_and_bootstrap_replay(self):
        code = self.dataset.access._local_owner_token()
        self.assertEqual(self.request('/api/access/session', {'token': code})[0], 403)
        status, identity, headers = self.request('/api/access/session', {'token': code}, {'Origin': self.root})
        self.assertEqual(status, 200)
        self.assertEqual(identity['kind'], 'owner')
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        self.assertEqual(self.request('/api/access/session', {'token': code}, {'Origin': self.root})[0], 401)
        session = {'Cookie': cookie.split(';')[0]}
        self.assertEqual(self.request('/api/access/logout', {}, session)[0], 403)
        self.assertEqual(self.request('/api/access/logout', {}, {**session, 'Origin': 'http://elsewhere.invalid'})[0], 403)
        self.assertEqual(self.request('/api/access/logout', {}, {**session, **self.owner.headers})[0], 403)
        self.assertEqual(self.request('/api/access/logout', {}, {**session, 'Origin': self.root})[0], 200)
        self.assertEqual(self.request('/api/access/session', headers=session)[0], 401)

    def test_denial_audit_storage_outage_still_returns_structured_error(self):
        self.dataset.db.connection.close()
        status, body, _ = self.request('/api/access/session', headers={'Authorization': 'Bearer'})
        self.assertEqual((status, body['code']), (503, 'storage'))

    def test_agent_review_and_execution_denied_before_mutation(self):
        with self.owner.bound(self.dataset):
            agent = self.dataset.access.issue({'label': 'Editor', 'scopes': ['inspect', 'edit', 'execute']})
            row = self.dataset.workbench.import_asset({'kind': 'text', 'text': 'Bound review target', 'groups': ['source']})
        review = {'revision': row['revision'], 'source_revision': row['source_revision'],
                  'task': 'text_classification', 'annotation': {'label': 'topic'},
                  'groups': row['groups'], 'review': 'human_reviewed'}
        with self.dataset.access.bind(agent['token']):
            with self.assertRaises(AccessError):
                self.dataset.workbench.save(row['id'], review)
            self.assertEqual(self.dataset.workbench.get(row['id'])['revision'], row['revision'])
            response = {'id': uuid.uuid4().hex, 'prompt_id': row['id'], 'revision': 0,
                        'parent_revision': row['revision'], 'source_revision': row['source_revision'],
                        'completion': 'Agent draft', 'review': 'human_reviewed'}
            with self.assertRaises(AccessError):
                self.dataset.workbench.save_response(response)
            draft = self.dataset.workbench.save_response(dict(response, review='draft'))['response']
            self.assertEqual(draft['provenance']['method'], 'agent_authored')
            self.assertEqual(draft['review'], 'draft')
            with self.assertRaises(AccessError):
                self.dataset.workbench.save_response(dict(response, revision=draft['revision']))
            with self.assertRaises(AccessError):
                generate(self.dataset.workbench, {})
            for start in (self.dataset.runs.submit, self.dataset.generation_jobs.start,
                          self.dataset.grounded.start, self.dataset.caption_proposals.start,
                          self.dataset.text_classification_proposals.start):
                with self.assertRaises(AccessError):
                    start({})
        headers = {'Authorization': 'Bearer ' + agent['token']}
        self.assertEqual(self.request('/api/workspace/runs', {}, headers)[0], 403)
        self.assertEqual(self.request('/api/access/credentials', {'label': 'Forged', 'scopes': ['inspect']}, headers)[0], 403)
        with self.owner.bound(self.dataset):
            self.dataset.access.revoke(agent['identity']['credential_id'])
        self.assertEqual(self.request('/api/access/session', headers=headers)[0], 401)


if __name__ == '__main__':
    unittest.main()
