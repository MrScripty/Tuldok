"""Comparing chosen models (docs/plans/training-and-curation/spec-t3.md sections 1 to 4).

Flattening, the differences, the bootstrap and the axes are tested on data the
tests write, against arithmetic the tests do themselves (their own seeded
random.Random, choices and percentiles). The three operations run on a copy of
tests/fixtures/tuldok_project/minimal with its per-case values imported, when
TULDOK_DATABASE_URL names a disposable cluster.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import comparing, local, operations  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
from test_tuldok_project_store import StoreCase  # noqa: E402

DATABASE = os.environ.get('TULDOK_DATABASE_URL')
COMPARING = ('model_compare', 'benchmark_axes', 'intervals')
OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner',
         'scopes': ['inspect', 'edit', 'execute', 'cancel', 'approve-execution']}


# ------------------------------------------------------------ the test's own arithmetic

def percentile(ordered, q):
    """numpy's 'linear' percentile, written again: position q (n − 1), interpolated."""
    position = q * (len(ordered) - 1)
    low = int(position)
    if low + 1 >= len(ordered):
        return ordered[-1]
    return ordered[low] * (1 - (position - low)) + ordered[low + 1] * (position - low)


def stat(values, name):
    ordered = sorted(values)
    return {'mean': lambda: math.fsum(ordered) / len(ordered), 'min': lambda: ordered[0], 'max': lambda: ordered[-1],
            'median': lambda: percentile(ordered, 0.5), 'p10': lambda: percentile(ordered, 0.1),
            'p90': lambda: percentile(ordered, 0.9)}[name]()


def bootstrap(values, name, resamples=2000):
    rng, ordered = random.Random(20261119), sorted(values)
    draws = sorted(stat(rng.choices(ordered, k=len(ordered)), name) for _ in range(resamples))
    return [percentile(draws, 0.025), percentile(draws, 0.975)]


def close(test, got, want, places=12):
    test.assertEqual(len(got), len(want))
    for a, b in zip(got, want):
        test.assertAlmostEqual(a, b, places=places)


class Flattening(unittest.TestCase):

    def test_leaves_paths_and_identity_left_out(self):
        document = {'format': 'tuldok_definition_v1', 'kind': 'recipe', 'title': 'T', 'description': 'D',
                    'labels': {'short': 'X'}, 'earlier_work': {}, 'compared_with': [], 'card': 'notes/x.md',
                    'group': 'g', 'change': 'refinement', 'derived_from': 'recipes/a',
                    'run': {'settings': {'lr': 0.001, 'layers': [8, 16], 'opt': {'name': 'adam', 'betas': []},
                                         'a.b': 1, '': 2, 'with space': {'x': True}, 'empty': {}},
                            'inputs': {'training': 'datasets/w'}}}
        flat, truncated = comparing.flatten(document)
        self.assertFalse(truncated)
        self.assertEqual(flat, {
            'group': 'g', 'change': 'refinement', 'derived_from': 'recipes/a',
            'run.settings.lr': 0.001, 'run.settings.layers[0]': 8, 'run.settings.layers[1]': 16,
            'run.settings.opt.name': 'adam', 'run.settings.opt.betas': [], 'run.settings["a.b"]': 1,
            'run.settings[""]': 2, 'run.settings["with space"].x': True, 'run.settings.empty': {},
            'run.inputs.training': 'datasets/w'})
        self.assertEqual([comparing.kind_of(path) for path in ('group', 'change', 'derived_from',
                                                                 'run.inputs.training', 'run.settings.lr')],
                         ['group', 'change', 'parent', 'data', 'setting'])

    def test_bounds(self):
        document = {'run': {'settings': {f'k{i}': i for i in range(10)}}}
        flat, truncated = comparing.flatten(document, leaves=4)
        self.assertEqual((len(flat), truncated), (4, True))
        deep = {'a': {'b': {'c': {'d': 1}}}, 'e': 2}
        flat, truncated = comparing.flatten(deep, depth=3)
        self.assertEqual((flat, truncated), ({'e': 2}, True))
        self.assertEqual(comparing.flatten(deep, depth=4), ({'a.b.c.d': 1, 'e': 2}, False))


class Differences(unittest.TestCase):

    def test_what_differs_in_its_order_and_what_is_the_same(self):
        a = {'group': 'g', 'change': 'refinement', 'run': {'inputs': {'t': 'datasets/a'},
                                                          'settings': {'lr': 1, 'n': 2, 'flag': True, 'x10': 1,
                                                                       'x2': 1, 'name': 'adam'}}}
        b = {'group': 'g', 'change': 'architecture', 'derived_from': 'recipes/a',
             'run': {'inputs': {'t': 'datasets/b'}, 'settings': {'lr': 1.0, 'n': 3, 'flag': 1, 'x10': 2, 'x2': 2,
                                                                 'name': 'adam'}}}
        c = {'group': 'g', 'change': 'refinement', 'run': {'inputs': {'t': 'datasets/a'},
                                                          'settings': {'lr': 1, 'n': 2, 'flag': True, 'x10': 1,
                                                                       'x2': 1, 'name': 'adam'}}}
        got = comparing.differences([a, b, c])
        self.assertEqual([(row['kind'], row['path']) for row in got['differs']],
                         [('change', 'change'), ('parent', 'derived_from'), ('data', 'run.inputs.t'),
                          ('setting', 'run.settings.flag'), ('setting', 'run.settings.n'),
                          ('setting', 'run.settings.x2'), ('setting', 'run.settings.x10')])
        parent = got['differs'][1]
        self.assertEqual((parent['values'], parent['present']), ([None, 'recipes/a', None], [False, True, False]))
        self.assertEqual(got['differs'][3]['values'], [True, 1, True])   # true is not 1
        self.assertEqual(got['same'], 3)   # group, lr (1 is 1.0) and name
        self.assertEqual(got['more'], 0)
        limited = comparing.differences([a, b, c], most=2)
        self.assertEqual((len(limited['differs']), limited['more']), (2, 5))
        long = comparing.differences([{'note': 'x' * 300}, {'note': 'y'}])
        self.assertEqual(len(long['differs'][0]['values'][0]), comparing.SHOWN)


class Bootstrap(unittest.TestCase):
    VALUES = [0.31, 0.12, 0.5, 0.44, 0.27, 0.9, 0.05, 0.61, 0.33, 0.29, 0.71]

    def test_every_statistic_against_the_tests_own_resampling(self):
        got = comparing.interval_set(self.VALUES)
        for name in comparing.STATISTICS:
            with self.subTest(name):
                close(self, got[name], bootstrap(self.VALUES, name))
                self.assertLessEqual(got[name][0], got[name][1])
        self.assertEqual(comparing.interval_set(self.VALUES), got)   # the same on every reading
        self.assertEqual(comparing.interval_set(list(reversed(self.VALUES))), got)   # sorted first
        self.assertLessEqual(got['median'][0], stat(self.VALUES, 'median'))
        self.assertGreaterEqual(got['median'][1], stat(self.VALUES, 'median'))

    def test_fewer_than_two_values_have_none(self):
        self.assertIsNone(comparing.interval_set([0.5]))
        self.assertIsNone(comparing.interval_set([]))
        self.assertEqual(comparing.interval_set([2.0, 2.0])['mean'], [2.0, 2.0])

    def test_paired_difference(self):
        first = {('c1', ''): 1.0, ('c2', ''): 2.0, ('c3', ''): 3.0, ('c4', ''): 4.0, ('c5', ''): 5.0}
        second = {key: value - 0.5 + 0.01 * i for i, (key, value) in enumerate(sorted(first.items()))}
        second[('only', '')] = 99.0
        got = comparing.difference(first, second, 'median')
        keys = sorted(set(first) & set(second))
        a, b = [first[k] for k in keys], [second[k] for k in keys]
        rng, draws = random.Random(20261119), []
        for _ in range(2000):
            drawn = rng.choices(range(len(keys)), k=len(keys))
            draws.append(stat([a[i] for i in drawn], 'median') - stat([b[i] for i in drawn], 'median'))
        draws.sort()
        want = [percentile(draws, 0.025), percentile(draws, 0.975)]
        close(self, [got['low'], got['high']], want)
        self.assertEqual((got['paired'], got['count']), (True, 5))
        self.assertTrue(got['significant'])   # every case of the first is about 0.5 above the second

    def test_independent_difference_and_not_significant(self):
        first = {('a', ''): 1.0, ('b', ''): 2.0, ('c', ''): 3.0}
        second = {('x', ''): 1.5, ('y', ''): 2.5, ('z', ''): 2.0, ('w', ''): 3.5}
        got = comparing.difference(first, second, 'mean')
        rng, draws = random.Random(20261119), []
        av, bv = sorted(first.values()), sorted(second.values())
        for _ in range(2000):
            draws.append(stat(rng.choices(av, k=3), 'mean') - stat(rng.choices(bv, k=4), 'mean'))
        draws.sort()
        close(self, [got['low'], got['high']], [percentile(draws, 0.025), percentile(draws, 0.975)])
        self.assertEqual((got['paired'], got['count'], got['significant']), (False, 3, False))
        self.assertIsNone(comparing.difference({('a', ''): 1.0}, second, 'mean'))


class FrontierPairs(unittest.TestCase):

    def test_neighbours_compared_on_both_metrics(self):
        def point(subject, x, value, frontier=True):
            return {'subject': subject, 'x': x, 'value': value, 'frontier': frontier}
        chart = {'chart': 'charts/t', 'title': 'T', 'statistic': 'median', 'group': None,
                 'metric': {'id': 'err'}, 'metric_x': {'id': 'ms'},
                 'series': [{'group': '', 'points': [point('a', 1, 0.9), point('off', 1.5, 0.95, False),
                                                     point('b', 2, 0.5), point('c', 2.1, 0.49)]}]}
        cases = [('k%d' % i, '') for i in range(8)]
        held = {('a', 'ms'): {k: 1.0 + 0.01 * i for i, k in enumerate(cases)},
                ('a', 'err'): {k: 0.9 + 0.01 * i for i, k in enumerate(cases)},
                ('b', 'ms'): {k: 2.0 + 0.01 * i for i, k in enumerate(cases)},
                ('b', 'err'): {k: 0.5 + 0.01 * i for i, k in enumerate(cases)},
                # c is b again, a hair better and a hair slower on alternate cases: not told apart from b.
                ('c', 'ms'): {k: 2.0 + 0.01 * i + (0.02 if i % 2 else -0.02) for i, k in enumerate(cases)},
                ('c', 'err'): {k: 0.5 + 0.01 * i + (-0.02 if i % 2 else 0.02) for i, k in enumerate(cases)}}
        pairs = comparing._frontier_pairs(chart, held)
        self.assertEqual([pair['subjects'] for pair in pairs], [['a', 'b'], ['b', 'c']])
        self.assertEqual(pairs[0]['metric'], comparing.difference(held['a', 'err'], held['b', 'err'], 'median'))
        self.assertEqual((pairs[0]['separated'], pairs[1]['separated']), (True, False))
        self.assertEqual(comparing._frontier_pairs(chart, held, touching={'a'})[0]['subjects'], ['a', 'b'])
        self.assertEqual(len(comparing._frontier_pairs(chart, held, touching={'c'})), 1)
        del held['c', 'ms']
        self.assertIsNone(comparing._frontier_pairs(chart, held)[1]['separated'])
        self.assertEqual(comparing._frontier_pairs({**chart, 'group': 'horizon'}, held), [])


class Axes(unittest.TestCase):

    def gathered(self, recipes, metric_values):
        class Row:
            def __init__(self, value):
                self.count, self.median, self.mean = 4, value, value

        class Stored:
            def __init__(self, value):
                self.row, self.origin = Row(value), 'file'

        subjects = [{'name': f's{i}', 'title': f'S{i}', 'recipe': f'recipes/r{i}'} for i in range(len(recipes))]
        summaries = {(f's{i}', 'err'): Stored(value) for i, value in enumerate(metric_values) if value is not None}
        return {'benchmark': 'b', 'metrics': [{'id': 'err', 'title': 'Error', 'units': '1', 'better': 'lower'}],
                'subjects': subjects, 'summaries': summaries,
                'recipes': {f'recipes/r{i}': document for i, document in enumerate(recipes)}}

    def test_number_and_category_axes_and_their_order(self):
        recipes, errors = [], [0.5, 0.4, 0.3, 0.2, 0.1, None]
        for i in range(6):
            recipes.append({'change': ['refinement', 'architecture'][i % 2],
                            'run': {'settings': {'width': 8 * (i + 1), 'seed': [3, 1, 4, 1, 5, 9][i], 'constant': 7,
                                                 'opt': ['adam', 'sgd', 'adam', 'sgd', 'adam', 'sgd'][i],
                                                 'tag': f'run-{i}', 'flag': i > 2}}})
        recipes[5]['run']['settings']['width'] = 'wide'    # a mix of texts and numbers: a category
        got = comparing.benchmark_axes(self.gathered(recipes, errors))
        axes = {axis['path']: axis for axis in got['settings']}
        self.assertNotIn('run.settings.constant', axes)       # the same everywhere
        self.assertIn('run.settings.tag', axes)               # 6 texts are a category
        width = axes['run.settings.width']
        self.assertEqual((width['kind'], width['categories']), ('category', [8, 16, 24, 32, 40, 'wide']))
        seed = axes['run.settings.seed']
        self.assertEqual((seed['kind'], seed['low'], seed['high'], seed['distinct'], seed['count']),
                         ('number', 1, 9, 5, 6))
        xs, ys = [3, 1, 4, 1, 5], [0.5, 0.4, 0.3, 0.2, 0.1]   # s5 has no error
        self.assertAlmostEqual(seed['association'], spearman(xs, ys))
        flag = axes['run.settings.flag']
        self.assertEqual((flag['kind'], flag['categories']), ('category', [False, True]))
        self.assertAlmostEqual(flag['association'], spearman([0, 0, 0, 1, 1], ys))
        order = [abs(axis['association']) for axis in got['settings'] if axis['association'] is not None]
        self.assertEqual(order, sorted(order, reverse=True))
        self.assertEqual(got['subjects'][1]['settings']['run.settings.opt'], 1)   # sgd, second category
        self.assertEqual(got['subjects'][5]['metrics'], {'err': None})
        self.assertEqual(got['metrics'][0]['positive'], True)
        self.assertEqual((got['metrics'][0]['low'], got['metrics'][0]['high']), (0.1, 0.5))
        # Thirteen distinct texts are left out; a bound on the axes counts the others in left_out.
        recipes13 = [{'run': {'settings': {'name': f'n{i}', 'x': i}}} for i in range(13)]
        got13 = comparing.benchmark_axes(self.gathered(recipes13, [float(i) for i in range(13)]))
        self.assertEqual([axis['path'] for axis in got13['settings']], ['run.settings.x'])
        self.assertEqual(comparing.benchmark_axes(self.gathered(recipes, errors), most=2)['left_out'],
                         len(got['settings']) - 2)


def spearman(xs, ys):
    def ranks(values):
        out = []
        for value in values:
            below = sum(1 for other in values if other < value)
            equal = sum(1 for other in values if other == value)
            out.append(below + (equal + 1) / 2)
        return out
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return sxy / math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))


# ------------------------------------------------------------ on a project

@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class OnAProject(StoreCase):
    """The minimal fixture: benchmark rollout of three recipes, a tradeoff chart speed-accuracy, values imported."""

    def setUp(self):
        super().setUp()
        project = self.open()
        self.values = {}
        for path in sorted((self.base / 'values').glob('*.json')):
            text = path.read_text(encoding='utf-8')
            project.import_values(text)
            document = json.loads(text)
            for item in document['values']:
                if item['value'] is not None:
                    group = ';'.join(f'{k}={v}' for k, v in sorted((item.get('group') or {}).items()))
                    self.values.setdefault((document['subject'], item['metric']), {})[item['case'], group] = \
                        item['value']
        self.close(project)
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.temporary / 'home'),
                                               local.SETTINGS_VARIABLE: str(self.temporary / 'settings.json')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, **arguments):
        result = self.service.call(name, arguments, OWNER)
        json.dumps(result, allow_nan=False)
        return result

    def test_intervals_and_the_frontier(self):
        got = self.call('intervals', benchmark='benchmarks/rollout')
        self.assertEqual((got['resamples'], got['level'], got['seed']), (2000, 0.95, 20261119))
        rows = {(row['subject'], row['metric']): row for row in got['intervals']}
        self.assertEqual(set(rows), set(self.values))
        for key, cases in self.values.items():
            with self.subTest(key):
                self.assertEqual(rows[key]['count'], len(cases))
                for name in ('median', 'mean', 'p90'):
                    close(self, rows[key][name], bootstrap(list(cases.values()), name))
        [front] = got['frontiers']
        self.assertEqual((front['chart'], front['statistic'], front['grouped']), ('charts/speed-accuracy', 'median',
                                                                                  False))
        # The pairs are the frontier's neighbours as chart_data orders them.
        with self.opened_project() as project:
            from tuldok_project import charts
            data = charts.chart_data(project, 'charts/speed-accuracy')
        on = [point['subject'] for point in data['series'][0]['points'] if point['frontier']]
        self.assertEqual(len(front['pairs']), max(0, len(on) - 1))
        for pair, (a, b) in zip(front['pairs'], zip(on, on[1:])):
            self.assertEqual(pair['subjects'], [a, b])
            for key, metric in (('metric', 'rmse'), ('metric_x', 'seconds')):
                want = comparing.difference(self.values[a, metric], self.values[b, metric], 'median')
                self.assertEqual(pair[key], want)
        apart = sorted({s for pair in front['pairs'] if pair['separated'] is False for s in pair['subjects']})
        self.assertEqual(front['not_separated'], apart)
        with self.assertRaises(ProjectError) as caught:
            self.service.call('intervals', {'benchmark': 'nothing'}, OWNER)
        self.assertEqual(caught.exception.code, 'not-found')

    def opened_project(self):
        return self.service._open()

    def test_model_compare(self):
        recipes = ['recipes/stepper-k2', 'recipes/stepper-k1', 'recipes/early-fit']
        got = self.call('model_compare', recipes=recipes, statistic='mean')
        self.assertEqual([model['reference'] for model in got['models']], recipes)
        self.assertEqual([model['change'] for model in got['models']],
                         ['refinement', 'training-policy', 'architecture'])
        kinds = {row['path']: row['kind'] for row in got['differs']}
        self.assertEqual(kinds['change'], 'change')
        self.assertEqual(kinds['derived_from'], 'parent')
        self.assertEqual(kinds['run.inputs.start.from'], 'data')
        self.assertEqual(kinds['run.settings.learning_rate'], 'setting')
        self.assertNotIn('model', kinds)   # all three are models/stepper
        [bench] = got['benchmarks']
        self.assertEqual(bench['benchmark'], 'rollout')
        self.assertEqual([column['subject'] for column in bench['models']], ['stepper-k2', 'stepper-k1', 'early-fit'])
        k2 = bench['models'][0]['values']['rmse']
        cases = list(self.values['stepper-k2', 'rmse'].values())
        self.assertAlmostEqual(k2['value'], math.fsum(cases) / len(cases))
        close(self, [k2['low'], k2['high']], bootstrap(cases, 'mean'))
        self.assertTrue(bench['models'][0]['per_case'])
        [front] = bench['frontiers']
        flags = [row['on'] if row else None for row in front['models']]
        with self.opened_project() as project:
            from tuldok_project import charts
            data = charts.chart_data(project, 'charts/speed-accuracy')
        points = {point['subject']: point['frontier'] for point in data['series'][0]['points']}
        self.assertEqual(flags, [points.get(s) for s in ('stepper-k2', 'stepper-k1', 'early-fit')])
        refused = []
        for arguments in ({'recipes': ['recipes/stepper-k1', 'recipes/stepper-k1']},
                          {'recipes': ['recipes/stepper-k1', 'recipes/none']}, {'recipes': ['recipes/stepper-k1']},
                          {'recipes': recipes, 'statistic': 'mode'}):
            with self.assertRaises(ProjectError) as caught:
                self.service.call('model_compare', arguments, OWNER)
            refused.append(caught.exception.code)
        self.assertEqual(refused, ['invalid', 'not-found', 'invalid', 'invalid'])

    def test_benchmark_axes(self):
        got = self.call('benchmark_axes', benchmark='rollout')
        self.assertEqual([metric['id'] for metric in got['metrics']], ['rmse', 'seconds'])
        self.assertEqual([row['subject'] for row in got['subjects']], ['stepper-k1', 'stepper-k2', 'early-fit'])
        axes = {axis['path']: axis for axis in got['settings']}
        self.assertEqual(axes['change']['categories'], ['architecture', 'refinement', 'training-policy'])
        self.assertEqual([row['settings']['change'] for row in got['subjects']], [2, 1, 0])
        with self.assertRaises(ProjectError) as caught:
            self.service.call('benchmark_axes', {'benchmark': 'nothing'}, OWNER)
        self.assertEqual(caught.exception.code, 'not-found')


class Published(unittest.TestCase):

    def test_the_three_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in COMPARING:
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.' + name for name in COMPARING} <= folder)
        self.assertFalse({'project.' + name for name in COMPARING} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
