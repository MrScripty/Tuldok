"""A project folder served by the app (spec-m7.md, sections 6 and 7): contracts, the HTTP routes, the clients, the page.

The contract tests need no database. Everything else needs one and runs only
when TULDOK_DATABASE_URL names a disposable cluster: each test starts from
test_tuldok_project_builds.BuildCase (a Git-committed copy of the buildable
fixture with its environment connected, dropped afterwards), opens a catalog
in the same temporary directory with a ProjectHost on that copy, and serves it
with app.make_handler on port 0. The owner signs in as the app's tests do
(auth_helpers.ExplicitOwnerFixture) and issues agent credentials. Builds run
the fixture's stand-in scripts; no GPU is used.
"""
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import operations  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
PUBLISHED = {
    'catalog': (115, 'b31b7a2b794020622e64d593cd29455226a4170451f15201e28cad5d9edd18f1'),
    'project': (152, '58e4270277a38b58869ca4c6ae4bccffe74387b2ee70d3c178b30821f8d27320'),
}
DISCOVERY = '9c02284ed750bce31c53100d4657deaf40b519c9d17d5e3165b6b6342930b660'
PROJECT_NAMES = {'project.' + operation.name for operation in operations.OPERATIONS}
AGENT_SCOPES = ['inspect', 'edit', 'execute', 'cancel']
# The files of the project workspace page and their media types (app.py serves each with '; charset=utf-8').
WORKSPACE_FILES = {
    '/project-workspace/base.css': 'text/css',
    '/project-workspace/adapter.js': 'text/javascript',
    '/project-workspace/charts.js': 'text/javascript',
    '/project-workspace/markdown.js': 'text/javascript',
    '/project-workspace/tree.js': 'text/javascript',
    '/project-workspace/screens.js': 'text/javascript',
    '/project-workspace/actions.js': 'text/javascript',
    '/project-workspace/tabs.js': 'text/javascript',
    '/project-workspace/app.js': 'text/javascript',
    '/static/vendor/ubuntu-sans/UbuntuSans[wdth,wght].ttf': 'font/ttf',
    '/static/vendor/ubuntu-sans/UbuntuSans-Italic[wdth,wght].ttf': 'font/ttf',
    '/static/vendor/ubuntu-sans/UbuntuSansMono[wght].ttf': 'font/ttf',
    '/static/vendor/ubuntu-sans/UbuntuSansMono-Italic[wght].ttf': 'font/ttf',
    '/static/vendor/ubuntu-sans/LICENCE.txt': 'text/plain',
}


def digest(value):
    return hashlib.sha256(agent_api.encoded(value)).hexdigest()


class Contracts(unittest.TestCase):
    """What is published: unchanged for catalogs and old projects, the table for project folders."""

    def test_the_published_digests_are_unchanged(self):
        for profile, (count, expected) in PUBLISHED.items():
            with self.subTest(profile):
                value = agent_api.capabilities('b' * 32, profile=profile)
                self.assertEqual(len(value['operations']), count)
                self.assertEqual(digest(value), expected)
                self.assertFalse([item['id'] for item in value['operations'] if item['id'].startswith('project.')])
        self.assertEqual(digest(agent_api.discovery()), DISCOVERY)

    def test_the_project_folder_profile_is_the_table(self):
        value = agent_api.capabilities('b' * 32, profile='project_folder')
        self.assertEqual(agent_api.negotiate(value, 'b' * 32).keys(), PROJECT_NAMES | {'context.get', 'identity.get'})
        self.assertEqual({item['id'] for item in value['operations']}, PROJECT_NAMES | {'context.get', 'identity.get'})
        self.assertEqual({item['availability'] for item in value['operations']}, {'available'})
        published = {item['id']: item['contracts'] for item in value['operations']}
        for operation in operations.OPERATIONS:
            with self.subTest(operation.name):
                [contract] = published['project.' + operation.name]
                self.assertEqual(contract['input_schema'], operation.arguments)
                self.assertEqual(contract['authority'], 'owner' if operation.who == 'owner' else 'agent')
                self.assertEqual(contract['effects'], 'mutation' if operation.mutation else 'read')
                self.assertEqual(contract['retry'], 'never' if operation.mutation else 'read')
                success, refusal = contract['output_schema']['oneOf']
                self.assertEqual(success['properties']['result']['required'], list(operation.result))
                self.assertEqual(refusal['properties']['result']['required'], ['error'])
                published_operation = agent_api.operation('project.' + operation.name)
                self.assertEqual((published_operation['method'], published_operation['path']),
                                 ('POST', '/api/project/' + operation.name))
                self.assertEqual(published_operation['description'], operation.summary)
                self.assertEqual(agent_api.operation(published_operation['mcp_name'])['operation_id'],
                                 'project.' + operation.name)

    def test_a_result_is_checked_against_its_keys(self):
        agent_api.validate_output('project.summary', {'status': 200, 'result': {
            key: None for key in operations.by_name('summary').result} | {'more': 1}})
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.validate_output('project.summary', {'status': 200, 'result': {'name': 'x'}})
        agent_api.validate_output('project.summary', {'status': 409, 'result': {
            'error': 'No.', 'code': 'not-awaiting', 'problems': [{'message': 'x'}], 'references': ['a/b'], 'files': []}})
        with self.assertRaises(agent_api.AgentAPIError):
            agent_api.validate_output('project.summary', {'status': 409, 'result': {'error': 'No.', 'detail': 'x'}})


class Served(builds_base.BuildCase):
    """BuildCase with a ProjectHost on the copy, served on port 0, an owner and an agent credential."""

    def setUp(self):
        super().setUp()
        from app import make_handler
        from auth_helpers import ExplicitOwnerFixture
        from tuldok_project.host import ProjectHost
        self.host = ProjectHost(self.temporary / 'catalog', self.folder)
        self.addCleanup(self.host.close)
        self.catalog_id = self.host.db.dataset_id
        self.owner = ExplicitOwnerFixture.bootstrap(self.host)
        with self.owner.bound(self.host):
            self.agent = self.host.access.issue({'label': 'Project agent', 'scopes': AGENT_SCOPES})
            self.reader = self.host.access.issue({'label': 'Reader', 'scopes': ['inspect']})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.host))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def http(self, path, body=None, token=None, *, contract=None, raw=False):
        token = self.agent['token'] if token is None else token
        headers = {'Authorization': 'Bearer ' + token}
        if body is not None:
            headers['Content-Type'] = 'application/json'
        if contract is not None:
            headers[agent_api.CONTRACT_HEADER] = contract
        request = Request(self.root + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            data = response.read()
            if raw:
                return response.status, response.headers.get('Content-Type'), data
            return response.status, json.loads(data)

    def call(self, name, arguments=None, token=None):
        """POST /api/project/<name> with its contract selected; (status, body)."""
        return self.http('/api/project/' + name, arguments or {}, token,
                         contract=agent_api.selected_header('project.' + name))

    def ok(self, name, arguments=None, token=None):
        status, value = self.call(name, arguments, token)
        self.assertEqual(status, 200, value)
        return value

    def activity(self):
        return self.ok('activity', {'limit': 500})['items']


class Routes(Served):

    def test_a_request_without_its_contract_is_refused(self):
        self.assertEqual(self.http('/api/project/summary', {})[0], 409)
        status, value = self.http('/api/project/summary', {})
        self.assertEqual(value['code'], 'contract_mismatch')
        status, value = self.call('summary')
        self.assertEqual(status, 200, value)
        self.assertEqual(value['folder'], os.path.realpath(self.folder))

    def test_an_unknown_operation(self):
        status, value = self.http('/api/project/nothing', {}, contract='project.nothing/1/' + 'a' * 64)
        self.assertEqual((status, value['code']), (409, 'contract_mismatch'))
        status, value = self.http('/api/project/nothing', {}, contract=agent_api.selected_header('project.summary'))
        self.assertEqual((status, value['code']), (409, 'contract_mismatch'))
        status, value = self.http('/api/project/summary', {}, contract=agent_api.selected_header('project.status'))
        self.assertEqual((status, value['code']), (409, 'contract_mismatch'))

    def test_an_agent_calling_an_owner_operation_is_refused_and_nothing_is_done(self):
        status, value = self.call('disconnect_environment', {'reference': 'environments/test-python'})
        self.assertEqual((status, value['code']), (403, 'forbidden'))
        environment = self.ok('environment', {'reference': 'environments/test-python'})
        self.assertIsNotNone(environment['interpreter'])
        self.assertEqual(self.activity(), [])
        status, value = self.call('request_build', {'targets': ['datasets/numbers']}, self.reader['token'])
        self.assertEqual((status, value['code']), (403, 'forbidden'))
        status, value = self.call('set_definition', {'reference': 'datasets/numbers', 'text': '{}'},
                                  self.reader['token'])
        self.assertEqual((status, value['code']), (403, 'forbidden'))
        self.assertEqual(self.activity(), [])
        done = self.ok('disconnect_environment', {'reference': 'environments/test-python'}, self.owner.token)
        self.assertEqual(done['disconnected'], 'environments/test-python')

    def test_invalid_arguments(self):
        status, value = self.call('definitions', {'kind': 'nothing', 'more': 1})
        self.assertEqual((status, value['code']), (400, 'invalid'), value)
        self.assertEqual(len(value['problems']), 2)
        self.assertEqual({problem['severity'] for problem in value['problems']}, {'error'})
        status, value = self.http('/api/project/summary', None, contract=agent_api.selected_header('project.summary'))
        self.assertEqual(status, 409)
        request = Request(self.root + '/api/project/summary', data=b'{"a":1,"a":2}', headers={
            'Authorization': 'Bearer ' + self.agent['token'], 'Content-Type': 'application/json',
            agent_api.CONTRACT_HEADER: agent_api.selected_header('project.summary')})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=30)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.loads(caught.exception.read())['code'], 'invalid')

    def test_a_refusal_arrives_with_its_code_status_and_problems(self):
        status, value = self.call('definition', {'reference': 'recipes/nothing'})
        self.assertEqual((status, value['code']), (404, 'not-found'), value)
        status, value = self.call('set_definition', {'reference': 'datasets/numbers', 'text': '{"format": 1}'})
        self.assertEqual((status, value['code']), (400, 'invalid'), value)
        self.assertTrue(value['problems'])
        self.assertEqual(set(value['problems'][0]), {'severity', 'path', 'pointer', 'message'})
        self.assertEqual(self.activity()[0]['outcome'], 'invalid')
        status, value = self.call('approve_build', {'request': 'abcdef'}, self.owner.token)
        self.assertEqual(status, operations.error_status(value['code']), value)

    def test_a_result_that_breaks_its_keys_is_not_sent_as_a_success(self):
        with mock.patch.object(self.host.service, 'call', return_value={'name': 'Only a name'}):
            status, value = self.call('summary')
        self.assertEqual((status, value['code']), (502, 'contract_output'))
        self.assertNotIn('name', value)

    def test_other_routes_in_folder_mode(self):
        for path, body in (('/api/samples', None), ('/api/workspace/runs', None), ('/api/workspace/projects', None),
                           ('/api/workbench/import', {'text': 'x', 'groups': ['a']}), ('/api/export', None)):
            with self.subTest(path):
                status, value = self.http(path, body)
                self.assertEqual((status, value['code']), (409, 'unavailable'), value)
        status, value = self.http('/api/access/session')
        self.assertEqual((status, value['kind'], value['label']), (200, 'agent', 'Project agent'))
        status, value = self.http('/api/agent/capabilities')
        self.assertEqual((status, value), (200, agent_api.capabilities(self.catalog_id, profile='project_folder')))
        status, value = self.http('/api/agent/operations')
        self.assertEqual((status, value), (200, agent_api.discovery()))
        status, value = self.http('/api/workspace/context')
        self.assertEqual((status, value), (200, {'version': 1, 'mode': 'real', 'dataset_id': self.catalog_id,
                                                 'project_folder': True}))
        status, value = self.http('/api/access/credentials', {'label': 'Another', 'scopes': ['inspect']},
                                  self.owner.token)
        self.assertEqual(status, 201, value)

    def test_the_page(self):
        """The project workspace (spec-w2.md): served for /, /workspaces and /workbench with each of its files."""
        page = (REPOSITORY / 'static' / 'project-workspace.html').read_bytes()
        for path in ('/', '/workspaces', '/workbench', '/project-workspace'):
            status, kind, data = self.http(path, raw=True)
            self.assertEqual((status, kind), (200, 'text/html; charset=utf-8'))
            self.assertEqual(data, page)
        self.assertIn(b'/auth.js', page)
        for path, expected in WORKSPACE_FILES.items():
            with self.subTest(path):
                status, kind, data = self.http(path, raw=True)
                self.assertEqual((status, kind), (200, expected + '; charset=utf-8'))
                source = path.removeprefix('/static/').removeprefix('/')
                self.assertEqual(data, (REPOSITORY / 'static' / source).read_bytes())
                if not path.startswith('/static/vendor/'):
                    self.assertIn(path.encode(), page)
        for path in ('/project-folder', '/project-folder.js', '/project-folder.css'):
            status, value = self.http(path)
            self.assertEqual((status, value), (404, {'error': 'Not found.'}))
        for name in ('project-folder.html', 'project-folder.js', 'project-folder.css'):
            self.assertFalse((REPOSITORY / 'static' / name).exists())

    def test_the_page_files_follow_the_page_rules(self):
        """No external reference, no pinned contract, no markup from text, no inline script or handler."""
        files = {path: (REPOSITORY / 'static' / path.lstrip('/')).read_text(encoding='utf-8')
                 for path in WORKSPACE_FILES if path.endswith(('.js', '.css'))}
        files['/project-workspace.html'] = (REPOSITORY / 'static' / 'project-workspace.html').read_text(encoding='utf-8')
        for path, text in files.items():
            with self.subTest(path):
                self.assertNotRegex(text, r'https?://(?!www\.w3\.org/2000/svg)')
                self.assertNotRegex(text, '[a-f0-9]{64}')
                self.assertNotRegex(text, r'innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function')
        self.assertIn('/api/agent/capabilities', files['/project-workspace/adapter.js'])
        self.assertNotRegex(files['/project-workspace.html'], r'<script(?![^>]*\bsrc=)|\son[a-z]+=|style=')
        self.assertIn("default-src 'self'", files['/project-workspace.html'])
        css = files['/project-workspace/base.css']
        self.assertIn('prefers-color-scheme: dark', css)
        self.assertIn('[data-theme="dark"]', css)
        licence = (REPOSITORY / 'static' / 'vendor' / 'ubuntu-sans' / 'LICENCE.txt').read_text(encoding='utf-8')
        self.assertIn('UBUNTU FONT LICENCE Version 1.0', licence)
        self.assertIn('Canonical Ltd', licence)

    def test_a_folder_that_does_not_open_ends_start_up(self):
        (self.folder / 'datasets' / 'numbers.json').write_text('{"format": ', encoding='utf-8')
        command = [sys.executable, str(REPOSITORY / 'app.py'), '--data', str(self.temporary / 'catalog-2'),
                   '--port', '0', '--project-folder', str(self.folder)]
        finished = subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=REPOSITORY)
        self.assertEqual(finished.returncode, 2, finished.stderr)
        self.assertIn('datasets/numbers.json', finished.stderr)
        finished = subprocess.run(command + ['--project-root', 'a=/tmp'], capture_output=True, text=True,
                                  timeout=120, cwd=REPOSITORY)
        self.assertEqual(finished.returncode, 2, finished.stderr)
        self.assertIn('--project-folder', finished.stderr)


class Clients(Served):

    def test_an_agent_client_reads_and_edits(self):
        client = agent_api.AgentClient(self.root, self.agent['token'], self.catalog_id)
        started = client.bootstrap()
        self.assertEqual(set(started['operations']), PROJECT_NAMES | {'context.get', 'identity.get'})
        summary = client.call('project.summary', {})
        self.assertEqual(summary['status'], 200, summary)
        self.assertEqual(summary['result']['project_id'], self.project_id)
        recipes = client.call('project_definitions', {'kind': 'recipe'})['result']['definitions']
        self.assertEqual({row['reference'] for row in recipes}, {'recipes/fit-a', 'recipes/fit-b'})
        planned = client.call('project.plan', {'targets': ['recipes/fit-a']})['result']
        self.assertIn('recipes/fit-a', [step['reference'] for step in planned['steps']])
        definition = client.call('project.definition', {'reference': 'datasets/numbers'})['result']
        document = json.loads(definition['text'])
        document['title'] = 'A few numbers, edited by an agent'
        edited = client.call('project.set_definition', {'reference': 'datasets/numbers',
                                                        'text': json.dumps(document, indent=2) + '\n'})
        self.assertEqual(edited['status'], 200, edited)
        self.assertEqual(edited['result']['title'], 'A few numbers, edited by an agent')
        self.assertTrue(edited['result']['unsaved'])
        [row] = self.activity()
        self.assertEqual((row['operation'], row['outcome'], row['actor']['kind']), ('set_definition', 'done', 'agent'))
        refused = client.call('project.definition', {'reference': 'recipes/nothing'})
        self.assertEqual((refused['status'], refused['result']['code']), (404, 'not-found'))
        refused = client.call('project.approve_build', {'request': 'abcdef'})
        self.assertEqual((refused['status'], refused['result']['code']), (403, 'forbidden'))
        with self.assertRaises(agent_api.AgentAPIError):
            client.call('project.definitions', {'kind': 'nothing'})  # refused before anything is sent

    def test_the_owner_client(self):
        client = agent_api.ProjectFolderOwnerClient(self.root, self.owner.token, self.catalog_id)
        started = client.bootstrap()
        self.assertEqual(set(started['operations']), PROJECT_NAMES)
        self.assertEqual(client.call('project.summary', {})['status'], 200)
        self.assertEqual(client.call('project_environments', {})['status'], 200)
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            client.call('context.get', {})
        self.assertEqual(caught.exception.code, 'operation_unsupported')
        with self.assertRaises(agent_api.AgentAPIError) as caught:
            agent_api.ProjectFolderOwnerClient(self.root, self.agent['token'], self.catalog_id).bootstrap()
        self.assertEqual(caught.exception.code, 'unauthenticated')


class Requests(Served):

    def test_an_agent_requests_a_build_and_the_owner_approves_it(self):
        requested = self.ok('request_build', {'targets': ['datasets/numbers']})
        self.assertEqual(requested['state'], 'awaiting-approval')
        self.assertEqual(requested['requested_by']['kind'], 'agent')
        status, value = self.call('approve_build', {'request': requested['id']})
        self.assertEqual((status, value['code']), (403, 'forbidden'))
        approved = self.ok('approve_build', {'request': requested['id']}, self.owner.token)
        self.assertEqual(approved['state'], 'queued')
        deadline = time.monotonic() + 120
        while True:
            shown = self.ok('build_request', {'request': requested['id']})
            if shown['state'] not in ('queued', 'running') or time.monotonic() > deadline:
                break
            time.sleep(0.3)
        self.assertEqual(shown['state'], 'succeeded', shown)
        self.assertEqual([row['id'] for row in self.ok('build_requests')['requests']], [requested['id']])
        self.assertTrue(shown['runs'])
        run = self.ok('run', {'run': shown['runs'][0]['id']})
        self.assertEqual(run['state'], 'succeeded')
        self.assertIn('BUILDABLE_LABEL', run['env_names'])
        progress = self.ok('progress', {'run': run['id']})
        self.assertTrue(progress['ended'])
        self.assertEqual(progress['run']['id'], run['id'])
        status, value = self.call('request_build', {'targets': ['datasets/numbers']})
        self.assertEqual((status, value['code']), (409, 'nothing-to-build'), value)


@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class CatalogMode(unittest.TestCase):

    def test_project_operations_are_unavailable(self):
        from app import Dataset, make_handler
        from auth_helpers import ExplicitOwnerFixture
        with tempfile.TemporaryDirectory() as directory:
            dataset = Dataset(Path(directory) / 'catalog')
            try:
                owner = ExplicitOwnerFixture.bootstrap(dataset)
                server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    request = Request(f'http://127.0.0.1:{server.server_port}/api/project/summary', data=b'{}', headers={
                        'Authorization': 'Bearer ' + owner.token, 'Content-Type': 'application/json',
                        agent_api.CONTRACT_HEADER: agent_api.selected_header('project.summary')})
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(request, timeout=30)
                    self.assertEqual(caught.exception.code, 409)
                    self.assertEqual(json.loads(caught.exception.read()),
                                     {'error': 'Start Tuldok with --project-folder to use this.', 'code': 'unavailable'})
                    request = Request(f'http://127.0.0.1:{server.server_port}/api/agent/capabilities',
                                      headers={'Authorization': 'Bearer ' + owner.token})
                    with urlopen(request, timeout=30) as response:
                        listed = json.loads(response.read())
                    self.assertFalse([item for item in listed['operations'] if item['id'].startswith('project.')])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(5)
            finally:
                dataset.close()


if __name__ == '__main__':
    unittest.main()
