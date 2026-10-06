import base64
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Dataset
from fake_images import png, start
import synthetic


class SyntheticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dataset = Dataset(self.temp.name)
        self.jobs = self.dataset.generation_jobs
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(lambda: self.dataset.close())

    def config(self, **extra):
        return dict(server_url='http://localhost:1234', model='image-test', prompt='open books',
                    width=512, height=512, count=3, strategy='repeat', session_id='synthetic', **extra)

    def wait(self):
        self.jobs.worker.join(10)
        self.assertFalse(self.jobs.worker.is_alive())
        return self.jobs.snapshot()

    def image(self, body, **kwargs):
        return dict(image=base64.b64encode(png(color='#%06x' % body.get('seed', 1))).decode(), metadata={'seed': body.get('seed')})

    def test_500_unique_prompts_are_batched_and_exist_before_first_render(self):
        batches = []
        def prompts(config, offset, count, previous):
            batches.append((offset, count, len(previous)))
            return ['Book at location ' + str(i) for i in range(offset, offset + count)]
        def render(body, **kwargs):
            state = self.jobs.snapshot()
            self.assertEqual(len(state['entries']), 500)
            self.assertEqual(len({e['prompt'] for e in state['entries']}), 500)
            raise ValueError('Stop after checking preparation')
        config = self.config()
        config.update(strategy='varied', count=500, prompt_model='text-test')
        with patch('synthetic.prompt_batch', side_effect=prompts), patch.object(self.dataset.image_requests, 'generate', side_effect=render):
            self.jobs.start(config)
            state = self.wait()
        self.assertEqual(len(batches), 50)
        self.assertTrue(all(size == 10 and history <= 10 for _, size, history in batches))
        self.assertEqual(state['jobs'][0]['status'], 'failed')

    def test_repeat_creates_one_pending_entry_then_links_images_and_labels(self):
        def render(body, **kwargs):
            entries = self.jobs.snapshot()['entries']
            self.assertEqual(sum(not e['sample_id'] for e in entries), 1)
            self.assertEqual(body['prompt'], 'open books')
            return self.image(body)
        with patch.object(self.dataset.image_requests, 'generate', side_effect=render):
            self.jobs.start(self.config(seed=20))
            state = self.wait()
        self.assertEqual(state['jobs'][0]['status'], 'completed')
        self.assertEqual(len(self.dataset.rows()), 3)
        self.assertEqual([e['metadata']['seed'] for e in state['entries']], [20, 21, 22])
        sample = self.dataset.rows()[0]
        self.assertEqual(sample['generation']['prompt'], 'open books')
        self.assertIsNone(sample['annotation'])
        self.dataset.save(sample['id'], dict(sample, annotation={'book_present': False, 'crop_suitable': False}))
        with self.dataset.export() as archive:
            self.assertGreater(len(archive.read()), 0)

    def test_cancel_and_resume_does_not_regenerate_completed_images(self):
        started = threading.Event()
        calls = []
        def render(body, cancel_event):
            calls.append(body['seed'])
            if body['seed'] == 21:
                started.set()
                cancel_event.wait(5)
                raise ValueError('cancelled')
            return self.image(body)
        with patch.object(self.dataset.image_requests, 'generate', side_effect=render):
            job = self.jobs.start(self.config(seed=20))
            self.assertTrue(started.wait(5))
            with self.assertRaises(ValueError):
                self.jobs.start(self.config())
            self.jobs.cancel(job['id'])
            self.assertEqual(self.wait()['jobs'][0]['status'], 'cancelled')
        with patch.object(self.dataset.image_requests, 'generate', side_effect=self.image):
            self.jobs.resume(job['id'])
            state = self.wait()
        self.assertEqual(state['jobs'][0]['completed'], 3)
        self.assertEqual(len(self.dataset.rows()), 3)
        self.assertEqual(calls, [20, 21])

    def test_duplicates_are_bounded_and_saved_prompts_survive_restart(self):
        config = self.config()
        config.update(strategy='varied', prompt_model='text-test')
        with patch('synthetic.prompt_batch', side_effect=lambda c, o, n, p: ['same'] * n):
            job = self.jobs.start(config)
            state = self.wait()
        self.assertEqual(len(state['entries']), 1)
        self.assertIn('duplicates', state['jobs'][0]['error'])
        self.dataset.close()
        self.dataset = Dataset(self.temp.name)
        self.jobs = self.dataset.generation_jobs
        self.assertEqual(self.jobs.snapshot()['entries'], state['entries'])
        with patch('synthetic.prompt_batch', return_value=['second', 'third']), patch.object(self.dataset.image_requests, 'generate', side_effect=ValueError('fixture stop')):
            self.jobs.resume(job['id'])
            self.assertEqual(len(self.wait()['entries']), 3)

    def test_server_interruption_preserves_completed_links_on_resume(self):
        with patch.object(self.dataset.image_requests, 'generate', side_effect=self.image):
            job = self.jobs.start(self.config(seed=10))
            state = self.wait()
        first_ids = [e['sample_id'] for e in state['entries']]
        # Simulate a restart after the final image committed but before final job status.
        job.update(status='generating')
        with self.jobs.lock, self.jobs.db:
            self.jobs._save(job)
        self.dataset.close()
        self.dataset = Dataset(self.temp.name)
        self.jobs = self.dataset.generation_jobs
        self.assertEqual(self.jobs.snapshot()['jobs'][0]['status'], 'interrupted')
        with patch.object(self.dataset.image_requests, 'generate') as render:
            self.jobs.resume(job['id'])
            state = self.wait()
            render.assert_not_called()
        self.assertEqual(state['jobs'][0]['status'], 'completed')
        self.assertEqual([e['sample_id'] for e in state['entries']], first_ids)

    def test_duplicate_images_stop_without_losing_saved_image_or_queue(self):
        with patch.object(self.dataset.image_requests, 'generate', side_effect=self.image):
            self.jobs.start(self.config())
            state = self.wait()
        self.assertEqual(state['jobs'][0]['status'], 'failed')
        self.assertEqual(state['jobs'][0]['completed'], 1)
        self.assertEqual(len(self.dataset.rows()), 1)
        self.assertEqual([e['status'] for e in state['entries']], ['completed', 'failed'])
        self.assertEqual(len(list((self.dataset.path / 'images').iterdir())), 1)

    def test_deleted_generated_image_is_not_recreated_on_resume(self):
        calls = []
        def render(body, **kwargs):
            calls.append(body['seed'])
            if body['seed'] == 21:
                raise ValueError('fixture stop')
            return self.image(body)
        with patch.object(self.dataset.image_requests, 'generate', side_effect=render):
            job = self.jobs.start(self.config(seed=20))
            self.wait()
        sample = self.dataset.rows()[0]
        result = self.dataset.delete(sample['id'], {'revision': sample['revision']})
        self.assertEqual(result['entries'][0]['status'], 'deleted')
        self.assertIsNone(result['entries'][0]['sample_id'])
        with patch.object(self.dataset.image_requests, 'generate', side_effect=self.image) as resumed:
            self.jobs.resume(job['id'])
            state = self.wait()
            self.assertEqual([call.args[0]['seed'] for call in resumed.call_args_list], [21, 22])
        self.assertEqual(state['jobs'][0]['status'], 'completed')
        self.assertEqual(len(self.dataset.rows()), 2)
        self.assertEqual(state['entries'][0]['status'], 'deleted')
        self.assertFalse((self.dataset.path / 'images' / sample['id']).exists())

    def test_invalid_request_creates_no_job(self):
        for changes in ({'count': True}, {'count': 0}, {'count': 10001}, {'strategy': 'unknown'}, {'session_id': ''}, {'strategy': 'varied'}, {'seed': -1}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.jobs.start(dict(self.config(), **changes))
        self.assertEqual(self.jobs.snapshot(), {'jobs': [], 'entries': []})

    def test_real_http_prompt_batches_and_images(self):
        server, url, requests = start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        config = self.config(seed=50)
        config.update(server_url=url, prompt_url=url, prompt_model='vision-only', strategy='varied', count=12)
        self.jobs.start(config)
        state = self.wait()
        self.assertEqual(state['jobs'][0]['status'], 'completed', state['jobs'])
        chats = [r for r in requests if r['path'] == '/v1/chat/completions']
        self.assertEqual([json.loads(r['body']['messages'][1]['content'])['number_of_prompts'] for r in chats], [10, 2])
        self.assertEqual(len(self.dataset.rows()), 12)
