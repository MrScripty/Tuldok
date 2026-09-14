import base64
import json
import sys
import threading
import time
import unittest
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
        return {'request_id': 'a'*32, 'server_url': self.url+'/v1', 'model': 'image-test', 'prompt': prompt, 'size': '512x512'}
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
            image_generation.decode_image(json.dumps({'data':[{'b64_json':base64.b64encode(png((768,768))).decode()}]}), '512x512')
    def test_invalid_options_never_reach_the_gateway(self):
        for changes in ({'seed': True}, {'seed': -1}, {'size':'4096x4096'}, {'prompt':'   '}, {'n':2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.generate({**self.body(), **changes})
        self.assertFalse(self.requests)
    def test_cancel_closes_transport_and_allows_next_request_without_retry(self):
        errors = []
        def generate():
            try:
                self.manager.generate(self.body('slow'))
            except ValueError as error:
                errors.append(str(error))
        worker = threading.Thread(target=generate)
        worker.start()
        deadline = time.monotonic()+3
        while not self.requests and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertTrue(self.requests)
        self.manager.cancel('a'*32)
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ['Image generation cancelled.'])
        self.manager.generate({**self.body(), 'request_id':'b'*32})
        self.assertEqual(len(self.requests), 2)
        self.assertFalse(self.manager.active)
