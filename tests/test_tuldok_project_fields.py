"""The fields a run kept, side by side (docs/plans/definition-first-projects/spec-d6.md, slice D6a).

The readers are tested on files the tests write with the standard library
(NPY with struct, the index and probe with json) and need no database. The
operations need one and run only when TULDOK_DATABASE_URL names a disposable
cluster: they adopt a product for recipes/fit-a (as test_tuldok_project_weights
does) holding a field index and its arrays. No GPU is used.
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
from tuldok_project import adoption, inside, inside_archive, inside_fields, local, operations, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
from test_tuldok_project_inside import OWNER, f32, floats, npy, raw_header  # noqa: E402

FIELDS = ('fields', 'field_compare')
NAN = float('nan')


def flat(shape, value):
    """value(index) over shape in C order."""
    indexes = [()]
    for size in shape:
        indexes = [index + (position,) for index in indexes for position in range(size)]
    return [value(index) for index in indexes]


def case(predicted='p.npy', reference='r.npy', mask=None, **extra):
    return {'predicted': {'name': predicted, **extra.pop('predicted_extra', {})},
            'reference': {'name': reference, **extra.pop('reference_extra', {})},
            'mask': None if mask is None else {'name': mask}, **extra}


def norm(values):
    return math.sqrt(math.fsum(value * value for value in values))


def same(a, b):
    """Two lists of floats equal, NaN equal to NaN."""
    return len(a) == len(b) and all((x != x and y != y) or x == y for x, y in zip(a, b))


class FieldCase(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = os.path.realpath(directory.name)
        inside_archive.forget_members()
        inside.forget_indexes()
        inside_fields.forget_figures()
        self.product = inside.Product('run-1', self.root)

    def write(self, name, data):
        path = Path(self.root, name)
        path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
        return path

    def index(self, *entries):
        self.write('field-index.json', [{'run_id': 'r' * 32, 'cases': list(cases)} for cases in entries])

    def pair(self, shape, reference, predicted, *, descr='<f8', names=('r.npy', 'p.npy'), fortran=False):
        self.write(names[0], npy(shape, descr, reference, fortran=fortran))
        self.write(names[1], npy(shape, descr, predicted))

    def refused(self, code, call, *arguments, **options):
        with self.assertRaises(store.ProjectError) as caught:
            call(*arguments, **options)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def compare(self, **options):
        got = inside_fields.field_compare(self.product, **{'entry': 0, 'case': 0, **options})
        json.dumps(got, allow_nan=False)
        return got


# ------------------------------------------------------------------ fields

class Listing(FieldCase):

    def test_a_product_without_an_index_keeps_none(self):
        self.write('pressure-diagnostic.json', {'format': 'x_diagnostic_v1', 'relative_l2': 0.5})
        self.assertEqual(inside_fields.fields(self.product), {'kept': False, 'cases': [], 'reported': [],
                                                              'more': False})
        self.refused('not-found', inside_fields.field_compare, self.product, entry=0, case=0)

    def test_two_cases_named_from_the_probe_with_the_reported_figures(self):
        value = lambda index: index[0] * 10.0 + index[1]  # noqa: E731
        self.pair((3, 4), value, lambda index: value(index) + 1)
        self.write('p2.npy', npy((3, 4), '<f4', value))
        size = os.path.getsize(Path(self.root, 'r.npy'))
        self.index([case(member_ordinal=0, time_units='not_applicable', reference_extra={'bytes': size},
                         predicted_extra={'sha256': '0' * 64}),
                    case('p2.npy', member_ordinal=1)])
        self.write('probe.json', {'format': 'probe_v1', 'split': 'validation', 'members': [
            {'ordinal': 0, 'frozen_reference': {'member_id': 'scene-0000-frame-15', 'split': 'validation'}},
            {'ordinal': 1, 'frozen_reference': {'member_id': 'scene-0001-frame-03', 'split': 'test'}}]})
        self.write('pressure-diagnostic.json', {
            'format': 'rheon_pressure_diagnostic_v1', 'mean_free_same_request_pressure_relative_l2': 0.0028,
            'relative_l2': 1, 'other_relative_l2': True, 'nested': {'inner_relative_l2': 0.1}, 'count': 3})
        self.write('summary.json', {'format': 'summary_v1', 'relative_l2': 9.0})
        got = inside_fields.fields(self.product)
        self.assertTrue(got['kept'])
        first, second = got['cases']
        self.assertEqual({key: first[key] for key in ('entry', 'case', 'name', 'split', 'predicted', 'reference',
                                                      'mask', 'shape', 'dtype', 'comparable')},
                         {'entry': 0, 'case': 0, 'name': 'scene-0000-frame-15', 'split': 'validation',
                          'predicted': 'p.npy', 'reference': 'r.npy', 'mask': None, 'shape': [3, 4],
                          'dtype': 'float64', 'comparable': True})
        self.assertEqual(first['details'], {'member_ordinal': 0, 'time_units': 'not_applicable'})
        self.assertNotIn('bytes_mismatch', first)
        self.assertNotIn('reason', first)
        self.assertEqual((second['name'], second['split'], second['dtype'], second['comparable']),
                         ('scene-0001-frame-03', 'test', 'float32 / float64', True))
        self.assertEqual(got['reported'], [
            {'file': 'pressure-diagnostic.json', 'field': 'mean_free_same_request_pressure_relative_l2',
             'value': 0.0028},
            {'file': 'pressure-diagnostic.json', 'field': 'relative_l2', 'value': 1}])
        os.remove(Path(self.root, 'probe.json'))
        self.assertEqual([(item['name'], item['split']) for item in inside_fields.fields(self.product)['cases']],
                         [('case 0', None), ('case 1', None)])

    def test_each_case_that_cannot_be_compared_is_listed_with_its_reason(self):
        value = lambda index: float(sum(index))  # noqa: E731
        self.pair((2, 3), value, value)
        self.write('wide.npy', npy((3, 2), '<f8', value))
        self.write('flags.npy', npy((2, 3), '|b1', lambda index: True))
        self.write('wide-mask.npy', npy((3, 2), '|u1', lambda index: 1))
        self.write('complex.npy', raw_header('<c8', (2, 3)))
        self.write('short.npy', npy((2, 3), '<f8', value)[:-8])
        self.write('notes.txt', b'not an array')
        sub = Path(self.root, 'sub')
        sub.mkdir()
        (sub / 'p.npy').write_bytes(npy((2, 3), '<f8', value))
        self.index([case(),
                    case('wide.npy'),
                    case('gone.npy'),
                    case('sub/p.npy'),
                    case('../p.npy'),
                    case('flags.npy'),
                    case('complex.npy'),
                    case('short.npy'),
                    case('notes.txt'),
                    case(reference_extra={'bytes': 7}, predicted_extra={'bytes': 1}),
                    {'predicted': {'name': 'p.npy'}},
                    'not a case',
                    case(mask='wide-mask.npy'),
                    case(mask='complex.npy'),
                    case(mask='wide.npy')],
                   [case(member_ordinal=4)])
        got = inside_fields.fields(self.product)['cases']
        self.assertEqual([(item['entry'], item['case']) for item in got], [(0, i) for i in range(15)] + [(1, 0)])
        reasons = [(item['comparable'], item.get('reason')) for item in got]
        self.assertEqual(reasons[0], (True, None))
        expected = {1: 'of the shape [3, 2]', 2: 'gone.npy is not in the product', 3: 'not a plain file name',
                    4: 'not a plain file name', 5: 'of the type bool, not a number', 6: 'a complex array',
                    7: 'shorter than its shape says', 8: 'not an .npy file',
                    10: 'does not name its predicted and reference', 11: 'not a JSON object',
                    12: 'The mask file is of the shape [3, 2]', 13: 'a complex array',
                    14: 'not a boolean or integer mask'}
        for position, words in expected.items():
            with self.subTest(position):
                self.assertFalse(reasons[position][0])
                self.assertIn(words, reasons[position][1])
        self.assertEqual((got[9]['comparable'], sorted(got[9]['bytes_mismatch'])), (True, ['p.npy', 'r.npy']))
        self.assertEqual((got[15]['name'], got[15]['comparable']), ('entry 1 case 0', True))
        for position in expected:
            self.refused('unsupported', inside_fields.field_compare, self.product, entry=0, case=position)
        self.refused('not-found', inside_fields.field_compare, self.product, entry=0, case=15)
        self.refused('not-found', inside_fields.field_compare, self.product, entry=2, case=0)
        self.assertEqual(self.compare(case=9)['figures']['max_abs_error'], 0.0)

    def test_a_damaged_index_is_refused(self):
        for text in (b'[{"cases": [', b'{"cases": []}', b'[{"run_id": "x"}]', b'[{"cases": {}}]', b'null',
                     b'\xff\xfe'):
            with self.subTest(text):
                self.write('field-index.json', text)
                self.refused('unsupported', inside_fields.fields, self.product)
                self.refused('unsupported', inside_fields.field_compare, self.product, entry=0, case=0)
        self.write('field-index.json', b'[]')
        self.assertEqual(inside_fields.fields(self.product)['cases'], [])
        with mock.patch.object(inside_fields, 'INDEX_BYTES', 1):
            self.refused('too-large', inside_fields.fields, self.product)


# ------------------------------------------------------------------ field_compare

class Compare(FieldCase):

    def test_identical_fields(self):
        value = lambda index: index[0] - 2.0 * index[1]  # noqa: E731
        self.pair((4, 5), value, value)
        self.index([case()])
        got = self.compare()
        self.assertEqual(got['figures'], {'count': 20, 'nonfinite': 0, 'max_abs_error': 0.0, 'mean_error': 0.0,
                                          'rmse': 0.0, 'relative_l2': 0.0, 'mean_free_relative_l2': 0.0})
        self.assertEqual((got['error_limit'], got['axes'], got['axis'], got['rows'], got['columns'], got['stride']),
                         (0.0, [0, 1], None, 4, 5, 1))
        self.assertEqual(floats(got['error_f32']), [0.0] * 20)
        values = flat((4, 5), value)
        self.assertEqual(got['range'], [min(values), max(values)])

    def test_a_constant_offset_is_gone_without_the_mean(self):
        value = lambda index: index[0] * 3.0 + index[1] - 4.0  # noqa: E731
        self.pair((3, 4), value, lambda index: value(index) + 0.5)
        self.index([case()])
        got = self.compare()
        reference = flat((3, 4), value)
        figures = got['figures']
        self.assertEqual((figures['max_abs_error'], figures['mean_error'], figures['rmse']), (0.5, 0.5, 0.5))
        self.assertAlmostEqual(figures['relative_l2'], math.sqrt(12 * 0.25) / norm(reference), places=15)
        self.assertGreater(figures['relative_l2'], 0)
        self.assertEqual(figures['mean_free_relative_l2'], 0.0)
        self.assertEqual(floats(got['error_f32']), [0.5] * 12)
        self.assertEqual(got['error_limit'], 0.5)
        free = self.compare(mean_free=True)
        self.assertEqual((free['mean_free'], floats(free['error_f32']), free['error_limit']), (True, [0.0] * 12, 0.0))
        self.assertEqual(free['figures'], figures)
        self.assertEqual(free['reference_f32'], got['reference_f32'])   # the panels stay native
        self.assertEqual(got['range'], [min(reference), max(reference) + 0.5])

    def test_figures_against_arithmetic(self):
        shape = (3, 5, 4)
        reference = lambda index: math.sin(index[0] + 0.3 * index[1] - 0.7 * index[2])  # noqa: E731
        predicted = lambda index: 1.1 * reference(index) + 0.02 * index[2] - 0.3  # noqa: E731
        self.pair(shape, reference, predicted)
        self.index([case()])
        r, p = flat(shape, reference), flat(shape, predicted)
        e = [b - a for a, b in zip(r, p)]
        mr, mp = math.fsum(r) / len(r), math.fsum(p) / len(p)
        free = [(b - mp) - (a - mr) for a, b in zip(r, p)]
        figures = self.compare()['figures']
        self.assertEqual((figures['count'], figures['nonfinite']), (60, 0))
        self.assertEqual(figures['max_abs_error'], max(map(abs, e)))
        self.assertAlmostEqual(figures['mean_error'], math.fsum(e) / 60, places=15)
        self.assertAlmostEqual(figures['rmse'], norm(e) / math.sqrt(60), places=15)
        self.assertAlmostEqual(figures['relative_l2'], norm(e) / norm(r), places=15)
        self.assertAlmostEqual(figures['mean_free_relative_l2'], norm(free) / norm([a - mr for a in r]), places=15)

    def test_a_mask(self):
        value = lambda index: float(index[0] * 4 + index[1])  # noqa: E731
        self.pair((3, 4), value, lambda index: value(index) + (100.0 if index[1] == 0 else 1.0))
        self.write('inside.npy', npy((3, 4), '|u1', lambda index: 0 if index[1] == 0 else 7))
        self.write('bools.npy', npy((3, 4), '|b1', lambda index: index[1] != 0))
        self.index([case(mask='inside.npy'), case(mask='bools.npy')])
        for position in (0, 1):
            got = self.compare(case=position)
            self.assertEqual((got['figures']['count'], got['figures']['max_abs_error'], got['figures']['rmse'],
                              got['error_limit']), (9, 1.0, 1.0, 1.0))
            inside_values = [value((i, j)) for i in range(3) for j in range(1, 4)]
            self.assertAlmostEqual(got['figures']['relative_l2'], 3.0 / norm(inside_values), places=15)
            for key in ('reference_f32', 'predicted_f32', 'error_f32'):
                shown = floats(got[key])
                self.assertTrue(all(math.isnan(shown[at]) for at in (0, 4, 8)), key)
                self.assertFalse(any(math.isnan(item) for at, item in enumerate(shown) if at % 4), key)
            self.assertEqual(got['range'], [1.0, 12.0])

    def test_non_finite_values_are_counted_and_left_out(self):
        value = lambda index: float(index[0] + 1)  # noqa: E731
        self.pair((2, 3), value, lambda index: NAN if index == (0, 0) else math.inf if index == (1, 2)
                  else value(index) + 1.0)
        self.write('r2.npy', npy((2, 3), '<f8', lambda index: -math.inf if index == (0, 0) else value(index)))
        self.index([case(), case(reference='r2.npy')])
        got = self.compare()
        self.assertEqual((got['figures']['count'], got['figures']['nonfinite'], got['figures']['rmse']), (4, 2, 1.0))
        self.assertAlmostEqual(got['figures']['relative_l2'], 2.0 / norm([1.0, 1.0, 2.0, 2.0]), places=15)
        self.assertEqual(got['error_limit'], 1.0)
        error = floats(got['error_f32'])
        self.assertTrue(math.isnan(error[0]) and math.isinf(error[5]))
        self.assertEqual(self.compare(case=1)['figures']['nonfinite'], 3)   # both of (0, 0), and (1, 2)

    def test_a_zero_reference(self):
        self.pair((2, 2), lambda index: 0.0, lambda index: 1.0 + index[0])
        self.write('flat.npy', npy((2, 2), '<f8', lambda index: 3.0))
        self.index([case(), case('flat.npy')])
        figures = self.compare()['figures']
        self.assertEqual((figures['relative_l2'], figures['mean_free_relative_l2'], figures['rmse']),
                         (None, None, math.sqrt(10 / 4)))
        self.assertEqual(self.compare(case=1)['figures']['mean_free_relative_l2'], None)

    def test_each_axis_of_a_three_dimensional_field_is_the_slice_of_both_files(self):
        shape = (3, 4, 5)
        reference = lambda index: index[0] * 100.0 + index[1] * 10.0 + index[2]  # noqa: E731
        predicted = lambda index: reference(index) * 0.5 - index[1]  # noqa: E731
        self.pair(shape, reference, predicted, fortran=True)   # a Fortran-ordered reference beside a C one
        self.index([case()])
        default = self.compare()
        self.assertEqual((default['axis'], default['axes'], default['index']), (2, [0, 1], [1, 2, 2]))
        for axis in range(3):
            for position in range(shape[axis]):
                index = [1, 2, 2]
                index[axis] = position
                with self.subTest(axis=axis, position=position):
                    got = self.compare(axis=axis, index=index)
                    axes = [other for other in range(3) if other != axis]
                    self.assertEqual(got['axes'], axes)
                    for key, path in (('reference_f32', 'r.npy'), ('predicted_f32', 'p.npy')):
                        want = inside.array_slice(self.product, path=path, axes=axes, index=index)
                        self.assertEqual(floats(got[key]), floats(want['values_f32']))
                        self.assertEqual((got['rows'], got['columns'], got['stride']),
                                         (want['rows'], want['columns'], want['stride']))
                    r, p = floats(got['reference_f32']), floats(got['predicted_f32'])
                    self.assertEqual(floats(got['error_f32']), [f32(b - a) for a, b in zip(r, p)])
        self.assertAlmostEqual(default['figures']['relative_l2'],
                               norm([predicted(i) - reference(i) for i in self._indexes(shape)])
                               / norm([reference(i) for i in self._indexes(shape)]), places=15)
        self.refused('invalid', self.compare, axis=3)
        self.refused('invalid', self.compare, index=[0, 0])
        self.refused('invalid', self.compare, axis=0, index=[3, 0, 0])

    @staticmethod
    def _indexes(shape):
        out = [()]
        for size in shape:
            out = [index + (position,) for index in out for position in range(size)]
        return out

    def test_one_two_and_four_axes(self):
        self.pair((7,), lambda index: float(index[0]), lambda index: index[0] * 2.0, names=('r1.npy', 'p1.npy'))
        self.pair((2, 3), lambda index: float(index[1]), lambda index: 1.0, names=('r2.npy', 'p2.npy'))
        shape4 = (2, 3, 4, 5)
        value4 = lambda index: float(index[0] * 1000 + index[1] * 100 + index[2] * 10 + index[3])  # noqa: E731
        self.pair(shape4, value4, lambda index: value4(index) + index[0], names=('r4.npy', 'p4.npy'))
        self.write('one.npy', npy((), '<f8', lambda index: 1.0))
        self.write('five.npy', npy((1, 1, 1, 1, 2), '<f8', lambda index: 1.0))
        self.index([case('p1.npy', 'r1.npy'), case('p2.npy', 'r2.npy'), case('p4.npy', 'r4.npy'),
                    case('one.npy', 'one.npy'), case('five.npy', 'five.npy')])
        one = self.compare(case=0)
        self.assertEqual((one['axes'], one['axis'], one['rows'], one['columns']), ([0], None, 1, 7))
        self.assertEqual(floats(one['error_f32']), [float(i) for i in range(7)])
        two = self.compare(case=1, axis=0)
        self.assertEqual((two['axes'], two['axis'], two['rows'], two['columns']), ([0, 1], None, 2, 3))
        four = self.compare(case=2, axis=1, index=[1, 2, 0, 0])
        self.assertEqual((four['axes'], four['axis'], four['rows'], four['columns']), ([2, 3], 1, 4, 5))
        want = inside.array_slice(self.product, path='r4.npy', axes=[2, 3], index=[1, 2, 0, 0])
        self.assertEqual(floats(four['reference_f32']), floats(want['values_f32']))
        self.assertEqual(floats(four['error_f32']), [1.0] * 20)
        last = self.compare(case=2)
        self.assertEqual((last['axes'], last['axis'], last['index']), ([1, 2], 3, [1, 1, 2, 2]))
        listed = inside_fields.fields(self.product)['cases']
        self.assertIn('0 axes', listed[3]['reason'])
        self.assertIn('5 axes', listed[4]['reason'])

    def test_subsampling_and_the_size_bound(self):
        self.pair((300, 40), lambda index: index[0] + index[1] / 100, lambda index: float(index[0]))
        self.index([case()])
        got = self.compare()
        want = inside.array_slice(self.product, path='r.npy')
        self.assertEqual((got['stride'], got['rows'], got['columns']), (2, 150, 20))
        self.assertEqual(floats(got['reference_f32']), floats(want['values_f32']))
        self.assertEqual(got['figures']['count'], 12000)   # figures over the whole field, not the slice
        inside_fields.forget_figures()
        with mock.patch.object(inside_fields, 'FIELD_VALUES', 11999):
            listed = inside_fields.fields(self.product)['cases'][0]
            self.assertFalse(listed['comparable'])
            self.assertIn('12000 values', listed['reason'])
            self.refused('too-large', self.compare)
        with mock.patch.object(inside_fields, 'FIELD_VALUES', 12000):
            self.compare()

    def test_figures_are_kept_while_the_files_are_unchanged(self):
        self.pair((2, 2), lambda index: 1.0, lambda index: 2.0)
        self.index([case()])
        self.assertEqual(self.compare()['figures']['rmse'], 1.0)
        with mock.patch.object(inside_fields.inside_arrays, 'c_order_values',
                               side_effect=AssertionError('read again')):
            self.assertEqual(self.compare(index=[0, 0])['figures']['rmse'], 1.0)
        path = self.write('p.npy', npy((2, 2), '<f8', lambda index: 4.0))
        stamp = os.stat(path).st_mtime_ns + 10 ** 9
        os.utime(path, ns=(stamp, stamp))   # changed, whatever the clock's granularity
        self.assertEqual(self.compare()['figures']['rmse'], 3.0)


# ------------------------------------------------------------ through the service

@unittest.skipUnless(builds_base.DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Operations(builds_base.BuildCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        inside_archive.forget_members()
        inside.forget_indexes()
        inside_fields.forget_figures()
        sources = self.temporary / 'sources'
        sources.mkdir()
        shape = (4, 4, 4)
        files = {'pressure-reference.npy': npy(shape, '<f8', lambda index: float(sum(index))),
                 'pressure-prediction.npy': npy(shape, '<f8', lambda index: float(sum(index)) + 0.25),
                 'probe.json': json.dumps({'format': 'probe_v1', 'members': [
                     {'ordinal': 0, 'frozen_reference': {'member_id': 'scene-7', 'split': 'validation'}}]}).encode(),
                 'pressure-diagnostic.json': json.dumps({'format': 'lab_pressure_diagnostic_v1',
                                                         'mean_free_relative_l2': 0.0}).encode(),
                 'field-index.json': json.dumps([{'cases': [case('pressure-prediction.npy', 'pressure-reference.npy',
                                                                 member_ordinal=0)]}]).encode()}
        for name, data in files.items():
            (sources / name).write_bytes(data)

        def declare(document):   # adoption takes the files a recipe declares
            document['run']['outputs'] = {name.split('.')[0].replace('-', '_'): {'path': name, 'role': 'results'}
                                          for name in files}
        self.edit('recipes/fit-a', declare)
        manifest = {'format': 'tuldok_adoption_v1',
                    'products': [{'reference': 'recipes/fit-a',
                                  'files': {name: str(sources / name) for name in files}}]}
        with self.opened() as project:
            done = adoption.adopt(project, adoption.make_plan(project, manifest, copy=True, replace=True))
        self.run_id = done['entries'][0]['run_id']
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, **arguments):
        result = self.service.call(name, arguments, OWNER)
        json.dumps(result, allow_nan=False)
        return result

    def test_the_two_operations_and_nothing_is_written(self):
        before = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        listed = self.call('fields', run=self.run_id)
        [found] = listed['cases']
        self.assertEqual((found['name'], found['split'], found['shape'], found['comparable']),
                         ('scene-7', 'validation', [4, 4, 4], True))
        self.assertEqual(listed['reported'], [{'file': 'pressure-diagnostic.json', 'field': 'mean_free_relative_l2',
                                               'value': 0.0}])
        got = self.call('field_compare', run=self.run_id[:8], entry=0, case=0, axis=0, index=[1, 0, 0],
                        mean_free=True)
        self.assertEqual((got['axes'], got['axis'], got['rows'], got['columns']), ([1, 2], 0, 4, 4))
        self.assertEqual(floats(got['error_f32']), [0.0] * 16)
        self.assertEqual((got['figures']['rmse'], got['figures']['mean_free_relative_l2']), (0.25, 0.0))
        refused = []
        for arguments in ({'entry': 0, 'case': 1}, {'entry': 0}, {'entry': 0, 'case': 0, 'axis': 4},
                          {'entry': 0, 'case': 0, 'index': [0] * 5}, {'entry': -1, 'case': 0}):
            with self.assertRaises(store.ProjectError) as caught:
                self.service.call('field_compare', {'run': self.run_id, **arguments}, OWNER)
            refused.append(caught.exception.code)
        self.assertEqual(refused, ['not-found', 'invalid', 'invalid', 'invalid', 'invalid'])
        after = sorted((path, path.stat().st_mtime_ns) for path in self.home.rglob('*') if path.is_file())
        self.assertEqual(before, after)
        with self.opened() as project:
            self.assertEqual(project._execute('SELECT count(*) FROM {schema}.activity').fetchone()[0], 0)


class Published(unittest.TestCase):

    def test_the_two_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in FIELDS:
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        from tuldok_project import service
        self.assertTrue(set(FIELDS) <= set(service.INSIDE_READS))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in FIELDS} <= folder)
        self.assertFalse({'project.' + name for name in FIELDS} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
