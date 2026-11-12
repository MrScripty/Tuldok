"""What the Map workspace reads: the map of a project, one note, and one recipe's results.

Owns section 2 of docs/plans/definition-first-projects/spec-w1.md. project_map
answers from the definitions, tuldok.json as last imported (store's state
row), the build and environment states and the summary rows, with the same
few queries however many recipes there are; it reads no file of the folder.
read_note reads one file under notes/ straight from the folder, the way
folder.py reads: through directory descriptors that refuse links, a
regular file of at most NOTE_LIMIT bytes, strict UTF-8; it opens no project.
recipe_results reads the summary rows of every benchmark subject made from
one recipe.
"""
import dataclasses
import os

from psycopg import sql

from . import builds, charts, documents, environments, folder as folder_reader, graph, result_rows, results
from .store import ProjectError, _REFERENCE_SQL

NOTE_LIMIT = 1024 * 1024
DESCRIPTION_LIMIT = 300   # characters of a recipe's description on the map (spec-w2.md section 2)


def _labels(document):
    labels = document.get('labels')
    return labels if isinstance(labels, dict) else {}


def _text(value):
    return value if isinstance(value, str) and value else None


def _description(document):
    """The first DESCRIPTION_LIMIT characters of a recipe's description, cut at a word; None when it has none.

    Whitespace runs become one space. A description longer than the limit is
    cut after the last whole word that fits and ends with an ellipsis (the
    ellipsis counts in the limit); a first word longer than the limit is cut
    at the limit.
    """
    text = ' '.join(document.get('description').split()) if isinstance(document.get('description'), str) else ''
    if len(text) <= DESCRIPTION_LIMIT:
        return text or None
    head = text[:DESCRIPTION_LIMIT]   # the ellipsis replaces the character after the last whole word
    cut = head.rfind(' ')
    return (head[:cut] if cut > 0 else head[:DESCRIPTION_LIMIT - 1]).rstrip(' ,;:') + '…'


def _better(metric, value, best):
    """True when value beats best by the metric's better (none counts as lower is better, as in charts)."""
    return best is None or (value > best if metric['better'] == 'higher' else value < best)


def _subject_recipes(benchmark):
    """{subject name: recipe reference} for the subjects of a benchmark document that name a recipe."""
    subjects = benchmark.get('subjects') if isinstance(benchmark.get('subjects'), list) else []
    return {item['name']: item['recipe'] for item in subjects
            if isinstance(item, dict) and isinstance(item.get('name'), str) and isinstance(item.get('recipe'), str)}


def _track(project, chart_reference, definitions):
    """(track, {recipe: (value, count)}) for map.chart, or (None, {}) when the chart is not a usable progression."""
    chart = definitions.get(chart_reference) if isinstance(chart_reference, str) else None
    chart = chart and chart['document']
    if not isinstance(chart, dict) or chart.get('form') != 'progression':
        return None, {}
    benchmark = definitions.get(chart.get('benchmark'))
    if benchmark is None:
        return None, {}
    statistic = chart.get('statistic', charts.DEFAULT_STATISTIC)
    if statistic not in results.STATISTICS:
        return None, {}
    metric = charts._metric(benchmark['document'], chart['metric'])
    name = chart['benchmark'].split('/', 1)[1]
    recipes = _subject_recipes(benchmark['document'])
    rows = project._connection.execute(
        sql.SQL("SELECT subject, count, {statistic} FROM {schema}.result_summaries "
                "WHERE benchmark = %s AND metric = %s AND grp = ''").format(
            statistic=sql.Identifier(statistic), schema=sql.Identifier(project.schema)),
        (name, metric['id'])).fetchall()
    values = {}
    for subject, count, value in sorted(rows, key=lambda row: row[0]):
        recipe = recipes.get(subject)
        if recipe is None or count <= 0 or value is None:
            continue
        if _better(metric, value, values.get(recipe, (None,))[0]):
            values[recipe] = (value, count)
    track = {'chart': chart_reference, 'benchmark': chart['benchmark'], 'metric': metric, 'statistic': statistic}
    return track, values


def project_map(project):
    """The map of an open project (spec-w1.md section 2): groups, models, edges, comparisons and the track."""
    rows = project._execute(f'SELECT {_REFERENCE_SQL}, kind, title, document FROM {{schema}}.definitions '
                            'WHERE NOT removed').fetchall()
    definitions = {reference: {'kind': kind, 'title': title, 'document': document}
                   for reference, kind, title, document in rows}
    documents_by_reference = {reference: item['document'] for reference, item in definitions.items()}
    state = project._state()
    tuldok = state['project'] or {}
    status = builds.status(project)
    local = {**environments.recorded_states(project._connection, project.schema),
             **{reference: entry['state'] for reference, entry in status.items()}}
    states = graph.states(documents_by_reference, local)

    map_block = tuldok.get('map') if isinstance(tuldok.get('map'), dict) else {}
    track, values = _track(project, map_block.get('chart'), definitions)

    subjects = {}  # (benchmark name, subject) -> recipe
    for reference, item in definitions.items():
        if item['kind'] == 'benchmark':
            for subject, recipe in _subject_recipes(item['document']).items():
                subjects[reference.split('/', 1)[1], subject] = recipe
    with_rows = {}
    for benchmark, subject in project._execute('SELECT DISTINCT benchmark, subject FROM {schema}.result_summaries'):
        recipe = subjects.get((benchmark, subject))
        if recipe is not None:
            with_rows.setdefault(recipe, set()).add(benchmark)

    recipes = sorted(reference for reference, item in definitions.items() if item['kind'] == 'recipe')
    models = []
    for reference in recipes:
        document = definitions[reference]['document']
        value, count = values.get(reference, (None, None))
        models.append({
            'reference': reference, 'title': definitions[reference]['title'],
            'description': _description(document), 'short': _text(_labels(document).get('short')),
            'group': _text(document.get('group')), 'change': _text(document.get('change')),
            'derived_from': _text(document.get('derived_from')),
            'trained_at': _text(_labels(document).get('trained_at')),
            'state': states[reference], 'adopted': bool((status.get(reference) or {}).get('adopted')),
            'card': _text(document.get('card')), 'value': value, 'count': count,
            'benchmarks': len(with_rows.get(reference, ())),
        })
    models.sort(key=lambda model: (model['trained_at'] is None, model['trained_at'] or '', model['reference']))

    recipe_documents = {reference: definitions[reference]['document'] for reference in recipes}
    edges = []
    for edge in graph.edges(recipe_documents):
        if edge.to_ref not in recipe_documents:
            continue
        kind = 'derived' if edge.role == 'derived' else 'input' if edge.role.startswith('input:') else None
        if kind is not None and {'from': edge.from_ref, 'to': edge.to_ref, 'kind': kind} not in edges:
            edges.append({'from': edge.from_ref, 'to': edge.to_ref, 'kind': kind})

    comparisons = []
    for reference in recipes:
        compared = recipe_documents[reference].get('compared_with')
        for item in compared if isinstance(compared, list) else []:
            if isinstance(item, dict) and isinstance(item.get('recipe'), str):
                comparisons.append({'from': reference, 'to': item['recipe'], 'explanation': item.get('explanation'),
                                    'excerpt': item.get('excerpt')})

    counts = {}
    for model in models:
        if model['group'] is not None:
            counts[model['group']] = counts.get(model['group'], 0) + 1
    groups = [{'id': group['id'], 'title': group['title'], 'parent': group.get('parent'),
               'description': group.get('description'), 'models': counts.get(group['id'], 0)}
              for group in tuldok.get('groups', []) if isinstance(group, dict)]
    return {'groups': groups, 'models': models, 'edges': edges, 'comparisons': comparisons, 'track': track}


def read_note(folder, path):
    """{path, text} of notes/<path> in the folder on disk; ProjectError not-found for anything else.

    path is relative to notes/ and in normal form. Every directory on the
    way and the file itself are opened without following a link; the file
    must be regular, at most NOTE_LIMIT bytes and UTF-8.
    """
    def refused(why):
        return ProjectError(f'There is no note {path!r}: {why}', 'not-found', references=[str(path)])

    wrong = documents.relative_path_problem(path)
    if wrong:
        raise refused(f'the path {wrong}.')
    *directories, name = path.split('/')
    try:
        fd = os.open(os.fspath(folder), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as exc:
        raise refused(f'the project folder cannot be opened ({exc.strerror}).') from None
    try:
        for part in (folder_reader.NOTES, *directories):
            try:
                child = os.open(part, folder_reader.DIRECTORY_FLAGS, dir_fd=fd)
            except OSError:
                raise refused(f'{part} is not a directory of the folder (a link is not followed).') from None
            os.close(fd)
            fd = child
        try:
            raw = folder_reader.read(fd, name, NOTE_LIMIT)
        except folder_reader.Unsafe as exc:
            raise refused(str(exc)) from None
    finally:
        os.close(fd)
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise refused(f'the file is not UTF-8 text (bad byte at offset {exc.start}).') from None
    return {'path': path, 'text': text}


def recipe_results(project, recipe, group=None):
    """{rows, benchmarks}: the summary rows of every benchmark subject made from recipe (spec-w1.md section 2).

    group None means the ungrouped rows only; a key, the rows grouped by that
    one key (as the results operation reads it). benchmarks names the
    benchmarks with a subject made from recipe, whether or not it has rows.
    """
    parsed = documents.parse_reference(recipe)
    found = project._execute("SELECT 1 FROM {schema}.definitions WHERE directory = 'recipes' AND name = %s "
                             'AND NOT removed', (parsed[1],)).fetchone() if parsed and parsed[0] == 'recipes' else None
    if found is None:
        raise ProjectError(f'There is no recipe {recipe}.', 'not-found', references=[recipe])
    pairs = []
    for name, document in project._execute("SELECT name, document FROM {schema}.definitions "
                                           "WHERE directory = 'benchmarks' AND NOT removed ORDER BY name"):
        pairs += [(name, subject) for subject, used in sorted(_subject_recipes(document).items()) if used == recipe]
    where, parameters = ['(benchmark, subject) IN (SELECT * FROM unnest(%s::text[], %s::text[]))'], \
        [[benchmark for benchmark, _ in pairs], [subject for _, subject in pairs]]
    if group is None or group == '':
        where.append("grp = ''")
    else:
        where.append("left(grp, length(%s) + 1) = %s || '=' AND strpos(grp, ';') = 0")
        parameters += [group, group]
    query = (result_rows._SELECT_SUMMARY.replace('SELECT ', 'SELECT benchmark, ', 1) + ' WHERE ' + ' AND '.join(where)
             + ' ORDER BY benchmark COLLATE "C", subject COLLATE "C", metric COLLATE "C", grp COLLATE "C"')
    rows = []
    for record in project._execute(query, parameters):
        stored = result_rows._stored(record[1:])
        rows.append({'benchmark': record[0], **dataclasses.asdict(stored.row), 'origin': stored.origin})
    return {'rows': rows, 'benchmarks': sorted({benchmark for benchmark, _ in pairs})}
