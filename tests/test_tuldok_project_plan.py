"""The rebuild plan (docs/plans/definition-first-projects/spec-m4.md).

make_plan is tested as a pure function over the fixture's decoded
definitions, changed in memory where a test needs another shape of graph.
build_plan is tested against the database copy only when TULDOK_DATABASE_URL
names a disposable cluster (spec-m1-m2.md, section 1); each of those tests
copies tests/fixtures/tuldok_project/minimal, gives it a fresh project id and
drops that project's schema afterwards. One of them makes starting a process
and opening a file fail while the plan is made.
"""
import builtins
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import graph, plan, store  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / 'tests' / 'fixtures' / 'tuldok_project' / 'minimal'
DATABASE = os.environ.get('TULDOK_DATABASE_URL')


def _fixture_documents():
    found = {}
    for path in sorted((FIXTURE / 'project').glob('*/*.json')):
        found[f'{path.parent.name}/{path.stem}'] = json.loads(path.read_text(encoding='utf-8'))
    return found


def _references(made):
    return [step['reference'] for step in made['steps']]


def _step(made, reference):
    return next(step for step in made['steps'] if step['reference'] == reference)


class PlanCase(unittest.TestCase):

    def setUp(self):
        self.documents = _fixture_documents()

    def mark(self, reference, rebuild, reason=None):
        self.documents[reference]['earlier_work'] = {'rebuild': rebuild, 'reason': reason or f'{reference} test.'}

    def make(self, *targets, every=False):
        return plan.make_plan(self.documents, list(targets), every=every)


class Closure(PlanCase):
    """Which definitions enter a plan: section 2."""

    def test_inputs_and_environments_are_followed_models_are_not(self):
        made = self.make('recipes/stepper-k2')
        self.assertEqual(sorted(_references(made)), ['datasets/waves', 'environments/lab-cpu', 'recipes/stepper-k1',
                                                     'recipes/stepper-k2', 'steps/solver'])
        self.assertNotIn('models/stepper', _references(made))  # role model

    def test_subjects_are_followed_cases_and_charts_are_not(self):
        other = copy.deepcopy(self.documents['datasets/waves'])
        other['title'] = 'Other scenes'
        self.documents['datasets/other'] = other
        self.documents['benchmarks/rollout']['cases']['dataset'] = 'datasets/other'
        references = _references(self.make('benchmarks/rollout'))
        for reference in ('recipes/stepper-k1', 'recipes/stepper-k2'):
            self.assertIn(reference, references)  # role subject:<name>
        self.assertNotIn('recipes/early-fit', references)  # a blocked subject recipe is not a step
        self.assertNotIn('datasets/other', references)  # role cases
        self.assertFalse([reference for reference in references if reference.startswith(('charts/', 'models/'))])

    def test_nothing_is_followed_out_of_a_blocked_step(self):
        self.mark('datasets/waves', 'no', 'The scenes were made by hand.')
        made = self.make('recipes/stepper-k1')
        self.assertEqual(_references(made), ['recipes/stepper-k1'])  # not its dataset, solver or environment
        self.assertEqual(made['counts'], {'build': 0, 'set-up': 0, 'blocked': 1, 'ready': 0, 'built': 0})
        self.assertEqual(made['steps'][0]['blocked_by'], [{'reference': 'datasets/waves', 'rebuild': 'no',
                                                           'reason': 'The scenes were made by hand.'}])
        # A cause is a step when it is a target itself.
        both = self.make('recipes/stepper-k1', 'datasets/waves')
        self.assertEqual(sorted(_references(both)), ['datasets/waves', 'recipes/stepper-k1'])

    def test_a_blocked_subject_recipe_and_what_only_it_uses_are_not_steps(self):
        extra = copy.deepcopy(self.documents['datasets/waves'])
        extra['title'] = 'Extra scenes'
        self.documents['datasets/extra'] = extra
        self.documents['recipes/stepper-k2']['run']['inputs']['extra'] = 'datasets/extra'
        self.mark('recipes/stepper-k2', 'needs-work')
        made = self.make('benchmarks/rollout')
        references = _references(made)
        for reference in ('recipes/stepper-k2', 'datasets/extra', 'recipes/early-fit'):
            self.assertNotIn(reference, references)
        self.assertEqual(sorted(references), ['benchmarks/rollout', 'datasets/waves', 'environments/lab-cpu',
                                              'recipes/stepper-k1', 'steps/solver'])
        skipped = _step(made, 'benchmarks/rollout')['subjects']['skipped']
        self.assertEqual([(item['name'], item['recipe']) for item in skipped],
                         [('stepper-k2', 'recipes/stepper-k2'), ('early-fit', 'recipes/early-fit')])
        self.assertEqual(made['counts']['blocked'], 0)

    def test_an_environment_alone(self):
        made = self.make('environments/lab-cpu')
        self.assertEqual([(step['reference'], step['action']) for step in made['steps']],
                         [('environments/lab-cpu', 'set-up')])
        self.assertTrue(made['buildable'])

    def test_a_chart_is_replaced_by_its_benchmark(self):
        made = self.make('charts/rollout-ranking')
        self.assertEqual(made['targets'], ['benchmarks/rollout'])
        self.assertEqual(made['steps'], self.make('benchmarks/rollout')['steps'])
        self.assertEqual(made['notes'], ['charts/rollout-ranking is drawn from benchmarks/rollout, '
                                         'which is planned in its place.'])

    def test_a_model_is_not_built(self):
        made = self.make('models/stepper')
        self.assertEqual(made['targets'], ['models/stepper'])
        self.assertEqual(made['steps'], [])
        self.assertTrue(made['buildable'])
        self.assertEqual(made['counts'], {'build': 0, 'set-up': 0, 'blocked': 0, 'ready': 0, 'built': 0})
        self.assertEqual(made['notes'], ['models/stepper is a model; a model is not built, '
                                         'only the recipes that train it.'])

    def test_several_targets_share_their_steps(self):
        made = self.make('recipes/stepper-k1', 'steps/solver', 'charts/rollout-ranking', 'benchmarks/rollout')
        self.assertEqual(made['targets'], ['recipes/stepper-k1', 'steps/solver', 'benchmarks/rollout'])
        references = _references(made)
        self.assertEqual(len(references), len(set(references)))
        self.assertEqual(sorted(references), sorted(_references(self.make('benchmarks/rollout'))))
        self.assertTrue(self.make('recipes/stepper-k1', 'steps/solver')['buildable'])

    def test_every(self):
        made = self.make(every=True)
        self.assertTrue(made['every'])
        self.assertEqual(made['targets'], ['benchmarks/rollout', 'datasets/waves', 'recipes/early-fit',
                                           'recipes/stepper-k1', 'recipes/stepper-k2', 'steps/solver'])
        self.assertEqual(sorted(_references(made)), sorted(made['targets'] + ['environments/lab-cpu']))
        self.assertFalse(made['buildable'])  # recipes/early-fit is a target
        self.assertEqual(made['blocked_targets'], ['recipes/early-fit'])

    def test_an_unknown_target(self):
        with self.assertRaisesRegex(ValueError, 'There is no definition datasets/nothing.'):
            self.make('datasets/nothing')


class Steps(PlanCase):
    """Order, actions and the fields of a step: section 3."""

    def test_order_puts_each_step_after_what_it_uses(self):
        made = self.make('benchmarks/rollout')
        references = _references(made)
        self.assertEqual([step['number'] for step in made['steps']], list(range(1, len(references) + 1)))
        self.assertEqual(references, graph.order({reference: self.documents[reference] for reference in references}))
        position = {reference: index for index, reference in enumerate(references)}
        for edge in graph.edges(self.documents):
            if edge.from_ref in position and edge.to_ref in position:
                self.assertLess(position[edge.to_ref], position[edge.from_ref], edge)

    def test_every_action(self):
        self.mark('recipes/stepper-k2', 'needs-work')
        made = self.make('benchmarks/rollout', 'recipes/stepper-k2', 'recipes/early-fit')
        actions = {step['reference']: (step['state'], step['action']) for step in made['steps']}
        self.assertEqual(actions, {
            'environments/lab-cpu': ('not-set-up', 'set-up'),
            'steps/solver': ('not-built', 'build'),
            'datasets/waves': ('not-built', 'build'),
            'recipes/stepper-k1': ('not-built', 'build'),
            'recipes/stepper-k2': ('needs-work', 'blocked'),
            'recipes/early-fit': ('cannot-rebuild', 'blocked'),
            'benchmarks/rollout': ('not-built', 'build'),
        })
        self.assertEqual(made['counts'], {'build': 4, 'set-up': 1, 'blocked': 2, 'ready': 0, 'built': 0})
        self.assertFalse(made['buildable'])
        self.assertEqual(made['blocked_targets'], ['recipes/stepper-k2', 'recipes/early-fit'])

    def test_fields_of_a_step(self):
        made = self.make('recipes/stepper-k2')
        step = _step(made, 'recipes/stepper-k2')
        self.assertEqual(step['kind'], 'recipe')
        self.assertEqual(step['title'], 'Stepper fine-tuned from k1')
        self.assertEqual(step['command'][:3], ['python', 'lab/train.py', '--start'])
        self.assertIn('{inputs.start}', step['command'])  # placeholders not filled in
        self.assertEqual(step['environment'], 'environments/lab-cpu')
        self.assertEqual(step['inputs'], {'start': {'reference': 'recipes/stepper-k1', 'output': 'weights'},
                                          'training': {'reference': 'datasets/waves', 'output': None}})
        self.assertEqual(step['resources'], {name: None for name in plan.RESOURCES})
        self.assertIsNone(step['estimate'])
        self.assertEqual((step['blocked_by'], step['blocked_by_more']), ([], 0))
        self.assertNotIn('subjects', step)
        self.assertEqual(_step(made, 'recipes/stepper-k1')['resources'],
                         {'gpu': False, 'cpu_threads': 4, 'memory_gb': 2, 'wall_hours': 0.5, 'disk_gb': 0.1})
        environment = _step(made, 'environments/lab-cpu')
        self.assertEqual((environment['command'], environment['environment'], environment['inputs']), (None, None, {}))
        # A dataset's estimate command is never run: the estimate stays null.
        self.assertIsNone(_step(made, 'datasets/waves')['estimate'])


class Causes(PlanCase):
    """blocked_by: root causes, nearest first, at most five."""

    def test_a_cause_two_inputs_away_and_no_blocked_ancestor_in_between(self):
        self.mark('steps/solver', 'no', 'The solver source was lost.')
        made = self.make('recipes/stepper-k1')
        self.assertFalse(made['buildable'])
        step = _step(made, 'recipes/stepper-k1')
        self.assertEqual(step['action'], 'blocked')
        # datasets/waves is blocked too, but its own label is not the cause; neither is a step.
        self.assertEqual(step['blocked_by'], [{'reference': 'steps/solver', 'rebuild': 'no',
                                               'reason': 'The solver source was lost.'}])
        self.assertEqual(_references(made), ['recipes/stepper-k1'])

    def test_nearest_first_then_by_reference(self):
        self.mark('recipes/stepper-k2', 'needs-work')
        self.mark('steps/solver', 'no')
        self.mark('recipes/stepper-k1', 'needs-work')
        self.mark('datasets/waves', 'needs-work')
        step = _step(self.make('recipes/stepper-k2'), 'recipes/stepper-k2')
        self.assertEqual([(cause['reference'], cause['rebuild']) for cause in step['blocked_by']], [
            ('recipes/stepper-k2', 'needs-work'),   # itself, no edge away
            ('datasets/waves', 'needs-work'),       # one input away; before recipes/ by reference
            ('recipes/stepper-k1', 'needs-work'),   # one input away
            ('steps/solver', 'no'),                 # two inputs away by the shortest way
        ])

    def test_at_most_five_with_a_count_of_the_rest(self):
        definitions = {'recipes/many': {'kind': 'recipe', 'title': 'Many', 'run': {
            'command': ['true'], 'inputs': {f'in_{index}': f'datasets/d{index}' for index in range(7)}}}}
        for index in range(7):
            definitions[f'datasets/d{index}'] = {'kind': 'dataset', 'title': f'D{index}',
                                                 'earlier_work': {'rebuild': 'no', 'reason': f'Lost {index}.'}}
        step = _step(plan.make_plan(definitions, ['recipes/many']), 'recipes/many')
        self.assertEqual([cause['reference'] for cause in step['blocked_by']],
                         [f'datasets/d{index}' for index in range(5)])
        self.assertEqual(step['blocked_by_more'], 2)

    def test_other_edges_carry_no_cause(self):
        self.documents['models/stepper']['earlier_work'] = {'rebuild': 'no', 'reason': 'Lost.'}
        made = self.make('recipes/stepper-k1')
        self.assertTrue(made['buildable'])
        self.assertEqual(_step(made, 'recipes/stepper-k1')['action'], 'build')


class Subjects(PlanCase):
    """A benchmark runs the subjects it can and is never blocked by one."""

    def test_a_blocked_recipe_is_skipped_and_a_subject_without_a_recipe_runs(self):
        self.documents['benchmarks/rollout']['subjects'].append({'name': 'baseline', 'title': 'Baseline'})
        made = self.make('benchmarks/rollout')
        step = _step(made, 'benchmarks/rollout')
        self.assertEqual(step['action'], 'build')
        self.assertEqual(step['subjects'], {
            'run': ['stepper-k1', 'stepper-k2', 'baseline'],
            'skipped': [{'name': 'early-fit', 'recipe': 'recipes/early-fit',
                         'reason': 'its recipe recipes/early-fit is blocked'}]})
        self.assertEqual((step['blocked_by'], step['blocked_by_more']), ([], 0))
        self.assertTrue(made['buildable'])

    def test_one_runnable_subject_is_enough(self):
        self.mark('recipes/stepper-k2', 'no')
        step = _step(self.make('benchmarks/rollout'), 'benchmarks/rollout')
        self.assertEqual((step['action'], step['subjects']['run']), ('build', ['stepper-k1']))

    def test_no_subject_to_run(self):
        self.mark('recipes/stepper-k1', 'no')   # blocks stepper-k2 through its input as well
        made = self.make('benchmarks/rollout')
        step = _step(made, 'benchmarks/rollout')
        self.assertEqual(_references(made), ['benchmarks/rollout'])  # nothing is followed out of it
        self.assertEqual(step['state'], 'not-built')
        self.assertEqual(step['action'], 'blocked')
        self.assertEqual(step['subjects']['run'], [])
        self.assertEqual(step['blocked_by'], [])
        self.assertFalse(made['buildable'])


class Totals(PlanCase):
    """Section 4: build steps only, with how many declare no figure."""

    def test_fixture_figures(self):
        made = self.make('benchmarks/rollout')
        self.assertEqual((made['disk_gb'], made['disk_unknown']), (0.1, 4))
        self.assertEqual((made['wall_hours'], made['wall_unknown']), (0.6, 3))  # solver 0.1 + stepper-k1 0.5
        self.assertEqual(made['gpu_steps'], 0)

    def test_every_figure_declared_and_blocked_steps_not_counted(self):
        for index, reference in enumerate(('steps/solver', 'datasets/waves', 'recipes/stepper-k1',
                                           'recipes/stepper-k2', 'benchmarks/rollout'), 1):
            self.documents[reference]['run']['resources'] = {'gpu': index % 2 == 0, 'disk_gb': index,
                                                             'wall_hours': index / 4}
        self.mark('recipes/stepper-k2', 'needs-work')
        made = self.make('benchmarks/rollout')
        self.assertEqual(made['counts']['build'], 4)
        self.assertEqual((made['disk_gb'], made['disk_unknown']), (1 + 2 + 3 + 5, 0))
        self.assertEqual((made['wall_hours'], made['wall_unknown']), (2.75, 0))
        self.assertEqual(made['gpu_steps'], 1)  # datasets/waves; stepper-k2 is blocked

    def test_nothing_to_build(self):
        made = self.make('recipes/early-fit')
        self.assertEqual((made['disk_gb'], made['disk_unknown'], made['wall_hours'], made['wall_unknown'],
                          made['gpu_steps']), (0, 0, 0, 0, 0))


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class BuildPlan(unittest.TestCase):
    """build_plan reads the database copy and nothing else."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name) / 'minimal'
        shutil.copytree(FIXTURE, base)
        self.folder = base / 'project'
        self.project_id = uuid.uuid4().hex
        project_file = self.folder / 'tuldok.json'
        document = json.loads(project_file.read_text(encoding='utf-8'))
        document['id'] = self.project_id
        project_file.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
        self.addCleanup(store.drop_project, self.project_id)
        self.project = store.open_project(self.folder)
        self.addCleanup(self.project.close)

    def test_the_same_plan_as_from_the_files(self):
        self.assertEqual(plan.build_plan(self.project, ['benchmarks/rollout']),
                         plan.make_plan(_fixture_documents(), ['benchmarks/rollout']))
        self.assertEqual(plan.build_plan(self.project, [], every=True)['targets'],
                         plan.every_target(_fixture_documents()))

    def test_unknown_references(self):
        for reference, message in (('datasets/nothing', 'There is no definition datasets/nothing.'),
                                   ('nothing', "'nothing' is not a reference such as datasets/<name>.")):
            with self.assertRaises(ProjectError) as raised:
                plan.build_plan(self.project, ['steps/solver', reference])
            self.assertEqual((raised.exception.code, str(raised.exception)), ('not-found', message))

    def test_nothing_is_run_and_no_file_is_opened(self):
        def refuse(*args, **kwargs):
            raise AssertionError(f'A plan must not run or open anything: {args!r}')

        expected = plan.make_plan(_fixture_documents(), [], every=True)
        patches = [mock.patch.object(subprocess, 'Popen', refuse), mock.patch.object(os, 'system', refuse),
                   mock.patch.object(os, 'fork', refuse), mock.patch.object(os, 'posix_spawn', refuse),
                   mock.patch.object(os, 'posix_spawnp', refuse), mock.patch.object(os, 'execv', refuse),
                   mock.patch.object(os, 'execve', refuse), mock.patch.object(os, 'open', refuse),
                   mock.patch.object(builtins, 'open', refuse), mock.patch.object(io, 'open', refuse)]
        for patcher in patches:
            patcher.start()
        try:
            made = plan.build_plan(self.project, [], every=True)
        finally:
            for patcher in patches:
                patcher.stop()
        self.assertEqual(made, expected)
        with self.assertRaises(AssertionError):  # the guard works
            with mock.patch.object(builtins, 'open', refuse):
                open(self.folder / 'tuldok.json')


if __name__ == '__main__':
    unittest.main()
