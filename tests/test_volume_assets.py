"""Authored bounded native volume fixtures; no model or medical acceptance."""
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import unittest
import zipfile

import volume_assets as volumes
from workbench import WorkbenchError

FIXTURES = Path(__file__).parent / 'fixtures' / 'volumes'


def npy(header=None, data=bytes(range(24))):
    header = header or "{'descr': '|u1', 'fortran_order': False, 'shape': (2, 3, 4)}"
    raw = header.encode('ascii')
    raw += b' ' * ((-10 - len(raw) - 1) % 64) + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(raw)) + raw + data


def fixture(raw=None, change=None):
    raw = (FIXTURES / 'oriented.npy').read_bytes() if raw is None else raw
    sidecar = json.loads((FIXTURES / 'oriented.json').read_bytes())
    sidecar.update(volume_bytes=len(raw), volume_sha256=hashlib.sha256(raw).hexdigest())
    if change:
        change(sidecar)
    return raw, json.dumps(sidecar).encode()


class VolumeAssets(unittest.TestCase):
    def test_originals_retained_and_deterministic(self):
        raw, sidecar = fixture()
        prepared = volumes.prepare(raw, sidecar)
        self.assertEqual(prepared, volumes.prepare(raw, sidecar))
        with zipfile.ZipFile(io.BytesIO(prepared['bundle'])) as archive:
            self.assertEqual(archive.namelist(), ['volume.npy', 'volume.json'])
            self.assertEqual(archive.read('volume.npy'), raw)
            self.assertEqual(archive.read('volume.json'), sidecar)
        self.assertEqual(prepared['metadata']['spacing_xyz'], [2, 3, 5])
        self.assertEqual(prepared['volume'], dict(shape=[2, 3, 4], data=bytes(range(24))))

    def test_each_index_plane_values_and_physical_coordinates(self):
        prepared = volumes.prepare(*fixture())
        z = volumes.project_slice(prepared, 'z', 1)
        self.assertEqual(z['values'], [[12, 13, 14, 15], [16, 17, 18, 19], [20, 21, 22, 23]])
        self.assertEqual(z['physical_origin'], [10, -20, 35])
        self.assertEqual(z['physical_row_step'], [-3, 0, 0])
        self.assertEqual(z['physical_column_step'], [0, 2, 0])
        self.assertEqual(volumes.project_slice(prepared, 'y', 2)['values'], [[8, 9, 10, 11], [20, 21, 22, 23]])
        self.assertEqual(volumes.project_slice(prepared, 'x', 3)['values'], [[3, 7, 11], [15, 19, 23]])
        for axis, index in [('a', 0), ('z', 2), ('x', -1), ('y', True), ('x', 1.0)]:
            with self.subTest(axis=axis, index=index), self.assertRaises(WorkbenchError):
                volumes.project_slice(prepared, axis, index)

    def test_npy_rejects_alternate_types_shapes_headers_and_lengths(self):
        headers = ["{'descr': '|O', 'fortran_order': False, 'shape': (2,3,4)}",
                   "{'descr': '<u2', 'fortran_order': False, 'shape': (2,3,4)}",
                   "{'descr': [('x','u1')], 'fortran_order': False, 'shape': (2,3,4)}",
                   "{'descr': '|u1', 'fortran_order': True, 'shape': (2,3,4)}",
                   "{'descr': '|u1', 'fortran_order': False, 'shape': (2,3)}",
                   "{'descr': '|u1', 'fortran_order': False, 'shape': (0,3,4)}",
                   "{'descr': '|u1', 'fortran_order': False, 'shape': (129,3,4)}",
                   "{'descr': '|u1', 'fortran_order': False, 'shape': (True,3,4)}",
                   "{'descr': '|u1', 'fortran_order': False, 'shape': [2,3,4]}",
                   "{'descr': '|u1', 'descr': '|u1', 'shape': (2,3,4)}",
                   "__import__('os').system('false')"]
        raw = npy()
        bad = [npy(header) for header in headers] + [raw[:-1], raw + b'x', raw[:6] + b'\x02\x00' + raw[8:], b'', raw[:10]]
        for source in bad:
            with self.subTest(source=source[:100]), self.assertRaises(WorkbenchError):
                volumes.parse_npy(source)

    def test_maximum_and_single_voxel(self):
        maximum = npy("{'descr': '|u1', 'fortran_order': False, 'shape': (128,128,128)}", b'\xff' * volumes.VOXEL_LIMIT)
        self.assertEqual(len(volumes.parse_npy(maximum)['data']), volumes.VOXEL_LIMIT)
        single = npy("{'descr': '|u1', 'fortran_order': False, 'shape': (1,1,1)}", b'\x07')
        self.assertEqual(volumes.parse_npy(single)['data'], b'\x07')

    def test_sidecar_rejects_wrong_hash_length_shape_and_semantics(self):
        updates = [dict(volume_sha256='0' * 64), dict(volume_bytes=True), dict(shape=[True, 3, 4]),
                   dict(shape=[2, 4, 3]), dict(dtype='int8'), dict(order='F'), dict(units='inch'),
                   dict(value_semantics=''), dict(provenance={}), dict(extra=True)]
        for update in updates:
            with self.subTest(update=update), self.assertRaises(WorkbenchError):
                volumes.prepare(*fixture(change=lambda value: value.update(update)))
        raw, sidecar = fixture()
        for bad in [sidecar[:-1] + b',"units":"mm"}', b'{', b'\xff', b'x' * (volumes.MANIFEST_LIMIT + 1)]:
            with self.assertRaises(WorkbenchError):
                volumes.prepare(raw, bad)

    def test_reject_shear_degenerate_nonfinite_and_overflow(self):
        original = json.loads(fixture()[1])['affine']
        changes = [(0, 0, 1), (2, 2, 0), (0, 0, float('nan')), (0, 0, float('inf')),
                   (3, 0, 1), (0, 1, -1e308), (0, 3, 10 ** 400)]
        for row, column, value in changes:
            matrix = copy.deepcopy(original)
            matrix[row][column] = value
            with self.subTest(value=value), self.assertRaises(WorkbenchError):
                volumes.prepare(*fixture(change=lambda sidecar: sidecar.update(affine=matrix)))

    def test_general_rotation_reflection_and_representable_affine(self):
        angle = math.pi / 7
        c, s = math.cos(angle), math.sin(angle)
        matrix = [[2*c, -3*s, 0, -2], [2*s, 3*c, 0, 7], [0, 0, -5, 11], [0, 0, 0, 1]]
        prepared = volumes.prepare(*fixture(change=lambda sidecar: sidecar.update(affine=matrix)))
        for actual, expected in zip(prepared['metadata']['spacing_xyz'], [2, 3, 5]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(volumes.project_slice(prepared, 'z', 1)['physical_origin'], [-2, 7, 6])
        for matrix in [[], [[1]], [[True, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]]:
            with self.assertRaises(WorkbenchError):
                volumes.prepare(*fixture(change=lambda sidecar: sidecar.update(affine=matrix)))
        raw, sidecar = fixture()
        for token in [b'1e999', b'1e-999']:
            with self.assertRaises(WorkbenchError):
                volumes.prepare(raw, sidecar.replace(b'10]', token + b']'))

    def test_family_cannot_split_by_header_or_physical_metadata(self):
        first = volumes.prepare(*fixture())
        other = npy("{'shape': (2,3,4), 'fortran_order': False, 'descr': '|u1'}")
        second = volumes.prepare(*fixture(raw=other, change=lambda sidecar: sidecar.update(units='cm')))
        self.assertNotEqual(first['metadata']['source_sha256'], second['metadata']['source_sha256'])
        self.assertEqual(first['metadata']['protected_groups'][1], second['metadata']['protected_groups'][1])

    def test_independent_numpy_reader(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('Independent native-reader qualification requires NumPy.')
        raw, sidecar = fixture()
        prepared = volumes.prepare(raw, sidecar)
        with zipfile.ZipFile(io.BytesIO(prepared['bundle'])) as archive:
            array = np.load(io.BytesIO(archive.read('volume.npy')), allow_pickle=False)
        self.assertEqual(array.dtype, np.dtype('uint8'))
        self.assertEqual(array.shape, (2, 3, 4))
        self.assertTrue(array.flags.c_contiguous)
        np.testing.assert_array_equal(array, np.arange(24, dtype=np.uint8).reshape(2, 3, 4))
        affine = np.asarray(json.loads(sidecar)['affine'])
        np.testing.assert_array_equal(affine @ [3, 2, 1, 1], [4, -14, 35, 1])
        for axis, index, expected in [('z', 1, array[1]), ('y', 2, array[:, 2]), ('x', 3, array[:, :, 3])]:
            np.testing.assert_array_equal(volumes.project_slice(prepared, axis, index)['values'], expected)


if __name__ == '__main__':
    unittest.main()
