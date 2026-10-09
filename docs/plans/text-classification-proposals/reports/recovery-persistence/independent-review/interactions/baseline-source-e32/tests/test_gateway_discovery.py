import json
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gateway_discovery as discovery


class DiscoveryTests(unittest.TestCase):
    def server(self, models, rpc=None, props=None):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def reply(self, value):
                data = json.dumps(value).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                observed.append(self.path)
                self.reply(props if self.path == '/props' else models)
            def do_POST(self):
                observed.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.reply(rpc)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return ('127.0.0.1', server.server_port), observed

    def test_finds_ephemeral_pumas_port_and_rejects_other_model_servers(self):
        pumas, requests = self.server({'data': [{'id': 'image', 'owned_by': 'pumas', 'capabilities': ['image_generation']}]})
        unrelated, _ = self.server({'data': [{'id': 'text', 'owned_by': 'llamacpp'}]})
        with patch.object(discovery, 'listening_endpoints', return_value=[unrelated, pumas]):
            result = discovery.scan()
        self.assertEqual(result['gateways'], [{'server_url': f'http://127.0.0.1:{pumas[1]}', 'models': 1, 'image_models': 1}])
        self.assertEqual(requests, ['/v1/models'])

    def test_empty_pumas_is_verified_using_read_only_rpc(self):
        endpoint, requests = self.server({'data': []}, {'jsonrpc': '2.0', 'result': {
            'success': True, 'version': '1.0', 'currentCommit': 'abc', 'branch': 'main', 'isGitRepo': True}})
        result = discovery.probe(endpoint, time.monotonic() + 3)
        self.assertEqual(result['image_models'], 0)
        self.assertEqual(requests[1]['method'], 'get_launcher_version')
        self.assertEqual(requests[1]['params'], {})

    def test_labeling_finds_served_vlm_outside_empty_pumas_gateway(self):
        idle, _ = self.server({'data': []}, {'result': {
            'success': True, 'version': '1.0', 'currentCommit': 'abc', 'branch': 'main', 'isGitRepo': True}})
        vision, requests = self.server({'data': [{'id': 'vlm/example'}]}, props={
            'build_info': 'llama.cpp', 'modalities': {'vision': True}})
        with patch.object(discovery, 'listening_endpoints', return_value=[idle, vision]):
            result = discovery.scan_labeling()
        self.assertEqual(result['endpoints'], [{'server_url': f'http://127.0.0.1:{vision[1]}',
                                               'models': 1, 'kind': 'model server'}])
        self.assertEqual(requests, ['/v1/models', '/props'])

    def test_non_gateway_and_malformed_models_are_ignored(self):
        for response in ({'status': 'ok'}, {'data': 'invalid'}, {'data': [None]}, {'data': []}):
            endpoint, _ = self.server(response)
            self.assertIsNone(discovery.probe(endpoint, time.monotonic() + 3))

    def test_proc_discovery_includes_ipv6_and_high_ports_but_not_connections(self):
        contents = 'header\n0: 0100007F:FFFF 00000000:0000 0A rest\n1: 0100007F:1234 00000000:0000 01 rest\n'
        with patch.object(Path, 'read_text', return_value=contents):
            endpoints = discovery.listening_endpoints()
        self.assertEqual(endpoints, [('127.0.0.1', 65535), ('::1', 65535)])

    def test_scan_lock_released_on_error_and_empty_scan_has_help(self):
        with patch.object(discovery, 'listening_endpoints', side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError):
                discovery.scan()
        self.assertFalse(discovery.SCAN_LOCK.locked())
        with patch.object(discovery, 'listening_endpoints', return_value=[]):
            self.assertIn('Start Pumas', discovery.scan()['message'])
