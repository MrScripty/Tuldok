import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project.results import (  # noqa: E402
    COLUMNS, STATISTICS, SummaryRow, check_results, read_results, summarise, write_results,
)

HEADER = ','.join(COLUMNS)
COMMIT = '0123456789abcdef0123456789abcdef01234567'
BENCHMARK = {
    'kind': 'benchmark',
    'metrics': [{'id': 'rmse', 'title': 'RMSE', 'better': 'lower'},
                {'id': 'step_time', 'title': 'Step time', 'better': 'lower'}],
    'subjects': [{'name': 'baseline'}, {'name': 'stepper-v2'}],
    'summary': {'group_by': ['resolution', 'case_family']},
}
GOOD_ROW = f'baseline,rmse,,3,0,2.0,2.0,1.2,2.8,1.0,3.0,{COMMIT},2026-11-02'


def row(**changes):
    """Return one valid SummaryRow with the given fields changed."""
    fields = dict(subject='baseline', metric='rmse', group='', count=3, unavailable=0,
                  mean=2.0, median=2.0, p10=1.2, p90=2.8, min=1.0, max=3.0,
                  commit=COMMIT, produced='2026-11-02')
    fields.update(changes)
    return SummaryRow(**fields)


def results_text(*lines):
    return '\n'.join((HEADER,) + lines) + '\n'


def replace_cell(line, column, value):
    cells = line.split(',')
    cells[COLUMNS.index(column)] = value
    return ','.join(cells)


class SummariseTests(unittest.TestCase):
    def assertSummary(self, values, expected, unavailable=0):
        summary = summarise(values, unavailable)
        self.assertEqual(set(summary), {'count', 'unavailable', *STATISTICS})
        for name, value in expected.items():
            self.assertEqual(summary[name], value, name)

    def test_one_value(self):
        self.assertSummary([5], dict(count=1, unavailable=0, mean=5.0, median=5.0,
                                     p10=5.0, p90=5.0, min=5.0, max=5.0))

    def test_two_values(self):
        # Positions: median 0.5, p10 0.1, p90 0.9 between 1 and 3.
        self.assertSummary([3, 1], dict(count=2, mean=2.0, median=2.0, p10=1.2, p90=2.8,
                                        min=1.0, max=3.0))

    def test_odd_count(self):
        # Ascending 1..5, count - 1 = 4: median at 2, p10 at 0.4, p90 at 3.6.
        self.assertSummary([3, 1, 2, 5, 4], dict(count=5, mean=3.0, median=3.0, p10=1.4,
                                                 p90=4.6, min=1.0, max=5.0))

    def test_even_count(self):
        # Ascending 1..4, count - 1 = 3: median at 1.5, p10 at 0.3, p90 at 2.7.
        self.assertSummary([4, 2, 3, 1], dict(count=4, mean=2.5, median=2.5, p10=1.3,
                                              p90=3.7, min=1.0, max=4.0))

    def test_positions_on_whole_ranks(self):
        # Eleven values 0..10: p10 at exactly 1, p90 at exactly 9.
        self.assertSummary(list(range(11)), dict(count=11, mean=5.0, median=5.0,
                                                 p10=1.0, p90=9.0))

    def test_ties(self):
        # Ascending 2, 2, 2, 7: median at 1.5 is 2; p90 at 2.7 is 2 + 0.7 * 5.
        self.assertSummary([2, 7, 2, 2], dict(count=4, mean=3.25, median=2.0, p10=2.0,
                                              p90=5.5, min=2.0, max=7.0))

    def test_negative_values(self):
        # Ascending -10, -4, -1: p10 at 0.2 is -10 + 0.2 * 6; p90 at 1.8 is -4 + 0.8 * 3.
        summary = summarise([-4, -1, -10])
        self.assertEqual((summary['mean'], summary['median'], summary['min'], summary['max']),
                         (-5.0, -4.0, -10.0, -1.0))
        self.assertAlmostEqual(summary['p10'], -8.8, places=12)
        self.assertAlmostEqual(summary['p90'], -1.6, places=12)

    def test_zero_values(self):
        self.assertSummary([0, 0, 0], dict(count=3, mean=0.0, median=0.0, p10=0.0, p90=0.0,
                                           min=0.0, max=0.0))

    def test_zero_count(self):
        self.assertSummary([], dict(count=0, unavailable=3, **{name: None for name in STATISTICS}),
                           unavailable=3)

    def test_rejects_non_finite_values_and_bad_unavailable(self):
        with self.assertRaises(ValueError):
            summarise([1.0, float('nan')])
        with self.assertRaises(ValueError):
            summarise([1.0], unavailable=-1)


class RoundTripTests(unittest.TestCase):
    def test_rows_round_trip_exactly_and_are_sorted(self):
        rows = [
            row(subject='stepper-v2', metric='step_time', mean=0.1 + 0.2, median=1e-05,
                p10=-0.0, p90=1.5e+16, min=-3.25, max=123456789.123456789),
            row(group='case_family=plume;resolution=64', commit='', produced='2026-11-02T10:30:00Z'),
            row(count=0, unavailable=4, **{name: None for name in STATISTICS}),
            row(metric='step_time', group='case_family=a "quoted", value'),
        ]
        text = write_results(rows)
        self.assertTrue(text.startswith(HEADER + '\n'))
        self.assertNotIn('\r', text)
        self.assertIn('"case_family=a ""quoted"", value"', text)
        back = read_results(text)
        self.assertEqual(back, sorted(rows, key=lambda r: (r.subject, r.metric, r.group)))
        self.assertEqual(write_results(back), text)
        self.assertEqual(repr(back[-1].mean), repr(0.1 + 0.2))

    def test_empty_cells_for_missing_statistics(self):
        text = write_results([row(count=0, **{name: None for name in STATISTICS})])
        self.assertEqual(text.splitlines()[1], f'baseline,rmse,,0,0,,,,,,,{COMMIT},2026-11-02')

    def test_written_file_passes_the_check(self):
        rows = [row(), row(subject='stepper-v2', group='resolution=32')]
        self.assertEqual(check_results(write_results(rows), BENCHMARK), [])

    def test_read_rejects_malformed_files(self):
        for text in ('', 'subject,metric\n', results_text('baseline,rmse'),
                     results_text(replace_cell(GOOD_ROW, 'count', 'three')),
                     results_text(replace_cell(GOOD_ROW, 'mean', 'nan')),
                     results_text('"baseline,rmse')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_results(text)


class CheckResultsTests(unittest.TestCase):
    def assertProblem(self, text, severity, pointer, fragment):
        problems = check_results(text, BENCHMARK)
        matching = [p for p in problems if p[0] == severity and p[1] == pointer and fragment in p[2]]
        self.assertTrue(matching, f'no {severity} at {pointer!r} mentioning {fragment!r}: {problems}')

    def assertBadCell(self, column, value, fragment):
        self.assertProblem(results_text(GOOD_ROW, replace_cell(GOOD_ROW.replace('baseline', 'stepper-v2'),
                                                               column, value)),
                           'error', 'line 3', fragment)

    def test_valid_file_has_no_problems(self):
        self.assertEqual(check_results(results_text(GOOD_ROW), BENCHMARK), [])

    def test_header_only_file_is_valid(self):
        self.assertEqual(check_results(HEADER + '\n', BENCHMARK), [])

    # UTF-8, line ends, quoting, header.
    def test_not_utf8(self):
        problems = check_results(b'\xff' + results_text(GOOD_ROW).encode(), BENCHMARK)
        self.assertEqual(problems, [('error', '', 'The results file is not UTF-8.')])

    def test_utf8_bytes_are_accepted(self):
        self.assertEqual(check_results(results_text(GOOD_ROW).encode('utf-8'), BENCHMARK), [])

    def test_carriage_return_line_ends(self):
        self.assertProblem(results_text(GOOD_ROW).replace('\n', '\r\n'), 'error', '', '\\r')

    def test_missing_final_line_end(self):
        self.assertProblem(results_text(GOOD_ROW).rstrip('\n'), 'warning', '', 'line end')

    def test_bad_quoting(self):
        self.assertProblem(results_text(GOOD_ROW, 'baseline,"rm"se,,0,0,,,,,,,,2026-11-02'),
                           'error', 'line 3', 'RFC 4180')

    def test_empty_file(self):
        self.assertProblem('', 'error', '', 'empty')

    def test_wrong_header(self):
        self.assertProblem(results_text(GOOD_ROW).replace('p10,p90', 'p90,p10'),
                           'error', 'line 1', 'first line')

    def test_quoted_header_is_not_exact(self):
        text = '"subject"' + results_text(GOOD_ROW)[len('subject'):]
        self.assertProblem(text, 'error', 'line 1', 'first line')

    def test_wrong_cell_count(self):
        self.assertProblem(results_text(GOOD_ROW + ',extra'), 'error', 'line 2', 'cells')

    def test_empty_line(self):
        self.assertProblem(results_text(GOOD_ROW, '', GOOD_ROW.replace('baseline', 'stepper-v2')),
                           'error', 'line 3', 'Empty lines')

    # Subject and metric.
    def test_unknown_subject(self):
        self.assertBadCell('subject', 'nobody', 'subject')

    def test_unknown_metric(self):
        self.assertBadCell('metric', 'accuracy', 'metric')

    # Group.
    def test_group_key_not_in_group_by(self):
        self.assertBadCell('group', 'seed=1', 'summary.group_by')

    def test_group_keys_unsorted(self):
        self.assertBadCell('group', 'resolution=64;case_family=plume', 'sorted')

    def test_group_key_repeated(self):
        self.assertBadCell('group', 'resolution=32;resolution=64', 'repeat')

    def test_group_pair_without_equals(self):
        self.assertBadCell('group', 'resolution', 'key=value')

    def test_group_value_with_equals(self):
        self.assertBadCell('group', 'resolution=6=4', 'key=value')

    def test_group_value_with_line_break(self):
        line = replace_cell(GOOD_ROW, 'group', '"resolution=6\n4"')
        self.assertProblem(results_text(line), 'error', 'line 2', 'line break')

    def test_group_without_group_by_in_benchmark(self):
        benchmark = dict(BENCHMARK, summary={})
        problems = check_results(results_text(replace_cell(GOOD_ROW, 'group', 'resolution=64')), benchmark)
        self.assertEqual([(p[0], p[1]) for p in problems], [('error', 'line 2')])

    # Count, unavailable and statistics.
    def test_count_not_an_integer(self):
        self.assertBadCell('count', '2.5', 'count')

    def test_count_negative(self):
        self.assertBadCell('count', '-1', 'count')

    def test_unavailable_not_an_integer(self):
        self.assertBadCell('unavailable', 'none', 'unavailable')

    def test_statistic_not_a_decimal_number(self):
        self.assertBadCell('median', 'nan', 'median')

    def test_statistic_infinite(self):
        self.assertBadCell('max', 'inf', 'max')

    def test_statistics_filled_when_count_is_zero(self):
        self.assertBadCell('count', '0', 'empty when count is 0')

    def test_statistics_missing_when_count_above_zero(self):
        self.assertBadCell('p90', '', 'missing')

    def test_statistics_outside_summary_statistics_may_be_empty(self):
        benchmark = dict(BENCHMARK, summary={'statistics': ['median']})
        line = f'baseline,rmse,,3,0,,2.0,,,,,{COMMIT},2026-11-02'
        self.assertEqual(check_results(results_text(line), benchmark), [])

    def test_zero_count_with_empty_statistics_is_valid(self):
        line = 'baseline,rmse,,0,5,,,,,,,,2026-11-02'
        self.assertEqual(check_results(results_text(line), BENCHMARK), [])

    # Commit and produced.
    def test_commit_uppercase(self):
        self.assertBadCell('commit', COMMIT.upper(), 'commit')

    def test_commit_short(self):
        self.assertBadCell('commit', COMMIT[:7], 'commit')

    def test_produced_wrong_form(self):
        self.assertBadCell('produced', '2026-11-02 10:30', 'produced')

    def test_produced_not_a_real_date(self):
        self.assertBadCell('produced', '2026-02-30', 'produced')

    def test_produced_empty(self):
        self.assertBadCell('produced', '', 'produced')

    def test_produced_with_time(self):
        line = replace_cell(GOOD_ROW, 'produced', '2026-11-02T23:59:59Z')
        self.assertEqual(check_results(results_text(line), BENCHMARK), [])

    # Uniqueness and order.
    def test_duplicate_row(self):
        self.assertProblem(results_text(GOOD_ROW, GOOD_ROW), 'error', 'line 3', 'repeats')

    def test_rows_out_of_order(self):
        later = GOOD_ROW.replace('baseline', 'stepper-v2')
        self.assertProblem(results_text(later, GOOD_ROW), 'error', 'line 3', 'out of order')

    def test_order_is_by_group_as_string(self):
        first = replace_cell(GOOD_ROW, 'group', 'resolution=128')
        second = replace_cell(GOOD_ROW, 'group', 'resolution=64')
        self.assertEqual(check_results(results_text(first, second), BENCHMARK), [])
        self.assertProblem(results_text(second, first), 'error', 'line 3', 'out of order')

    # Collecting and robustness.
    def test_collects_every_problem(self):
        line = 'nobody,accuracy,seed=1,x,-1,,,,,,,ABC,yesterday'
        problems = check_results(results_text(line), BENCHMARK)
        self.assertGreaterEqual(len(problems), 7)
        self.assertTrue(all(p[:2] == ('error', 'line 2') for p in problems))

    def test_line_numbers_follow_physical_lines(self):
        quoted = replace_cell(GOOD_ROW, 'group', '"resolution=6\n4"')
        bad = replace_cell(GOOD_ROW.replace('baseline', 'stepper-v2'), 'metric', 'accuracy')
        self.assertProblem(results_text(quoted, bad), 'error', 'line 4', 'metric')

    def test_never_raises_on_bad_input(self):
        for text, benchmark in ((None, BENCHMARK), (results_text(GOOD_ROW), None),
                                (results_text(GOOD_ROW), {'subjects': 'x', 'metrics': [1],
                                                          'summary': {'group_by': 5}}),
                                ('\x00,"', BENCHMARK)):
            with self.subTest(text=text, benchmark=benchmark):
                problems = check_results(text, benchmark)
                self.assertTrue(problems)
                self.assertTrue(all(p[0] in ('error', 'warning') for p in problems))


if __name__ == '__main__':
    unittest.main()
