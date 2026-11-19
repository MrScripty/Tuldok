"""The Map workspace's reading (docs/plans/definition-first-projects/spec-w1.md): format fields and three operations.

The checker rules and the graph roles are tested without a database, on a
copy of tests/fixtures/tuldok_project/minimal (FixtureCopy of the checker's
tests). read_note needs no database either. Everything else runs only when
TULDOK_DATABASE_URL names a disposable cluster (spec-m1-m2.md, section 1):
map and recipe_results on a copy of the minimal fixture (StoreCase), the
operations through Service.call and the two commands, and one build of the
buildable fixture (BuildCase) with comparisons and a derivation added, which
must build exactly as without them. Anything that could reach the local
project home points TULDOK_PROJECT_HOME at a temporary directory.
Section 2 of spec-w3.md is tested here too: the map's unsaved and trained_at
fallback (MapAdditions), draft_branch (Branch, Operations) and the branch and
revert commands; revert_definition itself is tested in the store's tests.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import build_requests, graph, local, plan, workspace  # noqa: E402
from tuldok_project.check import check_folder  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
import test_tuldok_project_check as check_base  # noqa: E402
import test_tuldok_project_store as store_base  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')
INSPECTOR = {'actor_id': 'agent-inspect', 'kind': 'agent', 'label': 'An agent', 'scopes': ['inspect']}
NOBODY = {'actor_id': 'agent-none', 'kind': 'agent', 'label': 'An agent', 'scopes': []}
COMMIT = '0123456789abcdef0123456789abcdef01234567'

FIXTURE_MAP = {
    'groups': [
        {'id': 'steppers', 'title': 'Steppers', 'parent': None,
         'description': 'Every stepper trained on wave scenes.', 'models': 2},
        {'id': 'fine-tuned', 'title': 'Fine-tuned steppers', 'parent': 'steppers', 'description': None, 'models': 1},
    ],
    'models': [
        {'reference': 'recipes/early-fit', 'title': 'Early fit (fit-0042)',
         'description': 'A stepper trained before this format; only its weights and measurements remain.',
         'short': 'F42', 'group': 'steppers',
         'change': 'architecture', 'derived_from': None, 'trained_at': '2026-03-14', 'state': 'cannot-rebuild',
         'unsaved': False, 'adopted': False, 'card': 'notes/fits/early-fit.md', 'value': 0.625, 'count': 4, 'benchmarks': 1},
        {'reference': 'recipes/stepper-k1', 'title': 'Stepper on wave scenes', 'description': None, 'short': 'K1',
         'group': 'steppers',
         'change': 'training-policy', 'derived_from': 'recipes/early-fit', 'trained_at': None, 'state': 'not-built',
         'unsaved': False, 'adopted': False, 'card': None, 'value': 0.875, 'count': 8, 'benchmarks': 1},
        {'reference': 'recipes/stepper-k2', 'title': 'Stepper fine-tuned from k1', 'description': None, 'short': 'K2',
         'group': 'fine-tuned', 'change': 'refinement', 'derived_from': 'recipes/stepper-k1', 'trained_at': None,
         'state': 'not-built', 'unsaved': False, 'adopted': False, 'card': None, 'value': 0.5, 'count': 8, 'benchmarks': 1},
    ],
    'edges': [
        {'from': 'recipes/stepper-k1', 'to': 'recipes/early-fit', 'kind': 'derived'},
        {'from': 'recipes/stepper-k2', 'to': 'recipes/stepper-k1', 'kind': 'derived'},
        {'from': 'recipes/stepper-k2', 'to': 'recipes/stepper-k1', 'kind': 'input'},
    ],
    'comparisons': [
        {'from': 'recipes/stepper-k1', 'to': 'recipes/early-fit',
         'explanation': 'Same stepper, trained again with a recorded command and data.', 'excerpt': None},
        {'from': 'recipes/stepper-k2', 'to': 'recipes/stepper-k1',
         'explanation': 'Fine-tuning lowers the rollout error at both horizons.',
         'excerpt': 'k2 halves the median error at horizon 1.'},
    ],
    'track': {'chart': 'charts/rollout-progression', 'benchmark': 'benchmarks/rollout',
              'metric': {'id': 'rmse', 'title': 'Rollout RMSE', 'units': 'm/s', 'better': 'lower'},
              'statistic': 'median'},
}


def _strip_map_fields(documents):
    """The documents without derived_from and compared_with."""
    stripped = copy.deepcopy(documents)
    for document in stripped.values():
        document.pop('derived_from', None)
        document.pop('compared_with', None)
    return stripped


# ----------------------------------------------------------- the checker

class MapFields(check_base.FixtureCopy):
    """Section 1: each new error, in the checker's style."""

    def test_the_fixture_with_every_field_is_valid(self):
        report = check_folder(self.project)
        self.assertClean(report)
        self.assertEqual([group['id'] for group in report.project['groups']], ['steppers', 'fine-tuned'])

    def test_a_folder_without_the_fields_is_valid(self):
        self.edit('tuldok.json', '/groups', check_base.DELETE)
        self.edit('tuldok.json', '/map', check_base.DELETE)
        for name in ('early-fit', 'stepper-k1', 'stepper-k2'):
            for field in ('group', 'change', 'derived_from', 'compared_with'):
                path = self.project / 'recipes' / f'{name}.json'
                if field in json.loads(path.read_text(encoding='utf-8')):
                    self.edit(f'recipes/{name}.json', f'/{field}', check_base.DELETE)
        self.assertClean(check_folder(self.project))

    def test_a_recipe_group_that_is_no_group(self):
        self.edit('recipes/stepper-k1.json', '/group', 'missing')
        problem = self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/group')
        self.assertIn("'missing' is not a group of this project", problem.message)

    def test_a_recipe_group_when_the_project_has_no_groups(self):
        self.edit('tuldok.json', '/groups', check_base.DELETE)
        report = check_folder(self.project)
        for name in ('early-fit', 'stepper-k1', 'stepper-k2'):
            self.assertProblem(report, f'recipes/{name}.json', '/group', alone=False)
        self.assertEqual(len(report.problems), 3)

    def test_a_group_parent_that_is_unknown(self):
        self.edit('tuldok.json', '/groups/1/parent', 'nobody')
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/groups/1/parent')
        self.assertIn("'nobody' is not a group", problem.message)

    def test_a_group_that_is_its_own_parent(self):
        self.edit('tuldok.json', '/groups/0/parent', 'steppers')
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/groups/0/parent')
        self.assertIn('its own ancestor', problem.message)

    def test_a_group_that_is_its_own_ancestor(self):
        self.edit('tuldok.json', '/groups/0/parent', 'fine-tuned')
        report = check_folder(self.project)
        self.assertProblem(report, 'tuldok.json', '/groups/0/parent', alone=False)
        self.assertProblem(report, 'tuldok.json', '/groups/1/parent', alone=False)
        self.assertEqual(len(report.problems), 2)

    def test_a_group_id_used_twice(self):
        self.edit('tuldok.json', '/groups/2', {'id': 'steppers', 'title': 'Again'})
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/groups/2/id')
        self.assertIn('used more than once', problem.message)

    def test_group_and_map_fields_follow_the_schema(self):
        cases = [
            ('tuldok.json', '/groups/0/colour', 'blue', '/groups/0/colour'),
            ('tuldok.json', '/groups/2', {'id': '-bad', 'title': 'Bad'}, '/groups/2/id'),
            ('tuldok.json', '/groups/0/title', '', '/groups/0/title'),
            ('tuldok.json', '/groups/0/description', 'x' * 2001, '/groups/0/description'),
            ('tuldok.json', '/map/size', 3, '/map/size'),
            ('tuldok.json', '/map/chart', 'benchmarks/rollout', '/map/chart'),
            ('recipes/stepper-k1.json', '/change', 'colour', '/change'),
            ('recipes/stepper-k1.json', '/derived_from', 'datasets/waves', '/derived_from'),
            ('recipes/stepper-k1.json', '/compared_with/0/explanation', '', '/compared_with/0/explanation'),
            ('recipes/stepper-k1.json', '/compared_with/0/note', 'x', '/compared_with/0/note'),
            ('recipes/stepper-k1.json', '/compared_with/0/excerpt', 'x' * 2001, '/compared_with/0/excerpt'),
        ]
        for relative, pointer, value, expected in cases:
            with self.subTest(pointer=pointer):
                self.setUp()
                self.edit(relative, pointer, value)
                self.assertProblem(check_folder(self.project), relative, expected)

    def test_more_than_200_groups_or_50_comparisons(self):
        self.edit('tuldok.json', '/groups', [{'id': f'g{index}', 'title': 'G'} for index in range(201)]
                  + [{'id': 'steppers', 'title': 'S'}, {'id': 'fine-tuned', 'title': 'F'}])
        self.assertProblem(check_folder(self.project), 'tuldok.json', '/groups')
        self.setUp()
        self.edit('recipes/stepper-k1.json', '/compared_with',
                  [{'recipe': 'recipes/early-fit', 'explanation': 'x'}] * 51)
        report = check_folder(self.project)
        self.assertProblem(report, 'recipes/stepper-k1.json', '/compared_with', alone=False)

    def test_derived_from_a_recipe_that_does_not_exist(self):
        self.edit('recipes/stepper-k1.json', '/derived_from', 'recipes/missing')
        problem = self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/derived_from')
        self.assertIn('recipes/missing does not exist', problem.message)

    def test_derived_from_itself(self):
        self.edit('recipes/stepper-k1.json', '/derived_from', 'recipes/stepper-k1')
        problem = self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/derived_from')
        self.assertIn('cannot be derived from itself', problem.message)

    def test_a_loop_of_derived_from_is_reported_on_each_member(self):
        self.edit('recipes/early-fit.json', '/derived_from', 'recipes/stepper-k2')
        report = check_folder(self.project)
        for name in ('early-fit', 'stepper-k1', 'stepper-k2'):
            problem = self.assertProblem(report, f'recipes/{name}.json', '/derived_from', alone=False)
            self.assertIn('recipes/early-fit, recipes/stepper-k1, recipes/stepper-k2', problem.message)
        self.assertEqual(len(report.problems), 3)

    def test_compared_with_a_recipe_that_does_not_exist(self):
        self.edit('recipes/stepper-k2.json', '/compared_with/0/recipe', 'recipes/missing')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k2.json', '/compared_with/0/recipe')

    def test_compared_with_itself(self):
        self.edit('recipes/stepper-k2.json', '/compared_with/0/recipe', 'recipes/stepper-k2')
        problem = self.assertProblem(check_folder(self.project), 'recipes/stepper-k2.json', '/compared_with/0/recipe')
        self.assertIn('cannot be compared with itself', problem.message)

    def test_compared_with_the_same_recipe_twice(self):
        self.edit('recipes/stepper-k2.json', '/compared_with/1', {'recipe': 'recipes/stepper-k1', 'explanation': 'x'})
        problem = self.assertProblem(check_folder(self.project), 'recipes/stepper-k2.json', '/compared_with/1/recipe')
        self.assertIn('compared more than once', problem.message)

    def test_a_mutual_comparison_is_not_a_cycle(self):
        self.edit('recipes/stepper-k1.json', '/compared_with/1', {'recipe': 'recipes/stepper-k2', 'explanation': 'x'})
        self.assertClean(check_folder(self.project))

    def test_map_chart_must_be_a_progression_chart(self):
        self.edit('tuldok.json', '/map/chart', 'charts/rollout-ranking')
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/map/chart')
        self.assertIn("form 'ranking', not progression", problem.message)

    def test_map_chart_must_exist(self):
        self.edit('tuldok.json', '/map/chart', 'charts/missing')
        problem = self.assertProblem(check_folder(self.project), 'tuldok.json', '/map/chart')
        self.assertIn('charts/missing does not exist', problem.message)


# ------------------------------------------------------------- the graph

class Roles(unittest.TestCase):
    """Section 1: the derived and compared roles are edges, and nothing else."""

    def setUp(self):
        self.documents = store_base._fixture_documents()
        # A mutual comparison on top of the fixture's.
        self.documents['recipes/stepper-k1']['compared_with'].append(
            {'recipe': 'recipes/stepper-k2', 'explanation': 'The other way.'})

    def test_both_roles_are_edges(self):
        found = graph.edges(self.documents)
        for edge in (graph.Edge('recipes/stepper-k1', 'recipes/early-fit', 'derived'),
                     graph.Edge('recipes/stepper-k1', 'recipes/early-fit', 'compared'),
                     graph.Edge('recipes/stepper-k1', 'recipes/stepper-k2', 'compared'),
                     graph.Edge('recipes/stepper-k2', 'recipes/stepper-k1', 'derived'),
                     graph.Edge('recipes/stepper-k2', 'recipes/stepper-k1', 'compared')):
            self.assertIn(edge, found)
        uses = graph.uses(self.documents['recipes/stepper-k1'])
        self.assertIn(graph.Use('derived', '/derived_from', 'recipes/early-fit'), uses)
        self.assertIn(graph.Use('compared', '/compared_with/1/recipe', 'recipes/stepper-k2'), uses)

    def test_order_cycles_and_states_ignore_them(self):
        stripped = _strip_map_fields(self.documents)
        self.assertEqual(graph.cycles(self.documents), [])
        self.assertEqual(graph.order(self.documents), graph.order(stripped))
        self.assertEqual(graph.states(self.documents), graph.states(stripped))
        self.assertEqual(graph.states(self.documents)['recipes/stepper-k1'], 'not-built')  # early-fit is "no"

    def test_a_derived_loop_is_not_a_cycle_of_uses(self):
        self.documents['recipes/early-fit']['derived_from'] = 'recipes/stepper-k2'
        self.assertEqual(graph.cycles(self.documents), [])
        self.assertEqual(graph.derived_loops(self.documents),
                         [('recipes/early-fit', 'recipes/stepper-k1', 'recipes/stepper-k2')])
        self.assertEqual(graph.derived_loops(store_base._fixture_documents()), [])
        self.assertEqual(graph.derived_loops({'recipes/a': {'kind': 'recipe', 'derived_from': 'recipes/a'}}), [])

    def test_the_plan_is_the_same(self):
        stripped = _strip_map_fields(self.documents)
        targets = plan.every_target(self.documents)
        self.assertEqual(plan.make_plan(self.documents, targets), plan.make_plan(stripped, targets))


# ----------------------------------------------------------------- notes

class Notes(unittest.TestCase):
    """read_note: the folder on disk, read as carefully as folder.py reads it."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name) / 'project'
        shutil.copytree(FIXTURE / 'project', self.folder)
        self.notes = self.folder / 'notes'

    def refused(self, path):
        with self.assertRaises(ProjectError) as caught:
            workspace.read_note(self.folder, path)
        self.assertEqual(caught.exception.code, 'not-found')
        return caught.exception

    def test_a_card(self):
        expected = (self.notes / 'fits' / 'early-fit.md').read_text(encoding='utf-8')
        self.assertEqual(workspace.read_note(self.folder, 'fits/early-fit.md'),
                         {'path': 'fits/early-fit.md', 'text': expected})

    def test_a_missing_file_or_a_directory(self):
        self.refused('fits/missing.md')
        self.refused('missing/early-fit.md')
        self.refused('fits')

    def test_paths_not_in_normal_form(self):
        for path in ('../tuldok.json', 'fits/../decisions.md', '/etc/passwd', 'fits//early-fit.md', './decisions.md',
                     'fits/', '', 'a\x00b'):
            with self.subTest(path=path):
                self.refused(path)

    def test_a_link_anywhere_in_the_path(self):
        (self.notes / 'linked.md').symlink_to(self.notes / 'decisions.md')
        self.refused('linked.md')
        (self.notes / 'linked').symlink_to(self.notes / 'fits')
        self.refused('linked/early-fit.md')
        os.rename(self.notes, self.folder.parent / 'real-notes')
        self.notes.symlink_to(self.folder.parent / 'real-notes')
        self.refused('decisions.md')

    def test_a_file_over_the_limit(self):
        (self.notes / 'big.md').write_bytes(b'a' * (workspace.NOTE_LIMIT + 1))
        self.refused('big.md')
        (self.notes / 'full.md').write_bytes(b'a' * workspace.NOTE_LIMIT)
        self.assertEqual(len(workspace.read_note(self.folder, 'full.md')['text']), workspace.NOTE_LIMIT)

    def test_bytes_that_are_not_utf8(self):
        (self.notes / 'latin.md').write_bytes('café'.encode('latin-1'))
        self.assertIn('not UTF-8', str(self.refused('latin.md')))


# ------------------------------------------------------------ the database

def _append_subject(folder, name, recipe, row):
    """Add a benchmark subject for recipe and one ungrouped rmse row to results/rollout.csv, in order."""
    path = folder / 'benchmarks' / 'rollout.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    document['subjects'].append({'name': name, 'title': name, 'recipe': recipe, 'argument': '{recipe}/model.pt'})
    path.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    results_path = folder / 'results' / 'rollout.csv'
    header, *lines = results_path.read_text(encoding='utf-8').splitlines()
    lines.append(f'{name},rmse,,{row},{COMMIT},2026-11-02')
    lines.sort(key=lambda line: line.split(',')[:3])
    results_path.write_text('\n'.join([header, *lines]) + '\n', encoding='utf-8')


def _add_recipe(folder, name, **fields):
    document = {'format': 'tuldok_definition_v1', 'kind': 'recipe', 'title': f'Recipe {name}',
                'earlier_work': {'rebuild': 'no', 'reason': 'Test.'}, 'model': 'models/stepper', **fields}
    (folder / 'recipes' / f'{name}.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')


class _Counting:
    """Counts the statements run on a psycopg connection: every execute goes through a cursor of its factory."""

    def __init__(self, connection):
        counter = self
        self.count = 0

        class Cursor(connection.cursor_factory):
            def execute(self, *arguments, **options):
                counter.count += 1
                return super().execute(*arguments, **options)

            def executemany(self, *arguments, **options):
                counter.count += 1
                return super().executemany(*arguments, **options)

        connection.cursor_factory = Cursor


class Description(unittest.TestCase):
    """A model's description on the map (spec-w2.md section 2): the first 300 characters, cut at a word."""

    def test_a_short_description_is_whole_with_its_spaces_made_single(self):
        self.assertEqual(workspace._description({'description': '  One  line,\n\tthen  another. '}),
                         'One line, then another.')

    def test_none_when_absent_or_blank(self):
        self.assertIsNone(workspace._description({}))
        self.assertIsNone(workspace._description({'description': '   '}))

    def test_exactly_the_limit_is_not_cut(self):
        text = ('word ' * 60)[:300]
        self.assertEqual(len(text), 300)
        self.assertEqual(workspace._description({'description': text}), text.strip())

    def test_a_long_description_is_cut_after_the_last_whole_word(self):
        words = [f'w{index:03d}' for index in range(100)]   # 4 characters and a space each
        shown = workspace._description({'description': ' '.join(words)})
        self.assertLessEqual(len(shown), 300)
        self.assertTrue(shown.endswith('…'))
        kept = shown[:-1].split(' ')
        self.assertEqual(kept, words[:len(kept)])
        self.assertEqual(len(kept), 60)   # 60 words are 299 characters; the ellipsis makes 300

    def test_a_cut_drops_the_punctuation_before_the_ellipsis(self):
        shown = workspace._description({'description': 'a' * 296 + ', then more words follow here'})
        self.assertEqual(shown, 'a' * 296 + '…')

    def test_one_word_longer_than_the_limit_is_cut_at_the_limit(self):
        shown = workspace._description({'description': 'x' * 400})
        self.assertEqual(shown, 'x' * 299 + '…')


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Map(store_base.StoreCase):
    """map and recipe_results on the minimal fixture."""

    def test_the_fixture(self):
        found = workspace.project_map(self.open())
        self.assertEqual(found, FIXTURE_MAP)
        json.dumps(found, allow_nan=False)

    def test_a_recipe_under_two_subject_names_and_one_with_no_result(self):
        # stepper-k2 is also the subject k2-long, with a better median (0.25 < 0.5) from 3 cases; and a worse one.
        _append_subject(self.folder, 'k2-long', 'recipes/stepper-k2', '3,0,0.3,0.25,0.1,0.5,0.1,0.6')
        _append_subject(self.folder, 'k2-short', 'recipes/stepper-k2', '2,0,0.9,0.9,0.8,1.0,0.8,1.0')
        _add_recipe(self.folder, 'stepper-k3', derived_from='recipes/stepper-k2', change='refinement',
                    labels={'trained_at': '2026-01-01'})
        found = workspace.project_map(self.open())
        models = {model['reference']: model for model in found['models']}
        self.assertEqual((models['recipes/stepper-k2']['value'], models['recipes/stepper-k2']['count']), (0.25, 3))
        self.assertEqual(models['recipes/stepper-k2']['benchmarks'], 1)
        k3 = models['recipes/stepper-k3']
        self.assertEqual((k3['value'], k3['count'], k3['benchmarks'], k3['group'], k3['state']),
                         (None, None, 0, None, 'cannot-rebuild'))
        self.assertEqual([model['reference'] for model in found['models']],
                         ['recipes/stepper-k3', 'recipes/early-fit', 'recipes/stepper-k1', 'recipes/stepper-k2'])
        self.assertIn({'from': 'recipes/stepper-k3', 'to': 'recipes/stepper-k2', 'kind': 'derived'}, found['edges'])
        self.assertEqual([group['models'] for group in found['groups']], [2, 1])

    def test_higher_is_better_picks_the_highest(self):
        path = self.folder / 'benchmarks' / 'rollout.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        document['metrics'][0]['better'] = 'higher'
        path.write_text(json.dumps(document), encoding='utf-8')
        _append_subject(self.folder, 'k2-long', 'recipes/stepper-k2', '3,0,0.3,0.25,0.1,0.5,0.1,0.6')
        models = {model['reference']: model for model in workspace.project_map(self.open())['models']}
        self.assertEqual(models['recipes/stepper-k2']['value'], 0.5)

    def test_no_track_without_map_chart(self):
        path = self.folder / 'tuldok.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        del document['map']
        path.write_text(json.dumps(document), encoding='utf-8')
        found = workspace.project_map(self.open())
        self.assertIsNone(found['track'])
        self.assertEqual({model['value'] for model in found['models']}, {None})
        self.assertEqual([model['benchmarks'] for model in found['models']], [1, 1, 1])

    def test_a_change_to_tuldok_json_alone_is_imported(self):
        self.close(self.open())
        path = self.folder / 'tuldok.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        document['groups'][0]['title'] = 'Every stepper'
        path.write_text(json.dumps(document), encoding='utf-8')
        self.assertEqual(workspace.project_map(self.open())['groups'][0]['title'], 'Every stepper')

    def test_an_edit_naming_an_unknown_group_is_refused(self):
        project = self.open()
        text = (self.folder / 'recipes' / 'stepper-k1.json').read_text(encoding='utf-8')
        with self.assertRaises(ProjectError) as caught:
            project.set_definition('recipes/stepper-k1', text.replace('"group": "steppers"', '"group": "nobody"'))
        self.assertEqual([(p.path, p.pointer) for p in caught.exception.problems],
                         [('recipes/stepper-k1.json', '/group')])

    def test_uses_and_used_by_show_the_new_edges(self):
        shown = self.open().definition('recipes/stepper-k1')
        self.assertIn({'reference': 'recipes/early-fit', 'role': 'derived'}, shown['uses'])
        self.assertIn({'reference': 'recipes/early-fit', 'role': 'compared'}, shown['uses'])
        self.assertIn({'reference': 'recipes/stepper-k2', 'role': 'derived'}, shown['used_by'])
        self.assertIn({'reference': 'recipes/stepper-k2', 'role': 'compared'}, shown['used_by'])

    def test_the_number_of_queries_does_not_grow_with_the_recipes(self):
        project = self.open()
        counting = _Counting(project._connection)
        self.assertEqual(workspace.project_map(project), FIXTURE_MAP)
        few = counting.count
        self.close(project)
        for index in range(8):
            _add_recipe(self.folder, f'more-{index}', group='steppers', change='component',
                        derived_from='recipes/stepper-k1',
                        compared_with=[{'recipe': 'recipes/stepper-k2', 'explanation': 'x'}])
            _append_subject(self.folder, f'more-{index}', f'recipes/more-{index}', '1,0,1,1,1,1,1,1')
        project = self.open()
        counting = _Counting(project._connection)
        found = workspace.project_map(project)
        self.assertEqual(len(found['models']), 11)
        self.assertEqual(counting.count, few)
        self.assertGreater(few, 0)

    def test_recipe_results(self):
        project = self.open()
        found = workspace.recipe_results(project, 'recipes/stepper-k1')
        self.assertEqual(found['benchmarks'], ['rollout'])
        self.assertEqual([(row['benchmark'], row['subject'], row['metric'], row['group']) for row in found['rows']],
                         [('rollout', 'stepper-k1', 'rmse', ''), ('rollout', 'stepper-k1', 'seconds', '')])
        self.assertEqual(found['rows'][0], {
            'benchmark': 'rollout', 'subject': 'stepper-k1', 'metric': 'rmse', 'group': '', 'count': 8,
            'unavailable': 0, 'mean': 1.25, 'median': 0.875, 'p10': 0.425, 'p90': 2.65, 'min': 0.25, 'max': 3.0,
            'commit': COMMIT, 'produced': '2026-11-02T10:15:00Z', 'origin': 'file'})
        grouped = workspace.recipe_results(project, 'recipes/stepper-k1', 'horizon')
        self.assertEqual([row['group'] for row in grouped['rows']], ['horizon=1', 'horizon=8'])
        self.assertEqual(workspace.recipe_results(project, 'recipes/stepper-k1', 'nothing')['rows'], [])
        for missing in ('recipes/missing', 'models/stepper', 'nonsense'):
            with self.assertRaises(ProjectError) as caught:
                workspace.recipe_results(project, missing)
            self.assertEqual(caught.exception.code, 'not-found')

    def test_recipe_results_under_two_names_and_with_none(self):
        _append_subject(self.folder, 'k2-long', 'recipes/stepper-k2', '3,0,0.3,0.25,0.1,0.5,0.1,0.6')
        _add_recipe(self.folder, 'stepper-k3')
        project = self.open()
        found = workspace.recipe_results(project, 'recipes/stepper-k2')
        self.assertEqual([(row['subject'], row['metric']) for row in found['rows']],
                         [('k2-long', 'rmse'), ('stepper-k2', 'rmse'), ('stepper-k2', 'seconds')])
        self.assertEqual(workspace.recipe_results(project, 'recipes/stepper-k3'), {'rows': [], 'benchmarks': []})


def _record_product(project, reference, finished_at, *, state='succeeded'):
    """A run and the current product it made for reference, written straight into the tables builds.py owns."""
    run_id = f'run-{reference.split("/")[1]}-0000'
    text = project.definition(reference)['text']
    project._execute("""INSERT INTO {schema}.runs (id, reference, subject, plan_id, state, scratch, commit, definition,
                                                    inputs, argv, env, directory, queued_at, started_at, finished_at)
                        VALUES (%s, %s, '', 'plan-0000', %s, true, '', %s, '{{}}', '[]', '{{}}', '/nonexistent',
                                %s, %s, %s)""", (run_id, reference, state, text, finished_at, finished_at, finished_at))
    project._execute("""INSERT INTO {schema}.products (run_id, reference, subject, directory, outputs, current)
                        VALUES (%s, %s, '', '/nonexistent', '{{}}', true)""", (run_id, reference))


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class MapAdditions(store_base.StoreCase):
    """The map's unsaved and the trained_at fallback (spec-w3.md section 2)."""

    def test_unsaved(self):
        project = self.open()
        text = (self.folder / 'recipes' / 'stepper-k2.json').read_text(encoding='utf-8')
        project.set_definition('recipes/stepper-k2', text.replace('Stepper fine-tuned from k1', 'Edited'))
        models = {model['reference']: model for model in workspace.project_map(project)['models']}
        self.assertEqual({reference: model['unsaved'] for reference, model in models.items()},
                         {'recipes/early-fit': False, 'recipes/stepper-k1': False, 'recipes/stepper-k2': True})

    def test_trained_at_falls_back_to_the_finish_of_the_current_product(self):
        project = self.open()
        _record_product(project, 'recipes/stepper-k1', '2026-01-02T03:04:05+00:00')
        _record_product(project, 'recipes/stepper-k2', '2025-01-01T00:00:00+00:00', state='adopted')
        _record_product(project, 'recipes/early-fit', '2025-01-01T00:00:00+00:00')   # its label wins
        found = workspace.project_map(project)
        models = {model['reference']: model for model in found['models']}
        self.assertEqual(models['recipes/stepper-k1']['trained_at'], '2026-01-02T03:04:05+00:00')
        self.assertEqual((models['recipes/stepper-k2']['trained_at'], models['recipes/stepper-k2']['adopted']),
                         (None, True))
        self.assertEqual(models['recipes/early-fit']['trained_at'], '2026-03-14')
        self.assertEqual([model['reference'] for model in found['models']],
                         ['recipes/stepper-k1', 'recipes/early-fit', 'recipes/stepper-k2'])

    def test_the_number_of_queries_is_the_same_with_products(self):
        project = self.open()
        counting = _Counting(project._connection)
        workspace.project_map(project)
        without = counting.count
        _record_product(project, 'recipes/stepper-k1', '2026-01-02T03:04:05+00:00')
        _record_product(project, 'recipes/stepper-k2', '2026-01-03T03:04:05+00:00')
        counting = _Counting(project._connection)
        workspace.project_map(project)
        # builds.status asks more once any run exists; neither it nor the map asks per recipe or product.
        with_runs = counting.count
        _record_product(project, 'recipes/early-fit', '2026-01-04T03:04:05+00:00')
        counting = _Counting(project._connection)
        workspace.project_map(project)
        self.assertEqual(counting.count, with_runs)
        self.assertGreater(without, 0)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Branch(store_base.StoreCase):
    """draft_branch (spec-w3.md section 2)."""

    def setUp(self):
        super().setUp()
        self.code = self.base / 'code'

    def draft(self, recipe='recipes/stepper-k1', title='Stepper k1, more epochs!', **options):
        project = self.open()
        before = self.dump()
        found = workspace.draft_branch(project, recipe, title, **options)
        self.assertEqual(self.dump(), before)   # nothing is stored
        self.close(project)
        json.dumps(found, allow_nan=False)
        return found

    def test_a_branch_of_a_recipe_with_a_settings_file(self):
        found = self.draft()
        self.assertEqual(set(found), {'reference', 'text', 'parent', 'inlined', 'problems'})
        self.assertEqual((found['reference'], found['parent'], found['inlined'], found['problems']),
                         ('recipes/stepper-k1-more-epochs', 'recipes/stepper-k1', 'configs/train-k1.json', []))
        parent = json.loads((self.folder / 'recipes' / 'stepper-k1.json').read_text(encoding='utf-8'))
        document = json.loads(found['text'])
        self.assertEqual(list(document), ['format', 'kind', 'title', 'model', 'group', 'change', 'derived_from', 'run'])
        self.assertEqual((document['title'], document['change'], document['derived_from'], document['group']),
                         ('Stepper k1, more epochs!', 'training-policy', 'recipes/stepper-k1', 'steppers'))
        settings = json.loads((self.code / 'configs' / 'train-k1.json').read_text(encoding='utf-8'))
        expected_run = {('settings' if key == 'settings_file' else key): (settings if key == 'settings_file' else value)
                        for key, value in parent['run'].items()}
        self.assertEqual(document['run'], expected_run)
        self.assertEqual(list(document['run']), list(expected_run))   # the parent's order of keys
        self.assertEqual(found['text'], json.dumps(document, indent=2, ensure_ascii=False) + '\n')
        project = self.open()
        project.set_definition(found['reference'], found['text'])   # it can be kept as it is
        self.assertTrue(project.definition(found['reference'])['unsaved'])

    def test_what_is_and_is_not_carried(self):
        found = self.draft('recipes/early-fit', 'Again', change='component', description='Retrained.')
        document = json.loads(found['text'])
        self.assertEqual(document, {'format': 'tuldok_definition_v1', 'kind': 'recipe', 'title': 'Again',
                                    'description': 'Retrained.', 'model': 'models/stepper', 'group': 'steppers',
                                    'change': 'component', 'derived_from': 'recipes/early-fit'})
        self.assertIsNone(found['inlined'])
        # Without run and earlier_work it does not check yet: the caller is told so.
        self.assertEqual([(p['severity'], p['path'], p['pointer']) for p in found['problems']],
                         [('error', 'recipes/again.json', '/run')])
        self.assertEqual(json.loads(self.draft('recipes/stepper-k2', 'K3')['text'])['change'], 'refinement')

    def test_inline_settings_and_indentation_are_kept(self):
        found = self.draft('recipes/stepper-k2', 'K3')
        self.assertIsNone(found['inlined'])
        self.assertEqual(json.loads(found['text'])['run']['settings'], {'epochs': 2, 'learning_rate': 0.0005, 'seed': 2})
        path = self.folder / 'recipes' / 'stepper-k2.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        for indent, expected in ((4, '    '), ('\t', '\t'), (None, '  ')):
            with self.subTest(indent=indent):
                path.write_text(json.dumps(document, indent=indent), encoding='utf-8')
                text = self.draft('recipes/stepper-k2', 'K3')['text']
                self.assertEqual(text, json.dumps(json.loads(text), indent=expected, ensure_ascii=False) + '\n')

    def test_names(self):
        self.assertEqual(self.draft(title='  Héllo, World!! ')['reference'], 'recipes/h-llo-world')
        self.assertEqual(self.draft(title='!!!')['reference'], 'recipes/recipe')
        long = self.draft(title='a' * 79 + ' b' + 'c' * 100)['reference']
        self.assertEqual(long, 'recipes/' + 'a' * 79)   # cut to 80, then trimmed of the '-' it ends with
        self.assertEqual(self.draft(title='Stepper K1')['reference'], 'recipes/stepper-k1-2')
        _add_recipe(self.folder, 'stepper-k1-2')
        self.assertEqual(self.draft(title='Stepper K1')['reference'], 'recipes/stepper-k1-3')
        self.assertEqual(self.draft(title='x', name='chosen')['reference'], 'recipes/chosen')

    def test_a_name_that_is_wrong_or_taken_is_refused(self):
        _add_recipe(self.folder, 'spare')
        project = self.open()
        project.remove_definition('recipes/spare')
        for name in ('Upper', '-dash', 'a' * 121, 'stepper-k1', 'spare'):
            with self.subTest(name=name):
                with self.assertRaises(ProjectError) as caught:
                    workspace.draft_branch(project, 'recipes/stepper-k1', 'x', name=name)
                self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual(workspace.draft_branch(project, 'recipes/stepper-k1', 'Spare')['reference'],
                         'recipes/spare-2')   # a removed definition's name is not free

    def test_an_unknown_or_removed_recipe_is_not_found(self):
        _add_recipe(self.folder, 'spare')
        project = self.open()
        project.remove_definition('recipes/spare')
        for recipe in ('recipes/missing', 'recipes/spare', 'models/stepper', 'nonsense'):
            with self.subTest(recipe=recipe):
                with self.assertRaises(ProjectError) as caught:
                    workspace.draft_branch(project, recipe, 'x')
                self.assertEqual(caught.exception.code, 'not-found')

    def replace_settings(self, make):
        """Replace stepper-k1's settings file in the code root with what make(path) puts there."""
        path = self.code / 'configs' / 'train-k1.json'
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        elif path.exists() or path.is_symlink():
            path.unlink()
        make(path)

    def test_settings_that_are_not_carried(self):
        self.close(self.open())   # imported once: later opens attach without looking at the code root
        outside = self.temporary / 'outside.json'
        outside.write_text('{"secret": 1}', encoding='utf-8')
        cases = {
            'a list': lambda path: path.write_text('[1, 2]', encoding='utf-8'),
            'not JSON': lambda path: path.write_text('{"a": ', encoding='utf-8'),
            'a key twice': lambda path: path.write_text('{"a": 1, "a": 2}', encoding='utf-8'),
            'over the limit': lambda path: path.write_text(
                '{"a": "' + 'x' * (workspace.SETTINGS_LIMIT - 8) + '"}', encoding='utf-8'),
            'a link out of the code root': lambda path: path.symlink_to(outside),
            'a directory': lambda path: path.mkdir(),
            'missing': lambda path: None,
        }
        for case, make in cases.items():
            with self.subTest(case=case):
                self.replace_settings(make)
                found = self.draft()
                run = json.loads(found['text'])['run']
                self.assertIsNone(found['inlined'])
                self.assertEqual(run['settings_file'], 'configs/train-k1.json')
                self.assertNotIn('settings', run)
                if case in ('a link out of the code root', 'missing'):
                    self.assertIn('/run/settings_file', [problem['pointer'] for problem in found['problems']])

    def test_settings_carried_through_a_link_inside_the_code_root_and_at_the_limit(self):
        self.close(self.open())
        real = self.code / 'configs' / 'real.json'
        real.write_text('{"epochs": 9}', encoding='utf-8')
        self.replace_settings(lambda path: path.symlink_to(real))
        found = self.draft()
        self.assertEqual((found['inlined'], json.loads(found['text'])['run']['settings']),
                         ('configs/train-k1.json', {'epochs': 9}))
        exact = '{"a": "' + 'x' * (workspace.SETTINGS_LIMIT - 9) + '"}'
        self.assertEqual(len(exact.encode()), workspace.SETTINGS_LIMIT)
        self.replace_settings(lambda path: path.write_text(exact, encoding='utf-8'))
        self.assertEqual(self.draft()['inlined'], 'configs/train-k1.json')


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Operations(store_base.StoreCase):
    """The three operations through Service.call, for an inspect credential."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {local.HOME_VARIABLE: str(self.temporary / 'home')})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, arguments):
        result = self.service.call(name, arguments, INSPECTOR)
        json.dumps(result, allow_nan=False)
        return result

    def refused(self, name, arguments, actor=INSPECTOR):
        with self.assertRaises(ProjectError) as caught:
            self.service.call(name, arguments, actor)
        return caught.exception.code

    def test_map(self):
        self.assertEqual(self.call('map', {}), FIXTURE_MAP)
        self.assertEqual(self.refused('map', {}, NOBODY), 'forbidden')
        self.assertEqual(self.refused('map', {'extra': 1}), 'invalid')

    def test_note(self):
        found = self.call('note', {'path': 'fits/early-fit.md'})
        self.assertEqual(found['text'], (self.folder / 'notes/fits/early-fit.md').read_text(encoding='utf-8'))
        self.assertEqual(self.refused('note', {'path': '../tuldok.json'}), 'not-found')
        self.assertEqual(self.refused('note', {'path': 'missing.md'}), 'not-found')
        self.assertEqual(self.refused('note', {}), 'invalid')
        self.assertEqual(self.refused('note', {'path': 'decisions.md'}, NOBODY), 'forbidden')

    def test_note_does_not_open_the_project(self):
        with mock.patch('tuldok_project.builds.opened', side_effect=AssertionError('opened')):
            self.assertEqual(self.call('note', {'path': 'decisions.md'})['path'], 'decisions.md')

    def test_recipe_results(self):
        found = self.call('recipe_results', {'recipe': 'recipes/early-fit'})
        self.assertEqual(found['benchmarks'], ['rollout'])
        self.assertEqual(len(found['rows']), 2)
        self.assertEqual(len(self.call('recipe_results', {'recipe': 'early-fit', 'group': 'horizon'})['rows']), 2)
        self.assertEqual(self.refused('recipe_results', {'recipe': 'recipes/missing'}), 'not-found')
        self.assertEqual(self.refused('recipe_results', {}), 'invalid')

    def test_draft_branch(self):
        found = self.call('draft_branch', {'recipe': 'stepper-k1', 'title': 'More epochs', 'change': 'refinement',
                                           'description': 'Twice the epochs.'})
        self.assertEqual((found['reference'], found['parent'], found['inlined'], found['problems']),
                         ('recipes/more-epochs', 'recipes/stepper-k1', 'configs/train-k1.json', []))
        self.assertEqual(json.loads(found['text'])['change'], 'refinement')
        self.assertEqual(self.call('draft_branch', {'recipe': 'recipes/stepper-k1', 'title': 'x', 'name': 'k9'})
                         ['reference'], 'recipes/k9')
        self.assertEqual(self.call('definitions', {'kind': 'recipe'})['definitions'][-1]['reference'],
                         'recipes/stepper-k2')   # nothing was stored
        self.assertEqual(self.refused('draft_branch', {'recipe': 'recipes/missing', 'title': 'x'}), 'not-found')
        self.assertEqual(self.refused('draft_branch', {'recipe': 'stepper-k1', 'title': 'x', 'name': 'stepper-k2'}),
                         'invalid')
        for wrong in ({'recipe': 'stepper-k1'}, {'recipe': 'stepper-k1', 'title': ''},
                      {'recipe': 'stepper-k1', 'title': 'x' * 201}, {'recipe': 'stepper-k1', 'title': 'x', 'change': 'big'},
                      {'recipe': 'stepper-k1', 'title': 'x', 'description': 'x' * 4001},
                      {'recipe': 'stepper-k1', 'title': 'x', 'keep': True}):
            with self.subTest(arguments=wrong):
                self.assertEqual(self.refused('draft_branch', wrong), 'invalid')
        self.assertEqual(self.refused('draft_branch', {'recipe': 'stepper-k1', 'title': 'x'}, NOBODY), 'forbidden')

    def test_revert_needs_edit(self):
        self.assertEqual(self.refused('revert_definition', {'reference': 'recipes/stepper-k1'}), 'forbidden')

    def test_none_writes_activity(self):
        self.call('map', {})
        self.call('note', {'path': 'decisions.md'})
        self.call('recipe_results', {'recipe': 'recipes/early-fit'})
        self.call('draft_branch', {'recipe': 'recipes/early-fit', 'title': 'x'})
        self.assertEqual(self.service.call('activity', {}, INSPECTOR)['total'], 0)


def _run(*arguments, home):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', **{local.HOME_VARIABLE: str(home)})
    return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                          env=environment, capture_output=True, text=True, timeout=120)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Commands(store_base.StoreCase):

    def test_map(self):
        done = _run('map', self.folder, home=self.temporary / 'home')
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0].split(), ['group', 'models', 'training-policy', 'architecture', 'refinement',
                                            'component', 'no', 'kind'])
        self.assertEqual(lines[1].split(), ['Steppers', '2', '1', '1', '0', '0', '0'])
        self.assertEqual(lines[2].split(), ['Fine-tuned', 'steppers', '1', '0', '0', '1', '0', '0'])
        self.assertEqual(lines[3].split(), ['total', '3', '1', '1', '1', '0', '0'])
        self.assertIn('3 lines (2 derived, 1 input), 2 comparisons.', done.stdout)
        self.assertIn('Track charts/rollout-progression on benchmarks/rollout: rmse: median Rollout RMSE (m/s), '
                      'lower is better; 3 of 3 models have a value.', done.stdout)
        shown = _run('map', self.folder, '--json', home=self.temporary / 'home')
        self.assertEqual(json.loads(shown.stdout), FIXTURE_MAP)

    def test_branch(self):
        home = self.temporary / 'home'
        done = _run('branch', self.folder, 'stepper-k1', '--title', 'More epochs', home=home)
        self.assertEqual(done.returncode, 0, done.stderr)
        first, *rest = done.stdout.splitlines()
        self.assertEqual(first, 'recipes/more-epochs, branched from recipes/stepper-k1, with the settings of '
                                'configs/train-k1.json copied in.')
        shown = _run('branch', self.folder, 'recipes/stepper-k1', '--title', 'More epochs', '--json', home=home)
        found = json.loads(shown.stdout)
        self.assertEqual(done.stdout.split('\n', 2)[2], found['text'])   # the text after the line and a blank one
        self.assertFalse((self.folder / 'recipes' / 'more-epochs.json').exists())

        kept = _run('branch', self.folder, 'stepper-k1', '--title', 'More epochs', '--change', 'component', '--keep',
                    home=home)
        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertIn('Kept recipes/more-epochs in the database; run save to write it to the folder.', kept.stdout)
        status = _run('status', self.folder, '--json', home=home)
        self.assertEqual(json.loads(status.stdout)['unsaved'], ['recipes/more-epochs'])

        refused = _run('branch', self.folder, 'early-fit', '--title', 'Again', '--keep', home=home)
        self.assertEqual(refused.returncode, 1)
        self.assertIn('error  recipes/again.json  /run', refused.stdout)
        self.assertIn('recipes/again was not kept: it has 1 error.', refused.stderr)
        missing = _run('branch', self.folder, 'missing', '--title', 'x', home=home)
        self.assertEqual(missing.returncode, 1)
        self.assertIn('There is no recipe recipes/missing to branch from.', missing.stderr)
        self.assertEqual(_run('branch', self.folder, 'stepper-k1', home=home).returncode, 2)   # --title is required

        reverted = _run('revert', self.folder, 'recipes/more-epochs', '--json', home=home)
        self.assertEqual(json.loads(reverted.stdout), {'reference': 'recipes/more-epochs', 'dropped': True})
        again = _run('revert', self.folder, 'recipes/more-epochs', home=home)
        self.assertEqual(again.returncode, 1)
        self.assertIn('There is no definition recipes/more-epochs.', again.stderr)

    def test_revert(self):
        home = self.temporary / 'home'
        path = self.folder / 'recipes' / 'stepper-k2.json'
        edited = self.temporary / 'edited.json'
        edited.write_text(path.read_text(encoding='utf-8').replace('Stepper fine-tuned from k1', 'Edited'),
                          encoding='utf-8')
        self.assertEqual(_run('set', self.folder, 'recipes/stepper-k2', edited, home=home).returncode, 0)
        done = _run('revert', self.folder, 'recipes/stepper-k2', home=home)
        self.assertEqual((done.returncode, done.stdout), (0, 'Reverted recipes/stepper-k2 to its file in the folder.\n'))
        nothing = _run('revert', self.folder, 'recipes/stepper-k2', home=home)
        self.assertEqual(nothing.returncode, 1)
        self.assertIn('there is nothing to revert', nothing.stderr)

    def test_note(self):
        done = _run('note', self.folder, 'fits/early-fit.md', home=self.temporary / 'home')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, (self.folder / 'notes/fits/early-fit.md').read_text(encoding='utf-8'))
        missing = _run('note', self.folder, '../tuldok.json', home=self.temporary / 'home')
        self.assertEqual((missing.returncode, missing.stdout), (1, ''))
        self.assertIn("There is no note '../tuldok.json'", missing.stderr)
        self.assertEqual(_run('note', self.folder, home=self.temporary / 'home').returncode, 2)


# ------------------------------------------------------- building as before

class BuildsAsBefore(builds_base.BuildCase):
    """A derivation and a mutual comparison change nothing about building (section 1)."""

    def add_map_fields(self):
        for name, fields in (('fit-a', {'compared_with': [{'recipe': 'recipes/fit-b', 'explanation': 'A to b.'}]}),
                             ('fit-b', {'derived_from': 'recipes/fit-a',
                                        'compared_with': [{'recipe': 'recipes/fit-a', 'explanation': 'B to a.'}]})):
            path = self.folder / 'recipes' / f'{name}.json'
            document = json.loads(path.read_text(encoding='utf-8'))
            document.update(fields)
            path.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.commit('Map fields.')

    def shape(self, made):
        return [(step['reference'], step['action'], step['reasons'], step.get('subjects')) for step in made['steps']]

    def covered(self, made):
        with self.opened() as project:
            return build_requests.covers(project, made, [], every=True, scratch=False)['steps']

    def test_plan_covers_order_and_build_are_unchanged(self):
        before = self.plan(every=True)
        covers_before = self.covered(before)
        with self.opened() as project:
            order_before = project.order()
        self.add_map_fields()
        after = self.plan(every=True)
        self.assertEqual(self.shape(after), self.shape(before))
        self.assertEqual(self.covered(after), covers_before)
        with self.opened() as project:
            self.assertEqual(project.order(), order_before)
            self.assertIn({'reference': 'recipes/fit-a', 'role': 'derived'},
                          project.definition('recipes/fit-b')['uses'])
            self.assertIn({'reference': 'recipes/fit-b', 'role': 'compared'},
                          project.definition('recipes/fit-a')['used_by'])
        done = builds_base.builds.execute(self.folder, after, confirm=lambda _plan: True)
        self.assertTrue(done)
        states = self.states()
        for reference in ('datasets/numbers', 'recipes/fit-a', 'recipes/fit-b'):
            self.assertEqual(states[reference], 'built', reference)
        self.assertEqual(self.plan(every=True)['counts']['build'], 0)


if __name__ == '__main__':
    unittest.main()
