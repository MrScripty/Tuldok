"""Charts of benchmark results: their data from the summary table, their SVG drawing, and the report page.

Owns section 5 of docs/plans/definition-first-projects/spec-m3.md. chart_data
answers a chart definition with SQL only, through the Project's reading
methods and a few queries of its own on the project's connection: the chart,
its benchmark and the subjects' recipes come from the definitions table, the
numbers from result_summaries. Nothing here opens a file. render_svg and
render_report are pure functions of what they are given: the same data gives
the same bytes. Colours and type are the design tokens of the project
workspace redesign (docs/plans/project-workspace-redesign/README.md), one hue
for marks and the good colour for the frontier and the running best; text is
drawn in the ink tokens only, never in a mark colour.
"""
import html
import math
import re

from . import documents
from .store import ProjectError

DEFAULT_STATISTIC = 'median'
THEMES = ('light', 'dark')

# Design tokens (project-workspace-redesign/README.md, "Design system").
_TOKENS = {
    'light': {'page': '#f3f5f7', 'surface': '#ffffff', 'line': '#dfe4ea', 'line_strong': '#c5cdd6',
              'ink': '#1b2330', 'ink2': '#596679', 'ink3': '#8a94a3', 'accent': '#2c5fb8', 'good': '#237c60'},
    'dark': {'page': '#0f1317', 'surface': '#171c22', 'line': '#2a323c', 'line_strong': '#3a4552',
             'ink': '#e6eaf0', 'ink2': '#aab3c0', 'ink3': '#7c8694', 'accent': '#6a9ae8', 'good': '#4fb68f'},
}
FONT = "'Ubuntu Sans', 'Noto Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
MONO = "'Ubuntu Sans Mono', 'Ubuntu Mono', ui-monospace, 'SFMono-Regular', Menlo, monospace"


# ================================================================== data

def _query(project, template, parameters=None):
    """Rows of one query on the project's own connection; {schema} names the project's schema."""
    return project._execute(template, parameters).fetchall()


def _document(project, directory, name):
    rows = _query(project, 'SELECT document FROM {schema}.definitions '
                           'WHERE directory = %s AND name = %s AND NOT removed', (directory, name))
    return rows[0][0] if rows else None


def _trained_at(project, recipe_names):
    """{recipe name: labels.trained_at} for the recipes that have one."""
    if not recipe_names:
        return {}
    rows = _query(project, "SELECT name, document->'labels'->>'trained_at' FROM {schema}.definitions "
                           "WHERE directory = 'recipes' AND NOT removed AND name = ANY(%s)", (sorted(recipe_names),))
    return {name: value for name, value in rows if isinstance(value, str) and value}


def chart_reference(text):
    """charts/<name> for a chart given as a bare name or as a reference; None when it is neither."""
    name = text[len('charts/'):] if isinstance(text, str) and text.startswith('charts/') else text
    return f'charts/{name}' if documents.is_name(name) else None


def _lower_first(better):
    return better != 'higher'


def frontier(points, better_y, better_x):
    """For each (x, value) pair, whether no other pair is at least as good on both and better on one.

    better_* is the metric's `better`; `none` counts as lower is better. Two
    identical pairs do not beat each other, so both stay on the frontier.
    """
    sign_y = 1 if _lower_first(better_y) else -1
    sign_x = 1 if _lower_first(better_x) else -1
    keyed = [(sign_x * x, sign_y * y) for x, y in points]  # smaller is better on both
    flags = []
    for index, (x, y) in enumerate(keyed):
        beaten = any(ox <= x and oy <= y and (ox < x or oy < y)
                     for other, (ox, oy) in enumerate(keyed) if other != index)
        flags.append(not beaten)
    return flags


def _metric(document, metric_id):
    for item in document.get('metrics', []):
        if item.get('id') == metric_id:
            return {'id': metric_id, 'title': item.get('title', metric_id), 'units': item.get('units'),
                    'better': item.get('better', 'none')}
    raise ProjectError(f'{metric_id!r} is not a metric of the benchmark.', 'not-found')


def _group_order(values):
    """Group values sorted numerically when every one is a number, as text otherwise."""
    def number(text):
        try:
            value = float(text)
        except ValueError:
            return None
        return value if math.isfinite(value) else None

    numbers = [number(value) for value in values]
    if values and all(value is not None for value in numbers):
        return [value for _, value in sorted(zip(numbers, values))]
    return sorted(values)


def _value_sort(better):
    lower = _lower_first(better)
    return lambda point: ((point['value'] if lower else -point['value']), point['subject'])


def chart_data(project, reference):
    """The data of one chart definition, from the definitions and result_summaries tables only.

    reference is charts/<name> (a bare name is accepted too). Raises
    ProjectError (not-found) when the chart or its benchmark does not exist.
    """
    chart_ref = chart_reference(reference)
    if chart_ref is None:
        raise ProjectError(f'{reference!r} is not a chart name or a reference such as charts/<name>.', 'not-found',
                           references=[str(reference)])
    chart = _document(project, 'charts', chart_ref[len('charts/'):])
    if chart is None:
        raise ProjectError(f'There is no chart {chart_ref}.', 'not-found', references=[chart_ref])
    parsed = documents.parse_reference(chart.get('benchmark'))
    benchmark = _document(project, *parsed) if parsed and parsed[0] == 'benchmarks' else None
    if benchmark is None:
        raise ProjectError(f'{chart_ref} names no existing benchmark.', 'not-found', references=[chart_ref])
    benchmark_name = parsed[1]
    form = chart['form']
    statistic = chart.get('statistic', DEFAULT_STATISTIC)
    group_key = chart.get('group') or ''
    metric = _metric(benchmark, chart['metric'])
    metric_x = _metric(benchmark, chart['metric_x']) if form == 'tradeoff' else None

    declared = {item['name']: item for item in benchmark.get('subjects', [])}
    names = [name for name in chart.get('subjects', list(declared)) if name in declared]
    subjects = {name: {'subject': name, 'title': declared[name].get('title') or name,
                       'recipe': declared[name].get('recipe')} for name in names}

    # {(subject, metric, group value): (statistic, row)} for the usable rows of this chart's group.
    wanted = [metric['id']] + ([metric_x['id']] if metric_x else [])
    if form == 'comparison':
        wanted = [item['id'] for item in benchmark.get('metrics', [])]
    stats, group_values = {}, set()
    for metric_id in dict.fromkeys(wanted):
        for stored in project.result_summaries(benchmark_name, metric=metric_id, group=group_key):
            row = stored.row
            if row.subject not in subjects:
                continue
            value = row.group.split('=', 1)[1] if group_key else ''
            group_values.add(value)
            number = getattr(row, statistic)
            if row.count > 0 and number is not None:
                stats[(row.subject, metric_id, value)] = (number, row)

    groups = _group_order(sorted(group_values)) if group_key else ['']
    result = {'chart': chart_ref, 'title': chart['title'], 'description': chart.get('description'),
              'form': form, 'benchmark': f'benchmarks/{benchmark_name}', 'statistic': statistic,
              'group': group_key or None, 'metric': metric, 'metric_x': metric_x, 'subject_count': len(names)}

    if form == 'comparison':
        return _comparison(result, benchmark, names, subjects, stats, groups, explicit='subjects' in chart)

    trained = _trained_at(project, {item['recipe'].split('/', 1)[1] for item in subjects.values()
                                    if isinstance(item['recipe'], str) and item['recipe'].startswith('recipes/')})
    series, missing = [], set()
    for value in groups:
        points, lacking = [], []
        for name in names:
            found = stats.get((name, metric['id'], value))
            found_x = stats.get((name, metric_x['id'], value)) if metric_x else None
            if found is None or (metric_x is not None and found_x is None):
                lacking.append(name)
                continue
            number, row = found
            point = {**subjects[name], 'value': number, 'count': row.count, 'unavailable': row.unavailable,
                     'produced': row.produced}
            if metric_x is not None:
                point['x'] = found_x[0]
            points.append(point)
        missing.update(lacking)
        if form == 'ranking':
            points.sort(key=_value_sort(metric['better']))
        elif form == 'tradeoff':
            on_front = frontier([(point['x'], point['value']) for point in points], metric['better'], metric_x['better'])
            for point, flag in zip(points, on_front):
                point['frontier'] = flag
            by_value = _value_sort(metric['better'])
            points.sort(key=lambda point: (point['x'], *by_value(point)))
        else:  # progression
            for point in points:
                recipe = point['recipe']
                point['trained_at'] = trained.get(recipe.split('/', 1)[1]) if isinstance(recipe, str) else None
            points.sort(key=lambda point: (point['trained_at'] is None, point['trained_at'] or '', point['subject']))
            best = None
            pick = min if _lower_first(metric['better']) else max
            for position, point in enumerate(points):
                best = point['value'] if best is None else pick(best, point['value'])
                point['position'] = position
                point['best_so_far'] = best
        series.append({'group': value, 'points': points, 'missing': lacking})
    if not groups:  # a grouped chart with no rows for its group at all
        missing.update(names)
    result['series'] = series
    result['missing'] = [name for name in names if name in missing]
    return result


def _comparison(result, benchmark, names, subjects, stats, groups, *, explicit):
    """Fill metrics, rows and missing of a comparison: one row per subject (and group value) with a value."""
    metrics = [_metric(benchmark, item['id']) for item in benchmark.get('metrics', [])]
    metric_id, lower = result['metric']['id'], _lower_first(result['metric']['better'])
    rows, held = [], set()
    for value in groups:
        found = []
        for name in names:
            values = {item['id']: stats[(name, item['id'], value)][0] if (name, item['id'], value) in stats else None
                      for item in metrics}
            if any(number is not None for number in values.values()):
                held.add(name)
                found.append({**subjects[name], 'group': value, 'values': values})
        if not explicit:  # the ranking order of the chart's metric; rows without it last, by name
            found.sort(key=lambda row: (row['values'][metric_id] is None,
                                        0 if row['values'][metric_id] is None
                                        else row['values'][metric_id] if lower else -row['values'][metric_id],
                                        row['subject']))
        rows.extend(found)
    result['metrics'] = metrics
    result['rows'] = rows
    result['missing'] = [name for name in names if name not in held]
    return result


# ============================================================== numbers

def format_number(value):
    """Three significant digits; very small and very large numbers as 2.43e-6 or 1.5e7."""
    if value is None:
        return '-'
    if value == 0:
        return '0'
    rounded = float(f'{value:.2e}')
    if abs(rounded) < 1e-3 or abs(rounded) >= 1e5:
        mantissa, exponent = f'{value:.2e}'.split('e')
        return f'{mantissa}e{int(exponent)}'
    decimals = max(0, 2 - math.floor(math.log10(abs(rounded))))
    return f'{rounded:.{decimals}f}'


def _tick_text(value):
    """A tick label: like format_number but without trailing zeros (ticks are round numbers)."""
    text = format_number(value)
    if 'e' in text:
        mantissa, exponent = text.split('e')
        if '.' in mantissa:
            mantissa = mantissa.rstrip('0').rstrip('.')
        return f'{mantissa}e{exponent}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if text in ('-0', '') else text


class _Scale:
    """A value axis: logarithmic when every value is positive and they span a factor of at least 100."""

    def __init__(self, values, start, end, *, zero=False):
        self.start, self.end = start, end
        lo, hi = min(values), max(values)
        self.log = lo > 0 and hi >= 100 * lo
        if self.log:
            first, last = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
            step = max(1, math.ceil((last - first) / 8))
            self.lo, self.hi = 10.0 ** first, 10.0 ** last
            self.ticks = [10.0 ** power for power in range(first, last + 1, step)]
            return
        if zero:
            lo, hi = min(lo, 0.0), max(hi, 0.0)
        if lo == hi:
            pad = abs(lo) * 0.1 or 1.0
            lo, hi = lo - pad, hi + pad
        raw = (hi - lo) / 5
        power = 10.0 ** math.floor(math.log10(raw))
        step = next(factor * power for factor in (1, 2, 2.5, 5, 10) if factor * power >= raw)
        self.lo = math.floor(lo / step + 1e-9) * step
        self.hi = math.ceil(hi / step - 1e-9) * step
        count = round((self.hi - self.lo) / step)
        self.ticks = [self.lo + index * step for index in range(count + 1)]
        self.ticks = [0.0 if abs(tick) < step * 1e-9 else float(f'{tick:.12g}') for tick in self.ticks]

    def __call__(self, value):
        if self.log:
            share = (math.log10(value) - math.log10(self.lo)) / (math.log10(self.hi) - math.log10(self.lo))
        else:
            share = (value - self.lo) / (self.hi - self.lo)
        return self.start + share * (self.end - self.start)


# ================================================================== SVG

_XML_FORBIDDEN = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')
_CHAR = 0.58  # average advance of a character, in em, for estimating text width


def _esc(text):
    return html.escape(_XML_FORBIDDEN.sub('', str(text)), quote=True)


def _f(number):
    text = f'{number:.1f}'
    return text[:-2] if text.endswith('.0') else text


def _width(text, size):
    return len(text) * size * _CHAR


def _fit(text, size, width):
    """text, cut with an ellipsis so that it fits width at size."""
    text = str(text)
    limit = max(1, int(width / (size * _CHAR)))
    return text if len(text) <= limit else text[:max(1, limit - 1)].rstrip() + '…'


def _units(metric):
    """The metric's units for display; '1' (a pure number) shows nothing."""
    units = metric.get('units')
    return None if units in (None, '', '1') else units


def _sentence(title):
    """A metric title inside a sentence: first letter lowered unless it starts an acronym (GPU stays)."""
    if len(title) > 1 and title[0].isupper() and not title[1].isupper():
        return title[0].lower() + title[1:]
    return title


def _metric_label(metric, *, log=False):
    units = _units(metric)
    text = metric['title'] + (f' ({units})' if units else '')
    return text + (', log scale' if log else '')


def _better_words(metric):
    return {'lower': 'lower is better', 'higher': 'higher is better'}.get(metric['better'], 'no better direction')


class _Svg:
    """Collects SVG elements; every attribute and text is escaped here."""

    def __init__(self, colours):
        self.c = colours
        self.parts = []

    def add(self, tag, attributes, text=None, tooltip=None):
        attrs = ''.join(f' {key.replace("_", "-")}="{_esc(value)}"' for key, value in attributes.items()
                        if value is not None)
        inner = (f'<title>{_esc(tooltip)}</title>' if tooltip else '') + (_esc(text) if text is not None else '')
        self.parts.append(f'<{tag}{attrs}>{inner}</{tag}>' if inner else f'<{tag}{attrs}/>')

    def text(self, x, y, text, *, size=12, fill='ink2', anchor=None, weight=None, numeric=False, tooltip=None,
             halo=False):
        self.add('text', {'x': _f(x), 'y': _f(y), 'font-size': size, 'fill': self.c[fill], 'text-anchor': anchor,
                          'font-weight': weight, 'style': 'font-variant-numeric:tabular-nums' if numeric else None,
                          'stroke': self.c['surface'] if halo else None, 'stroke-width': 3 if halo else None,
                          'paint-order': 'stroke' if halo else None, 'stroke-linejoin': 'round' if halo else None},
                 text, tooltip)

    def line(self, x1, y1, x2, y2, colour='line', width=1):
        self.add('line', {'x1': _f(x1), 'y1': _f(y1), 'x2': _f(x2), 'y2': _f(y2), 'stroke': self.c[colour],
                          'stroke-width': width, 'shape-rendering': 'crispEdges' if width == 1 else None})

    def dot(self, x, y, colour='accent', tooltip=None, r=4):
        self.add('circle', {'cx': _f(x), 'cy': _f(y), 'r': r, 'fill': self.c[colour], 'stroke': self.c['surface'],
                            'stroke-width': 2}, tooltip=tooltip)

    def path(self, d, colour, width=2):
        self.add('path', {'d': d, 'fill': 'none', 'stroke': self.c[colour], 'stroke-width': width,
                          'stroke-linejoin': 'round', 'stroke-linecap': 'round'})

    def bar(self, x0, x1, y, height, tooltip=None):
        """A horizontal bar from x0, square at the baseline and rounded (4px) at its data end."""
        length = x1 - x0
        if length <= 0.5:
            self.line(x0, y, x0, y + height, 'accent', 1)
            return
        r = min(4.0, length, height / 2)
        d = (f'M{_f(x0)},{_f(y)}H{_f(x1 - r)}A{_f(r)},{_f(r)} 0 0 1 {_f(x1)},{_f(y + r)}'
             f'V{_f(y + height - r)}A{_f(r)},{_f(r)} 0 0 1 {_f(x1 - r)},{_f(y + height)}H{_f(x0)}Z')
        self.add('path', {'d': d, 'fill': self.c['accent']}, tooltip=tooltip)

    def document(self, width, height, data, note, heading):
        ident = 'chart-' + re.sub('[^a-z0-9_-]', '-', str(data.get('chart', 'chart')).split('/')[-1])
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_f(width)} {_f(height)}" '
                f'width="{_f(width)}" height="{_f(height)}" role="img" '
                f'aria-labelledby="{ident}-title {ident}-desc" font-family="{_esc(FONT)}">'
                f'<title id="{ident}-title">{_esc(data.get("title", ""))}</title>'
                f'<desc id="{ident}-desc">{_esc(note)}</desc>'
                f'<rect width="100%" height="100%" fill="{self.c["surface"] if heading else "none"}"/>')
        return head + ''.join(self.parts) + '</svg>\n'


WIDTH = 760
_SIDE = 12


def _subtitle(data):
    metric, statistic = data['metric'], data['statistic'].capitalize()
    if data['form'] == 'tradeoff':
        text = (f'{statistic} {_sentence(metric["title"])} against {data["statistic"]} '
                f'{_sentence(data["metric_x"]["title"])}')
    elif data['form'] == 'comparison':
        text = f'{statistic} of every metric'
    else:
        text = f'{statistic} {_sentence(metric["title"])}, {_better_words(metric)}'
    return text + f' · {data["benchmark"]}'


def _lines(svg, x, y, text, *, size, width, lines=2, fill='ink2', step=None):
    """Text wrapped at spaces into at most `lines` lines; returns the y below the last line."""
    step = step or round(size * 1.35)
    for number, line in enumerate(_wrap(text, size, width, lines)):
        svg.text(x, y + number * step, line, size=size, fill=fill, tooltip=text if number == 0 and line != text else None)
    return y + (number + 1) * step


def describe(data):
    """One line on what the chart shows and how many subjects are not drawn."""
    form, metric, total = data['form'], data['metric'], data.get('subject_count', 0)
    statistic = data['statistic']
    if form == 'ranking':
        shown = f'Subjects ranked by {statistic} {_sentence(metric["title"])}, best first ({_better_words(metric)}).'
    elif form == 'tradeoff':
        on = sum(point.get('frontier', False) for series in data['series'] for point in series['points'])
        shown = (f'{statistic.capitalize()} {_sentence(metric["title"])} against {statistic} '
                 f'{_sentence(data["metric_x"]["title"])}; the line joins the '
                 + (f'{on} {"subject" if on == 1 else "subjects"} ' if on else 'subjects ')
                 + 'no other subject beats on both.')
    elif form == 'progression':
        shown = (f'{statistic.capitalize()} {_sentence(metric["title"])} in the order the subjects were trained, '
                 f'with the best so far.')
    else:
        shown = f'{statistic.capitalize()} of every metric per subject; the best in each column is marked.'
    if data.get('group'):
        shown = shown[:-1] + f', one panel per {data["group"]}.'
    missing = len(data['missing'])
    if total == 0:
        return shown + ' The benchmark has no subjects.'
    if missing == total:
        return shown + f' None of the {total} subjects has a result yet.'
    if missing:
        return shown + f' {missing} of {total} subjects {"has" if missing == 1 else "have"} no value and ' \
                       f'{"is" if missing == 1 else "are"} not drawn.'
    return shown + f' All {total} subjects are drawn.'


def _names_line(names, width, prefix):
    """prefix + as many names as fit in width, then 'and N more'."""
    shown = []
    for index, name in enumerate(names):
        rest = len(names) - index - 1
        candidate = prefix + ', '.join(shown + [name]) + (f' and {rest} more' if rest else '')
        if _width(candidate, 12) > width and shown:
            return prefix + ', '.join(shown) + f' and {len(names) - len(shown)} more'
        shown.append(name)
    return prefix + ', '.join(shown)


def render_svg(data, *, theme='light', heading=True):
    """One self-contained SVG document drawing chart_data's result; the same input gives the same bytes.

    With heading=False the title and subtitle are left out (the report page
    sets them as HTML) and the background is transparent.
    """
    if theme not in THEMES:
        raise ValueError(f'theme is one of {", ".join(THEMES)}')
    svg = _Svg(_TOKENS[theme])
    note = describe(data)
    y = 8
    if heading:
        svg.text(_SIDE, 28, _fit(data['title'], 16, WIDTH - 2 * _SIDE), size=16, fill='ink', weight=600,
                 tooltip=data['title'])
        y = _lines(svg, _SIDE, 48, _subtitle(data), size=12.5, width=WIDTH - 2 * _SIDE) + 2
    drawers = {'ranking': _ranking, 'tradeoff': _tradeoff, 'progression': _progression, 'comparison': _comparison_grid}
    has_points = (bool(data.get('rows')) if data['form'] == 'comparison'
                  else any(series['points'] for series in data.get('series', [])))
    width = WIDTH
    if not has_points:
        y = _empty(svg, data, y)
    else:
        y, width = drawers[data['form']](svg, data, y)
    if data['missing'] and has_points and not data.get('group'):
        y += 8
        svg.text(_SIDE, y + 12, _names_line(data['missing'], width - 2 * _SIDE,
                                            'Not drawn, no value: '), size=12)
        y += 20
    return svg.document(width, y + 12, data, note, heading)


def _empty(svg, data, y):
    total = data.get('subject_count', 0)
    if total == 0:
        message = f'Nothing to draw: {data["benchmark"]} has no subjects.'
    else:
        statistic = data['statistic']
        message = (f'No results yet: none of the {total} subjects of {data["benchmark"]} has a {statistic} '
                   f'{_sentence(data["metric"]["title"])}.')
    svg.line(_SIDE, y + 8, WIDTH - _SIDE, y + 8)
    bottom = _lines(svg, _SIDE, y + 34, message, size=13, width=WIDTH - 2 * _SIDE, lines=3)
    svg.line(_SIDE, bottom + 2, WIDTH - _SIDE, bottom + 2)
    return bottom + 6


def _series_heading(svg, data, series, y, width):
    """A panel heading for a grouped chart, with the subjects it lacks; returns the new y."""
    if not data.get('group'):
        return y
    svg.text(_SIDE, y + 16, _fit(f'{data["group"]} = {series["group"]}', 13, width - 2 * _SIDE), size=13,
             fill='ink', weight=600)
    y += 22
    if series['missing']:
        svg.text(_SIDE, y + 12, _names_line(series['missing'], width - 2 * _SIDE, 'No value: '), size=12)
        y += 18
    return y + 4


def _x_axis_top(svg, scale, y, bottom):
    for tick in scale.ticks:
        x = scale(tick)
        svg.line(x, y + 6, x, bottom, 'line')
        svg.text(x, y, _tick_text(tick), size=11, anchor='middle', numeric=True)


# ------------------------------------------------------------- ranking

_ROW = 18
_BAR = 10
_LABEL = 250


def _ranking(svg, data, y):
    values = [point['value'] for series in data['series'] for point in series['points']]
    longest = max(_width(point['title'], 12) for series in data['series'] for point in series['points'])
    label_width = min(_LABEL, max(60.0, math.ceil(longest)))
    left, right = _SIDE + label_width + 10, WIDTH - _SIDE - 64
    scale = _Scale(values, left, right, zero=True)
    for index, series in enumerate(data['series']):
        if index:
            y += 16
        y = _series_heading(svg, data, series, y, WIDTH)
        if not series['points']:
            svg.text(_SIDE, y + 14, 'No subject has a value here.', size=12)
            y += 24
            continue
        svg.text(left, y + 12, _fit(_metric_label(data['metric'], log=scale.log), 12, right - left), size=12)
        top = y + 38
        bottom = top + len(series['points']) * _ROW
        _x_axis_top(svg, scale, top - 6, bottom)
        base = scale(scale.lo)
        svg.line(base, top, base, bottom, 'line_strong')
        for row, point in enumerate(series['points']):
            middle = top + row * _ROW + _ROW / 2
            tip = scale(point['value'])
            label = f'{point["title"]}: {format_number(point["value"])} ({point["count"]} values)'
            svg.text(_SIDE, middle + 4, _fit(point['title'], 12, label_width), size=12, fill='ink', tooltip=label)
            svg.bar(base, tip, middle - _BAR / 2, _BAR, tooltip=label)
            svg.text(tip + 6, middle + 4, format_number(point['value']), size=11, numeric=True)
        y = bottom + 4
        if len(series['points']) > 30:  # a long ranking repeats its scale at the foot
            for tick in scale.ticks:
                svg.text(scale(tick), bottom + 16, _tick_text(tick), size=11, anchor='middle', numeric=True)
            y = bottom + 22
    return y, WIDTH


# ------------------------------------------------- scatter (tradeoff, progression)

_PLOT_HEIGHT = 320


def _boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _place_labels(svg, items, bounds, taken):
    """Label (x, y, text) points where a label fits without touching another; returns how many were left out."""
    left_out = 0
    for x, y, text in items:
        width, size = _width(text, 12), 12
        candidates = ((x + 8, y + 4, 'start', (x + 7, y - 9, x + 9 + width, y + 6)),
                      (x - 8, y + 4, 'end', (x - 9 - width, y - 9, x - 7, y + 6)),
                      (x, y - 10, 'middle', (x - width / 2, y - 23, x + width / 2, y - 7)),
                      (x, y + 20, 'middle', (x - width / 2, y + 7, x + width / 2, y + 23)),
                      (x + 6, y - 10, 'start', (x + 5, y - 23, x + 7 + width, y - 7)),
                      (x - 6, y - 10, 'end', (x - 7 - width, y - 23, x - 5, y - 7)),
                      (x + 6, y + 20, 'start', (x + 5, y + 7, x + 7 + width, y + 23)),
                      (x - 6, y + 20, 'end', (x - 7 - width, y + 7, x - 5, y + 23)))
        for tx, ty, anchor, box in candidates:
            inside = box[0] >= bounds[0] and box[2] <= bounds[2] and box[1] >= bounds[1] and box[3] <= bounds[3]
            if inside and not any(_boxes_overlap(box, other) for other in taken):
                svg.text(tx, ty, text, size=size, fill='ink', anchor=anchor, halo=True)
                taken.append(box)
                break
        else:
            left_out += 1
    return left_out


def _step_boxes(points):
    """Thin boxes along a step path through (x, y) screen points, so labels keep off the line."""
    boxes = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        boxes.append((min(x0, x1), y0 - 2, max(x0, x1), y0 + 2))
        boxes.append((x1 - 2, min(y0, y1), x1 + 2, max(y0, y1)))
    return boxes


def _step(points):
    """A step path through (x, y) screen points: across, then up or down to the next point."""
    if not points:
        return ''
    d = f'M{_f(points[0][0])},{_f(points[0][1])}'
    for x, y in points[1:]:
        d += f'H{_f(x)}V{_f(y)}'
    return d


def _point_label(point, width=150):
    """A point's label: its title when it fits, else its (short) name when that fits, else the title cut."""
    for text in (point['title'], point['subject']):
        if _width(text, 12) <= width:
            return text
    return _fit(point['title'], 12, width)


def _scatter_frame(svg, data, values, y):
    """The y axis and plot area of one scatter panel: returns (top, bottom, left, right, y_scale)."""
    left, right = _SIDE + 58, WIDTH - _SIDE - 8
    top = y + 34
    bottom = top + _PLOT_HEIGHT
    y_scale = _Scale(values, bottom - 10, top + 4)  # inset, so points on the extremes stay clear of the axis
    svg.text(_SIDE, y + 14, _fit(_metric_label(data['metric'], log=y_scale.log), 12, WIDTH - 2 * _SIDE), size=12)
    for tick in y_scale.ticks:
        ty = y_scale(tick)
        svg.line(left, ty, right, ty, 'line')
        svg.text(left - 6, ty + 4, _tick_text(tick), size=11, anchor='end', numeric=True)
    svg.line(left, bottom, right, bottom, 'line_strong')
    return top, bottom, left, right, y_scale


def _tradeoff(svg, data, y):
    xs = [point['x'] for series in data['series'] for point in series['points']]
    for index, series in enumerate(data['series']):
        if index:
            y += 20
        y = _series_heading(svg, data, series, y, WIDTH)
        if not series['points']:
            svg.text(_SIDE, y + 14, 'No subject has both values here.', size=12)
            y += 24
            continue
        top, bottom, left, right, y_scale = _scatter_frame(svg, data, [point['value'] for point in series['points']], y)
        x_scale = _Scale(xs, left + 12, right - 12)
        for tick in x_scale.ticks:
            tx = x_scale(tick)
            svg.line(tx, top, tx, bottom, 'line')
            svg.text(tx, bottom + 16, _tick_text(tick), size=11, anchor='middle', numeric=True)
        svg.text(right, bottom + 36, _fit(_metric_label(data['metric_x'], log=x_scale.log), 12, right - left),
                 size=12, anchor='end')
        front = [point for point in series['points'] if point['frontier']]
        screen = [(x_scale(point['x']), y_scale(point['value'])) for point in front]
        if len(screen) > 1:
            svg.path(_step(screen), 'good')
        for point in series['points']:
            if not point['frontier']:
                svg.dot(x_scale(point['x']), y_scale(point['value']), 'accent', _point_tip(data, point))
        for point in front:
            svg.dot(x_scale(point['x']), y_scale(point['value']), 'good', _point_tip(data, point) + ', on the frontier')
        taken = [(sx - 5, sy - 5, sx + 5, sy + 5) for sx, sy in
                 ((x_scale(point['x']), y_scale(point['value'])) for point in series['points'])]
        taken += _step_boxes(screen)
        left_out = _place_labels(svg, [(sx, sy, _point_label(point)) for (sx, sy), point in zip(screen, front)],
                                 (left, top - 4, right, bottom - 2), taken)
        y = bottom + 44
        svg.dot(_SIDE + 4, y + 8, 'good', None)
        key = f'On the frontier: no other subject is at least as good on both and better on one ({len(front)}).'
        if left_out:
            key += f' {left_out} frontier labels left out where they would overlap.'
        y = _lines(svg, _SIDE + 14, y + 12, key, size=12, width=WIDTH - 2 * _SIDE - 14) - 8
    return y, WIDTH


def _point_tip(data, point):
    text = f'{point["title"]}: {format_number(point["value"])}'
    if 'x' in point:
        text += f' at {format_number(point["x"])}'
    return text


def _progression(svg, data, y):
    for index, series in enumerate(data['series']):
        if index:
            y += 20
        y = _series_heading(svg, data, series, y, WIDTH)
        points = series['points']
        if not points:
            svg.text(_SIDE, y + 14, 'No subject has a value here.', size=12)
            y += 24
            continue
        values = [point['value'] for point in points] + [point['best_so_far'] for point in points]
        top, bottom, left, right, y_scale = _scatter_frame(svg, data, values, y)
        count = len(points)
        span = right - left - 40

        def x_of(position):
            return left + 20 + (span * position / (count - 1) if count > 1 else span / 2)

        # Ticks: up to eight subjects along the order, named by their short name.
        every = max(1, math.ceil(count / 8))
        for position in range(0, count, every):
            tx = x_of(position)
            svg.line(tx, bottom, tx, bottom + 4, 'line_strong')
            svg.text(tx, bottom + 16, _fit(points[position]['subject'], 11, span / 8 - 4), size=11, anchor='middle')
        undated = next((point['position'] for point in points if point['trained_at'] is None), None)
        if undated is not None and undated > 0:
            ux = (x_of(undated - 1) + x_of(undated)) / 2
            svg.line(ux, top, ux, bottom, 'line_strong')
            svg.text(ux + 6, top + 10, 'no training date from here', size=11)
        dated = count if undated is None else undated
        axis = f'Training order, earliest first ({dated} of {count} with a training date)'
        svg.text(right, bottom + 36, _fit(axis, 12, right - left), size=12, anchor='end')
        best = [(x_of(point['position']), y_scale(point['best_so_far'])) for point in points]
        svg.path(_step(best), 'good')
        records = [point for index, point in enumerate(points)
                   if index == 0 or point['best_so_far'] != points[index - 1]['best_so_far']]
        for point in points:
            record = point in records
            svg.dot(x_of(point['position']), y_scale(point['value']), 'good' if record else 'accent',
                    f'{point["title"]}: {format_number(point["value"])}'
                    + (f', trained {point["trained_at"]}' if point['trained_at'] else '')
                    + (', a new best' if record else ''), r=4 if record or count <= 60 else 3.5)
        taken = [(x_of(p['position']) - 4, y_scale(p['value']) - 4, x_of(p['position']) + 4, y_scale(p['value']) + 4)
                 for p in points] + _step_boxes(best)
        left_out = _place_labels(svg, [(x_of(point['position']), y_scale(point['value']), _point_label(point))
                                       for point in records], (left, top - 4, right, bottom - 2), taken)
        y = bottom + 44
        svg.line(_SIDE, y + 8, _SIDE + 14, y + 8, 'good', 2)
        key = f'Best so far; {len(records)} subjects set a new best.'
        if left_out:
            key += f' {left_out} of their labels left out where they would overlap.'
        y = _lines(svg, _SIDE + 20, y + 12, key, size=12, width=WIDTH - 2 * _SIDE - 20) - 8
    return y, WIDTH


# ---------------------------------------------------------- comparison

_CELL = 136
_NAME = 230


def _wrap(text, size, width, lines):
    """Up to `lines` lines of text wrapped at spaces to width; the last one cut with an ellipsis."""
    words, out, current = str(text).split(), [], ''
    for word in words:
        trial = f'{current} {word}'.strip()
        if _width(trial, size) <= width or not current:
            current = trial
        else:
            out.append(current)
            current = word
    out.append(current)
    if len(out) > lines:
        out = out[:lines - 1] + [' '.join(out[lines - 1:])]
    return [_fit(line, size, width) for line in out]


def _comparison_grid(svg, data, y):
    metrics, rows = data['metrics'], data['rows']
    grouped = bool(data.get('group'))
    name_width = _NAME + (90 if grouped else 0)
    width = max(WIDTH, 2 * _SIDE + name_width + _CELL * len(metrics))
    best = {}
    for metric in metrics:
        numbers = [row['values'][metric['id']] for row in rows if row['values'][metric['id']] is not None]
        if numbers and metric['better'] in ('lower', 'higher'):
            best[metric['id']] = min(numbers) if metric['better'] == 'lower' else max(numbers)
    header_lines = max(len(_wrap(metric['title'], 12, _CELL - 12, 4)) for metric in metrics)
    top = y + 8
    svg.text(_SIDE, top + 14, 'Subject', size=12, weight=500)
    if grouped:
        svg.text(_SIDE + _NAME, top + 14, data['group'], size=12, weight=500)
    for column, metric in enumerate(metrics):
        right = _SIDE + name_width + _CELL * (column + 1) - 4
        lines = _wrap(metric['title'], 12, _CELL - 12, 4)
        for number, line in enumerate(lines):
            svg.text(right, top + 14 + 15 * number, line, size=12, fill='ink', weight=500, anchor='end',
                     tooltip=metric['title'] if number == 0 else None)
        hint = {'lower': 'lower is better', 'higher': 'higher is better'}.get(metric['better'], 'no direction')
        for number, part in enumerate((_units(metric) or '', hint)):
            svg.text(right, top + 14 + 15 * header_lines + 14 * number, _fit(part, 11, _CELL - 8), size=11,
                     anchor='end')
    y = top + 36 + 15 * header_lines
    svg.line(_SIDE, y, width - _SIDE, y, 'line_strong')
    for row in rows:
        svg.text(_SIDE, y + 16, _fit(row['title'], 12, _NAME - 8), size=12, fill='ink', tooltip=row['title'])
        if grouped:
            svg.text(_SIDE + _NAME, y + 16, _fit(row['group'], 12, 82), size=12)
        for column, metric in enumerate(metrics):
            right = _SIDE + name_width + _CELL * (column + 1) - 4
            value = row['values'][metric['id']]
            is_best = value is not None and best.get(metric['id']) == value
            text = format_number(value)
            if is_best:
                svg.dot(right - _width(text, 12) - 9, y + 12, 'good', None, r=3)
            svg.text(right, y + 16, text, size=12, fill='ink' if value is not None else 'ink3', anchor='end',
                     weight=600 if is_best else None, numeric=True,
                     tooltip=f'{row["title"]}, {metric["title"]}: {text}' + (' (best)' if is_best else ''))
        y += 24
        svg.line(_SIDE, y, width - _SIDE, y, 'line')
    y += 10
    svg.dot(_SIDE + 4, y + 8, 'good', None, r=3)
    svg.text(_SIDE + 14, y + 12, 'Best in its column; columns with no better direction mark none.', size=12)
    return y + 20, width


# =============================================================== report

_PLURALS = {'dataset': 'Datasets', 'model': 'Models', 'recipe': 'Recipes', 'benchmark': 'Benchmarks',
            'step': 'Steps', 'environment': 'Environments', 'chart': 'Charts',
            'annotation': 'Annotation tasks'}
_STATE_WORDS = {'cannot-rebuild': 'cannot rebuild', 'needs-work': 'needs work', 'not-built': 'not built',
                'not-set-up': 'not set up', 'none': 'no state'}


def _style(colours):
    c = colours
    return f'''
:root {{ color-scheme: {'dark' if c['surface'] == _TOKENS['dark']['surface'] else 'light'}; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: {c['surface']}; color: {c['ink']};
  font: 14px/1.5 {FONT}; }}
main {{ max-width: 1040px; margin: 0 auto; padding: 32px 16px 64px; }}
h1 {{ font-size: 20px; font-weight: 600; margin: 0 0 4px; }}
h2 {{ font-size: 17px; font-weight: 600; margin: 40px 0 8px; padding-top: 16px; border-top: 1px solid {c['line']}; }}
h3 {{ font-size: 16px; font-weight: 600; margin: 32px 0 2px; }}
p {{ max-width: 66ch; margin: 0 0 8px; }}
.sum, .note {{ color: {c['ink2']}; font-weight: 400; }}
.note {{ font-size: 13px; margin-bottom: 12px; }}
.mono, code {{ font-family: {MONO}; font-size: 12.5px; }}
figure {{ margin: 0 -12px; overflow-x: auto; }}
figure svg {{ display: block; max-width: 100%; height: auto; }}
.wide {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 13px; }}
th, td {{ text-align: left; padding: 4px 20px 4px 0; border-bottom: 1px solid {c['line']}; vertical-align: top; }}
th {{ font-weight: 500; color: {c['ink2']}; }}
td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums; }}
details {{ border-bottom: 1px solid {c['line']}; padding: 6px 0; }}
details:first-of-type {{ border-top: 1px solid {c['line']}; }}
summary {{ cursor: pointer; font-weight: 500; }}
details table {{ margin: 8px 0 4px; }}
.refused {{ color: {c['ink2']}; }}
'''


def _plural(count, word):
    return f'{count} {word}' + ('' if count == 1 else 's')


def render_report(project, *, theme='light'):
    """One self-contained HTML page of the project: where it stands, every chart, the results, the definitions."""
    if theme not in THEMES:
        raise ValueError(f'theme is one of {", ".join(THEMES)}')
    colours = _TOKENS[theme]
    summary = project.summary()
    rows = [row for row in project.definitions() if not row['removed']]
    overview = project.results_overview()
    out = [f'<!DOCTYPE html>\n<html lang="en" data-theme="{theme}">\n<head>\n<meta charset="utf-8"/>\n'
           f'<meta name="viewport" content="width=device-width, initial-scale=1"/>\n'
           f'<title>{_esc(summary["name"])}</title>\n<style>{_style(colours)}</style>\n</head>\n<body>\n<main>\n']
    out.append(f'<h1>{_esc(summary["name"])}</h1>\n')
    # The folder's own name only: a report may be shared, and the full path says where it sits on this machine.
    folder_name = summary["folder"].rstrip('/').rsplit('/', 1)[-1]
    out.append(f'<p class="sum"><span class="mono">{_esc(folder_name)}</span> · project '
               f'<span class="mono">{_esc(summary["project_id"])}</span></p>\n')

    # Where the project stands.
    kinds = summary['kinds']
    total = sum(kinds.values())
    kind_words = ', '.join(_plural(count, kind) for kind, count in kinds.items())
    with_results = sum(1 for item in overview if item['rows'])
    differ = sum(1 for item in overview if item['differs_from_file'])
    out.append(f'<p>{_plural(total, "definition")}: {_esc(kind_words)}. '
               f'{with_results} of {_plural(len(overview), "benchmark")} have results in the database'
               + (f'; {differ} differ from their results file' if differ else '') + '.</p>\n')
    states = sorted({row['state'] for row in rows})
    table = {}
    for row in rows:
        table.setdefault(row['kind'], {}).setdefault(row['state'], 0)
        table[row['kind']][row['state']] += 1
    out.append('<div class="wide"><table>\n<tr><th>kind</th>'
               + ''.join(f'<th class="n">{_esc(_STATE_WORDS.get(state, state))}</th>' for state in states)
               + '<th class="n">total</th></tr>\n')
    for kind in sorted(table):
        out.append(f'<tr><td>{_esc(kind)}</td>'
                   + ''.join(f'<td class="n">{table[kind].get(state, "") or ""}</td>' for state in states)
                   + f'<td class="n">{sum(table[kind].values())}</td></tr>\n')
    out.append('</table></div>\n')

    # Charts.
    charts = [row for row in rows if row['kind'] == 'chart']
    out.append(f'<h2>Charts <span class="sum">{len(charts)}</span></h2>\n')
    if not charts:
        out.append('<p class="note">The project has no chart definitions.</p>\n')
    for row in charts:
        out.append(f'<h3>{_esc(row["title"])}</h3>\n')
        try:
            data = chart_data(project, row['reference'])
        except ProjectError as exc:
            out.append(f'<p class="note refused">{_esc(row["reference"])}: {_esc(exc)}</p>\n')
            continue
        out.append(f'<p class="note"><span class="mono">{_esc(row["reference"])}</span> · {_esc(describe(data))}</p>\n')
        out.append('<figure>' + render_svg(data, theme=theme, heading=False).rstrip('\n') + '</figure>\n')

    # Results overview.
    out.append(f'<h2>Results <span class="sum">{_plural(len(overview), "benchmark")}</span></h2>\n')
    out.append('<div class="wide"><table>\n<tr><th>benchmark</th><th class="n">subjects with results</th>'
               '<th class="n">with values here</th><th class="n">summary rows</th><th>results file</th></tr>\n')
    for item in overview:
        saved = 'differs' if item['differs_from_file'] else 'saved' if item['rows'] else 'none yet'
        out.append(f'<tr><td class="mono">{_esc(item["benchmark"])}</td><td class="n">{item["subjects_with_results"]}</td>'
                   f'<td class="n">{item["subjects_with_values"]}</td><td class="n">{item["rows"]}</td>'
                   f'<td>{saved}</td></tr>\n')
    out.append('</table></div>\n')

    # Definitions by kind.
    out.append(f'<h2>Definitions <span class="sum">{total}</span></h2>\n')
    by_kind = {}
    for row in rows:
        by_kind.setdefault(row['kind'], []).append(row)
    for kind in sorted(by_kind):
        items = by_kind[kind]
        out.append(f'<details><summary>{_esc(_PLURALS.get(kind, kind))} <span class="sum">{len(items)}</span></summary>\n'
                   '<div class="wide"><table>\n<tr><th>reference</th><th>title</th><th>state</th></tr>\n')
        for item in items:
            mark = ' (unsaved)' if item['unsaved'] else ''
            out.append(f'<tr><td class="mono">{_esc(item["reference"])}</td><td>{_esc(item["title"])}</td>'
                       f'<td>{_esc(_STATE_WORDS.get(item["state"], item["state"]) + mark)}</td></tr>\n')
        out.append('</table></div></details>\n')
    out.append('</main>\n</body>\n</html>\n')
    return ''.join(out)
