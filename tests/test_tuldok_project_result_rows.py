"""Benchmark results in the database (spec-m3.md sections 1 to 4, slice T7).

The values-file check and the summaries computed from values are tested
without a database. Everything else runs only when TULDOK_DATABASE_URL names
a disposable cluster: each test copies tests/fixtures/tuldok_project/minimal
with a fresh project id (test_tuldok_project_store.StoreCase) and drops that
project's schema afterwards. The command-line tests run the commands as a
child process, as test_tuldok_project_cli.py does.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import check, result_rows, results  # noqa: E402
from tuldok_project.results import SummaryRow  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
from test_tuldok_project_store import FIXTURE, StoreCase  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
VALUES = FIXTURE / 'values'
BENCHMARK = json.loads((FIXTURE / 'project' / 'benchmarks' / 'rollout.json').read_text(encoding='utf-8'))
COMMIT = '0123456789abcdef0123456789abcdef01234567'


def values_file(subject='stepper-k1', values=None, **fields):
    """The text of a small values file for the fixture's benchmark (the hand-computed case unless values is given)."""
    if values is None:
        values = [
            {'case': 'a', 'metric': 'rmse', 'value': 1.0, 'group': {'horizon': 1}},
            {'case': 'b', 'metric': 'rmse', 'value': 2.0, 'group': {'horizon': 1}},
            {'case': 'c', 'metric': 'rmse', 'value': None, 'reason': 'diverged', 'group': {'horizon': 1}},
            {'case': 'a', 'metric': 'rmse', 'value': 4.0, 'group': {'horizon': 8}},
            {'case': 'a', 'metric': 'seconds', 'value': 3.0},
        ]
    document = {'format': 'tuldok_results_v1', 'benchmark': 'rollout', 'subject': subject, 'commit': COMMIT,
                'produced': '2026-11-10', 'values': values}
    document.update(fields)
    return json.dumps({key: value for key, value in document.items() if value is not ...})


# The summaries of values_file(), by hand: (metric, group) -> (count, unavailable, mean, median, p10, p90, min, max).
HAND = {
    ('rmse', ''): (3, 1, 7 / 3, 2.0, 1.2, 3.6, 1.0, 4.0),            # 1, 2, 4 and one null
    ('rmse', 'horizon=1'): (2, 1, 1.5, 1.5, 1.1, 1.9, 1.0, 2.0),     # 1, 2 and one null
    ('rmse', 'horizon=8'): (1, 0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0),
    ('seconds', ''): (1, 0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0),
}


def find(name):
    return BENCHMARK if name == 'rollout' else None


def summary_numbers(row):
    return (row.count, row.unavailable, row.mean, row.median, row.p10, row.p90, row.min, row.max)


class ValuesCheck(unittest.TestCase):
    """Section 1: one failing case per rule."""

    def problems(self, text):
        found, problems = result_rows.check_values(text, find, path='v.json')
        self.assertIsNone(found)
        self.assertTrue(problems)
        self.assertTrue(all(problem.severity == 'error' and problem.path == 'v.json' for problem in problems))
        return [(problem.pointer, problem.message) for problem in problems]

    def assertPointer(self, text, pointer):
        found = self.problems(text)
        self.assertIn(pointer, [p for p, _ in found], found)

    def one(self, **change):
        """values_file() with one value changed (None in change removes that field)."""
        value = {'case': 'a', 'metric': 'rmse', 'value': 1.0, 'group': {'horizon': 1}}
        value.update(change)
        return values_file(values=[{k: v for k, v in value.items() if v is not ...}])

    def test_a_good_file_passes(self):
        found, problems = result_rows.check_values(values_file(), find)
        self.assertEqual(problems, [])
        self.assertEqual((found.benchmark, found.subject, found.commit, found.produced),
                         ('rollout', 'stepper-k1', COMMIT, '2026-11-10'))
        self.assertEqual(found.values[0].group, 'horizon=1')
        self.assertEqual(found.values[2].reason, 'diverged')
        for path in sorted(VALUES.glob('*.json')):
            self.assertEqual(result_rows.check_values(path.read_bytes(), find)[1], [], path.name)

    def test_strict_json(self):
        self.assertPointer('{"format": "tuldok_results_v1", "format": "tuldok_results_v1"}', '')
        self.assertPointer(values_file().replace('1.0', 'NaN', 1), '')
        self.assertPointer('[1, 2]', '')

    def test_size_limit(self):
        self.assertPointer(b' ' * (result_rows.VALUES_LIMIT + 1), '')

    def test_format(self):
        self.assertPointer(values_file(format='tuldok_results_v2'), '/format')

    def test_required_fields(self):
        found = self.problems(values_file(commit=...))
        self.assertIn(('', "The field 'commit' is required."), found)

    def test_unknown_fields(self):
        self.assertPointer(values_file(extra=1), '/extra')
        self.assertPointer(self.one(units='m'), '/values/0/units')

    def test_benchmark_and_subject(self):
        self.assertPointer(values_file(benchmark='nothing'), '/benchmark')
        self.assertPointer(values_file(subject='nobody'), '/subject')

    def test_commit_and_produced(self):
        self.assertPointer(values_file(commit='abc'), '/commit')
        self.assertPointer(values_file(produced='2026-13-01'), '/produced')
        self.assertPointer(values_file(produced='yesterday'), '/produced')

    def test_values_is_a_non_empty_list(self):
        self.assertPointer(values_file(values={}), '/values')
        self.assertPointer(values_file(values=[]), '/values')
        self.assertPointer(values_file(values=[3]), '/values/0')

    def test_case(self):
        self.assertPointer(self.one(case=''), '/values/0/case')
        self.assertPointer(self.one(case='x' * 201), '/values/0/case')
        self.assertPointer(self.one(case=...), '/values/0/case')

    def test_metric(self):
        self.assertPointer(self.one(metric='speed'), '/values/0/metric')

    def test_value(self):
        self.assertPointer(self.one(value='1.0'), '/values/0/value')
        self.assertPointer(self.one(value=True), '/values/0/value')
        self.assertPointer(self.one(value=10 ** 400), '/values/0/value')
        self.assertPointer(self.one(value=...), '/values/0')

    def test_reason(self):
        self.assertPointer(self.one(value=None), '/values/0/reason')
        self.assertPointer(self.one(value=None, reason=''), '/values/0/reason')
        self.assertPointer(self.one(value=None, reason='x' * 401), '/values/0/reason')
        self.assertPointer(self.one(reason='measured anyway'), '/values/0/reason')

    def test_group(self):
        self.assertPointer(self.one(group=[1]), '/values/0/group')
        self.assertPointer(self.one(group={'size': 1}), '/values/0/group/size')
        self.assertPointer(self.one(group={'horizon': [1]}), '/values/0/group/horizon')
        self.assertPointer(self.one(group={'horizon': None}), '/values/0/group/horizon')
        self.assertPointer(self.one(group={'horizon': 'a;b'}), '/values/0/group/horizon')
        self.assertPointer(self.one(group={'horizon': 'a=b'}), '/values/0/group/horizon')

    def test_group_values_are_stored_as_text(self):
        for written, text in ((1, '1'), (1.5, '1.5'), (2.0, '2.0'), (True, 'true'), (False, 'false'), ('x', 'x')):
            found, problems = result_rows.check_values(self.one(group={'horizon': written}), find)
            self.assertEqual(problems, [])
            self.assertEqual(found.values[0].group, f'horizon={text}')

    def test_case_metric_and_group_are_unique(self):
        first = {'case': 'a', 'metric': 'rmse', 'value': 1.0, 'group': {'horizon': 1}}
        self.assertPointer(values_file(values=[first, dict(first, value=2.0)]), '/values/1')
        # The same case and metric in another group is a different value.
        found, problems = result_rows.check_values(values_file(values=[first, dict(first, group={'horizon': 8})]), find)
        self.assertEqual(problems, [])


class SummariesFromValues(unittest.TestCase):
    """Section 3, which summaries exist, against hand-computed numbers."""

    def test_hand_computed(self):
        found, _ = result_rows.check_values(values_file(), find)
        rows = result_rows.summaries_from_values(found)
        self.assertEqual({(row.metric, row.group): summary_numbers(row) for row in rows}, HAND)
        self.assertTrue(all(row.subject == 'stepper-k1' and row.commit == COMMIT and row.produced == '2026-11-10'
                            for row in rows))

    def test_no_rows_for_combinations(self):
        two_keys = dict(BENCHMARK, summary={'group_by': ['horizon', 'size']})
        text = values_file(values=[{'case': 'a', 'metric': 'rmse', 'value': 1.0, 'group': {'horizon': 1, 'size': 's'}},
                                   {'case': 'b', 'metric': 'rmse', 'value': 3.0, 'group': {'size': 's'}}])
        found, problems = result_rows.check_values(text, lambda name: two_keys)
        self.assertEqual(problems, [])
        self.assertEqual(found.values[0].group, 'horizon=1;size=s')
        rows = {row.group: row.count for row in result_rows.summaries_from_values(found)}
        self.assertEqual(rows, {'': 2, 'horizon=1': 1, 'size=s': 2})

    def test_fixture_results_file_is_made_from_the_fixture_values(self):
        rows = []
        for path in sorted(VALUES.glob('*.json')):
            rows += result_rows.summaries_from_values(result_rows.check_values(path.read_bytes(), find)[0])
        self.assertEqual(results.write_results(rows),
                         (FIXTURE / 'project' / 'results' / 'rollout.csv').read_text(encoding='utf-8'))


class ResultsCase(StoreCase):

    @property
    def csv(self):
        return self.folder / 'results' / 'rollout.csv'

    def stored(self, project, **filters):
        return {(item.row.subject, item.row.metric, item.row.group): item
                for item in project.result_summaries('rollout', **filters)}

    def rewrite_csv(self, change):
        """Rewrite the results file with change(rows) applied to its SummaryRow list."""
        rows = results.read_results(self.csv.read_text(encoding='utf-8'))
        self.csv.write_text(results.write_results(change(rows)), encoding='utf-8')

    def replace_row(self, subject, metric, group, **fields):
        def change(rows):
            return [SummaryRow(**{**vars(row), **fields}) if (row.subject, row.metric, row.group) == (subject, metric, group)
                    else row for row in rows]
        self.rewrite_csv(change)


class OpenResults(ResultsCase):

    def test_open_imports_every_summary_row(self):
        project = self.open()
        stored = self.stored(project)
        file_rows = results.read_results(self.csv.read_text(encoding='utf-8'))
        self.assertEqual([item.row for item in stored.values()], file_rows)
        self.assertEqual({item.origin for item in stored.values()}, {'file'})
        self.assertEqual(project.results_overview(), [{
            'benchmark': 'rollout', 'subjects_with_results': 3, 'subjects_with_values': 0, 'rows': 12,
            'rows_file': 12, 'rows_values': 0, 'differs_from_file': False}])
        self.assertEqual(project.result_values('rollout', 'stepper-k1'), {'total': 0, 'values': []})

    def test_group_filters(self):
        project = self.open()
        self.assertEqual(len(project.result_summaries('rollout')), 12)
        self.assertEqual({item.row.group for item in project.result_summaries('rollout', group='')}, {''})
        self.assertEqual({item.row.group for item in project.result_summaries('rollout', group='horizon')},
                         {'horizon=1', 'horizon=8'})
        self.assertEqual(project.result_summaries('rollout', group='hor'), [])
        self.assertEqual(len(project.result_summaries('rollout', subject='early-fit', metric='rmse')), 3)
        with self.assertRaises(ProjectError) as caught:
            project.result_summaries('nothing')
        self.assertEqual(caught.exception.code, 'not-found')

    def test_unchanged_results_attach_without_the_checker(self):
        self.close(self.open())
        before = self.dump()
        checker = self.counting_checker()
        self.open()
        checker.assert_not_called()
        self.assertEqual(self.dump(), before)

    def test_changed_results_file_is_imported(self):
        self.close(self.open())
        self.replace_row('stepper-k2', 'seconds', '', median=1.4)
        checker = self.counting_checker()
        project = self.open()
        checker.assert_called_once()
        self.assertEqual(self.stored(project)['stepper-k2', 'seconds', ''].row.median, 1.4)

    def test_removed_and_added_results_file(self):
        self.close(self.open())
        text = self.csv.read_text(encoding='utf-8')
        self.csv.unlink()
        checker = self.counting_checker()
        project = self.open()
        self.assertEqual(checker.call_count, 1)
        self.assertEqual(project.result_summaries('rollout'), [])
        self.assertFalse(project.results_overview()[0]['differs_from_file'])
        self.close(project)
        self.close(self.open())  # unchanged again: no check
        self.assertEqual(checker.call_count, 1)
        self.csv.write_text(text, encoding='utf-8')
        project = self.open()
        self.assertEqual(checker.call_count, 2)
        self.assertEqual(len(project.result_summaries('rollout')), 12)

    def test_bad_results_file_refuses_the_open_and_changes_nothing(self):
        self.close(self.open())
        before = self.dump()
        self.csv.write_text(self.csv.read_text(encoding='utf-8').replace('stepper-k1,', 'nobody,', 1), encoding='utf-8')
        with self.assertRaises(ProjectError) as caught:
            self.open()
        self.assertIn('results/rollout.csv', [problem.path for problem in caught.exception.problems])
        self.assertEqual(self.dump(), before)

    def test_floats_round_trip_exactly(self):
        awkward = (0.1 + 0.2, 1e-300, 123456789.12345679, -2.5e-07)
        self.replace_row('stepper-k1', 'seconds', '', mean=awkward[0], median=awkward[1], p10=awkward[2],
                         p90=awkward[3])
        project = self.open()
        row = self.stored(project)['stepper-k1', 'seconds', ''].row
        self.assertEqual((row.mean, row.median, row.p10, row.p90), awkward)
        self.assertEqual(project.status()['results_unsaved'], [])  # the database makes the same text again


class ImportValues(ResultsCase):

    def setUp(self):
        super().setUp()
        self.project = self.open()

    def test_import_replaces_the_subjects_values_and_summaries(self):
        imported = self.project.import_values(values_file())
        self.assertEqual(imported, {'benchmark': 'rollout', 'subject': 'stepper-k1', 'values': 5, 'summaries': 4})
        stored = self.stored(self.project, subject='stepper-k1')
        self.assertEqual({(metric, group): summary_numbers(item.row) for (_, metric, group), item in stored.items()},
                         HAND)
        self.assertEqual({item.origin for item in stored.values()}, {'values'})
        self.assertEqual({item.row.produced for item in stored.values()}, {'2026-11-10'})
        # The other subjects keep the file's rows.
        self.assertEqual({item.origin for item in self.project.result_summaries('rollout', subject='stepper-k2')},
                         {'file'})
        held = self.project.result_values('rollout', 'stepper-k1')
        self.assertEqual(held['total'], 5)
        self.assertIn({'case': 'c', 'metric': 'rmse', 'group': 'horizon=1', 'value': None, 'reason': 'diverged'},
                      held['values'])
        page = self.project.result_values('rollout', 'stepper-k1', metric='rmse', offset=1, limit=2)
        self.assertEqual((page['total'], [row['case'] for row in page['values']]), (4, ['a', 'b']))
        overview = self.project.results_overview()[0]
        self.assertEqual((overview['subjects_with_values'], overview['rows_file'], overview['rows_values'],
                          overview['differs_from_file']), (1, 8, 4, True))
        # A second import of the same subject replaces, it does not add.
        self.project.import_values(values_file(values=[{'case': 'z', 'metric': 'seconds', 'value': 9.0}]))
        self.assertEqual(self.project.result_values('rollout', 'stepper-k1')['total'], 1)
        self.assertEqual(list(self.stored(self.project, subject='stepper-k1')), [('stepper-k1', 'seconds', '')])

    def test_a_file_with_a_problem_changes_nothing(self):
        before = self.dump()
        bad = values_file(values=[{'case': 'a', 'metric': 'rmse', 'value': 1.0},
                                  {'case': 'b', 'metric': 'speed', 'value': 1.0}])
        with self.assertRaises(ProjectError) as caught:
            self.project.import_values(bad, path='bad.json')
        self.assertEqual(caught.exception.code, 'invalid')
        self.assertEqual([(p.path, p.pointer) for p in caught.exception.problems], [('bad.json', '/values/1/metric')])
        self.assertEqual(self.dump(), before)

    def test_values_keep_their_summaries_when_the_results_file_is_reimported(self):
        self.project.import_values(values_file())
        self.close(self.project)
        self.replace_row('stepper-k1', 'seconds', '', median=99.0)
        self.replace_row('stepper-k2', 'seconds', '', median=98.0)
        project = self.open()
        stored = self.stored(project)
        self.assertEqual(stored['stepper-k1', 'seconds', ''].origin, 'values')
        self.assertEqual(stored['stepper-k1', 'seconds', ''].row.median, 3.0)
        self.assertNotIn(('stepper-k1', 'rmse', 'horizon=8'), [k for k, v in stored.items() if v.origin == 'file'])
        self.assertEqual(stored['stepper-k2', 'seconds', ''].row.median, 98.0)
        self.assertEqual(stored['stepper-k2', 'seconds', ''].origin, 'file')

    def test_many_values_import_quickly(self):
        cases = [{'case': f'scene-{index:05d}', 'metric': metric, 'value': index * 0.001,
                  'group': {'horizon': index % 2 * 7 + 1}} for index in range(10000) for metric in ('rmse', 'seconds')]
        started = time.monotonic()
        imported = self.project.import_values(values_file(values=cases))
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(imported['values'], 20000)
        self.assertEqual(self.project.result_values('rollout', 'stepper-k1', limit=5)['total'], 20000)
        self.assertEqual(self.stored(self.project)['stepper-k1', 'rmse', 'horizon=8'].row.count, 5000)


class SaveAndStatus(ResultsCase):

    def setUp(self):
        super().setUp()
        self.project = self.open()

    def test_save_writes_the_results_file_and_status_is_clean_after(self):
        self.project.import_values(values_file())
        status = self.project.status()
        self.assertEqual((status['results_unsaved'], status['results_changed']), (['rollout'], []))
        saved = self.project.save()
        self.assertEqual((saved['results_written'], saved['results_deleted']), (['rollout'], []))
        rows = results.read_results(self.csv.read_text(encoding='utf-8'))
        self.assertEqual(rows, [item.row for item in self.project.result_summaries('rollout')])
        self.assertEqual(self.project.status()['results_unsaved'], [])
        self.assertTrue(check.check_folder(self.folder).ok)
        self.assertEqual(self.project.save()['results_written'], [])  # same text: nothing written
        self.close(self.project)
        checker = self.counting_checker()
        self.open()
        checker.assert_not_called()

    def test_values_matching_the_file_write_nothing(self):
        for path in sorted(VALUES.glob('*.json')):
            self.project.import_values(path.read_bytes())
        self.assertEqual(self.project.status()['results_unsaved'], [])
        modified = self.csv.stat().st_mtime_ns
        self.assertEqual(self.project.save()['results_written'], [])
        self.assertEqual(self.csv.stat().st_mtime_ns, modified)

    def test_save_refuses_when_the_results_file_changed_on_disk(self):
        self.project.import_values(values_file())
        waves = self.edited('datasets/waves', lambda d: d.update(title='Waves, edited'))
        self.project.set_definition('datasets/waves', waves)
        self.replace_row('stepper-k2', 'seconds', '', median=1.4)
        on_disk = self.csv.read_text(encoding='utf-8')
        self.assertEqual(self.project.status()['results_changed'], ['results/rollout.csv'])
        with self.assertRaises(ProjectError) as caught:
            self.project.save()
        self.assertEqual(caught.exception.code, 'changed-on-disk')
        self.assertEqual(caught.exception.references, ['results/rollout.csv'])
        self.assertEqual(self.csv.read_text(encoding='utf-8'), on_disk)
        self.assertNotEqual(self.read('datasets/waves'), waves)  # nothing at all was written

    def test_removing_the_benchmark_removes_its_results_and_save_deletes_the_file(self):
        self.project.import_values(values_file())
        self.project.remove_definition('charts/speed-accuracy')
        self.project.remove_definition('charts/rollout-ranking')
        self.project.remove_definition('benchmarks/rollout')
        connection = self.database()
        for table in ('result_summaries', 'result_values'):
            count = connection.execute(f'SELECT count(*) FROM {self.schema}.{table}').fetchone()[0]
            self.assertEqual(count, 0, table)
        self.assertEqual(self.project.status()['results_unsaved'], ['rollout'])
        saved = self.project.save()
        self.assertEqual(saved['results_deleted'], ['rollout'])
        self.assertFalse(self.csv.exists())
        self.assertEqual(connection.execute(f'SELECT count(*) FROM {self.schema}.results_files').fetchone()[0], 0)
        self.assertTrue(check.check_folder(self.folder).ok)
        self.assertEqual(self.project.status()['results_unsaved'], [])

    def test_removing_a_subject_removes_its_rows(self):
        self.project.import_values(values_file(subject='stepper-k2'))
        self.project.set_definition('charts/rollout-ranking', self.edited('charts/rollout-ranking', lambda d: d.update(
            subjects=['stepper-k1', 'early-fit'])))
        benchmark = self.edited('benchmarks/rollout', lambda d: d.update(
            subjects=[s for s in d['subjects'] if s['name'] != 'stepper-k2']))
        self.project.set_definition('benchmarks/rollout', benchmark)
        self.assertEqual(self.project.result_summaries('rollout', subject='stepper-k2'), [])
        self.assertEqual(self.database().execute(
            f'SELECT count(*) FROM {self.schema}.result_values').fetchone()[0], 0)
        self.assertEqual(len(self.project.result_summaries('rollout')), 8)
        self.project.save()
        self.assertTrue(check.check_folder(self.folder).ok)
        self.assertNotIn('stepper-k2', self.csv.read_text(encoding='utf-8'))


def run(*arguments):
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                          env=environment, capture_output=True, text=True, timeout=120)


class Commands(ResultsCase):

    def setUp(self):
        super().setUp()
        self.values_files = sorted(self.base.glob('values/*.json'))

    def run_ok(self, *arguments):
        done = run(*arguments)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stderr, '')
        return done.stdout

    def test_results(self):
        lines = self.run_ok('results', self.folder).splitlines()
        self.assertEqual(lines[0].split(), ['benchmark', 'subjects', 'with', 'values', 'rows', 'from', 'file',
                                            'from', 'values', 'saved'])
        self.assertEqual(lines[1].split(), ['rollout', '3', '0', '12', '12', '0', 'yes'])
        self.assertEqual(json.loads(self.run_ok('results', self.folder, '--json'))[0]['rows'], 12)
        lines = self.run_ok('results', self.folder, 'rollout', '--subject', 'stepper-k1', '--group', '').splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1].split()[:4], ['stepper-k1', 'rmse', '-', '8'])
        rows = json.loads(self.run_ok('results', self.folder, 'rollout', '--metric', 'rmse', '--group', 'horizon',
                                      '--json'))
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], {'subject': 'early-fit', 'metric': 'rmse', 'group': 'horizon=1', 'count': 4,
                                   'unavailable': 0, 'mean': 0.625, 'median': 0.625, 'p10': 0.325, 'p90': 0.925,
                                   'min': 0.25, 'max': 1.0, 'commit': COMMIT, 'produced': '2026-11-02',
                                   'origin': 'file'})
        missing = run('results', self.folder, 'nothing')
        self.assertEqual((missing.returncode, missing.stderr), (1, 'There is no benchmark benchmarks/nothing.\n'))

    def test_values_before_and_after_import(self):
        self.assertIn('holds no per-case values for stepper-k1',
                      self.run_ok('values', self.folder, 'rollout', '--subject', 'stepper-k1'))
        self.assertEqual(json.loads(self.run_ok('values', self.folder, 'rollout', '--subject', 'stepper-k1', '--json')),
                         {'total': 0, 'values': []})
        output = self.run_ok('import-values', self.folder, *self.values_files)
        self.assertEqual(len(output.splitlines()), 3)
        self.assertIn('imported  benchmarks/rollout  early-fit', output)
        lines = self.run_ok('values', self.folder, 'rollout', '--subject', 'early-fit', '--limit', '2').splitlines()
        self.assertEqual(lines, ['case      metric  group      value', 'scene-01  rmse    horizon=1  0.25',
                                 'scene-01  rmse    horizon=8  none (diverged before step 8)',
                                 '2 of 12 values shown; use --limit to see more.'])
        held = json.loads(self.run_ok('values', self.folder, 'rollout', '--subject', 'early-fit', '--metric',
                                      'seconds', '--json'))
        self.assertEqual(held['total'], 4)
        self.assertEqual(held['values'][1], {'case': 'scene-02', 'metric': 'seconds', 'group': '', 'value': None,
                                             'reason': 'timer not recorded'})
        overview = json.loads(self.run_ok('results', self.folder, '--json'))[0]
        self.assertEqual((overview['rows_values'], overview['differs_from_file']), (12, False))
        self.assertEqual(self.run_ok('status', self.folder),
                         'Nothing is unsaved and no file changed on disk since the last import.\n')

    def test_import_values_json_and_refusal(self):
        imported = json.loads(self.run_ok('import-values', self.folder, self.values_files[0], '--json'))
        self.assertEqual(imported, [{'benchmark': 'rollout', 'subject': 'early-fit', 'values': 12, 'summaries': 4}])
        bad = self.temporary / 'bad.json'
        bad.write_text(values_file(subject='stepper-k2', commit='abc'), encoding='utf-8')
        before = json.loads(self.run_ok('results', self.folder, '--json'))
        done = run('import-values', self.folder, self.values_files[1], bad)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout, '')
        self.assertIn(f'error  {bad}  /commit  ', done.stderr)
        self.assertIn('Nothing was imported', done.stderr)
        self.assertEqual(json.loads(self.run_ok('results', self.folder, '--json')), before)
        twice = run('import-values', self.folder, self.values_files[1], self.values_files[1])
        self.assertEqual(twice.returncode, 2)
        self.assertIn('same benchmark and subject', twice.stderr)

    def test_save_and_status_report_results(self):
        changed = self.temporary / 'k1.json'
        changed.write_text(values_file(), encoding='utf-8')
        self.run_ok('import-values', self.folder, changed)
        self.assertEqual(self.run_ok('status', self.folder), 'results unsaved  rollout\n')
        self.assertEqual(self.run_ok('save', self.folder), 'wrote  results/rollout.csv\n')
        self.assertEqual(json.loads(self.run_ok('status', self.folder, '--json'))['results_unsaved'], [])


if __name__ == '__main__':
    unittest.main()
