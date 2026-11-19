"""Agreement between annotation sets (spec-t4.md section 5, slice T4c) and the four operations (section 6, T4d).

The measures are checked against arithmetic done here, on hand-made values:
kappas on a known table, Kendall's tau, interval IoU, box, polygon, mask
(instance and semantic), point-set and rotated 3-D box IoU, OKS, track
switches and fragments, the Hungarian matching against brute force, the
confidence filter and the order of the disputed list. The operations are
then asked of a Service on the stand-in segmentors' sets of
test_tuldok_project_annotate_step (database only).
"""
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import annotation_agreement as agree, annotation_payloads as payloads  # noqa: E402
from tuldok_project import builds, check, environments, local, plan, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402


def entry(value, confidence=None):
    found = {'value': value}
    if confidence is not None:
        found['confidence'] = confidence
    return found


class Measures(unittest.TestCase):
    def test_cohen_kappa_on_a_known_table(self):
        # 50 records: both yes 20, a yes b no 5, a no b yes 10, both no 15.
        pairs = [('yes', 'yes')] * 20 + [('yes', 'no')] * 5 + [('no', 'yes')] * 10 + [('no', 'no')] * 15
        observed = 35 / 50
        expected = (25 / 50) * (30 / 50) + (25 / 50) * (20 / 50)
        self.assertAlmostEqual(agree.cohen_kappa(pairs), (observed - expected) / (1 - expected))
        self.assertAlmostEqual(agree.cohen_kappa(pairs), 0.4)
        self.assertEqual(agree.cohen_kappa([('a', 'a')] * 3), 1.0)
        self.assertIsNone(agree.cohen_kappa([]))

    def test_fleiss_kappa(self):
        # Three raters, four records: (a,a,a), (a,a,b), (b,b,b), (a,b,b).
        rows = [['a', 'a', 'a'], ['a', 'a', 'b'], ['b', 'b', 'b'], ['a', 'b', 'b']]
        per_record = [(9 - 3) / 6, (4 + 1 - 3) / 6, (9 - 3) / 6, (1 + 4 - 3) / 6]
        observed = sum(per_record) / 4
        share_a, share_b = 6 / 12, 6 / 12
        expected = share_a ** 2 + share_b ** 2
        self.assertAlmostEqual(agree.fleiss_kappa(rows), (observed - expected) / (1 - expected))

    def test_kendall_tau(self):
        self.assertEqual(agree.kendall_tau(['a', 'b', 'c'], ['a', 'b', 'c']), 1.0)
        self.assertEqual(agree.kendall_tau(['a', 'b', 'c'], ['c', 'b', 'a']), -1.0)
        # a b c d against b a c d: one discordant pair of six.
        self.assertAlmostEqual(agree.kendall_tau(list('abcd'), list('bacd')), (5 - 1) / 6)
        self.assertEqual(agree.kendall_tau(['a', 'x'], ['a', 'y']), 1.0)   # one shared
        score, figures = agree.compare({'task': 'ranking'}, list('abcd'), list('bacd'))
        self.assertAlmostEqual(score, (4 / 6 + 1) / 2)

    def test_interval_iou(self):
        # [0,4] against [2,6]: 2 over 6. Merged unions: [0,1]+[1,3] is [0,3].
        self.assertAlmostEqual(agree.interval_iou([(0, 4)], [(2, 6)]), 2 / 6)
        self.assertAlmostEqual(agree.interval_iou([(0, 1), (1, 3)], [(0, 3)]), 1.0)
        a = [{'term': 'x', 'start': 0, 'end': 4}, {'term': 'y', 'start': 0, 'end': 2}]
        b = [{'term': 'x', 'start': 2, 'end': 6}]
        self.assertAlmostEqual(agree.compare({'task': 'timeseries'}, a, b)[0], (2 / 6 + 0) / 2)

    def test_boxes_and_matching(self):
        self.assertAlmostEqual(agree.box_iou((0, 0, 4, 4), (2, 0, 4, 4)), 8 / 24)
        a = [{'term': 'c', 'x': 0, 'y': 0, 'w': 4, 'h': 4}, {'term': 'c', 'x': 10, 'y': 10, 'w': 2, 'h': 2}]
        b = [{'term': 'c', 'x': 10, 'y': 10, 'w': 2, 'h': 2}, {'term': 'c', 'x': 2, 'y': 0, 'w': 4, 'h': 4},
             {'term': 'd', 'x': 0, 'y': 0, 'w': 4, 'h': 4}]
        score, figures = agree.compare({'task': 'boxes'}, a, b)
        self.assertAlmostEqual(score, (1 + 8 / 24) / 3)
        self.assertEqual(figures['matches'], 2)
        self.assertAlmostEqual(figures['mean_iou'], (1 + 8 / 24) / 2)
        self.assertAlmostEqual(figures['f1'], 2 * 1 / 5)
        self.assertEqual(agree.compare({'task': 'boxes'}, [], []), (1.0, {'matches': 0, 'mean_iou': None, 'f1': 1.0}))

    def test_hungarian_against_brute_force(self):
        rng = random.Random(4)
        for rows, columns in ((3, 3), (2, 5), (5, 2), (6, 6)):
            table = [[rng.random() for _ in range(columns)] for _ in range(rows)]
            chosen = agree.hungarian(table)
            best = max((sum(table[r][c] for r, c in zip(order, perm)) for order in [range(rows)]
                        for perm in itertools.permutations(range(columns), rows)) if rows <= columns else
                       (sum(table[r][c] for r, c in zip(perm, range(columns)))
                        for perm in itertools.permutations(range(rows), columns)))
            self.assertAlmostEqual(sum(table[r][c] for r, c in chosen), best)
            self.assertEqual(len(chosen), min(rows, columns))

    def test_polygon_iou(self):
        # A 10 by 10 square and a 5 by 10 half of it: 50 of 100 pixel centres.
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        half = [(0, 0), (5, 0), (5, 10), (0, 10)]
        self.assertAlmostEqual(agree.polygon_iou(square, half), 0.5)
        # A triangle covering half the square: on the grid, the centres under the diagonal (45 of 100 strictly).
        triangle = [(0, 0), (10, 0), (0, 10)]
        under = sum(1 for x in range(10) for y in range(10) if x + 0.5 + y + 0.5 < 10)
        self.assertAlmostEqual(agree.polygon_iou(square, triangle), under / 100)
        # Large polygons are drawn on at most GRID cells a side.
        big = [(0, 0), (1000, 0), (1000, 1000), (0, 1000)]
        self.assertAlmostEqual(agree.polygon_iou(big, [(0, 0), (500, 0), (500, 1000), (0, 1000)]), 0.5)

    def test_box3d_iou(self):
        unit = ([0, 0, 0], [2, 2, 2], 0.0)
        self.assertAlmostEqual(agree.box3d_iou(unit, unit), 1.0)
        shifted = ([1, 0, 0], [2, 2, 2], 0.0)
        self.assertAlmostEqual(agree.box3d_iou(unit, shifted), 4 / 12)
        # Turned by 45 degrees: a 2 by 2 square and its turned copy overlap in a regular octagon.
        side = 2 * (math.sqrt(2) - 1)
        octagon = 2 * (1 + math.sqrt(2)) * side ** 2
        turned = ([0, 0, 0], [2, 2, 2], math.pi / 4)
        self.assertAlmostEqual(agree.box3d_iou(unit, turned), octagon * 2 / (16 - octagon * 2))
        # Half the height overlapping.
        self.assertAlmostEqual(agree.box3d_iou(unit, ([0, 0, 1], [2, 2, 2], 0.0)), 4 / 12)

    def test_point_sets_and_files(self):
        a = [{'term': 'car', 'indices': [0, 1, 2, 3]}]
        b = [{'term': 'car', 'indices': [2, 3, 4]}]
        self.assertAlmostEqual(agree.compare({'task': 'points'}, a, b)[0], 2 / 5)
        ids = payloads.write_npy([6], [0, 0, 1, 1, 1, 0], '<i4')
        value = {'file': 'ids.npy', 'classes': {'1': 'car'}}
        score, _ = agree.compare({'task': 'points'}, a, value, None, lambda name: ids)
        self.assertAlmostEqual(score, 2 / 5)   # {0,1,2,3} against {2,3,4}

    def test_masks(self):
        # Two 4 by 2 instance masks: a has objects 1 (3 px) and 2 (2 px); b has 1 (2 px of a's 1) and 5 (b's 2's px).
        a = {'rle': [[1, 3], [0, 1], [2, 2], [0, 2]], 'classes': {'1': 'cell', '2': 'cell'}}
        b = {'rle': [[1, 2], [0, 2], [5, 2], [0, 2]], 'classes': {'1': 'cell', '5': 'cell'}}
        score, figures = agree.compare({'task': 'mask', 'mask': 'instance'}, a, b)
        self.assertAlmostEqual(score, (2 / 3 + 1) / 2)
        self.assertEqual(figures['matches'], 2)
        # The same pixels as a semantic mask: cell is 5 pixels in a, 4 in b, 4 together.
        score, figures = agree.compare({'task': 'mask'}, a, b)
        self.assertAlmostEqual(score, 4 / 5)
        # From a PNG sidecar against runs.
        png = payloads.write_png(4, 2, [1, 1, 1, 0, 2, 2, 0, 0])
        score, _ = agree.compare({'task': 'mask', 'mask': 'instance'}, {'file': 'm.png', 'classes': a['classes']},
                                 a, lambda name: png)
        self.assertEqual(score, 1.0)
        with self.assertRaises(agree.AgreementProblem):
            agree.compare({'task': 'mask'}, a, {'rle': [[0, 9]], 'classes': {'1': 'cell'}})

    def test_depth(self):
        first = payloads.write_npy([1, 4], [1.0, 2.0, 0.0, 4.0], '<f4')
        second = payloads.write_npy([1, 4], [1.0, 3.0, 5.0, 4.0], '<f4')
        score, figures = agree.compare({'task': 'depth'}, {'file': 'a.npy'}, {'file': 'b.npy'},
                                       lambda n: first, lambda n: second)
        # Pixels with depth in both: 1/1, 2/3, 4/4. Mean |a-b| 1/3; mean (|a|+|b|)/2 = (1 + 2.5 + 4) / 3.
        self.assertAlmostEqual(figures['mean_abs'], 1 / 3)
        self.assertAlmostEqual(score, 1 - (1 / 3) / (7.5 / 3))
        self.assertAlmostEqual(figures['delta'], 2 / 3)   # 3/2 is not below 1.25

    def test_keypoints_oks(self):
        a = [[0, 0, 2], [10, 0, 2], [10, 10, 2]]
        b = [[0, 0, 2], [10, 0, 2], [10, 13, 1]]
        # Areas: a 10 x 10 = 100, b 10 x 13 = 130; s² = 115; one point off by 3.
        expected = (1 + 1 + math.exp(-9 / (2 * 115 * 0.01))) / 3
        self.assertAlmostEqual(agree.oks(a, b), expected)
        self.assertAlmostEqual(agree.oks(a, [[0, 0, 2], None, [10, 10, 0]]), 1 / 3)
        score, figures = agree.compare({'task': 'keypoints'}, [{'term': 'p', 'points': a}],
                                       [{'term': 'p', 'points': b}])
        self.assertAlmostEqual(score, expected)
        self.assertAlmostEqual(figures['mean_oks'], expected)

    def test_tracks(self):
        def track(identifier, frames, x=0):
            return {'track': identifier, 'term': 'car',
                    'frames': [{'frame': f, 'x': x, 'y': 0, 'w': 4, 'h': 4} for f in frames]}
        a = [track('1', [0, 1, 2, 3])]
        # b follows a's object as two tracks (a switch at frame 2) with a gap in the first (a fragment).
        b = [track('x', [0, 1]), track('y', [2, 3])]
        score, figures = agree.compare({'task': 'track'}, a, b)
        self.assertEqual(figures['switches'], 1)
        self.assertEqual(figures['fragments'], [0, 0])
        self.assertAlmostEqual(score, (2 / 4) / 2)   # 1's match covers half its frames; the larger count is 2
        gappy = [track('1', [0, 1, 3, 6])]
        self.assertEqual(agree.fragments(agree._tracks(gappy)), 2)

    def test_text_and_tags(self):
        self.assertAlmostEqual(agree.compare({'task': 'tags'}, ['a', 'b'], ['b', 'c'])[0], 1 / 3)
        self.assertEqual(agree.compare({'task': 'tags'}, [], [])[0], 1.0)
        self.assertEqual(agree.compare({'task': 'text'}, 'abcd', 'abcd'), (1.0, {'exact': True}))
        self.assertAlmostEqual(agree.compare({'task': 'text'}, 'abcd', 'abxd')[0], 2 * 3 / 8)


class Sets(unittest.TestCase):
    def test_the_disputed_list_and_its_order(self):
        sets = {'kept': {'r1': entry('a'), 'r2': entry('a'), 'r3': entry('b')},
                'datasets/x': {'r1': entry('a'), 'r2': entry('b'), 'r3': entry('b'), 'r4': entry('a')},
                'datasets/y': {'r1': entry('a'), 'r2': entry('b'), 'r3': entry('a'), 'r4': entry('a')}}
        found = agree.agreement({'task': 'class'}, sets)
        rows = {row['record']: row for row in found['disputed']}
        # r4: kept lacks it, so kept-x and kept-y score 0, x-y 1: disagreement 1 - 1/3.
        self.assertAlmostEqual(rows['r4']['disagreement'], 2 / 3)
        self.assertEqual(rows['r4']['missing'], ['kept'])
        # r2: a, b, b -> pairs 0, 0, 1; r3: b, b, a -> 1, 0, 0; both 2/3; r1 0.
        self.assertEqual([row['record'] for row in found['disputed']], ['r2', 'r3', 'r4', 'r1'])
        pairs = {(p['a'], p['b']): p for p in found['pairs']}
        self.assertEqual(pairs[('kept', 'datasets/x')]['records'], 4)
        self.assertAlmostEqual(pairs[('kept', 'datasets/x')]['agreement'], 2 / 4)
        # Cohen's kappa over the records both annotated (r1 a-a, r2 a-b, r3 b-b).
        self.assertAlmostEqual(pairs[('kept', 'datasets/x')]['kappa'],
                               agree.cohen_kappa([('a', 'a'), ('a', 'b'), ('b', 'b')]))
        self.assertAlmostEqual(found['fleiss'], agree.fleiss_kappa([['a', 'a', 'a'], ['a', 'b', 'b'],
                                                                    ['b', 'b', 'a']]))
        page = agree.agreement({'task': 'class'}, sets, offset=1, limit=2)
        self.assertEqual([row['record'] for row in page['disputed']], ['r3', 'r4'])
        self.assertEqual(page['total'], 4)

    def test_the_confidence_filter(self):
        a = {'r1': entry([{'term': 'c', 'x': 0, 'y': 0, 'w': 2, 'h': 2, 'confidence': 0.9},
                          {'term': 'c', 'x': 5, 'y': 5, 'w': 2, 'h': 2, 'confidence': 0.2}]),
             'r2': entry([{'term': 'c', 'x': 0, 'y': 0, 'w': 2, 'h': 2}], confidence=0.1)}
        b = {'r1': entry([{'term': 'c', 'x': 0, 'y': 0, 'w': 2, 'h': 2}]),
             'r2': entry([{'term': 'c', 'x': 0, 'y': 0, 'w': 2, 'h': 2}])}
        loose = agree.agreement({'task': 'boxes'}, {'a': a, 'b': b})
        strict = agree.agreement({'task': 'boxes'}, {'a': a, 'b': b}, min_confidence=0.5)
        self.assertAlmostEqual(loose['pairs'][0]['agreement'], (0.5 + 1) / 2)
        # r1 loses its low box (agreement 1); r2's whole line is under the filter: missing in a, so 0.
        self.assertAlmostEqual(strict['pairs'][0]['agreement'], (1 + 0) / 2)
        self.assertEqual(strict['disputed'][0]['missing'], ['a'])

    def test_refusals(self):
        with self.assertRaises(agree.AgreementProblem):
            agree.agreement({'task': 'review'}, {'a': {}, 'b': {}})
        with self.assertRaises(agree.AgreementProblem):
            agree.agreement({'task': 'class'}, {'a': {}})


DATABASE = os.environ.get('TULDOK_DATABASE_URL')
OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner',
         'scopes': ['approve-execution', 'cancel', 'edit', 'execute', 'inspect']}
READER = {'actor_id': 'agent-2', 'kind': 'agent', 'label': 'reader', 'scopes': ['inspect']}


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Operations(unittest.TestCase):
    """annotation_sets, annotation_agreement, annotation_compare and keep_annotation on the stand-ins' sets."""

    @classmethod
    def setUpClass(cls):
        import test_tuldok_project_annotate_step as stand_ins
        cls.stand_ins = stand_ins
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.temporary = Path(directory.name)
        cls.root = cls.temporary / 'repository'
        cls.root.mkdir()
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(cls.temporary / 'home'),
                                               local.SETTINGS_VARIABLE: str(cls.temporary / 'settings.json')})
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.addClassCleanup(stand_ins._writable, cls.temporary / 'home')
        cls.project_id = uuid.uuid4().hex
        cls.folder = stand_ins.make_project(cls.root, cls.project_id)
        for arguments in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'The project.']):
            subprocess.run([*stand_ins.GIT, '-C', str(cls.root), *arguments], check=True)
        cls.addClassCleanup(store.drop_project, cls.project_id)
        with store.open_project(cls.folder) as project:
            environments.connect(project, 'environments/test-python', sys.executable)
            made = plan.build_plan(project, ['datasets/masks-a', 'datasets/masks-b', 'datasets/objects-a',
                                             'datasets/objects-b', 'datasets/shapes-a', 'datasets/shapes-b'])
        done = builds.execute(cls.folder, made, confirm=lambda given: True)
        assert done['ok'], done
        cls.service = Service(cls.folder)
        cls.addClassCleanup(cls.service.close)

    def call(self, name, arguments, actor=OWNER):
        return self.service.call(name, arguments, actor)

    def refused(self, name, arguments, actor=OWNER):
        with self.assertRaises(ProjectError) as raised:
            self.call(name, arguments, actor)
        return raised.exception

    def test_a_sets(self):
        found = self.call('annotation_sets', {'task': 'masks'}, READER)
        self.assertEqual(found['type'], 'mask')
        self.assertEqual([(s['set'], s['annotated']) for s in found['sets']],
                         [('kept', 0), ('datasets/masks-a', 4), ('datasets/masks-b', 4)])
        self.assertEqual(found['sets'][1]['by']['name'], 'segment-a')

    def test_b_agreement_against_the_arithmetic(self):
        found = self.call('annotation_agreement', {'task': 'masks', 'sets': ['datasets/masks-a', 'datasets/masks-b']},
                          READER)
        rows = {row['record']: row['disagreement'] for row in found['disputed']}
        # a.png: red 30 of 56 pixels, blue 49 of 81, both matched; d.png: no object in either: 1.
        self.assertAlmostEqual(1 - rows['images__a.png'], (30 / 56 + 49 / 81) / 2)
        self.assertAlmostEqual(rows['images__d.png'], 0.0)
        # b.png: one red 10 x 8 against 12 x 10. c.png: the stand-in gives one id per colour, so its two blue
        # rectangles are one object: 4 x 4 + 5 x 9 against 6 x 6 + 7 x 11.
        self.assertAlmostEqual(1 - rows['images__b.png'], 80 / 120)
        self.assertAlmostEqual(1 - rows['images__c.png'], (16 + 45) / (36 + 77))
        self.assertEqual([row['record'] for row in found['disputed']],
                         sorted(rows, key=lambda record: (-rows[record], record)))
        pair = found['pairs'][0]
        self.assertAlmostEqual(pair['agreement'], sum(1 - value for value in rows.values()) / 4)
        objects = self.call('annotation_agreement', {'task': 'objects'}, READER)
        self.assertEqual([p['a'] + ' ' + p['b'] for p in objects['pairs']],
                         ['kept datasets/objects-a', 'kept datasets/objects-b', 'datasets/objects-a datasets/objects-b'])
        rows = {row['record']: row for row in objects['disputed']}
        self.assertAlmostEqual(rows['clouds__p.ply']['pairs']['datasets/objects-a|datasets/objects-b'], 9 / 10)
        self.assertEqual(rows['clouds__p.ply']['missing'], ['kept'])
        # The confidence filter: the shapes' polygons carry 0.9 (red) and 0.8 (blue).
        strict = self.call('annotation_agreement', {'task': 'shapes', 'sets': ['datasets/shapes-a', 'datasets/shapes-b'],
                                                    'min_confidence': 0.85}, READER)
        loose = self.call('annotation_agreement', {'task': 'shapes', 'sets': ['datasets/shapes-a', 'datasets/shapes-b']},
                          READER)
        self.assertNotEqual(strict['pairs'][0]['agreement'], loose['pairs'][0]['agreement'])

    def test_c_compare(self):
        found = self.call('annotation_compare', {'task': 'masks', 'record': 'images__a.png',
                                                 'sets': ['datasets/masks-a', 'datasets/masks-b']}, READER)
        self.assertEqual(found['size'], [24, 16])
        drawn = found['sets'][0]['drawn']
        self.assertEqual((drawn['width'], drawn['height']), (24, 16))
        self.assertEqual(sum(n for v, n in drawn['runs'] if v == 1), 30)
        self.assertAlmostEqual(found['pairs'][0]['agreement'], (30 / 56 + 49 / 81) / 2)
        refused = self.refused('annotation_compare', {'task': 'masks', 'record': 'images__a.png',
                                                      'sets': ['datasets/nobody']}, READER)
        self.assertEqual(refused.code, 'not-found')

    def test_d_keep_and_save(self):
        self.assertEqual(self.refused('keep_annotation', {'task': 'masks', 'record': 'images__a.png', 'keep': 'one',
                                                          'sets': ['datasets/masks-a']}, READER).code, 'forbidden')
        self.assertEqual(self.refused('keep_annotation', {'task': 'masks', 'record': 'images__a.png', 'keep': 'both',
                                                          'sets': ['datasets/masks-a', 'datasets/masks-b']}).code,
                         'invalid')   # a mask is not a list
        kept = self.call('keep_annotation', {'task': 'masks', 'record': 'images__a.png', 'keep': 'one',
                                             'sets': ['datasets/masks-b'], 'note': 'the wider one'})
        self.assertEqual((kept['state'], kept['unsaved']), ('accepted', 1))
        line = self.call('annotation', {'task': 'masks', 'record': 'images__a.png'})['annotation']
        self.assertEqual(line['from']['set'], 'datasets/masks-b')
        self.assertEqual(line['from']['by']['name'], 'segment-b')
        self.assertTrue(payloads.is_kept_name(line['value']['file']))
        # The kept set now agrees with b on a.png, and its sidecar is read from the working copy.
        found = self.call('annotation_compare', {'task': 'masks', 'record': 'images__a.png',
                                                 'sets': ['kept', 'datasets/masks-b']})
        self.assertEqual(found['pairs'][0]['agreement'], 1.0)
        self.call('keep_annotation', {'task': 'masks', 'record': 'images__b.png', 'keep': 'none',
                                      'sets': ['datasets/masks-a', 'datasets/masks-b']})
        saved = self.call('save', {})
        self.assertIn('annotations/masks.jsonl', saved['annotations_written'])
        sidecar = self.folder / 'annotations' / 'masks' / line['value']['file']
        self.assertTrue(sidecar.is_file())
        written = (self.folder / 'annotations' / 'masks.jsonl').read_text().splitlines()
        self.assertEqual([json.loads(text)['state'] for text in written], ['accepted', 'rejected'])
        self.assertEqual(check.check_folder(self.folder).problems, [])
        # Both polygon sets kept together, then the mask replaced by a's: Save removes b's sidecar.
        both = self.call('keep_annotation', {'task': 'shapes', 'record': 'images__c.png', 'keep': 'both',
                                             'sets': ['datasets/shapes-a', 'datasets/shapes-b']})
        self.assertEqual(both['state'], 'accepted')
        value = self.call('annotation', {'task': 'shapes', 'record': 'images__c.png'})['annotation']['value']
        self.assertEqual(len(value), 2)
        self.call('keep_annotation', {'task': 'masks', 'record': 'images__a.png', 'keep': 'one',
                                      'sets': ['datasets/masks-a']})
        self.call('save', {})
        files = sorted(path.name for path in (self.folder / 'annotations' / 'masks').iterdir())
        now = self.call('annotation', {'task': 'masks', 'record': 'images__a.png'})['annotation']['value']['file']
        self.assertEqual(files, [now])
        self.assertEqual(check.check_folder(self.folder).problems, [])
        activity = [row for row in self.call('activity', {'limit': 20})['items']
                    if row['operation'] == 'keep_annotation' and row['outcome'] == 'done']
        self.assertEqual(len(activity), 4)


if __name__ == '__main__':
    unittest.main()
