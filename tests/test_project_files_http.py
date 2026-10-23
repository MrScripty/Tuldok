"""Real authenticated project-file transport with disposable PostgreSQL catalogs.

Set TULDOK_DATABASE_URL to a disposable local database. An optional distinct
TULDOK_PROJECT_FILES_COLD_DATABASE_URL also proves reconstruction without the
source role/database; no lab fixture or execution service is used.
"""
from datetime import timedelta
import hashlib
import importlib.util
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import uuid

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import make_handler
import agent_api
from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
from project_workspace import ProjectWorkspace

API = '/api/workspace/project-files'
TEXT = 'Café 山 🧪 — authored source\nA scientist’s unique rationale.\n'


def canonical_bytes(directory):
    """Track only portable authored files, ignoring local operational state."""
    result = {}
    for file in directory.rglob('*'):
        relative = file.relative_to(directory)
        if any(part in ('.git', '.tuldok-local') for part in relative.parts):
            continue
        if file.is_file() and not file.is_symlink():
            result[relative.as_posix()] = file.read_bytes()
    return result


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable local PostgreSQL')
class ProjectFilesHTTP(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-project-files-http-')
        self.path = Path(self.temporary.name)
        self.external = self.path / 'external'
        self.external.mkdir()
        self.hosts = []
        self.schemas = []
        self.controls = []
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.cleanup_owned)
        self.select_host(self.path / 'control', {'fixture': self.external})

    def cleanup_owned(self):
        for workspace, server, thread in reversed(self.hosts):
            server.shutdown()
            server.server_close()
            thread.join(5)
            workspace.close()
        for dsn, schema in self.schemas:
            with psycopg.connect(connection_info(dsn), autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        # Projection manifests are physical identities, distinct from logical project IDs.
        for dsn, control in self.controls:
            for manifest in control.rglob('.tuldok.json'):
                value = json.loads(manifest.read_bytes())
                schema = ('projection_' + value['projection_id'] if value['version'] == 2
                          else 'catalog_' + value['dataset_id'])
                with psycopg.connect(connection_info(dsn), autocommit=True) as connection:
                    connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def select_host(self, control, roots, dsn=None):
        dsn = dsn or os.environ['TULDOK_DATABASE_URL']
        workspace = ProjectWorkspace(control, roots, dsn=dsn)
        self.schemas.append((dsn, workspace.db.schema))
        self.controls.append((dsn, Path(control)))
        owner = ExplicitOwnerFixture.bootstrap(workspace)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(workspace))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.hosts.append((workspace, server, thread))
        self.workspace, self.owner = workspace, owner
        self.origin = f'http://127.0.0.1:{server.server_port}'

    def request(self, path, body=None, *, authenticated=True, method=None, token=None):
        headers = {'Content-Type': 'application/json', 'Origin': self.origin}
        route = urlsplit(path).path
        if route == API:
            operation = 'status'
        elif route == API + '/records':
            operation = 'query'
        elif route.startswith(API + '/records/'):
            operation = 'annotate' if body is not None else 'get'
        elif route.startswith(API + '/'):
            operation = route.removeprefix(API + '/').replace('-', '_')
        else:
            operation = None
        if operation is not None:
            headers['Tuldok-Operation-Contract'] = agent_api.selected_header('project_files.' + operation)
        if authenticated:
            headers['Authorization'] = 'Bearer ' + (token or self.owner.token)
        request = Request(self.origin + path,
                          data=None if body is None else json.dumps(body, ensure_ascii=False).encode(),
                          headers=headers, method=method)
        try:
            response = urlopen(request, timeout=getattr(self, 'request_timeout_seconds', 15))
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            value = json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw
            return response.status, value

    def state(self):
        status, value = self.request(API)
        self.assertEqual(status, 200, value)
        self.assertEqual(value['format'], 'project_files_state_v1')
        return value

    def envelope(self, state=None, **extra):
        state = state or self.state()
        return {'binding': state['binding'],
                'expected_checkpoint': state['project']['checkpoint'] if state['project'] else None,
                'request_key': uuid.uuid4().hex, **extra}

    def action(self, action_name, state=None, **extra):
        status, value = self.request(API + '/' + action_name, self.envelope(state, **extra))
        self.assertIn(status, (200, 201), value)
        return value

    def records(self, state=None):
        state = state or self.state()
        query = urlencode({'binding': state['binding'], 'checkpoint': state['project']['checkpoint']})
        status, value = self.request(API + '/records?' + query)
        self.assertEqual(status, 200, value)
        return value['items']

    def detail(self, identifier, state=None):
        state = state or self.state()
        arguments = {'binding': state['binding'], 'checkpoint': state['project']['checkpoint'], 'history_limit': 4}
        status, value = self.request(API + '/records/' + identifier + '?' + urlencode(arguments))
        self.assertEqual(status, 200, value)
        history = list(value['history'])
        cursor = value['next_history_before_revision']
        while cursor is not None:
            arguments['before_revision'] = cursor
            status, page = self.request(API + '/records/' + identifier + '?' + urlencode(arguments))
            self.assertEqual(status, 200, page)
            self.assertEqual(page['record'], value['record'])
            history.extend(page['history'])
            cursor = page['next_history_before_revision']
        return {**value, 'history': history, 'next_history_before_revision': None}

    def create(self):
        before = self.state()
        self.action('new', root='fixture', directory='alpha', name='External café 🧪')
        opened = self.state()
        self.assertEqual(opened['state'], 'open')
        self.assertNotEqual(opened['binding'], before['binding'])
        return opened

    def import_text(self):
        self.action('import-text', asset={'name': 'Unicode source 山', 'text': TEXT,
                                         'groups': ['source-fixture'], 'parents': [],
                                         'rights': 'Owned synthetic verification input'})
        records = self.records()
        self.assertEqual(len(records), 1)
        record = self.detail(records[0]['id'])['record']
        self.assertEqual(record['text'], TEXT)
        return record

    def test_authenticated_owner_only_selection_and_inert_control(self):
        self.assertEqual(self.request(API, authenticated=False)[0], 401)
        state = self.state()
        self.assertEqual(state['state'], 'no_project_open')
        self.assertIsNone(state['project'])
        self.assertIn('fixture', state['roots'])
        for name in ('runs', 'jobs', 'generation_jobs', 'caption_proposals'):
            self.assertFalse(hasattr(self.workspace, name), name + ' must not be constructed')
        with self.owner.bound(self.workspace):
            editor = self.workspace.access.issue({'label': 'Fixture editor', 'scopes': ['inspect', 'edit']})
        status, _ = self.request(API + '/new', self.envelope(state, root='fixture', directory='editor', name='Denied'), token=editor['token'])
        self.assertEqual(status, 403)
        self.assertFalse((self.external / 'editor').exists())
        self.assertEqual(self.state()['binding'], state['binding'])

    def test_cold_copy_reconstructs_exact_identity_values_and_history_without_credentials(self):
        self.create()
        initial = self.import_text()
        first = self.detail(initial['id'])
        body = {'revision': initial['revision'], 'source_revision': initial['source_revision'],
                'task': 'text_classification', 'annotation': {'label': 'positive 山'},
                'groups': ['source-fixture', 'review-fixture'], 'review': 'human_reviewed'}
        status, value = self.request(API + '/records/' + initial['id'], self.envelope(annotation=body))
        self.assertEqual(status, 200, value)
        expected = self.detail(initial['id'])
        self.assertEqual(expected['record']['annotation'], {'label': 'positive 山'})
        self.assertGreater(len(expected['history']), len(first['history']))
        self.assertEqual(expected['record']['revision'], initial['revision'] + 1)
        self.action('save')
        source_state = self.state()
        source = self.external / 'alpha'
        scripts = source / 'scripts'
        scripts.mkdir(exist_ok=True)
        trap = scripts / 'must-not-run.py'
        trap.write_text("from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('unsafe')\n")
        before = canonical_bytes(source)
        self.assertTrue(before)
        raw = b'\n'.join(before.values())
        for secret in (self.owner.token.encode(), hashlib.sha256(self.owner.token.encode()).hexdigest().encode(),
                       b'access_credentials', b'Authorization', b'TULDOK_DATABASE_URL'):
            self.assertNotIn(secret, raw)
        self.action('close')
        self.assertEqual(self.state()['state'], 'no_project_open')
        relocated = self.path / 'cold-external'
        relocated.mkdir()
        shutil.copytree(source, relocated / 'clone', ignore=shutil.ignore_patterns('.tuldok-local'))
        self.assertEqual(canonical_bytes(relocated / 'clone'), before)
        cold_dsn = os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL', os.environ['TULDOK_DATABASE_URL'])
        if 'TULDOK_PROJECT_FILES_COLD_DATABASE_URL' in os.environ:
            source_database = psycopg.conninfo.conninfo_to_dict(connection_info(os.environ['TULDOK_DATABASE_URL']))['dbname']
            with psycopg.connect(connection_info(cold_dsn)) as connection:
                database, source_access = connection.execute(
                    'SELECT current_database(), has_database_privilege(current_user,%s,\'CONNECT\')',
                    (source_database,)).fetchone()
                self.assertNotEqual(database, source_database)
                self.assertFalse(source_access, 'Cold role must not connect to the source database')
        self.select_host(self.path / 'fresh-control', {'fixture': relocated}, cold_dsn)
        self.action('open', root='fixture', directory='clone')
        cold = self.state()
        self.assertEqual(cold['project'], source_state['project'])
        actual = self.detail(initial['id'])
        self.assertEqual(actual['record'], expected['record'])
        self.assertEqual(actual['history'], expected['history'])
        self.action('save')
        self.assertEqual(canonical_bytes(relocated / 'clone'), before, 'No-op Save has no canonical byte changes')
        self.assertFalse((relocated / 'clone' / 'scripts' / 'EXECUTED').exists())

    def test_old_binding_and_stale_checkpoint_reject_without_canonical_effect(self):
        self.create()
        old = self.state()
        record = self.import_text()
        current = self.state()
        self.assertNotEqual(old['project']['checkpoint'], current['project']['checkpoint'])
        stale_query = urlencode({'binding': old['binding'], 'checkpoint': old['project']['checkpoint']})
        self.assertEqual(self.request(API + '/records?' + stale_query)[0], 409)
        before = canonical_bytes(self.external / 'alpha')
        status, _ = self.request(API + '/save', self.envelope(old))
        self.assertEqual(status, 409)
        self.assertEqual(canonical_bytes(self.external / 'alpha'), before)
        self.action('close')
        self.action('open', root='fixture', directory='alpha')
        self.assertNotEqual(self.state()['binding'], current['binding'])
        status, _ = self.request(API + '/import-text', self.envelope(current, asset={
            'name': 'Delayed wrong binding', 'text': 'Must not commit', 'groups': ['fixture'], 'parents': [], 'rights': 'fixture'}))
        self.assertEqual(status, 409)
        self.assertEqual(canonical_bytes(self.external / 'alpha'), before)
        self.assertEqual([item['id'] for item in self.records()], [record['id']])

    def test_legacy_mutations_are_unavailable_before_and_after_open(self):
        for opened in (False, True):
            if opened:
                self.create()
            before = canonical_bytes(self.external)
            for path in ('/api/samples', '/api/workbench/import', '/api/workspace/runs',
                         '/api/releases', '/api/workspace/datasets'):
                with self.subTest(opened=opened, path=path):
                    status, value = self.request(path, {'kind': 'image', 'image': 'fixture', 'name': 'Must not write'})
                    self.assertIn(status, (403, 404, 405, 409), value)
            self.assertEqual(canonical_bytes(self.external), before)
            self.assertEqual(list((self.path / 'control').rglob('*.png')), [])

    def test_real_deferred_sql_failure_returns_committed_receipt_and_explicit_recovery(self):
        self.create()
        selected = self.state()
        projection_schema = self.workspace._projection.schema
        # A real deferred PostgreSQL trigger fails the outer SQL COMMIT, after
        # canonical publication. It exists only in this disposable projection.
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            function = sql.Identifier(projection_schema, 'qa_reject_projection_commit')
            table = sql.Identifier(projection_schema, 'workbench_records')
            connection.execute(sql.SQL('''CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql
                AS $$ BEGIN RAISE EXCEPTION 'Disposable QA deferred commit failure'; END; $$''').format(function))
            connection.execute(sql.SQL('''CREATE CONSTRAINT TRIGGER qa_reject_projection_commit
                AFTER INSERT ON {} DEFERRABLE INITIALLY DEFERRED
                FOR EACH ROW EXECUTE FUNCTION {}()''').format(table, function))
        asset = {'name': 'Committed despite unavailable SQL 山', 'text': TEXT,
                 'groups': ['recovery'], 'parents': [], 'rights': 'Owned synthetic recovery fixture'}
        original = self.envelope(selected, asset=asset)
        status, error = self.request(API + '/import-text', original)
        self.assertEqual(status, 503, error)
        self.assertEqual(error['code'], 'projection_unavailable')
        receipt = error['receipt']
        self.assertEqual(receipt['committed'], True)
        self.assertEqual(receipt['selected'], True)
        self.assertEqual(receipt['project_id'], selected['project']['project_id'])
        self.assertEqual(receipt['request_key'], original['request_key'])
        self.assertNotEqual(receipt['checkpoint'], selected['project']['checkpoint'])
        before_recovery = canonical_bytes(self.external / 'alpha')
        manifest = json.loads(before_recovery['.tuldok/project.json'])
        self.assertEqual(manifest['checkpoint'], receipt['checkpoint'])
        recovery = self.state()
        self.assertEqual(recovery['state'], 'recovery_required')
        self.assertEqual(recovery['available_actions'], ['open'])
        self.assertEqual(recovery['recovery']['reason'], 'projection_unavailable')
        status, denied = self.request(API + '/save', self.envelope(recovery))
        self.assertEqual(status, 503, denied)
        self.assertEqual(canonical_bytes(self.external / 'alpha'), before_recovery)
        self.action('open', recovery, root='fixture', directory='alpha')
        recovered = self.state()
        self.assertEqual(recovered['state'], 'open')
        self.assertEqual(recovered['project']['checkpoint'], receipt['checkpoint'])
        self.assertNotEqual(self.workspace._projection.schema, projection_schema)
        records = self.records(recovered)
        self.assertEqual(len(records), 1)
        self.assertEqual(self.detail(records[0]['id'])['record']['text'], TEXT)
        # Reconcile the exact durable request with its old checkpoint and the
        # new process binding. A committed operation cannot be duplicated.
        status, replayed = self.request(API + '/import-text', dict(original, binding=recovered['binding']))
        self.assertEqual(status, 200, replayed)
        self.assertEqual(replayed['record']['id'], records[0]['id'])
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(canonical_bytes(self.external / 'alpha'), before_recovery)

    @unittest.skipUnless(importlib.util.find_spec('mcp') and importlib.util.find_spec('anyio'),
                         'Requires the pinned optional MCP environment for real adapter acceptance')
    def test_real_owner_sdk_cli_and_agent_sdk_mcp_share_authenticated_project(self):
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from tuldok_client import ProjectFilesClient

        repository = Path(__file__).resolve().parents[1]
        owner_client = agent_api.ProjectFilesOwnerClient(self.origin, self.owner.token, self.owner.catalog_id, timeout=15)
        bootstrapped = owner_client.bootstrap()
        self.assertEqual(bootstrapped['identity']['kind'], 'owner')
        self.assertIn('project_files.new', bootstrapped['operations'])
        owner_files = ProjectFilesClient(owner_client)
        initial = owner_files.status()
        opened = owner_files.new(root='fixture', directory='adapter', name='SDK CLI MCP café 山',
                                 **self.envelope(initial))
        with self.owner.bound(self.workspace):
            credential = self.workspace.access.issue({'label': 'Real adapter fixture agent', 'scopes': ['inspect', 'edit']})
        agent = agent_api.AgentClient(self.origin, credential['token'], self.owner.catalog_id, timeout=15)
        self.assertEqual(agent.bootstrap()['identity']['kind'], 'agent')
        with self.assertRaises(agent_api.AgentAPIError) as wrong_identity:
            agent_api.AgentClient(self.origin, self.owner.token, self.owner.catalog_id, timeout=15).bootstrap()
        self.assertEqual(wrong_identity.exception.code, 'unauthenticated')
        files = ProjectFilesClient(agent)
        imported = files.import_text({'name': 'Actual adapters 山', 'text': TEXT, 'groups': ['adapters'],
                                     'parents': [], 'rights': 'Owned synthetic adapter fixture'},
                                    **self.envelope(opened))
        record = imported['record']
        annotation = {'revision': record['revision'], 'source_revision': record['source_revision'],
                      'task': 'text_corpus', 'annotation': {'note': 'Agent-authored historical note 山'},
                      'groups': ['adapters'], 'review': 'draft'}
        annotated = files.annotate(record['id'], annotation, **self.envelope(self.state()))
        self.assertEqual(annotated['record']['annotation'], annotation['annotation'])
        stable = self.state()
        before = canonical_bytes(self.external / 'adapter')
        denied = agent.call('project_files.close', self.envelope(stable))
        self.assertEqual(denied['status'], 403)
        denied_review = dict(annotation, revision=annotated['record']['revision'], review='human_reviewed')
        denied = agent.call('project_files.annotate', dict(self.envelope(stable),
                            record_id=record['id'], annotation=denied_review))
        self.assertEqual(denied['status'], 403)
        self.assertEqual(canonical_bytes(self.external / 'adapter'), before)
        query_arguments = {'binding': stable['binding'], 'checkpoint': stable['project']['checkpoint'], 'limit': 1}
        queried = agent.call('project_files.query', query_arguments)
        self.assertEqual(queried['status'], 200)
        self.assertEqual([item['id'] for item in queried['result']['items']], [record['id']])
        self.assertNotIn('text', queried['result']['items'][0], 'The list returns bounded summaries')
        print('Actual adapter SDK authoring and authorization assertions passed', flush=True)

        def configuration(name, token):
            token_file, config_file = self.path / (name + '.token'), self.path / (name + '.config.json')
            token_file.write_text(token + '\n'); token_file.chmod(0o600)
            config_file.write_text(json.dumps({'endpoint': self.origin, 'catalog_id': self.owner.catalog_id,
                                              'token_file': str(token_file), 'timeout': 15}))
            config_file.chmod(0o600)
            return config_file

        owner_config = configuration('adapter-owner', self.owner.token)
        agent_config = configuration('adapter-agent', credential['token'])
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('TULDOK_', 'PG'))}
        environment['PYTHONDONTWRITEBYTECODE'] = '1'

        def owner_cli(action, current, **extra):
            arguments = self.envelope(current)
            command = [sys.executable, str(repository / 'project_cli.py'), '--config', str(owner_config),
                       '--owner-project-files', 'file-' + action,
                       '--binding', arguments['binding'], '--expected-checkpoint',
                       arguments['expected_checkpoint'] or 'null', '--request-key', arguments['request_key']]
            for key, value in extra.items():
                command.extend(['--' + key, value])
            result = subprocess.run(command, cwd=repository, env=environment,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(self.owner.token, result.stdout + result.stderr)
            return json.loads(result.stdout)

        self.assertEqual(owner_cli('save', stable)['project'], stable['project'])
        closed = owner_cli('close', self.state())
        self.assertEqual(closed['state'], 'no_project_open')
        reopened = owner_cli('open', closed, root='fixture', directory='adapter')
        self.assertEqual(reopened['project'], stable['project'])
        expected = self.detail(record['id'])
        print('Actual owner CLI Save/Close/Open assertions passed', flush=True)

        async def exercise():
            started = time.monotonic()
            parameters = StdioServerParameters(command=sys.executable,
                args=[str(repository / 'mcp_stdio.py'), '--config', str(agent_config)],
                cwd=str(repository), env=environment)
            with (self.path / 'actual-mcp.stderr').open('w+') as errors:
                async with stdio_client(parameters, errlog=errors) as (reader, writer):
                    async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as session:
                        await session.initialize()
                        print(json.dumps({'actual_mcp_initialize_seconds': time.monotonic() - started,
                                          'initialize_deadline_seconds': 20}), flush=True)
                        tools = {tool.name for tool in (await session.list_tools()).tools}
                        self.assertTrue({'project_files_status', 'project_files_query', 'project_files_get',
                                         'project_files_annotate'} <= tools)

                        async def tool(name, arguments, expected_status=200):
                            response = await session.call_tool(name.replace('.', '_'), arguments)
                            self.assertEqual(response.isError, expected_status >= 400)
                            envelope = response.structuredContent
                            self.assertEqual(envelope['status'], expected_status, envelope)
                            self.assertEqual(json.loads(response.content[0].text), envelope)
                            return envelope['result']

                        current = await tool('project_files.status', {})
                        selected = {'binding': current['binding'], 'checkpoint': current['project']['checkpoint']}
                        found = await tool('project_files.query', dict(selected, limit=1))
                        self.assertEqual([item['id'] for item in found['items']], [record['id']])
                        actual = await tool('project_files.get', dict(selected, record_id=record['id'], history_limit=4))
                        self.assertEqual(actual['record'], expected['record'])
                        self.assertEqual(actual['history'], expected['history'])
                        mcp_annotation = dict(annotation, revision=actual['record']['revision'],
                                              annotation={'note': 'Actual MCP retained note café 🧪'})
                        saved = await tool('project_files.annotate', dict(self.envelope(current),
                                           record_id=record['id'], annotation=mcp_annotation))
                        self.assertEqual(saved['record']['annotation'], mcp_annotation['annotation'])
                        after_edit = await tool('project_files.get', dict(binding=saved['binding'],
                            checkpoint=saved['checkpoint'], record_id=record['id'], history_limit=4))
                        self.assertEqual(len(after_edit['history']), 3)
                        self.assertTrue(any(item['annotation'] == annotation['annotation']
                                            for item in after_edit['history']))
                        before_revocation = canonical_bytes(self.external / 'adapter')
                        with self.owner.bound(self.workspace):
                            self.workspace.access.revoke(credential['identity']['credential_id'])
                        refusal = await tool('project_files.status', {}, 401)
                        self.assertEqual(refusal['code'], 'unauthenticated')
                        self.assertEqual(agent.call('project_files.status', {})['status'], 401)
                        self.assertEqual(canonical_bytes(self.external / 'adapter'), before_revocation)
                errors.seek(0)
                self.assertNotIn(credential['token'], errors.read())

        anyio.run(exercise)


if __name__ == '__main__':
    unittest.main()
