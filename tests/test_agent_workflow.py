"""Real official-SDK stdio client → authenticated HTTP → durable domain workflow.

Run this gate with the optional pinned agent dependencies installed explicitly.
Base environments without that optional capability report a skip, not acceptance.
The subprocess is the production bridge; the executable is the neutral byte-copy
fixture. No model, scientific metric, mocked queue or synthetic completion claim.
"""
import asyncio
import base64
import copy
from contextlib import asynccontextmanager
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import unittest
import uuid
import zipfile

from test_agent_http import AgentHTTPCase

ROOT = Path(__file__).resolve().parents[1]
SDK_AVAILABLE = importlib.util.find_spec('mcp') is not None and importlib.util.find_spec('jsonschema') is not None


def private_file(path, raw):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as target:
        target.write(raw)


@unittest.skipUnless(SDK_AVAILABLE, 'Optional pinned MCP/jsonschema environment required; not workflow acceptance')
class AgentWorkflowTests(AgentHTTPCase):
    def setUp(self):
        super().setUp()
        # Same neutral executable; larger bounded input admits an actual canonical
        # text release rather than pretending that an arbitrary blob is reviewed.
        self.definition['inputs']['sample']['max_bytes'] = 128 * 1024
        self.definition['outputs'][0]['max_bytes'] = 128 * 1024
        self.definition['resources']['max_output_bytes'] = 256 * 1024
        self.definition_raw = json.dumps(self.definition).encode()
        self.manifest['id'] = uuid.uuid4().hex
        self.manifest['recipes'][0]['sha256'] = hashlib.sha256(self.definition_raw).hexdigest()
        (self.project_path / 'recipe.json').write_bytes(self.definition_raw)
        (self.project_path / 'project.json').write_text(json.dumps(self.manifest))
        self.editor = self.issue_http(['inspect', 'edit', 'freeze', 'execute', 'cancel'])
        self.config_count = 0

    @asynccontextmanager
    async def mcp(self, credential):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.config_count += 1
        token_file = self.path / f'agent-token-{self.config_count}'
        config_file = self.path / f'agent-config-{self.config_count}.json'
        private_file(token_file, (credential['token'] + '\n').encode('ascii'))
        private_file(config_file, json.dumps({'endpoint': self.root, 'catalog_id': self.owner.catalog_id,
                                              'token_file': str(token_file), 'timeout': 30}).encode())
        arguments = [str(ROOT / 'mcp_stdio.py'), '--config', str(config_file)]
        if getattr(self, 'observer_database', None) is not None:
            arguments.extend(['--observe-database', str(self.observer_database)])
        parameters = StdioServerParameters(command=sys.executable, args=arguments, cwd=str(ROOT))
        log = self.path / f'agent-stderr-{self.config_count}.log'
        with log.open('w+') as errors:
            async with stdio_client(parameters, errlog=errors) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    initialized = await session.initialize()
                    self.assertEqual(initialized.protocolVersion, '2025-06-18')
                    self.assertIsNotNone(initialized.capabilities.tools)
                    self.assertIsNone(initialized.capabilities.resources)
                    self.assertIsNone(initialized.capabilities.prompts)
                    yield session
            errors.seek(0)
            self.assertNotIn(credential['token'], errors.read())

    async def tool(self, session, operation, arguments=None, status=200):
        response = await session.call_tool(operation.replace('.', '_'), arguments or {})
        envelope = response.structuredContent
        self.assertIsInstance(envelope, dict, operation + ' must preserve the typed status/result envelope')
        self.assertEqual(set(envelope), {'status', 'result'})
        self.assertEqual(json.loads(response.content[0].text), envelope)
        self.assertEqual(envelope['status'], status, {'operation': operation, 'response': envelope})
        self.assertEqual(response.isError, status >= 400)
        return envelope['result']

    async def invalid_tool(self, session, operation, arguments):
        from mcp.shared.exceptions import McpError
        with self.assertRaises(McpError) as refused:
            await session.call_tool(operation.replace('.', '_'), arguments)
        self.assertEqual(refused.exception.error.code, -32602)

    async def terminal(self, session, run_id, wanted='completed'):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            run = await self.tool(session, 'runs.get', {'run_id': run_id})
            if run['state'] in ('completed', 'failed', 'cancelled', 'unknown', 'interrupted'):
                self.assertEqual(run['state'], wanted, {key: run.get(key) for key in ('id', 'state', 'error')})
                self.assertEqual(run['custody_phase'], 'drained')
                return run
            await asyncio.sleep(.05)
        self.fail('Neutral agent Run did not reach the required terminal state: ' + run_id)

    async def artifact(self, session, run):
        item = next(item for item in run['artifacts'] if item['name'] == 'result.txt')
        pieces, offset = [], 0
        while True:
            part = await self.tool(session, 'runs.artifact_chunk', {'run_id': run['id'], 'name': item['name'],
                'expected_sha256': item['sha256'], 'offset': offset, 'max_bytes': 257})
            self.assertEqual(part['verification'], 'segment_read_whole_hash_unverified')
            raw = base64.b64decode(part['data_base64'], validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), part['segment_sha256'])
            self.assertEqual((part['offset'], part['bytes'], part['next_offset']), (offset, len(raw), offset + len(raw)))
            pieces.append(raw)
            offset = part['next_offset']
            if part['eof']:
                break
            self.assertGreater(len(raw), 0)
        raw = b''.join(pieces)
        self.assertEqual(len(raw), item['bytes'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
        return raw

    def approve_http(self, graph, preflight, actor):
        status, approval = self.http('/api/workspace/runs/approve-external',
            {'graph_id': graph['id'], 'graph_revision': graph['revision'],
             'expected_digest': preflight['material_sha256'], 'consumer_actor_id': actor}, self.owner.token)
        self.assertEqual(status, 201, approval)
        return approval

    def test_real_agent_draft_owner_review_freeze_approval_replay_restart_and_revocation(self):
        asyncio.run(self.workflow())

    def test_observed_real_workflow_preserves_mutation_authority_restart_and_privacy(self):
        import mcp_observer
        self.observer_database = self.path / 'mcp-observer.sqlite'
        asyncio.run(self.workflow())
        checked = mcp_observer.check_store(self.observer_database)
        self.assertEqual(checked['unfinished'], 0)
        with sqlite3.connect(self.observer_database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 3)
            for outcome, status in [('success', 201), ('domain-error', 409),
                                    ('permission-refusal', 403), ('permission-refusal', 401)]:
                self.assertGreater(db.execute("SELECT count(*) FROM events WHERE phase='returned' AND outcome=? AND http_status=?",
                                             (outcome, status)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM events e JOIN interactions i ON e.interaction=i.id WHERE i.operation='data_import_text' AND e.phase='dispatch'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM events e JOIN interactions i ON e.interaction=i.id WHERE i.operation='data_import_text' AND e.phase='returned' AND e.http_status=201").fetchone()[0], 1)
            self.assertGreater(db.execute("SELECT count(*) FROM events WHERE phase='terminal' AND outcome='invalid-parameters'").fetchone()[0], 0)
        raw = self.observer_database.read_bytes()
        for secret in (self.editor['token'], self.owner.token, self.owner.catalog_id,
                       str(self.path), 'Neutral reviewed text', 'project.json',
                       'Authored QA fixture', self.manifest['id']):
            self.assertNotIn(secret.encode(), raw)

    async def workflow(self):
        async with self.mcp(self.editor) as session:
            tools = await session.list_tools()
            names = {item.name for item in tools.tools}
            for required in ('data_save_draft', 'releases_freeze', 'graphs_preflight_external',
                             'runs_submit_external', 'runs_artifact_chunk', 'runs_expose_test'):
                self.assertIn(required, names)
            for forbidden in ('runs_approve_external', 'credentials_issue', 'data_approve_review', 'runs_retry'):
                self.assertNotIn(forbidden, names)
            identity = await self.tool(session, 'identity.get')
            self.assertEqual((identity['kind'], identity['actor_id']), ('agent', self.editor['identity']['actor_id']))
            project = await self.tool(session, 'projects.open', {'root': 'fixture', 'manifest_path': 'project.json'}, 201)
            self.assertEqual(project['id'], self.manifest['id'])
            recipe = await self.tool(session, 'recipes.inspect', {'project_id': project['id'],
                'reference_id': 'neutral', 'expected_sha256': hashlib.sha256(self.definition_raw).hexdigest()})
            self.assertEqual(recipe['definition']['id'], 'neutral')
            record = await self.tool(session, 'data.import_text', {'text': 'Neutral reviewed text: λ\n',
                'name': 'Agent-authored fixture', 'rights': 'Authored QA fixture', 'groups': ['p6-independent-source']}, 201)
            draft = {'record_id': record['id'], 'revision': record['revision'], 'source_revision': record['source_revision'],
                     'task': 'text_classification', 'annotation': {'label': '  neutral  '}, 'groups': record['groups'], 'review': 'draft'}
            await self.invalid_tool(session, 'data.save_draft', dict(draft, review='human_reviewed'))
            http_draft = {key: value for key, value in draft.items() if key != 'record_id'}
            self.assertEqual(self.http('/api/workbench/records/' + record['id'],
                dict(http_draft, review='human_reviewed'), self.editor['token'])[0], 403)
            saved = await self.tool(session, 'data.save_draft', draft)
            self.assertEqual((saved['review'], saved['annotation']), ('draft', {'label': 'neutral'}))
            await self.tool(session, 'data.save_draft', draft, 409)
            selection = {'format': 'canonical_v1', 'items': [{key: saved[key] for key in ('id', 'revision', 'source_revision')}],
                         'ratios': {'train': 100, 'validation': 0, 'test': 0}, 'seed': 42}
            blocked = await self.tool(session, 'releases.preview', selection)
            self.assertFalse(blocked['eligible'])
            self.assertTrue(blocked['blockers'])
            owner_review = dict(http_draft, revision=saved['revision'], annotation=saved['annotation'], review='human_reviewed')
            status, reviewed = self.http('/api/workbench/records/' + record['id'], owner_review, self.owner.token)
            self.assertEqual(status, 200, reviewed)
            selection['items'][0]['revision'] = reviewed['revision']
            preview = await self.tool(session, 'releases.preview', selection)
            self.assertTrue(preview['eligible'], preview)
            await self.tool(session, 'releases.freeze', dict(selection, preview_token='0' * 64), 409)
            release = await self.tool(session, 'releases.freeze', dict(selection, preview_token=preview['preview_token']), 201)
            status, archive = self.http(release['url'], token=self.owner.token, binary=True)
            self.assertEqual(status, 200)
            self.assertEqual(hashlib.sha256(archive).hexdigest(), release['id'])
            with zipfile.ZipFile(io.BytesIO(archive)) as package:
                frozen = json.loads(package.read('manifest.json'))
                self.assertEqual(frozen['records'][0]['annotation'], {'label': 'neutral'})
                self.assertEqual(frozen['records'][0]['review'], 'human_reviewed')
            graph = await self.tool(session, 'graphs.create_external', {'name': 'Neutral frozen bytes through agent',
                'project_id': project['id'], 'recipe_id': 'neutral', 'expected_sha256': hashlib.sha256(self.definition_raw).hexdigest(),
                'inputs': {'sample': {'kind': 'frozen_release', 'release_id': release['id'], 'expected_sha256': release['id']}}}, 201)
            changed = copy.deepcopy(graph)
            changed['name'] = 'Edited exact agent graph'
            graph = await self.tool(session, 'graphs.save', {'graph_id': graph['id'], 'revision': graph['revision'], 'document': changed})
            await self.tool(session, 'graphs.save', {'graph_id': graph['id'], 'revision': changed['revision'], 'document': changed}, 409)
            await self.tool(session, 'graphs.preflight_external', {'graph_id': graph['id'], 'revision': changed['revision']}, 409)
            preflight = await self.tool(session, 'graphs.preflight_external', {'graph_id': graph['id'], 'revision': graph['revision']})
            self.assertTrue(preflight['valid'])
            grant = self.approve_http(graph, preflight, self.editor['identity']['actor_id'])
            submission = {'graph_id': graph['id'], 'graph_revision': graph['revision'], 'expected_digest': preflight['material_sha256'],
                          'request_key': 'p6-neutral-' + uuid.uuid4().hex, 'approval_id': grant['id']}
            await self.invalid_tool(session, 'runs.submit_external', {key: value for key, value in submission.items() if key != 'approval_id'})
            self.assertEqual(self.http('/api/workspace/runs/approve-external', {}, self.editor['token'])[0], 403)
            self.assertEqual(self.http('/api/workspace/runs', {}, self.editor['token'])[0], 403)
            admitted = await self.tool(session, 'runs.submit_external', submission, 201)
            replay = await self.tool(session, 'runs.submit_external', submission, 201)
            self.assertEqual(replay['id'], admitted['id'])
            await self.tool(session, 'runs.submit_external', dict(submission, request_key='p6-reused-grant-' + uuid.uuid4().hex), 409)
            completed = await self.terminal(session, admitted['id'])
            self.assertEqual(await self.artifact(session, completed), archive)
            progress = await self.tool(session, 'runs.progress', {'run_id': completed['id']})
            self.assertEqual(progress['evidence'], 'custody_verified')
            await self.tool(session, 'runs.expose_test', {'run_id': completed['id'], 'reason': 'No exposure scope'}, 403)
            fresh_grant = self.approve_http(graph, preflight, self.editor['identity']['actor_id'])
            fresh_submission = dict(submission, request_key='p6-explicit-fresh-' + uuid.uuid4().hex, approval_id=fresh_grant['id'])
            fresh = await self.tool(session, 'runs.submit_external', fresh_submission, 201)
            self.assertNotEqual(fresh['id'], completed['id'])
            self.assertEqual(await self.artifact(session, await self.terminal(session, fresh['id'])), archive)
            all_runs = await self.tool(session, 'runs.list')
            self.assertEqual({run['id'] for run in all_runs}, {completed['id'], fresh['id']})
        # Disconnect is not a retry or revocation; restart the actual HTTP owner
        # and reconnect a new production stdio process using retained identity.
        self.reopen_http()
        async with self.mcp(self.editor) as session:
            replay = await self.tool(session, 'runs.submit_external', submission, 201)
            self.assertEqual(replay['id'], completed['id'])
            self.assertEqual(await self.artifact(session, replay), archive)
            status, _ = self.http('/api/access/credentials/' + self.editor['identity']['credential_id'] + '/revoke',
                                  {}, self.owner.token)
            self.assertEqual(status, 200)
            await self.tool(session, 'runs.get', {'run_id': completed['id']}, 401)
            await self.tool(session, 'runs.submit_external', submission, 401)
        scoped = self.issue_http(['inspect', 'expose-holdout'])
        async with self.mcp(scoped) as session:
            refusal = await self.tool(session, 'runs.expose_test',
                {'run_id': completed['id'], 'reason': 'Explicitly scoped request; neutral external has no classifier holdout'}, 409)
            self.assertEqual(refusal['code'], 'unsupported')
