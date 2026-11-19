"""tuldok_log writes the training files Tuldok reads (docs/plans/training-and-curation/spec-t1.md, slice T1b).

The Logger is tested with the standard library and read back with Tuldok's own
reader (tuldok_project.training) when it can be imported. autolog needs
PyTorch and is skipped when it cannot be imported; Tuldok's environment has no
PyTorch, so run this file with an interpreter that has it (on the CPU) to
cover it, for example the lab's:

    <lab>/.venv/bin/python -m unittest tests/test_tuldok_log.py

There the reader may not be importable (its database driver is absent); the
lines are then checked as JSON against the contract by this file itself.
"""
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tuldok_log  # noqa: E402

try:
    from tuldok_project import training as reader
except ImportError:  # an interpreter without Tuldok's own requirements
    reader = None
try:
    import torch
except ImportError:
    torch = None


def png(width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\x00' + b'\x10\x20\x30' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def lines(path):
    raw = Path(path).read_bytes()
    assert raw.endswith(b'\n'), 'every line is whole'
    return [json.loads(text) for text in raw.decode('utf-8').splitlines()]


def npy_values(data):
    """(descr, shape, values) of a little-endian .npy of version 1 written by tuldok_log."""
    assert data[:8] == b'\x93NUMPY\x01\x00'
    length = struct.unpack('<H', data[8:10])[0]
    header = eval(data[10:10 + length].decode('latin-1'), {})  # the test's own bytes
    assert (10 + length) % 64 == 0
    body = data[10 + length:]
    code = {'<f4': 'f', '<f8': 'd', '<i8': 'q', '|u1': 'B'}[header['descr']]
    return header['descr'], header['shape'], list(struct.unpack(f'<{len(body) // struct.calcsize(code)}{code}', body))


def contract_histogram(line):
    """The contract's checks of a histogram line (section 2.2), made here when the reader is absent."""
    if reader is not None:
        return reader.histogram_problem(line)
    edges, counts = line['edges'], line['counts']
    ok = (line['kind'] in ('weights', 'gradients') and isinstance(line['step'], int) and len(edges) == len(counts) + 1
          and all(math.isfinite(e) for e in edges) and edges == sorted(edges) and all(c >= 0 for c in counts))
    return None if ok else 'not a histogram line'


class LoggerCase(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = directory.name
        self.files = os.path.join(self.output, 'training')
        if reader is not None:
            reader.forget()

    def test_metrics_with_gaps_and_the_start(self):
        with tuldok_log.Logger(self.output) as log:
            log.log(0, loss=2.5, lr=0.1)
            log.log(1, epoch=0, loss=float('nan'), lr=0.1, acc=None)
            log.log(2, loss=float('inf'), extra=3)
            with self.assertRaises(ValueError):
                log.log(3, time=1.0)
        got = lines(os.path.join(self.files, 'metrics.jsonl'))
        self.assertEqual([(g['step'], g.get('loss'), g.get('epoch')) for g in got],
                         [(0, 2.5, None), (1, None, 0.0), (2, None, None)])
        self.assertTrue(all(isinstance(g['time'], float) and g['time'] >= 0 for g in got))
        self.assertEqual(got[1]['acc'], None)
        started = json.loads(Path(self.files, 'training.json').read_text())
        self.assertEqual(started['format'], 'tuldok_training_v1')
        if reader is not None:
            run = reader.Run('r', 'running', self.output)
            seen = reader.overview(run)
            self.assertEqual(seen['started_at'], started['started_at'])
            self.assertEqual({s['name']: (s['points'], s['nonfinite']) for s in seen['series']},
                             {'loss': (3, 2), 'lr': (2, 0), 'acc': (1, 1), 'extra': (1, 0)})
            self.assertEqual(seen['bad_lines'], 0)

    def test_histograms_from_lists_and_objects(self):
        class Values:   # an object with tolist(), as an array is
            def tolist(self):
                return [[0.0, 1.0], [2.0, 3.0]]
        with tuldok_log.Logger(self.output) as log:
            log.log_histograms(5, tensors={'a': [0.0, 0.5, 1.0, 1.0, float('nan')], 'b': Values(), 'c': [7.0, 7.0],
                                           'd': [float('nan')]}, bins=4)
        got = lines(os.path.join(self.files, 'histograms.jsonl'))
        self.assertEqual([g['name'] for g in got], ['a', 'b', 'c'])
        a, b, c = got
        self.assertEqual((a['edges'], a['counts'], a['nonfinite']), ([0.0, 0.25, 0.5, 0.75, 1.0], [1, 0, 1, 2], 1))
        self.assertEqual((b['counts'], b['kind'], b['step']), ([1, 1, 1, 1], 'weights', 5))
        self.assertEqual((c['edges'][0], c['edges'][-1], sum(c['counts'])), (6.5, 7.5, 2))
        self.assertTrue(all(contract_histogram(g) is None for g in got))
        if reader is not None:
            h = reader.histograms(reader.Run('r', 'running', self.output), name='a', kind='weights', bins=4)
            self.assertEqual(h['counts'], [[1.0, 0.0, 1.0, 2.0]])

    def test_samples_png_and_arrays(self):
        with tuldok_log.Logger(self.output) as log:
            first = log.log_sample(10, 'prediction', png(3, 2))
            second = log.log_sample(10, 'field map', [[1, 2, 3], [4, 5, 6]])
            with self.assertRaises(ValueError):
                log.log_sample(11, 'bad', b'not a png')
            with self.assertRaises(ValueError):
                log.log_sample(11, 'ragged', [[1, 2], [3]])
        self.assertEqual((first, second), ('samples/000000010-prediction.png', 'samples/000000010-field_map.npy'))
        self.assertEqual(Path(self.files, first).read_bytes(), png(3, 2))
        self.assertEqual(npy_values(Path(self.files, second).read_bytes()),
                         ('<f4', (2, 3), [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))
        self.assertEqual([(g['name'], g['path']) for g in lines(os.path.join(self.files, 'samples.jsonl'))],
                         [('prediction', first), ('field map', second)])
        self.assertEqual([name for name in os.listdir(os.path.join(self.files, 'samples')) if name.endswith('.part')],
                         [])
        if reader is not None:
            run = reader.Run('r', 'running', self.output)
            self.assertEqual(reader.sample(run, index=0)['content']['width'], 3)
            self.assertEqual(reader.sample(run, index=1)['content']['shape'], [2, 3])

    def test_an_array_like_object_keeps_its_type(self):
        class Dtype:
            str, kind = '<i8', 'i'

        class Array:
            dtype, shape = Dtype(), (2, 2)

            def tobytes(self, order='C'):
                return struct.pack('<4q', 1, -2, 3, -4)
        with tuldok_log.Logger(self.output) as log:
            path = log.log_sample(0, 'counts', Array())
        self.assertEqual(npy_values(Path(self.files, path).read_bytes()), ('<i8', (2, 2), [1, -2, 3, -4]))

    def test_checkpoints(self):
        with tuldok_log.Logger(self.output) as log:
            log.checkpoint(100, 'checkpoints/100.safetensors', loss=0.5)
        [got] = lines(os.path.join(self.files, 'checkpoints.jsonl'))
        self.assertEqual((got['step'], got['path'], got['loss']), (100, 'checkpoints/100.safetensors', 0.5))

    def test_lines_from_several_threads_are_whole(self):
        log = tuldok_log.Logger(self.output)
        self.addCleanup(log.close)

        def write(offset):
            for step in range(200):
                log.log(offset + step, value=step, padding=float(step) / 3)
        threads = [threading.Thread(target=write, args=(1000 * n,)) for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        got = lines(os.path.join(self.files, 'metrics.jsonl'))
        self.assertEqual(len(got), 800)
        self.assertEqual(sorted(g['step'] for g in got), sorted(1000 * n + s for n in range(4) for s in range(200)))


@unittest.skipIf(torch is None, 'PyTorch is not importable here; run this file with an interpreter that has it')
class Autolog(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.output = directory.name
        self.files = os.path.join(self.output, 'training')
        torch.manual_seed(0)
        self.model = torch.nn.Sequential(torch.nn.Linear(3, 5), torch.nn.Tanh(), torch.nn.Linear(5, 1))
        self.x = torch.randn(32, 3)
        self.y = (self.x ** 2).sum(1, keepdim=True)

    def train(self, steps, optimizer, criterion, track=None):
        for _ in range(steps):
            optimizer.zero_grad()
            loss = criterion(self.model(self.x), self.y)
            loss.backward()
            if track is not None:
                track.note(loss=loss.item())
            optimizer.step()

    def test_autolog_records_loss_lr_grad_norm_and_histograms(self):
        optimizer = torch.optim.SGD(self.model.parameters(), lr=0.05)
        criterion = torch.nn.MSELoss()
        expected_norms, losses = {}, []

        def watch(opt, args, kwargs):   # the test's own gradient norm, before the step
            norms = [p.grad.norm(2) ** 2 for p in self.model.parameters()]
            expected_norms[len(losses)] = math.sqrt(float(sum(norms)))
        optimizer.register_step_pre_hook(watch)
        track = tuldok_log.autolog(self.model, optimizer, directory=self.output, every=2, loss=criterion)
        for _ in range(10):
            optimizer.zero_grad()
            loss = criterion(self.model(self.x), self.y)
            losses.append(loss.item())
            loss.backward()
            optimizer.step()
        track.close()
        self.assertEqual(track.steps, 10)
        metrics = lines(os.path.join(self.files, 'metrics.jsonl'))
        self.assertEqual([m['step'] for m in metrics], [1, 2, 4, 6, 8, 10])
        for m in metrics:
            self.assertEqual(set(m) - {'time'}, {'step', 'loss', 'lr', 'grad_norm'})
            self.assertEqual(m['lr'], 0.05)
            self.assertAlmostEqual(m['grad_norm'], expected_norms[m['step']], places=5)
        self.assertAlmostEqual(metrics[0]['loss'], losses[0], places=6)
        self.assertAlmostEqual(metrics[2]['loss'], (losses[2] + losses[3]) / 2, places=6)
        histograms = lines(os.path.join(self.files, 'histograms.jsonl'))
        names = [name for name, _ in self.model.named_parameters()]
        for kind in ('weights', 'gradients'):
            rows = [h for h in histograms if h['kind'] == kind]
            self.assertEqual(sorted({h['name'] for h in rows}), sorted(names), kind)
            self.assertEqual(sorted({h['step'] for h in rows}), [1, 2, 4, 6, 8, 10], kind)
        for h in histograms:
            self.assertIsNone(contract_histogram(h))
            parameter = dict(self.model.named_parameters())[h['name']]
            self.assertEqual(sum(h['counts']), parameter.numel())
        # close() removed the hooks: training on writes nothing more.
        size = os.path.getsize(os.path.join(self.files, 'metrics.jsonl'))
        self.train(4, optimizer, criterion)
        self.assertEqual(os.path.getsize(os.path.join(self.files, 'metrics.jsonl')), size)

    def test_note_and_several_parameter_groups(self):
        first, second = self.model[0], self.model[2]
        optimizer = torch.optim.Adam([{'params': first.parameters(), 'lr': 0.01},
                                      {'params': second.parameters(), 'lr': 0.001}])
        with tuldok_log.autolog(self.model, optimizer, directory=self.output, every=3, histograms_every=100) as track:
            self.train(6, optimizer, torch.nn.MSELoss(), track)
            track.note(accuracy=0.75)
            self.train(1, optimizer, torch.nn.MSELoss(), track)
        metrics = lines(os.path.join(self.files, 'metrics.jsonl'))
        self.assertEqual([m['step'] for m in metrics], [1, 3, 6])
        self.assertEqual((metrics[0]['lr/0'], metrics[0]['lr/1']), (0.01, 0.001))
        self.assertNotIn('accuracy', metrics[-1])
        histograms = lines(os.path.join(self.files, 'histograms.jsonl'))
        self.assertEqual({h['step'] for h in histograms}, {1})
        with tuldok_log.Logger(self.output) as log:   # a tensor sample and a tensor histogram
            path = log.log_sample(7, 'out', self.model(self.x).detach())
            log.log_histograms(7, tensors={'w': self.model[0].weight})
        descr, shape, values = npy_values(Path(self.files, path).read_bytes())
        self.assertEqual((descr, shape, len(values)), ('<f4', (32, 1), 32))
        self.assertEqual(sum(lines(os.path.join(self.files, 'histograms.jsonl'))[-1]['counts']), 15)


if __name__ == '__main__':
    unittest.main()
