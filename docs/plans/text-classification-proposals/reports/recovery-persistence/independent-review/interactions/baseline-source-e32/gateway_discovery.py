"""Find Pumas among HTTP services listening on this computer's loopback ports."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import threading
import time

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


def get_json(host, port, path, deadline, payload=None):
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
                if len(data) > MAX_RESPONSE:
                    raise ValueError('Oversized discovery response')
            return json.loads(data)
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
