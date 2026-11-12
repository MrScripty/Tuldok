"""Building a plan (docs/plans/definition-first-projects/spec-m6.md, sections 4 to 6 and 8): runs, products, states.

Placeholders and the precedence of build states are tested as pure functions.
Everything else needs a database and runs only when TULDOK_DATABASE_URL names
a disposable cluster (spec-m1-m2.md, section 1). Each of those tests copies
tests/fixtures/tuldok_project/buildable into a temporary directory, gives it
a fresh project id, makes its code a Git repository of its own with one
commit, points TULDOK_PROJECT_HOME at a temporary directory, connects the
fixture's environment to the interpreter running the tests, and drops the
project's schema afterwards. The commands are the fixture's stand-in scripts:
they need only the standard library, finish in well under a second, and are
made to fail, stall, pause or leave out an output through BUILDABLE_*
variables passed as extra environment. No GPU is used: the two "GPU" steps
only declare gpu: true and sleep.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import builds, charts, environments, graph, launcher, local, plan, snapshot, store  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'buildable'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')
GIT = ['git', '-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false']
TARGETS = ('datasets/numbers', 'recipes/fit-a', 'benchmarks/score')


def _documents():
    return {f'{path.parent.name}/{path.stem}': json.loads(path.read_text(encoding='utf-8'))
            for path in sorted((FIXTURE / 'project').glob('*/*.json'))}


class Fill(unittest.TestCase):
    """builds.fill: the placeholder rules of documents.py, with values."""

    def test_names_and_literal_braces(self):
        self.assertEqual(builds.fill('--out={output} {{x}} {inputs.a}/f', {'output': '/o', 'inputs.a': '/a'}),
                         '--out=/o {x} /a/f')
        self.assertEqual(builds.fill('{{{output}}}', {'output': 'o'}), '{o}')
        self.assertEqual(builds.fill('plain', {}), 'plain')

    def test_an_unknown_name_and_a_stray_brace(self):
        with self.assertRaises(KeyError) as raised:
            builds.fill('{inputs.b}', {'output': 'o'})
        self.assertEqual(raised.exception.args[0], 'inputs.b')
        for text in ('{output', 'out}', '{a{b}'):
            with self.assertRaises(ValueError):
                builds.fill(text, {'output': 'o'})


class States(unittest.TestCase):
    """graph.states' local argument for build states, and the plan's built action (section 5)."""

    def setUp(self):
        self.documents = _documents()

    def test_build_states_override_by_their_precedence(self):
        self.documents['recipes/fit-b']['earlier_work'] = {'rebuild': 'needs-work', 'reason': 'Test.'}
        local = {'datasets/numbers': 'built', 'recipes/fit-a': 'out-of-date', 'steps/gpu-one': 'running',
                 'steps/gpu-two': 'failed', 'recipes/fit-b': 'failed', 'benchmarks/score': 'ready',
                 'environments/test-python': 'ready', 'charts/score-ranking': 'built'}
        states = graph.states(self.documents, local)
        self.assertEqual(states['datasets/numbers'], 'built')
        self.assertEqual(states['recipes/fit-a'], 'out-of-date')
        self.assertEqual(states['steps/gpu-one'], 'running')
        self.assertEqual(states['steps/gpu-two'], 'failed')
        self.assertEqual(states['recipes/fit-b'], 'needs-work')   # held wins over failed (no product)
        self.assertEqual(states['benchmarks/score'], 'not-built')  # not a build state: ignored
        self.assertEqual(states['environments/test-python'], 'ready')
        self.assertEqual(states['charts/score-ranking'], 'none')
        built = graph.states(self.documents, {'recipes/fit-b': 'built'})
        self.assertEqual(built['recipes/fit-b'], 'built')           # a current product wins over needs-work

    def test_the_built_action_is_not_work(self):
        local = {'environments/test-python': 'ready', 'datasets/numbers': 'built', 'recipes/fit-a': 'out-of-date'}
        made = plan.make_plan(self.documents, ['recipes/fit-a'], local=local,
                              built={'recipes/fit-a': {'causes': ['its code changed'], 'scratch': False},
                                     'datasets/numbers': {'causes': [], 'scratch': True}})
        actions = {step['reference']: (step['action'], step['reasons'], step['scratch']) for step in made['steps']}
        self.assertEqual(actions, {'environments/test-python': ('ready', [], False),
                                   'datasets/numbers': ('built', [], True),
                                   'recipes/fit-a': ('build', ['its code changed'], False)})
        self.assertEqual(made['counts'], {'build': 1, 'set-up': 0, 'blocked': 0, 'ready': 1, 'built': 1})


class NoGit(unittest.TestCase):

    def test_a_code_root_outside_git_has_no_code_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(builds._changes(directory, {'a' * 40}), {})


def _writable(root):
    for current, directories, _files in os.walk(root):
        for name in directories:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                os.chmod(path, 0o755)
    if os.path.isdir(root):
        os.chmod(root, 0o755)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class BuildCase(unittest.TestCase):
    """A fresh Git-committed copy of the buildable fixture, its environment connected."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.home = self.temporary / 'home'
        self.addCleanup(_writable, self.home)  # runs before the directory is removed
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        shutil.copytree(FIXTURE, self.temporary / 'buildable')
        self.root = self.temporary / 'buildable'
        self.folder = self.root / 'project'
        self.code = self.root / 'code'
        self.project_id = uuid.uuid4().hex
        project_file = self.folder / 'tuldok.json'
        document = json.loads(project_file.read_text(encoding='utf-8'))
        document['id'] = self.project_id
        project_file.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.git('init', '-q')
        self.commit('The fixture.')
        self.addCleanup(store.drop_project, self.project_id)
        with self.opened() as project:
            self.assertTrue(environments.connect(project, 'environments/test-python', sys.executable)['ok'])

    def git(self, *arguments):
        subprocess.run([*GIT, '-C', str(self.root), *arguments], check=True, capture_output=True, timeout=60)

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', message)

    def opened(self):
        return store.open_project(self.folder)

    def plan(self, *targets, every=False):
        with self.opened() as project:
            return plan.build_plan(project, list(targets), every=every)

    def build(self, *targets, extra_env=None, scratch=False, answer=True):
        made = self.plan(*targets)
        self.asked = []

        def confirm(given):
            self.asked.append(given)
            return answer

        return builds.execute(self.folder, made, confirm=confirm, extra_env=extra_env, scratch=scratch)

    def states(self):
        with self.opened() as project:
            return {row['reference']: row['state'] for row in project.definitions()}

    def runs(self, reference=None):
        with self.opened() as project:
            return builds.runs(project, reference)

    def products(self, reference=None):
        with self.opened() as project:
            return builds.products(project, reference)

    def status(self):
        with self.opened() as project:
            return builds.status(project)

    def ran(self, done):
        return [(item['reference'], item['subject'], item['state']) for item in done['steps']]

    def edit(self, reference, change):
        with self.opened() as project:
            document = project.definition(reference)['document']
            change(document)
            project.set_definition(reference, json.dumps(document, indent=2) + '\n')
            project.save()

    def write_code(self, path, text):
        target = self.code / path
        target.write_text(text, encoding='utf-8')

    def build_all(self):
        done = self.build('benchmarks/score')
        self.assertTrue(done['ok'], done)
        return done


class FullBuild(BuildCase):

    def test_a_full_build_from_nothing(self):
        before = self.states()
        self.assertEqual({reference: before[reference] for reference in TARGETS},
                         {reference: 'not-built' for reference in TARGETS})
        with mock.patch.object(environments, 'probe', wraps=environments.probe) as probe:
            done = self.build('benchmarks/score')
        self.assertEqual(probe.call_count, 1)  # the environment is checked once per build
        self.assertTrue(done['ok'])
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.ran(done), [('datasets/numbers', '', 'succeeded'), ('recipes/fit-a', '', 'succeeded'),
                                          ('benchmarks/score', 'fit-a', 'succeeded'),
                                          ('benchmarks/score', 'zero', 'succeeded')])
        after = self.states()
        self.assertEqual({reference: after[reference] for reference in TARGETS},
                         {reference: 'built' for reference in TARGETS})
        self.assertEqual(after['recipes/fit-b'], 'not-built')

        products = {(item['reference'], item['subject']): item for item in self.products()}
        self.assertEqual(sorted(products), [('benchmarks/score', 'fit-a'), ('benchmarks/score', 'zero'),
                                            ('datasets/numbers', ''), ('recipes/fit-a', '')])
        for item in products.values():
            self.assertFalse(item['scratch'])
            self.assertEqual(item['directory'], os.path.join(self.home, self.project_id, 'runs', item['run_id'], 'output'))
            for output in item['outputs'].values():
                self.assertEqual(output['bytes'], os.path.getsize(os.path.join(item['directory'], output['path'])))
        self.assertEqual(products['recipes/fit-a', '']['outputs'],
                         {'weights': {'path': 'weights.json', 'role': 'weights',
                                      'bytes': products['recipes/fit-a', '']['outputs']['weights']['bytes']}})

        runs = {(row['reference'], row['subject']): row for row in self.runs()}
        commit = subprocess.run(['git', '-C', str(self.root), 'rev-parse', 'HEAD'], capture_output=True,
                                text=True, check=True).stdout.strip()
        data, fit = runs['datasets/numbers', ''], runs['recipes/fit-a', '']
        self.assertEqual((fit['commit'], fit['scratch'], fit['owner_pid']), (commit, False, os.getpid()))
        self.assertEqual(fit['argv'][0], sys.executable)
        self.assertEqual(fit['inputs'], {'data': {'reference': 'datasets/numbers', 'run_id': data['id'],
                                                  'output': 'data'}})
        self.assertEqual(fit['argv'][1:5], ['train.py', '--data',
                                            os.path.join(products['datasets/numbers', '']['directory'], 'numbers.json'),
                                            '--settings'])
        snapshot_root = os.path.join(self.home, self.project_id, 'code', commit, 'code')
        self.assertEqual(fit['argv'][5], os.path.join(snapshot_root, 'settings/fit-a.json'))
        self.assertEqual(fit['environment']['interpreter'], sys.executable)
        self.assertEqual(runs['benchmarks/score', 'fit-a']['inputs']['{recipe}']['run_id'], fit['id'])
        self.assertIn(os.path.join(products['recipes/fit-a', '']['directory'], 'weights.json'),
                      runs['benchmarks/score', 'fit-a']['argv'])
        self.assertIn('constant:0', runs['benchmarks/score', 'zero']['argv'])
        with self.opened() as project:
            env = project._execute('SELECT env, settings FROM {schema}.runs WHERE id = %s', (data['id'],)).fetchone()
        self.assertEqual(env[0]['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual((env[0]['PYTHONDONTWRITEBYTECODE'], env[0]['PYTHONUNBUFFERED']), ('1', '1'))
        self.assertEqual(env[0]['BUILDABLE_LABEL'], f'numbers in {products["datasets/numbers", ""]["directory"]}')
        self.assertTrue(set(env[0]) <= {*builds.PASSED_VARIABLES, 'PYTHONDONTWRITEBYTECODE', 'PYTHONUNBUFFERED',
                                        'CUDA_VISIBLE_DEVICES', 'BUILDABLE_LABEL'})
        settings_path = os.path.join(data['directory'], 'settings.json')
        self.assertEqual(json.loads(Path(settings_path).read_text()), {'count': 6, 'seed': 3})
        self.assertEqual(env[1], Path(settings_path).read_text())
        self.assertFalse(os.access(snapshot_root, os.W_OK))
        event = launcher.progress(fit['directory'])['event']
        self.assertEqual((event['stage'], event['completed'], event['total']), ('fit', 4, 4))

        with self.opened() as project:
            summaries = project.result_summaries('score', metric='error')
            self.assertEqual(sorted({(item.row.subject, item.origin, item.row.count) for item in summaries}),
                             [('fit-a', 'values', 6), ('zero', 'values', 6)])
            data_chart = charts.chart_data(project, 'charts/score-ranking')
        points = data_chart['series'][0]['points']
        self.assertEqual(sorted(point['subject'] for point in points), ['fit-a', 'zero'])
        self.assertEqual(data_chart['missing'], [])

    def test_a_second_build_runs_nothing(self):
        self.build_all()
        count = len(self.runs())
        made = self.plan('benchmarks/score')
        self.assertEqual(made['counts']['build'], 0)
        self.assertEqual({step['reference']: step['action'] for step in made['steps']},
                         {'environments/test-python': 'ready', 'datasets/numbers': 'built',
                          'recipes/fit-a': 'built', 'benchmarks/score': 'built'})
        with mock.patch.object(environments, 'probe', wraps=environments.probe) as probe:
            done = self.build('benchmarks/score')
        self.assertEqual(probe.call_count, 0)
        self.assertTrue(done['ok'])
        self.assertEqual(done['steps'], [])
        self.assertEqual(done['skipped'], list(TARGETS))
        self.assertEqual(len(self.runs()), count)

    def test_a_product_made_current_replaces_the_earlier_one(self):
        self.build_all()
        first = {item['reference']: item['run_id'] for item in self.products()}
        self.edit('datasets/numbers', lambda document: document['run']['settings'].update(count=5))
        self.build('datasets/numbers')
        with self.opened() as project:
            rows = project._execute("SELECT run_id, current FROM {schema}.products "
                                    "WHERE reference = 'datasets/numbers'").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(dict(rows)[first['datasets/numbers']], False)
        self.assertTrue(os.path.isdir(self.runs('datasets/numbers')[1]['directory']))  # nothing deleted


class OutOfDate(BuildCase):
    """The four causes of section 5, each with the plan's reasons and a rebuild of only what is needed."""

    def step(self, made, reference):
        return next(step for step in made['steps'] if step['reference'] == reference)

    def rebuild(self, expected):
        count = len(self.runs())
        done = self.build('benchmarks/score')
        self.assertTrue(done['ok'], done)
        self.assertEqual(self.ran(done), expected)
        self.assertEqual(len(self.runs()), count + len(expected))
        states = self.states()
        self.assertEqual({reference: states[reference] for reference in TARGETS},
                         {reference: 'built' for reference in TARGETS})

    def test_the_definition_changed(self):
        self.build_all()
        self.edit('recipes/fit-a', lambda document: document.update(description='Now described.'))
        states = self.states()
        self.assertEqual((states['datasets/numbers'], states['recipes/fit-a'], states['benchmarks/score']),
                         ('built', 'out-of-date', 'out-of-date'))
        made = self.plan('benchmarks/score')
        fit = self.step(made, 'recipes/fit-a')
        self.assertEqual(fit['action'], 'build')
        self.assertEqual(len(fit['reasons']), 1)
        self.assertTrue(fit['reasons'][0].startswith('its definition changed since run'))
        self.assertEqual(self.step(made, 'benchmarks/score')['reasons'],
                         ['subject fit-a: the recipe recipes/fit-a of its subject is out of date'])
        self.assertEqual(self.step(made, 'datasets/numbers')['action'], 'built')
        self.rebuild([('recipes/fit-a', '', 'succeeded'), ('benchmarks/score', 'fit-a', 'succeeded')])

    def test_the_settings_file_changed(self):
        self.build_all()
        self.write_code('settings/fit-a.json', '{"steps": 2, "scale": 1.0}\n')
        self.commit('Fewer steps.')
        reasons = self.step(self.plan('benchmarks/score'), 'recipes/fit-a')['reasons']
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith('its settings file settings/fit-a.json changed since run'), reasons)
        self.rebuild([('recipes/fit-a', '', 'succeeded'), ('benchmarks/score', 'fit-a', 'succeeded')])
        fit = self.runs('recipes/fit-a')[0]
        self.assertEqual(launcher.progress(fit['directory'])['event']['total'], 2)

    def test_an_input_was_rebuilt(self):
        self.build_all()
        self.edit('datasets/numbers', lambda document: document['run']['settings'].update(count=4))
        self.assertEqual(self.states()['recipes/fit-a'], 'out-of-date')
        self.assertEqual(self.step(self.plan('recipes/fit-a'), 'recipes/fit-a')['reasons'],
                         ['its input data (datasets/numbers) is out of date'])
        done = self.build('datasets/numbers')
        self.assertEqual(self.ran(done), [('datasets/numbers', '', 'succeeded')])
        made = self.plan('benchmarks/score')
        new_run = self.runs('datasets/numbers')[0]['id']
        self.assertEqual(self.step(made, 'recipes/fit-a')['reasons'],
                         [f'its input data (datasets/numbers) was rebuilt since (now run {new_run[:12]})'])
        score = self.step(made, 'benchmarks/score')['reasons']
        self.assertIn(f'subject zero: its input data (datasets/numbers) was rebuilt since (now run {new_run[:12]})',
                      score)
        self.rebuild([('recipes/fit-a', '', 'succeeded'), ('benchmarks/score', 'fit-a', 'succeeded'),
                      ('benchmarks/score', 'zero', 'succeeded')])

    def test_an_input_has_no_current_product(self):
        self.build_all()
        with self.opened() as project:
            project._execute("UPDATE {schema}.products SET current = false WHERE reference = 'datasets/numbers'")
            self.assertEqual(builds.status(project)['recipes/fit-a']['causes'],
                             ['its input data (datasets/numbers) has no current product'])

    def test_the_code_changed(self):
        self.build_all()
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# changed\n')
        self.commit('Change training.')
        with mock.patch.object(snapshot, 'changed_since', wraps=snapshot.changed_since) as changed:
            states = self.states()
        self.assertEqual(changed.call_count, 1)  # one distinct commit among the current products
        self.assertEqual((states['datasets/numbers'], states['recipes/fit-a'], states['benchmarks/score']),
                         ('built', 'out-of-date', 'out-of-date'))
        made = self.plan('benchmarks/score')
        reasons = self.step(made, 'recipes/fit-a')['reasons']
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith('its code changed since commit') and reasons[0].endswith(': train.py'))
        self.rebuild([('recipes/fit-a', '', 'succeeded'), ('benchmarks/score', 'fit-a', 'succeeded')])
        # Two commits now among the current products: one call each.
        with mock.patch.object(snapshot, 'changed_since', wraps=snapshot.changed_since) as changed:
            self.states()
        self.assertEqual(changed.call_count, 2)

    def test_an_uncommitted_change_counts_too(self):
        self.build_all()
        self.write_code('make_data.py', (self.code / 'make_data.py').read_text() + '# changed\n')
        self.assertEqual(self.states()['datasets/numbers'], 'out-of-date')


class Scratch(BuildCase):

    def test_a_dirty_tree_is_refused_without_scratch(self):
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# not committed\n')
        with self.assertRaises(ProjectError) as raised:
            self.build('recipes/fit-a')
        self.assertEqual((raised.exception.code, raised.exception.files), ('dirty', ['train.py']))
        self.assertEqual(self.asked, [])
        self.assertEqual(self.runs(), [])

    def test_a_scratch_build_on_a_dirty_tree_is_marked(self):
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# not committed\n')
        done = self.build('recipes/fit-a', scratch=True)
        self.assertTrue(done['ok'], done)
        self.assertEqual(self.states()['recipes/fit-a'], 'built')
        self.assertTrue(all(item['scratch'] for item in self.products()))
        fit = self.runs('recipes/fit-a')[0]
        self.assertTrue(fit['scratch'])
        self.assertTrue(fit['argv'][5].startswith(str(self.code)))  # the code root in place
        made = self.plan('recipes/fit-a')
        self.assertEqual({step['reference']: (step['action'], step['scratch']) for step in made['steps']},
                         {'environments/test-python': ('ready', False), 'datasets/numbers': ('built', True),
                          'recipes/fit-a': ('built', True)})
        self.commit('Now committed.')
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# more\n')
        self.commit('And changed again.')
        self.assertEqual(self.states()['recipes/fit-a'], 'built')  # never out of date because of code


class Failures(BuildCase):
    """A step that does not succeed stops the build; later steps are not run."""

    def assert_stopped_at_fit(self, done, state):
        self.assertFalse(done['ok'])
        self.assertEqual(self.ran(done), [('datasets/numbers', '', 'succeeded'), ('recipes/fit-a', '', state)])
        self.assertEqual(self.runs('benchmarks/score'), [])
        states = self.states()
        self.assertEqual((states['datasets/numbers'], states['recipes/fit-a'], states['benchmarks/score']),
                         ('built', 'failed', 'not-built'))
        self.assertEqual(self.products('recipes/fit-a'), [])
        return self.runs('recipes/fit-a')[0]

    def test_a_failing_command(self):
        done = self.build('benchmarks/score', extra_env={'BUILDABLE_FAIL': 'train'})
        run = self.assert_stopped_at_fit(done, 'failed')
        self.assertEqual(run['exit_status'], 3)
        self.assertIn('exited with status 3', run['problem'])
        self.assertIn('failing as asked', Path(run['directory'], 'stderr.log').read_text())
        reasons = next(step for step in self.plan('benchmarks/score')['steps']
                       if step['reference'] == 'recipes/fit-a')['reasons']
        self.assertTrue(reasons[0].startswith(f'its last run {run["id"][:12]} ended failed'), reasons)
        done = self.build('benchmarks/score')  # the cause gone, the rest is built
        self.assertTrue(done['ok'])
        self.assertEqual([item['reference'] for item in done['steps']],
                         ['recipes/fit-a', 'benchmarks/score', 'benchmarks/score'])

    def test_a_timed_out_command(self):
        self.edit('recipes/fit-a', lambda document: document['run'].update(resources={'wall_hours': 0.0003}))
        started = time.monotonic()
        done = self.build('benchmarks/score', extra_env={'BUILDABLE_STALL': 'train'})
        self.assertLess(time.monotonic() - started, 20)
        run = self.assert_stopped_at_fit(done, 'timed-out')
        self.assertIn('wall-time limit', run['problem'])

    def test_a_missing_output(self):
        done = self.build('benchmarks/score', extra_env={'BUILDABLE_SKIP_OUTPUT': 'train'})
        run = self.assert_stopped_at_fit(done, 'failed')
        self.assertEqual(run['problem'], 'The declared output weights (weights.json) was not written.')
        self.assertEqual(run['exit_status'], 0)

    def test_a_refused_results_file(self):
        done = self.build('benchmarks/score', extra_env={'BUILDABLE_BAD_RESULTS': '1'})
        self.assertFalse(done['ok'])
        self.assertEqual(self.ran(done)[-1], ('benchmarks/score', 'fit-a', 'failed'))
        self.assertEqual(len(done['steps']), 3)  # the subject zero was not run
        run = self.runs('benchmarks/score')[0]
        self.assertTrue(run['problem'].startswith('The results file values.json was refused: /values/0/metric:'),
                        run['problem'])
        self.assertEqual(self.products('benchmarks/score'), [])
        self.assertEqual(self.states()['benchmarks/score'], 'failed')
        with self.opened() as project:
            self.assertEqual(project.result_summaries('score'), [])

    def test_an_environment_that_is_not_ready(self):
        with self.opened() as project:
            environments.disconnect(project, 'environments/test-python')
        with self.assertRaises(ProjectError) as raised:
            self.build('benchmarks/score')
        self.assertEqual(raised.exception.code, 'not-ready')
        self.assertIn('set it up or connect an interpreter', str(raised.exception))
        self.assertEqual(self.runs(), [])

    def test_a_missing_program_fails_before_anything_runs(self):
        self.edit('datasets/numbers', lambda document: document['run'].update(
            command=['no-such-program-tuldok', '{output}']))
        done = self.build('benchmarks/score')
        self.assertEqual(self.ran(done), [('datasets/numbers', '', 'failed')])
        run = self.runs()[0]
        self.assertEqual(run['problem'], 'The program no-such-program-tuldok was not found on PATH.')
        self.assertIsNone(run['started_at'])
        self.assertFalse(os.path.exists(run['directory']))

    def test_a_blocked_target_is_refused_before_asking(self):
        self.edit('recipes/fit-a', lambda document: document.update(
            earlier_work={'rebuild': 'needs-work', 'reason': 'Its command needs a change.'}))
        with self.assertRaises(ProjectError) as raised:
            self.build('recipes/fit-a')
        self.assertEqual(raised.exception.code, 'blocked')
        self.assertEqual(self.asked, [])
        self.assertEqual(self.runs(), [])

    def test_a_refused_confirmation_runs_nothing(self):
        done = self.build('benchmarks/score', answer=False)
        self.assertEqual((done['confirmed'], done['ok'], done['steps']), (False, False, []))
        self.assertEqual(self.runs(), [])


class Ownership(BuildCase):
    """The project lock while a command runs, the GPU lock, orphans, removal."""

    def cli(self, *arguments, **options):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.Popen([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                                env={**environment, **options.pop('env', {})}, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, **options)

    def test_the_project_is_not_held_while_a_command_runs(self):
        hold = self.temporary / 'hold'
        hold.mkdir()
        child = self.cli('build', self.folder, 'datasets/numbers', '--yes', '--env', f'BUILDABLE_HOLD=make_data:{hold}')
        try:
            deadline = time.monotonic() + 30
            while not (hold / 'started').exists():
                self.assertIsNone(child.poll(), child.stderr.read() if child.poll() is not None else '')
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.05)
            with self.opened() as project:  # a second connection opens it while the command runs
                rows = builds.runs(project)
                self.assertEqual([(row['state'], row['owner_pid']) for row in rows], [('running', child.pid)])
                self.assertEqual({row['reference']: row['state'] for row in project.definitions()}['datasets/numbers'],
                                 'running')
                self.assertEqual(plan.build_plan(project, ['datasets/numbers'])['steps'][1]['state'], 'running')
        finally:
            (hold / 'release').touch()
            stdout, stderr = child.communicate(timeout=60)
        self.assertEqual(child.returncode, 0, stderr)
        self.assertEqual(self.states()['datasets/numbers'], 'built')

    def test_gpu_steps_take_turns(self):
        first = self.cli('build', self.folder, 'steps/gpu-one', '--yes', env={'CUDA_VISIBLE_DEVICES': '7',
                                                                              'BUILDABLE_HOLD_SECONDS': '1.0'})
        try:
            line = ''
            while not line.startswith('start'):
                line = first.stdout.readline()
                self.assertTrue(line, first.stderr.read() if first.poll() is not None else 'no start line')
            second = self.cli('build', self.folder, 'steps/gpu-two', '--yes', env={'BUILDABLE_HOLD_SECONDS': '0.2'})
            outputs = [process.communicate(timeout=60) for process in (second,)]
        finally:
            rest = first.communicate(timeout=60)
        self.assertEqual(first.returncode, 0, rest[1])
        self.assertEqual(second.returncode, 0, outputs[0][1])
        times = {}
        for item in self.products():
            times[item['reference']] = json.loads(Path(item['directory'], 'times.json').read_text())
        self.assertGreaterEqual(times['steps/gpu-two']['started'], times['steps/gpu-one']['ended'])
        self.assertEqual(times['steps/gpu-one']['cuda_visible_devices'], '7')  # left as the caller has it
        self.assertTrue((self.home / builds.GPU_LOCK).exists())

    def test_an_orphaned_running_row_becomes_unknown(self):
        gone = subprocess.Popen([sys.executable, '-c', 'pass'])
        gone.wait()
        with self.opened() as project:
            for run_id, pid, boot in (('a' * 32, gone.pid, builds.boot_id()), ('b' * 32, os.getpid(), 'another-boot'),
                                      ('c' * 32, os.getpid(), builds.boot_id())):
                project._execute('''INSERT INTO {schema}.runs (id, reference, plan_id, state, scratch, commit,
                                        definition, inputs, argv, env, directory, owner_pid, owner_boot, queued_at)
                                    VALUES (%s, 'steps/gpu-one', 'p', 'running', false, '', '{{}}', '{{}}', '[]',
                                            '{{}}', '/nowhere', %s, %s, now())''', (run_id, pid, boot))
        rows = {row['id']: row for row in self.runs()}
        self.assertEqual(rows['a' * 32]['state'], 'unknown')
        self.assertEqual(rows['b' * 32]['state'], 'unknown')
        self.assertIn('is gone', rows['a' * 32]['problem'])
        self.assertEqual(rows['c' * 32]['state'], 'running')  # this process is alive: left alone
        with self.opened() as project:
            project._execute("UPDATE {schema}.runs SET owner_pid = %s WHERE id = %s", (gone.pid, 'c' * 32))
        self.assertEqual(self.states()['steps/gpu-one'], 'failed')
        self.assertEqual(self.runs()[0]['state'], 'unknown')

    def test_removing_a_definition_removes_its_records_not_its_files(self):
        done = self.build('recipes/fit-b', 'steps/gpu-two', extra_env={'BUILDABLE_HOLD_SECONDS': '0'})
        self.assertTrue(done['ok'], done)
        directory = self.products('recipes/fit-b')[0]['directory']
        with self.opened() as project:
            project.remove_definition('recipes/fit-b')
        self.assertEqual(self.runs('recipes/fit-b'), [])
        self.assertEqual(self.products('recipes/fit-b'), [])
        self.assertTrue(os.path.isdir(directory))
        (self.folder / 'steps' / 'gpu-two.json').unlink()  # removed on disk, then opened
        self.assertEqual(self.runs('steps/gpu-two'), [])
        self.assertEqual(self.products('steps/gpu-two'), [])
        self.assertEqual([item['reference'] for item in self.products()], ['datasets/numbers'])


class Commands(BuildCase):
    """build, runs and products on the command line."""

    def run_cli(self, *arguments, stdin=''):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                              env=environment, input=stdin, capture_output=True, text=True, timeout=120)

    def test_build_runs_and_products(self):
        refused = self.run_cli('build', self.folder, 'benchmarks/score', stdin='n\n')
        self.assertEqual(refused.returncode, 1)
        self.assertTrue(refused.stdout.endswith('Build this? [y/N] \nNothing was built.\n'), refused.stdout)
        self.assertEqual(self.runs(), [])

        done = self.run_cli('build', self.folder, 'benchmarks/score', stdin='y\n')
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], '3 steps to build, 0 to set up, 0 blocked, 1 ready: benchmarks/score can be')
        starts = [line.split() for line in lines if line.startswith('start')]
        ends = [line.split() for line in lines if line.startswith('end')]
        self.assertEqual([row[1:3] for row in starts], [['datasets/numbers', 'run'], ['recipes/fit-a', 'run'],
                                                        ['benchmarks/score', 'fit-a'], ['benchmarks/score', 'zero']])
        self.assertEqual([row[-3] for row in ends], ['succeeded'] * 4)
        self.assertEqual(lines[-1], 'Done: 4 runs succeeded, 0 already built.')

        again = self.run_cli('build', self.folder, 'benchmarks/score')  # nothing to do: no question asked
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn('0 steps to build, 0 to set up, 0 blocked, 1 ready, 3 built', again.stdout)
        self.assertEqual(again.stdout.splitlines()[-1], 'Nothing was run: everything asked for is built.')

        runs = self.run_cli('runs', self.folder)
        self.assertEqual(runs.returncode, 0, runs.stderr)
        table = runs.stdout.splitlines()
        self.assertEqual(table[0].split(), ['run', 'reference', 'subject', 'state', 'started', 'seconds'])
        self.assertEqual(len(table), 5)
        self.assertEqual(table[-1].split()[1:4], ['datasets/numbers', '-', 'succeeded'])
        listed = json.loads(self.run_cli('runs', self.folder, 'recipes/fit-a', '--json').stdout)
        self.assertEqual([(row['reference'], row['state']) for row in listed], [('recipes/fit-a', 'succeeded')])

        products = self.run_cli('products', self.folder)
        self.assertEqual(products.returncode, 0, products.stderr)
        table = products.stdout.splitlines()
        self.assertEqual(table[0].split(), ['reference', 'subject', 'run', 'size', 'scratch', 'directory'])
        self.assertEqual([row.split()[:2] for row in table[1:]], [['benchmarks/score', 'fit-a'],
                                                                  ['benchmarks/score', 'zero'],
                                                                  ['datasets/numbers', '-'], ['recipes/fit-a', '-']])
        listed = json.loads(self.run_cli('products', self.folder, 'benchmarks/score', '--json').stdout)
        self.assertEqual([row['subject'] for row in listed], ['fit-a', 'zero'])
        self.assertFalse(any(row['scratch'] for row in listed))

    def test_refusals_on_the_command_line(self):
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# not committed\n')
        dirty = self.run_cli('build', self.folder, 'recipes/fit-a', '--yes')
        self.assertEqual(dirty.returncode, 1)
        self.assertIn('changes that are not committed', dirty.stderr)
        self.assertIn('changed  train.py', dirty.stderr)
        scratch = self.run_cli('build', self.folder, 'recipes/fit-a', '--yes', '--scratch')
        self.assertEqual(scratch.returncode, 0, scratch.stderr)
        self.assertIn('scratch', self.run_cli('products', self.folder, 'recipes/fit-a').stdout.splitlines()[1])
        failed = self.run_cli('build', self.folder, 'benchmarks/score', '--yes', '--scratch',
                              '--env', 'BUILDABLE_FAIL=score')
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout.splitlines()[-1],
                         'Stopped: benchmarks/score did not succeed; later steps were not run.')
        usage = self.run_cli('build', self.folder, 'recipes/fit-a', '--env', 'not a pair')
        self.assertEqual(usage.returncode, 2)
        none = self.run_cli('build', self.folder)
        self.assertEqual(none.returncode, 2)


if __name__ == '__main__':
    unittest.main()
