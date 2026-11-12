"""Building a plan: running each step from a snapshot of the code, and the runs, products and states that follow.

Owns sections 4 to 6 of docs/plans/definition-first-projects/spec-m6.md. Three
tables of a project schema record what was built: plans (one row per build
that was confirmed), runs (one row per command started or refused, written
with state running before the command starts) and products (the output
directory of a succeeded run; at most one current per reference and subject).
status() derives from them, the definitions and the code root the states
built, out-of-date, running and failed, with the causes of each; store.py
reports them through graph.states(local=...) and plan.py turns them into
actions. execute() runs a plan: the project is opened to read what a step
needs and to write its run row, closed while the command runs under
launcher.run (so other commands can open it), and opened again to check the
outputs, import a benchmark's results and record the product. A run left
queued or running by a builder that is gone becomes unknown whenever builds
are looked at; nothing is ever restarted. Files are never deleted here.
"""
from contextlib import contextmanager
import fcntl
import json
import os
import shutil
import time
import uuid

from psycopg import sql
from psycopg.types.json import Jsonb

from . import documents, environments, graph, launcher, local, result_rows, snapshot, store

BUILT_KINDS = ('dataset', 'recipe', 'step', 'benchmark')
ACTIVE = ('queued', 'running')
ENDED_BADLY = ('failed', 'timed-out', 'over-disk', 'unknown')
DEFAULT_WALL_HOURS = 24
DEFAULT_DISK_GB = 50
GB = 1000 ** 3
RUNS = 'runs'
OUTPUT = 'output'
SETTINGS_FILE = 'settings.json'
GPU_LOCK = 'gpu.lock'
BOOT_ID = '/proc/sys/kernel/random/boot_id'
PASSED_VARIABLES = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TZ')
RECIPE_INPUT = '{recipe}'   # the inputs key of a benchmark subject's recipe; never a valid input name
OPEN_WAIT_SECONDS = 60      # how long execute waits for a project another command has open
PROBLEMS_SHOWN = 5

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.plans (
           id text PRIMARY KEY, created_at timestamptz NOT NULL,
           targets jsonb NOT NULL, steps jsonb NOT NULL, scratch boolean NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS {schema}.runs (
           id text PRIMARY KEY,
           reference text NOT NULL, subject text NOT NULL DEFAULT '',
           plan_id text NOT NULL,
           state text NOT NULL,
           scratch boolean NOT NULL, commit text NOT NULL,
           definition text NOT NULL, settings text,
           inputs jsonb NOT NULL, environment jsonb,
           argv jsonb NOT NULL, env jsonb NOT NULL,
           directory text NOT NULL,
           owner_pid integer, owner_boot text,
           queued_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz,
           exit_status integer, seconds double precision, bytes bigint, strays integer,
           problem text)''',
    'CREATE INDEX IF NOT EXISTS runs_reference ON {schema}.runs (reference, subject, queued_at)',
    '''CREATE TABLE IF NOT EXISTS {schema}.products (
           run_id text PRIMARY KEY,
           reference text NOT NULL, subject text NOT NULL DEFAULT '',
           directory text NOT NULL, outputs jsonb NOT NULL,
           current boolean NOT NULL)''',
    'CREATE UNIQUE INDEX IF NOT EXISTS products_current ON {schema}.products (reference, subject) WHERE current',
)

_RUN_COLUMNS = ('id', 'reference', 'subject', 'plan_id', 'state', 'scratch', 'commit', 'inputs', 'environment',
                'argv', 'directory', 'owner_pid', 'owner_boot', 'queued_at', 'started_at', 'finished_at',
                'exit_status', 'seconds', 'bytes', 'strays', 'problem')


def _q(schema, template):
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def _kind(reference):
    return documents.KINDS[documents.parse_reference(reference)[0]]


def _run_block(document):
    run = document.get('run') if isinstance(document, dict) else None
    return run if isinstance(run, dict) else {}


def _short(run_id):
    return run_id[:12]


# ----------------------------------------------------------- the store's hooks

def forget(connection, schema, reference):
    """Drop the runs and products records of a definition that is gone; their files are left where they are."""
    connection.execute(_q(schema, 'DELETE FROM {schema}.products WHERE reference = %s'), (reference,))
    connection.execute(_q(schema, 'DELETE FROM {schema}.runs WHERE reference = %s'), (reference,))


def boot_id():
    try:
        with open(BOOT_ID, encoding='ascii') as handle:
            return handle.read().strip()
    except OSError:
        return ''


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap_orphans(connection, schema):
    """Mark unknown every queued or running run whose builder process is gone (or ran before this boot)."""
    rows = connection.execute(_q(schema, 'SELECT id, owner_pid, owner_boot FROM {schema}.runs '
                                         'WHERE state = ANY(%s)'), (list(ACTIVE),)).fetchall()
    if not rows:
        return []
    boot = boot_id()
    gone = [(run_id, pid) for run_id, pid, owner_boot in rows
            if owner_boot != boot or pid is None or not _alive(pid)]
    for run_id, pid in gone:
        connection.execute(_q(schema, '''UPDATE {schema}.runs SET state = 'unknown', finished_at = now(),
                                             problem = %s WHERE id = %s AND state = ANY(%s)'''),
                           (f'The build that ran it (process {pid}) is gone, so how it ended is not known; '
                            f'it is never restarted. stop kills anything it left running.', run_id, list(ACTIVE)))
    return [run_id for run_id, _ in gone]


# -------------------------------------------------------------------- states

def _code_root(project):
    state = project._state()
    return os.path.realpath(os.path.join(state['folder'], state['code_root']))


def settings_text(document, code_root):
    """The settings text a run of this definition would see: inline settings as written, or the settings file's text.

    None when the run has neither, or when the settings file cannot be read.
    """
    run = _run_block(document)
    if 'settings' in run:
        return json.dumps(run['settings'], indent=2, ensure_ascii=False) + '\n'
    if isinstance(run.get('settings_file'), str):
        try:
            with open(os.path.join(code_root, run['settings_file']), encoding='utf-8') as handle:
                return handle.read()
        except (OSError, UnicodeDecodeError):
            return None
    return None


def _declared_inputs(document):
    """{name: (reference, output or None)} of a definition's run.inputs."""
    found = {}
    inputs = _run_block(document).get('inputs')
    for name, value in (inputs.items() if isinstance(inputs, dict) else ()):
        if isinstance(value, str):
            found[name] = (value, None)
        elif isinstance(value, dict):
            found[name] = (value.get('from'), value.get('output'))
    return found


def _subjects(document):
    subjects = document.get('subjects') if isinstance(document, dict) else None
    return [subject for subject in (subjects if isinstance(subjects, list) else ())
            if isinstance(subject, dict) and isinstance(subject.get('name'), str)]


def runnable_subjects(document, held_states):
    """The subjects of a benchmark that would run: those whose recipe is not cannot-rebuild or needs-work."""
    return [subject for subject in _subjects(document)
            if held_states.get(subject.get('recipe')) not in ('cannot-rebuild', 'needs-work')]


def _uses(document, subject=None):
    """{inputs key: reference} a run of this definition (and subject) records: its inputs and the subject's recipe."""
    uses = {name: reference for name, (reference, _) in _declared_inputs(document).items()}
    if subject is not None and isinstance(subject.get('recipe'), str):
        uses[RECIPE_INPUT] = subject['recipe']
    return uses


def _input_words(key, reference):
    return f'the recipe {reference} of its subject' if key == RECIPE_INPUT else f'its input {key} ({reference})'


_UNKNOWN_COMMIT = object()


def _changes(code_root, commits):
    """{commit: set of changed paths, or _UNKNOWN_COMMIT}; empty when the code root is not in Git."""
    found = {}
    for commit in sorted(commits):
        try:
            found[commit] = snapshot.changed_since(code_root, commit)
        except snapshot.SnapshotError as exc:
            if exc.code == 'not-in-git':
                return {}
            found[commit] = _UNKNOWN_COMMIT if exc.code in ('unknown-commit', 'invalid') else set()
    return found


def _under(path, source):
    source = source.rstrip('/')
    return path == source or path.startswith(source + '/')


def _own_causes(document, text, product, current, changes, code_root):
    """The out-of-date causes of one current product that do not depend on other definitions' states."""
    causes = []
    if product['definition'] != text:
        causes.append(f'its definition changed since run {_short(product["run_id"])}')
    settings_file = _run_block(document).get('settings_file')
    if isinstance(settings_file, str) and settings_text(document, code_root) != product['settings']:
        causes.append(f'its settings file {settings_file} changed since run {_short(product["run_id"])}')
    recorded = product['inputs'] or {}
    for key, reference in _uses(document, product.get('subject_document')).items():
        now = current.get((reference, ''))
        if now is None:
            causes.append(f'{_input_words(key, reference)} has no current product')
        elif (recorded.get(key) or {}).get('run_id') != now['run_id']:
            causes.append(f'{_input_words(key, reference)} was rebuilt since (now run {_short(now["run_id"])})')
    if not product['scratch'] and product['commit']:
        changed = changes.get(product['commit'], set())
        if changed is _UNKNOWN_COMMIT:
            causes.append(f'its commit {product["commit"][:12]} is no longer in the repository, '
                          'so the code may have changed')
        else:
            sources = [source for source in _run_block(document).get('sources', []) if isinstance(source, str)]
            hits = sorted(path for path in changed if any(_under(path, source) for source in sources))
            if hits:
                shown = ', '.join(hits[:3]) + (f' and {len(hits) - 3} more' if len(hits) > 3 else '')
                causes.append(f'its code changed since commit {product["commit"][:12]}: {shown}')
    return causes


def status(project):
    """{reference: {state, causes, scratch, subjects}} for every dataset, recipe, step and benchmark with runs or products.

    state is running, built, out-of-date or failed (section 5); a definition
    absent from the result has none of them. causes are sentences saying why
    it is out of date or failed. For a benchmark, subjects maps each subject
    that would run to its own {state, causes, run_id}.
    """
    connection, schema = project._connection, project.schema
    if connection.execute(_q(schema, 'SELECT NOT EXISTS (SELECT 1 FROM {schema}.runs)')).fetchone()[0]:
        return {}
    reap_orphans(connection, schema)
    rows = connection.execute(_q(schema, f'''SELECT {store._REFERENCE_SQL}, text, document FROM {{schema}}.definitions
                                             WHERE NOT removed''')).fetchall()
    texts = {reference: text for reference, text, _ in rows}
    definitions = {reference: document for reference, _, document in rows}
    current = {}
    for (run_id, reference, subject, outputs, scratch, commit, definition, settings, inputs) in connection.execute(_q(
            schema, '''SELECT p.run_id, p.reference, p.subject, p.outputs, r.scratch, r.commit, r.definition,
                              r.settings, r.inputs
                       FROM {schema}.products p JOIN {schema}.runs r ON r.id = p.run_id WHERE p.current''')):
        current[reference, subject] = {'run_id': run_id, 'outputs': outputs, 'scratch': scratch, 'commit': commit,
                                       'definition': definition, 'settings': settings, 'inputs': inputs}
    latest = {reference: (run_id, state, problem) for reference, run_id, state, problem in connection.execute(_q(
        schema, '''SELECT DISTINCT ON (reference) reference, id, state, problem FROM {schema}.runs
                   ORDER BY reference, queued_at DESC, id''')).fetchall()}
    active = {reference for (reference,) in connection.execute(_q(
        schema, 'SELECT DISTINCT reference FROM {schema}.runs WHERE state = ANY(%s)'), (list(ACTIVE),))}
    code_root = _code_root(project) if current else None
    changes = _changes(code_root, {product['commit'] for product in current.values()
                                   if not product['scratch'] and product['commit']}) if current else {}
    held = graph.states(definitions)

    found = {}
    out_of_date = set()

    def judge(reference, document, subject=None):
        product = current.get((reference, subject['name'] if subject else ''))
        if product is None:
            return None
        product = {**product, 'subject_document': subject}
        causes = _own_causes(document, texts[reference], product, current, changes, code_root)
        for key, used in _uses(document, subject).items():
            if used in out_of_date and not any(cause.startswith(_input_words(key, used)) for cause in causes):
                causes.append(f'{_input_words(key, used)} is out of date')
        return {'state': 'out-of-date' if causes else 'built', 'causes': causes, 'run_id': product['run_id'],
                'scratch': product['scratch']}

    for reference in graph.order(definitions):
        if reference not in definitions or _kind(reference) not in BUILT_KINDS:
            continue
        document = definitions[reference]
        if _kind(reference) == 'benchmark':
            subjects = {subject['name']: judge(reference, document, subject)
                        for subject in runnable_subjects(document, held)}
            judged = {name: item for name, item in subjects.items() if item is not None}
            entry = {'subjects': {name: item or {'state': 'not-built', 'causes': [], 'run_id': None, 'scratch': False}
                                  for name, item in subjects.items()},
                     'scratch': any(item['scratch'] for item in judged.values())}
            if not subjects or not judged:
                entry.update(state=None, causes=[])
            elif len(judged) == len(subjects) and all(item['state'] == 'built' for item in judged.values()):
                entry.update(state='built', causes=[])
            else:
                causes = [f'subject {name} is not built' if item is None else f'subject {name}: {cause}'
                          for name, item in subjects.items() if item is None or item['state'] != 'built'
                          for cause in ([None] if item is None else item['causes'])]
                entry.update(state='out-of-date', causes=causes)
        else:
            judged = judge(reference, document)
            entry = {'subjects': None, 'scratch': bool(judged and judged['scratch']),
                     'state': judged and judged['state'], 'causes': judged['causes'] if judged else []}
        if entry['state'] is None and reference in latest and latest[reference][1] in ENDED_BADLY:
            run_id, state, problem = latest[reference]
            entry.update(state='failed', causes=[f'its last run {_short(run_id)} ended {state}'
                                                 + (f': {problem}' if problem else '')])
        if reference in active:
            entry['state'] = 'running'
            entry['causes'] = ['it is being built now']
        if entry['state'] == 'out-of-date':
            out_of_date.add(reference)
        if entry['state'] is not None:
            found[reference] = entry
    return found


def local_states(project):
    """{reference: state} of the build states, for graph.states(local=...)."""
    return {reference: entry['state'] for reference, entry in status(project).items()}


# ------------------------------------------------------------------ listings

def runs(project, reference=None):
    """The runs, newest first, as dicts (after marking orphaned ones unknown)."""
    reap_orphans(project._connection, project.schema)
    query = 'SELECT ' + ', '.join(_RUN_COLUMNS) + ' FROM {schema}.runs'
    parameters = ()
    if reference is not None:
        query += ' WHERE reference = %s'
        parameters = (reference,)
    query += ' ORDER BY queued_at DESC, id'
    return [dict(zip(_RUN_COLUMNS, row)) for row in project._execute(query, parameters).fetchall()]


def products(project, reference=None):
    """The current products, by reference and subject: run, size of the declared outputs, directory, scratch."""
    reap_orphans(project._connection, project.schema)
    query = '''SELECT p.reference, p.subject, p.run_id, p.directory, p.outputs, r.scratch, r.commit, r.finished_at
               FROM {schema}.products p JOIN {schema}.runs r ON r.id = p.run_id WHERE p.current'''
    parameters = ()
    if reference is not None:
        query += ' AND p.reference = %s'
        parameters = (reference,)
    query += ' ORDER BY p.reference, p.subject'
    found = []
    for reference_, subject, run_id, directory, outputs, scratch, commit, finished in project._execute(
            query, parameters).fetchall():
        found.append({'reference': reference_, 'subject': subject, 'run_id': run_id, 'directory': directory,
                      'outputs': outputs, 'bytes': sum(item.get('bytes') or 0 for item in outputs.values()),
                      'scratch': scratch, 'commit': commit, 'finished_at': finished})
    return found


# --------------------------------------------------------------- placeholders

class StepProblem(Exception):
    """A step that cannot be started as its definition stands; it fails before anything runs."""


def fill(text, values):
    """text with every {name} replaced from values; '{{' and '}}' become literal braces.

    The text must follow documents.placeholders' rules (ValueError otherwise);
    a name missing from values raises KeyError with that name.
    """
    documents.placeholders(text)  # the same rules as the checker; raises ValueError on a stray brace
    out, index = [], 0
    while index < len(text):
        char = text[index]
        if char == '{':
            if text.startswith('{{', index):
                out.append('{')
                index += 2
                continue
            end = text.index('}', index + 1)
            out.append(values[text[index + 1:end]])
            index = end + 1
        elif char == '}':
            out.append('}')
            index += 2
        else:
            out.append(char)
            index += 1
    return ''.join(out)


def _fill(text, values, missing, where):
    try:
        return fill(text, values)
    except KeyError as exc:
        name = exc.args[0]
        reason = missing.get(name, f'{{{name}}} cannot be filled here')
        raise StepProblem(f'{where} uses {{{name}}}, but {reason}.') from None
    except ValueError as exc:
        raise StepProblem(f'{where} {exc}.') from None


# -------------------------------------------------------------------- execute

@contextmanager
def _opened(folder, dsn):
    """Open the project for a moment, waiting while another command has it open."""
    deadline = time.monotonic() + OPEN_WAIT_SECONDS
    while True:
        try:
            project = store.open_project(folder, dsn=dsn)
            break
        except store.ProjectError as exc:
            if exc.code != 'busy' or time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    try:
        yield project
    finally:
        project.close()


@contextmanager
def _gpu_lock(needed):
    if not needed:
        yield
        return
    home = local.projects_home()
    os.makedirs(home, exist_ok=True)
    descriptor = os.open(os.path.join(home, GPU_LOCK), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _size(path):
    if os.path.isfile(path) and not os.path.islink(path):
        return os.lstat(path).st_size
    total = 0
    for current, _directories, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                pass
    return total


def _current_product(project, reference, subject=''):
    row = project._execute('SELECT run_id, directory, outputs FROM {schema}.products '
                           'WHERE reference = %s AND subject = %s AND current', (reference, subject)).fetchone()
    return None if row is None else {'run_id': row[0], 'directory': row[1], 'outputs': row[2]}


class _Build:
    """One execute(): the snapshot, the environments checked so far, and what each step did."""

    def __init__(self, folder, plan, *, extra_env, scratch, dsn, on_event):
        self.folder = folder
        self.plan = plan
        self.extra_env = dict(extra_env or {})
        self.scratch = scratch
        self.dsn = dsn
        self.on_event = on_event or (lambda kind, item: None)
        self.code = None
        self.environments = {}   # reference -> shown environment after a passing check in this build
        self.plan_id = uuid.uuid4().hex
        self.boot = boot_id()
        self.done = []

    # ------------------------------------------------------------ environment

    def environment(self, project, reference):
        """The environment checked once in this build; StepProblem-free stop when it is not ready."""
        if reference in self.environments:
            return self.environments[reference]
        try:
            shown = environments.check(project, reference)
        except store.ProjectError as exc:
            if exc.code != 'not-set-up':
                raise
            raise store.ProjectError(f'{reference} is not set up on this machine; set it up or connect an '
                                     'interpreter, then build again.', 'not-ready', references=[reference]) from None
        if not shown['ok']:
            raise store.ProjectError(f'{reference} is not ready: its check found '
                                     + '; '.join(shown['problems']) + ' Set it up or connect an interpreter '
                                     'that matches it, then build again.', 'not-ready', references=[reference])
        self.environments[reference] = shown
        return shown

    # ---------------------------------------------------------------- prepare

    def _resolve(self, project, reference, subject):
        """Everything a run needs, with the project open: (row values, argv, env, cwd, limits, gpu)."""
        directory_name, name = documents.parse_reference(reference)
        row = project._execute('SELECT text, document FROM {schema}.definitions '
                               'WHERE directory = %s AND name = %s AND NOT removed', (directory_name, name)).fetchone()
        if row is None:
            raise store.ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
        text, document = row
        run = _run_block(document)
        run_id = uuid.uuid4().hex
        run_directory = os.path.join(local.home(project.project_id), RUNS, run_id)
        output = os.path.join(run_directory, OUTPUT)
        values, missing, recorded = {'output': output}, {}, {}

        environment_record = None
        if isinstance(run.get('environment'), str):
            shown = self.environment(project, run['environment'])
            environment_record = {'reference': run['environment'], 'interpreter': shown['interpreter'],
                                  'found': shown['found']}

        prepared = {'id': run_id, 'reference': reference, 'subject': subject['name'] if subject else '',
                    'definition': text, 'settings': None, 'environment': environment_record,
                    'directory': run_directory, 'argv': list(run.get('command') or []), 'env': {},
                    'problem': None}
        try:
            if not run.get('command'):
                raise StepProblem(f'{reference} has no run.command, so it cannot be built.')
            for input_name, (used, output_name) in _declared_inputs(document).items():
                product = _current_product(project, used)
                if product is None:
                    missing[f'inputs.{input_name}'] = f'{used} has no current product'
                    raise StepProblem(f'Its input {input_name} ({used}) has no current product; build it first.')
                path = product['directory']
                if output_name is not None:
                    declared = (product['outputs'] or {}).get(output_name)
                    if declared is None:
                        raise StepProblem(f'Its input {input_name} names the output {output_name} of {used}, '
                                          f'which run {_short(product["run_id"])} did not record.')
                    path = os.path.join(path, declared['path'])
                values[f'inputs.{input_name}'] = path
                recorded[input_name] = {'reference': used, 'run_id': product['run_id'], 'output': output_name}
            if subject is not None:
                values['subject.name'] = subject['name']
                argument = subject.get('argument')
                recipe_values = {}
                if isinstance(subject.get('recipe'), str):
                    product = _current_product(project, subject['recipe'])
                    if product is None:
                        raise StepProblem(f'The recipe {subject["recipe"]} of subject {subject["name"]} has no '
                                          'current product; build it first.')
                    recipe_values['recipe'] = product['directory']
                    recorded[RECIPE_INPUT] = {'reference': subject['recipe'], 'run_id': product['run_id'],
                                              'output': None}
                values['subject'] = (_fill(argument, recipe_values, {}, f'The argument of subject {subject["name"]}')
                                     if isinstance(argument, str) else subject['name'])
            if 'settings' in run:
                values['settings'] = os.path.join(run_directory, SETTINGS_FILE)
                prepared['settings'] = settings_text(document, self.code.code_root)
            elif isinstance(run.get('settings_file'), str):
                values['settings'] = os.path.join(self.code.code_root, run['settings_file'])
                prepared['settings'] = settings_text(document, self.code.code_root)
                if prepared['settings'] is None:
                    raise StepProblem(f'Its settings file {run["settings_file"]} cannot be read in the code '
                                      f'at commit {self.code.commit[:12] or "(none)"}.')
            argv = [_fill(part, values, missing, f'The command word {part!r}') for part in run['command']]
            if run['command'][0] == 'python':
                if environment_record is None:
                    raise StepProblem('The command starts with python but the run names no environment.')
                argv[0] = environment_record['interpreter']
            elif '/' in argv[0]:
                program = os.path.join(self.code.code_root, argv[0])
                if not (os.path.isfile(program) and os.access(program, os.X_OK)):
                    raise StepProblem(f'The program {argv[0]} is not an executable file in the code.')
                argv[0] = program
            else:
                program = shutil.which(argv[0], path=os.environ.get('PATH', os.defpath))
                if program is None:
                    raise StepProblem(f'The program {argv[0]} was not found on PATH.')
                argv[0] = program
            prepared['argv'] = argv
            resources = run.get('resources') if isinstance(run.get('resources'), dict) else {}
            gpu = resources.get('gpu') is True
            env = {key: os.environ[key] for key in PASSED_VARIABLES if key in os.environ}
            env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
            if not gpu:
                env['CUDA_VISIBLE_DEVICES'] = ''
            elif 'CUDA_VISIBLE_DEVICES' in os.environ:
                env['CUDA_VISIBLE_DEVICES'] = os.environ['CUDA_VISIBLE_DEVICES']
            for key, value in (run.get('env') or {}).items():
                env[key] = _fill(value, values, missing, f'The value of env {key}')
            env.update(self.extra_env)
            prepared['env'] = env
            wall_hours = resources.get('wall_hours') or DEFAULT_WALL_HOURS
            disk_gb = resources.get('disk_gb') or DEFAULT_DISK_GB
            prepared['limits'] = {'wall_seconds': float(wall_hours) * 3600, 'disk_bytes': int(float(disk_gb) * GB)}
            prepared['gpu'] = gpu
        except StepProblem as exc:
            prepared['problem'] = str(exc)
        prepared['inputs'] = recorded
        prepared['outputs'] = run.get('outputs') if isinstance(run.get('outputs'), dict) else {}
        prepared['kind'] = _kind(reference)
        prepared['inline_settings'] = 'settings' in run
        return prepared

    def _insert(self, project, prepared, state):
        project._execute('''INSERT INTO {schema}.runs (id, reference, subject, plan_id, state, scratch, commit,
                                definition, settings, inputs, environment, argv, env, directory, owner_pid,
                                owner_boot, queued_at, started_at, finished_at, problem)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(),
                                    CASE WHEN %s = 'running' THEN now() END,
                                    CASE WHEN %s = 'running' THEN NULL ELSE now() END, %s)''',
                         (prepared['id'], prepared['reference'], prepared['subject'], self.plan_id, state,
                          self.code.scratch, self.code.commit, prepared['definition'], prepared['settings'],
                          Jsonb(prepared['inputs']), Jsonb(prepared['environment']) if prepared['environment'] else None,
                          Jsonb(prepared['argv']), Jsonb(prepared['env']), prepared['directory'], os.getpid(),
                          self.boot, state, state, prepared['problem']))

    # ------------------------------------------------------------------- run

    def run_one(self, reference, subject=None):
        """Run one step (one subject of a benchmark); return the item reported for it."""
        with _opened(self.folder, self.dsn) as project:
            prepared = self._resolve(project, reference, subject)
            item = {'reference': reference, 'subject': prepared['subject'], 'run_id': prepared['id'],
                    'directory': prepared['directory']}
            if prepared['problem'] is not None:
                self._insert(project, prepared, 'failed')
                item.update(state='failed', problem=prepared['problem'], seconds=None)
                return item
            os.makedirs(os.path.join(prepared['directory'], OUTPUT))
            if prepared['inline_settings']:
                with open(os.path.join(prepared['directory'], SETTINGS_FILE), 'w', encoding='utf-8') as handle:
                    handle.write(prepared['settings'])
            self._insert(project, prepared, 'running')
        self.on_event('start', item)
        try:
            with _gpu_lock(prepared['gpu']):
                outcome = launcher.run(prepared['argv'], cwd=self.code.code_root, env=prepared['env'],
                                       run_id=prepared['id'], directory=prepared['directory'],
                                       limits=prepared['limits'])
        except Exception as exc:  # launcher.run raises only before the command has started
            outcome = launcher.Outcome('failed', None, 0.0, 0, _size(prepared['directory']))
            started_problem = str(exc) or f'The command could not be started ({type(exc).__name__}).'
        except BaseException:
            with _opened(self.folder, self.dsn) as project:
                project._execute("UPDATE {schema}.runs SET state = 'unknown', finished_at = now(), "
                                 "problem = 'The build was interrupted while the command ran.' WHERE id = %s",
                                 (prepared['id'],))
            raise
        else:
            started_problem = None
        with _opened(self.folder, self.dsn) as project:
            state, problem = self._finish(project, prepared, outcome, started_problem)
        item.update(state=state, problem=problem, seconds=outcome.seconds)
        return item

    def _finish(self, project, prepared, outcome, problem):
        """Check the outputs, import results, record the run's end and its product; (state, problem)."""
        state = outcome.state
        output = os.path.join(prepared['directory'], OUTPUT)
        outputs, results_text = {}, None
        if problem is None:
            own = _outcome_problem(outcome, prepared)
            problem = ' '.join(part for part in (outcome.problem, own) if part) or None
        if state == 'succeeded':
            for name, declared in prepared['outputs'].items():
                path = os.path.join(output, declared['path'])
                if not os.path.exists(path):
                    state, problem = 'failed', f'The declared output {name} ({declared["path"]}) was not written.'
                    break
                outputs[name] = {'path': declared['path'], 'role': declared['role'], 'bytes': _size(path)}
                if declared['role'] == 'results' and prepared['kind'] == 'benchmark':
                    with open(path, 'rb') as handle:
                        results_text = handle.read(result_rows.VALUES_LIMIT + 1)
        if state == 'succeeded' and results_text is not None:
            problem = _results_problem(project, results_text, prepared, outputs)
            if problem is not None:
                state = 'failed'
        with project._connection.transaction():
            if state == 'succeeded':
                if results_text is not None:
                    project.import_values(results_text, path=os.path.join(output, outputs_path(outputs)))
                project._execute('UPDATE {schema}.products SET current = false '
                                 'WHERE reference = %s AND subject = %s AND current',
                                 (prepared['reference'], prepared['subject']))
                project._execute('INSERT INTO {schema}.products (run_id, reference, subject, directory, outputs, '
                                 'current) VALUES (%s, %s, %s, %s, %s, true)',
                                 (prepared['id'], prepared['reference'], prepared['subject'], output, Jsonb(outputs)))
            project._execute('''UPDATE {schema}.runs SET state = %s, finished_at = now(), exit_status = %s,
                                    seconds = %s, bytes = %s, strays = %s, problem = %s WHERE id = %s''',
                             (state, outcome.exit_status, outcome.seconds, outcome.bytes, outcome.strays, problem,
                              prepared['id']))
        return state, problem


def outputs_path(outputs):
    return next((item['path'] for item in outputs.values() if item['role'] == 'results'), '')


def _results_problem(project, text, prepared, outputs):
    """None when the results file is a values file for this benchmark and subject, else the first problems."""
    path = outputs_path(outputs)
    found, problems = result_rows.check_values(text, project._benchmark_document, path=path)
    messages = [f'{problem.pointer or "-"}: {problem.message}' for problem in problems]
    if found is not None:
        name = documents.parse_reference(prepared['reference'])[1]
        if found.benchmark != name:
            messages.append(f'/benchmark: the file is for benchmark {found.benchmark!r}, not {name!r}.')
        if found.subject != prepared['subject']:
            messages.append(f'/subject: the file is for subject {found.subject!r}, not {prepared["subject"]!r}.')
    if not messages:
        return None
    shown = '; '.join(messages[:PROBLEMS_SHOWN]) + (f'; and {len(messages) - PROBLEMS_SHOWN} more'
                                                     if len(messages) > PROBLEMS_SHOWN else '')
    return f'The results file {path} was refused: {shown}'


def _outcome_problem(outcome, prepared):
    logs = os.path.join(prepared['directory'], 'stderr.log')
    if outcome.state == 'succeeded':
        return None
    if outcome.state == 'failed':
        return f'The command exited with status {outcome.exit_status}; see {logs}.'
    if outcome.state == 'timed-out':
        return f'It ran past its wall-time limit of {prepared["limits"]["wall_seconds"] / 3600:.3g} h and was stopped.'
    if outcome.state == 'over-disk':
        return f'Its run directory grew past its disk limit of {prepared["limits"]["disk_bytes"] / GB:.3g} GB.'
    if outcome.state == 'cancelled':
        return 'It was cancelled.'
    return 'A process of the run could not be stopped, so how it ended is not known.'


def _snapshot_error(exc):
    return store.ProjectError(str(exc), exc.code, files=exc.files)


def execute(project_folder, plan, *, confirm, extra_env=None, scratch=False, dsn=None, on_event=None):
    """Run the build steps of plan (plan.build_plan's result) in order; return what was done.

    Refuses (ProjectError, before confirm is called) a plan with a blocked
    target (code blocked), with a step another build is running (running), or
    whose code cannot be prepared (the SnapshotError's code, with its files:
    dirty, not-in-git, ...). confirm(plan) must return true to go on;
    otherwise nothing is run or written and confirmed is false. The build
    stops at the first step that does not succeed, and at an environment that
    is not ready (ProjectError not-ready). on_event(kind, item) is called with
    'start' before each command and 'end' after each step.

    Returns {plan_id, confirmed, ok, steps: [{reference, subject, run_id,
    state, problem, seconds}], skipped: [references already built]}.
    """
    folder = os.fspath(project_folder)
    if plan['blocked_targets']:
        raise store.ProjectError('These targets cannot be built: ' + ', '.join(plan['blocked_targets'])
                                 + '. See plan for why.', 'blocked', references=plan['blocked_targets'])
    to_build = [step for step in plan['steps'] if step['action'] == 'build']
    running = [step['reference'] for step in to_build if step['state'] == 'running']
    if running:
        raise store.ProjectError('Another build is running ' + ', '.join(running) + '; wait for it to end.',
                                 'running', references=running)
    build = _Build(folder, plan, extra_env=extra_env, scratch=scratch, dsn=dsn, on_event=on_event)
    if to_build:
        with _opened(folder, dsn) as project:
            state = project._state()
            code_paths = (store._read_project_file(state['folder']) or {}).get('code_paths')
            code_root = _code_root(project)
            home = local.home(project.project_id, create=True)
        try:
            build.code = snapshot.prepare(code_root, code_paths, home=home, scratch=scratch)
        except snapshot.SnapshotError as exc:
            raise _snapshot_error(exc) from None
    result = {'plan_id': build.plan_id, 'confirmed': False, 'ok': False, 'steps': build.done, 'skipped': []}
    if not confirm(plan):
        return result
    result['confirmed'] = True
    with _opened(folder, dsn) as project:
        project._execute('INSERT INTO {schema}.plans (id, created_at, targets, steps, scratch) '
                         'VALUES (%s, now(), %s, %s, %s)',
                         (build.plan_id, Jsonb(plan['targets']), Jsonb(plan['steps']), scratch))
    needed_environments = {step['environment'] for step in to_build if step['environment']}
    for step in plan['steps']:
        reference = step['reference']
        if step['kind'] == 'environment':
            if reference in needed_environments:
                with _opened(folder, dsn) as project:
                    build.environment(project, reference)
            continue
        if step['action'] != 'build':
            result['skipped'].append(reference)
            continue
        if step['kind'] == 'benchmark':
            with _opened(folder, dsn) as project:
                document = project.definition(reference)['document']
                entry = status(project).get(reference) or {}
            built = {name for name, item in (entry.get('subjects') or {}).items() if item['state'] == 'built'}
            subjects = [subject for subject in _subjects(document)
                        if subject['name'] in step['subjects']['run'] and subject['name'] not in built]
        else:
            subjects = [None]
        for subject in subjects:
            item = build.run_one(reference, subject)
            build.done.append(item)
            build.on_event('end', item)
            if item['state'] != 'succeeded':
                return result
    result['ok'] = True
    return result
