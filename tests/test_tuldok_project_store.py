"""The database copy of a project folder: open, states, edit and save (spec sections 4.1 to 4.5).

Database tests run only when TULDOK_DATABASE_URL names a disposable cluster
(see docs/plans/definition-first-projects/spec-m1-m2.md, section 1). Each test
copies tests/fixtures/tuldok_project/minimal into a temporary directory, gives
it a fresh project id and drops that project's schema afterwards, so tests
share no state. The states of section 4.3 are also tested as a pure function.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from metadata import connection_info  # noqa: E402
from tuldok_project import check, graph, store  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')

FIXTURE_STATES = {
    'benchmarks/rollout': 'not-built',  # its early-fit subject carries nothing
    'charts/rollout-ranking': 'none',
    'charts/speed-accuracy': 'none',
    'datasets/waves': 'not-built',
    'environments/lab-cpu': 'not-set-up',
    'models/stepper': 'none',
    'recipes/early-fit': 'cannot-rebuild',
    'recipes/stepper-k1': 'not-built',
    'recipes/stepper-k2': 'not-built',
    'steps/solver': 'not-built',
}

CLEAN_STATUS = {'unsaved': [], 'removed': [], 'added': [], 'changed': [], 'missing': [], 'irregular': [],
                'results_unsaved': [], 'results_changed': []}



def _fixture_documents():
    project = FIXTURE / 'project'
    found = {}
    for path in sorted(project.glob('*/*.json')):
        found[f'{path.parent.name}/{path.stem}'] = json.loads(path.read_text(encoding='utf-8'))
    return found


class States(unittest.TestCase):
    """graph.states, section 4.3, without a database."""

    def setUp(self):
        self.documents = _fixture_documents()

    def mark(self, reference, rebuild):
        self.documents[reference]['earlier_work'] = {'rebuild': rebuild, 'reason': 'Test.'}

    def test_fixture(self):
        self.assertEqual(graph.states(self.documents), FIXTURE_STATES)

    def test_needs_work_travels_up_through_inputs(self):
        self.mark('steps/solver', 'needs-work')
        states = graph.states(self.documents)
        for reference in ('steps/solver', 'datasets/waves', 'recipes/stepper-k1', 'recipes/stepper-k2',
                          'benchmarks/rollout'):
            self.assertEqual(states[reference], 'needs-work', reference)
        self.assertEqual(states['recipes/early-fit'], 'cannot-rebuild')
        self.assertEqual(states['environments/lab-cpu'], 'not-set-up')

    def test_cannot_rebuild_travels_up_and_wins_over_needs_work(self):
        self.mark('steps/solver', 'needs-work')
        self.mark('recipes/stepper-k1', 'no')
        states = graph.states(self.documents)
        self.assertEqual(states['datasets/waves'], 'needs-work')
        self.assertEqual(states['recipes/stepper-k1'], 'cannot-rebuild')
        self.assertEqual(states['recipes/stepper-k2'], 'cannot-rebuild')  # k1 is no, waves needs-work
        self.assertEqual(states['benchmarks/rollout'], 'needs-work')  # k1 is only a subject of it

    def test_only_input_edges_carry_states(self):
        self.mark('models/stepper', 'no')  # used by recipes through "model", not an input
        states = graph.states(self.documents)
        self.assertEqual(states['models/stepper'], 'cannot-rebuild')
        self.assertEqual(states['recipes/stepper-k1'], 'not-built')

    def test_cycle_is_tolerated(self):
        self.documents['steps/solver']['run']['inputs'] = {'scenes': 'datasets/waves'}
        self.mark('datasets/waves', 'needs-work')
        states = graph.states(self.documents)
        self.assertEqual(states['steps/solver'], 'needs-work')
        self.assertEqual(states['datasets/waves'], 'needs-work')


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class StoreCase(unittest.TestCase):
    """A fresh copy of the fixture with its own project id, dropped afterwards."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.temporary = Path(directory.name)
        self.base = self.temporary / 'minimal'
        shutil.copytree(FIXTURE, self.base)
        self.folder = self.base / 'project'
        self.project_id = uuid.uuid4().hex
        project_file = self.folder / 'tuldok.json'
        document = json.loads(project_file.read_text(encoding='utf-8'))
        document['id'] = self.project_id
        project_file.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.schema = f'project_{self.project_id}'
        self.opened = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for project in self.opened:
            project.close()
        store.drop_project(self.project_id)

    def open(self, folder=None, **options):
        project = store.open_project(folder or self.folder, **options)
        self.opened.append(project)
        return project

    def close(self, project):
        project.close()
        self.opened.remove(project)

    def database(self):
        connection = psycopg.connect(connection_info(), autocommit=True)
        self.addCleanup(connection.close)
        return connection

    def dump(self):
        """Every row of the project's tables, for asserting that nothing changed."""
        connection = self.database()
        if connection.execute('SELECT 1 FROM pg_namespace WHERE nspname = %s', (self.schema,)).fetchone() is None:
            return None
        tables = {}
        for table in ('state', 'definitions', 'edges', 'results_files', 'result_summaries', 'result_values'):
            query = psycopg.sql.SQL('SELECT * FROM {}.{} ORDER BY 1, 2').format(
                psycopg.sql.Identifier(self.schema), psycopg.sql.Identifier(table))
            tables[table] = connection.execute(query).fetchall()
        return tables

    def read(self, reference):
        return (self.folder / f'{reference}.json').read_text(encoding='utf-8')

    def write(self, reference, text, folder=None):
        path = (folder or self.folder) / f'{reference}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def edited(self, reference, change, folder=None):
        """The file's document with change(document) applied, as indented text."""
        document = json.loads(((folder or self.folder) / f'{reference}.json').read_text(encoding='utf-8'))
        change(document)
        return json.dumps(document, indent=4) + '\n'

    def counting_checker(self):
        patcher = mock.patch.object(check, 'check_folder', wraps=check.check_folder)
        checker = patcher.start()
        self.addCleanup(patcher.stop)
        return checker


class Open(StoreCase):

    def test_first_open_imports_every_definition(self):
        project = self.open()
        summary = project.summary()
        self.assertEqual(summary['project_id'], self.project_id)
        self.assertEqual(summary['folder'], os.path.realpath(self.folder))
        self.assertEqual(summary['code_root'], '../code')
        self.assertEqual(summary['kinds'], {'benchmark': 1, 'chart': 2, 'dataset': 1, 'environment': 1,
                                            'model': 1, 'recipe': 3, 'step': 1})
        self.assertEqual(summary['states'], {'cannot-rebuild': 1, 'none': 3, 'not-built': 5, 'not-set-up': 1})
        rows = project.definitions()
        self.assertEqual({row['reference']: row['state'] for row in rows}, FIXTURE_STATES)
        self.assertEqual([row['reference'] for row in project.definitions(kind='chart')],
                         ['charts/rollout-ranking', 'charts/speed-accuracy'])

        shown = project.definition('datasets/waves')
        self.assertEqual(shown['text'], self.read('datasets/waves'))  # the exact file text
        self.assertEqual(shown['document']['run']['settings']['layout'], {'grid': [16, 16]})
        self.assertEqual(shown['uses'], [{'reference': 'environments/lab-cpu', 'role': 'environment'},
                                         {'reference': 'steps/solver', 'role': 'input:solver'}])
        self.assertIn({'reference': 'recipes/stepper-k1', 'role': 'input:training'}, shown['used_by'])
        self.assertIn({'reference': 'benchmarks/rollout', 'role': 'cases'}, shown['used_by'])

        drawn = project.graph()
        self.assertEqual(len(drawn['nodes']), 10)
        self.assertIn({'from': 'recipes/stepper-k2', 'to': 'recipes/stepper-k1', 'role': 'input:start'}, drawn['edges'])
        self.assertEqual(len(drawn['edges']), len(check.check_folder(self.folder).edges))
        order = project.order()
        self.assertLess(order.index('steps/solver'), order.index('datasets/waves'))
        self.assertLess(order.index('recipes/stepper-k1'), order.index('recipes/stepper-k2'))
        self.assertEqual(project.status(), CLEAN_STATUS)

    def test_second_open_of_unchanged_folder_does_not_run_the_checker(self):
        self.close(self.open())
        before = self.dump()
        checker = self.counting_checker()
        project = self.open()
        checker.assert_not_called()
        self.assertEqual(self.dump(), before)
        self.assertEqual(len(project.definitions()), 10)

    def test_changed_added_and_removed_files_are_imported(self):
        self.close(self.open())
        self.write('datasets/waves', self.edited('datasets/waves', lambda d: d.update(title='Waves again')))
        added = self.edited('charts/speed-accuracy', lambda d: d.update(title='Seconds against error'))
        self.write('charts/seconds', added)
        (self.folder / 'charts' / 'speed-accuracy.json').unlink()
        checker = self.counting_checker()
        project = self.open()
        checker.assert_called_once()
        references = {row['reference']: row for row in project.definitions()}
        self.assertEqual(references['datasets/waves']['title'], 'Waves again')
        self.assertEqual(project.definition('charts/seconds')['text'], added)
        self.assertNotIn('charts/speed-accuracy', references)
        self.assertNotIn('charts/speed-accuracy', [edge['from'] for edge in project.graph()['edges']])
        self.assertIn('charts/seconds', [edge['from'] for edge in project.graph()['edges']])

    def test_folder_with_errors_leaves_the_database_unchanged(self):
        self.close(self.open())
        before = self.dump()
        self.write('datasets/waves', self.edited('datasets/waves', lambda d: d.pop('title')))
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertIn(('datasets/waves.json', '/title'),
                      [(p.path, p.pointer) for p in caught.exception.problems if p.severity == 'error'])
        self.assertEqual(self.dump(), before)

    def test_first_open_with_errors_creates_nothing(self):
        self.write('recipes/stepper-k2', self.edited('recipes/stepper-k2',
                                                     lambda d: d.update(model='models/missing')))
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertEqual([(p.path, p.pointer) for p in caught.exception.problems],
                         [('recipes/stepper-k2.json', '/model')])
        self.assertIsNone(self.dump())

    def test_second_path_requires_rebind(self):
        self.close(self.open())
        moved = self.temporary / 'moved'
        shutil.copytree(self.base, moved)
        with self.assertRaises(ProjectError) as caught:
            self.open(moved / 'project')
        self.assertEqual(caught.exception.code, 'bound-elsewhere')
        self.assertIn(os.path.realpath(self.folder), str(caught.exception))
        self.assertIn(os.path.realpath(moved / 'project'), str(caught.exception))
        checker = self.counting_checker()
        project = self.open(moved / 'project', rebind=True)
        checker.assert_not_called()  # same files: rebinding attaches without a check
        self.assertEqual(project.summary()['folder'], os.path.realpath(moved / 'project'))
        self.close(project)
        with self.assertRaises(ProjectError):
            self.open()  # the original path is now the other one

    def test_rebind_to_a_folder_with_different_files_imports_them(self):
        self.close(self.open())
        moved = self.temporary / 'moved'
        shutil.copytree(self.base, moved)
        self.write('steps/solver', self.edited('steps/solver', lambda d: d.update(title='Moved solver'),
                                               folder=moved / 'project'), folder=moved / 'project')
        project = self.open(moved / 'project', rebind=True)
        self.assertEqual(project.definition('steps/solver')['title'], 'Moved solver')

    def test_a_project_is_open_once(self):
        self.open()
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'busy')
        with self.assertRaises(ProjectError):
            store.drop_project(self.project_id)

    def test_states_travel_up_in_the_store(self):
        self.write('steps/solver', self.edited('steps/solver', lambda d: d.update(
            earlier_work={'rebuild': 'needs-work', 'reason': 'Its command needs a new flag.'})))
        self.write('recipes/stepper-k1', self.edited('recipes/stepper-k1', lambda d: d.update(
            earlier_work={'rebuild': 'no', 'reason': 'Its code is lost.'})))
        project = self.open()
        states = {row['reference']: row['state'] for row in project.definitions()}
        self.assertEqual(states['datasets/waves'], 'needs-work')
        self.assertEqual(states['benchmarks/rollout'], 'needs-work')
        self.assertEqual(states['recipes/stepper-k2'], 'cannot-rebuild')
        self.assertEqual(project.definition('recipes/stepper-k2')['state'], 'cannot-rebuild')


class Edit(StoreCase):

    def setUp(self):
        super().setUp()
        self.project = self.open()

    def assert_refused(self, reference, text, *expected):
        before = self.dump()
        with self.assertRaises(ProjectError) as caught:
            self.project.set_definition(reference, text)
        self.assertEqual(caught.exception.code, 'invalid')
        found = [(p.path, p.pointer) for p in caught.exception.problems]
        for item in expected:
            self.assertIn(item, found)
        self.assertEqual(self.dump(), before)
        return caught.exception

    def test_set_definition_stores_the_exact_text_and_its_edges(self):
        extra = json.dumps({'format': 'tuldok_definition_v1', 'kind': 'step', 'title': 'Extra',
                            'run': {'command': ['true'], 'outputs': {'mesh': {'path': 'mesh.bin', 'role': 'file'}}}})
        self.project.set_definition('steps/extra', extra)
        waves = self.edited('datasets/waves', lambda d: d['run']['inputs'].update(
            mesh={'from': 'steps/extra', 'output': 'mesh'}))
        self.project.set_definition('datasets/waves', waves)
        shown = self.project.definition('datasets/waves')
        self.assertEqual(shown['text'], waves)
        self.assertTrue(shown['unsaved'])
        self.assertIn({'reference': 'steps/extra', 'role': 'input:mesh'}, shown['uses'])
        self.assertEqual(self.project.definition('steps/extra')['used_by'],
                         [{'reference': 'datasets/waves', 'role': 'input:mesh'}])
        self.assertEqual(self.project.status()['unsaved'], ['datasets/waves', 'steps/extra'])
        self.assertLess(self.project.order().index('steps/extra'), self.project.order().index('datasets/waves'))

    def test_set_definition_changes_states(self):
        self.project.set_definition('steps/solver', self.edited('steps/solver', lambda d: d.update(
            earlier_work={'rebuild': 'needs-work', 'reason': 'Its command needs a new flag.'})))
        self.assertEqual(self.project.definition('recipes/stepper-k2')['state'], 'needs-work')

    def test_refused_when_not_json(self):
        self.assert_refused('datasets/waves', '{"format": "tuldok_definition_v1",', ('datasets/waves.json', ''))

    def test_refused_when_the_document_alone_is_wrong(self):
        self.assert_refused('datasets/waves', self.edited('datasets/waves', lambda d: d.pop('title')),
                            ('datasets/waves.json', '/title'))
        self.assert_refused('datasets/waves', self.edited('datasets/waves', lambda d: d.update(kind='step')),
                            ('datasets/waves.json', '/kind'))
        self.assert_refused('datasets/waves', self.edited('datasets/waves', lambda d: d['run'].update(
            sources=['tools/missing.py'])), ('datasets/waves.json', '/run/sources/0'))

    def test_refused_when_a_reference_is_missing(self):
        self.assert_refused('recipes/stepper-k1', self.edited('recipes/stepper-k1', lambda d: d.update(
            model='models/missing')), ('recipes/stepper-k1.json', '/model'))

    def test_refused_when_a_named_output_is_missing(self):
        self.assert_refused('recipes/stepper-k2', self.edited('recipes/stepper-k2', lambda d: d['run']['inputs'].update(
            start={'from': 'recipes/stepper-k1', 'output': 'nothing'})),
            ('recipes/stepper-k2.json', '/run/inputs/start/output'))
        # Taking an output away from a producer breaks the definition that names it.
        self.assert_refused('steps/solver', self.edited('steps/solver', lambda d: d['run']['outputs'].pop('binary')),
                            ('datasets/waves.json', '/run/inputs/solver/output'))

    def test_refused_when_it_makes_a_cycle(self):
        error = self.assert_refused('steps/solver', self.edited('steps/solver', lambda d: d['run'].update(
            inputs={'scenes': 'datasets/waves'})), ('steps/solver.json', '/run/inputs/scenes'))
        self.assertTrue(any('cycle' in p.message for p in error.problems))

    def test_refused_when_a_chart_no_longer_fits_its_benchmark(self):
        self.assert_refused('benchmarks/rollout', self.edited('benchmarks/rollout', lambda d: d['metrics'].pop(1)),
                            ('charts/speed-accuracy.json', '/metric_x'))

    def test_refused_for_a_bad_reference(self):
        with self.assertRaises(ProjectError) as caught:
            self.project.set_definition('things/waves', self.read('datasets/waves'))
        self.assertEqual(caught.exception.code, 'not-found')

    def test_remove_definition(self):
        self.project.remove_definition('charts/speed-accuracy')
        row = {r['reference']: r for r in self.project.definitions()}['charts/speed-accuracy']
        self.assertTrue(row['removed'])
        self.assertNotIn('charts/speed-accuracy', [n['reference'] for n in self.project.graph()['nodes']])
        self.assertEqual(self.project.status()['removed'], ['charts/speed-accuracy'])
        self.assertEqual(self.project.summary()['kinds']['chart'], 1)

    def test_remove_refused_while_used(self):
        before = self.dump()
        with self.assertRaises(ProjectError) as caught:
            self.project.remove_definition('datasets/waves')
        self.assertEqual(caught.exception.code, 'in-use')
        self.assertEqual(caught.exception.references, ['benchmarks/rollout', 'recipes/stepper-k1', 'recipes/stepper-k2'])
        self.assertEqual(self.dump(), before)

    def test_removing_a_user_frees_what_it_used(self):
        self.project.remove_definition('charts/speed-accuracy')
        self.project.remove_definition('charts/rollout-ranking')
        self.project.remove_definition('benchmarks/rollout')
        self.assertTrue({r['reference']: r for r in self.project.definitions()}['benchmarks/rollout']['removed'])

    def test_open_refuses_a_folder_that_no_longer_fits_unsaved_edits(self):
        self.project.set_definition('datasets/waves', self.edited('datasets/waves', lambda d: d['run']['inputs'].update(
            log={'from': 'steps/solver', 'output': 'log'})))
        self.close(self.project)
        self.write('steps/solver', self.edited('steps/solver', lambda d: d['run']['outputs'].pop('log')))
        self.assertTrue(check.check_folder(self.folder).ok)  # the folder alone is fine
        before = self.dump()
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertIn(('datasets/waves.json', '/run/inputs/log/output'),
                      [(p.path, p.pointer) for p in caught.exception.problems])
        self.assertEqual(self.dump(), before)

    def test_removing_a_definition_never_saved_forgets_it(self):
        extra = json.dumps({'format': 'tuldok_definition_v1', 'kind': 'model', 'title': 'Extra'})
        self.project.set_definition('models/extra', extra)
        self.project.remove_definition('models/extra')
        self.assertNotIn('models/extra', [r['reference'] for r in self.project.definitions()])


class Save(StoreCase):

    def setUp(self):
        super().setUp()
        self.project = self.open()

    def test_save_writes_and_deletes_files(self):
        waves = self.edited('datasets/waves', lambda d: d.update(title='Waves, saved'))
        self.project.set_definition('datasets/waves', waves)
        extra = '{"format":"tuldok_definition_v1","kind":"model","title":"Extra"}'
        self.project.set_definition('models/extra', extra)
        self.project.remove_definition('charts/speed-accuracy')
        result = self.project.save()
        self.assertEqual(result, {'written': ['datasets/waves', 'models/extra'], 'deleted': ['charts/speed-accuracy'],
                                  'results_written': [], 'results_deleted': []})
        self.assertEqual(self.read('datasets/waves'), waves)
        self.assertEqual(self.read('models/extra'), extra)
        self.assertFalse((self.folder / 'charts' / 'speed-accuracy.json').exists())
        self.assertEqual(sorted(p.name for p in (self.folder / 'datasets').iterdir()), ['waves.json'])
        self.assertEqual(self.project.status(), CLEAN_STATUS)
        self.assertTrue(check.check_folder(self.folder).ok)
        # What was saved is what the database records, so the next open attaches without a check.
        self.close(self.project)
        checker = self.counting_checker()
        reopened = self.open()
        checker.assert_not_called()
        self.assertFalse(reopened.definition('datasets/waves')['unsaved'])

    def test_save_refuses_when_a_file_changed_on_disk(self):
        self.project.set_definition('steps/solver', self.edited('steps/solver', lambda d: d.update(title='Solver 2')))
        self.project.set_definition('datasets/waves', self.edited('datasets/waves', lambda d: d.update(title='W2')))
        self.project.remove_definition('charts/speed-accuracy')
        on_disk = self.edited('datasets/waves', lambda d: d.update(title='Changed by hand'))
        self.write('datasets/waves', on_disk)
        solver = self.read('steps/solver')
        self.assertEqual(self.project.status()['changed'], ['datasets/waves'])
        with self.assertRaises(ProjectError) as caught:
            self.project.save()
        self.assertEqual(caught.exception.code, 'changed-on-disk')
        self.assertEqual(caught.exception.references, ['datasets/waves'])
        self.assertEqual(self.read('datasets/waves'), on_disk)
        self.assertEqual(self.read('steps/solver'), solver)
        self.assertTrue((self.folder / 'charts' / 'speed-accuracy.json').exists())
        self.assertTrue(self.project.definition('steps/solver')['unsaved'])

    def test_save_refuses_when_a_new_file_appeared_on_disk(self):
        self.project.set_definition('models/extra', '{"format":"tuldok_definition_v1","kind":"model","title":"Extra"}')
        self.write('models/extra', '{"format":"tuldok_definition_v1","kind":"model","title":"By hand"}')
        with self.assertRaises(ProjectError) as caught:
            self.project.save()
        self.assertEqual(caught.exception.references, ['models/extra'])


class Conflict(StoreCase):

    def setUp(self):
        super().setUp()
        project = self.open()
        self.edit = self.edited('datasets/waves', lambda d: d.update(title='Edited in Tuldok'))
        project.set_definition('datasets/waves', self.edit)
        self.close(project)
        self.on_disk = self.edited('datasets/waves', lambda d: d.update(title='Edited by hand'))
        self.write('datasets/waves', self.on_disk)

    def test_refused_without_a_choice(self):
        before = self.dump()
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertEqual(caught.exception.code, 'conflict')
        self.assertEqual(caught.exception.references, ['datasets/waves'])
        self.assertEqual(self.dump(), before)

    def test_keep_holds_the_edit_and_save_then_overwrites(self):
        project = self.open(on_conflict='keep')
        shown = project.definition('datasets/waves')
        self.assertEqual(shown['text'], self.edit)
        self.assertTrue(shown['unsaved'])
        self.assertEqual(project.status()['changed'], [])
        project.save()
        self.assertEqual(self.read('datasets/waves'), self.edit)

    def test_discard_takes_the_file(self):
        project = self.open(on_conflict='discard')
        shown = project.definition('datasets/waves')
        self.assertEqual(shown['text'], self.on_disk)
        self.assertFalse(shown['unsaved'])

    def test_file_removed_on_disk_with_an_unsaved_edit(self):
        project = self.open(on_conflict='discard')
        chart = self.edited('charts/speed-accuracy', lambda d: d.update(title='Edited chart'))
        project.set_definition('charts/speed-accuracy', chart)
        self.close(project)
        (self.folder / 'charts' / 'speed-accuracy.json').unlink()
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertEqual(caught.exception.references, ['charts/speed-accuracy'])
        project = self.open(on_conflict='keep')
        self.assertTrue(project.definition('charts/speed-accuracy')['unsaved'])
        project.save()
        self.assertEqual(self.read('charts/speed-accuracy'), chart)
        self.close(project)
        (self.folder / 'charts' / 'speed-accuracy.json').unlink()
        project = self.open(on_conflict='discard')  # the row is clean now: no conflict, the file is just gone
        self.assertNotIn('charts/speed-accuracy', [r['reference'] for r in project.definitions()])


class Drop(StoreCase):

    def test_drop_project(self):
        self.close(self.open())
        self.assertIsNotNone(self.dump())
        store.drop_project(self.project_id)
        self.assertIsNone(self.dump())
        store.drop_project(self.project_id)  # dropping what is not there is fine

    def test_drop_refuses_a_bad_id(self):
        with self.assertRaises(ValueError):
            store.drop_project('project; drop')


if __name__ == '__main__':
    unittest.main()
