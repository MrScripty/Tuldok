"""Public PR51 source-derived conformance fixture across real bounded HTTP."""
import copy
import hashlib
import json
from pathlib import Path
import socketserver
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import gateway_discovery as discovery
import pumas_gateway_descriptor as descriptor

FIXTURE = Path(__file__).parent / 'fixtures/pumas-http-pr51/advertisement.json'


def fixture():
    return json.loads(FIXTURE.read_bytes())


class PumasGateways(unittest.TestCase):
    def server(self, value=None, status=200, raw=None, extra_length=0):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                observed.append(self.path)
                payload = fixture() if value is None else copy.deepcopy(value)
                payload['endpoint'] = f'http://127.0.0.1:{self.server.server_port}'
                body = json.dumps(payload).encode() if raw is None else raw
                self.send_response(status)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body) + extra_length))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                observed.append('FORBIDDEN POST')
                self.send_response(405)
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return ('127.0.0.1', server.server_port), observed

    def test_exact_named_identity_optional_provenance_and_raw_hash(self):
        raw = FIXTURE.read_bytes()
        decoded = descriptor.decode(raw)
        self.assertEqual(decoded['advertisement'], fixture())
        self.assertEqual(decoded['observed_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertNotIn('source_revision', decoded['advertisement']['build_info'])
        legacy = fixture(); legacy['instance'].pop('build_info')
        self.assertEqual(descriptor.decode(json.dumps(legacy).encode())['advertisement'], legacy)
        legacy['instance']['build_info'] = None
        self.assertIsNone(descriptor.decode(json.dumps(legacy).encode())['advertisement']['instance']['build_info'])

    def test_additive_fields_and_open_list_entries_are_accepted_and_not_retained(self):
        additions = [
            lambda v: v.update(future_field={'nested': [1, 2]}),
            lambda v: v['instance'].update(connection_token='never retained'),
            lambda v: v['instance']['build_info'].update(future_field=True),
            lambda v: v['build_info'].update(future_field='ignored'),
            lambda v: v['build_info']['protocols'][0].update(future_field='ignored'),
            lambda v: v['build_info']['schemas'][0].update(future_field='ignored'),
            lambda v: v['build_info']['schemas'].append({'name': 'pumas.discovery', 'version': 2}),
            lambda v: v['build_info']['schemas'].append({'name': 'pumas.future-schema', 'version': 1}),
            lambda v: v['build_info']['protocols'].append({'name': 'pumas.future-protocol', 'versions': [3]}),
            lambda v: v['build_info']['protocols'][-1].update(versions=[1, 2]),
            lambda v: v['instance'].update(capabilities=[f'future.capability{i}@1' for i in range(100)]),
        ]
        for add in additions:
            value = fixture(); add(value)
            with self.subTest(value=value):
                decoded = descriptor.decode(json.dumps(value).encode())['advertisement']
                self.assertEqual(decoded['instance']['registry_library_id'], fixture()['instance']['registry_library_id'])
                text = json.dumps(decoded)
                self.assertNotIn('future_field', text)
                self.assertNotIn('connection_token', text)
        value = fixture(); value['future_field'] = 'ignored'; value['instance']['future_field'] = 'ignored'
        self.assertEqual(descriptor.decode(json.dumps(value).encode())['advertisement'], fixture())
        endpoint, calls = self.server(value)
        self.assertEqual(discovery.inspect_advertised(f'http://127.0.0.1:{endpoint[1]}')['advertisement']['instance'],
                         fixture()['instance'])

    def test_missing_required_fields_and_unsupported_versions_are_refused_with_reasons(self):
        cases = [
            (lambda v: v.pop('service_generation'),
             'Pumas advertisement is missing required field(s) service_generation.'),
            (lambda v: v['instance'].pop('generation'),
             'Pumas advertisement instance is missing required field(s) generation.'),
            (lambda v: v['build_info'].pop('schemas'),
             'Pumas advertisement build_info is missing required field(s) schemas.'),
            (lambda v: v['build_info']['protocols'][0].pop('versions'),
             'Pumas advertisement build_info.protocols[0] is missing required field(s) versions.'),
            (lambda v: v.update(advertisement_schema_version=2),
             'Pumas advertisement advertisement_schema_version 2 is unsupported; Tuldok supports version 1.'),
            (lambda v: v['instance'].update(selector_schema_version='1'),
             'Pumas advertisement instance.selector_schema_version must be an unsigned 32-bit integer.'),
            (lambda v: v.update(endpoint='http://example.com:8765'),
             'Pumas advertisement endpoint is invalid: Enter a numeric-loopback HTTP base URL.'),
        ]
        for mutate, reason in cases:
            value = fixture(); mutate(value)
            with self.subTest(reason=reason):
                with self.assertRaises(descriptor.Rejected) as caught:
                    descriptor.decode(json.dumps(value).encode())
                self.assertEqual(str(caught.exception), reason)
        value = fixture(); value['instance'].pop('generation')
        endpoint, calls = self.server(value)
        with patch.object(discovery, 'listening_endpoints', return_value=[endpoint]):
            result = discovery.scan_advertised()
        self.assertEqual(result['gateways'], [])
        self.assertEqual(result['rejected'], [{'server_url': f'http://127.0.0.1:{endpoint[1]}',
            'reason': 'Pumas advertisement instance is missing required field(s) generation.'}])
        with self.assertRaisesRegex(ValueError, 'missing required field'):
            discovery.inspect_advertised(f'http://127.0.0.1:{endpoint[1]}')

    def test_versions_boolean_wrong_shapes_and_oversizing_fail(self):
        mutations = [
            lambda v: v.update(advertisement_schema_version=True),
            lambda v: v.update(advertisement_schema_version=2),
            lambda v: v['instance'].update(discovery_schema_version=True),
            lambda v: v['instance'].update(selector_schema_version=True),
            lambda v: v['build_info'].update(build_info_schema_version=True),
            lambda v: v['build_info']['protocols'][-1].update(versions=[True]),
            lambda v: v['build_info']['protocols'][-1].update(versions=[2]),
            lambda v: v['build_info']['schemas'][-1].update(version=True),
            lambda v: v['build_info'].update(compiled_features=[None]),
            lambda v: v.update(service_generation=''),
            lambda v: v['instance'].update(capabilities='model.query@1'),
            lambda v: v.update(instance=[]),
            lambda v: v['instance'].update(library_root='x' * 4097),
            lambda v: v.update(endpoint='http://example.com:8765'),
            lambda v: v.update(endpoint='http://[::1%lo]:8765'),
        ]
        for mutate in mutations:
            value = fixture(); mutate(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                descriptor.decode(json.dumps(value).encode())
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'\xff', b'{}' * 32769, b'[' * 1000):
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError): descriptor.decode(raw)

    def test_numeric_loopback_urls_preserve_context_and_reject_indirection(self):
        self.assertEqual(descriptor.endpoint('http://[::1]:8765/'), 'http://[::1]:8765')
        self.assertEqual(descriptor.endpoint('http://127.0.0.1'), 'http://127.0.0.1:80')
        for url in ('http://localhost:8765', 'https://127.0.0.1:8765', 'http://127.0.0.1:0',
                    'http://127.0.0.1:8765/v1', 'http://127.0.0.1:8765?', 'http://user@127.0.0.1:8765',
                    'http://127.0.0.1:8765#', 'http://127.0.0.1:8765\n', 'http://10.0.0.1:8765',
                    'http://[::1%lo]:8765', 'http://[::1%25lo]:8765', 'http://[::1%1]:8765'):
            with self.subTest(url=url), self.assertRaises(ValueError): descriptor.endpoint(url)

    def test_actual_get_scan_inspection_hash_and_no_rpc_catalog_or_inference(self):
        endpoint, calls = self.server()
        with patch.object(discovery, 'listening_endpoints', return_value=[endpoint]):
            result = discovery.scan_advertised()
        self.assertEqual(len(result['gateways']), 1)
        row = result['gateways'][0]
        again = discovery.inspect_advertised(row['server_url'])
        self.assertEqual(again, row)
        self.assertEqual(calls, ['/.well-known/pumas'] * 2)
        self.assertIn('not authenticated', result['qualification'])

    def test_wrong_endpoint_redirect_oversized_invalid_and_unavailable_are_not_legacy_fallback(self):
        for status, raw in ((302, b'{}'), (404, b'{}'), (503, b'{}'), (200, b'x' * 65537), (200, b'{')):
            endpoint, calls = self.server(status=status, raw=raw)
            with patch.object(discovery, 'listening_endpoints', return_value=[endpoint]):
                self.assertEqual(discovery.scan_advertised()['gateways'], [])
            self.assertEqual(calls, ['/.well-known/pumas'])
        endpoint, calls = self.server(raw=FIXTURE.read_bytes())
        with self.assertRaisesRegex(ValueError, 'different endpoint'):
            discovery.inspect_advertised(f'http://127.0.0.1:{endpoint[1]}')

    def test_shared_scan_lock_limit_release_and_same_port_distinct_libraries(self):
        discovery.SCAN_LOCK.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'already running'): discovery.scan_advertised()
        finally: discovery.SCAN_LOCK.release()
        with patch.object(discovery, 'listening_endpoints', return_value=[('127.0.0.1', 1)] * 513):
            with self.assertRaisesRegex(ValueError, 'Too many'): discovery.scan_advertised()
        rows = [dict(server_url='http://127.0.0.1:8765', advertisement=fixture()),
                dict(server_url='http://[::1]:8765', advertisement=fixture())]
        rows[1]['advertisement']['instance']['registry_library_id'] = 'different-library'
        with patch.object(discovery, 'listening_endpoints', return_value=[('127.0.0.1', 8765), ('::1', 8765)]), patch.object(discovery, 'inspect_advertised', side_effect=rows):
            self.assertEqual(discovery.scan_advertised()['gateways'], rows)
        self.assertFalse(discovery.SCAN_LOCK.locked())

    def test_expired_deadline_performs_no_network_request(self):
        with patch.object(discovery.http.client, 'HTTPConnection', side_effect=AssertionError('Must not connect')):
            with self.assertRaises(TimeoutError): discovery.inspect_advertised('http://127.0.0.1:8765', time.monotonic() - 1)

    def test_complete_json_with_incomplete_declared_http_body_is_rejected(self):
        endpoint, calls = self.server(extra_length=17)
        with self.assertRaisesRegex(ValueError, 'before its declared length'):
            discovery.inspect_advertised(f'http://127.0.0.1:{endpoint[1]}')
        self.assertEqual(calls, ['/.well-known/pumas'])

    def test_dribbled_headers_cannot_escape_absolute_observation_deadline(self):
        class Drip(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(4096)
                try:
                    self.request.sendall(b'HTTP/1.1 200 OK\r\nX-Dribble: ')
                    for _ in range(30):
                        time.sleep(.03)
                        self.request.sendall(b'x')
                    self.request.sendall(b'\r\nContent-Length: 2\r\n\r\n{}')
                except OSError:
                    pass
        server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Drip)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        start = time.monotonic()
        with self.assertRaises((OSError, ValueError)):
            discovery.inspect_advertised(f'http://127.0.0.1:{server.server_address[1]}', start + .15)
        self.assertLess(time.monotonic() - start, .5, 'Total deadline must interrupt header parsing, not only body reads')


if __name__ == '__main__':
    unittest.main()
