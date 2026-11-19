"""Sweeps (docs/plans/training-and-curation/spec-t7.md): the definition, the schedule, halving, trials and the runs.

The schedule, halving's decisions and a trial's text are checked against the
test's own arithmetic without a database. The rest needs a database and runs
only when TULDOK_DATABASE_URL names a disposable cluster: a project written
by the test, committed to a Git repository of its own, whose recipe runs the
stand-in tests/project_sweep_stand_in.py (plain Python, logging through
tuldok_log, about a second a trial, its loss falling to a floor its settings
decide) with this interpreter. No GPU is used.
"""
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_api  # noqa: E402
from tuldok_project import (builds, check, environments, launcher, local, operations, plan,  # noqa: E402
                            service as service_module, store, sweeps, training)
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
STAND_IN = Path(__file__).resolve().parent / 'project_sweep_stand_in.py'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')
GIT = ['git', '-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false']
ALL_SCOPES = ['admin', 'approve-execution', 'approve-review', 'cancel', 'edit', 'execute', 'expose-holdout',
              'freeze', 'inspect']
OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner', 'scopes': ALL_SCOPES}
AGENT = {'actor_id': 'agent-1', 'kind': 'agent', 'label': 'An agent', 'scopes': ['inspect', 'execute', 'cancel']}
ENDED = ('succeeded', 'failed', 'cancelled', 'declined', 'expired')


def r6(value):
    return float(f'{value:.6g}')


def floor(learning_rate, width):
    """The stand-in's floor (tests/project_sweep_stand_in.py)."""
    return 0.1 * (math.log10(learning_rate) + 2) ** 2 + 1 / width


def recipe(settings, group=None):
    document = {'format': 'tuldok_definition_v1', 'kind': 'recipe', 'title': 'The stand-in',
                'run': {'command': ['python', 'stand_in.py', '--settings', '{settings}', '--out', '{output}'],
                        'environment': 'environments/here', 'settings': settings,
                        'env': {'PYTHONPATH': str(REPOSITORY)},
                        'outputs': {'weights': {'path': 'weights.json', 'role': 'weights'}},
                        'sources': ['stand_in.py']}}
    if group:
        document['group'] = group
    return document


def sweep(**fields):
    document = {'format': 'tuldok_definition_v1', 'kind': 'sweep', 'title': 'Learning rate and width',
                'recipe': 'recipes/base',
                'parameters': [{'path': 'learning_rate', 'low': 0.001, 'high': 0.1, 'scale': 'log'},
                               {'path': 'width', 'values': [4, 8, 16, 32]}],
                'strategy': {'kind': 'random', 'seed': 7},
                'objectives': [{'metric': 'loss', 'better': 'lower'}],
                'budget': {'trials': 4}}
    document.update(fields)
    return document


# ======================================================================= the schedule

class Schedule(unittest.TestCase):

    def test_a_grid_is_the_product_in_order_with_its_points_rounded(self):
        document = sweep(parameters=[{'path': 'a', 'values': ['x', 'y']},
                                     {'path': 'b', 'low': 0.001, 'high': 0.1, 'scale': 'log', 'count': 3},
                                     {'path': 'c', 'low': 1, 'high': 2, 'integer': True, 'count': 5}],
                         strategy={'kind': 'grid'})
        b = [r6(math.exp(math.log(0.001) + i * (math.log(0.1) - math.log(0.001)) / 2)) for i in range(3)]
        c = []
        for i in range(5):   # 1, 1.25, 1.5, 1.75, 2 -> floor(x + 0.5): 1, 1, 2, 2, 2
            whole = math.floor(1 + i * 0.25 + 0.5)
            if whole not in c:
                c.append(whole)
        self.assertEqual(c, [1, 2])
        expected = [{'a': a, 'b': bv, 'c': cv} for a, bv, cv in itertools.product(['x', 'y'], b, c)]
        self.assertEqual(list(sweeps.schedule(document)), expected)
        self.assertEqual(b, [0.001, 0.01, 0.1])

    def test_random_draws_follow_the_seed_and_drop_repeats(self):
        document = sweep()
        rng = random.Random(7)
        expected, seen = [], set()
        while len(expected) < 30:
            u = rng.random()
            lr = r6(math.exp(math.log(0.001) + u * (math.log(0.1) - math.log(0.001))))
            width = [4, 8, 16, 32][rng.randrange(4)]
            if (lr, width) in seen:
                continue
            seen.add((lr, width))
            expected.append({'learning_rate': lr, 'width': width})
        self.assertEqual(list(itertools.islice(sweeps.schedule(document), 30)), expected)

    def test_a_small_space_is_exhausted(self):
        document = sweep(parameters=[{'path': 'width', 'values': [4, 8]}, {'path': 'deep', 'values': [True, False]}])
        drawn = list(sweeps.schedule(document))
        self.assertEqual(len(drawn), 4)
        self.assertEqual({(item['width'], item['deep']) for item in drawn},
                         {(4, True), (4, False), (8, True), (8, False)})

    def test_one_and_one_point_zero_are_the_same_draw(self):
        document = sweep(parameters=[{'path': 'x', 'values': [1, 1.0]}])
        self.assertEqual(len(list(sweeps.schedule(document))), 1)


# ======================================================================= halving

class FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, parameters=None):
        self.calls.append(parameters)


def write_log(directory, lines):
    path = Path(directory) / 'output' / 'training'
    path.mkdir(parents=True, exist_ok=True)
    with open(path / 'metrics.jsonl', 'a', encoding='utf-8') as handle:
        for line in lines:
            handle.write(json.dumps(line) + '\n')


class Halving(unittest.TestCase):
    STRATEGY = {'kind': 'halving', 'seed': 1, 'metric': 'loss', 'better': 'lower', 'min': 2, 'factor': 2}

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.addCleanup(training.forget)

    def watch(self, name, recorded, lines, strategy=None):
        """A watcher of a trial whose log holds lines, read once as the runner reads it."""
        document = sweep(strategy=strategy or self.STRATEGY)
        directory = self.base / name
        write_log(directory, lines)
        watch = sweeps._Watch(document, FakeConnection(), 's', 'run', 1, recorded, None, time.monotonic)
        watch.directory, watch.output, watch.run_id = str(directory), str(directory / 'output'), name
        watch.look()
        return watch

    def test_rungs_and_their_crossing(self):
        self.assertEqual(sweeps.rung_points(self.STRATEGY)[:4], [2, 4, 8, 16])
        self.assertEqual(sweeps.rung_points({**self.STRATEGY, 'unit': 'time', 'min': 0.5, 'factor': 3})[:3],
                         [0.5, 1.5, 4.5])
        rungs = sweeps.Rungs([2, 4, 8])
        self.assertEqual(rungs.feed(1, 0.9), [])
        self.assertEqual(rungs.feed(5, 0.7), [(0, 2, 0.7), (1, 4, 0.7)])   # one line crossing two rungs
        self.assertEqual(rungs.feed(5, 0.6), [])
        self.assertEqual(rungs.feed(9, None), [(2, 8, None)])

    def test_goes_on(self):
        self.assertEqual(sweeps.goes_on(5.0, [], 'lower', 3), (True, 1, 1))
        self.assertEqual(sweeps.goes_on(5.0, [1.0], 'lower', 3), (True, 2, 1))       # n < factor
        self.assertEqual(sweeps.goes_on(5.0, [1.0, 2.0], 'lower', 3), (False, 3, 1))
        self.assertEqual(sweeps.goes_on(0.5, [1.0, 2.0], 'lower', 3), (True, 3, 1))
        self.assertEqual(sweeps.goes_on(1.0, [1.0, 2.0], 'lower', 3), (True, 3, 1))  # a tie is not better
        self.assertEqual(sweeps.goes_on(1.5, [1.0, 2.0, 3.0], 'lower', 3), (True, 4, 2))
        self.assertEqual(sweeps.goes_on(1.5, [1.0, 2.0, 3.0], 'higher', 3), (False, 4, 2))

    def test_decisions_on_logs(self):
        recorded = {}
        # The value at a rung is the latest finite value on the line reaching it or before: here the line of
        # step 3 (no loss) reaches rung 2 with 0.8, the loss of step 1.
        first = self.watch('a', recorded, [{'step': 1, 'time': 0.1, 'loss': 0.8}, {'step': 3, 'time': 0.2},
                                            {'step': 4, 'time': 0.3, 'loss': 0.6}])
        self.assertEqual([(r['rung'], r['value'], r['goes_on']) for r in first.reached], [(0, 0.8, True), (1, 0.6, True)])
        self.assertIsNone(first.reason)
        # A second trial worse at rung 2: n = 2 = factor, kept 1, one better: pruned, its cancel file written.
        second = self.watch('b', recorded, [{'step': 2, 'time': 0.1, 'loss': 0.9}, {'step': 4, 'time': 0.2, 'loss': 0.1}])
        self.assertEqual([(r['rung'], r['value'], r['n'], r['kept'], r['goes_on']) for r in second.reached],
                         [(0, 0.9, 2, 1, False)])
        self.assertEqual(second.reason, 'pruned')
        self.assertTrue((self.base / 'b' / launcher.CANCEL_FILE).exists())
        self.assertIn('rung 1 (step 2)', second.problem)
        # A third, better at both rungs: n = 3, kept 2.
        third = self.watch('c', recorded, [{'step': 2, 'time': 0.1, 'loss': 0.5}, {'step': 4, 'time': 0.2, 'loss': 0.4}])
        self.assertEqual([(r['n'], r['kept'], r['goes_on']) for r in third.reached], [(3, 2, True), (2, 1, True)])
        self.assertEqual(recorded, {0: [0.8, 0.9, 0.5], 1: [0.6, 0.4]})
        # A trial with no value of the metric records nothing and goes on.
        fourth = self.watch('d', recorded, [{'step': 2, 'time': 0.1, 'other': 1.0}])
        self.assertEqual(fourth.reached, [])
        self.assertIsNone(fourth.reason)

    def test_appended_lines_are_read_on(self):
        recorded = {0: [0.1]}
        watch = self.watch('a', recorded, [{'step': 1, 'time': 0.1, 'loss': 0.9}])
        self.assertEqual(watch.reached, [])
        write_log(self.base / 'a', [{'step': 2, 'time': 0.2, 'loss': 0.95}])
        watch.look()
        self.assertEqual(watch.reason, 'pruned')
        self.assertEqual(watch.latest, {'loss': 0.95})

    def test_minutes_stop_a_trial(self):
        document = sweep()
        directory = self.base / 'late'
        write_log(directory, [{'step': 1, 'time': 0.1, 'loss': 0.9}])
        watch = sweeps._Watch(document, FakeConnection(), 's', 'run', 1, {}, 10.0, lambda: 11.0)
        watch.directory, watch.output, watch.run_id = str(directory), str(directory / 'output'), 'late'
        watch.look()
        self.assertEqual(watch.reason, 'minutes')
        self.assertTrue((directory / launcher.CANCEL_FILE).exists())


# ======================================================================= a trial's definition

class Trial(unittest.TestCase):

    def test_the_text_of_a_trial(self):
        base = recipe({'training': {'learning_rate': 0.01, 'schedule': [{'lr': 1}, {'lr': 2}]}, 'width': 8},
                      group='small')
        base['card'] = 'notes/x.md'
        base['labels'] = {'short': 'B'}
        base['compared_with'] = [{'recipe': 'recipes/other', 'explanation': 'x'}]
        base['model'] = 'models/m'
        document = sweep(title='A search')
        values = {'training.learning_rate': 0.003, 'training.schedule.1.lr': 5, 'width': 16}
        text = sweeps.trial_text('sweeps/s', document, 'recipes/base', base, 3, values)
        made = json.loads(text)
        self.assertTrue(text.endswith('}\n'))
        self.assertEqual(made['title'], 'A search · trial 3')
        self.assertEqual((made['derived_from'], made['change'], made['group'], made['model'], made['labels']),
                         ('recipes/base', 'sweep-trial', 'small', 'models/m', {'short': 'T3'}))
        self.assertEqual(made['sweep'], {'definition': 'sweeps/s', 'trial': 3, 'values': values})
        self.assertEqual(made['run']['settings'], {'training': {'learning_rate': 0.003,
                                                                'schedule': [{'lr': 1}, {'lr': 5}]}, 'width': 16})
        self.assertNotIn('card', made)
        self.assertNotIn('compared_with', made)
        self.assertEqual(base['run']['settings']['width'], 8)   # the recipe is not changed
        self.assertEqual(made['description'],
                         'Trial 3 of sweeps/s: training.learning_rate = 0.003, training.schedule.1.lr = 5, width = 16.')

    def test_names_never_overwrite(self):
        self.assertEqual(sweeps.place_trial({}, 'sweeps/s', 7, 'A'), ('recipes/s-007', False))
        self.assertEqual(sweeps.place_trial({'recipes/s-007': 'A'}, 'sweeps/s', 7, 'A'), ('recipes/s-007', True))
        self.assertEqual(sweeps.place_trial({'recipes/s-007': 'B'}, 'sweeps/s', 7, 'A'), ('recipes/s-007-2', False))
        self.assertEqual(sweeps.place_trial({'recipes/s-007': 'B', 'recipes/s-007-2': 'C'}, 'sweeps/s', 7, 'A'),
                         ('recipes/s-007-3', False))
        self.assertEqual(sweeps.place_trial({}, 'sweeps/' + 'x' * 120, 1000, 'A')[0], 'recipes/' + 'x' * 100 + '-1000')

    def test_paths(self):
        settings = {'a': {'b': [1, {'c': 2}]}, 'n': 3}
        self.assertIsNone(sweeps.path_problem(settings, 'a.b.1.c'))
        self.assertIsNone(sweeps.path_problem(settings, 'a.new'))
        self.assertIn('not in the recipe', sweeps.path_problem(settings, 'x.y'))
        self.assertIn('not an object or a list', sweeps.path_problem(settings, 'n.y'))
        self.assertIn('past its end', sweeps.path_problem(settings, 'a.b.2'))


# ======================================================================= the checker

class Checking(unittest.TestCase):

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name) / 'project'
        for part in ('recipes', 'sweeps', 'environments'):
            (self.folder / part).mkdir(parents=True)
        (self.folder / 'tuldok.json').write_text(json.dumps({'format': 'tuldok_project_v1', 'id': 'a' * 32,
                                                             'name': 'Sweeps', 'code_root': '.'}))
        self.write('environments/here', {'format': 'tuldok_definition_v1', 'kind': 'environment', 'title': 'Here',
                                         'python': '3.12', 'device': 'cpu', 'packages': {'jsonschema': '4.26.0'}})
        self.write('recipes/base', recipe({'learning_rate': 0.01, 'width': 8, 'nested': {'depth': 2}}))

    def write(self, reference, document):
        (self.folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n')

    def problems(self, document, name='s'):
        self.write(f'sweeps/{name}', document)
        report = check.check_folder(self.folder, code=False)
        return [(p.severity, p.path, p.pointer, p.message) for p in report.problems]

    def test_a_good_sweep_checks(self):
        self.assertEqual(self.problems(sweep()), [])

    def test_the_schema(self):
        found = self.problems(sweep(parameters=[{'path': 'learning_rate', 'values': [1], 'low': 0, 'high': 1}],
                                    strategy={'kind': 'halving', 'seed': 1}, objectives=[], budget={'trials': 0,
                                                                                                    'concurrency': 2}))
        pointers = {pointer for _, _, pointer, _ in found}
        self.assertTrue({'/parameters/0', '/strategy/metric', '/objectives', '/budget/trials', '/budget/concurrency'}
                        <= pointers, found)

    def test_rules_beyond_the_schema(self):
        found = self.problems(sweep(parameters=[{'path': 'learning_rate', 'low': 1, 'high': 0.5},
                                                {'path': 'learning_rate', 'low': -1, 'high': 1, 'scale': 'log'},
                                                {'path': 'width.x', 'values': [1, 1]},
                                                {'path': 'missing.y', 'values': [1]},
                                                {'path': 'steps', 'low': 1.5, 'high': 3, 'integer': True}],
                                    objectives=[{'metric': 'loss', 'better': 'lower'},
                                                {'metric': 'loss', 'better': 'higher'}]))
        messages = [(pointer, message) for _, _, pointer, message in found]
        self.assertIn(('/parameters/0', 'low (1) must be less than high (0.5).'), messages)
        self.assertIn(('/parameters/1/path', 'learning_rate is varied twice; keep one parameter for it.'), messages)
        self.assertIn(('/parameters/1/low', 'A log scale needs low above 0.'), messages)
        self.assertIn(('/parameters/2/values', 'The values repeat; list each once.'), messages)
        self.assertIn(('/parameters/2/path', "width is not an object or a list in the recipe's settings."), messages)
        self.assertIn(('/parameters/3/path', "missing is not in the recipe's settings."), messages)
        self.assertIn(('/parameters/4', 'An integer range needs whole numbers for low and high.'), messages)
        self.assertIn(('/objectives', 'The two objectives name the same metric; name two.'), messages)

    def test_a_grid(self):
        found = self.problems(sweep(strategy={'kind': 'grid'}))
        self.assertIn(('error', 'sweeps/s.json', '/parameters/0',
                       'A grid takes count points of a range; add count (2 to 64).'), found)
        found = self.problems(sweep(strategy={'kind': 'grid'},
                                    parameters=[{'path': 'learning_rate', 'low': 0.001, 'high': 0.1, 'count': 3},
                                                {'path': 'width', 'values': [4, 8]}]))
        self.assertEqual(found, [('warning', 'sweeps/s.json', '/budget/trials',
                                  'The grid has 6 points and the budget 4; the first 4 in order are run.')])
        found = self.problems(sweep(strategy={'kind': 'grid'},
                                    parameters=[{'path': f'p{i}', 'low': 0, 'high': 1, 'count': 64} for i in range(3)]))
        self.assertIn('at most 100,000', found[0][3])

    def test_the_recipe(self):
        found = self.problems(sweep(recipe='recipes/none'))
        self.assertTrue(any(pointer == '/recipe' for _, _, pointer, _ in found), found)
        filed = recipe({})
        del filed['run']['settings']
        filed['run']['settings_file'] = 'settings.json'
        self.write('recipes/filed', filed)
        found = self.problems(sweep(recipe='recipes/filed'))
        self.assertEqual(len(found), 1)
        self.assertIn('its settings are in a file', found[0][3])

    def test_a_trial_names_a_sweep(self):
        self.write('sweeps/s', sweep())
        trial = json.loads(sweeps.trial_text('sweeps/s', sweep(), 'recipes/base', recipe({'learning_rate': 0.01}), 1,
                                             {'learning_rate': 0.02}))
        self.write('recipes/s-001', trial)
        report = check.check_folder(self.folder, code=False)
        self.assertEqual(report.problems, [])
        roles = {(edge.from_ref, edge.to_ref, edge.role) for edge in report.edges}
        self.assertTrue({('recipes/s-001', 'sweeps/s', 'sweep'), ('sweeps/s', 'recipes/base', 'varies'),
                         ('recipes/s-001', 'recipes/base', 'derived')} <= roles)
        trial['sweep']['definition'] = 'sweeps/gone'
        self.write('recipes/s-001', trial)
        report = check.check_folder(self.folder, code=False)
        self.assertEqual([(p.path, p.pointer) for p in report.problems], [('recipes/s-001.json', '/sweep/definition')])


# ======================================================================= with a database

def _writable(root):
    for current, directories, _files in os.walk(root):
        for name in directories:
            os.chmod(os.path.join(current, name), 0o755)
    if os.path.isdir(root):
        os.chmod(root, 0o755)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class SweepCase(unittest.TestCase):
    """A project written by the test: the stand-in as recipes/base, committed, its environment connected."""

    SETTINGS = {'learning_rate': 0.01, 'width': 8, 'steps': 40, 'sleep': 0.03}

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.home = self.temporary / 'home'
        self.addCleanup(_writable, self.home)
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(service_module, 'POLL_SECONDS', 0.1)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(training.forget)
        self.root = self.temporary / 'repo'
        self.folder = self.root / 'project'
        code = self.root / 'code'
        code.mkdir(parents=True)
        shutil.copy(STAND_IN, code / 'stand_in.py')
        for part in ('recipes', 'sweeps', 'environments'):
            (self.folder / part).mkdir(parents=True)
        self.project_id = __import__('uuid').uuid4().hex
        (self.folder / 'tuldok.json').write_text(json.dumps({
            'format': 'tuldok_project_v1', 'id': self.project_id, 'name': 'Sweeps', 'code_root': '../code',
            'groups': [{'id': 'small', 'title': 'Small models'}]}, indent=2) + '\n')
        self.write('environments/here', {'format': 'tuldok_definition_v1', 'kind': 'environment', 'title': 'Here',
                                         'python': f'{sys.version_info[0]}.{sys.version_info[1]}', 'device': 'cpu',
                                         'packages': {'jsonschema': '4.26.0'}})
        self.write('recipes/base', recipe(dict(self.SETTINGS), group='small'))
        self.git('init', '-q')
        self.commit('The project.')
        self.addCleanup(store.drop_project, self.project_id)
        with builds.opened(self.folder) as project:
            self.assertTrue(environments.connect(project, 'environments/here', sys.executable)['ok'])
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        try:
            with builds.opened(self.folder) as project:
                run_ids = [row[0] for row in project._execute('SELECT id FROM {schema}.runs').fetchall()]
        except Exception:
            run_ids = []
        for run_id in run_ids:
            launcher.stop_strays(run_id)

    def write(self, reference, document):
        (self.folder / f'{reference}.json').write_text(json.dumps(document, indent=2) + '\n')

    def git(self, *arguments):
        subprocess.run([*GIT, '-C', str(self.root), *arguments], check=True, capture_output=True, timeout=60)

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def keep(self, reference, document):
        """Keep a definition through the store and save it, as the page does, then commit the folder."""
        with builds.opened(self.folder) as project:
            project.set_definition(reference, json.dumps(document, indent=2) + '\n')
            project.save()
        self.commit(f'{reference}.')

    def service(self):
        made = Service(self.folder)
        self.addCleanup(made.close)
        made.start()
        return made

    def wait_for(self, served, request_id, seconds=120):
        deadline = time.monotonic() + seconds
        while True:
            shown = served.call('build_request', {'request': request_id}, OWNER)
            if shown['state'] in ENDED:
                return shown
            self.assertLess(time.monotonic(), deadline, f'request still {shown["state"]}')
            time.sleep(0.1)


class Planning(SweepCase):

    def test_a_sweep_is_planned_alone_and_covers_its_recipe(self):
        self.keep('sweeps/s', sweep())
        with builds.opened(self.folder) as project:
            made = plan.build_plan(project, ['sweeps/s'])
            self.assertEqual(made['targets'], ['sweeps/s'])
            self.assertEqual([(step['reference'], step['kind'], step['action']) for step in made['steps']],
                             [('environments/here', 'environment', 'ready'), ('sweeps/s', 'sweep', 'build')])
            step = made['steps'][-1]
            self.assertEqual((step['recipe'], step['trials'], step['state']), ('recipes/base', 4, 'not-built'))
            self.assertTrue(made['buildable'])
            self.assertEqual(made['counts']['build'], 1)
            from tuldok_project import build_requests
            covered = build_requests.covers(project, made, ['sweeps/s'], every=False, scratch=False)
            self.assertEqual(set(covered['definitions']), {'environments/here', 'sweeps/s', 'recipes/base'})
            self.assertEqual(covered['steps'], [{'reference': 'sweeps/s', 'subjects': []}])
            for targets, every in ((['sweeps/s', 'recipes/base'], False), (['sweeps/s'], True)):
                with self.assertRaises(ProjectError) as refused:
                    plan.build_plan(project, targets, every=every)
                self.assertEqual(refused.exception.code, 'invalid')


class Running(SweepCase):

    def test_halving_through_a_service_approved_once(self):
        strategy = {'kind': 'halving', 'seed': 3, 'metric': 'loss', 'better': 'lower', 'min': 2, 'factor': 2}
        self.keep('sweeps/s', sweep(strategy=strategy, budget={'trials': 6},
                                    objectives=[{'metric': 'loss', 'better': 'lower'},
                                                {'metric': 'time', 'better': 'lower', 'title': 'Seconds'}]))
        served = self.service()
        asked = served.call('request_build', {'targets': ['sweeps/s']}, AGENT)
        self.assertEqual(asked['state'], 'awaiting-approval')
        self.assertEqual(served.call('sweep', {'sweep': 's'}, OWNER)['request']['state'], 'awaiting-approval')
        served.call('approve_build', {'request': asked['id']}, OWNER)
        done = self.wait_for(served, asked['id'])
        self.assertEqual(done['state'], 'succeeded', done['problem'])
        shown = served.call('sweep', {'sweep': 'sweeps/s'}, OWNER)
        json.dumps(shown, allow_nan=False)
        trials = shown['trials']
        # The test's arithmetic: the schedule, each trial's floor, and halving's rule over the rungs 2, 4, 8, 16, 32.
        values = list(itertools.islice(sweeps.schedule(sweep(strategy=strategy)), 6))
        self.assertEqual([trial['values'] for trial in trials], values)
        recorded, expected = {}, []
        for item in values:
            bottom = floor(item['learning_rate'], item['width'])
            state = 'completed'
            for rung, point in enumerate([2, 4, 8, 16, 32]):
                value = bottom + math.exp(-point / 8)
                held = recorded.setdefault(rung, [])
                n = len(held) + 1
                better = sum(1 for other in held if other < value)
                held.append(value)
                if n >= 2 and better >= math.ceil(n / 2):
                    state = 'pruned'
                    break
            expected.append(state)
        self.assertIn('pruned', expected)
        self.assertEqual([trial['state'] for trial in trials], expected)
        self.assertEqual(shown['run']['counts']['pruned'], expected.count('pruned'))
        self.assertEqual((shown['run']['state'], shown['run']['ended'], shown['state']), ('finished', 'trials', 'built'))
        for trial, item in zip(trials, values):
            if trial['state'] == 'completed':
                self.assertAlmostEqual(trial['objectives']['loss'], floor(item['learning_rate'], item['width'])
                                       + math.exp(-40 / 8))
            else:
                self.assertTrue(trial['problem'].startswith('Pruned by successive halving'))
                self.assertLess(trial['latest']['step'], 40)
        completed = [trial for trial in trials if trial['state'] == 'completed']
        best = min(completed, key=lambda trial: trial['objectives']['loss'])
        self.assertEqual(shown['best'], {'number': best['number'], 'reference': best['reference'],
                                         'value': best['objectives']['loss']})
        self.assertTrue(set(shown['frontier']) <= {trial['number'] for trial in completed})
        self.assertIn(best['number'], shown['frontier'])
        # The trials as axes: the objectives and the two parameters, one subject a trial.
        axes = shown['axes']
        self.assertEqual([metric['id'] for metric in axes['metrics']], ['loss', 'time'])
        self.assertEqual([(axis['path'], axis['kind']) for axis in axes['settings']],
                         [('learning_rate', 'number'), ('width', 'number')])
        self.assertEqual(len(axes['subjects']), 6)
        # One approval: one request, one plan id over every run, every run of a trial.
        runs = served.call('runs', {}, OWNER)['runs']
        self.assertEqual({run['plan_id'] for run in runs}, {done['plan_id']})
        self.assertEqual(sorted(run['reference'] for run in runs), sorted(trial['reference'] for trial in trials))
        self.assertEqual(len(done['runs']), 6)
        pruned = [trial for trial in trials if trial['state'] == 'pruned']
        for trial in pruned:
            run = served.call('run', {'run': trial['run_id']}, OWNER)
            self.assertEqual(run['state'], 'cancelled')
            self.assertEqual(run['problem'], trial['problem'])
        # Trials are recipes, unsaved, derived from the recipe, grouped under the sweep on the map.
        status = served.call('status', {}, OWNER)
        self.assertEqual(status['unsaved'], sorted(trial['reference'] for trial in trials))
        trial = served.call('definition', {'reference': trials[0]['reference']}, OWNER)
        self.assertEqual((trial['document']['derived_from'], trial['document']['change'],
                          trial['document']['sweep']['values']), ('recipes/base', 'sweep-trial', values[0]))
        made = served.call('map', {}, OWNER)
        group = [g for g in made['groups'] if g['id'] == 'sweeps/s']
        self.assertEqual(group, [{'id': 'sweeps/s', 'title': 'Learning rate and width', 'parent': 'small',
                                  'description': 'The trials of sweeps/s, a search over the settings of recipes/base.',
                                  'models': 6, 'sweep': True}])
        models = {model['reference']: model for model in made['models']}
        self.assertEqual({models[trial['reference']]['group'] for trial in trials}, {'sweeps/s'})
        self.assertNotIn('sweep', models['recipes/base'])   # only a trial and a sweep's group carry it
        self.assertEqual((models[trials[0]['reference']]['sweep'], models[trials[0]['reference']]['derived_from']),
                         ('sweeps/s', 'recipes/base'))
        listed = served.call('sweeps', {}, OWNER)['sweeps']
        self.assertEqual([(item['reference'], item['state'], item['run']['counts']['completed']) for item in listed],
                         [('sweeps/s', 'built', expected.count('completed'))])
        # Saved, the trials are files of the folder.
        served.call('save', {}, OWNER)
        self.assertTrue((self.folder / (trials[0]['reference'] + '.json')).exists())
        # Built already: asking again is refused.
        self.assertEqual(self.refused(served, 'request_build', {'targets': ['sweeps/s']}), 'nothing-to-build')

    def refused(self, served, name, arguments):
        with self.assertRaises(ProjectError) as refused:
            served.call(name, arguments, OWNER)
        return refused.exception.code

    def test_minutes_stop_a_sweep(self):
        self.write('recipes/base', recipe({**self.SETTINGS, 'steps': 30, 'sleep': 0.1}, group='small'))
        self.commit('Slower.')
        self.keep('sweeps/m', sweep(budget={'trials': 10, 'minutes': 0.06}))
        served = self.service()
        asked = served.call('request_build', {'targets': ['sweeps/m']}, OWNER)
        self.assertEqual(asked['state'], 'queued')
        started = time.monotonic()
        done = self.wait_for(served, asked['id'])
        self.assertEqual(done['state'], 'succeeded', done['problem'])
        shown = served.call('sweep', {'sweep': 'm'}, OWNER)
        self.assertEqual((shown['run']['state'], shown['run']['ended']), ('finished', 'minutes'))
        states = [trial['state'] for trial in shown['trials']]
        self.assertEqual(states[-1], 'stopped', states)
        self.assertLess(len(states), 10)
        self.assertLess(time.monotonic() - started, 30)
        self.assertEqual(shown['trials'][-1]['problem'], "The sweep's minutes were spent while it ran.")

    def test_a_grid_reuses_its_built_trials(self):
        document = sweep(strategy={'kind': 'grid'}, parameters=[{'path': 'width', 'values': [4, 8, 16]}],
                         budget={'trials': 2})
        self.write('recipes/base', recipe({**self.SETTINGS, 'steps': 4, 'sleep': 0.01}, group='small'))
        self.commit('Quicker.')
        self.keep('sweeps/g', document)
        with builds.opened(self.folder) as project:
            made = plan.build_plan(project, ['sweeps/g'])
        first = sweeps.execute(self.folder, made)
        self.assertTrue(first['ok'])
        self.assertEqual([item['reference'] for item in first['steps']], ['recipes/g-001', 'recipes/g-002'])
        with builds.opened(self.folder) as project:
            self.assertEqual(plan.build_plan(project, ['sweeps/g'])['steps'][-1]['action'], 'built')
            # Another trial taking the name of the third with other settings is never overwritten.
            other = json.loads(project.definition('recipes/g-001')['text'])
            other['title'] = 'Someone else'
            project.set_definition('recipes/g-003', json.dumps(other, indent=2) + '\n')
        document['budget'] = {'trials': 3}
        self.keep('sweeps/g', document)
        with builds.opened(self.folder) as project:
            made = plan.build_plan(project, ['sweeps/g'])
            self.assertEqual(made['steps'][-1]['state'], 'not-built')
        second = sweeps.execute(self.folder, made)
        self.assertEqual([item['reference'] for item in second['steps']], ['recipes/g-003-2'])
        with builds.opened(self.folder) as project:
            shown = sweeps.show(project, 'g')
            self.assertEqual([(t['reference'], t['state'], t['reused']) for t in shown['trials']],
                             [('recipes/g-001', 'completed', True), ('recipes/g-002', 'completed', True),
                              ('recipes/g-003-2', 'completed', False)])
            self.assertEqual(len(shown['runs']), 2)
            self.assertEqual(json.loads(project.definition('recipes/g-003')['text'])['title'], 'Someone else')
            self.assertEqual(json.loads(project.definition('recipes/g-003-2')['text'])['sweep']['values'],
                             {'width': 16})

    def test_a_stale_definition_is_refused(self):
        self.keep('sweeps/s', sweep())
        with builds.opened(self.folder) as project:
            made = plan.build_plan(project, ['sweeps/s'])
            from tuldok_project import build_requests
            covered = build_requests.covers(project, made, ['sweeps/s'], every=False, scratch=False)
        covered['definitions']['recipes/base'] = '0' * 64
        with self.assertRaises(ProjectError) as refused:
            sweeps.execute(self.folder, made, expect=covered)
        self.assertEqual(refused.exception.code, 'stale')


class Published(unittest.TestCase):

    def test_the_two_reads_are_in_the_project_folder_profile_and_not_in_the_catalog(self):
        for name in ('sweeps', 'sweep'):
            operation = operations.by_name(name)
            self.assertEqual((operation.who, operation.mutation), ('inspect', False))
        folder = {item['id'] for item in agent_api.capabilities('b' * 32, profile='project_folder')['operations']}
        catalog = agent_api.capabilities('b' * 32)
        self.assertTrue({'project.sweeps', 'project.sweep'} <= folder)
        self.assertFalse({'project.sweeps', 'project.sweep'} & {item['id'] for item in catalog['operations']})
        self.assertEqual((len(catalog['operations']), hashlib.sha256(agent_api.encoded(catalog)).hexdigest()),
                         (110, 'ad5cc7ac91646b39b7a20b9dfca5ec79ed96ded4b5e36732fcf1145f1cc24460'))


if __name__ == '__main__':
    unittest.main()
