"""Negotiated file-project contracts and thin consumer fault boundaries.

Controlled HTTP replies prove client correlation/refusal, not disk durability.
The optional real SDK subprocess proves registry-driven MCP forwarding.
"""
import copy
import importlib.util
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import json
import os
from pathlib import Path
import select
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import agent_api as api
import project_cli
from tuldok_client import ProjectFilesClient

CATALOG, BINDING, PROJECT, RECORD = ('a' * 32, 'b' * 32, 'c' * 32, 'd' * 32)
CHECKPOINT, OTHER = 'e' * 64, 'f' * 64
KEY = 'file-request-0001'
ROOT = Path(__file__).resolve().parents[1]
ACTIONS = ['new', 'open', 'save', 'close', 'query', 'get', 'import_text', 'annotate']


def state(opened=True):
    return {'format': 'project_files_state_v1', 'binding': BINDING,
        'state': 'open' if opened else 'no_project_open', 'roots': ['fixture'],
        'project': {'project_id': PROJECT, 'name': 'Text project', 'checkpoint': CHECKPOINT} if opened else None,
        'available_actions': ACTIONS if opened else ['new', 'open']}


def record():
    return {'id': RECORD, 'kind': 'text', 'name': 'Greeting', 'text': 'Hello world',
        'groups': ['source'], 'parents': [], 'provenance': {'method': 'import',
        'rights': 'unknown', 'normalization': 'NFC; LF newlines'},
        'task': 'text_classification', 'annotation': {'label': 'greeting'},
        'review': 'draft', 'revision': 1, 'source_revision': 1,
        'created_at': '2026-10-22T12:00:00+00:00', 'updated_at': '2026-10-22T12:00:00+00:00'}


def result():
    return {'binding': BINDING, 'project_id': PROJECT, 'checkpoint': CHECKPOINT,
        'record': record(), 'history': [record()], 'next_history_before_revision': None}


def bound():
    return {'binding': BINDING, 'expected_checkpoint': CHECKPOINT, 'request_key': KEY}


def client(reply, *, owner=False):
    client_type = api.ProjectFilesOwnerClient if owner else api.AgentClient
    value = client_type('http://127.0.0.1:12345', 'fixture-agent-token-for-client-tests', CATALOG)
    def request(method, path, body=None, **kwargs):
        if path == '/api/access/session':
            return {'status': 200, 'result': {'kind': 'owner' if owner else 'agent', 'catalog_id': CATALOG}}
        if path == '/api/workspace/context':
            return {'status': 200, 'result': {'dataset_id': CATALOG}}
        if path == '/api/agent/capabilities':
            return {'status': 200, 'result': api.capabilities(CATALOG)}
        return copy.deepcopy(reply)
    value._request = Mock(side_effect=request)
    return value


class M2Contracts(unittest.TestCase):
    def test_fixed_consumers_cover_all_m2_operations_and_preserve_m1(self):
        sdk = ProjectFilesClient(Mock())
        cli = project_cli.parser()
        for name in api.PROJECT_FILES_M2:
            action = name.split('.')[1]
            self.assertTrue(callable(getattr(sdk, action)), name)
            parsed = cli.parse_args(['--config', '/not-read', 'file-' + action.replace('_', '-'), '--arguments', '/not-read'])
            self.assertEqual(parsed.command, 'file-' + action.replace('_', '-'))
            tool, = api.tool_definitions({name: 1})
            self.assertEqual(tool['inputSchema'], api.operation(name)['inputSchema'])
        for action in ('model_publish', 'recipe_prepare', 'data_annotate', 'lineage_record', 'expose_holdout'):
            self.assertEqual(api.contract('project_files.' + action)['authority'], 'agent')
        for action in ('study_create', 'study_save', 'source_register'):
            self.assertEqual(api.contract('project_files.' + action)['authority'], 'owner')
        self.assertEqual(api.REGISTRY_DIGEST, api._LEGACY_DIGEST)

    def test_full_histories_have_smaller_bounds_than_summary_pages(self):
        for action in ('data_history', 'data_response_history', 'data_preference_history'):
            args = dict(binding=BINDING, checkpoint=CHECKPOINT, record_id=RECORD, offset=0, limit=4)
            api.validate_arguments('project_files.' + action, args)
            with self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.' + action, dict(args, limit=5))
        with self.assertRaises(api.AgentAPIError):
            api.validate_arguments('project_files.data_query', dict(binding=BINDING, checkpoint=CHECKPOINT, limit=41))

    def test_inline_imports_retain_aggregate_decoded_byte_bound(self):
        import base64
        blob = base64.b64encode(b'a' * (api.INLINE_LIMIT // 2 + 1)).decode()
        arguments = dict(bound(), files={'mesh.ply': blob, 'mesh.json': blob}, groups=['source'])
        with self.assertRaises(api.AgentAPIError) as caught:
            api.validate_arguments('project_files.data_import_mesh', arguments)
        self.assertEqual(caught.exception.code, 'too_large')

    def test_sdk_checks_binding_checkpoint_target_and_page_correlation(self):
        arguments = dict(binding=BINDING, checkpoint=CHECKPOINT, record_id=RECORD)
        good = dict(binding=BINDING, project_id=PROJECT, checkpoint=CHECKPOINT, value={'id': RECORD, 'kind': 'image'})
        # Bootstrap one real negotiated SDK; changing only its controlled response
        # keeps this a transport claim and avoids any canonical storage substitute.
        raw = client({'status': 200, 'result': good})
        self.assertEqual(ProjectFilesClient(raw).data_get(**arguments), good)
        for update in ({'binding': PROJECT}, {'checkpoint': OTHER}, {'value': {'id': PROJECT}}):
            raw._request = Mock(return_value={'status': 200, 'result': {**good, **update}})
            with self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(raw).data_get(**arguments)
        page = dict(good, value={'items': [{'id': RECORD}], 'offset': 0, 'limit': 40, 'total': 41})
        raw._request = Mock(return_value={'status': 200, 'result': page})
        with self.assertRaises(api.AgentAPIError):
            ProjectFilesClient(raw).studies(binding=BINDING, checkpoint=CHECKPOINT)
        receipt = {'committed': True, 'selected': True, 'project_id': PROJECT, 'checkpoint': OTHER, 'request_key': 'different-request'}
        raw._request = Mock(return_value={'status': 503, 'result': {'error': 'Projection unavailable', 'code': 'projection_unavailable', 'receipt': receipt}})
        with self.assertRaises(api.AgentAPIError) as caught:
            ProjectFilesClient(raw).data_rights(record_id=RECORD, revision=1, source_revision=1, note='authored', **bound())
        self.assertEqual(caught.exception.code, 'transport')

    def test_validator_cache_is_isolated_and_rejects_invalid_or_referenced_schemas(self):
        schema = {'type': 'string', 'maxLength': 2}
        first = api._validator(schema)
        schema['maxLength'] = 8
        self.assertIsNotNone(next(first.iter_errors('long'), None))
        self.assertIsNone(next(api._validator(schema).iter_errors('long'), None))
        for invalid in ({'type': 'unknown'}, {'$ref': 'https://invalid.example/schema'}, {'properties': {'value': {'$dynamicRef': '#anything'}}}):
            with self.assertRaises(api.AgentAPIError):
                api._validator(invalid)

    def test_validator_cache_evicts_by_exact_schema_byte_budget(self):
        with api._SCHEMA_CACHE_LOCK:
            saved, saved_bytes = api._SCHEMA_CACHE.copy(), api._SCHEMA_CACHE_BYTES
            api._SCHEMA_CACHE.clear(); api._SCHEMA_CACHE_BYTES = 0
        try:
            with patch.object(api, '_SCHEMA_CACHE_LIMIT_BYTES', 120), patch.object(api, '_SCHEMA_CACHE_LIMIT_ENTRIES', 2):
                for count in range(1, 6):
                    api._validator({'type': 'string', 'maxLength': count})
                    self.assertLessEqual(len(api._SCHEMA_CACHE), 2)
                    self.assertEqual(api._SCHEMA_CACHE_BYTES, sum(map(len, api._SCHEMA_CACHE)))
                    self.assertLessEqual(api._SCHEMA_CACHE_BYTES, 120)
                before = api._SCHEMA_CACHE_BYTES
                api._validator({'type': 'string', 'description': 'large schema' * 20})
                self.assertEqual(api._SCHEMA_CACHE_BYTES, before)
        finally:
            with api._SCHEMA_CACHE_LOCK:
                api._SCHEMA_CACHE.clear(); api._SCHEMA_CACHE.update(saved); api._SCHEMA_CACHE_BYTES = saved_bytes

    def test_retained_run_document_segment_checks_exact_selection_and_bytes(self):
        import base64
        arguments = dict(binding=BINDING, checkpoint=CHECKPOINT, run_id=RECORD,
                         origin_catalog_id=PROJECT, expected_sha256=OTHER, offset=0, limit=4)
        value = dict(format='project_run_document_segment_v1', origin_catalog_id=PROJECT,
                     run_id=RECORD, sha256=OTHER, bytes=6, offset=0, limit=4,
                     base64=base64.b64encode(b'abcd').decode(), next_offset=4)
        result = dict(binding=BINDING, project_id=PROJECT, checkpoint=CHECKPOINT, value=value)
        raw = client({'status': 200, 'result': result})
        self.assertEqual(ProjectFilesClient(raw).run_document_segment(**arguments), result)
        for change in ({'run_id': PROJECT}, {'sha256': CHECKPOINT}, {'offset': 1},
                       {'next_offset': None}, {'base64': base64.b64encode(b'ab').decode()}):
            raw._request = Mock(return_value={'status': 200, 'result': dict(result, value=dict(value, **change))})
            with self.assertRaises(api.AgentAPIError):
                ProjectFilesClient(raw).run_document_segment(**arguments)

    def test_browser_fixed_routes_are_generated_from_the_registry(self):
        source = (ROOT / 'static/project-files.js').read_text()
        routes = json.loads(re.search(r'/\* PROJECT_FILES_ROUTES_START \*/\s*(.*?)\s*/\* PROJECT_FILES_ROUTES_END \*/', source, re.S)[1])
        expected = {name: {'method': api.operation(name)['method'], 'path': api.operation(name)['path'],
                          'mutation': api.operation(name)['side_effects']} for name in api.PROJECT_FILES_M2}
        self.assertEqual(routes, expected)


class Contracts(unittest.TestCase):
    def test_additive_negotiation_preserves_installed_legacy_and_mcp_contracts(self):
        self.assertEqual(api.REGISTRY_DIGEST, api._LEGACY_DIGEST)
        selected = api.negotiate(api.capabilities(CATALOG), CATALOG)
        for action in ['status', *ACTIONS]:
            name = 'project_files.' + action
            self.assertEqual(selected[name], 1)
            contract = api.contract(name)
            self.assertEqual(contract['retry'], 'read' if action in ('status', 'query', 'get') else 'receipt')
            definition, = api.tool_definitions({name: 1})
            self.assertEqual(definition['name'], name.replace('.', '_'))
            self.assertEqual(definition['inputSchema'], api.operation(name)['inputSchema'])
            self.assertEqual(definition['outputSchema'], api.operation(name)['outputSchema'])

    def test_browser_contract_pins_are_current_registry_output(self):
        source = (ROOT / 'static/project-files.js').read_text()
        pins = json.loads(re.search(r'/\* PROJECT_FILES_CONTRACTS_START \*/\s*(.*?)\s*/\* PROJECT_FILES_CONTRACTS_END \*/', source, re.S)[1])
        self.assertEqual(pins, {name: api.contract(name)['sha256'] for name in api._CONTRACTS if name.startswith('project_files.')})
        for name, digest in pins.items():
            self.assertEqual(api.selected_header(name), name + '/1/' + digest)

    def test_reads_pin_binding_checkpoint_and_path_record_without_body(self):
        arguments = {'record_id': RECORD, 'binding': BINDING, 'checkpoint': CHECKPOINT}
        method, path, body = api.project_request('project_files.get', arguments)
        self.assertEqual((method, body), ('GET', None))
        self.assertEqual(path, f'/api/workspace/project-files/records/{RECORD}?binding={BINDING}&checkpoint={CHECKPOINT}')
        for missing in ('binding', 'checkpoint', 'record_id'):
            with self.subTest(missing=missing), self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.get', {key: value for key, value in arguments.items() if key != missing})

    def test_closed_text_inputs_refuse_execution_fields_and_wrong_annotation_family(self):
        good = dict(bound(), asset={'text': 'hello', 'groups': ['source']})
        for bad in (dict(good, execution=True), dict(good, asset={**good['asset'], 'script': 'run'}),
                    dict(good, asset={'text': 'hello', 'groups': ['source', 'source']}),
                    dict(good, asset={'text': 'hello', 'groups': ['source'], 'rights': ''}),
                    dict(good, expected_checkpoint=None), dict(good, binding=PROJECT + 'bad')):
            with self.subTest(bad=bad), self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.import_text', bad)
        annotation = {'revision': 1, 'source_revision': 1, 'task': 'text_corpus',
            'annotation': {'note': 'Reviewed'}, 'groups': ['source'], 'review': 'human_reviewed'}
        api.validate_arguments('project_files.annotate', dict(bound(), record_id=RECORD, annotation=annotation))
        for change in ({'annotation': {'label': 'wrong task'}}, {'task': 'image_caption'},
                       {'review': 'programmatically_verified'}, {'verified_provenance': {}}):
            with self.subTest(change=change), self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.annotate', dict(bound(), record_id=RECORD, annotation={**annotation, **change}))
        for checkpoint in (None, CHECKPOINT):
            api.validate_arguments('project_files.open', {**bound(), 'expected_checkpoint': checkpoint,
                'root': 'fixture', 'directory': 'project'})

    def test_bounded_pages_cover_maximum_unicode_source_without_full_history_response(self):
        large = record(); large['text'] = '🌸' * 200000
        api.validate_arguments('project_files.import_text', dict(bound(), asset={'text': large['text'], 'groups': ['source']}))
        large['task'] = 'text_entities'
        large['annotation'] = {'spans': [{'label': '🌸' * 80, 'start': index, 'end': index + 1} for index in range(500)]}
        large['groups'] = ['🌸' * 117 + str(index) for index in range(30)]
        large['parents'] = list(large['groups']); large['provenance']['rights'] = '🌸' * 1000
        large['name'] = '🌸' * 200; large['revision'] = 5
        page = dict(result(), record=large, history=[dict(large, revision=revision) for revision in (5, 4, 3, 2)], next_history_before_revision=2)
        api.validate_output('project_files.get', {'status': 200, 'result': page})
        self.assertLess(len(api.encoded(page)), api.RESPONSE_LIMIT)
        self.assertGreater(len(api.encoded(dict(page, history=[large] * 6))), api.RESPONSE_LIMIT)
        api.validate_arguments('project_files.get', {'binding': BINDING, 'checkpoint': CHECKPOINT, 'record_id': RECORD, 'before_revision': 5, 'history_limit': 4})
        for field, wrong in [('history_limit', 5), ('before_revision', 0)]:
            with self.subTest(field=field), self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.get', {'binding': BINDING, 'checkpoint': CHECKPOINT, 'record_id': RECORD, field: wrong})
        summary = {key: value for key, value in record().items() if key in api.PROJECT_FILES_SUMMARY['properties']}
        query = {'binding': BINDING, 'project_id': PROJECT, 'checkpoint': CHECKPOINT, 'items': [summary], 'next_after_id': RECORD}
        api.validate_output('project_files.query', {'status': 200, 'result': query})
        query['items'][0]['text'] = 'must use get'
        with self.assertRaises(api.AgentAPIError):
            api.validate_output('project_files.query', {'status': 200, 'result': query})

    def test_recovery_state_and_committed_error_receipt_are_closed(self):
        recovery = dict(state(), state='recovery_required', available_actions=['open'], recovery={
            'action': 'open', 'root': 'fixture', 'directory': 'project',
            'reason': 'unknown_publication', 'request_key': KEY})
        api.validate_output('project_files.status', {'status': 200, 'result': recovery})
        bad = copy.deepcopy(recovery); bad['available_actions'] = ['open', 'save']
        with self.assertRaises(api.AgentAPIError):
            api.validate_output('project_files.status', {'status': 200, 'result': bad})
        receipt = {'committed': True, 'selected': True, 'project_id': PROJECT, 'checkpoint': CHECKPOINT, 'request_key': KEY}
        api.validate_output('project_files.annotate', {'status': 503, 'result': {'code': 'projection_unavailable', 'error': 'Reopen to reconstruct.', 'receipt': receipt}})
        with self.assertRaises(api.AgentAPIError):
            api.validate_output('project_files.annotate', {'status': 503, 'result': {'error': 'Unknown', 'receipt': dict(receipt, secret='reject')}})

    def test_closed_record_output_rejects_unknown_and_inconsistent_history(self):
        api.validate_output('project_files.get', {'status': 200, 'result': result()})
        variants = []
        for path, value in ((('record', 'secret'), 'leak'), (('record', 'kind'), 'image'),
                            (('record', 'annotation'), {'note': 'wrong task'}),
                            (('record', 'provenance'), {'method': 'generated'})):
            bad = result(); bad[path[0]][path[1]] = value; variants.append(bad)
        bad = result(); bad['history'][0]['id'] = PROJECT; variants.append(bad)
        bad = result(); bad['history'].append(record()); variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad), self.assertRaises(api.AgentAPIError):
                api.validate_output('project_files.get', {'status': 200, 'result': bad})


class Consumers(unittest.TestCase):
    def test_owner_file_client_keeps_unrelated_operations_outside_authority(self):
        raw = client({'status': 200, 'result': state()}, owner=True)
        self.assertEqual(ProjectFilesClient(raw).save(**bound()), state())
        self.assertEqual(set(raw.selected_contracts()), api.ProjectFilesOwnerClient.OPERATIONS)
        self.assertEqual(raw._request.call_count, 4)
        raw._request.reset_mock()
        with self.assertRaises(api.AgentAPIError) as failure:
            raw.call('data.get', {'record_id': RECORD})
        self.assertEqual(failure.exception.code, 'operation_unsupported')
        raw._request.assert_not_called()
        for action in ('new', 'open', 'save', 'close'):
            self.assertEqual(api.contract('project_files.' + action)['authority'], 'owner')

    def test_cli_explicit_owner_mode_supports_only_file_commands(self):
        output, errors = io.StringIO(), io.StringIO()
        raw = client({'status': 200, 'result': state()}, owner=True)
        args = ['--config', '/not-read.json', '--owner-project-files', 'file-save',
            '--binding', BINDING, '--expected-checkpoint', CHECKPOINT, '--request-key', KEY]
        with patch.object(project_cli.ProjectFilesOwnerClient, 'from_config', return_value=raw), patch('sys.stdout', output), patch('sys.stderr', errors):
            self.assertEqual(project_cli.main(args), 0, errors.getvalue())
        self.assertEqual(json.loads(output.getvalue()), state())
        self.assertEqual(raw._request.call_args.kwargs['selection'], ('project_files.save', 1))
        with patch.object(project_cli.ProjectFilesOwnerClient, 'from_config') as configure, patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()) as errors:
            self.assertEqual(project_cli.main(['--config', '/not-read.json', '--owner-project-files', 'coordinator-status']), 1)
            self.assertEqual(json.loads(errors.getvalue())['code'], 'configuration')
            configure.assert_not_called()

    def test_sdk_negotiates_and_forwards_exact_body_once(self):
        raw = client({'status': 201, 'result': result()})
        files = ProjectFilesClient(raw)
        asset = {'text': 'Hello world', 'groups': ['source']}
        self.assertEqual(files.import_text(asset, **bound()), result())
        calls = raw._request.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[-1].args, ('POST', '/api/workspace/project-files/import-text', dict(bound(), asset=asset)))
        self.assertEqual(calls[-1].kwargs['selection'], ('project_files.import_text', 1))
        self.assertEqual(asset, {'text': 'Hello world', 'groups': ['source']})

    def test_wrong_binding_checkpoint_and_record_are_not_accepted_as_current(self):
        args = {'record_id': RECORD, 'binding': BINDING, 'checkpoint': CHECKPOINT}
        for key, wrong in (('binding', PROJECT), ('checkpoint', OTHER), ('record_id', PROJECT)):
            reply = result()
            if key == 'record_id':
                reply['record']['id'] = wrong; reply['history'][0]['id'] = wrong
            else:
                reply[key] = wrong
            raw = client({'status': 200, 'result': reply})
            with self.subTest(key=key), self.assertRaises(api.AgentAPIError) as failure:
                raw.call('project_files.get', args)
            self.assertEqual(failure.exception.code, 'transport')
            self.assertEqual(raw._request.call_count, 4)

    def test_cursor_parameters_and_committed_receipts_survive_sdk_cli_and_http(self):
        receipt = {'committed': True, 'selected': True, 'project_id': PROJECT, 'checkpoint': CHECKPOINT, 'request_key': KEY}
        raw = client({'status': 503, 'result': {'code': 'projection_unavailable', 'error': 'Saved; rebuild projection.', 'receipt': receipt}})
        with self.assertRaises(api.AgentAPIError) as failure:
            ProjectFilesClient(raw).save(**bound())
        self.assertEqual(failure.exception.receipt, receipt)
        status, value = self.cli(raw, ['file-save', '--binding', BINDING, '--expected-checkpoint', CHECKPOINT, '--request-key', KEY])
        self.assertEqual((status, value['receipt']), (1, receipt))
        raw = client({'status': 200, 'result': result()})
        ProjectFilesClient(raw).get(RECORD, binding=BINDING, checkpoint=CHECKPOINT, before_revision=2, history_limit=4)
        self.assertIn('before_revision=2&history_limit=4', raw._request.call_args.args[1])
        # The real transport must validate and preserve only a file-operation
        # receipt, and reject unknown fields or credential-bearing paths.
        envelope = {'error': 'Saved; rebuild projection.', 'code': 'projection_unavailable', 'receipt': receipt}
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                body = api.encoded(envelope)
                self.send_response(503); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *_): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(thread.join, 5); self.addCleanup(server.shutdown)
        transport = api.AgentClient(f'http://127.0.0.1:{server.server_port}', 'fixture-agent-token-for-client-tests', CATALOG)
        selected = ('project_files.save', 1)
        self.assertEqual(transport._request('POST', '/api/workspace/project-files/save', bound(), selection=selected)['result']['receipt'], receipt)
        unicode_body = dict(bound(), asset={'text': '🌸' * 200000, 'groups': ['source']})
        self.assertEqual(transport._request('POST', '/api/workspace/project-files/import-text', unicode_body, selection=('project_files.import_text', 1))['result']['receipt'], receipt)
        for bad in (dict(receipt, unexpected='reject'), dict(receipt, selected=False, root=transport._token, directory='project')):
            envelope['receipt'] = bad
            with self.assertRaises(api.AgentAPIError) as failure:
                transport._request('POST', '/api/workspace/project-files/save', bound(), selection=selected)
            self.assertEqual(failure.exception.code, 'transport')

    def test_typed_stale_busy_unknown_and_projection_failures_have_no_retry(self):
        for code, status in [('stale_checkpoint', 409), ('busy', 409), ('outcome_unknown', 503), ('projection_unavailable', 503)]:
            raw = client({'status': status, 'result': {'code': code, 'error': 'Inspect status before retrying.'}})
            with self.subTest(code=code), self.assertRaises(api.AgentAPIError) as failure:
                ProjectFilesClient(raw).save(**bound())
            self.assertEqual((failure.exception.code, failure.exception.status), (code, status))
            self.assertEqual(raw._request.call_count, 4)

    def cli(self, raw, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(project_cli.AgentClient, 'from_config', return_value=raw), patch('sys.stdout', output), patch('sys.stderr', errors):
            status = project_cli.main(['--config', '/not-read.json', *arguments])
        return status, json.loads(output.getvalue() if status == 0 else errors.getvalue())

    def test_cli_named_lifecycle_and_json_text_commands_use_registry(self):
        for action in ('new', 'open', 'save', 'close'):
            args = ['file-' + action, '--binding', BINDING, '--expected-checkpoint', 'null' if action in ('new', 'open') else CHECKPOINT, '--request-key', KEY]
            if action in ('new', 'open'): args += ['--root', 'fixture', '--directory', 'project']
            if action == 'new': args += ['--name', 'My text project']
            raw = client({'status': 200, 'result': state(opened=action != 'close')})
            status, value = self.cli(raw, args)
            self.assertEqual(status, 0, value)
            self.assertEqual(raw._request.call_args.kwargs['selection'], ('project_files.' + action, 1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'arguments.json'
            path.write_text(json.dumps({'binding': BINDING, 'checkpoint': CHECKPOINT, 'record_id': RECORD}))
            raw = client({'status': 200, 'result': result()})
            status, value = self.cli(raw, ['file-get', '--arguments', str(path)])
            self.assertEqual(status, 0, value)
            self.assertEqual(raw._request.call_args.kwargs['selection'], ('project_files.get', 1))
        raw = client({'status': 200, 'result': state(False)})
        self.assertEqual(self.cli(raw, ['file-status']), (0, state(False)))

    def test_cli_invalid_binding_rejects_before_network(self):
        raw = client({'status': 200, 'result': state()})
        status, value = self.cli(raw, ['file-save', '--binding', 'invalid', '--expected-checkpoint', CHECKPOINT, '--request-key', KEY])
        self.assertEqual((status, value['code']), (1, 'invalid'))
        raw._request.assert_not_called()


SDK_AVAILABLE = all(importlib.util.find_spec(name) for name in ('mcp', 'anyio', 'jsonschema'))


@unittest.skipUnless(SDK_AVAILABLE, 'Optional MCP SDK is required for actual stdio forwarding evidence')
class MCPForwarding(unittest.TestCase):
    def test_main_bootstraps_before_serving_and_bootstrap_failure_prevents_serving(self):
        import anyio
        import mcp_stdio
        order = []
        client = Mock()
        client.bootstrap.side_effect = lambda: order.append('bootstrap')

        def serve_ready(function, selected, *args):
            self.assertIs(function, mcp_stdio.serve)
            self.assertIs(selected, client)
            self.assertEqual(order, ['bootstrap'])
            order.append('serve')

        with patch.object(api.AgentClient, 'from_config', return_value=client), patch.object(
                anyio, 'run', side_effect=serve_ready) as run:
            self.assertEqual(mcp_stdio.main(['--config', 'fixture-only']), 0)
            self.assertEqual(order, ['bootstrap', 'serve'])
            run.assert_called_once()
        client.bootstrap.side_effect = api.AgentAPIError('Fixture authentication refusal.', 'unauthenticated', 401)
        with patch.object(api.AgentClient, 'from_config', return_value=client), patch.object(
                anyio, 'run') as run, patch('sys.stderr', new_callable=io.StringIO):
            self.assertEqual(mcp_stdio.main(['--config', 'fixture-only']), 1)
            run.assert_not_called()

    def test_registry_tool_status_and_typed_stale_error_cross_real_stdio(self):
        # Deliberately simulated HTTP owner: this claim is SDK/stdio forwarding.
        script = f'''
import anyio, agent_api
from mcp_stdio import serve
class Client:
    def selected_contracts(self): return {{'project_files.status':1,'project_files.save':1}}
    def tool_definitions(self): return agent_api.tool_definitions(self.selected_contracts())
    def call(self,name,arguments):
        if name=='project_files_status': return {{'status':200,'result':{state(False)!r}}}
        return {{'status':409,'result':{{'code':'stale_checkpoint','error':'Checkpoint changed.'}}}}
anyio.run(serve,Client())
'''
        process = subprocess.Popen([sys.executable, '-c', script], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            if process.poll() is None: process.terminate()
            try: process.communicate(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.communicate(timeout=5)
        self.addCleanup(cleanup)
        def send(method, request_id=None, params=None):
            value = {'jsonrpc': '2.0', 'method': method}
            if request_id is not None: value['id'] = request_id
            if params is not None: value['params'] = params
            process.stdin.write(json.dumps(value).encode() + b'\n'); process.stdin.flush()
        def read():
            raw, deadline = bytearray(), time.monotonic() + 12
            while not raw.endswith(b'\n'):
                ready, _, _ = select.select([process.stdout], [], [], max(0, deadline-time.monotonic()))
                self.assertTrue(ready, 'MCP reply deadline')
                block = os.read(process.stdout.fileno(), 1)
                self.assertTrue(block, 'MCP closed before reply')
                raw.extend(block)
            return json.loads(raw)
        send('initialize', 1, {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'project-files-test', 'version': '1'}})
        self.assertEqual(read()['id'], 1)
        send('notifications/initialized')
        send('tools/list', 2)
        self.assertEqual({tool['name'] for tool in read()['result']['tools']}, {'project_files_status', 'project_files_save'})
        send('tools/call', 3, {'name': 'project_files_status', 'arguments': {}})
        value = read()['result']; self.assertFalse(value['isError']); self.assertEqual(value['structuredContent']['result'], state(False))
        send('tools/call', 4, {'name': 'project_files_save', 'arguments': bound()})
        value = read()['result']; self.assertTrue(value['isError']); self.assertEqual(value['structuredContent']['result']['code'], 'stale_checkpoint')


if __name__ == '__main__':
    unittest.main()
