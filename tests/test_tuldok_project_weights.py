"""A model's weights, layer by layer (docs/plans/definition-first-projects/spec-d2.md, slice D2a).

The readers are tested on files the tests write with the standard library
(NPY and safetensors with struct and json, NPZ with zipfile) and need no
database: a Product is given the outputs its products row would record. The
operations need one and run only when TULDOK_DATABASE_URL names a disposable
cluster: they adopt products for recipes/fit-a (as test_tuldok_project_inside
does for datasets/numbers) and write their fixture files into the output
directory. No GPU is used.
"""
import builtins
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import adoption, inside, inside_archive, inside_weights, local, operations, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
from test_tuldok_project_inside import OWNER, f32, floats, npy, zip_bytes  # noqa: E402

WEIGHTS = ('weights', 'weights_compare', 'array_tiles')
# safetensors type -> (struct code, NPY descr)
TYPES = {'F16': ('e', '<f2'), 'F32': ('f', '<f4'), 'F64': ('d', '<f8'), 'I8': ('b', '|i1'), 'I16': ('h', '<i2'),
         'I32': ('i', '<i4'), 'I64': ('q', '<i8'), 'U8': ('B', '|u1'), 'U16': ('H', '<u2'), 'U32': ('I', '<u4'),
         'U64': ('Q', '<u8'), 'BOOL': ('?', '|b1')}


def _flat(shape, value):
    """The values of value(index) over shape, in C order."""
    indexes = [()]
    for size in shape:
        indexes = [index + (position,) for index in indexes for position in range(size)]
    return [value(index) for index in indexes]


def safetensors(tensors, *, metadata=None):
    """The bytes of a safetensors file of [(name, dtype, shape, raw bytes)], in that order."""
    header, data = {}, b''
    if metadata is not None:
        header['__metadata__'] = metadata
    for name, dtype, shape, raw in tensors:
        header[name] = {'dtype': dtype, 'shape': list(shape), 'data_offsets': [len(data), len(data) + len(raw)]}
        data += raw
    text = json.dumps(header).encode()
    text += b' ' * ((-len(text)) % 8)
    return struct.pack('<Q', len(text)) + text + data


def packed(dtype, values):
    return struct.pack('<' + TYPES[dtype][0] * len(values), *values)


def f4(shape, value):
    """(raw little-endian float32 bytes, the values as float32) of value over shape."""
    values = [f32(item) for item in _flat(shape, value)]
    return packed('F32', values), values


def npz(arrays):
    """An .npz of {name: (shape, value)} in float32, members in the order given."""
    return zip_bytes({name + '.npy': npy(shape, '<f4', value) for name, (shape, value) in arrays.items()})


def norm(values):
    return math.sqrt(math.fsum(value * value for value in values))


class ReaderCase(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = os.path.realpath(directory.name)
        inside_archive.forget_members()
        inside.forget_indexes()
        self.product = inside.Product('run-1', self.root)

    def write(self, address, data):
        path = Path(self.root, address)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def refused(self, code, call, *arguments, **options):
        with self.assertRaises(store.ProjectError) as caught:
            call(*arguments, **options)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception


# ------------------------------------------------------------------ safetensors

class SafeTensors(ReaderCase):

    def test_every_type_reads_as_the_same_values_in_an_npz(self):
        tensors, arrays = [], {}
        for dtype, (code, descr) in TYPES.items():
            if dtype == 'BOOL':
                value = lambda index: (index[0] + index[1]) % 2 == 0  # noqa: E731
            elif dtype[0] == 'F':
                value = lambda index: index[0] * 1.5 - index[1]  # noqa: E731
            elif dtype[0] == 'I':
                value = lambda index: index[0] * 7 - index[1] * 9  # noqa: E731
            else:
                value = lambda index: index[0] * 7 + index[1]  # noqa: E731
            tensors.append((f'layer.{dtype.lower()}', dtype, (3, 4), packed(dtype, _flat((3, 4), value))))
            arrays[f'layer.{dtype.lower()}.npy'] = npy((3, 4), descr, value)
        tensors.append(('layer.bf16', 'BF16', (2, 2), b'\x00' * 8))
        self.write('model.safetensors', safetensors(tensors, metadata={'format': 'pt'}))
        self.write('model.npz', zip_bytes(arrays))
        listed = inside.inside(self.product, path='model.safetensors')
        by_name = {entry['array']: (entry['shape'], entry['dtype'], entry['type']) for entry in listed['entries']}
        self.assertEqual(by_name['layer.bf16'], ([2, 2], 'BF16', 'array'))
        reference = {entry['array']: (entry['shape'], entry['dtype'], entry['type'])
                     for entry in inside.inside(self.product, path='model.npz')['entries']}
        self.assertEqual({name: item for name, item in by_name.items() if name != 'layer.bf16'}, reference)
        for dtype in TYPES:
            name = f'layer.{dtype.lower()}'
            with self.subTest(dtype):
                for call, options in ((inside.array_slice, {}), (inside.array_slice, {'axes': [1, 0], 'index': [0, 0]}),
                                      (inside.array_summary, {'bins': 8})):
                    self.assertEqual(call(self.product, path='model.safetensors', array=name, **options),
                                     call(self.product, path='model.npz', array=name, **options))
        error = self.refused('unsupported', inside.array_slice, self.product, path='model.safetensors',
                             array='layer.bf16')
        self.assertIn('BF16', str(error))
        self.refused('not-found', inside.array_slice, self.product, path='model.safetensors', array='nothing')
        self.refused('invalid', inside.array_slice, self.product, path='model.safetensors')
        root = {entry['name']: (entry['type'], entry['kind']) for entry in inside.inside(self.product)['entries']}
        self.assertEqual(root['model.safetensors'], ('archive', 'array'))
        record = inside.record(self.product, 'model.safetensors')
        self.assertEqual(record['content']['arrays'][0]['array'], 'layer.f16')   # the order of the header

    def test_damaged_headers_are_refused(self):
        raw, _ = f4((2, 2), lambda index: 1.0)
        good = safetensors([('w', 'F32', (2, 2), raw)])
        length = struct.unpack('<Q', good[:8])[0]
        header = json.loads(good[8:8 + length])

        def with_header(changed):
            text = json.dumps(changed).encode()
            text += b' ' * ((-len(text)) % 8)
            return struct.pack('<Q', len(text)) + text + raw
        cases = {
            'long.safetensors': struct.pack('<Q', len(good) * 10) + good[8:],
            'huge.safetensors': struct.pack('<Q', 1 << 40) + good[8:],
            'outside.safetensors': with_header({'w': {**header['w'], 'data_offsets': [0, 4000]}}),
            'overlap.safetensors': with_header({'w': {**header['w'], 'data_offsets': [-8, 8]}}),
            'reversed.safetensors': with_header({'w': {**header['w'], 'data_offsets': [16, 0]}}),
            'mismatch.safetensors': with_header({'w': {**header['w'], 'shape': [3, 3]}}),
            'notjson.safetensors': struct.pack('<Q', 8) + b'{"w": [1' + raw,
            'short.safetensors': b'\x01\x02',
        }
        for name, data in cases.items():
            self.write(name, data)
            with self.subTest(name):
                self.refused('unsupported', inside.inside, self.product, path=name)
                self.refused('unsupported', inside.array_slice, self.product, path=name, array='w')
                files = inside_weights.weights(inside.Product('run-1', self.root, outputs={
                    'weights': {'path': name, 'role': 'weights', 'bytes': len(data)}}))['files']
                self.assertEqual([(item['readable'], item['reason'][:20]) for item in files],
                                 [(False, 'It could not be read')])
        self.write('fine.safetensors', good)
        self.assertEqual(inside.array_summary(self.product, path='fine.safetensors', array='w')['mean'], 1.0)


# ------------------------------------------------------------------ weights

class Weights(ReaderCase):

    def product_with(self, outputs):
        return inside.Product('run-1', self.root, outputs=outputs)

    def test_layers_grouped_in_file_order_with_parameter_counts(self):
        arrays = {'encoder.1.weight': ((4, 3), lambda index: 1.0), 'encoder.1.bias': ((4,), lambda index: 0.0),
                  'head.weight': ((2, 4), lambda index: 2.0), 'scale': ((1,), lambda index: 1.0),
                  'encoder.0.weight': ((3, 3, 3), lambda index: 1.0)}
        self.write('weights.npz', npz(arrays))
        self.write('notes.txt', b'not weights')
        self.write('model-final.safetensors', safetensors([('b.weight', 'F32', (2,), f4((2,), lambda i: 1.0)[0]),
                                                           ('a.weight', 'F32', (3,), f4((3,), lambda i: 1.0)[0]),
                                                           ('b.bias', 'BF16', (5,), b'\x00' * 10)]))
        self.write('other.npz', npz({'x': ((2,), lambda index: 1.0)}))   # no weight or model in its name
        self.write('initial-weights.npz', npz({'scale': ((1,), lambda index: 0.0)}))
        files = inside_weights.weights(self.product)['files']
        self.assertEqual([(item['path'], item['output'], item['readable'], item['starts_from']) for item in files],
                         [('model-final.safetensors', None, True, None),
                          ('weights.npz', None, True, 'initial-weights.npz')])
        found = files[1]
        self.assertEqual(found['parameters'], 12 + 4 + 8 + 1 + 27)
        self.assertEqual((found['tensors'], found['reason'], found['bytes']),
                         (5, None, os.path.getsize(Path(self.root, 'weights.npz'))))
        self.assertEqual([(layer['name'], layer['parameters'], [tensor['name'] for tensor in layer['tensors']])
                          for layer in found['layers']],
                         [('encoder.1', 16, ['weight', 'bias']), ('head', 8, ['weight']), ('scale', 1, ['scale']),
                          ('encoder.0', 27, ['weight'])])
        self.assertEqual(found['layers'][0]['tensors'][0],
                         {'array': 'encoder.1.weight', 'name': 'weight', 'shape': [4, 3], 'dtype': 'float32',
                          'parameters': 12})
        safe = files[0]
        self.assertEqual([(layer['name'], [tensor['dtype'] for tensor in layer['tensors']])
                          for layer in safe['layers']],
                         [('b', ['float32', 'BF16']), ('a', ['float32'])])
        self.assertEqual(safe['parameters'], 10)
        with mock.patch.object(inside_weights, 'TENSORS', 2):
            limited = inside_weights.weights(self.product)['files'][1]
        self.assertEqual((limited['tensors'], sum(len(layer['tensors']) for layer in limited['layers'])), (5, 2))

    def test_a_declared_output_comes_first_and_a_directory_gives_its_files(self):
        self.write('weights.npz', npz({'w': ((2,), lambda index: 1.0)}))   # found by name only without outputs
        self.write('checkpoints/last.safetensors', safetensors([('w', 'F32', (2,), f4((2,), lambda i: 1.0)[0])]))
        self.write('checkpoints/initial-last.safetensors',
                   safetensors([('w', 'F32', (2,), f4((2,), lambda i: 0.0)[0])]))
        self.write('checkpoints/readme.txt', b'x')
        self.write('fit.npz', npz({'w': ((3,), lambda index: 1.0)}))
        outputs = {'model': {'path': 'fit.npz', 'role': 'weights', 'bytes': 1},
                   'history': {'path': 'checkpoints', 'role': 'weights', 'bytes': 1},
                   'results': {'path': 'weights.npz', 'role': 'results', 'bytes': 1},
                   'gone': {'path': 'missing.npz', 'role': 'weights', 'bytes': 1}}
        files = inside_weights.weights(self.product_with(outputs))['files']
        self.assertEqual([(item['path'], item['output'], item['readable'], item['starts_from']) for item in files],
                         [('fit.npz', 'model', True, None),
                          ('checkpoints/last.safetensors', 'history', True, 'checkpoints/initial-last.safetensors'),
                          ('missing.npz', 'gone', False, None)])
        self.assertEqual((files[0]['parameters'], files[2]['bytes'], files[2]['reason']),
                         (3, None, 'The file is not in the product.'))
        declared_json = self.product_with({'weights': {'path': 'weights.json', 'role': 'weights', 'bytes': 2}})
        self.write('weights.json', b'{}')
        [item] = inside_weights.weights(declared_json)['files']
        self.assertEqual((item['readable'], item['bytes']), (False, 2))
        self.assertIn('.npz and .safetensors', item['reason'])

    def test_a_pytorch_file_is_listed_and_never_opened(self):
        pickle = b'\x80\x04 a pickle that must not be read'
        self.write('model.pt', pickle)
        self.write('model.onnx', b'onnx')
        os.chmod(Path(self.root, 'model.pt'), 0)
        self.addCleanup(os.chmod, Path(self.root, 'model.pt'), 0o644)
        opened = []
        real_open, real_os_open = builtins.open, os.open

        def watch_open(file, *arguments, **options):
            opened.append(os.fspath(file) if not isinstance(file, int) else file)
            return real_open(file, *arguments, **options)

        def watch_os_open(path, *arguments, **options):
            opened.append(os.fspath(path))
            return real_os_open(path, *arguments, **options)
        with mock.patch('builtins.open', watch_open), mock.patch('os.open', watch_os_open):
            files = inside_weights.weights(self.product)['files']
        self.assertFalse([path for path in opened if str(path).endswith('model.pt')])
        self.assertEqual([(item['path'], item['readable'], item['bytes']) for item in files],
                         [('model.onnx', False, 4), ('model.pt', False, len(pickle))])
        self.assertIn('pickle', files[1]['reason'])
        self.assertIn('ONNX', files[0]['reason'])
        self.assertNotIn('layers', files[1])
        error = self.refused('unsupported', inside_weights.weights_compare, self.product, path='model.pt',
                             other=self.product, other_path='model.pt')
        self.assertIn('pickle', str(error))


# ------------------------------------------------------------------ compare

class Compare(ReaderCase):

    def compare(self, path, other_path, other=None):
        result = inside_weights.weights_compare(self.product, path=path, other=other or self.product,
                                                other_path=other_path)
        json.dumps(result, allow_nan=False)   # the reader itself gives no NaN or infinity
        return result

    def test_identical_files(self):
        data = npz({'a.weight': ((3, 5), lambda index: index[0] - index[1] * 0.25),
                    'a.bias': ((5,), lambda index: index[0] + 1.0)})
        self.write('weights.npz', data)
        self.write('initial-weights.npz', data)
        got = self.compare('weights.npz', 'initial-weights.npz')
        for row in got['tensors'] + [got['total']]:
            self.assertEqual((row['difference_norm'], row['relative_change'], row['cosine'], row['largest_change'],
                              row['nonfinite']), (0.0, 0.0, 1.0, 0.0, 0))
            self.assertEqual(row['norm'], row['other_norm'])
        self.assertEqual([row['array'] for row in got['tensors']], ['a.weight', 'a.bias'])
        self.assertEqual((got['total']['parameters'], got['only_here'], got['only_there'], got['reshaped']),
                         (20, [], [], []))

    def test_a_known_difference_missing_reshaped_and_zero_tensors(self):
        def here_value(index):
            return index[0] * 0.5 - index[1]

        def there_value(index):
            return here_value(index) + (0.125 if (index[0] + index[1]) % 3 == 0 else -0.25)
        self.write('weights.npz', npz({'w': ((4, 6), here_value), 'zero': ((3,), lambda index: 2.0),
                                       'grown': ((2, 2), lambda index: 1.0), 'new': ((2,), lambda index: 1.0)}))
        # The other side as safetensors: a file of each format compares like any other.
        raw_w, there = f4((4, 6), there_value)
        self.write('initial-weights.safetensors', safetensors([
            ('w', 'F32', (4, 6), raw_w), ('zero', 'F32', (3,), f4((3,), lambda index: 0.0)[0]),
            ('grown', 'F32', (2, 3), f4((2, 3), lambda index: 1.0)[0]),
            ('dropped', 'F32', (1,), f4((1,), lambda index: 1.0)[0])]))
        got = self.compare('weights.npz', 'initial-weights.safetensors')
        here = [f32(value) for value in _flat((4, 6), here_value)]
        difference = [a - b for a, b in zip(here, there)]
        rows = {row['array']: row for row in got['tensors']}
        w = rows['w']
        self.assertAlmostEqual(w['norm'], norm(here), places=12)
        self.assertAlmostEqual(w['other_norm'], norm(there), places=12)
        self.assertAlmostEqual(w['difference_norm'], norm(difference), places=12)
        self.assertAlmostEqual(w['relative_change'], norm(difference) / norm(there), places=12)
        self.assertAlmostEqual(w['cosine'], math.fsum(a * b for a, b in zip(here, there)) / (norm(here) * norm(there)),
                               places=12)
        self.assertEqual(w['largest_change'], max(abs(value) for value in difference))
        zero = rows['zero']
        self.assertEqual((zero['norm'], zero['other_norm'], zero['relative_change'], zero['cosine'],
                          zero['largest_change']), (math.sqrt(12), 0.0, None, None, 2.0))
        self.assertEqual((got['only_here'], got['only_there']), (['new'], ['dropped']))
        self.assertEqual(got['reshaped'], [{'array': 'grown', 'shape': [2, 2], 'other_shape': [2, 3]}])
        total = got['total']
        self.assertEqual(total['parameters'], 27)
        self.assertAlmostEqual(total['difference_norm'], norm(difference + [2.0] * 3), places=12)
        self.assertAlmostEqual(total['relative_change'], norm(difference + [2.0] * 3) / norm(there), places=12)
        self.assertEqual(total['largest_change'], 2.0)
        self.assertEqual(self.compare('weights.npz', 'weights.npz')['total']['relative_change'], 0.0)

    def test_non_finite_values_make_their_quantities_null(self):
        self.write('weights.npz', npz({'bad': ((2, 2), lambda index: math.nan if index == (1, 1) else 1.0),
                                       'good': ((2,), lambda index: 3.0)}))
        self.write('initial-weights.npz', npz({'bad': ((2, 2), lambda index: math.inf if index == (0, 0) else 1.0),
                                               'good': ((2,), lambda index: 4.0)}))
        got = self.compare('weights.npz', 'initial-weights.npz')
        bad, good = got['tensors']
        self.assertEqual((bad['norm'], bad['other_norm'], bad['difference_norm'], bad['relative_change'],
                          bad['cosine'], bad['largest_change'], bad['nonfinite']),
                         (None, None, None, None, None, None, 2))
        self.assertEqual((good['norm'], good['other_norm'], good['largest_change'], good['nonfinite']),
                         (math.sqrt(18), math.sqrt(32), 1.0, 0))
        self.assertEqual((got['total']['norm'], got['total']['nonfinite'], got['total']['parameters']), (None, 2, 6))
        self.write('one-side.npz', npz({'bad': ((2, 2), lambda index: 1.0), 'good': ((2,), lambda index: 3.0)}))
        one = self.compare('one-side.npz', 'initial-weights.npz')['tensors'][0]
        self.assertEqual((one['norm'], one['other_norm'], one['nonfinite']), (2.0, None, 1))

    def test_fortran_against_c_order_and_the_bound(self):
        def value(index):
            return index[0] * 10.0 + index[1] + index[2] * 0.5
        self.write('weights.npz', zip_bytes({'k.npy': npy((2, 3, 4), '<f4', value)}))
        self.write('fortran.npz', zip_bytes({'k.npy': npy((2, 3, 4), '<f4', value, fortran=True)}))
        got = self.compare('weights.npz', 'fortran.npz')
        self.assertEqual((got['total']['difference_norm'], got['total']['cosine']), (0.0, 1.0))
        with mock.patch.object(inside_weights, 'COMPARE_VALUES', 47):
            error = self.refused('too-large', inside_weights.weights_compare, self.product, path='weights.npz',
                                 other=self.product, other_path='fortran.npz')
        self.assertIn('48 values', str(error))
        with mock.patch.object(inside_weights, 'COMPARE_VALUES', 48):
            self.compare('weights.npz', 'fortran.npz')
        with mock.patch.object(inside_weights, '_PIECE', 5):   # pieces add up to the whole
            pieced = self.compare('weights.npz', 'fortran.npz')
        self.assertEqual(pieced['total']['norm'], got['total']['norm'])

    def test_an_unread_type_and_a_damaged_file(self):
        self.write('a.safetensors', safetensors([('w', 'BF16', (2,), b'\x00' * 4)]))
        got = self.compare('a.safetensors', 'a.safetensors')
        self.assertEqual((got['tensors'], got['unread']),
                         ([], [{'array': 'w', 'dtype': 'BF16', 'other_dtype': 'BF16'}]))
        self.write('broken.npz', b'PK\x05\x06' + b'\xff' * 18)
        self.refused('unsupported', inside_weights.weights_compare, self.product, path='broken.npz',
                     other=self.product, other_path='a.safetensors')
        self.refused('not-found', inside_weights.weights_compare, self.product, path='missing.npz',
                     other=self.product, other_path='a.safetensors')


# ------------------------------------------------------------------ tiles

class Tiles(ReaderCase):

    def setUp(self):
        super().setUp()
        self.shape = (2, 3, 4, 5, 6)
        self.value = lambda index: float(sum(position * 10 ** axis for axis, position in enumerate(index)))
        self.write('kernel.npz', zip_bytes({'conv.weight.npy': npy(self.shape, '<f4', self.value)}))

    def tiles(self, **options):
        return inside_weights.array_tiles(self.product, path='kernel.npz', array='conv.weight', **options)

    def tile_values(self, got):
        values = floats(got['values_f32'])
        size = got['rows'] * got['columns']
        return [values[at:at + size] for at in range(0, len(values), size)]

    def test_each_tile_equals_its_slice(self):
        index = [1, 0, 2, 0, 0]
        got = self.tiles(across=1, axes=[3, 4], index=index)
        self.assertEqual((got['tiles'], got['rows'], got['columns'], got['stride'], got['across'], got['first']),
                         (3, 5, 6, 1, 1, 0))
        for tile, values in enumerate(self.tile_values(got)):
            position = list(index)
            position[1] = tile
            want = inside.array_slice(self.product, path='kernel.npz', array='conv.weight', axes=[3, 4],
                                      index=position)
            self.assertEqual(values, floats(want['values_f32']))
        across_axes = self.tiles(across=3, axes=[0, 2], index=[0, 1, 0, 0, 5])
        for tile, values in enumerate(self.tile_values(across_axes)):
            want = inside.array_slice(self.product, path='kernel.npz', array='conv.weight', axes=[0, 2],
                                      index=[0, 1, 0, tile, 5])
            self.assertEqual(values, floats(want['values_f32']))
        default = self.tiles()
        self.assertEqual((default['across'], default['axes'], default['index'], default['tiles']),
                         (0, [3, 4], [0, 1, 2, 2, 3], 2))
        self.assertEqual((default['min'], default['max'], default['nonfinite']),
                         (min(min(tile) for tile in self.tile_values(default)),
                          max(max(tile) for tile in self.tile_values(default)), 0))

    def test_paging_and_subsampling(self):
        page = self.tiles(across=2, first=1, most=2)
        self.assertEqual((page['tiles'], page['first'], page['index'][2]), (2, 1, 1))
        whole = self.tile_values(self.tiles(across=2))
        self.assertEqual(self.tile_values(page), whole[1:3])
        self.assertEqual(self.tiles(across=2, first=3, most=10)['tiles'], 1)
        self.write('wide.npy', npy((3, 100, 130), '<f4', lambda index: index[1] * 1000.0 + index[2]))
        wide = inside_weights.array_tiles(self.product, path='wide.npy', most=64)
        self.assertEqual((wide['tiles'], wide['stride'], wide['rows'], wide['columns']), (3, 3, 34, 44))
        for tile, values in enumerate(self.tile_values(wide)):
            want = inside.array_slice(self.product, path='wide.npy', index=[tile, 0, 0], most=64)
            self.assertEqual(values, floats(want['values_f32']))
        with mock.patch.object(inside_weights, 'TILES_MOST', 2):
            self.assertEqual(inside_weights.array_tiles(self.product, path='wide.npy', most=64)['tiles'], 2)

    def test_refusals(self):
        self.write('flat.npy', npy((3, 4), '<f4', lambda index: 1.0))
        self.refused('invalid', inside_weights.array_tiles, self.product, path='flat.npy')
        self.refused('invalid', self.tiles, across=3, axes=[3, 4])
        self.refused('invalid', self.tiles, axes=[4, 4])
        self.refused('invalid', self.tiles, across=0, first=2)
        self.refused('invalid', self.tiles, index=[0, 0])
        self.refused('invalid', self.tiles, across=0, index=[0, 9, 0, 0, 0])
        self.refused('not-found', inside_weights.array_tiles, self.product, path='kernel.npz', array='nothing')


# ------------------------------------------------------------ through the service

class WeightsProducts(builds_base.BuildCase):
    """BuildCase with recipes/fit-a declaring weights.npz, adopted twice (two finished runs)."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        inside_archive.forget_members()
        inside.forget_indexes()

        def declare(document):
            document['run']['outputs'] = {'model': {'path': 'weights.npz', 'role': 'weights'}}
        self.edit('recipes/fit-a', declare)
        self.runs_made = []
        for scale in (1.0, 2.0):
            source = self.temporary / f'weights-{scale}.npz'
            source.write_bytes(npz({'layer.weight': ((2, 3), lambda index, scale=scale: scale * (index[1] + 1)),
                                    'layer.bias': ((3,), lambda index: 0.5)}))
            manifest = {'format': 'tuldok_adoption_v1',
                        'products': [{'reference': 'recipes/fit-a', 'files': {'weights.npz': str(source)}}]}
            with self.opened() as project:
                done = adoption.adopt(project, adoption.make_plan(project, manifest, copy=True, replace=True))
            self.runs_made.append((done['entries'][0]['run_id'], Path(done['entries'][0]['directory'])))
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, **arguments):
        result = self.service.call(name, arguments, OWNER)
        json.dumps(result, allow_nan=False)
        return result


@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Operations(WeightsProducts):

    def test_the_three_operations(self):
        (first, _), (second, output) = self.runs_made
        shutil.copyfile(self.temporary / 'weights-1.0.npz', output / 'initial-weights.npz')
        (output / 'model.pt').write_bytes(b'pickle')
        [found] = self.call('weights', run=second)['files']   # the declared output only: model.pt is not one
        self.assertEqual((found['path'], found['output'], found['readable'], found['starts_from'],
                          found['parameters']), ('weights.npz', 'model', True, 'initial-weights.npz', 9))
        self.assertEqual([layer['name'] for layer in found['layers']], ['layer'])
        started = self.call('weights_compare', run=second, path='weights.npz', other_run=second,
                            other_path='initial-weights.npz')
        other = self.call('weights_compare', run=second[:8], path='weights.npz', other_run=first,
                          other_path='weights.npz')
        self.assertEqual(started, other)
        weight = other['tensors'][0]
        self.assertEqual((weight['array'], weight['relative_change'], weight['cosine']), ('layer.weight', 1.0, 1.0))
        self.assertEqual(other['tensors'][1]['difference_norm'], 0.0)
        (output / 'kernel.npy').write_bytes(npy((3, 2, 2), '<f4', lambda index: float(index[0])))
        tiles = self.call('array_tiles', run=second, path='kernel.npy', first=1)
        self.assertEqual((tiles['tiles'], floats(tiles['values_f32'])), (2, [1.0] * 4 + [2.0] * 4))
        refused = []
        for name, arguments in (('array_tiles', {'path': 'weights.npz', 'array': 'layer.weight'}),
                                ('weights_compare', {'path': 'model.pt', 'other_run': first, 'other_path': 'x.npz'}),
                                ('weights_compare', {'path': 'weights.npz', 'other_run': 'f' * 32,
                                                     'other_path': 'weights.npz'}),
                                ('weights', {'colour': 'red'}), ('array_tiles', {'path': 'weights.npz', 'most': 65})):
            with self.assertRaises(store.ProjectError) as caught:
                self.service.call(name, {'run': second, **arguments}, OWNER)
            refused.append(caught.exception.code)
        self.assertEqual(refused, ['invalid', 'unsupported', 'not-found', 'invalid', 'invalid'])

    def test_a_run_without_declared_weights_is_read_by_name_and_nothing_is_written(self):
        (first, output), _ = self.runs_made
        with self.opened() as project:
            project._execute("UPDATE {schema}.products SET outputs = '{{}}'::jsonb WHERE run_id = %s", (first,))
        (output / 'model.pt').write_bytes(b'pickle')
        before = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        files = self.call('weights', run=first)['files']
        self.assertEqual([(item['path'], item['output'], item['readable']) for item in files],
                         [('model.pt', None, False), ('weights.npz', None, True)])
        self.call('weights_compare', run=first, path='weights.npz', other_run=first, other_path='weights.npz')
        after = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        self.assertEqual(before, after)
        with self.opened() as project:
            self.assertEqual(project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0], 0)


class Published(unittest.TestCase):

    def test_the_three_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in WEIGHTS:
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        from tuldok_project import service
        self.assertTrue(set(WEIGHTS) <= set(service.INSIDE_READS))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in WEIGHTS} <= folder)
        self.assertFalse({'project.' + name for name in WEIGHTS} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
