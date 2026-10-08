"""Find Pumas among HTTP services listening on this computer's loopback ports."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import threading
import time
import pumas_gateway_descriptor as descriptor

SCAN_LOCK = threading.Lock()
MAX_RESPONSE = 1024 * 1024


def listening_endpoints():
    """Include ephemeral ports and IPv6 without probing every unused TCP port."""
    endpoints = set()
    readable = False
    for filename, host in (('/proc/net/tcp', '127.0.0.1'), ('/proc/net/tcp6', '::1')):
        try:
            lines = Path(filename).read_text().splitlines()[1:]
            readable = True
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) > 3 and fields[3] == '0A':
                port = int(fields[1].rsplit(':', 1)[1], 16)
                endpoints.add((host, port))
                # Dual-stack listeners may also accept IPv4 loopback.
                if host == '::1':
                    endpoints.add(('127.0.0.1', port))
    if not readable:
        raise ValueError('Local port discovery is unavailable on this system. Enter the Pumas gateway URL manually.')
    return sorted(endpoints, key=lambda endpoint: (endpoint[1], endpoint[0]))


def get_json(host, port, path, deadline, payload=None, max_response=MAX_RESPONSE, decode=json.loads, require_complete=False):
    timeout = min(1.5, deadline - time.monotonic())
    if timeout <= 0:
        raise TimeoutError()
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request('POST' if payload is not None else 'GET', path,
                           body=json.dumps(payload) if payload is not None else None,
                           headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        transport = connection.sock
        with connection.getresponse() as response:
            if response.status != 200:
                raise ValueError('Not a gateway response')
            if require_complete:
                declared = response.getheader('Content-Length')
                if declared is not None and (not declared.strip().isdecimal() or response.chunked):
                    raise ValueError('Invalid Pumas descriptor response length')
            data = bytearray()
            while not response.isclosed():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                transport.settimeout(min(1.5, remaining))
                chunk = response.read1(65536)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_response:
                    raise ValueError('Oversized discovery response')
            if require_complete and response.length not in (None, 0):
                raise ValueError('Pumas descriptor response ended before its declared length')
            return decode(data)
    finally:
        connection.close()


def probe(endpoint, deadline):
    host, port = endpoint
    try:
        value = get_json(host, port, '/v1/models', deadline)
        entries = value.get('data') if isinstance(value, dict) else None
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            return None
        if not any(item.get('owned_by') == 'pumas' for item in entries):
            # An idle Pumas gateway has no model ownership markers. Verify its
            # read-only launcher RPC rather than accepting arbitrary /health APIs.
            rpc = get_json(host, port, '/rpc', deadline,
                           {'jsonrpc': '2.0', 'id': 'tuldok-discovery', 'method': 'get_launcher_version', 'params': {}})
            result = rpc.get('result') if isinstance(rpc, dict) else None
            if not isinstance(result, dict) or result.get('success') is not True or not all(
                    isinstance(result.get(key), str) for key in ('version', 'currentCommit', 'branch')) or type(result.get('isGitRepo')) is not bool:
                return None
        image_count = sum(isinstance(item.get('capabilities'), list) and 'image_generation' in item['capabilities'] for item in entries)
        address = '[' + host + ']' if ':' in host else host
        return {'server_url': f'http://{address}:{port}', 'models': len(entries), 'image_models': image_count}
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        return None


def probe_labeling(endpoint, deadline):
    """Find ready VLM endpoints, including Pumas-managed llama.cpp servers."""
    host, port = endpoint
    try:
        value = get_json(host, port, '/v1/models', deadline)
        entries = value.get('data') if isinstance(value, dict) else None
        if not isinstance(entries, list) or not entries or any(not isinstance(item, dict) for item in entries):
            return None
        address = '[' + host + ']' if ':' in host else host
        server_url = f'http://{address}:{port}'
        if any(item.get('owned_by') == 'pumas' for item in entries):
            candidates = [item for item in entries if 'image_generation' not in (item.get('capabilities') or [])]
            return {'server_url': server_url, 'models': len(candidates), 'kind': 'Pumas gateway'} if candidates else None
        props = get_json(host, port, '/props', deadline)
        if not isinstance(props, dict) or not isinstance(props.get('build_info'), str):
            return None
        modalities = props.get('modalities')
        if not ((isinstance(modalities, dict) and modalities.get('vision') is True) or
                any(isinstance(item.get('id'), str) and item['id'].startswith('vlm/') for item in entries)):
            return None
        return {'server_url': server_url, 'models': len(entries), 'kind': 'model server'}
    except (OSError, ValueError, TypeError, http.client.HTTPException):
        return None


def scan_labeling():
    if not SCAN_LOCK.acquire(blocking=False):
        raise ValueError('A gateway scan is already running. Wait for it to finish.')
    try:
        endpoints = listening_endpoints()
        deadline = time.monotonic() + 10
        with ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(lambda endpoint: probe_labeling(endpoint, deadline), endpoints))
        found = {}
        for endpoint, result in zip(endpoints, results):
            if result and endpoint[1] not in found:
                found[endpoint[1]] = result
        choices = list(found.values())
        return {'endpoints': choices, 'message': '' if choices else
                'No ready local vision endpoint found. Serve a VLM in Pumas or enter its model server URL manually.'}
    finally:
        SCAN_LOCK.release()


def scan():
    if not SCAN_LOCK.acquire(blocking=False):
        raise ValueError('A gateway scan is already running. Wait for it to finish.')
    try:
        endpoints = listening_endpoints()
        deadline = time.monotonic() + 10
        with ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(lambda endpoint: probe(endpoint, deadline), endpoints))
        # Prefer IPv4 for a dual-stack service on the same port.
        found = {}
        for endpoint, result in zip(endpoints, results):
            if result and endpoint[1] not in found:
                found[endpoint[1]] = result
        gateways = list(found.values())
        return {'gateways': gateways, 'message': '' if gateways else
                'No Pumas gateway found on this computer. Start Pumas and scan again, or enter its gateway URL manually.'}
    finally:
        SCAN_LOCK.release()


def inspect_advertised(server_url, deadline=None):
    """Observe one public HTTP descriptor, without IPC attachment or inference."""
    from urllib.parse import urlsplit
    base = descriptor.endpoint(server_url)
    parts = urlsplit(base)
    try:
        observed = get_json(parts.hostname, parts.port, '/.well-known/pumas',
                            deadline if deadline is not None else time.monotonic() + 3,
                            max_response=descriptor.MAX_DESCRIPTION_BYTES, decode=descriptor.decode,
                            require_complete=True)
    except http.client.HTTPException as error:
        raise ValueError('Pumas descriptor response is unavailable or incomplete.') from error
    if descriptor.endpoint(observed['advertisement']['endpoint']) != base:
        raise ValueError('Pumas advertises a different endpoint. Scan again.')
    return dict(observed, server_url=base)


def scan_advertised():
    if not SCAN_LOCK.acquire(blocking=False):
        raise ValueError('A gateway scan is already running. Wait for it to finish.')
    try:
        endpoints = listening_endpoints()
        if len(endpoints) > 512:
            raise ValueError('Too many local listeners for the bounded gateway scan. Enter the gateway URL manually.')
        deadline = time.monotonic() + 10
        def observe(item):
            host, port = item
            address = '[' + host + ']' if ':' in host else host
            try:
                return inspect_advertised(f'http://{address}:{port}', deadline)
            except (OSError, ValueError, TypeError, http.client.HTTPException):
                return None
        with ThreadPoolExecutor(max_workers=32) as pool:
            results = list(pool.map(observe, endpoints))
        # Distinct IPv4/IPv6 services on one port must retain their library context.
        found = {row['server_url']: row for row in results if row is not None}
        return {'gateways': list(found.values()), 'qualification':
                'Read-only HTTP advertisements. Core ownership is not authenticated; compiled features do not prove model readiness.'}
    finally:
        SCAN_LOCK.release()
