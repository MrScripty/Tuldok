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
draft_branch (spec-w3.md section 2) writes the text of a new recipe branched
from one of the project's, names it, and says what set_definition would say
of it, storing nothing. Its settings file, when it has one, is read from the
code root as it is on disk, never through a link that leaves the code root.
The map also says which models have unsaved edits and, for a model with no
trained_at label, when the run of its current product finished.
"""
import copy
import dataclasses
import datetime
import json
import os
import re

from psycopg import sql

from . import builds, charts, documents, environments, folder as folder_reader, graph, result_rows, results
from .store import ProjectError, _REFERENCE_SQL

NOTE_LIMIT = 1024 * 1024
DESCRIPTION_LIMIT = 300   # characters of a recipe's description on the map (spec-w2.md section 2)
SETTINGS_LIMIT = 256 * 1024   # bytes of a settings file a branch carries as its own settings (spec-w3.md section 2)
SLUG_LENGTH = 80              # characters of a branch's name made from its title, before any -2, -3, ...
_NOT_SLUG = re.compile(r'[^a-z0-9]+')
_INDENT = re.compile(r'\n([ \t]+)\S')


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


def _product_finish_times(project):
    """{reference: when the run that made its current product finished, as ISO 8601 text in UTC}, one query.

    A product that was adopted, or whose run has no finish time, is left out.
    """
    found = {}
    for reference, finished_at, state in project._execute(
            "SELECT p.reference, r.finished_at, r.state FROM {schema}.products p "
            "JOIN {schema}.runs r ON r.id = p.run_id WHERE p.current AND p.subject = ''"):
        if finished_at is not None and state != builds.ADOPTED:
            found[reference] = finished_at.astimezone(datetime.timezone.utc).isoformat()
    return found


def project_map(project):
    """The map of an open project (spec-w1.md section 2): groups, models, edges, comparisons and the track.

    Each model also says whether it is unsaved, and its trained_at falls back
    to its current product's finish time (spec-w3.md section 2).
    """
    rows = project._execute(f'SELECT {_REFERENCE_SQL}, kind, title, document, unsaved FROM {{schema}}.definitions '
                            'WHERE NOT removed').fetchall()
    definitions = {reference: {'kind': kind, 'title': title, 'document': document, 'unsaved': unsaved}
                   for reference, kind, title, document, unsaved in rows}
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

    finished = _product_finish_times(project)

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
            'trained_at': _text(_labels(document).get('trained_at')) or finished.get(reference),
            'state': states[reference], 'unsaved': definitions[reference]['unsaved'],
            'adopted': bool((status.get(reference) or {}).get('adopted')),
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


# ------------------------------------------------------------ branching

def _branch_name(title, taken):
    """A free name from title: lowercase, each run outside [a-z0-9] one '-', trimmed, then -2, -3, ... when taken."""
    base = _NOT_SLUG.sub('-', title.lower()).strip('-')[:SLUG_LENGTH].strip('-') or 'recipe'
    name, number = base, 1
    while name in taken:
        number += 1
        name = f'{base}-{number}'
    return name


def _indent(text):
    """The indentation of the first indented line of a definition's text; two spaces when it has none."""
    match = _INDENT.search(text)
    return match.group(1) if match else '  '


def _settings_object(code_root, path):
    """The JSON object in the settings file path under code_root, or None when it cannot be carried.

    The file is read as it is on disk: its real path must stay inside the
    code root (a link inside the code root is followed, one out of it is
    not), it must be a regular file of at most SETTINGS_LIMIT bytes, and it
    must hold one strict JSON object.
    """
    if documents.relative_path_problem(path) or not os.path.isdir(code_root):
        return None
    target = os.path.realpath(os.path.join(code_root, path))
    if os.path.commonpath([code_root, target]) != code_root or target == code_root:
        return None
    try:
        fd = os.open(os.path.dirname(target), folder_reader.DIRECTORY_FLAGS)
    except OSError:
        return None
    try:
        raw = folder_reader.read(fd, os.path.basename(target), SETTINGS_LIMIT)
        return documents.decode(raw)
    except (folder_reader.Unsafe, documents.DocumentError):
        return None
    finally:
        os.close(fd)


def draft_branch(project, recipe, title, *, name=None, change=None, description=None):
    """{reference, text, parent, inlined, problems}: a new recipe branched from recipe, stored nowhere (spec-w3.md).

    The text carries the parent's model, group and run, its kind of change
    unless change is given, and derived_from naming the parent; not its card,
    labels, earlier_work or comparisons. A run whose settings_file is a JSON
    object under the code root carries it as settings, and inlined names the
    file. problems are the errors and warnings set_definition would find in
    the text at reference, as dicts. Raises ProjectError not-found for a
    recipe that is not one of the project's, and invalid for a name that
    breaks the name rule or is taken (a removed definition's name included).
    """
    parsed = documents.parse_reference(recipe)
    row = project._execute("SELECT text FROM {schema}.definitions WHERE directory = 'recipes' "
                           'AND name = %s AND NOT removed', (parsed[1],)).fetchone() \
        if parsed and parsed[0] == 'recipes' else None
    if row is None:
        raise ProjectError(f'There is no recipe {recipe} to branch from.', 'not-found', references=[recipe])
    parent_text = row[0]
    parent = documents.decode(parent_text)   # from the text, not the jsonb column, to keep the order of its keys
    taken = {taken_name for (taken_name,) in project._execute(
        "SELECT name FROM {schema}.definitions WHERE directory = 'recipes'")}
    if name is not None:
        if not documents.is_name(name):
            raise ProjectError(f'{name!r} is not a name: use 1 to 120 lowercase letters, digits, ".", "_" or "-", '
                               'starting with a letter or digit.', 'invalid', references=[f'recipes/{name}'])
        if name in taken:
            raise ProjectError(f'recipes/{name} is taken (a removed definition keeps its name until the project '
                               'is saved); choose another name.', 'invalid', references=[f'recipes/{name}'])
    else:
        name = _branch_name(title, taken)
    reference = documents.reference('recipes', name)

    document = {'format': parent['format'], 'kind': 'recipe', 'title': title}
    if description is not None:
        document['description'] = description
    for field in ('model', 'group'):
        if field in parent:
            document[field] = parent[field]
    if change is not None or 'change' in parent:
        document['change'] = change if change is not None else parent['change']
    document['derived_from'] = recipe
    inlined = None
    if isinstance(parent.get('run'), dict):
        run = copy.deepcopy(parent['run'])
        path = run.get('settings_file')
        if isinstance(path, str) and 'settings' not in run:
            state = project._state()
            settings = _settings_object(os.path.realpath(os.path.join(state['folder'], state['code_root'])), path)
            if settings is not None:
                run = {('settings' if key == 'settings_file' else key): (settings if key == 'settings_file' else value)
                       for key, value in run.items()}
                inlined = path
        document['run'] = run
    text = json.dumps(document, indent=_indent(parent_text), ensure_ascii=False) + '\n'
    problems = project.definition_problems(reference, text)
    return {'reference': reference, 'text': text, 'parent': recipe, 'inlined': inlined,
            'problems': [problem.as_dict() for problem in problems]}
