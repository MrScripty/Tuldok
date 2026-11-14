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
are looked at; nothing is ever restarted. Files are never deleted here,
except an estimate's throwaway directory. A run in state adopted ran
nothing: adoption.py recorded files made elsewhere as its product, and
status counts that product built without comparing anything (spec-m8.md
section 3); a later build replaces it like any other. A dataset whose run
names a step Tuldok provides (spec-d4.md section 6) runs steps.py with
Tuldok's own interpreter and code, no environment; a freeze's run records the
line files of its tasks as it read them from the commit, and the product is
out of date when one of them differs at HEAD (_LineFiles).

What a person needs while and after a build runs (sections 7 and 8): a run is
named by its id or an unambiguous prefix of it (find_run); run_details reads
its row, and its logs are read after the project is closed again (read_log,
launcher.progress), so looking works during a build in another process;
follow repeats that until the run ends; cancel writes a running run's cancel
file, which its builder's launcher acts on; stop kills what a
run whose builder is gone left running and marks it unknown. estimate runs
the build steps' estimate commands from the same snapshot a build would use,
each under the launcher with small limits in a throwaway directory, and
stores what they print in a fourth table, estimates, keyed by reference and
the SHA-256 of the definition text it was measured for; stored_estimates
gives plan.py the ones whose definition is unchanged.
"""
from contextlib import contextmanager
import datetime
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import stat
import sys
import time
import uuid

from psycopg import sql
from psycopg.types.json import Jsonb

from . import annotations, documents, environments, graph, launcher, local, result_rows, snapshot, store
from . import folder as folder_reader

BUILT_KINDS = ('dataset', 'recipe', 'step', 'benchmark')
ACTIVE = ('queued', 'running')
ENDED_BADLY = ('failed', 'timed-out', 'over-disk', 'unknown')
ADOPTED = 'adopted'         # the state of a run that adopted files made elsewhere (adoption.py)
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
RUN_PREFIX_MINIMUM = 6      # a run may be named by at least this many of its first characters
FOLLOW_SECONDS = 2.0        # how often progress --follow looks again
ESTIMATES = 'estimates'     # <local home>/estimates/<id>/: an estimate's throwaway directory
ESTIMATE_LIMITS = {'wall_seconds': 300.0, 'disk_bytes': 100 * 1000 ** 2}
ESTIMATE_OUTPUT_LIMIT = 64 * 1024   # bytes of standard output an estimate may print
ESTIMATE_FIELDS = ('disk_bytes', 'wall_seconds', 'items')
_RUN_TEXT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
# A step Tuldok provides (spec-d4.md section 6) runs this module with Tuldok's own interpreter, from Tuldok's root.
STEPS_MODULE = 'tuldok_project.steps'
TULDOK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP_TASKS_FILE = 'tasks.json'          # <run>/tasks.json: what a freeze is told of its tasks
STEP_LINES = 'annotations'              # <run>/annotations/<name>.jsonl: the line files a freeze read

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
    # A freeze's run records each task's line file as it read it: {task: {file, sha256, blob}} (spec-d4.md section 6).
    'ALTER TABLE {schema}.runs ADD COLUMN IF NOT EXISTS annotations jsonb',
    '''CREATE TABLE IF NOT EXISTS {schema}.products (
           run_id text PRIMARY KEY,
           reference text NOT NULL, subject text NOT NULL DEFAULT '',
           directory text NOT NULL, outputs jsonb NOT NULL,
           current boolean NOT NULL)''',
    'CREATE UNIQUE INDEX IF NOT EXISTS products_current ON {schema}.products (reference, subject) WHERE current',
    '''CREATE TABLE IF NOT EXISTS {schema}.estimates (
           reference text PRIMARY KEY, definition_sha256 text NOT NULL,
           "values" jsonb NOT NULL, measured_at timestamptz NOT NULL)''',
)

_RUN_COLUMNS = ('id', 'reference', 'subject', 'plan_id', 'state', 'scratch', 'commit', 'inputs', 'environment',
                'argv', 'directory', 'owner_pid', 'owner_boot', 'queued_at', 'started_at', 'finished_at',
                'exit_status', 'seconds', 'bytes', 'strays', 'problem')
_DETAIL_COLUMNS = _RUN_COLUMNS + ('definition', 'settings', 'env', 'annotations')


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
    """Drop the runs, products and estimate records of a definition that is gone; their files are left where they are."""
    connection.execute(_q(schema, 'DELETE FROM {schema}.products WHERE reference = %s'), (reference,))
    connection.execute(_q(schema, 'DELETE FROM {schema}.runs WHERE reference = %s'), (reference,))
    connection.execute(_q(schema, 'DELETE FROM {schema}.estimates WHERE reference = %s'), (reference,))


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
                causes.append(f'its code changed since commit {product["commit"][:12]}: {_named(hits)}')
            source = import_source(document)
            hits = sorted(path for path in changed if source is not None and _under(path, source))
            if hits:
                causes.append(f'its source {source} changed since commit {product["commit"][:12]}: {_named(hits)}')
    return causes


def _named(paths):
    return ', '.join(paths[:3]) + (f' and {len(paths) - 3} more' if len(paths) > 3 else '')


def import_source(document):
    """The source of an import step when it is relative to the code root (read from the commit), else None."""
    run = _run_block(document)
    settings = run.get('settings') if isinstance(run.get('settings'), dict) else {}
    source = settings.get('source')
    if run.get('step') == 'import' and isinstance(source, str) and source and not source.startswith('/'):
        return source
    return None


def step_tasks(document):
    """The tasks a freeze step names in run.annotations (references, in order); empty for any other run."""
    run = _run_block(document)
    tasks = run.get('annotations') if run.get('step') == 'freeze' else None
    return [task for task in (tasks if isinstance(tasks, list) else ()) if isinstance(task, str)]


_LINE_HASHES = {}           # (path, size, mtime_ns, inode) -> SHA-256 of a working-tree line file, for scratch products
_LINE_HASHES_KEPT = 256


class _LineFiles:
    """The tasks' line files as a build would read them now, for the out-of-date state of a frozen dataset.

    A product built from a commit is compared with the code root's HEAD (the
    commit a build would use), a scratch product with the working tree.
    Nothing is read for a file whose Git blob is the one the run recorded.
    """
    _UNKNOWN = object()

    def __init__(self, folder, code_root):
        self.folder, self.code_root = folder, code_root
        self._head = None
        self._looked = False

    def head(self):
        if not self._looked:
            self._looked = True
            try:
                if snapshot._repository(self.folder)[0] == snapshot._repository(self.code_root)[0]:
                    self._head = snapshot._head(self.code_root)
            except snapshot.SnapshotError:
                self._head = None
        return self._head

    def now(self, item, scratch):
        """The SHA-256 of the file now, None when there is none, or _UNKNOWN when it cannot be told."""
        if scratch:
            path = os.path.join(self.folder, item['file'])
            try:
                info = os.stat(path)
            except FileNotFoundError:
                return None
            except OSError:
                return self._UNKNOWN
            key = (path, info.st_size, info.st_mtime_ns, info.st_ino)
            if key not in _LINE_HASHES:
                try:
                    with open(path, 'rb') as handle:
                        _LINE_HASHES[key] = hashlib.sha256(handle.read()).hexdigest()
                except OSError:
                    return self._UNKNOWN
                while len(_LINE_HASHES) > _LINE_HASHES_KEPT:
                    _LINE_HASHES.pop(next(iter(_LINE_HASHES)))
            return _LINE_HASHES[key]
        head = self.head()
        if head is None:
            return self._UNKNOWN
        try:
            found = snapshot.file_at(self.folder, head, item['file'], None)
            if found is None:
                return None
            if found[0] == item.get('blob'):
                return item['sha256']
            return hashlib.sha256(snapshot.file_at(self.folder, head, item['file'], annotations.FILE_LIMIT)[1]
                                  ).hexdigest()
        except (snapshot.SnapshotError, TypeError):
            return self._UNKNOWN

    def causes(self, product):
        found = []
        for reference, item in sorted((product.get('annotations') or {}).items()):
            now = self.now(item, product['scratch'])
            if now is self._UNKNOWN or now == item.get('sha256'):
                continue
            was = 'are gone' if now is None else 'changed'
            found.append(f'the annotations of {reference} ({item["file"]}) {was} since run {_short(product["run_id"])}')
        return found


def status(project):
    """{reference: {state, causes, scratch, adopted, subjects}} for every dataset, recipe, step and benchmark with runs or products.

    state is running, built, out-of-date or failed (section 5); a definition
    absent from the result has none of them. causes are sentences saying why
    it is out of date or failed. For a benchmark, subjects maps each subject
    that would run to its own {state, causes, run_id}. A definition whose
    current product was adopted (adoption.py) is built and adopted, and is
    never out of date: nothing of it is compared. A subject whose recipe has a
    current product would run even when the recipe's label holds it.
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
    for (run_id, reference, subject, outputs, scratch, commit, definition, settings, inputs, state,
         read) in connection.execute(_q(
            schema, '''SELECT p.run_id, p.reference, p.subject, p.outputs, r.scratch, r.commit, r.definition,
                              r.settings, r.inputs, r.state, r.annotations
                       FROM {schema}.products p JOIN {schema}.runs r ON r.id = p.run_id WHERE p.current''')):
        current[reference, subject] = {'run_id': run_id, 'outputs': outputs, 'scratch': scratch, 'commit': commit,
                                       'definition': definition, 'settings': settings, 'inputs': inputs,
                                       'adopted': state == ADOPTED, 'annotations': read}
    latest = {reference: (run_id, state, problem) for reference, run_id, state, problem in connection.execute(_q(
        schema, '''SELECT DISTINCT ON (reference) reference, id, state, problem FROM {schema}.runs
                   ORDER BY reference, queued_at DESC, id''')).fetchall()}
    active = {reference for (reference,) in connection.execute(_q(
        schema, 'SELECT DISTINCT reference FROM {schema}.runs WHERE state = ANY(%s)'), (list(ACTIVE),))}
    code_root = _code_root(project) if current else None
    changes = _changes(code_root, {product['commit'] for product in current.values()
                                   if not product['scratch'] and product['commit']}) if current else {}
    held = graph.states(definitions, {reference: 'built' for reference, subject in current if not subject})
    line_files = _LineFiles(project._state()['folder'], code_root) if current else None

    found = {}
    out_of_date = set()

    def judge(reference, document, subject=None):
        product = current.get((reference, subject['name'] if subject else ''))
        if product is None:
            return None
        if product['adopted']:
            return {'state': 'built', 'causes': [], 'run_id': product['run_id'], 'scratch': False, 'adopted': True}
        product = {**product, 'subject_document': subject}
        causes = _own_causes(document, texts[reference], product, current, changes, code_root)
        if product['annotations']:
            causes += line_files.causes(product)
        for key, used in _uses(document, subject).items():
            if used in out_of_date and not any(cause.startswith(_input_words(key, used)) for cause in causes):
                causes.append(f'{_input_words(key, used)} is out of date')
        return {'state': 'out-of-date' if causes else 'built', 'causes': causes, 'run_id': product['run_id'],
                'scratch': product['scratch'], 'adopted': False}

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
                     'scratch': any(item['scratch'] for item in judged.values()), 'adopted': False}
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
                     'adopted': bool(judged and judged['adopted']),
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
    """The current products, by reference and subject: run, size (of the declared outputs, or of the whole directory when none is declared), directory, scratch, adopted."""
    reap_orphans(project._connection, project.schema)
    query = '''SELECT p.reference, p.subject, p.run_id, p.directory, p.outputs, r.scratch, r.commit, r.finished_at,
                      r.state, r.bytes
               FROM {schema}.products p JOIN {schema}.runs r ON r.id = p.run_id WHERE p.current'''
    parameters = ()
    if reference is not None:
        query += ' AND p.reference = %s'
        parameters = (reference,)
    query += ' ORDER BY p.reference, p.subject'
    found = []
    for reference_, subject, run_id, directory, outputs, scratch, commit, finished, state, run_bytes in project._execute(
            query, parameters).fetchall():
        # A product with no declared outputs is its directory as a whole: its size is what the run recorded.
        size = sum(item.get('bytes') or 0 for item in outputs.values()) if outputs else (run_bytes or 0)
        found.append({'reference': reference_, 'subject': subject, 'run_id': run_id, 'directory': directory,
                      'outputs': outputs, 'bytes': size,
                      'scratch': scratch, 'commit': commit, 'finished_at': finished, 'adopted': state == ADOPTED})
    return found


# --------------------------------------------------------------- placeholders

class StepProblem(Exception):
    """A step that cannot be started as its definition stands; it fails before anything runs."""


class MissingInput(StepProblem):
    """An estimate command (or the env) names an input that has no current product: the estimate is skipped."""


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
        if name in missing and name.startswith('inputs.'):
            raise MissingInput(f'It needs {{{name}}}, but {missing[name]}.') from None
        if name in missing:
            raise StepProblem(f'{where} uses {{{name}}}, but {missing[name]}.') from None
        raise StepProblem(f'{where} uses {{{name}}}, but {{{name}}} cannot be filled here.') from None
    except ValueError as exc:
        raise StepProblem(f'{where} {exc}.') from None


# -------------------------------------------------------------------- execute

@contextmanager
def opened(folder, dsn=None, *, rebind=False, on_conflict=None, wait=None):
    """Open the project for a moment, waiting up to wait seconds (OPEN_WAIT_SECONDS) while another command has it open."""
    deadline = time.monotonic() + (OPEN_WAIT_SECONDS if wait is None else wait)
    while True:
        try:
            project = store.open_project(folder, dsn=dsn, rebind=rebind, on_conflict=on_conflict)
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

    def __init__(self, folder, plan, *, extra_env, scratch, dsn, on_event, expect=None):
        self.folder = folder
        self.plan = plan
        self.extra_env = dict(extra_env or {})
        self.scratch = scratch
        self.dsn = dsn
        self.on_event = on_event or (lambda kind, item: None)
        self.expect = expect     # a build request's covers, or None
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

    def _resolve(self, project, reference, subject, *, estimate=False):
        """Everything a run needs, with the project open: (row values, argv, env, cwd, limits, gpu).

        With estimate, the command is run.estimate.command, the directory is a
        throwaway one under <local home>/estimates/, {output} names a path that
        does not exist, the limits are ESTIMATE_LIMITS, and an input with no
        current product is a problem only when a placeholder names it
        (prepared['skipped'] is then true).
        """
        directory_name, name = documents.parse_reference(reference)
        row = project._execute('SELECT text, document FROM {schema}.definitions '
                               'WHERE directory = %s AND name = %s AND NOT removed', (directory_name, name)).fetchone()
        if row is None:
            raise store.ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
        text, document = row
        run = _run_block(document)
        if self.expect is not None and not estimate:
            self._check_expected(project, reference, text, run, subject)
        run_id = uuid.uuid4().hex
        run_directory = os.path.join(local.home(project.project_id), ESTIMATES if estimate else RUNS, run_id)
        output = os.path.join(run_directory, OUTPUT)
        estimate_block = run.get('estimate') if isinstance(run.get('estimate'), dict) else {}
        command = list(estimate_block.get('command') or []) if estimate else list(run.get('command') or [])
        step = None if estimate or not isinstance(run.get('step'), str) else run['step']
        if step is not None:
            command = ['tuldok', step]   # replaced by the step's own argv below
        values, missing, recorded = {'output': output}, {}, {}

        environment_record = None
        if isinstance(run.get('environment'), str):
            shown = self.environment(project, run['environment'])
            environment_record = {'reference': run['environment'], 'interpreter': shown['interpreter'],
                                  'found': shown['found']}

        prepared = {'id': run_id, 'reference': reference, 'subject': subject['name'] if subject else '',
                    'definition': text, 'settings': None, 'environment': environment_record,
                    'directory': run_directory, 'argv': list(command), 'env': {},
                    'problem': None, 'skipped': False, 'annotations': None, 'files': {}}
        try:
            if not command:
                raise StepProblem(f'{reference} has no run.estimate.command.' if estimate else
                                  f'{reference} has no run.command, so it cannot be built.')
            for input_name, (used, output_name) in _declared_inputs(document).items():
                product = _current_product(project, used)
                if product is None:
                    missing[f'inputs.{input_name}'] = f'its input {input_name} ({used}) has no current product'
                    if estimate:
                        continue
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
            elif estimate:
                for name in ('subject', 'subject.name'):
                    missing[name] = "an estimate is made once for the whole benchmark, not per subject"
            if 'settings' in run:
                values['settings'] = os.path.join(run_directory, SETTINGS_FILE)
                prepared['settings'] = settings_text(document, self.code.code_root)
            elif isinstance(run.get('settings_file'), str):
                values['settings'] = os.path.join(self.code.code_root, run['settings_file'])
                prepared['settings'] = settings_text(document, self.code.code_root)
                if prepared['settings'] is None:
                    raise StepProblem(f'Its settings file {run["settings_file"]} cannot be read in the code '
                                      f'at commit {self.code.commit[:12] or "(none)"}.')
            if step is not None:
                argv = self._step_argv(project, reference, run, step, values, prepared)
            else:
                argv = [_fill(part, values, missing, f'The command word {part!r}') for part in command]
                argv[0] = self._program(command, argv, environment_record)
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
            if step is not None:
                # Tuldok's own code first; the snapshot's code (the working directory) never importable.
                env.update(PYTHONSAFEPATH='1', PYTHONPATH=TULDOK_ROOT)
            prepared['env'] = env
            wall_hours = resources.get('wall_hours') or DEFAULT_WALL_HOURS
            disk_gb = resources.get('disk_gb') or DEFAULT_DISK_GB
            prepared['limits'] = {'wall_seconds': float(wall_hours) * 3600, 'disk_bytes': int(float(disk_gb) * GB)}
            if estimate:
                prepared['limits'] = dict(ESTIMATE_LIMITS)
            prepared['gpu'] = gpu
        except StepProblem as exc:
            prepared['problem'] = str(exc)
            prepared['skipped'] = isinstance(exc, MissingInput)
        prepared['inputs'] = recorded
        prepared['outputs'] = run.get('outputs') if isinstance(run.get('outputs'), dict) else {}
        prepared['kind'] = _kind(reference)
        prepared['inline_settings'] = 'settings' in run
        return prepared

    def _program(self, command, argv, environment_record):
        """The program a command runs: the environment's interpreter for python, a file in the code, or one on PATH."""
        if command[0] == 'python':
            if environment_record is None:
                raise StepProblem('The command starts with python but the run names no environment.')
            return environment_record['interpreter']
        if '/' in argv[0]:
            program = os.path.join(self.code.code_root, argv[0])
            if not (os.path.isfile(program) and os.access(program, os.X_OK)):
                raise StepProblem(f'The program {argv[0]} is not an executable file in the code.')
            return program
        program = shutil.which(argv[0], path=os.environ.get('PATH', os.defpath))
        if program is None:
            raise StepProblem(f'The program {argv[0]} was not found on PATH.')
        return program

    def _step_argv(self, project, reference, run, step, values, prepared):
        """The argv of a step Tuldok provides; for a freeze, the line files read and what the step is told of them."""
        if 'settings' not in values:
            raise StepProblem(f'{reference} runs the step {step}, which needs run.settings.')
        argv = [sys.executable, '-m', STEPS_MODULE, step, values['settings'], values['output']]
        if step == 'import':
            return argv + ['--code', self.code.code_root]
        if step != 'freeze':
            raise StepProblem(f'Tuldok provides no step {step!r}; use import or freeze.')
        inputs = _declared_inputs({'run': run})
        used = inputs.get('records', (None, None))[0]
        if 'inputs.records' not in values or used is None:
            raise StepProblem('A freeze reads the records of its input records; declare run.inputs.records.')
        tasks = step_tasks({'run': run})
        if not tasks:
            raise StepProblem('A freeze needs one or more tasks in run.annotations.')
        documents_ = {row[0]: row[1] for row in project._execute(
            f'SELECT {store._REFERENCE_SQL}, document FROM {{schema}}.definitions '
            f'WHERE NOT removed AND {store._REFERENCE_SQL} = ANY(%s)', ([*tasks, used],)).fetchall()}
        described, read = [], {}
        for task in tasks:
            document = documents_.get(task)
            if document is None:
                raise StepProblem(f'Its task {task} does not exist.')
            if document.get('dataset') != used:
                raise StepProblem(f'Its task {task} annotates {document.get("dataset")}, not its input {used}.')
            name = documents.parse_reference(task)[1]
            file = f'{folder_reader.ANNOTATIONS}/{name}{folder_reader.LINES_SUFFIX}'
            blob, data = self._line_file(project, file)
            digest = None if data is None else hashlib.sha256(data).hexdigest()
            read[task] = {'file': file, 'sha256': digest, 'blob': blob}
            copy = None
            if data is not None:
                copy = os.path.join(prepared['directory'], STEP_LINES, f'{name}{folder_reader.LINES_SUFFIX}')
                prepared['files'][copy] = data
            described.append({'reference': task, 'task': document.get('task'),
                              'vocabulary': document.get('vocabulary') or [], 'lines': copy, 'sha256': digest})
        view = (documents_.get(used) or {}).get('view')
        tasks_file = os.path.join(prepared['directory'], STEP_TASKS_FILE)
        prepared['files'][tasks_file] = (json.dumps({'tasks': described, 'view': view}, ensure_ascii=False,
                                                    indent=2) + '\n').encode('utf-8')
        prepared['annotations'] = read
        return argv + ['--records', values['inputs.records'], '--tasks', tasks_file]

    def _line_file(self, project, file):
        """(Git blob id or None, bytes or None) of a line file, relative to the project folder, as this build reads it.

        From the build's commit (annotations not committed are not frozen, as
        code is not); a scratch build reads the working tree.
        """
        folder = project._state()['folder']
        if self.code.scratch:
            path = os.path.join(folder, file)
            if not os.path.isfile(path):
                return None, None
            with open(path, 'rb') as handle:
                data = handle.read(annotations.FILE_LIMIT + 1)
            if len(data) > annotations.FILE_LIMIT:
                raise StepProblem(f'{file} is over {annotations.FILE_LIMIT} bytes.')
            return None, data
        try:
            same = snapshot._repository(folder)[0] == snapshot._repository(_code_root(project))[0]
        except snapshot.SnapshotError:
            same = False
        if not same:
            raise StepProblem(f'The project folder is not in the Git repository of the code, so {file} cannot be '
                              f'read from commit {self.code.commit[:12]}; commit it there, or build with scratch.')
        try:
            found = snapshot.file_at(folder, self.code.commit, file, annotations.FILE_LIMIT)
        except snapshot.SnapshotError as exc:
            raise StepProblem(str(exc)) from None
        return found if found is not None else (None, None)

    def _check_expected(self, project, reference, text, run, subject):
        """Refuse (stale) a step when a definition it reads to run is not the text whose SHA-256 expect holds.

        Those are the step's own definition (text, just read), its
        environment and, for a benchmark subject, the subject's recipe.
        """
        others = [used for used in (run.get('environment'), (subject or {}).get('recipe')) if isinstance(used, str)]
        others += step_tasks({'run': run})
        texts = dict(project._execute(f'SELECT {store._REFERENCE_SQL}, text FROM {{schema}}.definitions '
                                      f'WHERE NOT removed AND {store._REFERENCE_SQL} = ANY(%s)', (others,)).fetchall())
        texts[reference] = text
        expected = self.expect.get('definitions') or {}
        for used in [reference, *others]:
            if texts.get(used) is None or _sha256_text(texts[used]) != expected.get(used):
                step = reference + (f' (subject {subject["name"]})' if subject else '')
                raise store.ProjectError(f'{used} is not what the build was approved with, so {step} was not '
                                         'started; ask for the build again.', 'stale', references=[used])

    def _insert(self, project, prepared, state):
        project._execute('''INSERT INTO {schema}.runs (id, reference, subject, plan_id, state, scratch, commit,
                                definition, settings, inputs, environment, argv, env, directory, owner_pid,
                                owner_boot, queued_at, started_at, finished_at, problem, annotations)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(),
                                    CASE WHEN %s = 'running' THEN now() END,
                                    CASE WHEN %s = 'running' THEN NULL ELSE now() END, %s, %s)''',
                         (prepared['id'], prepared['reference'], prepared['subject'], self.plan_id, state,
                          self.code.scratch, self.code.commit, prepared['definition'], prepared['settings'],
                          Jsonb(prepared['inputs']), Jsonb(prepared['environment']) if prepared['environment'] else None,
                          Jsonb(prepared['argv']), Jsonb(prepared['env']), prepared['directory'], os.getpid(),
                          self.boot, state, state, prepared['problem'],
                          Jsonb(prepared['annotations']) if prepared['annotations'] is not None else None))

    # ------------------------------------------------------------------- run

    def run_one(self, reference, subject=None):
        """Run one step (one subject of a benchmark); return the item reported for it."""
        with opened(self.folder, self.dsn) as project:
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
            for path, data in prepared['files'].items():
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'xb') as handle:
                    handle.write(data)
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
            with opened(self.folder, self.dsn) as project:
                project._execute("UPDATE {schema}.runs SET state = 'unknown', finished_at = now(), "
                                 "problem = 'The build was interrupted while the command ran.' WHERE id = %s",
                                 (prepared['id'],))
            raise
        else:
            started_problem = None
        with opened(self.folder, self.dsn) as project:
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


def execute(project_folder, plan, *, confirm, extra_env=None, scratch=False, dsn=None, on_event=None, expect=None,
            stop=None):
    """Run the build steps of plan (plan.build_plan's result) in order; return what was done.

    Refuses (ProjectError, before confirm is called) a plan with a blocked
    target (code blocked), with a step another build is running (running), or
    whose code cannot be prepared (the SnapshotError's code, with its files:
    dirty, not-in-git, ...). confirm(plan) must return true to go on;
    otherwise nothing is run or written and confirmed is false. The build
    stops at the first step that does not succeed, and at an environment that
    is not ready (ProjectError not-ready). on_event(kind, item) is called with
    'start' before each command and 'end' after each step.

    For a build request (spec-m7.md section 4): expect is the request's
    covers. After the code is prepared, a commit other than expect['commit']
    (when that is not None) is refused (stale) before confirm is called; before
    each step, a definition it reads to run (its own, its environment, a
    benchmark subject's recipe) whose text does not have the SHA-256 in
    expect['definitions'] stops the build with ProjectError stale, naming it.
    stop() is called before each step (each subject of a benchmark); when it
    returns true the build ends there with ok false. Without them nothing
    differs.

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
    build = _Build(folder, plan, extra_env=extra_env, scratch=scratch, dsn=dsn, on_event=on_event, expect=expect)
    if to_build:
        with opened(folder, dsn) as project:
            state = project._state()
            code_paths = (store._read_project_file(state['folder']) or {}).get('code_paths')
            code_root = _code_root(project)
            home = local.home(project.project_id, create=True)
        try:
            build.code = snapshot.prepare(code_root, code_paths, home=home, scratch=scratch)
        except snapshot.SnapshotError as exc:
            raise _snapshot_error(exc) from None
        approved = (expect or {}).get('commit')
        if approved is not None and build.code.commit != approved:
            raise store.ProjectError(f'The code is at commit {build.code.commit[:12] or "(none)"}, not at '
                                     f'{approved[:12]} as approved; ask for the build again.', 'stale')
    result = {'plan_id': build.plan_id, 'confirmed': False, 'ok': False, 'steps': build.done, 'skipped': []}
    if not confirm(plan):
        return result
    result['confirmed'] = True
    with opened(folder, dsn) as project:
        project._execute('INSERT INTO {schema}.plans (id, created_at, targets, steps, scratch) '
                         'VALUES (%s, now(), %s, %s, %s)',
                         (build.plan_id, Jsonb(plan['targets']), Jsonb(plan['steps']), scratch))
    needed_environments = {step['environment'] for step in to_build if step['environment']}
    for step in plan['steps']:
        reference = step['reference']
        if step['kind'] == 'environment':
            if reference in needed_environments:
                with opened(folder, dsn) as project:
                    build.environment(project, reference)
            continue
        if step['action'] != 'build':
            result['skipped'].append(reference)
            continue
        if step['kind'] == 'benchmark':
            with opened(folder, dsn) as project:
                document = project.definition(reference)['document']
                entry = status(project).get(reference) or {}
            built = {name for name, item in (entry.get('subjects') or {}).items() if item['state'] == 'built'}
            subjects = [subject for subject in _subjects(document)
                        if subject['name'] in step['subjects']['run'] and subject['name'] not in built]
        else:
            subjects = [None]
        for subject in subjects:
            if stop is not None and stop():
                return result
            item = build.run_one(reference, subject)
            build.done.append(item)
            build.on_event('end', item)
            if item['state'] != 'succeeded':
                return result
    result['ok'] = True
    return result


# --------------------------------------------------------- one run, by name

def find_run(project, text):
    """The id of the run named by text: its id, or an unambiguous prefix of at least RUN_PREFIX_MINIMUM characters.

    Raises ProjectError: not-found when nothing matches (or the prefix is too
    short), ambiguous when a prefix matches several runs, with them listed.
    """
    if not isinstance(text, str) or not _RUN_TEXT.fullmatch(text):
        raise store.ProjectError(f'{text!r} is not a run id.', 'not-found')
    if project._execute('SELECT 1 FROM {schema}.runs WHERE id = %s', (text,)).fetchone() is not None:
        return text
    if len(text) < RUN_PREFIX_MINIMUM:
        raise store.ProjectError(f'There is no run {text}; name a run by its id or at least its first '
                           f'{RUN_PREFIX_MINIMUM} characters.', 'not-found')
    rows = project._execute('SELECT id, reference, subject, state FROM {schema}.runs '
                            'WHERE left(id, %s) = %s ORDER BY queued_at DESC, id', (len(text), text)).fetchall()
    if not rows:
        raise store.ProjectError(f'There is no run {text}.', 'not-found')
    if len(rows) > 1:
        listed = '\n'.join(f'  {run_id}  {reference}  {subject or "-"}  {state}'
                           for run_id, reference, subject, state in rows)
        raise store.ProjectError(f'{text} is the start of {len(rows)} runs; give more of the id:\n{listed}', 'ambiguous',
                           references=[run_id for run_id, *_ in rows])
    return rows[0][0]


def _row(project, run_id):
    row = project._execute('SELECT ' + ', '.join(_DETAIL_COLUMNS) + ' FROM {schema}.runs WHERE id = %s',
                           (run_id,)).fetchone()
    return dict(zip(_DETAIL_COLUMNS, row))


def builder_alive(row):
    """Whether the build process recorded in a run's row is still running on this boot."""
    return bool(row['owner_pid']) and row['owner_boot'] == boot_id() and _alive(row['owner_pid'])


def run_details(project, text):
    """One run's row (every column), its product when it made one, and whether its builder is alive.

    Orphaned runs are marked unknown first. The logs are not read here: the
    caller reads them from row['directory'] after closing the project.
    """
    run_id = find_run(project, text)
    reap_orphans(project._connection, project.schema)
    row = _row(project, run_id)
    product = project._execute('SELECT directory, outputs, current FROM {schema}.products WHERE run_id = %s',
                               (run_id,)).fetchone()
    row['product'] = None if product is None else {**dict(zip(('directory', 'outputs', 'current'), product)),
                                                    'adopted': row['state'] == ADOPTED}
    row['builder_alive'] = row['state'] in ACTIVE and builder_alive(row)
    return row


def read_log(directory, name, offset, *, final=False):
    """What a run's <name>.log holds from offset on: {text, offset, size, skipped}.

    At most launcher.LOG_TAIL bytes are read; when more were written since
    offset, the earlier ones are skipped (counted in skipped) and the first,
    cut line is dropped. Unless final, only complete lines are taken, so a
    line is never printed in two pieces. Links are not followed; a missing
    log reads as empty.
    """
    empty = {'text': '', 'offset': offset, 'size': None, 'skipped': 0}
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return empty
    try:
        try:
            descriptor = os.open(f'{name}.log', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                 dir_fd=directory_fd)
        except OSError:
            return empty
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode):
                return empty
            size = status.st_size
            offset = min(offset, size)
            start = max(offset, size - launcher.LOG_TAIL)
            data = os.pread(descriptor, size - start, start)
        finally:
            os.close(descriptor)
    finally:
        os.close(directory_fd)
    if not final:
        data = data[:data.rfind(b'\n') + 1]
    end = start + len(data)
    if start > offset:
        cut = data.find(b'\n')
        data = data[cut + 1:] if cut >= 0 else b''
    text = launcher._CONTROL.sub('', data.decode('utf-8', errors='replace'))
    return {'text': text, 'offset': end, 'size': size, 'skipped': start - offset}


def run_summary(row):
    """The few fields of a run's row that progress shows beside its logs."""
    return {name: row[name] for name in ('id', 'reference', 'subject', 'state', 'directory', 'started_at',
                                         'finished_at', 'seconds', 'problem')}


def follow(folder, text, *, dsn=None, interval=None, rebind=False, on_conflict=None):
    """Yield one pass every interval seconds (FOLLOW_SECONDS) until the run is no longer queued or running.

    Each pass opens the project only to read the run's row, then reads the
    logs with it closed: {run (id, reference, subject, state, ...), event (the
    latest progress event), new_event (true when it differs from the last
    pass), stdout, stderr (text written since the last pass), skipped_stdout,
    skipped_stderr (bytes not shown because more was written than one pass
    shows), ended}. The first pass shows the last part of each log.
    """
    interval = FOLLOW_SECONDS if interval is None else interval
    offsets = {name: 0 for name in launcher.LOGS}
    last_event, run_id = None, text
    while True:
        with opened(folder, dsn, rebind=rebind, on_conflict=on_conflict) as project:
            row = run_details(project, run_id)
        run_id = row['id']
        ended = row['state'] not in ACTIVE
        found = launcher.progress(row['directory'])
        item = {'run': run_summary(row), 'event': found['event'], 'new_event': found['event'] != last_event,
                'ended': ended}
        last_event = found['event']
        for name in launcher.LOGS:
            read = read_log(row['directory'], name, offsets[name], final=ended)
            offsets[name] = read['offset']
            item[name], item[f'skipped_{name}'] = read['text'], read['skipped']
        yield item
        if ended:
            return
        time.sleep(interval)


def cancel(project, text):
    """Ask a queued or running run to stop by creating its cancel file; its builder's launcher does the stopping.

    Raises ProjectError (not-active) for a run in any other state. Does not
    wait. Returns {id, reference, subject, state, cancel_file, already_asked}.
    """
    row = run_details(project, text)
    if row['state'] not in ACTIVE:
        hint = (' Its build is gone; stop kills anything it left running.' if row['state'] == 'unknown' else '')
        raise store.ProjectError(f'Run {row["id"]} ({row["reference"]}) is {row["state"]}; only a queued or running run '
                           f'can be cancelled.{hint}', 'not-active', references=[row['reference']])
    os.makedirs(row['directory'], exist_ok=True)  # a queued run's directory may not be made yet
    path = os.path.join(row['directory'], launcher.CANCEL_FILE)
    already = os.path.lexists(path)
    if not already:
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644))
        except FileExistsError:
            already = True
    return {'id': row['id'], 'reference': row['reference'], 'subject': row['subject'], 'state': row['state'],
            'cancel_file': path, 'already_asked': already}


def stop(folder, text, *, dsn=None, rebind=False, on_conflict=None):
    """For a run whose builder is gone: kill every process that carries its run id, and mark it unknown.

    Refused (ProjectError builder-alive) while the run is queued or running
    and the build process recorded in its row still runs on this boot: that
    run is stopped with cancel. The project is closed while the processes are
    stopped. Returns {id, reference, subject, was, state, killed, remaining,
    marked_unknown}; remaining lists the pids that could not be stopped.
    """
    with opened(folder, dsn, rebind=rebind, on_conflict=on_conflict) as project:
        row = _row(project, find_run(project, text))
    if row['state'] in ACTIVE and builder_alive(row):
        raise store.ProjectError(f'Run {row["id"]} ({row["reference"]}) is still being run by its build (process '
                           f'{row["owner_pid"]}); use cancel to stop it.', 'builder-alive',
                           references=[row['reference']])
    result = launcher.stop_strays(row['id'])
    marked = False
    with opened(folder, dsn, rebind=rebind, on_conflict=on_conflict) as project:
        if row['state'] in ACTIVE:
            problem = (f'Stopped with stop: the build that ran it (process {row["owner_pid"]}) was gone; '
                       f'{result["killed"]} stray process' + ('' if result['killed'] == 1 else 'es')
                       + ' killed.')
            marked = project._execute('''UPDATE {schema}.runs SET state = 'unknown', problem = %s,
                                             finished_at = coalesce(finished_at, now()),
                                             strays = coalesce(strays, 0) + %s
                                         WHERE id = %s AND state = ANY(%s) RETURNING id''',
                                      (problem, result['killed'], row['id'], list(ACTIVE))).fetchone() is not None
        reap_orphans(project._connection, project.schema)
        state = project._execute('SELECT state FROM {schema}.runs WHERE id = %s', (row['id'],)).fetchone()[0]
    return {'id': row['id'], 'reference': row['reference'], 'subject': row['subject'], 'was': row['state'],
            'state': state, 'killed': result['killed'], 'remaining': result['remaining'], 'marked_unknown': marked}


# ------------------------------------------------------------------ estimates

def _sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def stored_estimates(project):
    """{reference: {disk_bytes, wall_seconds, items, measured_at}} for the definitions' current text.

    measured_at is ISO 8601 text in UTC.
    An estimate measured for another text of the definition is left out.
    """
    rows = project._execute('''SELECT e.reference, e."values", e.measured_at
                               FROM {schema}.estimates e JOIN {schema}.definitions d
                                 ON d.directory || '/' || d.name = e.reference AND NOT d.removed
                               WHERE e.definition_sha256 = encode(sha256(convert_to(d.text, 'UTF8')), 'hex')''')
    return {reference: {**{field: values.get(field) for field in ESTIMATE_FIELDS},
                        'measured_at': measured_at.astimezone(datetime.timezone.utc).isoformat(timespec='seconds')}
            for reference, values, measured_at in rows.fetchall()}


def _first_line(directory, name):
    text = read_log(directory, name, 0, final=True)['text'].strip()
    return text.splitlines()[-1][:400] if text else ''


def _estimate_values(outcome, directory):
    """(values, None) from what a finished estimate command printed, or (None, why it is not an estimate)."""
    if outcome.state != 'succeeded':
        said = _first_line(directory, 'stderr')
        reason = {'failed': f'The estimate command exited with status {outcome.exit_status}',
                  'timed-out': f'The estimate command ran past its limit of '
                               f'{ESTIMATE_LIMITS["wall_seconds"] / 60:g} minutes and was stopped',
                  'over-disk': f'The estimate command wrote more than '
                               f'{ESTIMATE_LIMITS["disk_bytes"] / 1000 ** 2:g} MB and was stopped',
                  'cancelled': 'The estimate command was stopped'}.get(
                      outcome.state, 'A process of the estimate command could not be stopped')
        return None, reason + (f'; its last error line: {said}' if said else '.')
    try:
        with open(os.path.join(directory, 'stdout.log'), 'rb') as handle:
            raw = handle.read(ESTIMATE_OUTPUT_LIMIT + 1)
    except OSError:
        raw = b''
    if len(raw) > ESTIMATE_OUTPUT_LIMIT:
        return None, f'It printed more than {ESTIMATE_OUTPUT_LIMIT // 1024} KiB; it must print one JSON object.'
    if not raw.strip():
        return None, 'It printed nothing; it must print one JSON object.'
    try:
        document = launcher._decode_json(raw.decode('utf-8'))
    except UnicodeDecodeError:
        return None, 'Its standard output is not UTF-8 text; it must print one JSON object.'
    except (ValueError, RecursionError) as exc:
        return None, f'Its standard output is not one JSON object ({exc}).'
    if not isinstance(document, dict):
        return None, f'Its standard output is a JSON {type(document).__name__}, not an object.'
    values = {}
    for field in ESTIMATE_FIELDS:
        if field not in document:
            continue
        value = document[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            return None, f'Its {field} is {json.dumps(value)}; it must be a number of at least 0.'
        values[field] = value
    if not values:
        return None, 'Its object has none of ' + ', '.join(ESTIMATE_FIELDS) + '.'
    return values, None


def estimate(project_folder, targets, *, every=False, scratch=False, extra_env=None, dsn=None, on_event=None):
    """Run the estimate command of each build step in the plan for targets, and store what each prints (section 7).

    The code is the snapshot a build would use (ProjectError with the
    SnapshotError's code when it cannot be prepared: dirty, not-in-git, ...).
    Each command runs through launcher.run in <local home>/estimates/<id>/,
    removed afterwards, with ESTIMATE_LIMITS, the child environment a build
    step would get and {output} naming a path that does not exist. A step
    without an estimate command, or whose estimate command or env names an
    input with no current product, is skipped; one whose command fails or
    prints anything but one JSON object fails, and the next step still runs.
    on_event(item) is called after each step.

    Returns {targets, scratch, commit, steps: [{reference, result (measured,
    skipped or failed), reason, values, seconds}]}.
    """
    from . import plan as planning

    folder = os.fspath(project_folder)
    on_event = on_event or (lambda item: None)
    with opened(folder, dsn) as project:
        made = planning.build_plan(project, targets, every=every)
        state = project._state()
        code_paths = (store._read_project_file(state['folder']) or {}).get('code_paths')
        code_root = _code_root(project)
        home = local.home(project.project_id, create=True)
        documents_ = project._documents(removed=False)
    build = _Build(folder, made, extra_env=extra_env, scratch=scratch, dsn=dsn, on_event=None)
    result = {'targets': made['targets'], 'scratch': scratch, 'commit': None, 'steps': []}
    to_build = [step['reference'] for step in made['steps'] if step['action'] == 'build']
    with_command = [reference for reference in to_build
                    if (_run_block(documents_[reference]).get('estimate') or {}).get('command')]
    if with_command:
        try:
            build.code = snapshot.prepare(code_root, code_paths, home=home, scratch=scratch)
        except snapshot.SnapshotError as exc:
            raise _snapshot_error(exc) from None
        result['commit'] = build.code.commit
    for reference in to_build:
        item = {'reference': reference, 'result': 'skipped', 'reason': None, 'values': None, 'seconds': None}
        if reference not in with_command:
            item['reason'] = 'It has no estimate command.'
        else:
            _estimate_one(build, reference, item)
        result['steps'].append(item)
        on_event(item)
    return result


def _estimate_one(build, reference, item):
    with opened(build.folder, build.dsn) as project:
        try:
            prepared = build._resolve(project, reference, None, estimate=True)
        except store.ProjectError as exc:
            if exc.code != 'not-ready':
                raise
            item.update(result='failed', reason=str(exc).replace('then build again', 'then estimate again'))
            return
    if prepared['problem'] is not None:
        item.update(result='skipped' if prepared['skipped'] else 'failed', reason=prepared['problem'])
        return
    directory = prepared['directory']
    os.makedirs(directory)
    try:
        if prepared['inline_settings']:
            with open(os.path.join(directory, SETTINGS_FILE), 'w', encoding='utf-8') as handle:
                handle.write(prepared['settings'])
        try:
            outcome = launcher.run(prepared['argv'], cwd=build.code.code_root, env=prepared['env'],
                                   run_id=prepared['id'], directory=directory, limits=prepared['limits'])
        except Exception as exc:  # launcher.run raises only before the command has started
            item.update(result='failed', reason=str(exc) or f'The command could not be started ({type(exc).__name__}).')
            return
        item['seconds'] = outcome.seconds
        values, reason = _estimate_values(outcome, directory)
    finally:
        snapshot._remove(directory)
    if values is None:
        item.update(result='failed', reason=reason)
        return
    with opened(build.folder, build.dsn) as project:
        project._execute('''INSERT INTO {schema}.estimates (reference, definition_sha256, "values", measured_at)
                            VALUES (%s, %s, %s, now())
                            ON CONFLICT (reference) DO UPDATE SET definition_sha256 = EXCLUDED.definition_sha256,
                                "values" = EXCLUDED."values", measured_at = EXCLUDED.measured_at''',
                         (reference, _sha256_text(prepared['definition']), Jsonb(values)))
    item.update(result='measured', values=values)
