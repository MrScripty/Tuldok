"""Authored native point data and independently consumed byte-preserving bundles."""
from decimal import Decimal, localcontext
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import unittest
import zipfile

import pointclouds
from workbench import WorkbenchError

FIXTURES = Path(__file__).parent / 'fixtures' / 'pointclouds'


def fixture(raw=None, change=None):
    geometry = (FIXTURES / 'ordered.ply').read_bytes() if raw is None else raw
    value = json.loads((FIXTURES / 'ordered.json').read_bytes())
    value.update(geometry_bytes=len(geometry), geometry_sha256=hashlib.sha256(geometry).hexdigest())
    if change:
        change(value)
    return geometry, json.dumps(value).encode()


def simple(rows='0 0 0\n', count=1):
    return ('ply\nformat ascii 1.0\nelement vertex ' + str(count) +
            '\nproperty float x\nproperty double y\nproperty float z\nend_header\n' + rows).encode()


class PointClouds(unittest.TestCase):
    def test_native_values_and_exact_bundle(self):
        raw, sidecar = fixture()
        result = pointclouds.prepare(raw, sidecar)
        self.assertEqual(result['geometry']['points'][1], [1.25, -2.5, 3, 0, 1, 0, 1, 2, 3])
        self.assertEqual(result['geometry']['points'][0], result['geometry']['points'][2])
        self.assertEqual(math.copysign(1, result['geometry']['points'][0][0]), -1)
        self.assertEqual(result['metadata']['bounds'], {'min': [-0., -2.5, 1], 'max': [1.25, 0., 3]})
        self.assertTrue(result['metadata']['provided_normals'])
        self.assertTrue(result['metadata']['provided_colors'])
        self.assertEqual(result['metadata']['point_count'], 3)
        with zipfile.ZipFile(io.BytesIO(result['bundle'])) as archive:
            self.assertEqual(archive.namelist(), ['points.ply', 'points.json'])
            self.assertEqual(archive.read('points.ply'), raw)
            self.assertEqual(archive.read('points.json'), sidecar)
        self.assertEqual(result['bundle'], pointclouds.prepare(raw, sidecar)['bundle'])

    def test_xyz_and_optional_groups(self):
        raw, _ = fixture()
        for normals, colors in ((False, False), (True, False), (False, True), (True, True)):
            lines = raw.decode().splitlines()
            fields = [0, 1, 2] + ([3, 4, 5] if normals else []) + ([6, 7, 8] if colors else [])
            header = lines[:4] + [line for i, line in enumerate(lines[4:13]) if i in fields] + ['end_header']
            data = [' '.join(line.split()[i] for i in fields) for line in lines[14:]]
            prepared = pointclouds.prepare(*fixture(('\n'.join(header + data) + '\n').encode()))
            self.assertEqual(prepared['metadata']['provided_normals'], normals)
            self.assertEqual(prepared['metadata']['provided_colors'], colors)

    def test_float_native_rounding_and_signed_zero(self):
        self.assertEqual(pointclouds.native('16777217', 'float'), 16777216.)
        self.assertEqual(pointclouds.native('16777217', 'double'), 16777217.)
        for dtype in ('float', 'double'):
            self.assertEqual(math.copysign(1, pointclouds.native('-0.0', dtype)), -1)
        with localcontext() as context:
            context.prec = 100
            midpoint = Decimal(1) + Decimal(2) ** -24
            token = str(midpoint + Decimal(2) ** -80)
        self.assertEqual(struct.pack('<f', pointclouds.native(token, 'float')), struct.pack('<I', 0x3f800001))

    def test_nonfinite_overflow_underflow(self):
        for token in ('nan', 'NaN', 'inf', '-inf', '1e999', '1e-999', '1000000000001', '0x1', '1_0'):
            for dtype in ('float', 'double'):
                with self.subTest(token=token, dtype=dtype), self.assertRaises(WorkbenchError):
                    pointclouds.native(token, dtype)
        with self.assertRaises(WorkbenchError):
            pointclouds.native('1e-46', 'float')

    def test_bad_ply_structure(self):
        raw = simple()
        bad = [raw[:-1], raw + b'0 0 0\n', raw.replace(b'vertex 1', b'vertex 0'),
               raw.replace(b'vertex 1', b'vertex 20001'), raw.replace(b'vertex 1', b'vertex 01'),
               raw.replace(b'float x', b'float y'), raw.replace(b'float x', b'int x'),
               raw.replace(b'end_header', b'element face 0\nend_header'),
               raw.replace(b'end_header', b'property float nx\nend_header'),
               raw.replace(b'end_header', b'property uchar red\nend_header'),
               raw.replace(b'0 0 0', b'0 0'), raw.replace(b'ascii', b'binary_little_endian'),
               raw.replace(b'0 0 0', b'0\x0b0 0'), raw.replace(b'0 0 0', b'0\r0 0'),
               raw.replace(b'0 0 0', b'0 \xff 0'), raw.replace(b'end_header', b'comment '+b'x'*1025+b'\nend_header'),
               raw.replace(b'end_header', (b'comment '+b'x'*1000+b'\n')*17+b'end_header')]
        for index, value in enumerate(bad):
            with self.subTest(case=index), self.assertRaises(WorkbenchError):
                pointclouds.prepare(*fixture(value))

    def test_rgb_negatives(self):
        raw, _ = fixture()
        for token in ('256', '-1', '1.5', '+1', '01'):
            with self.subTest(token=token), self.assertRaises(WorkbenchError):
                pointclouds.prepare(*fixture(raw.replace(b'255', token.encode())))

    def test_crlf_preserved(self):
        raw = simple().replace(b'\n', b'\r\n')
        result = pointclouds.prepare(*fixture(raw))
        with zipfile.ZipFile(io.BytesIO(result['bundle'])) as archive:
            self.assertEqual(archive.read('points.ply'), raw)

    def test_bounds(self):
        pointclouds.prepare(*fixture(simple('0 0 0\n' * pointclouds.POINT_LIMIT, pointclouds.POINT_LIMIT)))
        with self.assertRaises(WorkbenchError):
            pointclouds.prepare(b' ' * (pointclouds.PLY_LIMIT + 1), b'{}')
        with self.assertRaises(WorkbenchError):
            pointclouds.prepare(simple(), b' ' * (pointclouds.MANIFEST_LIMIT + 1))

    def test_manifest_integrity_types_paths_and_duplicates(self):
        raw, sidecar = fixture()
        changes = [lambda v: v.update(geometry_file='../points.ply'), lambda v: v.update(geometry_bytes=True),
                   lambda v: v.update(geometry_sha256='0'*64), lambda v: v.update(units='in'),
                   lambda v: v.update(extra=1), lambda v: v['coordinate_system'].update(up_axis='w'),
                   lambda v: v['lineage'].update(source_id='../origin'), lambda v: v['lineage'].update(source_sha256='ABC'),
                   lambda v: v['provenance'].update(source=[])]
        for index, change in enumerate(changes):
            with self.subTest(case=index), self.assertRaises(WorkbenchError):
                pointclouds.prepare(*fixture(change=change))
        for data in (sidecar.replace(b'"units": "mm"', b'"units": "mm", "units": "m"'),
                     b'[]', b'{"x":NaN}', b'\xff', b'['*2000):
            with self.assertRaises(WorkbenchError):
                pointclouds.prepare(raw, data)

    def test_lineage_is_declared_and_groups_stable(self):
        first = pointclouds.prepare(*fixture())
        raw = simple('2 3 4\n')
        second = pointclouds.prepare(*fixture(raw))
        self.assertEqual(first['metadata']['protected_groups'][0], second['metadata']['protected_groups'][0])
        self.assertNotEqual(first['metadata']['protected_groups'][1], second['metadata']['protected_groups'][1])


class IndependentPointReader(unittest.TestCase):
    def test_plyfile_reads_original_bundle_with_native_types_and_order(self):
        try:
            from plyfile import PlyData
            import numpy as np
        except ImportError:
            self.skipTest('Run in .venv-training with qualified plyfile and NumPy.')
        raw, sidecar = fixture()
        prepared = pointclouds.prepare(raw, sidecar)
        with zipfile.ZipFile(io.BytesIO(prepared['bundle'])) as archive:
            downloaded = archive.read('points.ply')
        self.assertEqual(downloaded, raw)
        data = PlyData.read(io.BytesIO(downloaded))['vertex'].data
        self.assertEqual(data.dtype.names, ('x', 'y', 'z', 'nx', 'ny', 'nz', 'red', 'green', 'blue'))
        self.assertEqual([data.dtype[name].itemsize for name in data.dtype.names], [4, 8, 4, 4, 4, 4, 1, 1, 1])
        self.assertTrue(np.signbit(data['x'][0]))
        for row, expected in zip(data, prepared['geometry']['points']):
            self.assertEqual(list(row), expected)


if __name__ == '__main__':
    unittest.main()
