"""Optional tools-only MCP stdio bridge to the existing authenticated HTTP API.

The SDK owns typed requests, sessions and results. This module owns a bounded
POSIX stdio transport and the explicitly narrower product protocol profile.
It never imports catalog/domain owners or retries an HTTP operation.
"""
import argparse
import json
import math
import os
import stat
import sys

PROTOCOL_VERSION = '2025-06-18'
INPUT_LIMIT = 1024 * 1024
OUTPUT_LIMIT = 32 * 1024 * 1024
DEPTH_LIMIT = 64
WRITE_SECONDS = 5
OUTPUT_PIPE_BYTES = 1024 * 1024


def prepare_output_pipe(output_fd):
    """Bound local kernel buffering for large frames; retain ordinary backpressure."""
    try:
        import fcntl
        if not stat.S_ISFIFO(os.fstat(output_fd).st_mode):
            return None
        capacity = fcntl.fcntl(output_fd, fcntl.F_GETPIPE_SZ)
        if capacity < OUTPUT_PIPE_BYTES:
            try:
                fcntl.fcntl(output_fd, fcntl.F_SETPIPE_SZ, OUTPUT_PIPE_BYTES)
            except OSError:
                # Some hosts prohibit resizing. The same bounded writer still owns
                # timeout and incomplete delivery; never change global pipe policy.
                pass
        return fcntl.fcntl(output_fd, fcntl.F_GETPIPE_SZ)
    except (ImportError, AttributeError, OSError):
        return None


class FrameError(ValueError):
    """Public bounded framing error; never includes raw client input."""
    def __init__(self, message, code=-32700):
        super().__init__(message)
        self.code = code


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FrameError('Duplicate JSON member')
        result[key] = value
    return result


def _constant(value):
    raise FrameError('Nonfinite JSON number')


def parse_frame(raw):
    """Decode one complete bounded object, before constructing SDK models."""
    if not isinstance(raw, bytes) or len(raw) > INPUT_LIMIT or not raw.endswith(b'\n'):
        raise FrameError('Expected a complete JSON line within 1 MiB')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=_constant)
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > DEPTH_LIMIT:
                raise FrameError('JSON nesting exceeds 64 levels')
            if isinstance(item, dict):
                pending.extend((v, depth + 1) for v in item.values())
                for key in item:
                    if '\x00' in key:
                        raise FrameError('NUL is not permitted in JSON text')
                    key.encode('utf-8')
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
            elif isinstance(item, str):
                if '\x00' in item:
                    raise FrameError('NUL is not permitted in JSON text')
                item.encode('utf-8')
            elif isinstance(item, float) and not math.isfinite(item):
                raise FrameError('Nonfinite JSON number')
        if not isinstance(value, dict):
            raise FrameError('JSON-RPC batches and scalar messages are unsupported', -32600)
        return value
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        if isinstance(exc, FrameError):
            raise
        raise FrameError('Invalid UTF-8 JSON object') from None


def error_response(request_id, code, message):
    return {'jsonrpc': '2.0', 'id': request_id,
            'error': {'code': code, 'message': message}}


def tool_error(code, message, status=502):
    return {'status': status, 'result': {'code': code, 'error': message}}


def encode_response(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False,
                     separators=(',', ':')).encode('utf-8') + b'\n'
    if len(raw) > OUTPUT_LIMIT:
        raise FrameError('Encoded MCP response exceeds 32 MiB')
    return raw


class Profile:
    """Only product restrictions; SDK still validates and handles each request."""
    def __init__(self, tool_names):
        self.tool_names = frozenset(tool_names)
        self.state = 'new'
        self.pending = None
        self.pending_method = None

    def accept(self, value):
        """Return (forwarded message, direct error); ignore notifications as needed."""
        request_id = value.get('id')
        has_id = 'id' in value
        valid_id = (type(request_id) is int and abs(request_id) <= 2 ** 53 - 1 or
                    isinstance(request_id, str) and len(request_id) <= 128)
        if value.get('jsonrpc') != '2.0' or (has_id and not valid_id):
            return None, error_response(None, -32600, 'Invalid JSON-RPC request')
        method = value.get('method')
        if not isinstance(method, str) or not method or len(method) > 128:
            return None, error_response(request_id if valid_id else None, -32600,
                                        'Invalid JSON-RPC method')
        if set(value) - {'jsonrpc', 'id', 'method', 'params'}:
            return None, error_response(request_id if valid_id else None, -32600,
                                        'Unexpected JSON-RPC member')
        if not has_id:
            # No request cancellation can roll back durable HTTP work. All unknown
            # notifications, including cancellation, are ignored without a reply.
            if method == 'notifications/initialized' and self.state == 'offered':
                if value.get('params', {}) not in ({}, None):
                    return None, None
                self.state = 'ready'
                return value, None
            return None, None
        if self.pending is not None:
            if request_id == self.pending:
                return None, error_response(None, -32600, 'Request ID is already in use')
            return None, error_response(request_id, -32000, 'Bridge busy; one request at a time')
        if method not in ('initialize', 'ping', 'tools/list', 'tools/call'):
            return None, error_response(request_id, -32601, 'Method not supported')
        if method == 'initialize':
            if self.state != 'new':
                return None, error_response(request_id, -32600, 'Already initialized')
            params = value.get('params')
            if not isinstance(params, dict) or not isinstance(params.get('protocolVersion'), str):
                return None, error_response(request_id, -32602, 'Invalid initialize parameters')
            # Public stream-edge version selection: SDK returns our sole offered
            # version, without changing SDK globals or private session methods.
            value = dict(value, params=dict(params, protocolVersion=PROTOCOL_VERSION))
        elif method != 'ping' and self.state != 'ready':
            return None, error_response(request_id, -32600, 'Initialization is incomplete')
        params = value.get('params', {})
        if params is None or not isinstance(params, dict):
            return None, error_response(request_id, -32602, 'Expected object parameters')
        if method in ('tools/list', 'ping') and set(params) - {'_meta'}:
            return None, error_response(request_id, -32602, 'Pagination and extra parameters unsupported')
        if method == 'tools/call':
            if (set(params) - {'name', 'arguments', '_meta'} or
                    not isinstance(params.get('name'), str) or params['name'] not in self.tool_names):
                return None, error_response(request_id, -32602, 'Unknown tool or unsupported parameters')
            if not isinstance(params.get('arguments', {}), dict):
                return None, error_response(request_id, -32602, 'Tool arguments must be an object')
        return value, None

    def admitted(self, value):
        if 'id' in value:
            self.pending, self.pending_method = value['id'], value['method']
            if self.pending_method == 'initialize':
                self.state = 'initializing'

    def replied(self, value):
        if self.pending is not None and value.get('id') == self.pending:
            if self.pending_method == 'initialize':
                self.state = 'offered' if 'result' in value else 'new'
            self.pending = self.pending_method = None


async def serve(client, input_fd=0, output_fd=1, observer=None):
    """Run the public SDK over bounded stdio; caller bootstraps AgentClient first."""
    import anyio
    from mcp import types
    from mcp.server.lowlevel import Server
    from mcp.server.models import InitializationOptions
    from mcp.shared.message import SessionMessage
    import agent_api

    agent_api.validate_registry()
    definitions = (client.tool_definitions() if hasattr(client, 'tool_definitions')
                   else agent_api.tool_definitions())
    selected = client.selected_contracts() if hasattr(client, 'selected_contracts') else {}

    def contract_version(name):
        return selected.get(agent_api.operation(name)['operation_id'])

    profile = Profile(item['name'] for item in definitions)
    server = Server('tuldok', version='1')
    pending_observation = None
    pending_outcome, pending_status = 'response', None
    pending_http_status = None

    def observe(phase, observation=None, **values):
        if observer is not None:
            try:
                observer.stage(observation, phase, **values)
            except Exception:
                pass

    def begin(value, size, framing=False):
        if observer is not None:
            try:
                return observer.begin(value, size, framing=framing)
            except Exception:
                pass
        return None

    @server.list_tools()
    async def list_tools():
        return [types.Tool.model_validate(item) for item in definitions]

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        nonlocal pending_outcome, pending_status, pending_http_status
        pending_http_status = None
        try:
            agent_api.validate_arguments(name, arguments, contract_version(name))
            observe('dispatch', pending_observation)
            envelope = await anyio.to_thread.run_sync(client.call, name, arguments)
            pending_http_status = envelope.get('status') if isinstance(envelope, dict) else None
            agent_api.validate_output(name, envelope, contract_version(name))
            pending_outcome = ('permission-refusal' if envelope['status'] in (401, 403)
                               else 'domain-error' if envelope['status'] >= 400 else 'success')
        except agent_api.AgentAPIError as exc:
            # Owner supplies bounded, public API errors; no raw transport exception.
            envelope = tool_error(exc.code, str(exc), exc.status)
            pending_outcome = ('transport-error' if exc.code in ('transport', 'response_too_large')
                               else 'registry-refusal' if exc.code == 'registry_mismatch'
                               else 'permission-refusal' if exc.status in (401, 403) else 'call-error')
        except Exception:
            envelope = tool_error('bridge_failure', 'Tool call failed; acknowledgement may be unknown')
            pending_outcome = 'bridge-error'
        pending_status = envelope['status']
        observe('returned', pending_observation, outcome=pending_outcome,
                envelope_status=pending_status, http_status=pending_http_status)
        return types.CallToolResult(
            content=[types.TextContent(type='text', text=json.dumps(envelope, ensure_ascii=False,
                                                                  allow_nan=False, separators=(',', ':')))],
            structuredContent=envelope, isError=envelope['status'] >= 400)

    options = InitializationOptions(server_name='tuldok', server_version='1',
                                    capabilities=types.ServerCapabilities(tools=types.ToolsCapability()))
    incoming_send, incoming_receive = anyio.create_memory_object_stream(0)
    outgoing_send, outgoing_receive = anyio.create_memory_object_stream(0)
    output_lock = anyio.Lock()
    regular_input = stat.S_ISREG(os.fstat(input_fd).st_mode)
    regular_output = stat.S_ISREG(os.fstat(output_fd).st_mode)
    prepare_output_pipe(output_fd)
    old_input, old_output = os.get_blocking(input_fd), os.get_blocking(output_fd)
    os.set_blocking(input_fd, False)
    os.set_blocking(output_fd, False)

    async def write(value, sdk_response=False, observation=None):
        nonlocal pending_observation
        outcome, status = (pending_outcome, pending_status) if sdk_response else ('response', None)
        http_status = pending_http_status if sdk_response else None
        rpc_code = None
        if 'error' in value:
            rpc_code = value['error'].get('code')
            outcome = {-32700: 'parse-error', -32600: 'invalid-request',
                       -32601: 'unsupported-method', -32602: 'invalid-parameters',
                       -32000: 'busy-or-not-ready'}.get(rpc_code, 'protocol-error')
        try:
            raw = encode_response(value)
        except (FrameError, UnicodeError, ValueError):
            envelope = tool_error('response_too_large', 'Encoded response exceeds bridge limit')
            value = {'jsonrpc': '2.0', 'id': value.get('id'), 'result': {
                'content': [{'type': 'text', 'text': json.dumps(envelope)}],
                'structuredContent': envelope, 'isError': True}}
            raw = encode_response(value)
            outcome, status = 'response-too-large', 502
        written = 0
        try:
            async with output_lock:
                with anyio.fail_after(WRITE_SECONDS):
                    view = memoryview(raw)
                    while view:
                        if not regular_output:
                            await anyio.wait_writable(output_fd)
                        try:
                            count = os.write(output_fd, view)
                        except BlockingIOError:
                            continue
                        if count <= 0:
                            raise BrokenPipeError('Closed output')
                        written += count
                        view = view[count:]
                if sdk_response:
                    profile.replied(value)
        except BaseException:
            observe('terminal', observation, outcome='unknown', response_bytes=written, delivery='incomplete')
            raise
        observe('terminal', observation, outcome=outcome, envelope_status=status, http_status=http_status, rpc_code=rpc_code,
                response_bytes=written, delivery='written')
        if sdk_response:
            pending_observation = None

    async def reader():
        nonlocal pending_observation, pending_outcome, pending_status, pending_http_status
        buffer = bytearray()
        async with incoming_send:
            while True:
                if not regular_input:
                    await anyio.wait_readable(input_fd)
                try:
                    block = os.read(input_fd, min(65536, INPUT_LIMIT + 1 - len(buffer)))
                except BlockingIOError:
                    continue
                if not block:
                    if buffer:
                        observation = begin(None, len(buffer), framing=True)
                        await write(error_response(None, -32700, 'Incomplete JSON line at EOF'), observation=observation)
                    return
                buffer.extend(block)
                while b'\n' in buffer:
                    newline = buffer.index(b'\n') + 1
                    raw = bytes(buffer[:newline])
                    del buffer[:newline]
                    try:
                        value = parse_frame(raw)
                    except FrameError as exc:
                        observation = begin(None, len(raw), framing=True)
                        await write(error_response(None, exc.code, str(exc)), observation=observation)
                        continue
                    original = value
                    value, refusal = profile.accept(value)
                    observation = begin(original, len(raw)) if 'id' in original or refusal is not None else None
                    if refusal is not None:
                        await write(refusal, observation=observation)
                    if value is None:
                        continue
                    try:
                        if 'id' in value:
                            types.ClientRequest.model_validate(value)
                        else:
                            types.ClientNotification.model_validate(value)
                        message = types.JSONRPCMessage.model_validate(value)
                    except ValueError:
                        await write(error_response(value.get('id'), -32602, 'Invalid method parameters'), observation=observation)
                        continue
                    if value.get('method') == 'tools/call':
                        params = value['params']
                        try:
                            agent_api.validate_arguments(params['name'], params.get('arguments', {}),
                                                         contract_version(params['name']))
                        except agent_api.AgentAPIError:
                            await write(error_response(value['id'], -32602, 'Invalid tool arguments'), observation=observation)
                            continue
                    observe('validated', observation)
                    observe('admitted', observation)
                    if 'id' in value:
                        pending_observation = observation
                        pending_outcome, pending_status = 'response', None
                        pending_http_status = None
                    profile.admitted(value)
                    await incoming_send.send(SessionMessage(message))
                if len(buffer) >= INPUT_LIMIT:
                    observation = begin(None, len(buffer), framing=True)
                    await write(error_response(None, -32700, 'Input line exceeds 1 MiB'), observation=observation)
                    return

    async def writer():
        async with outgoing_receive:
            async for session_message in outgoing_receive:
                value = session_message.message.model_dump(by_alias=True, exclude_none=True)
                await write(value, sdk_response=True, observation=pending_observation)

    try:
        async with anyio.create_task_group() as group:
            group.start_soon(reader)
            group.start_soon(writer)
            async with outgoing_send:
                await server.run(incoming_receive, outgoing_send, options, raise_exceptions=True)
    finally:
        try:
            os.set_blocking(input_fd, old_input)
            os.set_blocking(output_fd, old_output)
        finally:
            if observer is not None:
                try:
                    observer.close()
                except Exception:
                    pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Private AgentClient JSON configuration file')
    parser.add_argument('--observe-v2-database', help='Explicit operator opt-in to a fresh private v2 interface store')
    parser.add_argument('--observe-database', help='Opt in to operator-only SQLite in an existing private directory')
    parser.add_argument('--observe-max-calls')
    parser.add_argument('--observe-max-age-seconds')
    parser.add_argument('--observe-max-bytes')
    args = parser.parse_args(argv)
    observer = None
    try:
        import anyio
        import mcp  # noqa: F401 - explicit optional consumer boundary
        import jsonschema  # noqa: F401
        import agent_api
        client = agent_api.AgentClient.from_config(args.config)
        client.bootstrap()
        if args.observe_database is not None or args.observe_v2_database is not None:
            try:
                from pathlib import Path
                from mcp_observer import (InteractionRecorder, RecorderConfig, DEFAULT_MAX_CALLS,
                                          DEFAULT_MAX_AGE_SECONDS, DEFAULT_MAX_BYTES)
                if args.observe_database is not None and args.observe_v2_database is not None:
                    raise ValueError('invalid-observer-configuration')
                config = RecorderConfig(Path(args.observe_v2_database or args.observe_database),
                    int(args.observe_max_calls) if args.observe_max_calls is not None else DEFAULT_MAX_CALLS,
                    int(args.observe_max_age_seconds) if args.observe_max_age_seconds is not None else DEFAULT_MAX_AGE_SECONDS,
                    int(args.observe_max_bytes) if args.observe_max_bytes is not None else DEFAULT_MAX_BYTES)
                if args.observe_v2_database is not None:
                    from mcp_observer import InterfaceRecorder
                    observer = InterfaceRecorder(config, agent_api.discovery(), boundary='mcp',
                        selected=client.selected_contracts())
                else:
                    observer = InteractionRecorder(config, agent_api.discovery())
            except Exception:
                try:
                    print('tuldok observer invalid-observer-configuration', file=sys.stderr, flush=True)
                except Exception:
                    pass
        anyio.run(serve, client, 0, 1, observer)
        return 0
    except ImportError:
        print('Optional agent dependencies unavailable; install the approved requirements-agent lock in a separate environment.', file=sys.stderr)
    except (Exception, KeyboardInterrupt):
        # No token, config, URL, request body, or raw exception reaches diagnostics.
        print('Agent bridge stopped: configuration, authentication, transport or protocol failure.', file=sys.stderr)
    finally:
        if observer is not None:
            try:
                observer.close()
            except Exception:
                pass
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
