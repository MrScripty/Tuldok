"""New queued HTTP input cannot masquerade as a legacy saved generation job."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from app import Dataset, make_handler
from fake_images import start


class GenerationJobApiTests(unittest.TestCase):
    def setUp(self):
        self.gateway, self.gateway_url, self.requests = start()
        self.addCleanup(self.gateway.server_close)
        self.addCleanup(self.gateway.shutdown)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dataset = Dataset(self.temp.name)
        self.addCleanup(self.dataset.close)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def body(self):
        return dict(server_url=self.gateway_url, model='image-test', prompt='open books',
                    count=1, strategy='repeat', seed=40, session_id='queued-http')

    def post(self, route, body):
        request = urllib.request.Request(self.root + route, data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)

    def test_new_jobs_reject_size_without_persistence_or_provider_work(self):
        for size in ('512x512', '768x1024', None, True, 512, [], {}):
            for dimensions in ({}, {'width': 37, 'height': 29}):
                with self.subTest(size=size, dimensions=dimensions):
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        self.post('/api/generation/jobs', dict(self.body(), size=size, **dimensions))
                    self.assertEqual(rejected.exception.code, 400)
                    self.assertIn('numeric width and height', json.load(rejected.exception)['error'])
        # The direct route already rejects obsolete fields; both acquisition
        # paths must reject rather than silently select defaults.
        direct = {key: value for key, value in self.body().items() if key not in ('count', 'strategy', 'session_id')}
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            self.post('/api/generation/generate', dict(direct, request_id='a'*32, size='512x512'))
        self.assertEqual(rejected.exception.code, 400)
        self.assertEqual(self.dataset.generation_jobs.snapshot(), {'jobs': [], 'entries': []})
        self.assertIsNone(self.dataset.generation_jobs.worker)
        self.assertEqual(self.dataset.rows(), [])
        self.assertEqual(self.requests, [])

    def test_numeric_and_omitted_new_dimensions_keep_current_api_behavior(self):
        for seed, dimensions, expected in ((41, {'width': 37, 'height': 29}, (37, 29)),
                                           (42, {}, (1280, 720))):
            with self.subTest(dimensions=dimensions):
                body = dict(self.body(), seed=seed, **dimensions)
                status, created = self.post('/api/generation/jobs', body)
                self.assertEqual(status, 201)
                self.dataset.generation_jobs.worker.join(10)
                self.assertFalse(self.dataset.generation_jobs.worker.is_alive())
                job = next(j for j in self.dataset.generation_jobs.snapshot()['jobs'] if j['id'] == created['id'])
                self.assertEqual(job['status'], 'completed', job)
                sent = self.requests[-1]['body']
                self.assertEqual((sent['width'], sent['height']), expected)
                self.assertNotIn('size', sent)
