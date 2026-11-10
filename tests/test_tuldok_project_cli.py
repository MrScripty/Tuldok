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
        self.assertIn('total        10', lines)
        self.assertIn('state           count', lines)
        self.assertIn('cannot-rebuild  1', lines)
        self.assertTrue(self.schema_exists())
        again = self.run_json('open', self.folder)
        self.assertEqual(again['project_id'], self.project_id)
        self.assertEqual(again['kinds']['recipe'], 3)
        self.assertEqual(again['states'], {'cannot-rebuild': 1, 'none': 3, 'not-built': 5, 'not-set-up': 1})
        self.assertIsInstance(again['seconds'], float)

    def test_list(self):
        lines = self.run_ok('list', self.folder).splitlines()
        self.assertEqual(len(lines), 10)
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
        self.assertEqual(len(nodes.splitlines()), 10)
        self.assertIn('recipes/stepper-k2      input:start         recipes/stepper-k1', edges.splitlines())
        drawn = self.run_json('graph', self.folder)
        self.assertEqual(len(drawn['nodes']), 10)
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
        self.assertEqual(len(self.run_json('list', moved / 'project', '--rebind')), 10)

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


if __name__ == '__main__':
    unittest.main()
