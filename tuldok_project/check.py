"""The project folder checker: every rule of the format, applied to one folder, every problem reported.

Owns the order in which sections 2.1 to 2.9 of
docs/plans/definition-first-projects/spec-m1-m2.md are applied and the rules
that are neither layout (folder.py), single-field syntax (documents.py and the
schemas) nor summary-file content (results.py): kind against directory, cards,
placeholders in context, benchmark uniqueness rules, references and named
outputs, charts against their benchmark, cycles, paths into the code root
(in definitions and in the code_paths of tuldok.json), the map's fields
(spec-w1.md section 1): groups, a recipe's group, derived_from and
compared_with, and map.chart, each annotations/<name>.jsonl against its
task (spec-d4.md section 2; the rules of a line are annotations.py's), and
the settings, inputs and tasks of a dataset whose run names a step Tuldok
provides (section 6; generate is spec-d5.md section 3).
Problems are collected, never raised, so one bad file never hides another.
"""
from dataclasses import dataclass, field
import json
import math
import os
import re

from . import annotations, documents, folder as folder_reader, graph, results, steps
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
    check_steps(definitions, add)
    check_charts(definitions, unsound, add)
    check_cycles(definitions, add)
    check_map(project, definitions, add)
    _check_results(read.results, definitions, unsound, add)
    _check_annotations(read.annotations, definitions, unsound, add, read.sidecars)

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
    if definition.kind == 'dataset' and isinstance(run, dict) and run.get('step') in STEP_SETTINGS:
        _check_step(run, path, add)


def _check_view(view, path, add):
    """The addresses of a dataset's view: a record list's at most two '!', a pattern's at most one."""
    from . import inside_archive  # here: inside_archive imports store, which imports this module
    for key, archives in (('records', 2), ('files', 1)):
        if isinstance(view.get(key), str):
            wrong = inside_archive.address_problem(view[key], archives=archives)
            if wrong:
                add('error', path, documents.pointer('view', key), wrong)


# The settings of each step Tuldok provides (spec-d4.md section 6): {member: required}.
STEP_SETTINGS = {'import': {'source': True, 'pattern': False, 'kind': False, 'rights': True, 'lines': False},
                 'freeze': {'seed': True, 'shares': True, 'include': False, 'records': False},
                 'generate': {'make': True, 'model': True, 'profile': False, 'prompt': True, 'count': False,
                              'per': False, 'seed': False, 'options': False, 'rights': True},
                 'annotate': {'by': True, 'pumas': False, 'limit': False, 'options': False},
                 # docs/plans/training-and-curation/spec-t5.md section 5
                 'embed': {'model': False, 'profile': False, 'prefix': False, 'dimensions': False, 'name': False,
                           'batch': False},
                 'select': {'records': True}}
SELECT_LIMIT = 20_000               # records named by a select or a freeze's records
EMBED_PREFIX_LIMIT = 1000
EMBED_DIMENSIONS_LIMIT = 4096
EMBED_BATCH_LIMIT = 256
_SET_NAME = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')
BY_KINDS = ('model', 'script', 'person')        # what made an annotation set (spec-t4.md section 3)
BY_TEXT_LIMIT = 200
OPTIONS_BYTES = 8 * 1024
SEED_LIMIT = 2 ** 63
GENERATE_SEED_LIMIT = 2 ** 32       # a seed Pumas takes is unsigned 32-bit
PROMPT_LIMIT = 16_000               # characters of a generate prompt
PER_LIMIT = 1000
OPTIONS_LIMIT = 32
_OPTION_NAME = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
_PROFILE = re.compile(r'^[A-Za-z0-9_.-]{1,128}$')
SHARES_LIMIT = 16
SHARE_LIMIT = 1_000_000
RIGHTS_LIMIT = 1000


def _check_step(run, path, add):
    """The settings, inputs and tasks of a run that names a step Tuldok provides."""
    step = run['step']
    settings = run.get('settings')
    if 'settings' not in run:
        needed = [key for key, required in STEP_SETTINGS[step].items() if required]
        add('error', path, '/run/settings', f'Add the required field \'settings\'; the step {step} needs '
                                            + (' and '.join(needed) if needed else 'it, {} when no setting is given')
                                            + '.')
    if isinstance(settings, dict):
        for key in settings:
            if key not in STEP_SETTINGS[step]:
                add('error', path, documents.pointer('run', 'settings', key),
                    f'Remove the unknown setting {key!r}; the step {step} takes '
                    + ', '.join(STEP_SETTINGS[step]) + '.')
        for key, needed in STEP_SETTINGS[step].items():
            if needed and key not in settings:
                add('error', path, documents.pointer('run', 'settings', key),
                    f'Add the required setting {key!r} of the step {step}.')
    settings = settings if isinstance(settings, dict) else {}
    where = lambda key: documents.pointer('run', 'settings', key)  # noqa: E731
    if step in ('import', 'generate', 'embed', 'select') and 'annotations' in run:
        add('error', path, '/run/annotations', 'Only the steps freeze and annotate name tasks; remove annotations.')

    if step == 'import':
        _check_import(settings, path, where, add)
        if 'inputs' in run:
            add('error', path, '/run/inputs', 'The step import reads files, not other products; remove inputs.')
    elif step == 'generate':
        _check_generate(run, settings, path, where, add)
    elif step == 'annotate':
        _check_annotate(run, settings, path, where, add)
    elif step in ('embed', 'select'):
        _check_records_input(run, step, path, add)
        if step == 'embed':
            _check_embed(settings, path, where, add)
        elif 'records' in settings:
            _check_record_ids(settings['records'], path, where, add)
    else:
        _check_freeze(run, settings, path, where, add)


def _check_import(settings, path, where, add):
    source = settings.get('source')
    if 'source' in settings:
        if not isinstance(source, str) or not source or len(source) > 1024 or '\x00' in source:
            add('error', path, where('source'), 'The source must be a directory: a path of 1 to 1,024 characters.')
        elif source.startswith('/'):
            add('warning', path, where('source'), f'The source {source} is absolute, so this dataset can be built '
                                                  'on this machine only; give a path relative to the code root.')
    if 'pattern' in settings:
        pattern = settings['pattern']
        wrong = documents.relative_path_problem(pattern) if isinstance(pattern, str) else 'must be a string'
        if not wrong and len(pattern) > 1024:
            wrong = 'is longer than 1,024 characters'
        if not wrong and '!' in pattern:
            wrong = "reaches into an archive with '!', which import does not do"
        if wrong:
            add('error', path, where('pattern'), f'The pattern {pattern!r} {wrong}.')
    if 'kind' in settings and settings['kind'] not in annotations.RECORD_KINDS:
        add('error', path, where('kind'), f'The kind {settings["kind"]!r} is not one of ' + ', '.join(annotations.RECORD_KINDS)
                                          + '.')
    rights = settings.get('rights')
    if 'rights' in settings and (not isinstance(rights, str) or not rights.strip() or len(rights) > RIGHTS_LIMIT):
        add('error', path, where('rights'), f'rights must be a sentence of 1 to {RIGHTS_LIMIT:,} characters on '
                                            'what may be done with the files.')
    if 'lines' in settings and not isinstance(settings['lines'], bool):
        add('error', path, where('lines'), 'lines must be true or false.')


def _check_generate(run, settings, path, where, add):
    """The settings and the one optional input (prompts) of the step generate (spec-d5.md section 3)."""
    inputs = run.get('inputs')
    with_input = 'inputs' in run
    if with_input and (not isinstance(inputs, dict) or set(inputs) != {'prompts'}
                       or not isinstance(inputs['prompts'], str) or not inputs['prompts'].startswith('datasets/')):
        add('error', path, '/run/inputs', 'The step generate takes at most one input, prompts, naming a dataset: '
                                          '"inputs": {"prompts": "datasets/<name>"}.')
    if 'make' in settings and settings['make'] not in steps.MAKES:
        add('error', path, where('make'), 'make must be ' + ' or '.join(steps.MAKES) + '.')
    model = settings.get('model')
    if 'model' in settings and not (isinstance(model, str) and model and model == model.strip()
                                    and len(model.encode('utf-8', 'surrogatepass')) <= 256
                                    and not any(ord(char) < 32 or ord(char) == 127 for char in model)):
        add('error', path, where('model'), 'model must be the alias a Pumas endpoint serves: 1 to 256 bytes, with no '
                                           'spaces around it and no control characters.')
    if 'profile' in settings and not (isinstance(settings['profile'], str) and _PROFILE.match(settings['profile'])):
        add('error', path, where('profile'), 'profile must be a Pumas profile: 1 to 128 of A-Z a-z 0-9 . _ -.')
    prompt = settings.get('prompt')
    if 'prompt' in settings:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > PROMPT_LIMIT:
            add('error', path, where('prompt'), f'prompt must be a request of 1 to {PROMPT_LIMIT:,} characters.')
        else:
            allowed = ('n', 'text') if with_input else ('n',)
            try:
                names = [text for part, text in steps.prompt_parts(prompt) if part == 'name']
            except ValueError as exc:
                add('error', path, where('prompt'), f'The prompt {exc}.')
            else:
                for name in dict.fromkeys(name for name in names if name not in allowed):
                    add('error', path, where('prompt'), f'The prompt uses {{{name}}}; it may use '
                        + ' and '.join(f'{{{known}}}' for known in allowed)
                        + ('' if with_input else ' ({text} needs an input of prompts)') + '.')
    count, per = settings.get('count'), settings.get('per')
    if with_input:
        if 'count' in settings:
            add('error', path, where('count'), 'With an input, one item is made for each of its text records '
                                               '(times per); remove count.')
        if 'per' in settings and (type(per) is not int or not 1 <= per <= PER_LIMIT):
            add('error', path, where('per'), f'per must be a whole number from 1 to {PER_LIMIT:,}.')
    else:
        if 'count' not in settings:
            add('error', path, where('count'), 'Add the required setting \'count\' of the step generate: how many to '
                                               'make, without an input of prompts.')
        elif type(count) is not int or not 1 <= count <= steps.GENERATE_LIMIT:
            add('error', path, where('count'), f'count must be a whole number from 1 to {steps.GENERATE_LIMIT:,}.')
        if 'per' in settings:
            add('error', path, where('per'), 'per goes with an input of prompts; remove it or add the input.')
    seed = settings.get('seed')
    if 'seed' in settings and (type(seed) is not int or not 0 <= seed < GENERATE_SEED_LIMIT):
        add('error', path, where('seed'), 'The seed must be a whole number from 0 to 4,294,967,295.')
    options = settings.get('options')
    if 'options' in settings:
        if not isinstance(options, dict) or len(options) > OPTIONS_LIMIT:
            add('error', path, where('options'), f'options must be an object of at most {OPTIONS_LIMIT} options of '
                                                 'the capability, such as {"max_tokens": 256}.')
        else:
            for name, value in options.items():
                pointer = documents.pointer('run', 'settings', 'options', name)
                if name == 'seed':
                    add('error', path, pointer, 'The seed is the setting seed, not an option; move it there.')
                elif not _OPTION_NAME.match(name):
                    add('error', path, pointer, f'The option name {name!r} must be 1 to 64 of a-z 0-9 _, starting '
                                                'with a letter.')
                elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    add('error', path, pointer, f'The option {name} must be a number.')
    rights = settings.get('rights')
    if 'rights' in settings and (not isinstance(rights, str) or not rights.strip() or len(rights) > RIGHTS_LIMIT):
        add('error', path, where('rights'), f'rights must be a sentence of 1 to {RIGHTS_LIMIT:,} characters on '
                                            'what may be done with what is made.')


def _check_annotate(run, settings, path, where, add):
    """The input, task, annotator and settings of the step annotate (spec-t4.md section 4)."""
    inputs = run.get('inputs')
    if not isinstance(inputs, dict) or set(inputs) != {'records'} or not isinstance(inputs['records'], str) \
            or not inputs['records'].startswith('datasets/'):
        add('error', path, '/run/inputs', 'The step annotate takes one input, records, naming the dataset of its '
                                          'task: "inputs": {"records": "datasets/<name>"}.')
    tasks = run.get('annotations')
    if not isinstance(tasks, list) or len(tasks) != 1:
        add('error', path, '/run/annotations', 'The step annotate makes a set for one task: '
                                               '"annotations": ["annotations/<name>"].')
    if ('command' in run) == ('pumas' in settings):
        add('error', path, '/run', 'An annotate runs either the project\'s command (run.command) or a model of the '
                                   'Pumas endpoint (settings.pumas); give exactly one.')
    by = settings.get('by')
    if 'by' in settings:
        wrong = not isinstance(by, dict) or set(by) - {'kind', 'name', 'version'} or by.get('kind') not in BY_KINDS \
            or not isinstance(by.get('name'), str) or not 1 <= len(by['name']) <= BY_TEXT_LIMIT \
            or ('version' in by and not (isinstance(by['version'], str) and len(by['version']) <= BY_TEXT_LIMIT))
        if wrong:
            add('error', path, where('by'), 'by must say what makes the annotations: {"kind": "model", "script" or '
                                            f'"person", "name": 1 to {BY_TEXT_LIMIT} characters, and an optional '
                                            '"version"}.')
    asked = settings.get('pumas')
    if 'pumas' in settings and not (isinstance(asked, dict) and set(asked) <= {'model', 'profile', 'instruction'}
                                    and isinstance(asked.get('model'), str) and asked['model']
                                    and (not isinstance(asked.get('profile'), str) or _PROFILE.match(asked['profile']))
                                    and all(isinstance(asked.get(key, ''), str) for key in ('profile', 'instruction'))
                                    and len(asked.get('instruction', '')) <= PROMPT_LIMIT):
        add('error', path, where('pumas'), 'pumas must name the served model: {"model", and optionally "profile" and '
                                           f'"instruction" (at most {PROMPT_LIMIT:,} characters)}}.')
    limit = settings.get('limit')
    if 'limit' in settings and (type(limit) is not int or not 1 <= limit <= steps.ANNOTATE_LIMIT):
        add('error', path, where('limit'), f'limit must be a whole number from 1 to {steps.ANNOTATE_LIMIT:,}.')
    if 'options' in settings:
        options = settings['options']
        if not isinstance(options, dict) or len(json.dumps(options, separators=(',', ':'))) > OPTIONS_BYTES:
            add('error', path, where('options'), f'options must be an object of at most {OPTIONS_BYTES:,} bytes.')


def _check_records_input(run, step, path, add):
    inputs = run.get('inputs')
    if not isinstance(inputs, dict) or set(inputs) != {'records'} or not isinstance(inputs['records'], str) \
            or not inputs['records'].startswith('datasets/'):
        add('error', path, '/run/inputs', f'The step {step} takes one input, records, naming a dataset: '
                                          '"inputs": {"records": "datasets/<name>"}.')


def _check_record_ids(records, path, where, add):
    """records of a select or a freeze: 1 to SELECT_LIMIT different record ids (spec-t5.md section 5)."""
    if not isinstance(records, list) or not 1 <= len(records) <= SELECT_LIMIT:
        add('error', path, where('records'), f'records must be a list of 1 to {SELECT_LIMIT:,} record ids.')
        return
    for index, item in enumerate(records):
        if not isinstance(item, str) or not 1 <= len(item) <= 600 or any(ord(char) < 32 or ord(char) == 127
                                                                         for char in item):
            add('error', path, documents.pointer('run', 'settings', 'records', str(index)),
                'A record id is 1 to 600 characters with no control characters.')
            return
    if len(set(records)) != len(records):
        add('error', path, where('records'), 'records names a record more than once.')


def _check_embed(settings, path, where, add):
    """The settings of the step embed (spec-t5.md section 5); every one is optional."""
    model = settings.get('model')
    if 'model' in settings and not (isinstance(model, str) and model and model == model.strip()
                                    and len(model.encode('utf-8', 'surrogatepass')) <= 256
                                    and not any(ord(char) < 32 or ord(char) == 127 for char in model)):
        add('error', path, where('model'), 'model must be the alias a Pumas endpoint serves: 1 to 256 bytes, with no '
                                           'spaces around it and no control characters.')
    if 'profile' in settings and not (isinstance(settings['profile'], str) and _PROFILE.match(settings['profile'])):
        add('error', path, where('profile'), 'profile must be a Pumas profile: 1 to 128 of A-Z a-z 0-9 . _ -.')
    if 'profile' in settings and 'model' not in settings:
        add('error', path, where('profile'), 'profile goes with model; name the model too.')
    prefix = settings.get('prefix')
    if 'prefix' in settings and (not isinstance(prefix, str) or len(prefix) > EMBED_PREFIX_LIMIT):
        add('error', path, where('prefix'), f'prefix must be a string of at most {EMBED_PREFIX_LIMIT:,} characters.')
    dimensions = settings.get('dimensions')
    if 'dimensions' in settings and (type(dimensions) is not int or not 1 <= dimensions <= EMBED_DIMENSIONS_LIMIT):
        add('error', path, where('dimensions'), f'dimensions must be a whole number from 1 to '
                                                f'{EMBED_DIMENSIONS_LIMIT:,}.')
    if 'name' in settings and not (isinstance(settings['name'], str) and _SET_NAME.match(settings['name'])):
        add('error', path, where('name'), 'name must be 1 to 64 of a-z 0-9 . _ -, starting with a letter or digit.')
    batch = settings.get('batch')
    if 'batch' in settings and (type(batch) is not int or not 1 <= batch <= EMBED_BATCH_LIMIT):
        add('error', path, where('batch'), f'batch must be a whole number from 1 to {EMBED_BATCH_LIMIT}.')


def _check_freeze(run, settings, path, where, add):
    inputs = run.get('inputs')
    if not isinstance(inputs, dict) or set(inputs) != {'records'} or not isinstance(inputs['records'], str) \
            or not inputs['records'].startswith('datasets/'):
        add('error', path, '/run/inputs', 'The step freeze takes one input, records, naming a dataset: '
                                          '"inputs": {"records": "datasets/<name>"}.')
    if 'annotations' not in run:
        add('error', path, '/run/annotations', "Add the required field 'annotations': the tasks the step freeze "
                                               'reads, the first deciding which records are taken.')
    seed = settings.get('seed')
    if 'seed' in settings and (type(seed) is not int or not -SEED_LIMIT <= seed < SEED_LIMIT):
        add('error', path, where('seed'), 'The seed must be an integer of at most 63 bits.')
    shares = settings.get('shares')
    if 'shares' in settings:
        if not isinstance(shares, dict) or not 1 <= len(shares) <= SHARES_LIMIT:
            add('error', path, where('shares'), f'shares must be an object of 1 to {SHARES_LIMIT} splits and their '
                                                'relative sizes, such as {"train": 8, "validation": 1, "test": 1}.')
        else:
            for name, size in shares.items():
                if not documents.NAME.match(name) or len(name) > 32:
                    add('error', path, documents.pointer('run', 'settings', 'shares', name),
                        f'The split name {name!r} must be 1 to 32 characters of a-z 0-9 . _ -, starting with a '
                        'letter or digit.')
                if type(size) is not int or not 0 <= size <= SHARE_LIMIT:
                    add('error', path, documents.pointer('run', 'settings', 'shares', name),
                        f'The share of {name!r} must be an integer from 0 to {SHARE_LIMIT:,}.')
            if all(type(size) is int for size in shares.values()) and not any(shares.values()):
                add('error', path, where('shares'), 'At least one share must be above 0.')
    if 'records' in settings:
        _check_record_ids(settings['records'], path, where, add)
    include = settings.get('include')
    if 'include' in settings:
        if not isinstance(include, list) or not include or len(set(map(str, include))) != len(include) \
                or any(state not in annotations.STATES for state in include):
            add('error', path, where('include'), 'include must be a list of different states: '
                                                 + ', '.join(annotations.STATES) + '.')


def check_steps(definitions, add):
    """Report each task of a freeze that annotates another dataset than the freeze's input (a missing one is
    check_references' problem)."""
    for definition in definitions.values():
        run = definition.document.get('run') if isinstance(definition.document, dict) else None
        if definition.kind != 'dataset' or not isinstance(run, dict) or run.get('step') not in ('freeze', 'annotate'):
            continue
        inputs = run.get('inputs') if isinstance(run.get('inputs'), dict) else {}
        used = inputs.get('records') if isinstance(inputs.get('records'), str) else None
        tasks = run.get('annotations') if isinstance(run.get('annotations'), list) else []
        for index, task in enumerate(tasks):
            target = definitions.get(task) if isinstance(task, str) else None
            if target is None or target.kind != 'annotation' or not isinstance(target.document, dict):
                continue
            if used is not None and target.document.get('dataset') != used:
                add('error', definition.path, documents.pointer('run', 'annotations', index),
                    f'{task} annotates {target.document.get("dataset")}, not {used}, the input of this {run["step"]}; '
                    'name a task of its input.')


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
        settings = run.get('settings')
        source = settings.get('source') if run.get('step') == 'import' and isinstance(settings, dict) else None
        if isinstance(source, str) and source and not source.startswith('/'):
            yield '/run/settings/source', source   # relative to the code root, read from the commit
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


def _check_annotations(files, definitions, unsound, add, sidecars=None):
    """Each line file against its task: a file with no task is an error; a task with errors leaves it unchecked.

    The sidecars of a task (spec-t4.md section 2): a directory with no task
    is an error, a line naming a sidecar that is not there is an error, and a
    sidecar no line names is a warning.
    """
    sidecars = dict(sidecars or {})
    for name in sorted(sidecars):
        task = definitions.get(documents.reference(folder_reader.ANNOTATIONS, name))
        if task is None:
            add('error', f'{folder_reader.ANNOTATIONS}/{name}', '',
                f'There is no {folder_reader.ANNOTATIONS}/{name}.json, the task of these sidecars; add the task or '
                'remove the directory.')
    for definition in definitions.values():
        document = definition.document
        if definition.kind == 'annotation' and isinstance(document, dict) and document.get('task') == 'keypoints':
            names = document.get('keypoints') if isinstance(document.get('keypoints'), list) else []
            for index, pair in enumerate(document.get('skeleton') or []):
                if isinstance(pair, list) and any(point not in names for point in pair):
                    add('error', definition.path, documents.pointer('skeleton', index),
                        'A pair of the skeleton names a point that is not in keypoints; name two of the keypoints.')
    named = {}
    for file in files:
        name = file.path[len(f'{folder_reader.ANNOTATIONS}/'):-len(folder_reader.LINES_SUFFIX)]
        task = definitions.get(documents.reference(folder_reader.ANNOTATIONS, name))
        if task is None:
            add('error', file.path, '', f'There is no {folder_reader.ANNOTATIONS}/{name}.json, the task of these '
                                        'annotations; add the task or remove the file.')
            continue
        if file.text is None or task.document is None:
            continue  # unreadable: already reported
        if task.path in unsound:
            add('warning', file.path, '', f'Not checked, because {task.path} has errors; fix those first.')
            continue
        parsed = annotations.read(file.raw, task.document['task'], task.document.get('vocabulary', []),
                                  annotations.task_fields(task.document))
        for problem in parsed.reported():
            add(problem.severity, file.path, problem.pointer, problem.message)
        held = sidecars.get(name, {})
        used = named.setdefault(name, set())
        for number, row in parsed.rows:
            for sidecar in annotations.sidecars(task.document['task'], row.get('value')):
                used.add(sidecar)
                if sidecar not in held:
                    add('error', file.path, f'line {number}', f'The sidecar {folder_reader.ANNOTATIONS}/{name}/'
                                                              f'{sidecar} is not there; add it or change the line.')
    for name, held in sorted(sidecars.items()):
        if documents.reference(folder_reader.ANNOTATIONS, name) not in definitions:
            continue
        unused = sorted(set(held) - named.get(name, set()))
        if unused:
            add('warning', f'{folder_reader.ANNOTATIONS}/{name}', '',
                f'{len(unused)} sidecar{"s" if len(unused) > 1 else ""} no annotation names ({", ".join(unused[:5])}'
                f'{", …" if len(unused) > 5 else ""}); the next Save of this task removes them.')
