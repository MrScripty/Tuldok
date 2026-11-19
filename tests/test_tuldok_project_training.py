"""What a training script logged, read while it is written (docs/plans/training-and-curation/spec-t1.md, slice T1a).

The readers are tested on files the tests write with the standard library and
need no database. The operations need one and run only when
TULDOK_DATABASE_URL names a disposable cluster: they build recipes/fit-a (as
test_tuldok_project_builds does), write training files into its run's output,
and read them with the run marked running and queued. No GPU is used.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import builds, local, operations, store, training  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
from test_tuldok_project_inside import OWNER, floats, npy, png  # noqa: E402

TRAINING = ('training', 'training_series', 'training_histograms', 'training_samples', 'training_sample')


def line(value):
    return (json.dumps(value) + '\n').encode()


class TrainingCase(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = os.path.realpath(directory.name)
        os.makedirs(os.path.join(self.root, 'training', 'samples'))
        training.forget()
        self.addCleanup(training.forget)
        self.run = training.Run('run-1', 'running', self.root)

    def path(self, name):
        return os.path.join(self.root, 'training', name)

    def append(self, name, data):
        with open(self.path(name), 'ab') as handle:
            handle.write(data)

    def overview(self):
        got = training.overview(self.run)
        json.dumps(got, allow_nan=False)
        return got

    def series(self, *wanted, most=1000):
        got = training.series(self.run, [w if isinstance(w, dict) else {'name': w} for w in wanted], most=most)
        json.dumps(got, allow_nan=False)
        return got

    def refused(self, code, call, *arguments, **options):
        with self.assertRaises(store.ProjectError) as caught:
            call(*arguments, **options)
        self.assertEqual(caught.exception.code, code, str(caught.exception))


class Metrics(TrainingCase):

    def test_nothing_logged(self):
        got = training.overview(training.Run('run-2', 'queued', None))
        self.assertEqual((got['present'], got['series'], got['lines'], got['run']['active']), (False, [], 0, True))
        os.rmdir(os.path.join(self.root, 'training', 'samples'))
        os.rmdir(os.path.join(self.root, 'training'))
        self.assertFalse(self.overview()['present'])
        self.refused('not-found', training.series, training.Run('run-2', 'queued', None), [{'name': 'loss'}])

    def test_series_gaps_other_keys_and_bad_lines(self):
        self.append('metrics.jsonl', b''.join([
            line({'step': 0, 'time': 0.5, 'epoch': 0, 'loss': 2.0, 'lr': 0.1, 'note': 'warm-up'}),
            line({'step': 1, 'time': 1.0, 'loss': None, 'lr': 0.1}),
            b'{"step": 2, "time": 1.5, "loss": NaN, "lr": 0.1, "val/loss": 3.0}\n',
            b'not json\n',
            line({'step': -1, 'time': 2.0, 'loss': 1.0}),
            line({'step': 3, 'loss': 1.0}),
            line([1, 2]),
            line({'step': 4, 'time': 2.5, 'loss': 1.0, 'lr': 0.05, 'flag': True, 'big': 10 ** 400}),
            b'\n',
            b'{"step": 5, "time": 3.0, "loss": 0.5' + b' ' * (training.LINE_BYTES + 10) + b'}\n',
        ]))
        got = self.overview()
        by = {s['name']: s for s in got['series']}
        self.assertEqual(list(by), ['loss', 'lr', 'val/loss', 'big'])
        self.assertEqual((by['loss']['points'], by['loss']['nonfinite'], by['loss']['min'], by['loss']['max'],
                          by['loss']['last'], by['loss']['last_step']), (4, 2, 1.0, 2.0, 1.0, 4))
        self.assertEqual((by['lr']['points'], by['lr']['last']), (4, 0.05))
        self.assertEqual((by['val/loss']['points'], by['val/loss']['first_step']), (1, 2))
        self.assertEqual((by['big']['nonfinite'], by['big']['last']), (1, None))
        self.assertEqual(got['other_keys'], ['note', 'flag'])
        self.assertEqual((got['lines'], got['last_step'], got['last_time']), (4, 4, 2.5))
        self.assertEqual(got['bad_lines'], 5)
        self.assertEqual([p['line'] for p in got['problems']], [4, 5, 6, 7, 10])
        self.assertTrue(all(p['file'] == 'training/metrics.jsonl' for p in got['problems']))
        [loss] = self.series('loss')['series']
        self.assertEqual(loss['buckets'], [[0, 0, 0.5, 2.0, 2.0, 2.0], [1, 1, 1.0, None, None, None],
                                           [2, 2, 1.5, None, None, None], [4, 4, 2.5, 1.0, 1.0, 1.0]])
        self.assertEqual(self.series('missing')['series'][0]['points'], 0)

    def test_a_partial_last_line_waits_for_its_end(self):
        self.append('metrics.jsonl', line({'step': 0, 'time': 0.0, 'loss': 1.0}) + b'{"step": 1, "time": 0.1, "lo')
        got = self.overview()
        self.assertEqual((got['lines'], got['bad_lines']), (1, 0))
        self.append('metrics.jsonl', b'ss": 0.5}\n' + line({'step': 2, 'time': 0.2, 'loss': 0.25}))
        got = self.overview()
        self.assertEqual((got['lines'], got['bad_lines'], got['series'][0]['last']), (3, 0, 0.25))
        self.assertEqual([b[3] for b in self.series('loss')['series'][0]['buckets']], [1.0, 0.5, 0.25])

    def test_a_line_too_long_while_it_is_written(self):
        self.append('metrics.jsonl', line({'step': 0, 'time': 0.0, 'loss': 1.0}) + b'{"x": "'
                    + b'a' * (training.LINE_BYTES + 1))
        self.assertEqual(self.overview()['bad_lines'], 1)
        self.append('metrics.jsonl', b'a' * 100 + b'"}\n' + line({'step': 1, 'time': 0.1, 'loss': 0.5}))
        got = self.overview()
        self.assertEqual((got['lines'], got['bad_lines'], got['series'][0]['points']), (2, 1, 2))

    def test_a_file_replaced_or_shortened_is_read_again(self):
        self.append('metrics.jsonl', b''.join(line({'step': i, 'time': i, 'loss': i}) for i in range(5)))
        self.assertEqual(self.overview()['lines'], 5)
        with open(self.path('metrics.jsonl'), 'wb') as handle:   # the same inode, shorter
            handle.write(line({'step': 0, 'time': 0, 'loss': 9.0}))
        got = self.overview()
        self.assertEqual((got['lines'], got['series'][0]['last']), (1, 9.0))
        replacement = self.path('other')
        with open(replacement, 'wb') as handle:   # another file, longer
            handle.write(b''.join(line({'step': i, 'time': i, 'acc': i}) for i in range(7)))
        os.replace(replacement, self.path('metrics.jsonl'))
        got = self.overview()
        self.assertEqual(([s['name'] for s in got['series']], got['lines']), (['acc'], 7))

    def test_buckets_of_a_long_series_and_since(self):
        values = [math.sin(i / 7) * 10 + i for i in range(1000)]
        self.append('metrics.jsonl', b''.join(line({'step': 10 * i, 'time': i / 4, 'loss': v})
                                              for i, v in enumerate(values)))
        [raw] = self.series('loss', most=1000)['series']
        self.assertEqual((raw['size'], len(raw['buckets'])), (1, 1000))
        self.assertEqual([b[3] for b in raw['buckets']], values)
        [got] = self.series('loss', most=100)['series']
        self.assertEqual((got['size'], got['first'], len(got['buckets'])), (16, 0, 63))
        for number, bucket in enumerate(got['buckets']):
            part = values[number * 16:(number + 1) * 16]
            self.assertEqual(bucket[:3], [10 * number * 16, 10 * (number * 16 + len(part) - 1),
                                          (number * 16 + len(part) - 1) / 4])
            self.assertAlmostEqual(bucket[3], math.fsum(part) / len(part), places=12)
            self.assertEqual(bucket[4:], [min(part), max(part)])
        # The page holds 63 buckets of 16; more points arrive; it asks from its last one.
        self.append('metrics.jsonl', b''.join(line({'step': 10 * i, 'time': i / 4, 'loss': float(i)})
                                              for i in range(1000, 1020)))
        [more] = self.series({'name': 'loss', 'size': 16, 'since': 62}, most=100)['series']
        self.assertEqual((more['size'], more['first'], len(more['buckets']), more['points']), (16, 62, 2, 1020))
        self.assertEqual(more['buckets'][-1][1], 10190)
        # Past 1,600 points the size doubles: the page is sent everything again, from 0.
        self.append('metrics.jsonl', b''.join(line({'step': 10 * i, 'time': i / 4, 'loss': 1.0})
                                              for i in range(1020, 1700)))
        [again] = self.series({'name': 'loss', 'size': 16, 'since': 63}, most=100)['series']
        self.assertEqual((again['size'], again['first'], len(again['buckets'])), (32, 0, 54))
        self.assertEqual(training.bucket_size(0, 10), 1)
        self.assertEqual(training.bucket_size(11, 10), 2)

    def test_the_bound_on_lines(self):
        with mock.patch.object(training._Metrics, 'line_most', 3):
            self.append('metrics.jsonl', b''.join(line({'step': i, 'time': i, 'loss': i}) for i in range(6)))
            got = self.overview()
        self.assertEqual((got['lines'], got['truncated']), (3, True))

    def test_the_bound_on_series(self):
        with mock.patch.object(training, 'SERIES', 2):
            self.append('metrics.jsonl', line({'step': 0, 'time': 0, 'a': 1, 'b': 2, 'c': 3}))
            got = self.overview()
        self.assertEqual([s['name'] for s in got['series']], ['a', 'b'])
        self.assertEqual((got['bad_lines'], len(got['problems'])), (0, 1))

    def test_a_file_outside_the_output_is_not_read(self):
        outside = tempfile.NamedTemporaryFile('wb', delete=False)
        self.addCleanup(os.unlink, outside.name)
        outside.write(line({'step': 0, 'time': 0, 'secret': 1}))
        outside.close()
        os.symlink(outside.name, self.path('metrics.jsonl'))
        self.assertEqual(self.overview()['series'], [])


class Histograms(TrainingCase):

    def histogram(self, step, edges, counts, name='layer.weight', kind='weights', **extra):
        self.append('histograms.jsonl', line({'step': step, 'time': step / 10, 'name': name, 'kind': kind,
                                              'edges': edges, 'counts': counts, **extra}))

    def test_rows_re_binned_onto_one_grid(self):
        self.histogram(0, [0.0, 1.0, 2.0], [4, 6])
        self.histogram(10, [1.0, 3.0, 4.0], [10, 2], nonfinite=3)
        self.histogram(10, [0.0, 1.0], [5], kind='gradients')
        self.append('histograms.jsonl', b'{"step": 1}\n' + line({'step': 1, 'time': 0, 'name': 'x', 'kind': 'weights',
                                                                   'edges': [1, 0], 'counts': [1]}))
        got = self.overview()
        self.assertEqual([(h['name'], h['kind'], h['rows'], h['last_step']) for h in got['histograms']],
                         [('layer.weight', 'weights', 2, 10), ('layer.weight', 'gradients', 1, 10)])
        self.assertEqual((got['histogram_lines'], got['bad_lines']), (3, 2))
        h = training.histograms(self.run, name='layer.weight', kind='weights', bins=4)
        json.dumps(h, allow_nan=False)
        self.assertEqual((h['low'], h['high'], h['bins'], h['stride'], h['nonfinite']), (0.0, 4.0, 4, 1, 3))
        self.assertEqual(h['rows'], [{'step': 0, 'time': 0.0}, {'step': 10, 'time': 1.0}])
        self.assertEqual(h['counts'], [[4.0, 6.0, 0.0, 0.0], [0.0, 5.0, 5.0, 2.0]])
        self.assertEqual(h['totals'], [10.0, 12.0])
        h = training.histograms(self.run, name='layer.weight', kind='weights', bins=8)
        self.assertEqual(h['counts'][0], [2.0, 2.0, 3.0, 3.0, 0.0, 0.0, 0.0, 0.0])
        self.refused('not-found', training.histograms, self.run, name='nothing', kind='weights')

    def test_rows_chosen_past_most_keep_the_first_and_the_last(self):
        for step in range(50):
            self.histogram(step, [0.0, 1.0], [step])
        h = training.histograms(self.run, name='layer.weight', kind='weights', most=7, bins=2)
        steps = [row['step'] for row in h['rows']]
        self.assertEqual((len(steps), steps[0], steps[-1], h['stride']), (7, 0, 49, 49 / 6))
        self.assertEqual(steps, sorted(set(steps)))

    def test_rebin_keeps_the_total(self):
        counts = training.rebin([-1.0, -0.3, 0.2, 0.9, 0.9, 2.5], [3, 5, 7, 2, 11], -1.0, 2.5, 7)
        self.assertAlmostEqual(math.fsum(counts), 28.0, places=12)
        self.assertEqual(training.rebin([1.0, 1.0], [4], 1.0, 1.0, 5), [0.0, 0.0, 4.0, 0.0, 0.0])


class Samples(TrainingCase):

    def sample(self, step, name, path, data=None):
        if data is not None:
            with open(os.path.join(self.root, 'training', path), 'wb') as handle:
                handle.write(data)
        self.append('samples.jsonl', line({'step': step, 'time': step / 10, 'name': name, 'path': path}))

    def test_images_arrays_missing_files_and_bad_paths(self):
        self.sample(10, 'prediction', 'samples/000000010-prediction.png', png(5, 3))
        self.sample(10, 'field', 'samples/000000010-field.npy', npy((2, 3), '<f4', lambda i: float(i[0] * 3 + i[1])))
        self.sample(20, 'prediction', 'samples/000000020-prediction.png')
        self.sample(20, 'prediction', 'samples/../../escape.png')
        self.sample(20, 'prediction', 'elsewhere/x.png')
        self.sample(20, 'prediction', 'samples/x.txt')
        got = self.overview()
        self.assertEqual(got['samples'], [{'name': 'prediction', 'count': 2, 'last_step': 20},
                                          {'name': 'field', 'count': 1, 'last_step': 10}])
        self.assertEqual((got['sample_lines'], got['bad_lines']), (3, 3))
        listed = training.samples(self.run, name='prediction')
        self.assertEqual(listed['total'], 2)
        first, missing = listed['samples']
        self.assertEqual((first['index'], first['kind'], first['bytes'], first['problem']),
                         (0, 'image', len(png(5, 3)), None))
        self.assertEqual(first['url'], '/api/project/file?run=run-1&path=training%2Fsamples%2F000000010-prediction.png')
        self.assertEqual((missing['index'], missing['problem']), (2, 'The file is missing.'))
        self.assertEqual(training.samples(self.run, offset=1, limit=1)['samples'][0]['name'], 'field')
        image = training.sample(self.run, index=0)
        self.assertEqual((image['content']['width'], image['content']['height']), (5, 3))
        array = training.sample(self.run, index=1)
        json.dumps(array, allow_nan=False)
        self.assertEqual((array['content']['shape'], floats(array['content']['values_f32'])),
                         ([2, 3], [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]))
        self.refused('not-found', training.sample, self.run, index=2)
        self.refused('not-found', training.sample, self.run, index=9)


class Checkpoints(TrainingCase):

    def test_checkpoints_and_the_start(self):
        with open(self.path('training.json'), 'w') as handle:
            json.dump({'format': 'tuldok_training_v1', 'started_at': '2026-11-19T10:00:00+00:00'}, handle)
        self.append('checkpoints.jsonl', line({'step': 100, 'time': 5.0, 'path': 'ck/100.safetensors', 'loss': 0.5,
                                               'tag': 'best'}) + line({'time': 1}))
        got = self.overview()
        self.assertEqual(got['started_at'], '2026-11-19T10:00:00+00:00')
        self.assertEqual(got['checkpoints'], [{'step': 100, 'time': 5.0, 'path': 'ck/100.safetensors',
                                               'figures': {'loss': 0.5}}])
        self.assertEqual(got['bad_lines'], 1)


# ------------------------------------------------------------------ the operations

class Operations(builds_base.BuildCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        training.forget()
        self.addCleanup(training.forget)
        self.build('recipes/fit-a')
        with self.opened() as project:
            self.run_id, directory = project._execute(
                "SELECT id, directory FROM {schema}.runs WHERE reference = 'recipes/fit-a'").fetchone()
        self.output = Path(directory, builds.OUTPUT)
        files = self.output / 'training'
        (files / 'samples').mkdir(parents=True)
        (files / 'metrics.jsonl').write_bytes(b''.join(line({'step': i, 'time': i / 2, 'loss': 1 / (i + 1)})
                                                       for i in range(10)))
        (files / 'histograms.jsonl').write_bytes(line({'step': 0, 'time': 0, 'name': 'w', 'kind': 'weights',
                                                       'edges': [0, 1, 2], 'counts': [1, 3]}))
        (files / 'samples' / '000000005-out.png').write_bytes(png(4, 4))
        (files / 'samples.jsonl').write_bytes(line({'step': 5, 'time': 2.5, 'name': 'out',
                                                    'path': 'samples/000000005-out.png'}))
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, operation, **arguments):
        result = self.service.call(operation, arguments, OWNER)
        json.dumps(result, allow_nan=False)
        return result

    def mark(self, state):
        with self.opened() as project:
            project._execute('UPDATE {schema}.runs SET state = %s WHERE id = %s', (state, self.run_id))

    def test_a_running_run_is_read_and_its_samples_served(self):
        self.mark('running')
        got = self.call('training', run=self.run_id[:8])
        self.assertEqual((got['run']['state'], got['run']['active'], got['present'], got['lines']),
                         ('running', True, True, 10))
        [loss] = self.call('training_series', run=self.run_id, series=[{'name': 'loss'}], most=4)['series']
        self.assertEqual((loss['size'], len(loss['buckets'])), (4, 3))
        self.assertEqual(self.call('training_histograms', run=self.run_id, name='w', kind='weights', bins=2)['counts'],
                         [[1.0, 3.0]])
        listed = self.call('training_samples', run=self.run_id)
        self.assertEqual(listed['total'], 1)
        self.assertEqual(self.call('training_sample', run=self.run_id, index=0)['content']['width'], 4)
        served = self.service.product_file(self.run_id, 'training/samples/000000005-out.png')
        self.assertEqual(b''.join(served.chunks), png(4, 4))
        for address in ('weights.json', 'training/../weights.json'):
            with self.assertRaises(store.ProjectError) as caught:
                self.service.product_file(self.run_id, address)
            self.assertIn(caught.exception.code, ('not-found', 'invalid'))
        # Lines appended while it runs are read by the next call.
        with open(self.output / 'training' / 'metrics.jsonl', 'ab') as handle:
            handle.write(line({'step': 10, 'time': 5.0, 'loss': 0.01}) + b'{"step": 11')
        self.assertEqual(self.call('training', run=self.run_id)['lines'], 11)

    def test_a_queued_run_without_a_directory_has_nothing_logged(self):
        with self.opened() as project:
            project._execute("UPDATE {schema}.runs SET state = 'queued', directory = %s WHERE id = %s",
                             (str(self.temporary / 'not-yet'), self.run_id))
        got = self.call('training', run=self.run_id)
        self.assertEqual((got['present'], got['run']['active']), (False, True))
        for name, arguments in (('training_series', {'series': [{'name': 'loss'}]}),
                                ('training_samples', {}), ('training_sample', {'index': 0}),
                                ('training_histograms', {'name': 'w', 'kind': 'weights'})):
            with self.assertRaises(store.ProjectError) as caught:
                self.service.call(name, {'run': self.run_id, **arguments}, OWNER)
            self.assertEqual(caught.exception.code, 'not-found', name)

    def test_arguments_are_checked_and_nothing_is_written(self):
        before = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        refused = []
        for name, arguments in (('training_series', {'series': []}),
                                ('training_series', {'series': [{'name': 'loss', 'size': -1}]}),
                                ('training_series', {'series': [{'name': 'x'}] * 17}),
                                ('training_histograms', {'name': 'w', 'kind': 'activations'}),
                                ('training_samples', {'limit': 201}), ('training', {'run': 'abcdef0123'})):
            with self.assertRaises(store.ProjectError) as caught:
                self.service.call(name, {'run': self.run_id, **arguments}, OWNER)
            refused.append(caught.exception.code)
        self.assertEqual(refused, ['invalid', 'invalid', 'invalid', 'invalid', 'invalid', 'not-found'])
        self.call('training', run=self.run_id)
        after = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        self.assertEqual(before, after)
        with self.opened() as project:
            self.assertEqual(project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0], 0)


class Published(unittest.TestCase):

    def test_the_five_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in TRAINING:
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        from tuldok_project import service
        self.assertEqual(set(TRAINING), set(service.TRAINING_READS))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in TRAINING} <= folder)
        self.assertFalse({'project.' + name for name in TRAINING} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
