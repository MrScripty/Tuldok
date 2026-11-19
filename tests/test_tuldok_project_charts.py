"""Charts and the report page (spec-m3.md section 5): chart_data, render_svg and render_report.

The frontier, number formatting and drawing are tested on hand-made data
without a database. chart_data and the report run only when
TULDOK_DATABASE_URL names a disposable cluster: each test copies
tests/fixtures/tuldok_project/minimal with a fresh project id
(test_tuldok_project_store.StoreCase) and drops that project's schema
afterwards. The expectations were worked out by hand from the fixture's
results/rollout.csv.
"""
import builtins
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import charts  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
from test_tuldok_project_store import StoreCase  # noqa: E402

DATABASE = os.environ.get('TULDOK_DATABASE_URL')
SVG = '{http://www.w3.org/2000/svg}'
METRIC = {'id': 'rmse', 'title': 'Rollout RMSE', 'units': 'm/s', 'better': 'lower'}


def point(subject, value, **extra):
    return {'subject': subject, 'title': extra.pop('title', subject.title()), 'recipe': None, 'value': value,
            'count': 4, 'unavailable': 0, 'produced': '2026-11-02', **extra}


def ranking(points, *, missing=(), title='Error by subject', group=None, series=None):
    return {'chart': 'charts/error-ranking', 'title': title, 'description': None, 'form': 'ranking',
            'benchmark': 'benchmarks/rollout', 'statistic': 'median', 'group': group, 'metric': METRIC,
            'metric_x': None, 'subject_count': len(points) + len(missing),
            'series': series or [{'group': '', 'points': points, 'missing': list(missing)}], 'missing': list(missing)}


def parse(text):
    """The root element of an SVG document; fails the test when it is not well-formed."""
    root = ElementTree.fromstring(text)
    assert root.tag == SVG + 'svg', root.tag
    return root


def shown(element):
    """The visible text of an SVG text element, without its <title> tooltip."""
    tooltip = element.find(SVG + 'title')
    return (element.text or '') if tooltip is None else (tooltip.tail or '')


def texts(root):
    return [shown(element) for element in root.iter(SVG + 'text')]


class Numbers(unittest.TestCase):

    def test_three_significant_digits_and_compact_small_and_large(self):
        cases = {0.0123: '0.0123', 2.4321e-6: '2.43e-6', 0.5: '0.500', 12345: '12300', 123456: '1.23e5',
                 9.996: '10.0', -0.00042: '-4.20e-4', 0.0009999: '0.00100', 0: '0', 1.0: '1.00', None: '-'}
        for value, text in cases.items():
            self.assertEqual(charts.format_number(value), text, value)


class Frontier(unittest.TestCase):
    """A point is on the frontier when no other point is at least as good on both and better on one."""

    def test_lower_is_better_on_both_with_ties(self):
        points = [(1.0, 5.0),   # fastest
                  (2.0, 3.0),   # on the frontier
                  (2.0, 3.0),   # identical to the previous one: neither beats the other
                  (2.0, 4.0),   # same x as the previous ones, worse y: beaten
                  (3.0, 3.0),   # same y, slower: beaten
                  (4.0, 1.0),   # most accurate
                  (5.0, 6.0)]   # beaten by all
        self.assertEqual(charts.frontier(points, 'lower', 'lower'), [True, True, True, False, False, True, False])

    def test_direction_follows_better_and_none_counts_as_lower(self):
        points = [(1.0, 1.0), (2.0, 2.0), (3.0, 0.5)]
        self.assertEqual(charts.frontier(points, 'higher', 'lower'), [True, True, False])
        self.assertEqual(charts.frontier(points, 'none', 'none'), [True, False, True])
        self.assertEqual(charts.frontier(points, 'lower', 'higher'), [False, False, True])
        self.assertEqual(charts.frontier([], 'lower', 'lower'), [])
        self.assertEqual(charts.frontier([(1.0, 1.0)], 'lower', 'lower'), [True])


class Drawing(unittest.TestCase):

    def test_well_formed_self_contained_and_deterministic_in_both_themes(self):
        data = ranking([point('b', 0.3125), point('a', 0.5), point('c', 0.625)], missing=['d'])
        light = charts.render_svg(data)
        dark = charts.render_svg(data, theme='dark')
        self.assertEqual(light, charts.render_svg(json.loads(json.dumps(data))))
        self.assertNotEqual(light, dark)
        for text in (light, dark):
            root = parse(text)
            self.assertTrue(root.get('viewBox').startswith('0 0 '))
            self.assertEqual(root.find(SVG + 'title').text, 'Error by subject')
            self.assertTrue(root.get('font-family').startswith("'Ubuntu Sans'"))
            self.assertIn('sans-serif', root.get('font-family'))
            for forbidden in ('<script', 'href', 'url(', '@import', 'http://', 'https://'):
                self.assertNotIn(forbidden, text.replace('xmlns="http://www.w3.org/2000/svg"', ''), forbidden)
        self.assertIn('#ffffff', light)   # light surface
        self.assertIn('#171c22', dark)    # dark surface
        self.assertIn('#e6eaf0', dark)    # dark ink, so text reads on the dark surface
        self.assertNotIn('#1b2330', dark)  # and no light-theme ink is left behind
        shown = texts(parse(light))
        self.assertIn('0.312', shown)
        self.assertTrue(any('Not drawn, no value: d' in line for line in shown), shown)
        with self.assertRaises(ValueError):
            charts.render_svg(data, theme='blue')

    def test_text_is_escaped(self):
        data = ranking([point('a', 1.0, title='<b> & "quoted" \x01')], title='Fish & <chips>')
        root = parse(charts.render_svg(data))
        self.assertEqual(root.find(SVG + 'title').text, 'Fish & <chips>')
        self.assertIn('<b> & "quoted" ', texts(root))

    def test_an_empty_chart_says_so(self):
        for form in ('ranking', 'tradeoff', 'progression'):
            data = {**ranking([], missing=['a', 'b']), 'form': form,
                    'metric_x': {**METRIC, 'id': 'seconds', 'title': 'Time'} if form == 'tradeoff' else None,
                    'series': []}
            shown = ' '.join(texts(parse(charts.render_svg(data))))
            self.assertIn('No results yet: none of the 2 subjects of benchmarks/rollout', shown, form)
        data = {**ranking([]), 'form': 'comparison', 'metrics': [METRIC], 'rows': [], 'subject_count': 0}
        self.assertIn('has no subjects', ' '.join(texts(parse(charts.render_svg(data)))))

    def test_long_labels_are_cut_and_kept_whole_in_the_tooltip(self):
        long_title = 'A subject title of exactly one hundred characters, which is far too long for the label column' + '.' * 7
        self.assertEqual(len(long_title), 100)
        root = parse(charts.render_svg(ranking([point('a', 1.0, title=long_title), point('b', 2.0)])))
        labels = [element for element in root.iter(SVG + 'text') if element.find(SVG + 'title') is not None
                  and element.find(SVG + 'title').text.startswith(long_title)]
        self.assertEqual(len(labels), 1)
        cut = shown(labels[0])
        self.assertTrue(cut.endswith('…'), cut)
        self.assertLess(len(cut), 50)

    def test_a_ranking_grows_with_its_rows(self):
        def height(count):
            data = ranking([point(f's{index:03d}', 10.0 + index) for index in range(count)])
            return float(parse(charts.render_svg(data)).get('height'))

        self.assertGreater(height(150), height(10) + 140 * 17)
        root = parse(charts.render_svg(ranking([point(f's{index:03d}', 10.0 + index) for index in range(150)])))
        self.assertEqual(len([element for element in root.iter(SVG + 'path')]), 150)  # one bar per subject

    def test_log_axis_when_values_span_a_factor_of_100(self):
        log = texts(parse(charts.render_svg(ranking([point('a', 2.43e-6), point('b', 0.5)]))))
        self.assertIn('1e-6', log)
        self.assertIn('2.43e-6', log)
        self.assertTrue(any('log scale' in line for line in log))
        linear = texts(parse(charts.render_svg(ranking([point('a', 2.0), point('b', 150.0)]))))
        self.assertFalse(any('log scale' in line for line in linear))
        self.assertIn('0', linear)  # bars start from zero on a linear axis
        negative = texts(parse(charts.render_svg(ranking([point('a', -1.0), point('b', 500.0)]))))
        self.assertFalse(any('log scale' in line for line in negative))

    def test_grouped_series_draw_one_panel_each(self):
        series = [{'group': '1', 'points': [point('a', 1.0), point('b', 2.0)], 'missing': []},
                  {'group': '8', 'points': [point('a', 3.0)], 'missing': ['b']}]
        shown = texts(parse(charts.render_svg(ranking([], group='horizon', series=series, missing=['b']))))
        self.assertIn('horizon = 1', shown)
        self.assertIn('horizon = 8', shown)
        self.assertIn('No value: b', shown)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class ChartData(StoreCase):

    def setUp(self):
        super().setUp()
        self.project = self.open()

    def points(self, data, series=0):
        return [(item['subject'], item['value']) for item in data['series'][series]['points']]

    def test_ranking_by_group_best_first_with_missing(self):
        data = charts.chart_data(self.project, 'charts/rollout-ranking')
        self.assertEqual((data['form'], data['benchmark'], data['statistic'], data['group']),
                         ('ranking', 'benchmarks/rollout', 'median', 'horizon'))
        self.assertEqual(data['metric'], METRIC)
        self.assertIsNone(data['metric_x'])
        self.assertEqual([series['group'] for series in data['series']], ['1', '8'])
        self.assertEqual(self.points(data, 0), [('stepper-k2', 0.3125), ('stepper-k1', 0.5), ('early-fit', 0.625)])
        # early-fit's horizon=8 row has count 0: it is missing, not a point at zero.
        self.assertEqual(self.points(data, 1), [('stepper-k2', 1.25), ('stepper-k1', 2.0)])
        self.assertEqual(data['series'][1]['missing'], ['early-fit'])
        self.assertEqual(data['missing'], ['early-fit'])
        first = data['series'][0]['points'][0]
        self.assertEqual(first, {'subject': 'stepper-k2', 'title': 'Stepper k2', 'recipe': 'recipes/stepper-k2',
                                 'value': 0.3125, 'count': 4, 'unavailable': 0, 'produced': '2026-11-02T10:15:00Z'})
        self.assertEqual(charts.chart_data(self.project, 'rollout-ranking'), data)  # a bare name works too

    def test_tradeoff_sorted_by_x_with_its_frontier(self):
        data = charts.chart_data(self.project, 'charts/speed-accuracy')
        self.assertEqual(data['metric_x']['id'], 'seconds')
        self.assertEqual(len(data['series']), 1)
        self.assertEqual(data['series'][0]['group'], '')
        found = [(item['subject'], item['x'], item['value'], item['frontier']) for item in data['series'][0]['points']]
        # stepper-k2 is both faster and more accurate than the other two.
        self.assertEqual(found, [('stepper-k2', 1.375, 0.5, True), ('stepper-k1', 1.75, 0.875, False),
                                 ('early-fit', 2.5, 0.625, False)])
        self.assertEqual(data['missing'], [])

    def test_progression_in_training_order_with_best_so_far(self):
        data = charts.chart_data(self.project, 'charts/rollout-progression')
        found = [(item['position'], item['subject'], item['trained_at'], item['value'], item['best_so_far'])
                 for item in data['series'][0]['points']]
        # early-fit has a trained_at label; the two steppers have none and follow by name.
        self.assertEqual(found, [(0, 'early-fit', '2026-03-14', 0.625, 0.625),
                                 (1, 'stepper-k1', None, 0.875, 0.625),
                                 (2, 'stepper-k2', None, 0.5, 0.5)])

    def test_comparison_rows_in_ranking_order_or_the_charts_own(self):
        data = charts.chart_data(self.project, 'charts/rollout-comparison')
        self.assertNotIn('series', data)
        self.assertEqual([metric['id'] for metric in data['metrics']], ['rmse', 'seconds'])
        self.assertEqual([(row['subject'], row['values']) for row in data['rows']],
                         [('early-fit', {'rmse': 0.925, 'seconds': 2.9}),
                          ('stepper-k2', {'rmse': 1.65, 'seconds': 1.675}),
                          ('stepper-k1', {'rmse': 2.65, 'seconds': 2.35})])
        self.edit('charts/rollout-comparison', lambda d: d.update(subjects=['stepper-k1', 'early-fit']))
        data = charts.chart_data(self.project, 'charts/rollout-comparison')
        self.assertEqual([row['subject'] for row in data['rows']], ['stepper-k1', 'early-fit'])

    def edit(self, reference, change):
        path = self.folder / f'{reference}.json'
        document = json.loads(path.read_text(encoding='utf-8'))
        change(document)
        self.project.set_definition(reference, json.dumps(document, indent=2) + '\n')

    def test_higher_is_better_and_a_subject_without_rows(self):
        def change(document):
            document['metrics'][0]['better'] = 'higher'
            document['subjects'].append({'name': 'stepper-k3', 'title': 'Stepper k3'})

        self.edit('benchmarks/rollout', change)
        data = charts.chart_data(self.project, 'charts/rollout-progression')
        self.assertEqual([item['best_so_far'] for item in data['series'][0]['points']], [0.625, 0.875, 0.875])
        self.assertEqual(data['missing'], ['stepper-k3'])
        self.edit('charts/rollout-ranking', lambda d: d.pop('subjects'))
        data = charts.chart_data(self.project, 'charts/rollout-ranking')
        self.assertEqual(self.points(data, 0), [('early-fit', 0.625), ('stepper-k1', 0.5), ('stepper-k2', 0.3125)])
        self.assertEqual(data['missing'], ['early-fit', 'stepper-k3'])
        tradeoff = charts.chart_data(self.project, 'charts/speed-accuracy')
        # Higher error now counts as better: stepper-k1 is faster than early-fit and higher, so it beats it.
        self.assertEqual({item['subject']: item['frontier'] for item in tradeoff['series'][0]['points']},
                         {'stepper-k2': True, 'stepper-k1': True, 'early-fit': False})

    def test_values_imported_here_answer_the_same_chart(self):
        before = charts.chart_data(self.project, 'charts/speed-accuracy')
        for path in sorted((self.base / 'values').glob('*.json')):
            self.project.import_values(path.read_text(encoding='utf-8'))
        self.assertEqual(charts.chart_data(self.project, 'charts/speed-accuracy'), before)

    def test_unknown_chart(self):
        for reference in ('charts/nothing', 'nothing', 'recipes/early-fit', '../x'):
            with self.assertRaises(ProjectError) as caught:
                charts.chart_data(self.project, reference)
            self.assertEqual(caught.exception.code, 'not-found')

    def test_chart_data_opens_no_file(self):
        """Every chart is answered while any attempt to open a file fails."""
        references = [row['reference'] for row in self.project.definitions(kind='chart')]
        expected = [charts.chart_data(self.project, reference) for reference in references]  # also loads lazy imports
        opened = []

        def refuse(*arguments, **keywords):
            opened.append(arguments[:1])
            raise AssertionError(f'chart_data opened a file: {arguments[:1]}')

        with mock.patch.object(builtins, 'open', refuse), mock.patch.object(io, 'open', refuse), \
                mock.patch.object(io, 'FileIO', refuse), mock.patch.object(os, 'open', refuse), \
                mock.patch.object(os, 'scandir', refuse), mock.patch.object(os, 'listdir', refuse), \
                mock.patch.object(Path, 'open', refuse), mock.patch.object(Path, 'read_text', refuse), \
                mock.patch.object(Path, 'read_bytes', refuse):
            answered = [charts.chart_data(self.project, reference) for reference in references]
        self.assertEqual(opened, [])
        self.assertEqual(answered, expected)


@unittest.skipUnless(DATABASE, 'TULDOK_DATABASE_URL is not set; database tests need a disposable cluster.')
class Report(StoreCase):

    def test_one_self_contained_page_with_every_chart(self):
        project = self.open()
        light = charts.render_report(project)
        dark = charts.render_report(project, theme='dark')
        self.assertEqual(light, charts.render_report(project))
        self.assertNotEqual(light, dark)
        for page in (light, dark):
            root = ElementTree.fromstring(page.split('\n', 1)[1])  # well-formed after the doctype line
            self.assertEqual(root.tag, 'html')
            self.assertTrue(page.startswith('<!DOCTYPE html>\n'))
            body = page.replace('xmlns="http://www.w3.org/2000/svg"', '')
            for forbidden in ('<script', 'href', 'src=', 'url(', '@import', 'http://', 'https://', '<link'):
                self.assertNotIn(forbidden, body, forbidden)
            figures = root.findall('.//figure')
            self.assertEqual(len(figures), 4)
            self.assertTrue(all(figure.find(SVG + 'svg') is not None for figure in figures))
            headings = [element.text for element in root.iter('h3')]
            self.assertEqual(headings, ['Every metric side by side', 'Rollout error in training order',
                                        'Rollout error by subject', 'Error against time'])
            details = root.findall('.//details')
            self.assertEqual(len(details), 8)  # one per kind
            self.assertTrue(all(element.get('open') is None for element in details))
            sections = [element.text for element in root.iter('h2')]
            self.assertEqual(sections, ['Charts ', 'Results ', 'Definitions '])
            self.assertIn('13 definitions', page)
        self.assertIn('color-scheme: dark', dark)
        self.assertIn('#171c22', dark)
        # Where the project stands comes first, then the charts, then the results and the definitions.
        self.assertLess(light.index('13 definitions'), light.index('<h2>Charts'))
        self.assertLess(light.index('<h2>Charts'), light.index('<h2>Results'))
        self.assertLess(light.index('<h2>Results'), light.index('<h2>Definitions'))


if __name__ == '__main__':
    unittest.main()
