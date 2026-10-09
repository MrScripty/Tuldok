"""Restart/resume actual on-disk PR3 size-only queues through the numeric gateway."""
import base64
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from app import Dataset
from fake_images import png, start


class SavedGenerationTests(unittest.TestCase):
    def setUp(self):
        self.server, self.url, self.requests = start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dataset = Dataset(self.temp.name)
        self.addCleanup(lambda: self.dataset.close())

    def legacy_job(self, size='512x768', **changes):
        config = dict(server_url=self.url, model='image-test', prompt='open books',
                      size=size, count=3, strategy='repeat', seed=40)
        config.update(changes)
        return dict(id=uuid.uuid4().hex, config=config,
                    meta=dict(book_id='', session_id='legacy-queue', split='unassigned'),
                    status='generating', error='', completed=0)

    def legacy_entry(self, job, ordinal):
        return dict(id=uuid.uuid4().hex, job_id=job['id'], ordinal=ordinal,
                    prompt=job['config']['prompt'], model=job['config']['model'],
                    size=job['config']['size'], requested_seed=job['config']['seed']+ordinal,
                    status='pending', sample_id=None, error='')

    def store(self, job, entries=()):
        # These are the exact size-only JSON fields persisted by PR3, not
        # current validate()/start() objects altered after a worker has loaded.
        with self.dataset.db:
            self.dataset.db.execute('INSERT INTO generation_jobs VALUES (?,?)',
                                    (job['id'], json.dumps(job)))
            for entry in entries:
                self.dataset.db.execute('INSERT INTO generation_entries VALUES (?,?,?,?)',
                                        (entry['id'], job['id'], entry['ordinal'], json.dumps(entry)))

    def restart(self):
        self.dataset.close()
        self.dataset = Dataset(self.temp.name)

    def resume(self, job):
        self.dataset.generation_jobs.resume(job['id'])
        worker = self.dataset.generation_jobs.worker
        worker.join(10)
        self.assertFalse(worker.is_alive())
        result = next(j for j in self.dataset.generation_jobs.snapshot()['jobs'] if j['id'] == job['id'])
        self.assertEqual(result['status'], 'completed', result)
        return result

    def test_restart_resumes_partial_legacy_queue_and_preserves_source_provenance(self):
        job = self.legacy_job()
        first = self.legacy_entry(job, 0)
        raw = png((512, 768), '#000028')
        self.dataset.add(dict(job['meta'], image=base64.b64encode(raw).decode(), filename='old-output.png'),
                         generation=(first, job, {'seed': 40, 'duration_seconds': .01}))
        pending = self.legacy_entry(job, 1)
        with self.dataset.db:
            self.dataset.generation_jobs._entry(pending)
        raw_config = json.loads(self.dataset.db.execute('SELECT data FROM generation_jobs').fetchone()[0])['config']
        self.assertNotIn('width', raw_config)
        self.assertNotIn('width', first)
        source_id = first['sample_id']
        self.restart()
        state = self.dataset.generation_jobs.snapshot()
        self.assertEqual(state['jobs'][0]['status'], 'interrupted')
        self.assertEqual(state['jobs'][0]['config'], dict(raw_config, width=512, height=768))
        self.assertEqual(state['entries'][0], dict(first, width=512, height=768))
        self.assertEqual(state['entries'][1], dict(pending, width=512, height=768))
        result = self.resume(job)
        self.assertEqual(result['completed'], 3)
        sent = [r['body'] for r in self.requests if r['path'] == '/v1/images/generations']
        self.assertEqual([body['seed'] for body in sent], [41, 42])
        self.assertTrue(all((body['width'], body['height']) == (512, 768) and 'size' not in body for body in sent))
        self.assertEqual((Path(self.temp.name)/'images'/source_id/'source').read_bytes(), raw)
        samples = self.dataset.rows()
        self.assertEqual(len(samples), 3)
        original = next(row for row in samples if row['id'] == source_id)
        self.assertEqual(original['generation']['metadata'], first['metadata'])
        self.assertEqual((original['generation']['width'], original['generation']['height']), (512, 768))
        record = self.dataset.workbench.get(source_id)
        self.assertEqual(record['provenance']['generation']['size'], '512x768')
        self.assertEqual(record['provenance']['generation']['requested_seed'], 40)
        before = self.dataset.generation_jobs.snapshot()
        self.restart()
        self.assertEqual(self.dataset.generation_jobs.snapshot(), before)

    def test_all_pr3_supported_sizes_resume_through_real_numeric_http(self):
        # Independent literal fixture from PR3's size validator, including nonsquare images.
        sizes = ('512x512', '512x768', '512x1024', '768x512', '768x768',
                 '768x1024', '1024x512', '1024x768', '1024x1024')
        for index, size in enumerate(sizes):
            with self.subTest(size=size):
                job = self.legacy_job(size, count=1, seed=100+index)
                self.store(job)
                self.restart()
                result = self.resume(job)
                expected = tuple(map(int, size.split('x')))
                self.assertEqual((result['config']['width'], result['config']['height']), expected)
                self.assertEqual(result['config']['size'], size)
                sent = self.requests[-1]['body']
                self.assertEqual((sent['width'], sent['height']), expected)
                self.assertIs(type(sent['width']), int)
                self.assertNotIn('size', sent)
        self.assertEqual(len(self.requests), 9)

    def test_numeric_job_dimensions_are_not_replaced_by_legacy_or_api_defaults(self):
        job = self.legacy_job(count=1)
        del job['config']['size']
        job['config'].update(width=37, height=29)
        self.store(job)
        self.restart()
        loaded = self.dataset.generation_jobs.snapshot()['jobs'][0]
        self.assertEqual(loaded['config'], job['config'])
        self.resume(job)
        self.assertEqual((self.requests[0]['body']['width'], self.requests[0]['body']['height']), (37, 29))
        self.assertNotIn('size', self.requests[0]['body'])

    def test_invalid_saved_dimensions_remain_inspectable_and_cannot_start_provider_work(self):
        bad = (None, True, 512, [], {}, '', '512', '512X768', '512 x768',
               '0512x768', '512x768 ', '1280x720', '256x512')
        jobs = [self.legacy_job(size, count=1) for size in bad]
        for dimensions in ({}, {'width': 512}, {'height': 512}, {'width': True, 'height': 512},
                           {'width': '512', 'height': 512}, {'width': 0, 'height': 512}):
            job = self.legacy_job(count=1)
            del job['config']['size']
            job['config'].update(dimensions)
            jobs.append(job)
        jobs.append(self.legacy_job('512x512', count=1, width=768, height=512))
        for job in jobs:
            self.store(job)
        self.restart()
        for job in jobs:
            with self.subTest(config=job['config']):
                loaded = next(j for j in self.dataset.generation_jobs.snapshot()['jobs'] if j['id'] == job['id'])
                self.assertEqual(loaded['config'], job['config'])
                self.assertEqual(loaded['status'], 'failed')
                self.assertTrue(loaded['error'])
                with self.assertRaises(ValueError) as error:
                    self.dataset.generation_jobs.resume(job['id'])
                self.assertEqual(str(error.exception), loaded['error'])
                self.assertIsNone(self.dataset.generation_jobs.worker)
        self.assertFalse(self.requests)
        self.assertFalse(self.dataset.rows())

    def test_invalid_entry_refuses_the_entire_migration_without_partial_provenance_rewrite(self):
        job = self.legacy_job('512x512', count=2, strategy='varied',
                              prompt_url=self.url, prompt_model='vision-only')
        entries = [self.legacy_entry(job, 0), self.legacy_entry(job, 1)]
        entries[1]['size'] = '1280x720'
        self.store(job, entries)
        self.restart()
        state = self.dataset.generation_jobs.snapshot()
        self.assertEqual(state['jobs'][0]['config'], job['config'])
        self.assertEqual(state['jobs'][0]['status'], 'failed')
        self.assertEqual(state['entries'], entries)
        with self.assertRaisesRegex(ValueError, 'Unsupported saved image size'):
            self.dataset.generation_jobs.resume(job['id'])
        self.assertFalse(self.requests)
