"""Looking inside a product (docs/plans/definition-first-projects/spec-d1.md, slice D1a).

The readers are tested on files the tests write with the standard library
(arrays with struct, sounds with wave, a PNG with zlib, archives with zipfile)
and need no database. The operations and the file route need one and run only
when TULDOK_DATABASE_URL names a disposable cluster: each such test starts
from test_tuldok_project_builds.BuildCase, adopts a product for
datasets/numbers (adoption.py, as test_tuldok_project_adoption.py does) and
writes its fixture files into that product's output directory. No GPU is
used.
"""
import base64
import io
import itertools
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import (adoption, inside, inside_archive, inside_arrays, inside_shapes, local,  # noqa: E402
                            operations, store)
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402

OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner',
         'scopes': ['inspect', 'edit', 'execute', 'cancel', 'approve-execution']}
INSIDE = ('records', 'record', 'inside', 'array_slice', 'array_summary')
FORMATS = {'f2': 'e', 'f4': 'f', 'f8': 'd', 'i1': 'b', 'i2': 'h', 'i4': 'i', 'i8': 'q', 'u1': 'B', 'u2': 'H',
           'u4': 'I', 'u8': 'Q', 'b1': '?'}


# ------------------------------------------------------------------ fixtures

def npy(shape, descr, value, *, fortran=False, version=1):
    """The bytes of an NPY array whose element at an index tuple is value(index)."""
    header = repr({'descr': descr, 'fortran_order': fortran, 'shape': tuple(shape)}).encode('latin-1')
    prefix = 10 if version == 1 else 12
    header += b' ' * ((-(prefix + len(header) + 1)) % 64) + b'\n'
    start = b'\x93NUMPY' + bytes([version, 0]) + (struct.pack('<H', len(header)) if version == 1
                                                   else struct.pack('<I', len(header)))
    order = descr[0] if descr[0] in '<>' else '<'
    code = FORMATS[descr.lstrip('<>|=')]
    ranges = [range(size) for size in shape]
    if fortran:
        indexes = (tuple(reversed(index)) for index in itertools.product(*reversed(ranges)))
    else:
        indexes = itertools.product(*ranges)
    data = b''.join(struct.pack(order + code, value(index)) for index in indexes)
    return start + header + data


def raw_header(descr, shape=(2,)):
    header = repr({'descr': descr, 'fortran_order': False, 'shape': shape}).encode('latin-1')
    header += b' ' * ((-(10 + len(header) + 1)) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(header)) + header + b'\x00' * 32


def zip_bytes(members, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def png(width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\x00' + b'\x80\x40\x20' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def wav16(samples, *, channels=1, rate=8000):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as sound:
        sound.setnchannels(channels)
        sound.setsampwidth(2)
        sound.setframerate(rate)
        sound.writeframes(struct.pack(f'<{len(samples)}h', *samples))
    return buffer.getvalue()


def wav_float(samples, *, rate=4000):
    data = struct.pack(f'<{len(samples)}f', *samples)
    fmt = struct.pack('<HHIIHH', 3, 1, rate, rate * 4, 4, 32)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    return b'RIFF' + struct.pack('<I', len(body)) + body


CUBE = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
QUADS = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 3, 7, 4)]


def ply_mesh_binary():
    header = ('ply\nformat binary_little_endian 1.0\nelement vertex 8\nproperty float x\nproperty float y\n'
              'property float z\nelement face 6\nproperty list uchar int vertex_indices\nend_header\n').encode()
    body = b''.join(struct.pack('<fff', *vertex) for vertex in CUBE)
    body += b''.join(struct.pack('<B4i', 4, *quad) for quad in QUADS)
    return header + body


def ply_points_ascii(points):
    lines = ['ply', 'format ascii 1.0', f'element vertex {len(points)}', 'property float x', 'property float y',
             'property float z', 'property uchar red', 'property uchar green', 'property uchar blue', 'end_header']
    lines += [f'{x} {y} {z} {r} {g} {b}' for x, y, z, r, g, b in points]
    return ('\n'.join(lines) + '\n').encode()


def obj_cube():
    lines = [f'v {x} {y} {z}' for x, y, z in CUBE]
    lines += ['f ' + ' '.join(f'{index + 1}/1/1' for index in quad) for quad in QUADS[:5]]
    lines.append('f ' + ' '.join(str(index - 8) for index in QUADS[5]))  # negative indexes
    return ('\n'.join(lines) + '\n').encode()


def stl_binary(triangles):
    data = b'\x00' * 80 + struct.pack('<I', len(triangles))
    for triangle in triangles:
        data += struct.pack('<3f', 0, 0, 1) + b''.join(struct.pack('<3f', *point) for point in triangle) + b'\x00\x00'
    return data


def floats(text):
    raw = base64.b64decode(text)
    return list(struct.unpack(f'<{len(raw) // 4}f', raw))


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def value4(index):
    i, j, k, m = index
    return float(i * 1000 + j * 100 + k * 10 + m)


# ------------------------------------------------------------ the readers alone

class Readers(unittest.TestCase):
    """The readers on a directory, without a project or a database."""

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
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        return path

    def slice(self, path, **options):
        return inside.array_slice(self.product, path=path, **options)

    def refused(self, code, call, *arguments, **options):
        with self.assertRaises(store.ProjectError) as caught:
            call(*arguments, **options)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    # ---- arrays

    def test_every_supported_type_in_both_byte_orders(self):
        for code, fmt in FORMATS.items():
            for order in ('<', '>'):
                with self.subTest(code=code, order=order):
                    descr = ('|' if code in ('i1', 'u1', 'b1') else order) + code
                    if code == 'b1':
                        expected = lambda index: (index[0] + index[1]) % 2 == 0  # noqa: E731
                    elif code[0] == 'f':
                        expected = lambda index: index[0] * 3.5 - index[1]  # noqa: E731
                    elif code[0] == 'i':
                        expected = lambda index: index[0] * 7 - index[1] * 9  # noqa: E731
                    else:
                        expected = lambda index: index[0] * 7 + index[1]  # noqa: E731
                    name = f'types/{code}{"big" if order == ">" else "little"}.npy'
                    self.write(name, npy((3, 4), descr, expected))
                    got = self.slice(name)
                    want = [float(expected((r, c))) for r in range(3) for c in range(4)]
                    self.assertEqual(floats(got['values_f32']), [f32(value) for value in want])
                    self.assertEqual((got['rows'], got['columns'], got['stride']), (3, 4, 1))
                    self.assertEqual((got['min'], got['max']), (min(want), max(want)))

    def test_a_slice_on_each_pair_of_axes_in_both_storage_orders(self):
        shape = (2, 3, 4, 5)
        for fortran in (False, True):
            self.write(f'four-{fortran}.npy', npy(shape, '<f4', value4, fortran=fortran))
            for axes in itertools.permutations(range(4), 2):
                with self.subTest(fortran=fortran, axes=axes):
                    index = [1, 2, 3, 4]
                    got = self.slice(f'four-{fortran}.npy', axes=list(axes), index=index)
                    want = []
                    for r in range(shape[axes[0]]):
                        for c in range(shape[axes[1]]):
                            position = list(index)
                            position[axes[0]], position[axes[1]] = r, c
                            want.append(value4(position))
                    self.assertEqual(floats(got['values_f32']), want)
                    self.assertEqual((got['rows'], got['columns']), (shape[axes[0]], shape[axes[1]]))
        middle = self.slice('four-False.npy')   # the last two axes at the middle of the others
        self.assertEqual((middle['axes'], middle['index'][:2]), ([2, 3], [1, 1]))
        self.assertEqual(floats(middle['values_f32'])[0], value4((1, 1, 0, 0)))

    def test_subsampling_and_non_finite_values(self):
        self.write('tall.npy', npy((1000, 30), '<f8', lambda index: index[0] * 100 + index[1]))
        got = self.slice('tall.npy', most=256)
        self.assertEqual((got['stride'], got['rows'], got['columns']), (4, 250, 8))
        values = floats(got['values_f32'])
        self.assertEqual(values[:3], [0, 4, 8])
        self.assertEqual(values[8], 400)
        special = [1.0, math.nan, math.inf, -2.0, -math.inf, 3.0]
        self.write('odd.npy', npy((2, 3), '<f4', lambda index: special[index[0] * 3 + index[1]]))
        got = self.slice('odd.npy')
        self.assertEqual((got['min'], got['max'], got['nonfinite']), (-2.0, 3.0, 3))
        summary = inside.array_summary(self.product, path='odd.npy', bins=4)
        self.assertEqual((summary['count'], summary['nonfinite'], summary['min'], summary['max']), (6, 3, -2.0, 3.0))
        self.assertEqual(sum(summary['histogram']['counts']), 3)

    def test_a_summary_of_values_too_large_to_sum_is_plain_json(self):
        huge = 1.7e308
        self.write('same.npy', npy((2,), '<f8', lambda index: huge))
        self.write('apart.npy', npy((2,), '<f8', lambda index: huge if index[0] else -huge))
        same = inside.array_summary(self.product, path='same.npy', bins=4)
        apart = inside.array_summary(self.product, path='apart.npy', bins=4)
        for answer in (same, apart):
            json.dumps(answer, allow_nan=False)         # no infinity, no NaN
            self.assertEqual(answer['nonfinite'], 0)
        self.assertEqual((same['min'], same['max'], same['mean'], same['std']), (huge, huge, None, None))
        self.assertEqual(same['histogram']['counts'], [2, 0, 0, 0])
        self.assertEqual((apart['mean'], apart['std']), (0.0, None))
        self.assertEqual(apart['histogram']['counts'], [1, 0, 0, 1])
        json.dumps(self.slice('apart.npy'), allow_nan=False)

    def test_a_summary_compared_with_its_own_arithmetic(self):
        values = [((i * 37) % 101) - 50 for i in range(1000)]
        self.write('flat.npy', npy((1000,), '<i2', lambda index: values[index[0]]))
        got = inside.array_summary(self.product, path='flat.npy', bins=10)
        mean = sum(values) / len(values)
        std = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
        self.assertEqual((got['count'], got['min'], got['max'], got['zeros'], got['stride']),
                         (1000, min(values), max(values), values.count(0), 1))
        self.assertAlmostEqual(got['mean'], mean)
        self.assertAlmostEqual(got['std'], std)
        self.assertEqual(sum(got['histogram']['counts']), 1000)
        self.assertEqual(got['histogram']['counts'][-1], sum(1 for value in values if value >= 50 - 10))
        with mock.patch.object(inside_arrays, 'SUMMARY_VALUES', 100):
            sampled = inside.array_summary(self.product, path='flat.npy')
        self.assertEqual((sampled['stride'], sum(sampled['histogram']['counts'])), (10, 100))
        self.assertAlmostEqual(sampled['mean'], sum(values[::10]) / 100)

    def test_stored_compressed_and_nested_members_and_version_two(self):
        array = npy((3, 4), '<f4', lambda index: index[0] * 10 + index[1])
        version_two = npy((3, 4), '<f4', lambda index: index[0] * 10 + index[1], version=2)
        npz_stored = zip_bytes({'field.npy': array, 'line.npy': npy((5,), '<i4', lambda index: index[0])})
        npz_deflated = zip_bytes({'field.npy': version_two}, zipfile.ZIP_DEFLATED)
        self.write('a.npz', npz_stored)
        self.write('outer.zip', zip_bytes({'samples/s.npz': npz_stored, 'samples/d.npz': npz_deflated,
                                           'inner.zip': zip_bytes({'deep.npy': array}, zipfile.ZIP_DEFLATED)}))
        self.write('packed.zip', zip_bytes({'samples/s.npz': npz_stored}, zipfile.ZIP_DEFLATED))
        want = [float(r * 10 + c) for r in range(3) for c in range(4)]
        for path, name in (('a.npz', 'field'), ('outer.zip!samples/s.npz', 'field'),
                           ('outer.zip!samples/d.npz', 'field'), ('packed.zip!samples/s.npz', 'field'),
                           ('outer.zip!inner.zip!deep.npy', None)):
            with self.subTest(path):
                self.assertEqual(floats(self.slice(path, array=name)['values_f32']), want)
        stored = inside_archive.locate(self.root, 'outer.zip!samples/s.npz').blob()
        self.assertIsNotNone(stored.path)   # a stored member of a file on disk is read where it lies
        self.assertIsInstance(stored.view.obj, type(inside_archive.file_blob(os.path.join(self.root, 'a.npz')).view.obj))
        listed = inside.inside(self.product, path='outer.zip!samples/s.npz')
        self.assertEqual([(entry['name'], entry['type'], entry['shape'], entry['dtype']) for entry in listed['entries']],
                         [('field', 'array', [3, 4], 'float32'), ('line', 'array', [5], 'int32')])
        tree = inside.inside(self.product, path='outer.zip')
        self.assertEqual([(entry['name'], entry['type']) for entry in tree['entries']],
                         [('samples', 'directory'), ('inner.zip', 'archive')])
        self.assertEqual([entry['path'] for entry in inside.inside(self.product, path='outer.zip!samples')['entries']],
                         ['outer.zip!samples/d.npz', 'outer.zip!samples/s.npz'])
        root = inside.inside(self.product)
        self.assertEqual({entry['name']: entry['type'] for entry in root['entries']},
                         {'a.npz': 'archive', 'outer.zip': 'archive', 'packed.zip': 'archive'})

    def test_refusals_of_arrays_and_addresses(self):
        self.write('object.npy', raw_header('|O'))
        self.write('complex.npy', raw_header('<c8'))
        self.write('inside/ok.npy', npy((2,), '<f4', lambda index: 1.0))
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: (os.remove(outside / 'secret.npy'), os.rmdir(outside)))
        (outside / 'secret.npy').write_bytes(npy((2,), '<f4', lambda index: 1.0))
        os.symlink(outside / 'secret.npy', Path(self.root, 'link.npy'))
        error = self.refused('unsupported', self.slice, 'object.npy')
        self.assertIn('object', str(error))
        self.refused('unsupported', inside.array_summary, self.product, path='complex.npy')
        self.refused('invalid', self.slice, 'inside/../object.npy')
        self.refused('invalid', self.slice, '/etc/passwd')
        self.refused('not-found', self.slice, 'link.npy')
        self.refused('not-found', self.slice, 'missing.npy')
        self.write('inside/cube.npy', npy((2, 2, 2), '<f4', lambda index: 1.0))
        self.refused('invalid', self.slice, 'inside/cube.npy', index=[5, 0, 0])
        self.refused('invalid', self.slice, 'inside/cube.npy', index=[0, 0])
        self.refused('invalid', self.slice, 'inside/cube.npy', axes=[1, 1])
        self.refused('invalid', self.slice, 'inside/ok.npy', axes=[0, 1])
        listed = inside.inside(self.product)
        self.assertNotIn('link.npy', [entry['name'] for entry in listed['entries']])
        big = npy((64, 64), '<f4', lambda index: 0.0)
        self.write('big.zip', zip_bytes({'big.npy': big}, zipfile.ZIP_DEFLATED))
        with mock.patch.object(inside_archive, 'MEMBER_BYTES', 1024):
            error = self.refused('too-large', self.slice, 'big.zip!big.npy')
        self.assertIn(str(len(big)), str(error))

    def test_damaged_files_are_refused_and_never_fail(self):
        good = zip_bytes({'x.npy': npy((4, 4, 4), '<f4', lambda index: float(sum(index)))}, zipfile.ZIP_DEFLATED)
        start = good.index(b'x.npy') + len(b'x.npy')
        damaged = bytearray(good)
        damaged[start + 2:start + 12] = b'\xff' * 10          # inside the compressed data
        self.write('damaged.npz', bytes(damaged))
        self.refused('unsupported', self.slice, 'damaged.npz', array='x')
        self.refused('unsupported', inside.array_summary, self.product, path='damaged.npz', array='x')
        self.refused('unsupported', inside.file_response, self.product, 'damaged.npz!x.npy')
        self.write('short.ply', ply_mesh_binary()[:-9])           # ends inside its last face
        with self.assertLogs('tuldok_project.inside', 'WARNING'):   # a reader's own error, refused and logged
            self.refused('unsupported', inside.record, self.product, 'short.ply')
        self.write('short.npy', npy((8, 8), '<f8', lambda index: 1.0)[:-40])
        self.refused('unsupported', self.slice, 'short.npy')
        self.write('not.zip', b'PK\x05\x06' + b'\xff' * 18)
        self.refused('unsupported', inside.inside, self.product, path='not.zip')
        # The product is still listed: a damaged file is one record among the others.
        self.assertEqual(inside.records(self.product)['total'], 4)

    def test_a_compressed_member_is_decompressed_once(self):
        self.write('c.zip', zip_bytes({'x.npy': npy((10, 10), '<f4', lambda index: 1.0)}, zipfile.ZIP_DEFLATED))
        real = inside_archive._inflate
        with mock.patch.object(inside_archive, '_inflate', side_effect=real) as inflate:
            self.slice('c.zip!x.npy')
            self.slice('c.zip!x.npy')
            inside.array_summary(self.product, path='c.zip!x.npy')
        self.assertEqual(len([call for call in inflate.call_args_list if call.args[2] > 1000]), 1)
        with mock.patch.object(inside_archive, 'CACHE_BYTES', 10):
            inside_archive.forget_members()
            with mock.patch.object(inside_archive, '_inflate', side_effect=real) as inflate:
                self.slice('c.zip!x.npy')
                self.slice('c.zip!x.npy')
            self.assertEqual(len([call for call in inflate.call_args_list if call.args[2] > 1000]), 2)

    # ---- records

    def test_records_from_files_with_kinds(self):
        self.write('notes/a.txt', 'hello')
        self.write('b.png', png(3, 2))
        self.write('c.bin', b'\x00')
        self.write('d.ply', ply_mesh_binary())
        self.write('e.ply', ply_points_ascii([(0, 0, 0, 1, 2, 3)]))
        got = inside.records(self.product)
        self.assertEqual(got['source'], 'files')
        self.assertEqual([(record['id'], record['kind']) for record in got['records']],
                         [('b.png', 'image'), ('c.bin', 'file'), ('d.ply', 'mesh'), ('e.ply', 'pointcloud'),
                          ('notes/a.txt', 'text')])
        self.assertEqual(got['records'][-1]['preview'], 'hello')
        self.assertEqual(got['kinds'], {'image': 1, 'file': 1, 'mesh': 1, 'pointcloud': 1, 'text': 1})
        inside.forget_indexes()
        with mock.patch.object(inside, 'WALK_FILES', 2):
            limited = inside.records(self.product)
        self.assertEqual(limited['total'], 2)
        self.assertIn('2 files', limited['problems'][0]['message'])

    def test_records_from_a_list_with_paging_filters_and_a_bad_line(self):
        lines = [json.dumps({'id': f'r{i:03}', 'kind': 'text', 'text': f'text {i}', 'split': 'train' if i % 3 else 'test',
                             'rights': 'cc0', 'origin': {'n': i}, 'note': 'kept'}) for i in range(30)]
        lines.insert(5, '{"id": "bad id!", "kind": "text", "text": "x"}')
        lines.insert(9, 'not json')
        lines.insert(12, json.dumps({'id': 'r000', 'kind': 'text', 'text': 'again'}))
        lines.append('x' * (inside.LINE_BYTES + 10))
        lines.append(json.dumps({'id': 'img', 'kind': 'image', 'path': 'pictures/p.png', 'split': 'test'}))
        self.write('records.jsonl', '\n'.join(lines) + '\n')
        self.write('pictures/p.png', png(5, 7))
        got = inside.records(self.product, offset=10, limit=5)
        self.assertEqual((got['source'], got['total']), ('records.jsonl', 31))
        self.assertEqual([record['id'] for record in got['records']], [f'r{i:03}' for i in range(10, 15)])
        self.assertEqual(got['kinds'], {'text': 30, 'image': 1})
        self.assertEqual(got['splits'], {'train': 20, 'test': 11})
        self.assertEqual([problem['line'] for problem in got['problems']], [6, 10, 13, 34])
        first = got['records'][0]
        self.assertEqual((first['preview'], first['rights'], first['origin'], first['meta']),
                         ('text 10', 'cc0', {'n': 10}, {'note': 'kept'}))
        tests = inside.records(self.product, split='test', kind='text')
        self.assertEqual(tests['total'], 10)
        images = inside.records(self.product, kind='image')
        self.assertEqual([(record['id'], record['bytes']) for record in images['records']],
                         [('img', len(png(5, 7)))])
        shown = inside.record(self.product, 'img')
        self.assertEqual(shown['content'], {'width': 5, 'height': 7})
        self.assertEqual((shown['record']['media_type'], shown['record']['url']),
                         ('image/png', '/api/project/file?run=run-1&path=pictures%2Fp.png'))
        self.assertEqual(inside.record(self.product, 'r004')['content'],
                         {'text': 'text 4', 'characters': 6, 'truncated': False, 'replaced': 0})
        self.refused('not-found', inside.record, self.product, 'nothing')

    def test_records_from_each_form_of_view(self):
        self.write('lists/all.jsonl', json.dumps({'id': 'one', 'kind': 'text', 'path': 'a.txt'}) + '\n')
        self.write('a.txt', 'alpha')
        sample = zip_bytes({'target_pressure.npy': npy((2, 2), '<f4', lambda index: 1.0),
                            'features.npy': npy((2, 2, 2), '<f4', lambda index: 2.0)})
        self.write('training-view.zip', zip_bytes({'samples/x.npz': sample, 'samples/y.npz': sample,
                                                   'samples/readme.txt': b'r', 'other/z.npz': sample}))
        listed = inside.records(inside.Product('run-1', self.root, {'records': 'lists/all.jsonl'}))
        self.assertEqual((listed['source'], [record['id'] for record in listed['records']]), ('view', ['one']))
        view = {'files': 'training-view.zip!samples/*.npz', 'kind': 'array', 'show': 'target_pressure'}
        product = inside.Product('run-1', self.root, view)
        matched = inside.records(product)
        self.assertEqual([record['id'] for record in matched['records']],
                         ['training-view.zip!samples/x.npz', 'training-view.zip!samples/y.npz'])
        content = inside.record(product, 'training-view.zip!samples/x.npz')['content']
        self.assertEqual(content['show'], 'target_pressure')
        self.assertEqual([(item['array'], item['shape']) for item in content['arrays']],
                         [('features', [2, 2, 2]), ('target_pressure', [2, 2])])
        everything = inside.records(inside.Product('run-1', self.root, {'files': '**/*.txt'}))
        self.assertEqual([record['id'] for record in everything['records']], ['a.txt'])
        self.write('records.jsonl', json.dumps({'id': 'first', 'kind': 'file', 'path': 'a.txt'}) + '\n')
        self.assertEqual(inside.records(product)['source'], 'records.jsonl')   # the list comes first

    # ---- content of each kind

    def test_text_content(self):
        self.write('t.txt', b'caf\xc3\xa9 \xff ok')
        record = inside.record(inside.Product('run-1', self.root), 't.txt')
        self.assertEqual(record['content'], {'text': 'café � ok', 'characters': 9, 'truncated': False,
                                             'replaced': 1})
        self.write('long.txt', 'abc' * 100)
        with mock.patch.object(inside, 'TEXT_CHARACTERS', 10):
            content = inside.record(self.product, 'long.txt')['content']
        self.assertEqual((content['text'], content['characters'], content['truncated']), ('abcabcabca', 300, True))

    def test_image_sizes(self):
        jpeg = (b'\xff\xd8\xff\xe0' + struct.pack('>H', 16) + b'JFIF\x00' + b'\x00' * 9
                + b'\xff\xc0' + struct.pack('>HBHHB', 11, 8, 33, 44, 1) + b'\x00' * 3 + b'\xff\xd9')
        gif = b'GIF89a' + struct.pack('<HH', 12, 13) + b'\x00' * 10
        bmp = b'BM' + b'\x00' * 12 + struct.pack('<Iii', 40, 21, -22) + b'\x00' * 30
        webp = b'RIFF' + struct.pack('<I', 30) + b'WEBPVP8X' + struct.pack('<I', 10) + b'\x00' * 4 \
            + (99).to_bytes(3, 'little') + (49).to_bytes(3, 'little')
        for name, data, size in (('a.png', png(17, 9), (17, 9)), ('b.jpg', jpeg, (44, 33)), ('c.gif', gif, (12, 13)),
                                 ('d.bmp', bmp, (21, 22)), ('e.webp', webp, (100, 50)),
                                 ('f.png', b'not an image', (None, None))):
            with self.subTest(name):
                self.write(name, data)
                inside.forget_indexes()
                content = inside.record(self.product, name)['content']
                self.assertEqual((content['width'], content['height']), size)

    def test_sound(self):
        samples = [0, 16384, -32768, 32767, 100, -100] * 500
        self.write('s.wav', wav16(samples, channels=2, rate=8000))
        self.write('f.wav', wav_float([0.5, -0.25, 1.0, -1.0]))
        self.write('m.mp3', b'ID3')
        content = inside.record(self.product, 's.wav')['content']
        self.assertEqual((content['channels'], content['rate'], content['frames']), (2, 8000, 1500))
        self.assertAlmostEqual(content['seconds'], 1500 / 8000)
        self.assertEqual(len(content['peaks']), 1000)
        self.assertEqual(min(low for low, _ in content['peaks']), -1.0)
        self.assertAlmostEqual(max(high for _, high in content['peaks']), 32767 / 32768, places=4)
        floating = inside.record(self.product, 'f.wav')['content']
        self.assertEqual((floating['frames'], floating['peaks']), (4, [[0.5, 0.5], [-0.25, -0.25], [1.0, 1.0],
                                                                       [-1.0, -1.0]]))
        self.assertEqual(inside.record(self.product, 'm.mp3')['content']['rate'], None)
        record = inside.record(self.product, 's.wav')['record']
        self.assertEqual(record['media_type'], 'audio/wav')

    def test_point_clouds(self):
        points = [(i, i * 2, -i, i % 256, 0, 255) for i in range(10)]
        self.write('p.ply', ply_points_ascii(points))
        self.write('p.xyz', '\n'.join(f'{x} {y} {z}' for x, y, z, *_ in points) + '\n# comment\n')
        self.write('records.jsonl', '\n'.join(json.dumps(item) for item in (
            {'id': 'ply', 'kind': 'pointcloud', 'path': 'p.ply'}, {'id': 'xyz', 'kind': 'pointcloud', 'path': 'p.xyz'},
            {'id': 'npy', 'kind': 'pointcloud', 'path': 'p.npy'})) + '\n')
        self.write('p.npy', npy((10, 4), '<f8', lambda index: points[index[0]][index[1]] if index[1] < 3 else 9.0))
        for name in ('ply', 'xyz', 'npy'):
            with self.subTest(name):
                content = inside.record(self.product, name)['content']
                self.assertEqual((content['count'], content['stride']), (10, 1))
                self.assertEqual(floats(content['points_f32']), [float(v) for x, y, z, *_ in points for v in (x, y, z)])
                self.assertEqual(content['bounds'], [[0, 0, -9], [9, 18, 0]])
        colors = base64.b64decode(inside.record(self.product, 'ply')['content']['colors_u8'])
        self.assertEqual(list(colors[:6]), [0, 0, 255, 1, 0, 255])
        with mock.patch.object(inside_shapes, 'POINTS', 4):
            sampled = inside.record(self.product, 'xyz')['content']
        self.assertEqual((sampled['stride'], len(floats(sampled['points_f32']))), (3, 12))

    def test_meshes(self):
        self.write('m.ply', ply_mesh_binary())
        self.write('m.obj', obj_cube())
        triangles = [[CUBE[q[0]], CUBE[q[c]], CUBE[q[c + 1]]] for q in QUADS for c in (1, 2)]
        self.write('m.stl', stl_binary(triangles))
        self.write('a.stl', 'solid x\n' + ''.join(
            'facet normal 0 0 1\nouter loop\n' + ''.join(f'vertex {x} {y} {z}\n' for x, y, z in triangle)
            + 'endloop\nendfacet\n' for triangle in triangles) + 'endsolid x\n')
        for name in ('m.ply', 'm.obj', 'm.stl', 'a.stl'):
            with self.subTest(name):
                content = inside.record(self.product, name)['content']
                self.assertEqual((content['vertices'], content['triangles']), (8, 12))
                self.assertEqual(content['bounds'], [[0, 0, 0], [1, 1, 1]])
                positions = floats(content['positions_f32'])
                raw = base64.b64decode(content['triangles_u32'])
                indexes = struct.unpack(f'<{len(raw) // 4}I', raw)
                corners = {tuple(positions[3 * i:3 * i + 3]) for i in indexes}
                self.assertEqual(corners, {tuple(map(float, point)) for point in CUBE})
                if name != 'a.stl' and name != 'm.stl':
                    self.assertEqual(list(indexes[:6]), [0, 1, 2, 0, 2, 3])   # a quad as a fan
        with mock.patch.object(inside_shapes, 'MESH_TRIANGLES', 5):
            error = self.refused('too-large', inside.record, self.product, 'm.obj')
        self.assertIn('12 triangles', str(error))
        with mock.patch.object(inside_shapes, 'SHAPE_BYTES', 10):
            self.refused('too-large', inside.record, self.product, 'm.stl')

    def test_file_bytes(self):
        self.write('pic.png', png(2, 2))
        self.write('x.svg', '<svg/>')
        self.write('x.html', '<script></script>')
        self.write('box.zip', zip_bytes({'in.wav': wav16([1, 2, 3])}, zipfile.ZIP_DEFLATED))
        for address, media, disposition in (('pic.png', 'image/png', 'inline'),
                                            ('x.svg', 'application/octet-stream', 'attachment'),
                                            ('x.html', 'application/octet-stream', 'attachment'),
                                            ('box.zip!in.wav', 'audio/wav', 'inline')):
            with self.subTest(address):
                answer = inside.file_response(self.product, address)
                headers = dict(answer.headers)
                self.assertEqual(headers['Content-Type'], media)
                self.assertTrue(headers['Content-Disposition'].startswith(disposition))
                self.assertEqual(b''.join(bytes(chunk) for chunk in answer.chunks), inside_archive.locate(
                    self.root, address).blob().view.tobytes())
        answer = inside.file_response(self.product, 'pic.png', 'bytes=2-5')
        self.assertEqual((answer.status, dict(answer.headers)['Content-Range'], b''.join(answer.chunks)),
                         (206, f'bytes 2-5/{len(png(2, 2))}', png(2, 2)[2:6]))
        self.assertEqual(inside.file_response(self.product, 'pic.png', 'bytes=1-2,4-5').status, 200)


# ------------------------------------------------------------ through the service

class ProductCase(builds_base.BuildCase):
    """BuildCase with an adopted product for datasets/numbers, whose output directory the tests fill."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        inside_archive.forget_members()
        inside.forget_indexes()
        source = self.temporary / 'numbers.json'
        source.write_text('{"numbers": [1, 2]}', encoding='utf-8')
        manifest = {'format': 'tuldok_adoption_v1',
                    'products': [{'reference': 'datasets/numbers', 'files': {'numbers.json': str(source)}}]}
        with self.opened() as project:
            done = adoption.adopt(project, adoption.make_plan(project, manifest, copy=True))
        self.run_id = done['entries'][0]['run_id']
        self.output = Path(done['entries'][0]['directory'])

    def write(self, address, data):
        path = self.output / address
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())


@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Operations(ProductCase):

    def setUp(self):
        super().setUp()
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, **arguments):
        result = self.service.call(name, arguments, OWNER)
        json.dumps(result, allow_nan=False)
        return result

    def test_the_five_operations_on_an_adopted_product(self):
        self.write('field.npy', npy((4, 6), '<f4', lambda index: index[0] * 6 + index[1]))
        listed = self.call('records', run=self.run_id)
        self.assertEqual(([record['id'] for record in listed['records']], listed['source']),
                         (['field.npy', 'numbers.json'], 'files'))
        self.assertEqual(self.call('record', run=self.run_id, id='numbers.json')['content']['text'],
                         '{"numbers": [1, 2]}')
        self.assertEqual(self.call('inside', run=self.run_id)['total'], 2)
        got = self.call('array_slice', run=self.run_id[:8], path='field.npy', most=3)
        self.assertEqual((got['stride'], got['rows'], got['columns']), (2, 2, 3))
        self.assertEqual(self.call('array_summary', run=self.run_id, path='field.npy')['max'], 23.0)

    def test_a_view_on_the_dataset_is_used(self):
        def with_view(document):
            document['view'] = {'files': '*.npy', 'kind': 'array'}
        self.edit('datasets/numbers', with_view)
        self.write('field.npy', npy((2, 2), '<f4', lambda index: 1.0))
        listed = self.call('records', run=self.run_id)
        self.assertEqual((listed['source'], [record['id'] for record in listed['records']]), ('view', ['field.npy']))

    def test_refusals(self):
        with self.assertRaises(store.ProjectError) as caught:
            self.call('records', run='f' * 32)
        self.assertEqual(caught.exception.code, 'not-found')
        with self.assertRaises(store.ProjectError) as caught:
            self.call('inside', run=self.run_id, path='../..')
        self.assertEqual(caught.exception.code, 'invalid')
        with self.opened() as project:
            project._execute("UPDATE {schema}.runs SET state = 'failed' WHERE id = %s", (self.run_id,))
        with self.assertRaises(store.ProjectError) as caught:
            self.call('records', run=self.run_id)
        self.assertEqual(caught.exception.code, 'not-found')

    def test_nothing_is_written(self):
        self.write('field.npy', npy((2, 2), '<f4', lambda index: 1.0))
        before = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        with self.opened() as project:
            rows = project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0]
        for name, arguments in (('records', {}), ('record', {'id': 'field.npy'}), ('inside', {}),
                                ('array_slice', {'path': 'field.npy'}), ('array_summary', {'path': 'field.npy'})):
            self.call(name, run=self.run_id, **arguments)
        after = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        self.assertEqual(before, after)
        with self.opened() as project:
            self.assertEqual(project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0], rows)


class Published(unittest.TestCase):

    def test_the_five_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in INSIDE:
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in INSIDE} <= folder)
        self.assertFalse({'project.' + name for name in INSIDE} & {item['id'] for item in catalog['operations']})
        import hashlib
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))

    def test_check_validates_the_shape_of_view(self):
        from tuldok_project import documents
        base = {'format': 'tuldok_definition_v1', 'kind': 'dataset', 'title': 'x',
                'earlier_work': {'rebuild': 'no', 'reason': 'old'}}
        self.assertEqual(documents.schema_problems('dataset', {**base, 'view': {'files': 'a.zip!s/*.npz',
                                                                                 'kind': 'array', 'show': 'p'}}), [])
        self.assertTrue(documents.schema_problems('dataset', {**base, 'view': {'records': 'a', 'files': 'b'}}))
        self.assertTrue(documents.schema_problems('dataset', {**base, 'view': {'files': 'a', 'kind': 'video'}}))
        self.assertTrue(documents.schema_problems('dataset', {**base, 'view': {}}))
        from tuldok_project import check
        found = []
        check._check_view({'files': 'a.zip!b.zip!*.npy', 'records': '../x'}, 'datasets/x.json',
                          lambda *problem: found.append(problem))
        self.assertEqual([problem[2] for problem in found], ['/view/records', '/view/files'])


# ------------------------------------------------------------------- the route

@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class FileRoute(ProductCase):

    def setUp(self):
        super().setUp()
        from http.server import ThreadingHTTPServer
        import threading
        from app import make_handler
        from auth_helpers import ExplicitOwnerFixture
        from tuldok_project.host import ProjectHost
        self.host = ProjectHost(self.temporary / 'catalog', self.folder)
        self.addCleanup(self.host.close)
        self.owner = ExplicitOwnerFixture.bootstrap(self.host)
        with self.owner.bound(self.host):
            self.agent = self.host.access.issue({'label': 'Reader', 'scopes': ['inspect']})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.host))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.root = f'http://127.0.0.1:{self.server.server_port}'

    def get(self, address, token=None, headers=()):
        from urllib.parse import urlencode
        sent = {'Authorization': 'Bearer ' + token} if token else {}
        sent.update(headers)
        request = Request(f'{self.root}/api/project/file?' + urlencode({'run': self.run_id, 'path': address}),
                          headers=sent)
        try:
            response = urlopen(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_media_types_dispositions_a_range_and_the_right_to_inspect(self):
        picture, sound = png(4, 4), wav16([0, 1, 2, 3])
        self.write('p.png', picture)
        self.write('s.wav', sound)
        self.write('x.svg', '<svg xmlns="http://www.w3.org/2000/svg"/>')
        self.write('x.html', '<html><script>alert(1)</script></html>')
        token = self.agent['token']
        for address, body, media, disposition in (('p.png', picture, 'image/png', 'inline'),
                                                  ('s.wav', sound, 'audio/wav', 'inline'),
                                                  ('x.svg', None, 'application/octet-stream', 'attachment'),
                                                  ('x.html', None, 'application/octet-stream', 'attachment')):
            with self.subTest(address):
                status, headers, data = self.get(address, token)
                self.assertEqual((status, headers['Content-Type']), (200, media))
                self.assertTrue(headers['Content-Disposition'].startswith(disposition))
                self.assertEqual((headers['X-Content-Type-Options'], headers['Cache-Control']), ('nosniff', 'no-store'))
                if body is not None:
                    self.assertEqual(data, body)
        status, headers, data = self.get('s.wav', token, {'Range': 'bytes=4-9'})
        self.assertEqual((status, data, headers['Content-Range']), (206, sound[4:10], f'bytes 4-9/{len(sound)}'))
        status, _, data = self.get('p.png')
        self.assertEqual(status, 401, data)
        status, _, data = self.get('p.png', 'not-a-token')
        self.assertIn(status, (401, 403))
        status, _, data = self.get('../p.png', token)
        self.assertEqual((status, json.loads(data)['code']), (400, 'invalid'))
        status, _, data = self.get('missing.png', token)
        self.assertEqual((status, json.loads(data)['code']), (404, 'not-found'))
        request = Request(f'{self.root}/api/project/file?run={self.run_id}', headers={'Authorization': 'Bearer ' + token})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=30)
        self.assertEqual(caught.exception.code, 400)
        request = Request(f'{self.root}/api/samples', headers={'Authorization': 'Bearer ' + token})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=30)
        self.assertEqual(caught.exception.code, 409)   # every other /api/ GET is still refused


if __name__ == '__main__':
    unittest.main()
