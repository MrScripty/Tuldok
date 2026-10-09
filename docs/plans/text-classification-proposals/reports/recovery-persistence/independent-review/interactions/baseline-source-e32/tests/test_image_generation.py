import base64
import json
import socket
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import image_generation
from fake_images import png, start


class ImageGenerationTests(unittest.TestCase):
    def setUp(self):
        self.server, self.url, self.requests = start()
        self.manager = image_generation.ImageRequests()
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
    def body(self, prompt='bird'):
        return {'request_id': 'a'*32, 'server_url': self.url+'/v1', 'model': 'image-test', 'prompt': prompt, 'width': 512, 'height': 512}
    def test_discovery_excludes_vision_only_models(self):
        self.assertEqual(image_generation.models({'server_url': self.url})['models'], [{'id':'image-test','name':'image-test'}])
    def test_generation_decodes_and_preserves_the_returned_png(self):
        result = self.manager.generate(self.body())
        self.assertEqual(base64.b64decode(result['image']), png())
        self.assertEqual((result['width'], result['height']), (512, 512))
        self.assertEqual(len(self.requests), 1)
    def test_damaged_image_and_wrong_dimensions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid PNG'):
            self.manager.generate(self.body('invalid'))
        with self.assertRaisesRegex(ValueError, 'invalid PNG'):
            image_generation.decode_image(json.dumps({'data':[{'b64_json':base64.b64encode(png((768,768))).decode()}]}), 512, 512)
    def test_invalid_options_never_reach_the_gateway(self):
        for changes in ({'seed': True}, {'seed': -1}, {'width': 0}, {'height': -1}, {'width': '512'}, {'size': '512x512'}, {'prompt':'   '}, {'n':2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.generate({**self.body(), **changes})
        self.assertFalse(self.requests)
    def test_omitted_dimensions_default_to_1280_by_720(self):
        body = self.body()
        del body['width']
        del body['height']
        result = self.manager.generate(body)
        sent = self.requests[0]['body']
        self.assertEqual((sent['width'], sent['height']), (1280, 720))
        self.assertNotIn('size', sent)
        self.assertEqual((result['width'], result['height']), (1280, 720))
    def test_explicit_dimensions_reach_pumas_unchanged(self):
        body = {**self.body(), 'width': 1280, 'height': 720}
        result = self.manager.generate(body)
        sent = self.requests[0]['body']
        self.assertEqual((sent['width'], sent['height']), (1280, 720))
        self.assertIs(type(sent['width']), int)
        self.assertEqual((result['width'], result['height']), (1280, 720))
    def test_unprocessable_fields_name_a_contract_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'contract'):
            self.manager.generate({**self.body(), 'prompt': 'unprocessable', 'width': 33, 'height': 33})
        self.assertEqual(len(self.requests), 1)
    def test_no_duration_deadline_remains_and_connect_stays_bounded(self):
        source = Path(image_generation.__file__).read_text()
        self.assertFalse(hasattr(image_generation, 'TIMEOUT'))
        self.assertNotIn('630', source)
        self.assertNotIn('TimeoutError', source)
        self.assertNotIn('time.monotonic', source)
        self.assertNotIn('exceeded its deadline', source)
        self.assertNotIn('exceeded its time limit', source)
        self.assertNotIn('504:', source)
        self.assertIn('CONNECT_TIMEOUT', source)
        self.assertIn('timeout=CONNECT_TIMEOUT', source)
        self.assertIn('settimeout(None)', source)
    def test_silent_work_beyond_former_policy_completes_without_deadline(self):
        received = []
        class SilentHandler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append(body)
                time.sleep(2.5)
                raw = png((body['width'], body['height']))
                encoded = json.dumps({'data': [{'b64_json': base64.b64encode(raw).decode()}],
                                      'metadata': {'seed': body.get('seed', 7)}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (OSError, ValueError):
                    pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), SilentHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            body = {**self.body(), 'server_url': 'http://127.0.0.1:%d/v1' % server.server_port,
                    'width': 128, 'height': 96}
            result = self.manager.generate(body)
            self.assertEqual((result['width'], result['height']), (128, 96))
            self.assertEqual(base64.b64decode(result['image']), png((128, 96)))
            self.assertEqual(len(received), 1)
        finally:
            server.shutdown()
            server.server_close()
    def test_transport_closing_cancellation_reports_no_retry(self):
        errors = []
        def generate():
            try:
                self.manager.generate(self.body('slow'))
            except ValueError as error:
                errors.append(str(error))
        worker = threading.Thread(target=generate)
        worker.start()
        wait_until = time.monotonic()+3
        while not self.requests and time.monotonic()<wait_until:
            time.sleep(.01)
        self.assertTrue(self.requests)
        self.manager.cancel('a'*32)
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ['Image generation cancelled.'])
        observed_until = time.monotonic() + 2
        while not self.requests[0]['cancelled'] and time.monotonic() < observed_until:
            time.sleep(.01)
        self.assertTrue(self.requests[0]['cancelled'])
        self.assertEqual(len(self.requests), 1)
    def test_uncertain_lost_response_is_not_replayed(self):
        received = []
        class DropHandler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                received.append(True)
                try:
                    self.rfile.read(int(self.headers.get('Content-Length') or 0))
                except (OSError, ValueError):
                    pass
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), DropHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            body = {**self.body(), 'server_url': 'http://127.0.0.1:%d/v1' % server.server_port}
            with self.assertRaisesRegex(ValueError, 'Lost the Pumas image response'):
                self.manager.generate(body)
            try:
                self.manager.generate(body)
            except ValueError as error:
                self.assertIn('may have continued', str(error))
                self.assertIn('not retried', str(error))
            self.assertEqual(len(received), 2)
            self.assertFalse(self.manager.active)
        finally:
            server.shutdown()
            server.server_close()
    def test_additive_public_metadata_is_tolerated(self):
        raw = png((512, 512))
        payload = json.dumps({'data': [{'b64_json': base64.b64encode(raw).decode()}],
                              'metadata': {'seed': 7, 'steps': 8, 'guidance': 0,
                                           'duration_seconds': .01,
                                           'memory_policy': 'sequential_cpu_offload',
                                           'scheduler': 'euler', 'variant': 'supported',
                                           'extra_count': 3}})
        result = image_generation.decode_image(payload, 512, 512)
        self.assertEqual((result['width'], result['height']), (512, 512))
        self.assertEqual(result['metadata']['seed'], 7)
        self.assertEqual(result['metadata']['steps'], 8)
        self.assertNotIn('scheduler', result['metadata'])
        self.assertNotIn('variant', result['metadata'])
        self.assertNotIn('extra_count', result['metadata'])
    def test_cancel_closes_transport_and_allows_next_request_without_retry(self):
        errors = []
        def generate():
            try:
                self.manager.generate(self.body('slow'))
            except ValueError as error:
                errors.append(str(error))
        worker = threading.Thread(target=generate)
        worker.start()
        wait_until = time.monotonic()+3
        while not self.requests and time.monotonic()<wait_until:
            time.sleep(.01)
        self.assertTrue(self.requests)
        self.manager.cancel('a'*32)
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ['Image generation cancelled.'])
        self.manager.generate({**self.body(), 'request_id':'b'*32})
        self.assertEqual(len(self.requests), 2)
        self.assertFalse(self.manager.active)
