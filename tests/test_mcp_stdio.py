"""Protocol boundary tests, with an authored HTTP stub (not workflow acceptance).

Real SDK processes/clients are exercised only in the optional agent environment.
Public authenticated HTTP/domain acceptance is owned by test_agent_workflow.
"""
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mcp_stdio as bridge

SDK_AVAILABLE = all(importlib.util.find_spec(name) for name in ('mcp', 'anyio', 'jsonschema'))
CHILD = r'''
import os, time, anyio, copy
import agent_api
from mcp_stdio import serve
if os.environ.get('TULDOK_TEST_NEW_VERSION'):
    operation=copy.deepcopy(agent_api._CONTRACTS['context.get'][1])
    operation['inputSchema']={'type':'object','properties':{'future':{'type':'boolean'}},
                              'required':['future'],'additionalProperties':False}
    agent_api._CONTRACTS['context.get'][2]=operation
class AuthoredClient:
    def selected_contracts(self):
        return ({'context.get':1} if os.environ.get('TULDOK_TEST_CONTEXT_ONLY') else
                {name:1 for name in agent_api._CONTRACTS})
    def tool_definitions(self):
        return agent_api.tool_definitions(self.selected_contracts())
    def call(self, name, arguments):
        gate = os.environ.get('TULDOK_TEST_GATE')
        if gate:
            deadline = time.monotonic() + 10
            while not os.path.exists(gate):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Authored test gate deadline')
                time.sleep(0.01)
        time.sleep(float(os.environ.get('TULDOK_TEST_DELAY', '0')))
        if os.environ.get('TULDOK_TEST_FAIL'):
            raise RuntimeError('SECRET_AUTH_TOKEN_MUST_NOT_LEAK')
        return {'status': 200, 'result': {'dataset_id': 'a' * 32, 'mode': 'real', 'observed': name,
            'payload': 'x' * int(os.environ.get('TULDOK_TEST_PAYLOAD', '0'))}}
anyio.run(serve, AuthoredClient())
'''


def request(method, request_id=1, params=None):
    value = {'jsonrpc': '2.0', 'id': request_id, 'method': method}
    if params is not None:
        value['params'] = params
    return value


def initialize(version='2025-06-18'):
    return request('initialize', params={'protocolVersion': version, 'capabilities': {},
        'clientInfo': {'name': 'authored-protocol-test', 'version': '1'}})


class FramingTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith('linux'), 'Linux pipe capacity controls required')
    def test_output_pipe_capacity_is_bounded_and_optional(self):
        import fcntl
        from unittest.mock import patch
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        original = fcntl.fcntl(write_fd, fcntl.F_GETPIPE_SZ)
        actual = bridge.prepare_output_pipe(write_fd)
        self.assertGreaterEqual(actual, original)
        self.assertLessEqual(actual, max(original, bridge.OUTPUT_PIPE_BYTES))
        def unavailable(fd, action, *values):
            if action == fcntl.F_SETPIPE_SZ:
                raise PermissionError('Authored unavailable capacity')
            return 65536
        with patch('fcntl.fcntl', side_effect=unavailable):
            self.assertEqual(bridge.prepare_output_pipe(write_fd), 65536)
        self.assertIsNone(bridge.prepare_output_pipe(-1))

    def test_strict_json_bounds_unicode_duplicates_and_finite_values(self):
        self.assertEqual(bridge.parse_frame(b'{"id":1}\n'), {'id': 1})
        bad = [b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'{"x":1e999}\n',
               b'{"x":"\\ud800"}\n', b'\xff\n', b'{}', b'[]\n', b'null\n',
               b'{"x":' + b'[' * 66 + b'0' + b']' * 66 + b'}\n',
               b' ' * bridge.INPUT_LIMIT + b'{}\n']
        for raw in bad:
            with self.subTest(raw=raw[:60]), self.assertRaises(bridge.FrameError):
                bridge.parse_frame(raw)

    def test_nul_in_initialize_metadata_and_object_keys_is_refused(self):
        for value in (initialize(), {'jsonrpc': '2.0', 'method': 'ping', 'params': {'_meta': {'bad\x00key': 1}}}):
            if value.get('method') == 'initialize':
                value['params']['clientInfo']['name'] = 'client\x00name'
            with self.subTest(value=value), self.assertRaisesRegex(bridge.FrameError, 'NUL'):
                bridge.parse_frame(json.dumps(value).encode('utf-8') + b'\n')

    def test_profile_negotiates_only_admitted_version_and_requires_notification(self):
        profile = bridge.Profile(['context_get'])
        forwarded, error = profile.accept(initialize('1999-01-01'))
        self.assertIsNone(error)
        self.assertEqual(forwarded['params']['protocolVersion'], bridge.PROTOCOL_VERSION)
        profile.admitted(forwarded)
        self.assertEqual(profile.accept(request('tools/list', 2))[1]['error']['code'], -32000)
        profile.replied({'id': 1, 'result': {}})
        self.assertIsNotNone(profile.accept(request('tools/list', 2))[1])
        profile.accept({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        self.assertEqual(profile.accept(request('tools/list', 2)), (request('tools/list', 2), None))
        self.assertIsNotNone(profile.accept(initialize())[1])

    def test_invalid_ids_unknown_notifications_and_methods(self):
        profile = bridge.Profile([])
        for bad in (True, 1.2, None, 2 ** 54, 'x' * 129):
            with self.subTest(bad=bad):
                self.assertEqual(profile.accept(request('ping', bad))[1]['error']['code'], -32600)
        self.assertEqual(profile.accept(request('ping', '')), (request('ping', ''), None))
        self.assertEqual(profile.accept({'jsonrpc': '2.0', 'method': 'notifications/future'}), (None, None))
        self.assertEqual(profile.accept(request('resources/list'))[1]['error']['code'], -32601)

    def test_malformed_tool_names_and_arguments_are_typed_refusals(self):
        profile = bridge.Profile(['context_get'])
        profile.state = 'ready'
        for name in ([], {}, None, True, 1):
            with self.subTest(name=name):
                value, refusal = profile.accept(request('tools/call', 2, {'name': name, 'arguments': {}}))
                self.assertIsNone(value)
                self.assertEqual(refusal['error']['code'], -32602)
        for arguments in ([], None, 'text', True):
            with self.subTest(arguments=arguments):
                value, refusal = profile.accept(request('tools/call', 2, {'name': 'context_get', 'arguments': arguments}))
                self.assertIsNone(value)
                self.assertEqual(refusal['error']['code'], -32602)

    def test_final_encoding_cap_counts_structured_and_text_copies(self):
        value = {'data': 'x' * (bridge.OUTPUT_LIMIT // 2)}
        result = {'structuredContent': value, 'content': [{'type': 'text', 'text': json.dumps(value)}]}
        with self.assertRaises(bridge.FrameError):
            bridge.encode_response({'jsonrpc': '2.0', 'id': 1, 'result': result})


@unittest.skipUnless(SDK_AVAILABLE, 'Optional MCP environment required; skipped tests are not protocol qualification')
class SDKProcessTests(unittest.TestCase):
    def test_bound_recipe_uses_the_same_selected_contract(self):
        import agent_api as api
        from mcp.types import Tool
        selected=api.negotiate(api.capabilities('b'*32),'b'*32)
        self.assertEqual(selected['recipes.inspect'],4)
        for contracts in ({'recipes.inspect':2},{'recipes.inspect':3},selected):
            version=contracts['recipes.inspect']
            with self.subTest(version=version):
                definition=next(item for item in api.tool_definitions(contracts)
                                if item['name']==api.operation('recipes.inspect')['mcp_name'])
                tool=Tool.model_validate(definition)
                contract=api.operation('recipes.inspect',version)
                self.assertEqual(tool.outputSchema,contract['outputSchema'])
                self.assertEqual(tool.inputSchema,contract['inputSchema'])

    def start(self, **env):
        process = subprocess.Popen([sys.executable, '-c', CHILD], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, **env))
        self.addCleanup(self.cleanup, process)
        return process

    def cleanup(self, process):
        if process.stdin is not None and process.stdin.closed:
            process.stdin = None
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)

    def send(self, process, value):
        process.stdin.write(json.dumps(value).encode() + b'\n')
        process.stdin.flush()

    def read(self, process, timeout=8):
        deadline = time.monotonic() + timeout
        raw = bytearray()
        while not raw.endswith(b'\n'):
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0, 'Protocol reply exceeded test deadline')
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            self.assertTrue(ready, 'No protocol reply')
            block = os.read(process.stdout.fileno(), 1)
            self.assertTrue(block, 'Bridge closed before reply')
            raw.extend(block)
            self.assertLessEqual(len(raw), bridge.OUTPUT_LIMIT)
        return json.loads(raw)

    def ready(self, process, version=bridge.PROTOCOL_VERSION):
        self.send(process, initialize(version))
        value = self.read(process)
        self.assertEqual(value['result']['protocolVersion'], bridge.PROTOCOL_VERSION)
        self.assertEqual(value['result']['capabilities'], {'tools': {}})
        self.send(process, {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        return value

    def test_real_sdk_lifecycle_versions_and_closed_capabilities(self):
        for version in ('2025-06-18', '2024-11-05', '2099-01-01'):
            with self.subTest(version=version):
                process = self.start()
                self.ready(process, version)
                self.send(process, request('ping', 2))
                self.assertEqual(self.read(process)['result'], {})
                self.send(process, request('ping', ''))
                self.assertEqual(self.read(process), {'jsonrpc': '2.0', 'id': '', 'result': {}})
                self.send(process, initialize())
                self.assertIn('error', self.read(process))
                process.stdin.close()
                self.assertEqual(process.wait(timeout=8), 0)
                self.assertEqual(process.stderr.read(), b'')

    def test_selected_tools_and_older_selected_schema_are_used_by_real_sdk(self):
        process=self.start(TULDOK_TEST_CONTEXT_ONLY='1',TULDOK_TEST_NEW_VERSION='1')
        self.ready(process)
        self.send(process,request('tools/list',2))
        tools=self.read(process)['result']['tools']
        self.assertEqual([item['name'] for item in tools],['context_get'])
        self.send(process,request('tools/call',3,{'name':'context_get','arguments':{}}))
        result=self.read(process)['result']
        self.assertEqual(result['structuredContent']['status'],200)
        self.assertFalse(result['isError'])
        self.send(process,request('tools/call',4,{'name':'projects_open','arguments':{}}))
        self.assertEqual(self.read(process)['error']['code'],-32602)

    def test_invalid_schema_is_protocol_error_and_never_dispatched(self):
        process = self.start()
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {'unexpected': True}}))
        result = self.read(process)
        self.assertEqual(result, {'jsonrpc': '2.0', 'id': 2,
            'error': {'code': -32602, 'message': 'Invalid tool arguments'}})
        self.send(process, request('ping', 3))
        self.assertEqual(self.read(process)['result'], {})

    def test_unknown_method_malformed_json_and_incomplete_initialization(self):
        process = self.start()
        self.send(process, request('tools/list'))
        self.assertIn('error', self.read(process))
        process.stdin.write(b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n')
        process.stdin.flush()
        self.assertEqual(self.read(process)['error']['code'], -32700)
        self.send(process, request('resources/list', 3))
        self.assertEqual(self.read(process)['error']['code'], -32601)
        self.ready(process)
        for name in ([], {}):
            self.send(process, request('tools/call', 4, {'name': name, 'arguments': {}}))
            self.assertEqual(self.read(process)['error']['code'], -32602)
        self.send(process, request('tools/call', 4, {'name': 'unknown', 'arguments': {}}))
        self.assertEqual(self.read(process)['error']['code'], -32602)

    def test_serial_calls_refuse_overlap_and_do_not_retry_on_exception(self):
        process = self.start(TULDOK_TEST_DELAY='0.3', TULDOK_TEST_FAIL='1')
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        self.send(process, request('tools/call', 3, {'name': 'context_get', 'arguments': {}}))
        results = [self.read(process), self.read(process)]
        busy = next(item for item in results if item['id'] == 3)
        failed = next(item for item in results if item['id'] == 2)
        self.assertEqual(busy['error']['code'], -32000)
        self.assertEqual(failed['result']['structuredContent']['result']['code'], 'bridge_failure')
        self.assertNotIn('SECRET_AUTH', json.dumps(results))

    def test_duplicate_pending_id_refusal_does_not_consume_original_reply(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        gate = Path(directory.name) / 'release'
        process = self.start(TULDOK_TEST_GATE=str(gate))
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        self.send(process, request('ping', 2))
        refusal = self.read(process)
        self.assertEqual(refusal, {'jsonrpc': '2.0', 'id': None, 'error': {
            'code': -32600, 'message': 'Request ID is already in use'}})
        gate.touch()
        completed = self.read(process)
        self.assertEqual(completed['id'], 2)
        self.assertEqual(completed['result']['structuredContent']['status'], 200)
        self.send(process, request('ping', 3))
        self.assertEqual(self.read(process), {'jsonrpc': '2.0', 'id': 3, 'result': {}})

    def test_completed_request_id_can_be_reused_for_a_distinct_call(self):
        process = self.start()
        self.ready(process)
        for _ in range(2):
            self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
            completed = self.read(process)
            self.assertEqual(completed['id'], 2)
            self.assertEqual(completed['result']['structuredContent']['status'], 200)

    def test_partial_frame_at_eof_has_one_parse_refusal_and_no_raw_diagnostic(self):
        process = self.start()
        process.stdin.write(b'{"private_path":"/private/ISSUE59_SENTINEL"')
        process.stdin.close()
        self.assertEqual(self.read(process), {'jsonrpc': '2.0', 'id': None, 'error': {
            'code': -32700, 'message': 'Incomplete JSON line at EOF'}})
        self.assertEqual(process.wait(timeout=8), 0)
        self.assertEqual(process.stdout.read(), b'')
        self.assertEqual(process.stderr.read(), b'')

    def test_eof_and_oversized_line_are_bounded(self):
        process = self.start()
        process.stdin.write(b' ' * (bridge.INPUT_LIMIT + 1))
        process.stdin.flush()
        self.assertEqual(self.read(process)['error']['code'], -32700)
        process.stdin.close()
        self.assertEqual(process.wait(timeout=8), 0)

    def test_final_encoded_oversize_is_explicit_tool_error(self):
        process = self.start(TULDOK_TEST_PAYLOAD=str(17 * 1024 * 1024))
        self.ready(process)
        self.send(process, request('tools/call', 2, {'name': 'context_get', 'arguments': {}}))
        result = self.read(process)['result']
        self.assertTrue(result['isError'])
        self.assertEqual(result['structuredContent']['result']['code'], 'response_too_large')

    def test_official_sdk_client_negotiation_list_and_call(self):
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=['-c', CHILD], cwd=str(ROOT))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    self.assertEqual(initialized.protocolVersion, bridge.PROTOCOL_VERSION)
                    tools = await session.list_tools()
                    self.assertIn('context_get', [tool.name for tool in tools.tools])
                    result = await session.call_tool('context_get', {})
                    self.assertFalse(result.isError)
                    self.assertEqual(result.structuredContent['status'], 200)
        anyio.run(exercise)


if __name__ == '__main__':
    unittest.main()
