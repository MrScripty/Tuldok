"""Comparing chosen models: what differs between recipes, intervals from per-case values, parallel coordinates.

Owns sections 1 to 4 of docs/plans/training-and-curation/spec-t3.md. Nothing
here opens a file or runs anything of a project: the inputs are the
definitions, the summary rows and the per-case values a project holds. Each
operation is two halves: gather_* reads what it needs from an open Project
(under the service's lock), and the function of the same name without the
prefix computes the answer from what was gathered (outside it), so a long
resampling holds up no other call. Standard library only.

The bootstrap is a percentile bootstrap with one fixed seed: every interval
starts a fresh random.Random(SEED), so an answer is the same on every reading
and a test can repeat the arithmetic.
"""
import collections
import json
import math
import random
import re
import threading

from . import charts, documents, results
from .store import ProjectError

RESAMPLES = 2000
LEVEL = 0.95
SEED = 20261119
MIN_VALUES = 2              # values a subject needs for an interval
LEAVES = 5000               # leaves of one flattened document
DEPTH = 32                  # levels of one flattened document
SHOWN = 200                 # characters of a text value shown
DIFFERS = 400               # differing paths answered
CATEGORIES = 12             # distinct values of a category axis at most
SETTINGS = 48               # setting axes answered at most
KEPT = 8                    # benchmarks whose intervals are kept
STATISTICS = results.STATISTICS

# Keys of a definition that say who a model is, not how it is made (left out of the comparison).
IDENTITY = ('format', 'kind', 'title', 'description', 'card', 'labels', 'earlier_work', 'compared_with', 'sweep')
# Keys compared on rows of their own, first.
_OWN_ROWS = {'group': 'group', 'change': 'change', 'derived_from': 'parent'}
_KIND_ORDER = {'group': 0, 'change': 1, 'parent': 2, 'data': 3, 'setting': 4, 'code': 5}
_CODE = ('run.command', 'run.sources')   # the code a run ran: compared, never an axis
_QUOTED = re.compile(r'[.\[\]" ]')


# ================================================================ flattening

def _part(path, key):
    if key and not _QUOTED.search(key):
        return f'{path}.{key}' if path else key
    return f'{path}[{json.dumps(key)}]'


def flatten(document, *, leaves=LEAVES, depth=DEPTH):
    """(leaves, truncated): {path: leaf} of a definition's document, its identity keys left out (section 1).

    A leaf is None, a boolean, a number, a string, or an empty object or list.
    Past `leaves` leaves or `depth` levels the rest is left out and truncated
    is True.
    """
    out, truncated = {}, False

    def walk(value, path, level):
        nonlocal truncated
        if len(out) >= leaves:
            truncated = True
            return
        if isinstance(value, (dict, list)) and value:
            if level >= depth:
                truncated = True
                return
            items = value.items() if isinstance(value, dict) else enumerate(value)
            for key, item in items:
                walk(item, _part(path, str(key)) if isinstance(value, dict) else f'{path}[{key}]', level + 1)
        else:
            out[path] = value

    if isinstance(document, dict):
        for key, value in document.items():
            if key not in IDENTITY:
                walk(value, _part('', str(key)), 1)
    return out, truncated


def kind_of(path):
    """group, change, parent, data (under run.inputs), code (run.command, run.sources) or setting."""
    if path in _OWN_ROWS:
        return _OWN_ROWS[path]
    if path == 'run.inputs' or path.startswith(('run.inputs.', 'run.inputs[')):
        return 'data'
    if any(path == code or path.startswith((code + '.', code + '[')) for code in _CODE):
        return 'code'
    return 'setting'


def _canon(value):
    """A value as it is compared: numbers by value (1 is 1.0), booleans apart from numbers."""
    if isinstance(value, bool):
        return ('b', value)
    if isinstance(value, (int, float)):
        return ('n', float(value))
    if isinstance(value, str):
        return ('s', value)
    if value is None:
        return ('z',)
    return ('j', json.dumps(value, sort_keys=True))


def _natural(path):
    return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.split(r'(\d+)', path) if part]


def _shown(value):
    return value[:SHOWN - 1] + '…' if isinstance(value, str) and len(value) > SHOWN else value


def differences(documents_, *, most=DIFFERS, leaves=LEAVES, depth=DEPTH):
    """{differs, same, more, truncated} of two or more definitions' documents (section 1)."""
    flats = [flatten(document, leaves=leaves, depth=depth) for document in documents_]
    paths = set().union(*(flat for flat, _ in flats))
    differ, same = [], 0
    for path in paths:
        present = [path in flat for flat, _ in flats]
        canon = {_canon(flat[path]) for flat, _ in flats if path in flat}
        if all(present) and len(canon) == 1:
            same += 1
        else:
            differ.append(path)
    differ.sort(key=lambda path: (_KIND_ORDER[kind_of(path)], _natural(path)))
    rows = [{'kind': kind_of(path), 'path': path, 'values': [_shown(flat.get(path)) for flat, _ in flats],
             'present': [path in flat for flat, _ in flats]} for path in differ[:most]]
    return {'differs': rows, 'same': same, 'more': max(0, len(differ) - most),
            'truncated': [truncated for _, truncated in flats]}


# ================================================================ intervals

def _quantile(ordered, q):
    """Linear interpolation at q × (count − 1) of sorted numbers."""
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    if lower >= len(ordered) - 1:
        return ordered[-1]
    return ordered[lower] + (ordered[lower + 1] - ordered[lower]) * (position - lower)


def statistic(ordered, name):
    """One statistic of sorted numbers, as results.summarise computes it."""
    if name == 'mean':
        return math.fsum(ordered) / len(ordered)
    if name == 'min':
        return ordered[0]
    if name == 'max':
        return ordered[-1]
    return results._percentile(ordered, {'median': 5, 'p10': 1, 'p90': 9}[name])


def _ends(draws):
    ordered = sorted(draws)
    return [_quantile(ordered, (1 - LEVEL) / 2), _quantile(ordered, 1 - (1 - LEVEL) / 2)]


def interval_set(values, statistics=STATISTICS, *, resamples=RESAMPLES):
    """{statistic: [low, high]} of a percentile bootstrap of values (section 2); None under MIN_VALUES values."""
    ordered = sorted(float(value) for value in values)
    if len(ordered) < MIN_VALUES:
        return None
    rng, n = random.Random(SEED), len(ordered)
    draws = {name: [] for name in statistics}
    for _ in range(resamples):
        sample = sorted(rng.choices(ordered, k=n))
        for name in statistics:
            draws[name].append(statistic(sample, name))
    return {name: _ends(draws[name]) for name in statistics}


def difference(first, second, name, *, resamples=RESAMPLES):
    """The interval of statistic(first) − statistic(second), first and second {case key: value} (section 2).

    {low, high, paired, count, significant}; None when either has fewer than MIN_VALUES values.
    """
    if len(first) < MIN_VALUES or len(second) < MIN_VALUES:
        return None
    rng, draws = random.Random(SEED), []
    shared = sorted(set(first) & set(second))
    if len(shared) >= MIN_VALUES:
        a, b, m = [float(first[key]) for key in shared], [float(second[key]) for key in shared], len(shared)
        positions = range(m)
        for _ in range(resamples):
            drawn = rng.choices(positions, k=m)
            draws.append(statistic(sorted(a[i] for i in drawn), name) - statistic(sorted(b[i] for i in drawn), name))
        paired, count = True, m
    else:
        a, b = sorted(map(float, first.values())), sorted(map(float, second.values()))
        for _ in range(resamples):
            draws.append(statistic(sorted(rng.choices(a, k=len(a))), name)
                         - statistic(sorted(rng.choices(b, k=len(b))), name))
        paired, count = False, min(len(a), len(b))
    low, high = _ends(draws)
    return {'low': low, 'high': high, 'paired': paired, 'count': count, 'significant': low > 0 or high < 0}


# ================================================================ gathering (the project open)

def _rows(project, template, parameters=None):
    return project._execute(template, parameters).fetchall()


def _benchmark_document(project, name):
    document = charts._document(project, 'benchmarks', name)
    if document is None:
        raise ProjectError(f'There is no benchmark benchmarks/{name}.', 'not-found', references=[f'benchmarks/{name}'])
    return document


def _bare(text):
    return text[len('benchmarks/'):] if isinstance(text, str) and text.startswith('benchmarks/') else text


def _held_values(project, benchmark, subjects=None):
    """{(subject, metric): {(case, group): value}} of the numbers held for a benchmark."""
    query = ('SELECT subject, metric, case_id, grp, value FROM {schema}.result_values '
             'WHERE benchmark = %s AND value IS NOT NULL')
    parameters = [benchmark]
    if subjects is not None:
        query += ' AND subject = ANY(%s)'
        parameters.append(sorted(subjects))
    held = collections.defaultdict(dict)
    for subject, metric, case, group, value in _rows(project, query + ' ORDER BY 1, 2, 3, 4', parameters):
        held[subject, metric][case, group] = value
    return dict(held)


def _tradeoff_charts(project, benchmark):
    """The data of each tradeoff chart of a benchmark, by reference order."""
    found = []
    for name, document in _rows(project, "SELECT name, document FROM {schema}.definitions "
                                         "WHERE directory = 'charts' AND NOT removed ORDER BY name"):
        if not isinstance(document, dict) or document.get('form') != 'tradeoff':
            continue
        if documents.parse_reference(document.get('benchmark')) != ('benchmarks', benchmark):
            continue
        try:
            found.append(charts.chart_data(project, f'charts/{name}'))
        except ProjectError:
            continue   # a chart whose metric the benchmark lacks: listed nowhere here
    return found


def _recipe_documents(project, references):
    names = sorted({reference.split('/', 1)[1] for reference in references
                    if isinstance(reference, str) and reference.startswith('recipes/')})
    if not names:
        return {}
    return {f'recipes/{name}': document for name, document in _rows(
        project, "SELECT name, document FROM {schema}.definitions WHERE directory = 'recipes' AND NOT removed "
                 'AND name = ANY(%s)', (names,))}


def _summaries(project, benchmark, subjects=None):
    """{(subject, metric): SummaryRow-with-origin} of the rows over all cases."""
    out = {}
    for stored in project.result_summaries(benchmark, group=''):
        if subjects is None or stored.row.subject in subjects:
            out[stored.row.subject, stored.row.metric] = stored
    return out


def _metrics(document):
    return [{'id': item['id'], 'title': item.get('title', item['id']), 'units': item.get('units'),
             'better': item.get('better', 'none')} for item in document.get('metrics', []) if isinstance(item, dict)]


def gather_intervals(project, benchmark):
    """What intervals() needs: the held values of a benchmark and its tradeoff charts."""
    name = _bare(benchmark)
    _benchmark_document(project, name)
    return {'benchmark': name, 'held': _held_values(project, name), 'charts': _tradeoff_charts(project, name)}


def gather_compare(project, recipes):
    """What model_compare() needs: the recipes' documents and, per benchmark that measures one, its rows."""
    if len(set(recipes)) != len(recipes):
        raise ProjectError('Each recipe may be named once.', 'invalid')
    found = _recipe_documents(project, recipes)
    missing = [reference for reference in recipes if reference not in found]
    if missing:
        raise ProjectError(f'There is no recipe {missing[0]}.', 'not-found', references=missing)
    wanted, benchmarks = set(recipes), []
    for name, document in _rows(project, "SELECT name, document FROM {schema}.definitions "
                                         "WHERE directory = 'benchmarks' AND NOT removed ORDER BY name"):
        subjects = [item for item in (document or {}).get('subjects', []) if isinstance(item, dict)]
        made = {}
        for item in subjects:
            if item.get('recipe') in wanted and item.get('recipe') not in made:
                made[item['recipe']] = item
        if not made:
            continue
        benchmarks.append({'benchmark': name, 'title': (document or {}).get('title', name),
                           'metrics': _metrics(document),
                           'made': made, 'summaries': _summaries(project, name),
                           'held': _held_values(project, name), 'charts': _tradeoff_charts(project, name)})
    return {'recipes': list(recipes), 'documents': [found[reference] for reference in recipes],
            'benchmarks': benchmarks}


def gather_axes(project, benchmark):
    """What benchmark_axes() needs: the benchmark, its summary rows and its subjects' recipes."""
    name = _bare(benchmark)
    document = _benchmark_document(project, name)
    subjects = [item for item in document.get('subjects', []) if isinstance(item, dict) and 'name' in item]
    return {'benchmark': name, 'metrics': _metrics(document), 'subjects': subjects,
            'summaries': _summaries(project, name),
            'recipes': _recipe_documents(project, [item.get('recipe') for item in subjects])}


# ================================================================ answers

_kept = collections.OrderedDict()
_kept_lock = threading.Lock()


def _frontier_pairs(chart, held, touching=None):
    """The neighbour pairs of an ungrouped tradeoff chart's frontier, compared on both metrics (section 2)."""
    if chart.get('group'):
        return []
    points = [point for series in chart.get('series', []) for point in series['points'] if point.get('frontier')]
    pairs, name = [], chart['statistic']
    for a, b in zip(points, points[1:]):
        if touching is not None and not ({a['subject'], b['subject']} & touching):
            continue
        both = {}
        for key, metric in (('metric', chart['metric']), ('metric_x', chart['metric_x'])):
            first, second = held.get((a['subject'], metric['id'])), held.get((b['subject'], metric['id']))
            both[key] = difference(first, second, name) if first and second else None
        separated = None if both['metric'] is None or both['metric_x'] is None else (
            both['metric']['significant'] and both['metric_x']['significant'])
        pairs.append({'subjects': [a['subject'], b['subject']], **both, 'separated': separated})
    return pairs


def _chart_head(chart):
    return {'chart': chart['chart'], 'title': chart['title'], 'statistic': chart['statistic'],
            'metric': chart['metric'], 'metric_x': chart['metric_x'], 'grouped': bool(chart.get('group'))}


def intervals(gathered):
    """The answer of the intervals operation (section 4) for what gather_intervals read; kept while it is the same."""
    key = gathered['benchmark']
    with _kept_lock:
        if key in _kept and _kept[key][0] == gathered:
            _kept.move_to_end(key)
            return _kept[key][1]
    held = gathered['held']
    rows = []
    for (subject, metric), values in sorted(held.items()):
        ends = interval_set(values.values())
        rows.append({'subject': subject, 'metric': metric, 'count': len(values),
                     **{name: (ends[name] if ends else None) for name in STATISTICS}})
    frontiers = []
    for chart in gathered['charts']:
        pairs = _frontier_pairs(chart, held)
        apart = sorted({subject for pair in pairs if pair['separated'] is False for subject in pair['subjects']})
        frontiers.append({**_chart_head(chart), 'pairs': pairs, 'not_separated': apart})
    answer = {'benchmark': key, 'resamples': RESAMPLES, 'level': LEVEL, 'seed': SEED, 'intervals': rows,
              'frontiers': frontiers}
    with _kept_lock:
        _kept[key] = (gathered, answer)
        while len(_kept) > KEPT:
            _kept.popitem(last=False)
    return answer


def model_compare(gathered, statistic_name='median'):
    """The answer of model_compare (section 4) for what gather_compare read."""
    recipes, docs = gathered['recipes'], gathered['documents']
    models = []
    for reference, document in zip(recipes, docs):
        models.append({'reference': reference, 'title': document.get('title', reference),
                       'group': document.get('group'), 'change': document.get('change'),
                       'derived_from': document.get('derived_from'), 'truncated': flatten(document)[1]})
    diff = differences(docs)
    benchmarks = []
    for bench in gathered['benchmarks']:
        columns = []
        for reference in recipes:
            item = bench['made'].get(reference)
            if item is None:
                columns.append(None)
                continue
            subject, values = item['name'], {}
            per_case = False
            for metric in bench['metrics']:
                stored = bench['summaries'].get((subject, metric['id']))
                cases = bench['held'].get((subject, metric['id']))
                ends = interval_set(cases.values(), (statistic_name,)) if cases else None
                per_case = per_case or (stored is not None and stored.origin == 'values')
                row = stored.row if stored is not None else None
                values[metric['id']] = {'value': getattr(row, statistic_name) if row and row.count > 0 else None,
                                        'count': row.count if row else None,
                                        'low': ends[statistic_name][0] if ends else None,
                                        'high': ends[statistic_name][1] if ends else None}
            columns.append({'subject': subject, 'title': item.get('title') or subject, 'per_case': per_case,
                            'values': values})
        mine = {column['subject'] for column in columns if column}
        frontiers = []
        for chart in bench['charts']:
            points = {point['subject']: point for series in chart.get('series', []) for point in series['points']}
            pairs = _frontier_pairs(chart, bench['held'], touching=mine)
            rows = []
            for column in columns:
                point = points.get(column['subject']) if column else None
                if point is None:
                    rows.append(None)
                    continue
                apart = sorted({other for pair in pairs if pair['separated'] is False and column['subject'] in
                                pair['subjects'] for other in pair['subjects'] if other != column['subject']})
                rows.append({'on': bool(point.get('frontier')), 'x': point.get('x'), 'value': point.get('value'),
                             'not_separated_from': apart})
            frontiers.append({**_chart_head(chart), 'models': rows})
        benchmarks.append({'benchmark': bench['benchmark'], 'title': bench['title'], 'metrics': bench['metrics'],
                           'models': columns, 'frontiers': frontiers})
    return {'statistic': statistic_name, 'resamples': RESAMPLES, 'level': LEVEL, 'seed': SEED, 'models': models,
            'differs': diff['differs'], 'same': diff['same'], 'more': diff['more'], 'benchmarks': benchmarks}


def _ranks(values):
    """Ranks from 1, ties given their mean rank."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1
        start = end + 1
    return ranks


def spearman(xs, ys):
    """The Spearman rank correlation of two equal lists; None under three pairs or when either is constant."""
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = math.fsum(rx) / len(rx), math.fsum(ry) / len(ry)
    sxy = math.fsum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx, syy = math.fsum((a - mx) ** 2 for a in rx), math.fsum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _category_order(canon):
    """Categories in order: numbers by value, then false and true, then texts, then null and the rest."""
    tag = canon[0]
    if tag == 'n':
        return (0, canon[1], '')
    if tag == 'b':
        return (1, int(canon[1]), '')
    if tag == 's':
        return (2, 0, canon[1])
    return (3, 0, canon[-1] if len(canon) > 1 else '')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def benchmark_axes(gathered, statistic_name='median', *, most=SETTINGS):
    """The answer of benchmark_axes (section 3) for what gather_axes read."""
    subjects = gathered['subjects']
    metric_values = {}
    metrics = []
    for metric in gathered['metrics']:
        values = {}
        for item in subjects:
            stored = gathered['summaries'].get((item['name'], metric['id']))
            number = getattr(stored.row, statistic_name) if stored is not None and stored.row.count > 0 else None
            if number is not None:
                values[item['name']] = number
        metric_values[metric['id']] = values
        found = list(values.values())
        metrics.append({**metric, 'positive': bool(found) and all(v > 0 for v in found),
                        'low': min(found) if found else None, 'high': max(found) if found else None})
    by_path = collections.defaultdict(dict)
    for item in subjects:
        document = gathered['recipes'].get(item.get('recipe'))
        if isinstance(document, dict):
            for path, value in flatten(document)[0].items():
                by_path[path][item['name']] = value
    leading = next((values for values in metric_values.values() if len(values) >= 3), None)
    candidates = []
    for path, values in by_path.items():
        if kind_of(path) == 'code' or len(values) < 2 or len({_canon(value) for value in values.values()}) < 2:
            continue
        if all(_number(value) for value in values.values()):
            axis = {'path': path, 'kind': 'number', 'categories': None,
                    'low': min(values.values()), 'high': max(values.values())}
            positions = {name: value for name, value in values.items()}
        else:
            kinds = sorted({_canon(value) for value in values.values()}, key=_category_order)
            if len(kinds) > CATEGORIES:
                continue
            first = {}
            for value in values.values():
                first.setdefault(_canon(value), value)
            axis = {'path': path, 'kind': 'category', 'categories': [_shown(first[kind]) for kind in kinds],
                    'low': 0, 'high': len(kinds) - 1}
            positions = {name: kinds.index(_canon(value)) for name, value in values.items()}
        axis['count'] = len(values)
        axis['distinct'] = len({_canon(value) for value in values.values()})
        if leading is not None:
            both = [name for name in positions if name in leading]
            axis['association'] = spearman([positions[name] for name in both], [leading[name] for name in both])
            weight = abs(axis['association'] or 0) * len(both) / max(1, len(leading))
        else:
            axis['association'], weight = None, 0
        candidates.append((axis, positions, weight))
    # The strongest association first, weighed by the share of the measured subjects it is made over, so a path
    # that six of 150 subjects have does not lead on a chance correlation (spec-t3, as built).
    candidates.sort(key=lambda item: (item[0]['association'] is None, -item[2], -item[0]['count'],
                                      _natural(item[0]['path'])))
    candidates = [(axis, positions) for axis, positions, _ in candidates]
    chosen = candidates[:most]
    rows = []
    for item in subjects:
        rows.append({'subject': item['name'], 'title': item.get('title') or item['name'], 'recipe': item.get('recipe'),
                     'metrics': {metric['id']: metric_values[metric['id']].get(item['name']) for metric in metrics},
                     'settings': {axis['path']: positions.get(item['name']) for axis, positions in chosen}})
    return {'benchmark': gathered['benchmark'], 'statistic': statistic_name, 'metrics': metrics,
            'settings': [axis for axis, _ in chosen], 'left_out': max(0, len(candidates) - most), 'subjects': rows}
