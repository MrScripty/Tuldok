"""The command line, `python -m tuldok_project <command> FOLDER` (spec section 4.6), run as a child process.

Database tests run only when TULDOK_DATABASE_URL names a disposable cluster
(see docs/plans/definition-first-projects/spec-m1-m2.md, section 1). Each test
copies tests/fixtures/tuldok_project/minimal into a temporary directory, gives
it a fresh project id and drops that project's schema afterwards. The tests
check the text a person reads, that --json parses, the exit statuses, and
that every command leaves the project closed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from metadata import connection_info  # noqa: E402
from tuldok_project import store  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')


def run(*arguments, database=True, stdin=None):
    """Run the command line; return the CompletedProcess with text stdout and stderr."""
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    if not database:
        environment.pop('TULDOK_DATABASE_URL', None)
    return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                          env=environment, input=stdin, capture_output=True, text=True, timeout=120)


class FolderCase(unittest.TestCase):
    """A fresh copy of the fixture with its own project id."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        shutil.copytree(FIXTURE, self.temporary / 'minimal')
        self.folder = self.temporary / 'minimal' / 'project'
        self.project_id = uuid.uuid4().hex
        project_file = self.folder / 'tuldok.json'
        document = json.loads(project_file.read_text(encoding='utf-8'))
        document['id'] = self.project_id
        project_file.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.schema = f'project_{self.project_id}'

    def run_ok(self, *arguments):
        done = run(*arguments)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, '')
        return done.stdout

    def run_json(self, *arguments):
        return json.loads(self.run_ok(*arguments, '--json'))


class WithoutDatabase(FolderCase):

    def test_check_still_works_without_a_database(self):
        done = run('check', self.folder, database=False)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertTrue(done.stdout.endswith(f'0 errors, 0 warnings in {self.folder}\n'))
        report = json.loads(run('check', self.folder, '--json', database=False).stdout)
        self.assertTrue(report['ok'])

    def test_store_commands_need_a_database(self):
        for arguments in (('open', self.folder), ('list', self.folder), ('show', self.folder, 'models/stepper'),
                          ('graph', self.folder), ('status', self.folder), ('save', self.folder),
                          ('forget', self.folder)):
            done = run(*arguments, database=False)
            self.assertEqual(done.returncode, 2, arguments)
            self.assertIn('--database-url', done.stderr)
            self.assertIn('TULDOK_DATABASE_URL', done.stderr)
            self.assertEqual(done.stdout, '')

    def test_usage_errors_exit_2(self):
        for arguments in (('list',), ('frobnicate', self.folder), ('list', self.folder, '--kind', 'thing'),
                          ('open', self.folder, '--keep', '--discard'), ('show', self.folder)):
            done = run(*arguments)
            self.assertEqual(done.returncode, 2, arguments)
            self.assertIn('usage:', done.stderr)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class StoreCommands(FolderCase):

    def setUp(self):
        super().setUp()
        self.addCleanup(store.drop_project, self.project_id)

    def schema_exists(self):
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            return connection.execute('SELECT 1 FROM pg_namespace WHERE nspname = %s',
                                      (self.schema,)).fetchone() is not None

    def write_definition(self, path, change):
        """Write a changed copy of a fixture definition to path and return the text."""
        document = json.loads((self.folder / 'datasets' / 'waves.json').read_text(encoding='utf-8'))
        change(document)
        text = json.dumps(document, indent=2) + '\n'
        path.write_text(text, encoding='utf-8')
        return text

    def test_open_prints_counts_and_time_then_attaches(self):
        output = self.run_ok('open', self.folder)
        lines = output.splitlines()
        self.assertRegex(lines[0], rf'^Opened Minimal surrogate project \({self.project_id}\) from .* in \d+\.\d\d s\.$')
        self.assertIn('kind         count', lines)
        self.assertIn('recipe       3', lines)
        self.assertIn('total        12', lines)
        self.assertIn('state           count', lines)
        self.assertIn('cannot-rebuild  1', lines)
        self.assertTrue(self.schema_exists())
        again = self.run_json('open', self.folder)
        self.assertEqual(again['project_id'], self.project_id)
        self.assertEqual(again['kinds']['recipe'], 3)
        self.assertEqual(again['states'], {'cannot-rebuild': 1, 'none': 5, 'not-built': 5, 'not-set-up': 1})
        self.assertIsInstance(again['seconds'], float)

    def test_list(self):
        lines = self.run_ok('list', self.folder).splitlines()
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines[0].split(None, 2), ['benchmarks/rollout', 'not-built', 'Rollout error'])
        self.assertEqual(len({line.index('not-built') for line in lines if ' not-built ' in line}), 1)  # aligned
        rows = self.run_json('list', self.folder, '--kind', 'recipe')
        self.assertEqual([row['reference'] for row in rows],
                         ['recipes/early-fit', 'recipes/stepper-k1', 'recipes/stepper-k2'])
        self.assertEqual(rows[0]['state'], 'cannot-rebuild')

    def test_show(self):
        output = self.run_ok('show', self.folder, 'datasets/waves')
        head, text = output.split('\n\n', 1)
        lines = head.splitlines()
        self.assertEqual(lines[:4], ['reference  datasets/waves', 'title      Wave scenes', 'kind       dataset',
                                     'state      not-built'])
        self.assertIn('uses       steps/solver          input:solver', lines)
        self.assertIn('used by    recipes/stepper-k1    input:training', lines)
        self.assertEqual(text, (self.folder / 'datasets' / 'waves.json').read_text(encoding='utf-8'))
        shown = self.run_json('show', self.folder, 'models/stepper')
        self.assertEqual(shown['uses'], [])
        self.assertIn({'reference': 'recipes/stepper-k1', 'role': 'model'}, shown['used_by'])
        self.assertEqual(shown['document']['kind'], 'model')

    def test_show_of_a_missing_definition_exits_1(self):
        done = run('show', self.folder, 'datasets/nothing')
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, 'There is no definition datasets/nothing.\n')

    def test_graph_and_order(self):
        nodes, edges = self.run_ok('graph', self.folder).split('\n\n')
        self.assertEqual(len(nodes.splitlines()), 12)
        self.assertIn('recipes/stepper-k2          input:start         recipes/stepper-k1', edges.splitlines())
        drawn = self.run_json('graph', self.folder)
        self.assertEqual(len(drawn['nodes']), 12)
        self.assertEqual(len(drawn['edges']), len(edges.splitlines()))
        order = [line.split() for line in self.run_ok('graph', self.folder, '--order').splitlines()]
        references = [reference for reference, _ in order]
        self.assertLess(references.index('steps/solver'), references.index('datasets/waves'))
        self.assertIn(['recipes/early-fit', 'cannot-rebuild'], order)
        self.assertEqual([item['reference'] for item in self.run_json('graph', self.folder, '--order')], references)

    def test_set_status_save(self):
        edit = self.temporary / 'waves.json'
        text = self.write_definition(edit, lambda d: d.update(title='Waves, edited'))
        self.assertIn('run save', self.run_ok('set', self.folder, 'datasets/waves', edit))
        self.assertEqual(self.run_ok('status', self.folder), 'unsaved  datasets/waves\n')
        self.assertEqual(self.run_json('status', self.folder)['unsaved'], ['datasets/waves'])
        self.assertIn('not-built (unsaved)', self.run_ok('list', self.folder))
        self.assertEqual(self.run_ok('save', self.folder), 'wrote  datasets/waves\n')
        self.assertEqual((self.folder / 'datasets' / 'waves.json').read_text(encoding='utf-8'), text)
        self.assertEqual(self.run_json('save', self.folder), {'written': [], 'deleted': [], 'results_written': [],
                                                           'results_deleted': []})
        self.assertEqual(self.run_ok('status', self.folder),
                         'Nothing is unsaved and no file changed on disk since the last import.\n')

    def test_refused_edit_prints_its_problems_and_changes_nothing(self):
        before = self.run_json('show', self.folder, 'datasets/waves')
        edit = self.temporary / 'waves.json'
        self.write_definition(edit, lambda d: (d.pop('title'), d['run']['inputs'].update(more='steps/nothing')))
        done = run('set', self.folder, 'datasets/waves', edit)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, '')
        lines = done.stderr.splitlines()
        self.assertEqual(lines[0], 'datasets/waves cannot be set; see the problems.')
        self.assertTrue(any(line.startswith('error  datasets/waves.json  -  ') or
                            line.startswith('error  datasets/waves.json  /title  ') for line in lines[1:]), lines)
        self.assertTrue(any(line.startswith('error  datasets/waves.json  /run/inputs/more  ') for line in lines), lines)
        self.assertEqual(self.run_json('show', self.folder, 'datasets/waves'), before)
        not_json = self.temporary / 'broken.json'
        not_json.write_text('{"format": ', encoding='utf-8')
        self.assertEqual(run('set', self.folder, 'datasets/waves', not_json).returncode, 1)
        missing = run('set', self.folder, 'datasets/waves', self.temporary / 'absent.json')
        self.assertEqual(missing.returncode, 2)
        self.assertIn('cannot be read', missing.stderr)

    def test_remove_in_use_is_refused_and_unused_is_saved_as_a_deletion(self):
        done = run('remove', self.folder, 'steps/solver')
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr, 'steps/solver is used by datasets/waves; change those first.\n')
        self.assertIn('run save', self.run_ok('remove', self.folder, 'charts/speed-accuracy'))
        self.assertEqual(self.run_ok('status', self.folder), 'removed  charts/speed-accuracy\n')
        self.assertEqual(self.run_ok('save', self.folder), 'deleted  charts/speed-accuracy\n')
        self.assertFalse((self.folder / 'charts' / 'speed-accuracy.json').exists())

    def test_folder_with_errors_is_refused_with_its_problems(self):
        path = self.folder / 'datasets' / 'waves.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        document.pop('title')
        path.write_text(json.dumps(document), encoding='utf-8')
        done = run('list', self.folder)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, '')
        self.assertIn('has errors', done.stderr.splitlines()[0])
        self.assertIn('error  datasets/waves.json  ', done.stderr)
        self.assertFalse(self.schema_exists())

    def test_conflict_needs_keep_or_discard(self):
        edit = self.temporary / 'waves.json'
        self.write_definition(edit, lambda d: d.update(title='Edited here'))
        self.run_ok('set', self.folder, 'datasets/waves', edit)
        self.write_definition(self.folder / 'datasets' / 'waves.json', lambda d: d.update(title='Edited on disk'))
        done = run('open', self.folder)
        self.assertEqual(done.returncode, 1)
        self.assertIn('datasets/waves', done.stderr)
        self.assertEqual(self.run_json('show', self.folder, 'datasets/waves', '--keep')['title'], 'Edited here')
        # --keep took the disk version as the new base, so the edit stays unsaved and no conflict remains.
        self.write_definition(self.folder / 'datasets' / 'waves.json', lambda d: d.update(title='Edited again'))
        self.assertEqual(run('list', self.folder).returncode, 1)
        self.run_ok('open', self.folder, '--discard')
        self.assertEqual(self.run_json('show', self.folder, 'datasets/waves')['title'], 'Edited again')

    def test_a_moved_folder_needs_rebind(self):
        self.run_ok('open', self.folder)
        moved = self.temporary / 'moved'
        shutil.copytree(self.temporary / 'minimal', moved)
        done = run('list', moved / 'project')
        self.assertEqual(done.returncode, 1)
        self.assertIn('rebind', done.stderr)
        self.assertEqual(len(self.run_json('list', moved / 'project', '--rebind')), 12)

    def test_open_elsewhere_is_busy_and_every_command_releases_the_lock(self):
        for arguments in (('open',), ('list',), ('show', 'models/stepper'), ('graph',), ('status',), ('save',)):
            self.run_ok(arguments[0], self.folder, *arguments[1:])
        held = store.open_project(self.folder)  # would raise 'busy' if a command had kept the lock
        try:
            done = run('list', self.folder)
            self.assertEqual(done.returncode, 1)
            self.assertEqual(done.stderr, 'This project is already open in another session.\n')
            self.assertEqual(run('forget', self.folder).returncode, 1)
        finally:
            held.close()

    def test_forget_drops_the_copy_and_leaves_the_folder(self):
        self.run_ok('open', self.folder)
        files = sorted(path.relative_to(self.folder) for path in self.folder.rglob('*'))
        self.assertIn('holds no copy', self.run_ok('forget', self.folder))
        self.assertFalse(self.schema_exists())
        self.assertEqual(sorted(path.relative_to(self.folder) for path in self.folder.rglob('*')), files)
        self.assertIn('holds no copy', self.run_ok('forget', self.folder))  # forgetting twice is fine



@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class ChartCommands(FolderCase):
    """chart and report, and the two ways of naming a benchmark or a chart."""

    def setUp(self):
        super().setUp()
        self.addCleanup(store.drop_project, self.project_id)

    def test_chart_prints_its_data_as_text_or_json(self):
        lines = self.run_ok('chart', self.folder, 'rollout-ranking').splitlines()
        self.assertEqual(lines[0].split(), ['chart', 'charts/rollout-ranking', 'ranking'])
        self.assertIn('metric     rmse: median Rollout RMSE (m/s), lower is better', lines)
        self.assertIn('horizon = 8', lines)
        self.assertEqual(lines[lines.index('horizon = 1') + 1].split(), ['rank', 'subject', 'value', 'count'])
        self.assertEqual(lines[lines.index('horizon = 1') + 2].split(), ['1', 'stepper-k2', '0.3125', '4'])
        self.assertEqual(lines[-1], '1 of 3 subjects has no value: early-fit.')
        data = self.run_json('chart', self.folder, 'charts/speed-accuracy')
        self.assertEqual([(item['subject'], item['frontier']) for item in data['series'][0]['points']],
                         [('stepper-k2', True), ('stepper-k1', False), ('early-fit', False)])
        progression = self.run_ok('chart', self.folder, 'charts/rollout-progression').splitlines()
        self.assertIn(['0', 'early-fit', '0.625', '0.625', '2026-03-14'], [line.split() for line in progression])
        comparison = self.run_ok('chart', self.folder, 'rollout-comparison').splitlines()
        self.assertIn(['subject', 'rmse', 'seconds'], [line.split() for line in comparison])
        self.assertEqual(comparison[-1], 'Every one of the 3 subjects has a value.')

    def test_chart_svg_is_written_in_either_theme(self):
        light, dark = self.temporary / 'light.svg', self.temporary / 'dark.svg'
        output = self.run_ok('chart', self.folder, 'rollout-ranking', '--svg', light)
        self.assertTrue(output.endswith(f'Wrote {light} ({light.stat().st_size} bytes).\n'))
        data = self.run_json('chart', self.folder, 'rollout-ranking', '--svg', dark, '--theme', 'dark')
        self.assertEqual(data['chart'], 'charts/rollout-ranking')  # stdout holds the JSON alone
        for path in (light, dark):
            root = ElementTree.fromstring(path.read_text(encoding='utf-8'))
            self.assertEqual(root.find('{http://www.w3.org/2000/svg}title').text, 'Rollout error by subject')
        self.assertIn('#171c22', dark.read_text(encoding='utf-8'))
        self.assertNotEqual(light.read_bytes(), dark.read_bytes())
        self.run_ok('chart', self.folder, 'charts/rollout-ranking', '--svg', self.temporary / 'again.svg')
        self.assertEqual((self.temporary / 'again.svg').read_bytes(), light.read_bytes())
        blocked = run('chart', self.folder, 'rollout-ranking', '--svg', self.temporary / 'absent' / 'x.svg')
        self.assertEqual(blocked.returncode, 1)
        self.assertIn('cannot be written', blocked.stderr)

    def test_report_writes_one_page(self):
        page = self.temporary / 'report.html'
        output = self.run_ok('report', self.folder, '--output', page, '--theme', 'dark')
        self.assertEqual(output, f'Wrote {page} (4 charts, {page.stat().st_size} bytes).\n')
        text = page.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('<!DOCTYPE html>'))
        self.assertEqual(text.count('<svg '), 4)
        self.assertIn('color-scheme: dark', text)
        self.assertEqual(run('report', self.folder).returncode, 2)  # --output is required

    def test_benchmarks_and_charts_by_name_or_reference(self):
        for command in (('results',), ('values', '--subject', 'stepper-k1')):
            bare = self.run_json(command[0], self.folder, 'rollout', *command[1:])
            self.assertEqual(self.run_json(command[0], self.folder, 'benchmarks/rollout', *command[1:]), bare)
        self.assertEqual(len(self.run_json('results', self.folder, 'benchmarks/rollout')), 12)
        self.assertIn('benchmarks/rollout has no summary rows', self.run_ok('results', self.folder, 'benchmarks/rollout',
                                                                            '--subject', 'nobody'))
        self.assertEqual(self.run_json('chart', self.folder, 'charts/speed-accuracy'),
                         self.run_json('chart', self.folder, 'speed-accuracy'))
        for arguments in (('results', 'recipes/early-fit'), ('values', 'charts/x', '--subject', 'a'),
                          ('chart', 'benchmarks/rollout'), ('chart', 'Bad Name')):
            done = run(arguments[0], self.folder, *arguments[1:])
            self.assertEqual(done.returncode, 2, arguments)
            self.assertIn('is not a name or a reference', done.stderr)
        missing = run('chart', self.folder, 'nothing')
        self.assertEqual(missing.returncode, 1)
        self.assertEqual(missing.stderr, 'There is no chart charts/nothing.\n')

    def test_chart_of_a_benchmark_without_results_is_empty(self):
        (self.folder / 'results' / 'rollout.csv').unlink()
        data = self.run_json('chart', self.folder, 'rollout-ranking')
        self.assertEqual([series['points'] for series in data['series']], [])
        self.assertEqual(data['missing'], ['stepper-k1', 'stepper-k2', 'early-fit'])
        drawing = self.temporary / 'empty.svg'
        self.run_ok('chart', self.folder, 'rollout-ranking', '--svg', drawing)
        self.assertIn('No results yet: none of the 3 subjects of benchmarks/rollout', drawing.read_text(encoding='utf-8'))


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class PlanCommand(FolderCase):
    """plan: the opening sentence, the steps in order, the causes, the totals; and --json."""

    def setUp(self):
        super().setUp()
        self.addCleanup(store.drop_project, self.project_id)

    def test_a_buildable_plan_as_text(self):
        lines = self.run_ok('plan', self.folder, 'benchmarks/rollout').splitlines()
        self.assertEqual(lines[0], '5 steps to build, 1 to set up, 0 blocked: benchmarks/rollout can be built.')
        self.assertEqual(lines[2].split(), ['#', 'action', 'gpu', 'disk', 'time', 'reference'])
        rows = [line.split() for line in lines[3:] if line[:1].isdigit()]
        self.assertEqual([row[:2] + row[-1:] for row in rows], [
            ['1', 'set-up', 'environments/lab-cpu'], ['2', 'build', 'steps/solver'], ['3', 'build', 'datasets/waves'],
            ['4', 'build', 'recipes/stepper-k1'], ['5', 'build', 'recipes/stepper-k2'],
            ['6', 'build', 'benchmarks/rollout']])
        self.assertIn(['4', 'build', '-', '0.1', 'GB', '0.5', 'h', 'recipes/stepper-k1'], rows)
        self.assertIn(['2', 'build', '-', '?', '0.1', 'h', 'steps/solver'], rows)  # no gpu declared: none needed
        reference_column = lines[2].index('reference')
        self.assertTrue(all(line.index('environments/lab-cpu') == reference_column
                            for line in lines if line.startswith('1 ')))
        self.assertIn('start: recipes/stepper-k1 (weights)', [line.strip() for line in lines])
        self.assertIn('skips 1 whose recipe is blocked: early-fit', [line.strip() for line in lines])
        self.assertEqual(lines[-4:], ['To build: 5 steps, 0 on a GPU.',
                                      'Disk: 0.1 GB declared; 4 of 5 declare none.',
                                      'Time: 0.6 h declared; 3 of 5 declare none.',
                                      'Figures are as the definitions declare them; no command was run.'])
        self.assertTrue(all(len(line) <= 80 for line in lines), lines)

    def test_a_blocked_target_names_its_cause_and_still_exits_0(self):
        lines = self.run_ok('plan', self.folder, 'recipes/early-fit').splitlines()
        self.assertEqual(lines[0], '0 steps to build, 0 to set up, 1 blocked: recipes/early-fit cannot be built.')
        start = lines.index('recipes/early-fit cannot be built:')
        self.assertEqual(lines[start + 1], '  no  recipes/early-fit')
        self.assertEqual(' '.join(line.strip() for line in lines[start + 2:start + 4]),
                         'Trained by the earlier study harness; its command and training data were not recorded.')
        self.assertEqual(lines[-1], 'Nothing would be built, so there are no totals.')
        made = self.run_json('plan', self.folder, 'recipes/early-fit')
        self.assertFalse(made['buildable'])
        self.assertEqual(made['steps'][0]['blocked_by'][0]['rebuild'], 'no')

    def test_json_charts_models_and_all(self):
        made = self.run_json('plan', self.folder, 'charts/rollout-ranking', 'models/stepper')
        self.assertEqual(made['targets'], ['benchmarks/rollout', 'models/stepper'])
        for field in ('buildable', 'counts', 'gpu_steps', 'disk_gb', 'disk_unknown', 'wall_hours', 'wall_unknown',
                      'notes', 'steps'):
            self.assertIn(field, made)
        self.assertTrue(made['buildable'])
        self.assertEqual(made['counts'], {'build': 5, 'set-up': 1, 'blocked': 0})
        model = self.run_ok('plan', self.folder, 'models/stepper').splitlines()
        self.assertEqual(model[0], 'Nothing to build for models/stepper.')
        self.assertEqual(' '.join(model[1:3]),
                         'models/stepper is a model; a model is not built, only the recipes that train it.')
        self.assertEqual(model[-1], 'Nothing would be built, so there are no totals.')
        both = self.run_ok('plan', self.folder, 'steps/solver', 'recipes/stepper-k1').splitlines()
        self.assertEqual(both[0], '3 steps to build, 1 to set up, 0 blocked: all 2 targets can be built.')
        self.assertIn('Time: 0.6 h declared; 1 of 3 declares none.', both)
        alone = self.run_ok('plan', self.folder, 'datasets/waves').splitlines()
        self.assertIn('Disk: no step declares it.', alone)
        every = self.run_ok('plan', self.folder, '--all').splitlines()
        self.assertEqual(every[:2], ['5 steps to build, 1 to set up, 1 blocked: 1 of 6 targets (every dataset,',
                                     'recipe, step and benchmark) cannot be built.'])
        self.assertFalse(self.run_json('plan', self.folder, '--all')['buildable'])

    def test_unknown_references_and_usage(self):
        done = run('plan', self.folder, 'steps/solver', 'datasets/nothing')
        self.assertEqual((done.returncode, done.stdout, done.stderr), (1, '', 'There is no definition datasets/nothing.\n'))
        done = run('plan', self.folder)
        self.assertEqual(done.returncode, 2)
        self.assertIn('--all', done.stderr)


if __name__ == '__main__':
    unittest.main()
