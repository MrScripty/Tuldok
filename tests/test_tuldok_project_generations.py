"""Data generations (docs/plans/training-and-curation/spec-generations.md).

The rules (generations.resolve) are tested on small documents and through the
folder's checker on a copy of the minimal fixture, without a database. The
working copy's reads (map, definitions, definition) and set_definition run
only when TULDOK_DATABASE_URL names a disposable cluster.
"""
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import generations, workspace  # noqa: E402
from tuldok_project.check import check_folder  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
import test_tuldok_project_check as check_base  # noqa: E402
import test_tuldok_project_store as store_base  # noqa: E402

DATABASE = os.environ.get('TULDOK_DATABASE_URL')


def _step(generation=None):
    document = {'kind': 'step', 'run': {'command': ['make']}}
    if generation is not None:
        document['generation'] = generation
    return document


def _dataset(generation=None, **inputs):
    document = {'kind': 'dataset', 'run': {'command': ['make'], 'inputs': inputs}}
    if generation is not None:
        document['generation'] = generation
    return document


def _recipe(*, mixed=False, derived_from=None, **inputs):
    document = {'kind': 'recipe', 'run': {'command': ['train'], 'inputs': inputs}}
    if mixed:
        document['generations'] = 'mixed'
    if derived_from:
        document['derived_from'] = derived_from
    return document


def _benchmark(*recipes, generation=None, mixed=False, cases=None):
    document = {'kind': 'benchmark', 'run': {'command': ['bench']},
                'subjects': [{'name': recipe.split('/')[1], 'recipe': recipe} for recipe in recipes]}
    if cases:
        document['cases'] = {'dataset': cases}
    if generation is not None:
        document['generation'] = generation
    if mixed:
        document['generations'] = 'mixed'
    return document


def _two_sources():
    return {'steps/old': _step('rheon-reference-v1'), 'steps/new': _step('rheon-v2'),
            'datasets/old': _dataset(solver={'from': 'steps/old', 'output': 'bin'}),
            'datasets/new': _dataset(solver={'from': 'steps/new', 'output': 'bin'})}


class Resolve(unittest.TestCase):
    """generations.resolve on documents written here."""

    def problems(self, resolved):
        return [(reference, severity, pointer) for reference, severity, pointer, _ in resolved.problems]

    def test_inherited_through_steps_and_datasets_of_several_levels(self):
        definitions = {
            'steps/solver': _step('rheon-v2'),
            'datasets/raw': _dataset(solver={'from': 'steps/solver', 'output': 'bin'}),
            'datasets/frozen': {'kind': 'dataset', 'run': {'step': 'freeze', 'inputs': {'records': 'datasets/raw'}}},
            'datasets/embedded': _dataset(records='datasets/frozen'),
            'recipes/fit': _recipe(training='datasets/embedded'),
            'benchmarks/bench': _benchmark('recipes/fit', cases='datasets/frozen'),
        }
        resolved = generations.resolve(definitions)
        self.assertEqual(resolved.problems, [])
        self.assertEqual(resolved.generation, {reference: 'rheon-v2' for reference in definitions})

    def test_inputs_that_disagree_are_an_error_naming_each(self):
        definitions = {**_two_sources(), 'datasets/both': _dataset(a='datasets/old', b='datasets/new')}
        resolved = generations.resolve(definitions)
        self.assertEqual(self.problems(resolved), [('datasets/both', 'error', '/run/inputs/a')])
        message = resolved.problems[0][3]
        self.assertIn('datasets/old (rheon-reference-v1)', message)
        self.assertIn('datasets/new (rheon-v2)', message)
        self.assertIsNone(resolved.generation['datasets/both'])

    def test_a_declaration_that_differs_from_the_inputs_is_an_error(self):
        definitions = {**_two_sources(), 'datasets/relabelled': _dataset('rheon-v2', a='datasets/old')}
        resolved = generations.resolve(definitions)
        self.assertEqual(self.problems(resolved), [('datasets/relabelled', 'error', '/generation')])
        self.assertIn('datasets/old (rheon-reference-v1)', resolved.problems[0][3])
        # Declaring does not settle inputs that disagree.
        definitions['datasets/relabelled'] = _dataset('rheon-v2', a='datasets/old', b='datasets/new')
        self.assertEqual(self.problems(generations.resolve(definitions)),
                         [('datasets/relabelled', 'error', '/generation')])

    def test_a_declaration_equal_to_the_inputs_and_unlabelled_inputs_are_fine(self):
        definitions = {**_two_sources(), 'datasets/plain': _dataset(),
                       'datasets/same': _dataset('rheon-v2', a='datasets/new'),
                       'datasets/with-plain': _dataset(a='datasets/new', b='datasets/plain')}
        resolved = generations.resolve(definitions)
        self.assertEqual(resolved.problems, [])
        self.assertEqual(resolved.generation['datasets/same'], 'rheon-v2')
        self.assertEqual(resolved.generation['datasets/with-plain'], 'rheon-v2')
        self.assertIsNone(resolved.generation['datasets/plain'])

    def test_a_recipe_on_two_generations_is_an_error(self):
        definitions = {**_two_sources(), 'recipes/fit': _recipe(old='datasets/old', new='datasets/new')}
        resolved = generations.resolve(definitions)
        self.assertEqual(self.problems(resolved), [('recipes/fit', 'error', '/run/inputs/old')])
        self.assertIn('mixes data generations', resolved.problems[0][3])
        self.assertIn('"generations": "mixed"', resolved.problems[0][3])
        self.assertEqual(resolved.generation['recipes/fit'], 'mixed')

    def test_a_recipe_declared_mixed_is_a_warning(self):
        definitions = {**_two_sources(), 'recipes/fit': _recipe(mixed=True, old='datasets/old', new='datasets/new')}
        resolved = generations.resolve(definitions)
        self.assertEqual(self.problems(resolved), [('recipes/fit', 'warning', '/generations')])
        self.assertEqual(resolved.generation['recipes/fit'], 'mixed')

    def test_a_recipe_takes_only_its_data_inputs(self):
        # A model input (another recipe) and a parent of another generation are fine: fine-tuning across generations.
        definitions = {**_two_sources(), 'recipes/old': _recipe(training='datasets/old'),
                       'recipes/tuned': _recipe(derived_from='recipes/old', training='datasets/new',
                                                start='recipes/old')}
        resolved = generations.resolve(definitions)
        self.assertEqual(resolved.problems, [])
        self.assertEqual((resolved.generation['recipes/old'], resolved.generation['recipes/tuned']),
                         ('rheon-reference-v1', 'rheon-v2'))

    def test_a_benchmark_whose_subjects_span_generations_warns_unless_mixed(self):
        definitions = {**_two_sources(), 'recipes/a': _recipe(training='datasets/old'),
                       'recipes/b': _recipe(training='datasets/new'), 'recipes/plain': _recipe(),
                       'benchmarks/bench': _benchmark('recipes/a', 'recipes/b', 'recipes/plain')}
        resolved = generations.resolve(definitions)
        self.assertEqual(self.problems(resolved), [('benchmarks/bench', 'warning', '/subjects')])
        self.assertIn('rheon-reference-v1: a; rheon-v2: b', resolved.problems[0][3])
        self.assertIsNone(resolved.generation['benchmarks/bench'])
        definitions['benchmarks/bench'] = _benchmark('recipes/a', 'recipes/b', mixed=True)
        self.assertEqual(generations.resolve(definitions).problems, [])

    def test_a_benchmark_declares_its_cases(self):
        definitions = {**_two_sources(), 'benchmarks/bench': _benchmark(cases='datasets/old')}
        self.assertEqual(generations.resolve(definitions).generation['benchmarks/bench'], 'rheon-reference-v1')
        definitions['benchmarks/bench'] = _benchmark(cases='datasets/old', generation='rheon-reference-v1')
        self.assertEqual(generations.resolve(definitions).problems, [])
        definitions['benchmarks/bench'] = _benchmark(cases='datasets/old', generation='rheon-v2')
        resolved = generations.resolve(definitions)
        self.assertEqual(self.problems(resolved), [('benchmarks/bench', 'error', '/generation')])
        self.assertEqual(resolved.generation['benchmarks/bench'], 'rheon-v2')
        definitions['benchmarks/bench'] = _benchmark(generation='rheon-v2')   # no cases: the declaration alone
        self.assertEqual(generations.resolve(definitions).generation['benchmarks/bench'], 'rheon-v2')

    def test_an_unlabelled_project_has_no_generation_and_no_problem(self):
        definitions = {'steps/s': _step(), 'datasets/d': _dataset(s={'from': 'steps/s', 'output': 'x'}),
                       'recipes/r': _recipe(training='datasets/d'), 'benchmarks/b': _benchmark('recipes/r')}
        resolved = generations.resolve(definitions)
        self.assertEqual(resolved.problems, [])
        self.assertEqual(set(resolved.generation.values()), {None})
        self.assertEqual(generations.labelled(definitions), {})

    def test_a_cycle_of_inputs_ends(self):
        definitions = {'datasets/a': _dataset('g1', b='datasets/b'), 'datasets/b': _dataset(a='datasets/a')}
        resolved = generations.resolve(definitions)
        self.assertEqual(resolved.generation['datasets/a'], 'g1')


class Folder(check_base.FixtureCopy):
    """The rules through check_folder on the minimal fixture (steps/solver -> datasets/waves -> recipes/stepper-k1)."""

    def test_the_unlabelled_fixture_checks_as_before(self):
        self.assertEqual(check_folder(self.project).problems, [])

    def test_a_label_on_the_solver_reaches_the_dataset_the_recipe_and_the_benchmark(self):
        self.edit('steps/solver.json', '/generation', 'toy-solver-1')
        report = check_folder(self.project)
        self.assertEqual(report.problems, [])
        decoded = {reference: d.document for reference, d in report.definitions.items()}
        self.assertEqual(generations.labelled(decoded), {
            'steps/solver': 'toy-solver-1', 'datasets/waves': 'toy-solver-1',
            'recipes/stepper-k1': 'toy-solver-1', 'recipes/stepper-k2': 'toy-solver-1',
            'benchmarks/rollout': 'toy-solver-1'})

    def test_the_schema_holds_the_name_rule(self):
        for value in ('mixed', 'Rheon-V2', '', 'x' * 65, 'a b'):
            with self.subTest(value=value):
                self.edit('datasets/waves.json', '/generation', value)
                self.assertProblem(check_folder(self.project), 'datasets/waves.json', '/generation')
        self.edit('datasets/waves.json', '/generation', 'rheon-v2.1_b')
        self.edit('recipes/stepper-k1.json', '/generations', 'all')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/generations')

    def test_a_recipe_mixing_two_generations(self):
        waves = json.loads((self.project / 'datasets' / 'waves.json').read_text(encoding='utf-8'))
        self.edit('datasets/waves.json', '/generation', 'rheon-reference-v1')
        waves['generation'] = 'rheon-v2'
        self.write('datasets/waves-new.json', json.dumps(waves, indent=2) + '\n')
        self.edit('recipes/stepper-k1.json', '/run/inputs/newer', 'datasets/waves-new')
        report = check_folder(self.project)
        self.assertEqual(report.count('error'), 1)
        problem = self.assertProblem(report, 'recipes/stepper-k1.json', '/run/inputs/training', alone=False)
        self.assertIn('mixes data generations: datasets/waves (rheon-reference-v1), datasets/waves-new (rheon-v2)',
                      problem.message)
        # The benchmark measures k1 (mixed) beside k2 (rheon-reference-v1): a warning, as long as it does not say so.
        warning = self.assertProblem(report, 'benchmarks/rollout.json', '/subjects', 'warning', alone=False)
        self.assertIn('mixed: stepper-k1; rheon-reference-v1: stepper-k2', warning.message)
        self.edit('recipes/stepper-k1.json', '/generations', 'mixed')
        self.edit('benchmarks/rollout.json', '/generations', 'mixed')
        self.assertProblem(check_folder(self.project), 'recipes/stepper-k1.json', '/generations', 'warning')


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class WorkingCopy(store_base.StoreCase):
    """The reads and set_definition on the minimal fixture."""

    def test_an_unlabelled_project_reads_without_generation(self):
        project = self.open()
        self.assertFalse(any('generation' in model for model in workspace.project_map(project)['models']))
        self.assertFalse(any('generation' in row for row in project.definitions()))
        self.assertNotIn('generation', project.definition('datasets/waves'))

    def test_the_reads_carry_the_generation(self):
        self.write('steps/solver', self.edited('steps/solver', lambda d: d.update(generation='toy-solver-1')))
        project = self.open()
        models = {model['reference']: model for model in workspace.project_map(project)['models']}
        self.assertEqual(models['recipes/stepper-k1']['generation'], 'toy-solver-1')
        self.assertEqual(models['recipes/stepper-k2']['generation'], 'toy-solver-1')
        self.assertNotIn('generation', models['recipes/early-fit'])   # earlier work with no data input
        rows = {row['reference']: row for row in project.definitions()}
        self.assertEqual(rows['datasets/waves']['generation'], 'toy-solver-1')
        self.assertNotIn('generation', rows['environments/lab-cpu'])
        self.assertEqual(project.definition('benchmarks/rollout')['generation'], 'toy-solver-1')
        self.assertEqual(project.definition('steps/solver')['generation'], 'toy-solver-1')

    def test_set_definition_refuses_a_mixing_recipe_and_keeps_a_mixed_one(self):
        self.write('datasets/waves', self.edited('datasets/waves', lambda d: d.update(generation='rheon-reference-v1')))
        project = self.open()
        newer = self.edited('datasets/waves', lambda d: d.update(generation='rheon-v2'))
        project.set_definition('datasets/waves-new', newer)

        def both(document, mixed=False):
            document['run']['inputs']['newer'] = 'datasets/waves-new'
            if mixed:
                document['generations'] = 'mixed'

        with self.assertRaises(ProjectError) as caught:
            project.set_definition('recipes/stepper-k1', self.edited('recipes/stepper-k1', both))
        self.assertEqual([(p.path, p.pointer) for p in caught.exception.problems],
                         [('recipes/stepper-k1.json', '/run/inputs/training')])
        project.set_definition('recipes/stepper-k1', self.edited('recipes/stepper-k1', lambda d: both(d, True)))
        models = {model['reference']: model for model in workspace.project_map(project)['models']}
        self.assertEqual(models['recipes/stepper-k1']['generation'], 'mixed')


if __name__ == '__main__':
    unittest.main()
