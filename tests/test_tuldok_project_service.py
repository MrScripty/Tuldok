"""The operations table and the service of a served project folder (spec-m7.md, sections 2, 3 and 5).

The table is tested as data. Everything else needs a database and runs only
when TULDOK_DATABASE_URL names a disposable cluster. The service tests start
from test_tuldok_project_builds.BuildCase (a Git-committed copy of the
buildable fixture with its environment connected, dropped afterwards); the
results tests from test_tuldok_project_store.StoreCase (a copy of the
minimal fixture). Every result is passed through json.dumps(allow_nan=False).
The builds run the fixture's stand-in scripts; no GPU is used.
"""
import json
import os
from pathlib import Path
import sys
import unittest

import jsonschema
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from metadata import connection_info  # noqa: E402
from tuldok_project import operations, store  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402
import test_tuldok_project_store as store_base  # noqa: E402

ALL_SCOPES = ['admin', 'approve-execution', 'approve-review', 'cancel', 'edit', 'execute', 'expose-holdout',
              'freeze', 'inspect']
OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner', 'scopes': ALL_SCOPES}


def agent(*scopes):
    return {'actor_id': f'agent-{"-".join(scopes) or "none"}', 'kind': 'agent', 'label': 'An agent',
            'scopes': list(scopes)}


EVERY_AGENT_SCOPE = agent('inspect', 'edit', 'execute', 'cancel', 'freeze', 'expose-holdout')
REQUEST_OPERATIONS = ('request_build', 'approve_build', 'decline_build', 'cancel_build', 'build_requests',
                      'build_request')
SECRET = 'not-to-be-sent-7f3a'


class Table(unittest.TestCase):
    """operations.OPERATIONS as data."""

    def test_every_operation_is_declared_once(self):
        names = [operation.name for operation in operations.OPERATIONS]
        self.assertEqual(len(names), 92)  # spec-t6.md section 6 (7), spec-t7.md (2), and the rows of spec-m7.md section 2, of section 2 of spec-w1.md and spec-w3.md, of section 3 of spec-d1.md and spec-d2.md, of section 5 of spec-d4.md, of sections 2 and 4 of spec-d5.md, of section 2 of spec-d6.md, of section 3 of spec-t2.md, of section 4 of spec-t1.md, of sections 2 to 4 of spec-t3.md and spec-t5.md (7), and of section 6 of spec-t4.md (4)
        self.assertEqual(len(set(names)), len(names))
        for name in REQUEST_OPERATIONS:
            self.assertIsNotNone(operations.by_name(name))
        self.assertIsNone(operations.by_name('nothing'))
        self.assertIs(operations.by_name('summary'), operations.OPERATIONS[0])

    def test_every_schema_is_closed_and_valid(self):
        for operation in operations.OPERATIONS:
            with self.subTest(operation.name):
                jsonschema.Draft202012Validator.check_schema(operation.arguments)
                self.assertEqual(operation.arguments['type'], 'object')
                self.assertIs(operation.arguments['additionalProperties'], False)
                self.assertTrue(set(operation.arguments['required']) <= set(operation.arguments['properties']))

    def test_every_row_has_a_summary_sentence_a_rule_and_result_keys(self):
        for operation in operations.OPERATIONS:
            with self.subTest(operation.name):
                summary = operation.summary
                self.assertTrue(summary[0].isupper() and summary.endswith('.'), summary)
                self.assertNotIn('. ', summary[:-1])
                self.assertIn(operation.who, operations.WHO)
                self.assertIsInstance(operation.mutation, bool)
                self.assertTrue(operation.result)
                self.assertEqual(len(set(operation.result)), len(operation.result))

    def test_mutations_and_owner_rows(self):
        mutations = {operation.name for operation in operations.OPERATIONS if operation.mutation}
        self.assertEqual(mutations, {'set_definition', 'remove_definition', 'revert_definition', 'save', 'resolve_conflict',
                                     'import_values', 'check_environment', 'connect_environment',
                                     'disconnect_environment', 'request_build', 'approve_build', 'decline_build',
                                     'cancel_build', 'cancel_run', 'stop_run', 'set_annotation', 'revert_annotations',
                                     'set_endpoint', 'set_embedder', 'keep_annotation',
                                     'serve_start', 'serve_approve', 'serve_stop', 'serve_values'})
        owner = {operation.name for operation in operations.OPERATIONS if operation.who == 'owner'}
        self.assertEqual(owner, {'connect_environment', 'disconnect_environment', 'approve_build', 'decline_build',
                                 'set_endpoint', 'find_endpoints', 'set_embedder', 'serve_approve'})

    def test_error_status(self):
        self.assertEqual([operations.error_status(code) for code in
                          ('not-found', 'invalid', 'forbidden', 'conflict', 'unavailable', 'stale')],
                         [404, 400, 403, 409, 409, 409])


def plain(test, result):
    """The result as JSON text; fails the test when it is not plain JSON."""
    test.assertIsInstance(result, dict)
    return json.dumps(result, allow_nan=False)


class ServiceCase(builds_base.BuildCase):
    """BuildCase with a Service for the copy."""

    def setUp(self):
        super().setUp()
        self.service = Service(self.folder)
        self.service.start()
        self.addCleanup(self.service.close)

    def call(self, name, arguments=None, actor=OWNER):
        result = self.service.call(name, arguments or {}, actor)
        plain(self, result)
        return result

    def refused(self, name, arguments=None, actor=OWNER):
        with self.assertRaises(ProjectError) as caught:
            self.service.call(name, arguments or {}, actor)
        return caught.exception

    def activity(self):
        return self.call('activity', {'limit': 500})['items']


class WhoRules(ServiceCase):

    def test_inspect(self):
        self.assertEqual(self.call('summary', actor=agent('inspect'))['worker'], 'running')
        unstarted = Service(self.folder)
        self.addCleanup(unstarted.close)
        self.assertEqual(unstarted.call('summary', {}, OWNER)['worker'], 'stopped')  # before start()
        self.call('summary', actor=OWNER)
        self.assertEqual(self.refused('summary', actor=agent()).code, 'forbidden')
        self.assertEqual(self.refused('summary', actor=agent('edit', 'cancel')).code, 'forbidden')
        self.assertEqual(self.refused('summary', actor={**OWNER, 'scopes': ['edit']}).code, 'forbidden')

    def test_edit(self):
        self.assertEqual(self.refused('save', actor=agent('inspect', 'cancel', 'execute')).code, 'forbidden')
        self.call('save', actor=agent('edit'))
        self.call('save', actor=OWNER)

    def test_cancel(self):
        self.assertEqual(self.refused('cancel_run', {'run': 'abcdef12'}, actor=agent('inspect', 'edit')).code,
                         'forbidden')
        # Past the actor check, the run is looked for.
        self.assertEqual(self.refused('cancel_run', {'run': 'abcdef12'}, actor=agent('cancel')).code, 'not-found')
        self.assertEqual(self.refused('cancel_run', {'run': 'abcdef12'}, actor=OWNER).code, 'not-found')

    def test_request(self):
        arguments = {'targets': ['benchmarks/score']}
        self.assertEqual(self.refused('request_build', arguments, actor=agent('inspect', 'edit', 'cancel')).code,
                         'forbidden')
        self.assertEqual(self.refused('request_build', arguments, actor=agent('execute')).code, 'forbidden')
        # Past the actor check, the request is made (an agent's waits) or refused for what it asks.
        self.assertEqual(self.call('request_build', arguments, actor=agent('inspect', 'execute'))['state'],
                         'awaiting-approval')
        self.assertEqual(self.refused('request_build', {'targets': []}, actor=OWNER).code, 'nothing-to-build')

    def test_owner(self):
        arguments = {'reference': 'environments/test-python', 'interpreter': sys.executable}
        self.assertEqual(self.refused('connect_environment', arguments, actor=EVERY_AGENT_SCOPE).code, 'forbidden')
        self.assertEqual(self.refused('approve_build', {'request': 'abcdef12'}, actor=EVERY_AGENT_SCOPE).code,
                         'forbidden')
        self.assertEqual(self.refused('connect_environment', arguments,
                                      actor={**OWNER, 'scopes': ['inspect', 'edit']}).code, 'forbidden')
        self.assertTrue(self.call('connect_environment', arguments)['ok'])
        self.assertEqual(self.refused('approve_build', {'request': 'abcdef12'}).code, 'not-found')

    def test_forbidden_calls_write_no_activity(self):
        self.refused('save', actor=agent('inspect'))
        self.refused('disconnect_environment', {'reference': 'environments/test-python'}, actor=EVERY_AGENT_SCOPE)
        self.assertEqual(self.activity(), [])

    def test_unknown_operation(self):
        self.assertEqual(self.refused('drop_everything').code, 'not-found')


class Arguments(ServiceCase):

    def test_invalid_arguments_are_refused_with_one_problem_per_error(self):
        refused = self.refused('results', {'benchmark': '', 'limit': 5000, 'colour': 'red'})
        self.assertEqual(refused.code, 'invalid')
        self.assertEqual(len(refused.problems), 3)
        self.assertEqual(sorted(problem.pointer for problem in refused.problems), ['/', '/benchmark', '/limit'])
        self.assertEqual(self.refused('plan', {'targets': ['x'] * 51}).code, 'invalid')
        self.assertEqual(self.refused('summary', ['not', 'an', 'object']).code, 'invalid')
        self.assertEqual(self.refused('chart', {}).code, 'invalid')

    def test_an_invalid_mutation_is_recorded(self):
        self.assertEqual(self.refused('set_definition', {'reference': 'recipes/fit-b'}).code, 'invalid')
        [row] = self.activity()
        self.assertEqual((row['operation'], row['target'], row['outcome']), ('set_definition', 'recipes/fit-b',
                                                                             'invalid'))


class Reads(ServiceCase):
    """Every read operation answers with its declared keys and plain JSON."""

    def test_every_read(self):
        self.build_all()
        run_id = self.runs('recipes/fit-a')[0]['id']
        arguments = {
            'summary': {}, 'status': {}, 'check': {}, 'definitions': {'kind': 'recipe'},
            'definition': {'reference': 'recipes/fit-a'}, 'graph': {}, 'results_overview': {},
            'results': {'benchmark': 'benchmarks/score', 'limit': 3}, 'values': {'benchmark': 'score', 'subject': 'fit-a'},
            'chart': {'chart': 'score-ranking', 'svg': True, 'theme': 'dark'}, 'report': {'theme': 'dark'},
            'plan': {'targets': ['benchmarks/score']}, 'estimates': {}, 'environments': {},
            'environment': {'reference': 'environments/test-python'}, 'runs': {'limit': 2},
            'run': {'run': run_id}, 'progress': {'run': run_id[:8]}, 'products': {}, 'activity': {},
            'map': {}, 'note': {'path': 'missing.md'}, 'recipe_results': {'recipe': 'recipes/fit-a'},
            'draft_branch': {'recipe': 'recipes/fit-a', 'title': 'Fit c'},
            'records': {'run': run_id}, 'record': {'run': run_id, 'id': 'weights.json'}, 'inside': {'run': run_id},
            'array_slice': {'run': run_id, 'path': 'weights.npy'},
            'array_summary': {'run': run_id, 'path': 'weights.npy'},
            'weights': {'run': run_id},
            'weights_compare': {'run': run_id, 'path': 'weights.json', 'other_run': run_id,
                                'other_path': 'weights.json'},
            'array_tiles': {'run': run_id, 'path': 'weights.npy'},
            'fields': {'run': run_id}, 'field_compare': {'run': run_id, 'entry': 0, 'case': 0},
            'model_graph': {'run': run_id}, 'model_graph_overlay': {'run': run_id, 'kind': 'parameters'},
            'model_graph_compare': {'run': run_id, 'other_run': run_id},
            'training': {'run': run_id}, 'training_series': {'run': run_id, 'series': [{'name': 'loss'}]},
            'training_histograms': {'run': run_id, 'name': 'w', 'kind': 'weights'},
            'training_samples': {'run': run_id}, 'training_sample': {'run': run_id, 'index': 0},
            'model_compare': {'recipes': ['recipes/fit-a', 'recipes/fit-b']}, 'benchmark_axes': {'benchmark': 'score'},
            'intervals': {'benchmark': 'benchmarks/score'},
            'served': {}, 'serve_session': {'session': 'a' * 32},
            'serve_predict': {'model': 'fit-a', 'inputs': {}},
            'annotation_tasks': {}, 'annotated_records': {'task': 'none-here'},
            'annotation': {'task': 'none-here', 'record': 'r1'},
            'annotation_sets': {'task': 'none-here'}, 'annotation_agreement': {'task': 'none-here'},
            'annotation_compare': {'task': 'none-here', 'record': 'r1', 'sets': ['kept']},
            'endpoint': {}, 'find_endpoints': {}, 'suggestion_models': {'task': 'none-here'},
            'suggest_annotation': {'task': 'none-here', 'record': 'r1', 'model': 'm'},
            'embeddings': {'dataset': 'datasets/numbers'},
            'embedding_map': {'run': run_id, 'name': 'none-here'},
            'embedding_neighbours': {'run': run_id, 'name': 'none-here', 'record': 'r1'},
            'embedding_duplicates': {'run': run_id, 'name': 'none-here'},
            'embedding_outliers': {'run': run_id, 'name': 'none-here'},
            'embedding_leakage': {'run': run_id, 'name': 'none-here'},
            'sweeps': {},
            'sweep': {'sweep': 'none-here'},
        }
        reads = [operation for operation in operations.OPERATIONS if not operation.mutation]
        arguments['build_requests'] = {'state': 'queued', 'limit': 5}
        self.assertEqual({operation.name for operation in reads} - set(arguments), {'build_request'})
        for operation in reads:
            with self.subTest(operation.name):
                if operation.name == 'build_request':  # tested with a request in test_tuldok_project_build_requests
                    self.assertEqual(self.refused(operation.name, {'request': 'abcdef12'}).code, 'not-found')
                    continue
                if operation.name in ('array_slice', 'array_summary', 'array_tiles'):  # no arrays here; tested in
                    # test_tuldok_project_inside and test_tuldok_project_weights
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'not-found')
                    continue
                if operation.name in ('model_graph_overlay', 'model_graph_compare', 'training_histograms',
                                      'training_sample'):  # fit-a has no model-graph.json (model_graph
                    # answers path null) and logged nothing; test_tuldok_project_model_graph, _training
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'not-found')
                    continue
                if operation.name == 'field_compare':  # fit-a keeps no fields; test_tuldok_project_fields
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'not-found')
                    continue
                if operation.name == 'weights_compare':  # fit-a's weights are JSON; test_tuldok_project_weights
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'unsupported')
                    continue
                if operation.name == 'find_endpoints':  # the owner's, and it scans this machine: tested with the
                    # scanner patched in test_tuldok_project_pumas
                    self.assertEqual(self.refused(operation.name, {}, actor=agent('inspect')).code, 'forbidden')
                    continue
                if operation.name in ('suggestion_models', 'suggest_annotation'):  # no task here; asked in
                    # test_tuldok_project_pumas
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'not-found')
                    continue
                if operation.name in ('annotated_records', 'annotation', 'annotation_sets', 'annotation_agreement',
                                      'annotation_compare'):  # this fixture has no task; read in
                    # test_tuldok_project_annotation_rows and test_tuldok_project_annotation_agreement
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'not-found')
                    continue
                if operation.name.startswith('embedding_'):  # no embeddings here; test_tuldok_project_curation
                    self.assertEqual(self.refused(operation.name, arguments[operation.name]).code, 'not-found')
                    continue
                if operation.name in ('serve_session', 'serve_predict'):  # nothing served; test_tuldok_project_serving
                    self.assertIn(self.refused(operation.name, arguments[operation.name]).code,
                                  ('not-found', 'not-served'))
                    continue
                if operation.name == 'sweep':  # this fixture has no sweep; read in test_tuldok_project_sweeps
                    self.assertEqual(self.refused(operation.name, arguments['sweep']).code, 'not-found')
                    continue
                if operation.name == 'note':  # this fixture has no notes; read in test_tuldok_project_workspace
                    self.assertEqual(self.refused(operation.name, arguments['note']).code, 'not-found')
                    continue
                result = self.call(operation.name, arguments[operation.name], actor=agent('inspect'))
                self.assertTrue(set(operation.result) <= set(result), set(operation.result) - set(result))
        self.assertEqual(self.activity(), [])  # reads are not recorded

    def test_shapes(self):
        self.build_all()
        results = self.call('results', {'benchmark': 'score', 'limit': 3, 'offset': 1})
        self.assertEqual(len(results['rows']), 3)
        self.assertEqual(results['total'], 4)  # two subjects, two metrics, no groups
        self.assertEqual(self.call('runs', {'limit': 2})['runs'][0]['reference'], 'benchmarks/score')
        self.assertEqual(len(self.call('runs', {'limit': 2})['runs']), 2)
        chart = self.call('chart', {'chart': 'charts/score-ranking', 'svg': True})
        self.assertTrue(chart['svg'].startswith('<svg'))
        self.assertNotIn('svg', self.call('chart', {'chart': 'score-ranking'}))
        self.assertTrue(self.call('report')['html'].startswith('<!DOCTYPE html>'))
        summary = self.call('summary')
        self.assertEqual(summary['folder'], str(self.folder))
        self.assertEqual(self.call('plan', {'targets': ['benchmarks/score']})['counts']['build'], 0)
        progress = self.call('progress', {'run': self.runs('datasets/numbers')[0]['id']})
        self.assertTrue(progress['ended'])
        self.assertEqual(set(progress['stdout']), {'text', 'offset', 'size', 'skipped'})
        later = self.call('progress', {'run': progress['run']['id'], 'stdout_offset': progress['stdout']['offset']})
        self.assertEqual(later['stdout']['text'], '')
        self.assertIsInstance(self.call('runs')['runs'][0]['queued_at'], str)
        self.assertEqual(self.refused('definition', {'reference': 'recipes/none'}).code, 'not-found')
        self.assertEqual(self.refused('chart', {'chart': 'Not A Name'}).code, 'not-found')

    def test_run_never_returns_variable_values(self):
        made = self.plan('datasets/numbers')
        done = builds_base.builds.execute(self.folder, made, confirm=lambda given: True,
                                          extra_env={'SERVICE_SECRET': SECRET})
        self.assertTrue(done['ok'], done)
        run_id = done['steps'][0]['run_id']
        with self.opened() as project:
            env = project._execute('SELECT env FROM {schema}.runs WHERE id = %s', (run_id,)).fetchone()[0]
        self.assertEqual(env['SERVICE_SECRET'], SECRET)
        result = self.call('run', {'run': run_id})
        self.assertNotIn('env', result)
        self.assertEqual(result['env_names'], sorted(env))
        self.assertIn('SERVICE_SECRET', result['env_names'])
        for name in ('run', 'progress', 'runs', 'products'):
            given = {} if name in ('runs', 'products') else {'run': run_id}
            self.assertNotIn(SECRET, plain(self, self.call(name, given)), name)


class Changes(ServiceCase):

    def edited(self, reference, change):
        document = self.call('definition', {'reference': reference})['document']
        change(document)
        return json.dumps(document, indent=2) + '\n'

    def test_set_remove_and_save(self):
        text = self.edited('recipes/fit-b', lambda document: document.update(title='Fit b, edited'))
        shown = self.call('set_definition', {'reference': 'recipes/fit-b', 'text': text}, actor=agent('edit'))
        self.assertEqual((shown['title'], shown['unsaved'], shown['text']), ('Fit b, edited', True, text))
        self.assertEqual(self.call('remove_definition', {'reference': 'charts/score-ranking'}),
                         {'removed': 'charts/score-ranking'})
        status = self.call('status')
        self.assertEqual((status['unsaved'], status['removed']), (['recipes/fit-b'], ['charts/score-ranking']))
        saved = self.call('save')
        self.assertEqual((saved['written'], saved['deleted']), (['recipes/fit-b'], ['charts/score-ranking']))
        self.assertEqual((self.folder / 'recipes' / 'fit-b.json').read_text(encoding='utf-8'), text)
        self.assertFalse((self.folder / 'charts' / 'score-ranking.json').exists())

        refused = self.refused('set_definition', {'reference': 'recipes/fit-b', 'text': '{"format": 1}'})
        self.assertEqual(refused.code, 'invalid')
        self.assertTrue(refused.problems)
        self.assertEqual(self.refused('remove_definition', {'reference': 'datasets/numbers'}).code, 'in-use')

        rows = [(row['operation'], row['target'], row['outcome'], row['actor']['kind']) for row in self.activity()]
        self.assertEqual(rows, [('remove_definition', 'datasets/numbers', 'in-use', 'owner'),
                                ('set_definition', 'recipes/fit-b', 'invalid', 'owner'),
                                ('save', '', 'done', 'owner'),
                                ('remove_definition', 'charts/score-ranking', 'done', 'owner'),
                                ('set_definition', 'recipes/fit-b', 'done', 'agent')])
        items = self.activity()
        self.assertEqual(items[0]['detail'], str(self.refused_detail('datasets/numbers')))
        self.assertEqual(items[2]['detail'], '')
        self.assertEqual(set(items[0]['actor']), {'actor_id', 'kind', 'label'})
        page = self.call('activity', {'offset': 1, 'limit': 2})
        self.assertEqual((page['total'], [item['operation'] for item in page['items']]),
                         (5, ['set_definition', 'save']))

    def test_revert(self):
        before = self.call('definition', {'reference': 'recipes/fit-b'})
        text = self.edited('recipes/fit-b', lambda document: document.update(title='Fit b, edited'))
        self.call('set_definition', {'reference': 'recipes/fit-b', 'text': text})
        self.assertEqual(self.refused('revert_definition', {'reference': 'recipes/fit-b'}, actor=agent('inspect')).code,
                         'forbidden')
        self.assertEqual(self.call('revert_definition', {'reference': 'recipes/fit-b'}, actor=agent('edit')),
                         {'reference': 'recipes/fit-b', 'dropped': False})
        self.assertEqual(self.call('definition', {'reference': 'recipes/fit-b'}), before)
        self.assertEqual(self.refused('revert_definition', {'reference': 'recipes/fit-b'}).code, 'nothing-to-revert')
        self.assertEqual(self.refused('revert_definition', {'reference': 'recipes/none'}).code, 'not-found')
        draft = self.call('draft_branch', {'recipe': 'fit-a', 'title': 'Fit c'}, actor=agent('inspect'))
        self.assertEqual(draft['problems'], [])
        self.call('set_definition', {'reference': draft['reference'], 'text': draft['text']})
        self.assertEqual(self.call('revert_definition', {'reference': draft['reference']}),
                         {'reference': 'recipes/fit-c', 'dropped': True})
        rows = [(row['operation'], row['target'], row['outcome'], row['actor']['kind']) for row in self.activity()]
        self.assertEqual(rows, [('revert_definition', 'recipes/fit-c', 'done', 'owner'),
                                ('set_definition', 'recipes/fit-c', 'done', 'owner'),
                                ('revert_definition', 'recipes/none', 'not-found', 'owner'),
                                ('revert_definition', 'recipes/fit-b', 'nothing-to-revert', 'owner'),
                                ('revert_definition', 'recipes/fit-b', 'done', 'agent'),
                                ('set_definition', 'recipes/fit-b', 'done', 'owner')])

    def refused_detail(self, reference):
        return f'{reference} is used by benchmarks/score, recipes/fit-a, recipes/fit-b; change those first.'

    def test_environment_changes(self):
        reference = 'environments/test-python'
        self.assertTrue(self.call('check_environment', {'reference': reference}, actor=agent('edit', 'inspect'))['ok'])
        gone = self.call('disconnect_environment', {'reference': reference})
        self.assertEqual(gone['disconnected'], reference)
        self.assertEqual(self.call('environment', {'reference': reference})['state'], 'not-set-up')
        self.assertEqual(self.refused('check_environment', {'reference': reference}).code, 'not-set-up')
        outcomes = [(row['operation'], row['outcome']) for row in self.activity()]
        self.assertEqual(outcomes, [('check_environment', 'not-set-up'), ('disconnect_environment', 'done'),
                                    ('check_environment', 'done')])

    def test_check_answers_for_a_folder_with_errors(self):
        (self.folder / 'datasets' / 'broken.json').write_text('{"format": ', encoding='utf-8')
        found = self.call('check')
        self.assertFalse(found['ok'])
        self.assertGreaterEqual(found['errors'], 1)
        self.assertIn('datasets/broken.json', [problem['path'] for problem in found['problems']])
        self.assertEqual(set(found['problems'][0]), {'severity', 'path', 'pointer', 'message'})
        refused = self.refused('summary')
        self.assertEqual(refused.code, 'invalid')
        self.assertTrue(refused.problems)
        # A mutation refused because the folder does not open is still recorded.
        self.assertEqual(self.refused('save').code, 'invalid')
        (self.folder / 'datasets' / 'broken.json').unlink()
        [row] = self.activity()
        self.assertEqual((row['operation'], row['outcome']), ('save', 'invalid'))
        self.assertTrue(row['detail'])

    def test_resolve_conflict(self):
        text = self.edited('recipes/fit-b', lambda document: document.update(title='Kept here'))
        self.call('set_definition', {'reference': 'recipes/fit-b', 'text': text})
        path = self.folder / 'recipes' / 'fit-b.json'
        on_disk = json.loads(path.read_text(encoding='utf-8'))
        on_disk['title'] = 'Changed on disk'
        path.write_text(json.dumps(on_disk, indent=2) + '\n', encoding='utf-8')
        refused = self.refused('summary')
        self.assertEqual((refused.code, refused.references), ('conflict', ['recipes/fit-b']))
        summary = self.call('resolve_conflict', {'choice': 'discard'})
        self.assertTrue({'project_id', 'worker', 'kinds'} <= set(summary))
        self.assertEqual(self.call('definition', {'reference': 'recipes/fit-b'})['title'], 'Changed on disk')
        self.assertEqual(self.refused('resolve_conflict', {'choice': 'maybe'}).code, 'invalid')
        outcomes = [(row['operation'], row['outcome']) for row in self.activity()]
        self.assertEqual(outcomes, [('resolve_conflict', 'invalid'), ('resolve_conflict', 'done'),
                                    ('set_definition', 'done')])

    def test_cancel_and_stop_a_finished_run(self):
        self.build('datasets/numbers')
        run_id = self.runs('datasets/numbers')[0]['id']
        self.assertEqual(self.refused('cancel_run', {'run': run_id}).code, 'not-active')
        stopped = self.call('stop_run', {'run': run_id}, actor=agent('cancel'))
        self.assertEqual((stopped['id'], stopped['was'], stopped['state']), (run_id, 'succeeded', 'succeeded'))
        rows = [(row['operation'], row['target'], row['outcome']) for row in self.activity()]
        self.assertEqual(rows, [('stop_run', run_id, 'done'), ('cancel_run', run_id, 'not-active')])

    def test_refused_request_operations_are_recorded(self):
        self.refused('cancel_build', {'request': 'abcdef12'})
        self.refused('decline_build', {'request': 'abcdef12', 'reason': 'No.'})
        rows = [(row['operation'], row['target'], row['outcome']) for row in self.activity()]
        self.assertEqual(rows, [('decline_build', 'abcdef12', 'not-found'),
                                ('cancel_build', 'abcdef12', 'not-found')])


class Results(store_base.StoreCase):
    """results, values and import_values on the minimal fixture, which has a results file and values files."""

    def setUp(self):
        super().setUp()
        self.service = Service(self.folder)
        self.addCleanup(self.service.close)

    def call(self, name, arguments=None, actor=OWNER):
        result = self.service.call(name, arguments or {}, actor)
        plain(self, result)
        return result

    def test_results_values_and_import(self):
        before = self.call('results', {'benchmark': 'rollout'})
        self.assertEqual(before['total'], len(before['rows']))
        self.assertTrue(all(row['origin'] == 'file' for row in before['rows']))
        self.assertEqual(self.call('values', {'benchmark': 'rollout', 'subject': 'stepper-k1'}),
                         {'rows': [], 'total': 0})
        text = (self.base / 'values' / 'rollout-stepper-k1.json').read_text(encoding='utf-8')
        imported = self.call('import_values', {'text': text}, actor=agent('edit'))
        self.assertEqual((imported['benchmark'], imported['subject']), ('rollout', 'stepper-k1'))
        values = self.call('values', {'benchmark': 'benchmarks/rollout', 'subject': 'stepper-k1', 'limit': 2})
        self.assertEqual((len(values['rows']), values['total']), (2, imported['values']))
        grouped = self.call('results', {'benchmark': 'rollout', 'subject': 'stepper-k1', 'group': ''})
        self.assertTrue(grouped['rows'] and all(row['group'] == '' for row in grouped['rows']))
        overview = self.call('results_overview')['benchmarks']
        self.assertEqual(overview[0]['subjects_with_values'], 1)
        with self.assertRaises(ProjectError) as caught:
            self.service.call('import_values', {'text': '{}'}, OWNER)
        self.assertEqual(caught.exception.code, 'invalid')
        items = self.call('activity')['items']
        self.assertEqual([(row['operation'], row['outcome']) for row in items],
                         [('import_values', 'invalid'), ('import_values', 'done')])


class ActivityTable(store_base.StoreCase):

    def test_an_older_schema_gets_the_table(self):
        self.close(self.open())
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            connection.execute(f'DROP TABLE {self.schema}.activity')
        self.close(self.open())
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            found = connection.execute("SELECT 1 FROM pg_tables WHERE schemaname = %s AND tablename = 'activity'",
                                       (self.schema,)).fetchone()
        self.assertIsNotNone(found)


if __name__ == '__main__':
    unittest.main()
