"""One frozen M5 SDK/CLI/MCP workflow over the actual legacy HTTP controller.

Only a disposable fixture is authored. Stop uses the original live Dataset;
the two client configurations contain independent current owner credentials.
No runtime, provider, model preparation or scientific execution is qualified.
"""
from datetime import timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid

import agent_api as api
from backup_metadata import tree_manifest
from project_transfer import _assert_unchanged
from tuldok_client import ProjectTransferClient
import test_project_transfer_controller as controller_fixture

ROOT = Path(__file__).resolve().parents[1]
SDK_AVAILABLE = all(importlib.util.find_spec(name) for name in ('mcp', 'anyio', 'jsonschema'))


def frozen_subject():
    name = os.environ.get('TULDOK_M5_CLIENTS_MANIFEST')
    if not name:
        raise AssertionError('Provide the immutable M5 clients qualification manifest')
    path = Path(name)
    value = json.loads(path.read_text())
    if value['qualification_copy'] != str(ROOT):
        raise AssertionError('Run this acceptance test in the selected immutable copy')
    current = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in value['files']}
    if current != value['files']:
        raise AssertionError('Immutable M5 client source changed before acceptance')
    return dict(manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        parent_manifest_sha256=value['parent_manifest_sha256'], files=current)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ProjectTransferClientsHTTP(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SDK_AVAILABLE, 'Qualification requires the approved optional MCP dependencies')
        self.subject = frozen_subject()
        self.started, self.performed = time.monotonic(), []
        self.pins = {name: api.contract(name)['sha256'] for name in sorted(api.PROJECT_TRANSFER_OPERATIONS)}
        self.assertEqual(len(self.pins), 5)
        # Reuse only fixture authoring/cleanup, never inherit its TestCase or run
        # its controller test methods as a second acceptance campaign.
        self.fixture = controller_fixture.TransferControllerTests('test_actual_http_source_control_handoff_report_and_extraction')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.receipt)
        f = self.fixture
        f.workspace.transfer_controller = f.controller  # Same attachment as normal application startup.
        self.server = f.server()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith(('TULDOK_', 'PG'))}
        self.environment['PYTHONDONTWRITEBYTECODE'] = '1'
        self.source_config = self.config('source', f.source_token, f.dataset.db.dataset_id)
        self.control_config = self.config('control', f.control_token, f.workspace.db.dataset_id)

    def receipt(self):
        current = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in self.subject['files']}
        output = Path(os.environ.get('TULDOK_QA_OUTPUT_ROOT', '/workspace/scratch/tuldok-save-load-qa/artifacts')) / 'm5-clients'
        output.mkdir(parents=True, exist_ok=True)
        value = dict(test=self.id(), seconds=round(time.monotonic() - self.started, 3), performed=self.performed,
            qualification_manifest_sha256=self.subject['manifest_sha256'],
            parent_manifest_sha256=self.subject['parent_manifest_sha256'], source_stable=current == self.subject['files'],
            contract_sha256=self.pins, test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fixture='Actual owner SDK, CLI subprocesses and MCP SDK stdio over real HTTP; disposable legacy/control PG catalogs; authored text and inert script only')
        (output / (self._testMethodName + '-' + uuid.uuid4().hex + '.json')).write_text(json.dumps(value, indent=2) + '\n')
        self.assertEqual(current, self.subject['files'], 'Immutable M5 source changed during acceptance')

    def config(self, label, token, catalog_id):
        private = self.fixture.root / (label + '.token')
        config = self.fixture.root / (label + '.config.json')
        private.write_text(token + '\n'); private.chmod(0o600)
        config.write_text(json.dumps(dict(endpoint=self.origin, catalog_id=catalog_id, token_file=str(private), timeout=30)))
        config.chmod(0o600)
        return config

    def cli(self, config, action, *flags):
        result = subprocess.run([sys.executable, str(ROOT / 'project_cli.py'), '--config', str(config),
            'project-transfer', action, *flags], cwd=ROOT, env=self.environment, capture_output=True, text=True, timeout=45)
        for token in (self.fixture.source_token, self.fixture.control_token):
            self.assertNotIn(token, result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def parameters(self, config):
        from mcp import StdioServerParameters
        return StdioServerParameters(command=sys.executable, args=[str(ROOT / 'mcp_stdio.py'), '--config', str(config),
            '--project-transfer-owner'], cwd=str(ROOT), env=self.environment)

    async def tools(self, session):
        definitions = {tool.name: tool for tool in (await session.list_tools()).tools}
        expected = {api.operation(name)['mcp_name'] for name in api.PROJECT_TRANSFER_OPERATIONS}
        self.assertEqual(set(definitions), expected)
        preview = definitions[api.operation('project_transfer.preview')['mcp_name']]
        self.assertEqual(preview.inputSchema, api.operation('project_transfer.preview')['inputSchema'])
        self.assertEqual(preview.outputSchema, api.operation('project_transfer.preview')['outputSchema'])
        return definitions

    async def tool(self, session, action, arguments, status=200):
        name = 'project_transfer.' + action
        value = await session.call_tool(api.operation(name)['mcp_name'], arguments)
        envelope = value.structuredContent
        self.assertEqual(envelope['status'], status, envelope)
        self.assertEqual(value.isError, status >= 400)
        self.assertEqual(json.loads(value.content[0].text), envelope)
        api.validate_output(name, envelope)
        return envelope['result']

    def test_owner_handoff_and_single_extraction_through_sdk_cli_and_real_mcp(self):
        import anyio
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        f = self.fixture
        sentinel = f.root / 'must-not-execute'
        script = ('from pathlib import Path\nPath(' + repr(str(sentinel)) + ').write_text("executed")\n# exact inert Ω\r\n').encode()
        (f.registered / 'scripts').mkdir()
        (f.registered / 'scripts' / 'inert.py').write_bytes(script)
        f.selection['roots']['working_files'] = [dict(kind='script', path='scripts/inert.py')]
        source_transport = api.ProjectTransferOwnerClient.from_config(self.source_config)
        source = ProjectTransferClient(source_transport)
        bootstrap = source_transport.bootstrap()
        self.assertEqual(bootstrap['identity']['catalog_id'], f.dataset.db.dataset_id)
        self.assertEqual(set(bootstrap['operations']), api.PROJECT_TRANSFER_OPERATIONS)
        self.assertEqual(source_transport.selected_contracts(), {name: 1 for name in self.pins})
        initial = source.status()
        live = source.preview(f.selection, binding=initial['binding'])
        self.assertEqual(live['phase'], 'source_live')
        self.assertFalse(live['report']['can_extract'])
        first = source.report_page(binding=live['binding'], report_sha256=live['report']['report_sha256'], section='included', limit=1)
        second = self.cli(self.source_config, 'report-page', '--binding', live['binding'], '--report-sha256', live['report']['report_sha256'],
            '--section', 'included', '--offset', '1', '--limit', '1')
        self.assertEqual((first['offset'], second['offset'], len(second['items'])), (0, 1, 1))
        self.assertNotEqual(first['items'][0], second['items'][0])
        self.assertEqual(first['report_sha256'], second['report_sha256'])
        config_before = self.source_config.read_bytes()
        self.performed.append('Source owner SDK negotiates exactly five pins, previews read-only; named CLI pages the next report item')

        async def exercise():
            source_errors = f.root / 'source-mcp.stderr'
            with source_errors.open('w+') as diagnostics:
                async with stdio_client(self.parameters(self.source_config), errlog=diagnostics) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as source_session:
                        await source_session.initialize()
                        await self.tools(source_session)
                        before = await self.tool(source_session, 'status', {})
                        self.assertEqual(before['binding'], live['binding'])
                        working = await self.tool(source_session, 'report_page', dict(binding=live['binding'], report_sha256=live['report']['report_sha256'], section='working_files', offset=0, limit=40))
                        self.assertEqual(working['items'], [dict(kind='script', path='scripts/inert.py', sha256=hashlib.sha256(script).hexdigest(), bytes=len(script))])
                        self.performed.append('Source MCP exposes only five pinned tools and reads exact inert script availability')

                        stopped = source.stop(binding=live['binding'], report_sha256=live['report']['report_sha256'],
                            backup_root='output', backup_directory='backup', destination_root='output', directory='extracted')
                        self.assertEqual(stopped['phase'], 'source_stopped')
                        self.assertNotEqual(stopped['binding'], live['binding'])
                        baseline = tree_manifest(f.dataset.path)
                        with self.assertRaises(api.AgentAPIError) as fenced: source.status()
                        self.assertEqual(fenced.exception.code, 'authentication_handoff')
                        denied = await self.tool(source_session, 'status', {}, status=401)
                        self.assertIn(denied['code'], ('unauthenticated', 'forbidden'))
                        self.assertEqual(self.source_config.read_bytes(), config_before)
                        self.assertEqual(source_transport.catalog_id, f.dataset.db.dataset_id)

                        # New credentials AND catalog configuration are supplied
                        # explicitly; no old client learns a replacement token.
                        control_transport = api.ProjectTransferOwnerClient.from_config(self.control_config)
                        control = ProjectTransferClient(control_transport)
                        current = control_transport.bootstrap()
                        self.assertEqual(current['identity']['catalog_id'], f.workspace.db.dataset_id)
                        self.assertEqual(set(current['operations']), api.PROJECT_TRANSFER_OPERATIONS)
                        fresh = control.status()
                        selection_file = f.root / 'explicit-selection.json'
                        selection_file.write_text(json.dumps(f.selection))
                        selection_file.chmod(0o600)
                        ready = self.cli(self.control_config, 'preview', '--binding', fresh['binding'], '--selection', str(selection_file))
                        self.assertTrue(ready['report']['can_extract'])
                        self.assertNotEqual(ready['report']['report_sha256'], live['report']['report_sha256'])
                        self.assertEqual(ready['binding'], fresh['binding'])
                        self.performed.append('One explicit SDK Stop; old SDK fences locally and old MCP receives401; new independently configured owner SDK/CLI identify the control catalog')

                        arguments = dict(binding=ready['binding'], report_sha256=ready['report']['report_sha256'],
                            destination_root='output', directory='extracted', name='Client extraction Ω', request_key='m5-client-extraction-key')
                        with (f.root / 'control-mcp.stderr').open('w+') as errors:
                            async with stdio_client(self.parameters(self.control_config), errlog=errors) as (reader, writer):
                                async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as session:
                                    await session.initialize()
                                    await self.tools(session)
                                    result = await self.tool(session, 'extract', arguments)
                            errors.seek(0)
                            self.assertNotIn(f.source_token, errors.read())
                            errors.seek(0)
                            self.assertNotIn(f.control_token, errors.read())
                        self.assertTrue(result['receipt']['committed'])
                        self.assertFalse(result['receipt']['replayed'])
                        self.assertTrue(result['selection']['selected'])
                        self.assertEqual(result['receipt']['verification']['active_data_records'], 1)
                        self.assertEqual(result['receipt']['source']['catalog_id'], f.dataset.db.dataset_id)
                        self.assertNotIn(result['receipt']['project_id'], (f.dataset.db.dataset_id, f.workspace.db.dataset_id))
                        replay = control.extract(**arguments)
                        self.assertTrue(replay['receipt']['replayed'])
                        self.assertTrue(replay['selection']['selected'])
                        self.assertEqual(replay['receipt']['project_id'], result['receipt']['project_id'])
                        self.assertEqual(replay['receipt']['checkpoint'], result['receipt']['checkpoint'])
                        self.assertEqual(replay['selection']['state']['project']['checkpoint'], replay['receipt']['checkpoint'])
                        self.assertEqual(tree_manifest(f.dataset.path), baseline)
                        _assert_unchanged(f.controller._source)
                        self.performed.append('Fresh-control MCP publishes once and selects inertly; SDK exact-key retry reconciles the selected writer with the same verified project/head')
                diagnostics.seek(0)
                self.assertNotIn(f.source_token, diagnostics.read())
                diagnostics.seek(0)
                self.assertNotIn(f.control_token, diagnostics.read())
            return result

        result = anyio.run(exercise)
        self.assertEqual((f.publication / 'extracted' / 'scripts' / 'inert.py').read_bytes(), script)
        self.assertFalse(sentinel.exists())
        self.assertEqual(f.workspace._store.snapshot()['project_id'], result['receipt']['project_id'])
        canonical = json.dumps(f.workspace._store.snapshot(), ensure_ascii=False)
        self.assertNotIn(f.source_token, canonical)
        self.assertNotIn(f.control_token, canonical)
        self.performed.append('Original source remains unchanged; destination retains exact script bytes; no script executes or credentials enter canonical facts')


if __name__ == '__main__':
    unittest.main()
