"""The nine task types of spec-t4.md section 1 and the sidecars of section 2 (slice T4a).

A valid value of each type checks and each rule broken once gives its
error; the checks against an image's size, a cloud's point count, an
array's shape and a sound's length; sidecar PNGs and .npy arrays read,
written and refused; runs that do not cover the image; a line file of each
type written and read back byte for byte with its key order; and, in a
folder (a copy of tests/fixtures/tuldok_project/minimal), the task fields,
a sidecar directory without its task, a missing sidecar and one no line
names. No database is used.
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import annotation_payloads as payloads, annotations  # noqa: E402
from tuldok_project.check import check_folder  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
AT = '2026-11-19T10:00:00Z'
TERMS = ['cell', 'car', 'a', 'b', 'c']
FIELDS = {'keypoints': ['head', 'tail'], 'skeleton': [['head', 'tail']], 'units': 'm', 'mask': 'instance'}

# One sound value per new type, with the record facts it is checked against.
VALUES = {
    'polygons': ([{'term': 'cell', 'points': [[1, 1], [10, 1], [10.5, 8], [1, 8]], 'confidence': 0.9}],
                 {'kind': 'image', 'size': (16, 12)}),
    'mask': ({'rle': [[0, 100], [1, 92]], 'classes': {'1': 'cell'}}, {'kind': 'image', 'size': (16, 12)}),
    'depth': ({'file': 'aaaaaaaaaaaaaaaa.npy', 'confidence': 0.5}, {'kind': 'image', 'size': (16, 12)}),
    'keypoints': ([{'term': 'car', 'points': [[2, 3, 2], None]}], {'kind': 'image', 'size': (16, 12)}),
    'ranking': (['b', 'a', 'c'], {'kind': 'text'}),
    'timeseries': ([{'term': 'a', 'start': 0, 'end': 4.5}], {'kind': 'array', 'shape': [10, 2]}),
    'track': ([{'track': 'car-1', 'term': 'car', 'frames': [{'frame': 0, 'x': 0, 'y': 0, 'w': 4, 'h': 4},
                                                             {'frame': 3, 'x': 2, 'y': 1, 'w': 4, 'h': 4}]}],
              {'kind': 'array', 'shape': [4, 8, 8]}),
    'points': ([{'term': 'car', 'indices': [0, 4, 9]}], {'kind': 'pointcloud', 'points': 10}),
    'box3d': ([{'term': 'car', 'center': [0, 0, 1], 'size': [4, 2, 1.5], 'yaw': 0.3}], {'kind': 'pointcloud'}),
}


def problems(task, value, facts=None, fields=FIELDS, state='accepted'):
    errors, unknown = annotations.value_problems(task, TERMS, state, value, fields=fields, **(facts or {}))
    return errors + [f'unknown {term}' for term in unknown]


class Values(unittest.TestCase):
    def test_a_sound_value_of_each_type_checks(self):
        for task, (value, facts) in VALUES.items():
            with self.subTest(task):
                self.assertIn(task, annotations.TASKS)
                self.assertEqual(problems(task, value, facts), [])
                self.assertEqual(annotations.record_kinds(task)[:1] != (), True)
                self.assertIn(facts['kind'], annotations.record_kinds(task))

    def test_each_rule_broken_once(self):
        size = {'size': (16, 12)}
        cases = [
            ('polygons', [{'term': 'cell', 'points': [[1, 1], [2, 2]]}], size, '3 to'),
            ('polygons', [{'term': 'cell', 'points': [[1, 1], [2, 2], [17, 2]]}], size, 'outside the image'),
            ('polygons', [{'term': 'cell', 'points': [[1, 1], [2, 2], [3, 2]], 'confidence': 2}], size, 'confidence'),
            ('polygons', [{'term': 'nope', 'points': [[1, 1], [2, 2], [3, 2]]}], size, 'unknown nope'),
            ('polygons', [{'term': 'cell', 'pts': []}], size, 'unknown key'),
            ('mask', {'classes': {'1': 'cell'}}, size, 'either file or rle'),
            ('mask', {'rle': [[0, 0]], 'classes': {'1': 'cell'}}, size, 'count above zero'),
            ('mask', {'rle': [[0, 1]], 'classes': {'0': 'cell'}}, size, 'numbers 1 to 65535'),
            ('mask', {'file': '../x.png', 'classes': {'1': 'cell'}}, size, 'relative path'),
            ('mask', {'file': 'x.npy', 'classes': {'1': 'cell'}}, size, 'not a .png'),
            ('depth', {'file': 'x.png'}, size, 'not a .npy'),
            ('depth', [], size, 'must be an object'),
            ('keypoints', [{'term': 'car', 'points': [[1, 1]]}], size, 'one point per keypoint of the task (2)'),
            ('keypoints', [{'term': 'car', 'points': [[1, 1, 3], None]}], size, 'visibility'),
            ('keypoints', [{'term': 'car', 'points': [[1, 20], None]}], size, 'outside the image'),
            ('ranking', ['a', 'a'], {}, 'more than once'),
            ('ranking', [], {}, 'one or more terms'),
            ('timeseries', [{'term': 'a', 'start': 3, 'end': 3}], {}, 'start < end'),
            ('timeseries', [{'term': 'a', 'start': 0, 'end': 11}], {'shape': [10]}, 'past the 10 positions'),
            ('timeseries', [{'term': 'a', 'start': 0, 'end': 2}], {'duration': 1.5}, 'past the sound'),
            ('track', [{'track': 'x', 'term': 'car', 'frames': [{'frame': 1, 'x': 0, 'y': 0, 'w': 1, 'h': 1},
                                                                 {'frame': 1, 'x': 0, 'y': 0, 'w': 1, 'h': 1}]}],
             {}, 'above the one before'),
            ('track', [{'track': 'x', 'term': 'car', 'frames': [{'frame': 5, 'x': 0, 'y': 0, 'w': 1, 'h': 1}]}],
             {'shape': [4, 8, 8]}, 'past the 4 frames'),
            ('track', [{'track': 'x', 'term': 'car', 'frames': [{'frame': 0, 'x': 6, 'y': 0, 'w': 3, 'h': 1}]}],
             {'shape': [4, 8, 8]}, 'outside the frame'),
            ('track', [{'track': 'x', 'term': 'car', 'frames': [{'frame': 0, 'x': 0, 'y': 0, 'w': 1, 'h': 1}]},
                       {'track': 'x', 'term': 'car', 'frames': [{'frame': 0, 'x': 0, 'y': 0, 'w': 1, 'h': 1}]}],
             {}, 'repeats the track id'),
            ('points', [{'term': 'car', 'indices': [3, 2]}], {}, 'from 0 upward'),
            ('points', [{'term': 'car', 'indices': [1, 10]}], {'points': 10}, 'the cloud has 10 points'),
            ('points', {'file': 'ids.npy'}, {}, 'lacks classes'),
            ('box3d', [{'term': 'car', 'center': [0, 0, 0], 'size': [1, 0, 1], 'yaw': 0}], {}, 'above zero'),
            ('box3d', [{'term': 'car', 'center': [0, 0], 'size': [1, 1, 1], 'yaw': 0}], {}, 'center [x, y, z]'),
        ]
        for task, value, facts, expected in cases:
            with self.subTest(task=task, expected=expected):
                found = problems(task, value, facts)
                self.assertEqual(len(found), 1, found)
                self.assertIn(expected, found[0])
                self.assertNotIn('label', found[0].lower())

    def test_kinds_of_record(self):
        self.assertEqual(problems('polygons', VALUES['polygons'][0], {'kind': 'text'}),
                         ['A polygons task does not annotate records of kind \'text\'; it takes image.'])
        self.assertEqual(annotations.record_kinds('timeseries'), ('audio', 'array'))
        self.assertEqual(annotations.record_kinds('ranking'), annotations.record_kinds('class'))

    def test_null_values_and_confidence_on_old_types(self):
        self.assertEqual(problems('mask', None, state='draft'), [])
        self.assertEqual(len(problems('mask', None)), 1)
        self.assertEqual(problems('boxes', [{'term': 'cell', 'x': 0, 'y': 0, 'w': 1, 'h': 1, 'confidence': 1}]), [])
        self.assertIn('confidence', problems('boxes', [{'term': 'cell', 'x': 0, 'y': 0, 'w': 1, 'h': 1,
                                                        'confidence': -0.1}])[0])

    def test_sidecars_named(self):
        self.assertEqual(annotations.sidecars('mask', {'file': 'm.png', 'classes': {}}), ['m.png'])
        self.assertEqual(annotations.sidecars('mask', {'rle': [], 'classes': {}}), [])
        self.assertEqual(annotations.sidecars('points', [{'term': 'a', 'indices': [1]}]), [])
        self.assertEqual(annotations.sidecars('polygons', VALUES['polygons'][0]), [])


class Lines(unittest.TestCase):
    def test_each_type_round_trips_byte_for_byte_in_its_key_order(self):
        for task, (value, _facts) in VALUES.items():
            with self.subTest(task):
                shuffled = json.loads(json.dumps(value))
                if isinstance(shuffled, list) and shuffled and isinstance(shuffled[0], dict):
                    shuffled = [dict(reversed(list(item.items()))) for item in shuffled]
                elif isinstance(shuffled, dict):
                    shuffled = dict(reversed(list(shuffled.items())))
                rows = [{'record': 'r2', 'sha256': None, 'state': 'accepted', 'value': shuffled, 'by': 'owner',
                         'at': AT}, {'record': 'r1', 'sha256': None, 'state': 'draft', 'value': value,
                                     'by': 'agent:helper', 'at': AT}]
                data = annotations.write(rows)
                parsed = annotations.read(data, task, TERMS, FIELDS)
                self.assertEqual([p.message for p in parsed.problems], [])
                self.assertEqual(annotations.write([row for _, row in parsed.rows]), data)
                self.assertEqual(parsed.rows[0][1]['value'], parsed.rows[1][1]['value'])

    def test_written_key_orders(self):
        line = annotations.encode({'record': 'r', 'sha256': None, 'state': 'accepted', 'by': 'owner', 'at': AT,
                                   'value': [{'frames': [{'h': 1, 'w': 1, 'y': 0, 'x': 0, 'frame': 2}],
                                              'term': 'car', 'confidence': 0.5, 'track': 't'}]})
        self.assertIn('"value":[{"track":"t","term":"car","frames":[{"frame":2,"x":0,"y":0,"w":1,"h":1}],'
                      '"confidence":0.5}]', line)
        line = annotations.encode({'record': 'r', 'sha256': None, 'state': 'accepted', 'by': 'owner', 'at': AT,
                                   'value': {'confidence': 1, 'classes': {'12': 'b', '3': 'a'}, 'file': 'f.png'}})
        self.assertIn('"value":{"file":"f.png","classes":{"3":"a","12":"b"},"confidence":1}', line)


class Payloads(unittest.TestCase):
    def test_png_round_trip_8_and_16_bit(self):
        for values in ([0, 1, 2, 255] * 6, [0, 300, 65535, 7] * 6):
            data = payloads.write_png(4, 6, values)
            self.assertEqual(payloads.png_size(data)[:2], (4, 6))
            width, height, read = payloads.read_png(data)
            self.assertEqual((width, height, list(read)), (4, 6, values))

    def test_png_with_row_filters(self):
        import struct
        import zlib
        # Rows with each filter, worked out by hand: Sub, Up, Average and Paeth of a 3-pixel greyscale image.
        rows = bytes([1, 10, 5, 5]) + bytes([2, 1, 1, 1]) + bytes([3, 2, 2, 2]) + bytes([4, 1, 0, 0])
        def chunk(kind, body):
            return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body))
        data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 3, 4, 8, 0, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
        _, _, values = payloads.read_png(data)
        # Sub: 10, 15, 20. Up: 11, 16, 21. Average: 2 + (0 + 11) // 2 = 7, 2 + (7 + 16) // 2 = 13,
        # 2 + (13 + 21) // 2 = 19. Paeth: 1 + up (7) = 8; then left 8 vs up 13, corner 7: p = 14 -> up 13; 13 vs 19, 13: 19.
        self.assertEqual(list(values), [10, 15, 20, 11, 16, 21, 7, 13, 19, 8, 13, 19])

    def test_png_refusals(self):
        with self.assertRaises(payloads.PayloadError):
            payloads.read_png(b'not a png at all, not at all, not at all')
        rgb = payloads.write_png(2, 2, [0, 0, 0, 0]).replace(b'IHDR' + (2).to_bytes(4, 'big') * 2 + b'\x08\x00',
                                                              b'IHDR' + (2).to_bytes(4, 'big') * 2 + b'\x08\x02')
        with self.assertRaises(payloads.PayloadError):
            payloads.read_png(rgb)

    def test_runs(self):
        values = [0, 0, 1, 1, 1, 0, 2]
        runs = payloads.encode_runs(values)
        self.assertEqual(runs, [[0, 2], [1, 3], [0, 1], [2, 1]])
        self.assertEqual(list(payloads.decode_runs(runs, 7, 1)), values)
        with self.assertRaises(payloads.PayloadError):
            payloads.decode_runs(runs, 4, 2)

    def test_npy(self):
        data = payloads.write_npy([2, 3], [0.5, 1, 2, 3, 4, 5.25], '<f4')
        shape, kind, values = payloads.read_npy(data)
        self.assertEqual((shape, kind, list(values)), ([2, 3], 'f', [0.5, 1, 2, 3, 4, 5.25]))
        data = payloads.write_npy([4], [0, 1, 1, 2], '<i4')
        self.assertEqual(payloads.read_npy(data)[0], [4])
        with self.assertRaises(payloads.PayloadError):
            payloads.read_npy(data, most=3)
        with self.assertRaises(payloads.PayloadError):
            payloads.read_npy(data.replace(b"'<i4'", b"'|O8'"))
        with self.assertRaises(payloads.PayloadError):
            payloads.read_npy(data[:-4])

    def test_kept_names(self):
        name = payloads.kept_name(b'abc', '.png')
        self.assertTrue(payloads.is_kept_name(name))
        self.assertEqual(name, 'ba7816bf8f01cfea.png')
        self.assertFalse(payloads.is_kept_name('ba7816bf8f01cfea.jpg'))
        self.assertFalse(payloads.is_kept_name('mask.png'))


class Folder(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name) / 'minimal'
        shutil.copytree(FIXTURE, base)
        self.folder = base / 'project'

    def task(self, name, **fields):
        document = {'format': 'tuldok_definition_v1', 'kind': 'annotation', 'title': 'T', 'dataset': 'datasets/waves'}
        document.update(fields)
        (self.folder / f'annotations/{name}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')

    def problems(self):
        return [(p.severity, p.path, p.pointer, p.message) for p in check_folder(self.folder).problems]

    def test_task_fields(self):
        self.task('keys', task='keypoints', vocabulary=['car'], keypoints=['head', 'tail'], skeleton=[['head', 'tail']])
        self.task('depths', task='depth', units='m')
        self.task('masks', task='mask', vocabulary=['cell'], mask='instance')
        self.assertEqual(self.problems(), [])
        self.task('keys', task='keypoints', vocabulary=['car'], keypoints=['head'], skeleton=[['head', 'wing']])
        found = self.problems()
        self.assertEqual([(s, p, q) for s, p, q, _ in found], [('error', 'annotations/keys.json', '/skeleton/0')])
        self.task('keys', task='keypoints', vocabulary=['car'])
        self.task('depths', task='depth', units='m', vocabulary=['x'])
        self.task('masks', task='mask', vocabulary=['cell'], units='m')
        found = sorted((p, q) for _s, p, q, _m in self.problems())
        self.assertEqual([p for p, _ in found], ['annotations/depths.json', 'annotations/keys.json',
                                                 'annotations/masks.json'])

    def test_sidecars_in_the_folder(self):
        mask = payloads.write_png(2, 2, [0, 1, 1, 0])
        name = payloads.kept_name(mask, '.png')
        self.task('masks', task='mask', vocabulary=['cell'])
        (self.folder / 'annotations/masks').mkdir()
        (self.folder / 'annotations/masks' / name).write_bytes(mask)
        row = {'record': 'r1', 'sha256': None, 'state': 'accepted', 'value': {'file': name, 'classes': {'1': 'cell'}},
               'by': 'owner', 'at': AT}
        (self.folder / 'annotations/masks.jsonl').write_bytes(annotations.write([row]))
        self.assertEqual(self.problems(), [])
        # A sidecar no line names is a warning; one a line names and that is not there, an error.
        other = payloads.write_png(2, 2, [1, 1, 1, 1])
        (self.folder / 'annotations/masks' / payloads.kept_name(other, '.png')).write_bytes(other)
        self.assertEqual([(s, p) for s, p, _q, _m in self.problems()], [('warning', 'annotations/masks')])
        (self.folder / 'annotations/masks' / name).unlink()
        found = self.problems()
        self.assertIn(('error', 'annotations/masks.jsonl', 'line 1'), [(s, p, q) for s, p, q, _m in found])
        # A file not named by its content, and a directory with no task.
        (self.folder / 'annotations/masks' / 'mine.png').write_bytes(mask)
        (self.folder / 'annotations/stray').mkdir()
        found = [(s, p) for s, p, _q, _m in self.problems()]
        self.assertIn(('error', 'annotations/masks/mine.png'), found)
        self.assertIn(('error', 'annotations/stray'), found)
        for _s, _p, _q, message in self.problems():
            self.assertTrue(message.endswith('.'), message)


if __name__ == '__main__':
    unittest.main()
