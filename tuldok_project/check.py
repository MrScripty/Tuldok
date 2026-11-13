"""The project folder checker: every rule of the format, applied to one folder, every problem reported.

Owns the order in which sections 2.1 to 2.9 of
docs/plans/definition-first-projects/spec-m1-m2.md are applied and the rules
that are neither layout (folder.py), single-field syntax (documents.py and the
schemas) nor summary-file content (results.py): kind against directory, cards,
placeholders in context, benchmark uniqueness rules, references and named
outputs, charts against their benchmark, cycles, paths into the code root
(in definitions and in the code_paths of tuldok.json), and the map's fields
(spec-w1.md section 1): groups, a recipe's group, derived_from and
compared_with, and map.chart.
Problems are collected, never raised, so one bad file never hides another.
"""
from dataclasses import dataclass, field
import os

from . import documents, folder as folder_reader, graph, results
from .documents import Problem

_SEVERITY_ORDER = {'error': 0, 'warning': 1}


@dataclass
class Report:
    """The outcome of check_folder.

    project is the decoded tuldok.json (or None), definitions maps each
    reference to its folder.Definition, edges is graph.edges() over them.
    """
    folder: str
    problems: list = field(default_factory=list)
    project: dict | None = None
    definitions: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)

    @property
    def ok(self):
        return not any(problem.severity == 'error' for problem in self.problems)

    def count(self, severity):
        return sum(1 for problem in self.problems if problem.severity == severity)


def check_folder(folder, *, code=True):
    """Check the project folder at `folder`; with code=False, paths into the code root are not looked up."""
    read = folder_reader.read_folder(folder)
    problems = list(read.problems)

    def add(severity, path, pointer, message):
        problems.append(Problem(severity, path, pointer, message))

    project = read.project.document if read.project is not None else None
    if project is not None:
        for pointer, message in documents.schema_problems('project', project):
            add('error', folder_reader.PROJECT_FILE, pointer, message)

    definitions = {definition.reference: definition for definition in read.definitions}
    for definition in read.definitions:
        if definition.document is not None:
            check_definition(definition, read.notes, add)

    # Single-file errors so far decide which benchmarks are sound enough to check results against.
    unsound = {problem.path for problem in problems if problem.severity == 'error'}

    code_root = _code_root(project, read.root, add) if code and project is not None else None
    if project is not None:
        check_project_code_paths(project, code_root, add)
    for definition in read.definitions:
        if definition.document is not None:
            check_code_paths(definition, code_root, add)

    check_references(definitions, add)
    check_charts(definitions, unsound, add)
    check_cycles(definitions, add)
    check_map(project, definitions, add)
    _check_results(read.results, definitions, unsound, add)

    problems.sort(key=lambda p: (p.path, p.pointer, _SEVERITY_ORDER.get(p.severity, 2), p.message))
    decoded = {reference: d.document for reference, d in definitions.items() if d.document is not None}
    return Report(read.root, problems, project, definitions, graph.edges(decoded))


# ------------------------------------------------------- one definition

def check_definition(definition, notes, add):
    """Report the single-file rules of one decoded definition: schema, kind, card, placeholders, benchmark rules."""
    document, path = definition.document, definition.path
    for pointer, message in documents.schema_problems(definition.kind, document):
        add('error', path, pointer, message)

    kind = document.get('kind')
    if kind in documents.DIRECTORIES and kind != definition.kind:
        add('error', path, '/kind',
            f'The kind is {kind!r} but the file is in {definition.directory}/; '
            f'move it to {documents.DIRECTORIES[kind]}/ or change kind to {definition.kind!r}.')

    card = document.get('card')
    if isinstance(card, str) and card.startswith('notes/'):
        wrong = documents.relative_path_problem(card)
        if wrong:
            add('error', path, '/card', f'The card path {card!r} {wrong}.')
        elif card not in notes:
            add('error', path, '/card', f'The card {card} does not exist; add the file or fix the path.')

    run = document.get('run')
    if isinstance(run, dict):
        _check_run(run, path, benchmark=definition.kind == 'benchmark', add=add)
    if definition.kind == 'benchmark':
        _check_benchmark(document, path, add)
    if definition.kind == 'dataset' and isinstance(document.get('view'), dict):
        _check_view(document['view'], path, add)


def _check_view(view, path, add):
    """The addresses of a dataset's view: a record list's at most two '!', a pattern's at most one."""
    from . import inside_archive  # here: inside_archive imports store, which imports this module
    for key, archives in (('records', 2), ('files', 1)):
        if isinstance(view.get(key), str):
            wrong = inside_archive.address_problem(view[key], archives=archives)
            if wrong:
                add('error', path, documents.pointer('view', key), wrong)


def _check_run(run, path, *, benchmark, add):
    inputs = set(run['inputs']) if isinstance(run.get('inputs'), dict) else set()
    context = {'inputs': inputs, 'has_settings': 'settings' in run or 'settings_file' in run, 'benchmark': benchmark}
    texts = []
    if isinstance(run.get('command'), list):
        texts += [(documents.pointer('run', 'command', i), value) for i, value in enumerate(run['command'])]
    if isinstance(run.get('env'), dict):
        texts += [(documents.pointer('run', 'env', key), value) for key, value in run['env'].items()]
    estimate = run.get('estimate')
    if isinstance(estimate, dict) and isinstance(estimate.get('command'), list):
        texts += [(documents.pointer('run', 'estimate', 'command', i), value) for i, value in enumerate(estimate['command'])]
    for pointer, value in texts:
        if isinstance(value, str):
            for message in documents.command_placeholder_problems(value, **context):
                add('error', path, pointer, message)

    outputs = run.get('outputs')
    if isinstance(outputs, dict):
        for key, output in outputs.items():
            if isinstance(output, dict) and isinstance(output.get('path'), str):
                wrong = documents.relative_path_problem(output['path'])
                if wrong:
                    add('error', path, documents.pointer('run', 'outputs', key, 'path'),
                        f'The output path {output["path"]!r} {wrong}.')


def _first_repeats(items, key):
    """Yield (index, value) for each item whose key value already appeared earlier in the list."""
    seen = set()
    for index, item in enumerate(items):
        value = item.get(key) if isinstance(item, dict) else None
        if isinstance(value, str):
            if value in seen:
                yield index, value
            seen.add(value)


def _check_benchmark(document, path, add):
    metrics = document.get('metrics')
    if isinstance(metrics, list):
        for index, value in _first_repeats(metrics, 'id'):
            add('error', path, documents.pointer('metrics', index, 'id'),
                f'The metric id {value!r} is used more than once; give each metric its own id.')
    subjects = document.get('subjects')
    if isinstance(subjects, list):
        for index, value in _first_repeats(subjects, 'name'):
            add('error', path, documents.pointer('subjects', index, 'name'),
                f'The subject name {value!r} is used more than once; give each subject its own name.')
        for index, subject in enumerate(subjects):
            if isinstance(subject, dict) and isinstance(subject.get('argument'), str):
                for message in documents.argument_placeholder_problems(subject['argument'], has_recipe='recipe' in subject):
                    add('error', path, documents.pointer('subjects', index, 'argument'), message)
    run = document.get('run')
    if isinstance(run, dict):
        outputs = run.get('outputs')
        roles = [o.get('role') for o in outputs.values() if isinstance(o, dict)] if isinstance(outputs, dict) else []
        if roles.count('results') != 1:
            add('error', path, '/run/outputs' if 'outputs' in run else '/run',
                f'A benchmark run must declare exactly one output with role "results"; it declares {roles.count("results")}.')


# --------------------------------------------------------- code root (2.9.4)

def _code_root(project, root, add):
    """Return the real path of the code root, or None (with a problem) when it cannot be used."""
    value = project.get('code_root', '.')
    if not isinstance(value, str) or not value or value.startswith('/') or '\x00' in value:
        return None  # the schema has reported it
    resolved = os.path.realpath(os.path.join(root, value))
    if not os.path.isdir(resolved):
        add('error', folder_reader.PROJECT_FILE, '/code_root' if 'code_root' in project else '',
            f'The code root {value!r} is not a directory next to this folder; fix code_root or use --no-code.')
        return None
    return resolved


def _code_paths(document):
    """Yield (pointer, value) for every path relative to the code root in a document."""
    def sources(holder, *prefix):
        if isinstance(holder.get('sources'), list):
            for index, value in enumerate(holder['sources']):
                yield documents.pointer(*prefix, 'sources', index), value

    run = document.get('run')
    if isinstance(run, dict):
        if 'settings_file' in run:
            yield '/run/settings_file', run['settings_file']
        yield from sources(run, 'run')
    if 'config_file' in document:
        yield '/config_file', document['config_file']
    yield from sources(document)
    install = document.get('install')
    if isinstance(install, dict) and 'requirements' in install:
        yield '/install/requirements', install['requirements']


def check_code_paths(definition, code_root, add):
    """Report code-root paths in one definition that are malformed, escape the code root or do not exist (None skips lookups)."""
    document, path = definition.document, definition.path
    missing = 'warning' if 'earlier_work' in document else 'error'
    for pointer, value in _code_paths(document):
        if isinstance(value, str):
            _check_code_path(value, code_root, path, pointer, missing, add)


def check_project_code_paths(project, code_root, add):
    """Report tuldok.json code_paths that are malformed, repeated, escape the code root or do not exist (None skips lookups)."""
    paths = project.get('code_paths')
    if not isinstance(paths, list):
        return  # absent means the whole code root; a wrong type is a schema problem
    seen = set()
    for index, value in enumerate(paths):
        if not isinstance(value, str):
            continue
        pointer = documents.pointer('code_paths', index)
        if value in seen:
            add('error', folder_reader.PROJECT_FILE, pointer,
                f'The code path {value!r} is listed more than once; list each path once.')
            continue
        seen.add(value)
        _check_code_path(value, code_root, folder_reader.PROJECT_FILE, pointer, 'error', add)


def _check_code_path(value, code_root, path, pointer, missing, add):
    """Report one path relative to the code root: its form, then (unless code_root is None) where it leads."""
    wrong = documents.relative_path_problem(value)
    if wrong:
        add('error', path, pointer, f'The path {value!r} {wrong}.')
        return
    if code_root is None:
        return
    resolved = os.path.realpath(os.path.join(code_root, value))
    if resolved != code_root and not resolved.startswith(code_root + os.sep):
        add('error', path, pointer, f'The path {value!r} leads outside the code root through a symbolic link; point at a file inside it.')
    elif not os.path.exists(resolved):
        add(missing, path, pointer, f'The path {value!r} does not exist under the code root; fix the path or add the file.')


# ----------------------------------------------------------- across files

def check_references(definitions, add):
    """Report references to missing definitions and named outputs their producer does not declare."""
    for definition in definitions.values():
        for use in graph.uses(definition.document):
            if not graph.is_wellformed(use):
                continue  # malformed or in the wrong directory: the schema has reported it
            target = definitions.get(use.target)
            if target is None:
                add('error', definition.path, use.pointer,
                    f'{use.target} does not exist; add {use.target}.json or fix the reference.')
                continue
            if use.output is None or target.document is None:
                continue
            run = target.document.get('run')
            outputs = run.get('outputs') if isinstance(run, dict) else None
            if not isinstance(outputs, dict) or use.output not in outputs:
                name = use.role.split(':', 1)[1]
                add('error', definition.path, documents.pointer('run', 'inputs', name, 'output'),
                    f'{use.target} declares no output named {use.output!r}; use one of its run.outputs or declare it there.')


def _sound_benchmark(chart, definitions, unsound):
    """Return the chart's benchmark document, or None when it is missing or has its own errors."""
    target = definitions.get(chart.get('benchmark')) if isinstance(chart.get('benchmark'), str) else None
    if target is None or target.kind != 'benchmark' or target.document is None or target.path in unsound:
        return None
    return target.document


def check_charts(definitions, unsound, add):
    """Report chart metrics, subjects and groups missing from their benchmark (benchmarks whose path is in unsound are skipped)."""
    for definition in definitions.values():
        chart = definition.document
        if definition.kind != 'chart' or not isinstance(chart, dict):
            continue
        benchmark = _sound_benchmark(chart, definitions, unsound)
        if benchmark is None:
            continue  # a missing benchmark is a reference problem; a broken one reports its own
        reference = chart['benchmark']
        metrics = benchmark.get('metrics') if isinstance(benchmark.get('metrics'), list) else []
        metric_ids = {m.get('id') for m in metrics if isinstance(m, dict)}
        for key in ('metric', 'metric_x'):
            if isinstance(chart.get(key), str) and chart[key] not in metric_ids:
                add('error', definition.path, f'/{key}', f'{reference} has no metric {chart[key]!r}; use one of its metric ids.')
        subjects = benchmark.get('subjects') if isinstance(benchmark.get('subjects'), list) else []
        names = {s.get('name') for s in subjects if isinstance(s, dict)}
        if isinstance(chart.get('subjects'), list):
            for index, name in enumerate(chart['subjects']):
                if isinstance(name, str) and name not in names:
                    add('error', definition.path, documents.pointer('subjects', index),
                        f'{reference} has no subject {name!r}; use one of its subject names.')
        if isinstance(chart.get('group'), str):
            summary = benchmark.get('summary') if isinstance(benchmark.get('summary'), dict) else {}
            group_by = summary.get('group_by') if isinstance(summary.get('group_by'), list) else []
            if chart['group'] not in group_by:
                add('error', definition.path, '/group',
                    f'{reference} does not group its summary by {chart["group"]!r}; use one of its summary.group_by.')


def check_cycles(definitions, add):
    """Report every definition that is part of a cycle of uses."""
    decoded = {reference: d.document for reference, d in definitions.items() if d.document is not None}
    for group in graph.cycles(decoded):
        members = set(group)
        listed = ', '.join(group)
        for reference in group:
            definition = definitions[reference]
            pointer = next((use.pointer for use in graph.uses(definition.document)
                            if use.target in members and use.role not in graph.MAP_ROLES), '')
            add('error', definition.path, pointer,
                f'This definition is in a cycle of uses ({listed}); remove one of the references to break it.')


def _group_problems(groups, add):
    """Report repeated group ids, unknown parents and groups that are their own ancestor; return the ids."""
    parents, ids = {}, set()
    for index, group in enumerate(groups):
        if not isinstance(group, dict) or not isinstance(group.get('id'), str):
            continue
        if group['id'] in ids:
            add('error', folder_reader.PROJECT_FILE, documents.pointer('groups', index, 'id'),
                f'The group id {group["id"]!r} is used more than once; give each group its own id.')
            continue
        ids.add(group['id'])
        if isinstance(group.get('parent'), str):
            parents[group['id']] = (index, group['parent'])
    for group_id, (index, parent) in parents.items():
        where = documents.pointer('groups', index, 'parent')
        if parent not in ids:
            add('error', folder_reader.PROJECT_FILE, where,
                f'The parent {parent!r} is not a group of this project; use the id of another group or remove parent.')
            continue
        seen, current = set(), parent
        while current != group_id and current in parents and current not in seen:
            seen.add(current)
            current = parents[current][1]
        if current == group_id:
            add('error', folder_reader.PROJECT_FILE, where,
                f'The group {group_id!r} is its own ancestor through parent; change a parent to break the loop.')
    return ids


def check_map(project, definitions, add):
    """Report the map's fields (spec-w1.md section 1): groups, recipe group, derived_from, compared_with, map.chart.

    project is the decoded tuldok.json, or None, in which case the rules that
    need it (groups, a recipe's group, map.chart) are skipped. A reference to
    a missing recipe is check_references' problem.
    """
    groups = project.get('groups') if isinstance(project, dict) else None
    ids = _group_problems(groups, add) if isinstance(groups, list) else set()
    for reference, definition in definitions.items():
        document = definition.document
        if definition.kind != 'recipe' or not isinstance(document, dict):
            continue
        group = document.get('group')
        if project is not None and isinstance(group, str) and group not in ids:
            add('error', definition.path, '/group',
                f'{group!r} is not a group of this project; use the id of a group in tuldok.json or add the group there.')
        if document.get('derived_from') == reference:
            add('error', definition.path, '/derived_from',
                'A recipe cannot be derived from itself; name the recipe it was branched from or remove derived_from.')
        compared = document.get('compared_with')
        if isinstance(compared, list):
            for index, value in _first_repeats(compared, 'recipe'):
                add('error', definition.path, documents.pointer('compared_with', index, 'recipe'),
                    f'{value} is compared more than once; keep one entry for it.')
            for index, item in enumerate(compared):
                if isinstance(item, dict) and item.get('recipe') == reference:
                    add('error', definition.path, documents.pointer('compared_with', index, 'recipe'),
                        'A recipe cannot be compared with itself; name another recipe or remove the entry.')
    decoded = {reference: d.document for reference, d in definitions.items() if d.document is not None}
    for loop in graph.derived_loops(decoded):
        listed = ', '.join(loop)
        for reference in loop:
            add('error', definitions[reference].path, '/derived_from',
                f'Following derived_from from here comes back here ({listed}); remove one derived_from to break the loop.')
    chart = project.get('map', {}).get('chart') if isinstance(project, dict) and isinstance(project.get('map'), dict) else None
    if isinstance(chart, str) and documents.parse_reference(chart) is not None and chart.startswith('charts/'):
        target = definitions.get(chart)
        if target is None:
            add('error', folder_reader.PROJECT_FILE, '/map/chart',
                f'{chart} does not exist; name a chart of the form progression or add {chart}.json.')
        elif isinstance(target.document, dict) and target.document.get('form') != 'progression':
            add('error', folder_reader.PROJECT_FILE, '/map/chart',
                f'{chart} has the form {target.document.get("form")!r}, not progression; '
                'name a chart of the form progression.')


def _check_results(files, definitions, unsound, add):
    for file in files:
        name = file.path[len('results/'):-len('.csv')]
        benchmark = definitions.get(documents.reference('benchmarks', name))
        if benchmark is None:
            add('error', file.path, '', f'There is no benchmarks/{name}.json for this summary; add the benchmark or remove the file.')
            continue
        if file.text is None or benchmark.document is None:
            continue  # unreadable: already reported
        if benchmark.path in unsound:
            add('warning', file.path, '', f'Not checked, because {benchmark.path} has errors; fix those first.')
            continue
        for severity, pointer, message in results.check_results(file.text, benchmark.document):
            add(severity, file.path, pointer, message)
