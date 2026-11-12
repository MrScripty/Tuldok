"""Environments on this machine: which interpreter fulfils each one, its check, and installing one with uv.

Owns sections 2 to 4 of docs/plans/definition-first-projects/spec-m5.md. The
environments table of a project schema records, per environment definition,
the interpreter that fulfils it here, whether it was connected or installed,
and the result of its last check; the state an environment shows (ready,
failing, not-set-up) is read from that stored result, so opening a project
never runs anything. A check runs the recorded interpreter once as an
isolated child process with PROBE, which reports versions through
importlib.metadata without importing packages (torch alone, for a cuda
definition that lists it); compare() judges that report against the
definition as a pure function. A failed check is a stored result with
problems, never an exception: only a check that cannot be attempted at all
raises ProjectError. set_up installs with uv into the project's local home
(local.py) and keeps a log beside the target; nothing here installs anything
unless set_up is called without dry_run.
"""
import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile

from psycopg import sql
from psycopg.types.json import Jsonb

from . import documents, local, store

DIRECTORY = 'environments'
CHECK_SECONDS = 180
INSTALL_SECONDS = 3600
ERROR_CHARACTERS = 400
LOG_LINES = 20
UV_VARIABLE = 'TULDOK_UV'

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.environments (
           name text PRIMARY KEY,
           interpreter text NOT NULL,
           origin text NOT NULL CHECK (origin IN ('connected', 'installed')),
           recorded_at timestamptz NOT NULL,
           checked_at timestamptz,
           ok boolean,
           found jsonb,
           problems jsonb)''',
)

_COLUMNS = ('name', 'interpreter', 'origin', 'recorded_at', 'checked_at', 'ok', 'found', 'problems')
_SELECT = 'SELECT ' + ', '.join(_COLUMNS) + ' FROM {schema}.environments'

# Runs inside the environment's own interpreter, Python 3.10 to 3.14, with -I.
# Anything a package prints while torch is imported goes to stderr, so stdout
# carries exactly one JSON object.
PROBE = r'''
import json, os, sys
from importlib import metadata
report_stream = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)
request = json.loads(sys.argv[1])
packages = request.get("packages") or {}
report = {"python": "%d.%d.%d" % sys.version_info[:3], "executable": sys.executable, "packages": {}}
for name in packages:
    try:
        report["packages"][name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        report["packages"][name] = None
if request.get("device") == "cuda" and "torch" in packages:
    cuda = {"available": False, "version": None, "device": None, "driver": None, "error": None}
    try:
        import torch
        cuda["available"] = bool(torch.cuda.is_available())
        cuda["version"] = torch.version.cuda
        if cuda["available"]:
            cuda["device"] = torch.cuda.get_device_name(0)
    except BaseException as exc:
        cuda["error"] = ("%s: %s" % (type(exc).__name__, exc))[:400]
    try:
        with open("/proc/driver/nvidia/version", encoding="utf-8", errors="replace") as handle:
            cuda["driver"] = handle.readline().strip() or None
    except OSError:
        pass
    report["cuda"] = cuda
sys.stdout.flush()
report_stream.write(json.dumps(report))
report_stream.flush()
'''


# ------------------------------------------------------------ the store's hooks

def _q(schema, template):
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def recorded_states(connection, schema):
    """{reference: 'ready' | 'failing'} for every recorded environment; a record never checked is failing."""
    rows = connection.execute(_q(schema, 'SELECT name, ok FROM {schema}.environments')).fetchall()
    return {documents.reference(DIRECTORY, name): 'ready' if ok else 'failing' for name, ok in rows}


def forget(connection, schema, name):
    """Drop the record of one environment (its definition is gone); an installed directory is left alone."""
    connection.execute(_q(schema, 'DELETE FROM {schema}.environments WHERE name = %s'), (name,))


# ------------------------------------------------------------- the comparison

def _python_line(found):
    return found.get('python') if isinstance(found.get('python'), str) else None


def compare(definition, found):
    """(ok, problems) for what the probe reported against an environment definition.

    Pure: definition is the decoded environment document, found the probe's
    report. What must hold (spec-m5.md section 3): the Python version's
    major.minor equals the definition's python; every package's installed
    version equals the definition's exactly; for device cuda, torch is among
    the packages and reports CUDA as available.
    """
    problems = []
    asked_python = definition['python']
    python = _python_line(found)
    if python is None or '.'.join(python.split('.')[:2]) != asked_python:
        problems.append(f'Python is {python or "of an unknown version"}; the definition asks for {asked_python}.')
    reported = found.get('packages') if isinstance(found.get('packages'), dict) else {}
    for name, version in definition['packages'].items():
        installed = reported.get(name)
        if installed is None:
            problems.append(f'{name} is not installed; the definition asks for {version}.')
        elif installed != version:
            problems.append(f'{name} is {installed}; the definition asks for {version}.')
    if definition['device'] == 'cuda':
        if 'torch' not in definition['packages']:
            problems.append('The device is cuda but torch is not among the packages, so the check cannot see the GPU.')
        else:
            cuda = found.get('cuda') if isinstance(found.get('cuda'), dict) else {}
            if cuda.get('available') is not True:
                cause = f' ({cuda["error"]})' if cuda.get('error') else ''
                problems.append(f'CUDA is not available to torch{cause}.')
    return not problems, problems


def _is_report(found, definition):
    """True when the probe printed the object it promises for this definition."""
    if not isinstance(found, dict) or not isinstance(found.get('python'), str):
        return False
    if not isinstance(found.get('executable'), str) or not isinstance(found.get('packages'), dict):
        return False
    if set(found['packages']) != set(definition['packages']):
        return False
    if not all(value is None or isinstance(value, str) for value in found['packages'].values()):
        return False
    if definition['device'] == 'cuda' and 'torch' in definition['packages']:
        return isinstance(found.get('cuda'), dict)
    return True


# ------------------------------------------------------------------ the probe

def _error_text(data):
    text = data.decode('utf-8', errors='replace').strip() if data else ''
    return text[:ERROR_CHARACTERS]


def _with_error(sentence, error):
    return f'{sentence} Its error output began: {error}' if error else sentence


def probe(interpreter, definition):
    """Run PROBE in the interpreter; (found or None, [one problem] or []).

    The child runs with -I, an environment of PATH, LANG and a fresh HOME,
    that HOME as its working directory, no input and a time limit of
    CHECK_SECONDS. Its stdout and stderr are captured, never shown.
    """
    request = json.dumps({'device': definition['device'], 'packages': definition['packages']})
    with tempfile.TemporaryDirectory(prefix='tuldok-check-') as scratch:
        environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': scratch}
        try:
            done = subprocess.run([interpreter, '-I', '-c', PROBE, request], cwd=scratch, env=environment,
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=CHECK_SECONDS)
        except subprocess.TimeoutExpired as exc:
            return None, [_with_error(f'The check did not finish within {CHECK_SECONDS} seconds.',
                                      _error_text(exc.stderr))]
        except OSError as exc:
            return None, [f'The interpreter could not be started: {exc.strerror or exc}.']
    error = _error_text(done.stderr)
    if done.returncode != 0:
        return None, [_with_error(f'The check exited with status {done.returncode}.', error)]
    try:
        found = json.loads(done.stdout.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        found = None
    if not _is_report(found, definition):
        return None, [_with_error('The check printed something other than the report it should print.', error)]
    return found, []


# ------------------------------------------------------------------ records

def reference_of(text):
    """'environments/<name>' for a bare name or a reference; ProjectError not-found for anything else."""
    name = text[len(DIRECTORY) + 1:] if text.startswith(DIRECTORY + '/') else text
    if not documents.is_name(name):
        raise store.ProjectError(f'{text!r} is not an environment name or a reference such as environments/<name>.',
                                 'not-found', references=[text])
    return documents.reference(DIRECTORY, name)


def _name(reference):
    return reference_of(reference)[len(DIRECTORY) + 1:]


def _definition(project, reference):
    """The decoded environment document; ProjectError not-found when there is none (or it is removed)."""
    row = project._execute("SELECT document FROM {schema}.definitions "
                           "WHERE directory = 'environments' AND name = %s AND NOT removed",
                           (_name(reference),)).fetchone()
    if row is None:
        raise store.ProjectError(f'There is no environment {reference}.', 'not-found', references=[reference])
    return row[0]


def _record(project, name):
    row = project._execute(_SELECT + ' WHERE name = %s', (name,)).fetchone()
    return None if row is None else dict(zip(_COLUMNS, row))


def _shown(reference, definition, record):
    """One environment as the readers return it: the definition's asks, the record and its last check."""
    state = 'not-set-up' if record is None else 'ready' if record['ok'] else 'failing'
    shown = {'reference': reference, 'title': definition.get('title'), 'state': state,
             'python': definition.get('python'), 'device': definition.get('device'),
             'packages': definition.get('packages'), 'installable': _requirements(definition) is not None,
             'origin': None, 'interpreter': None, 'recorded_at': None, 'checked_at': None,
             'ok': None, 'found': None, 'problems': []}
    if record is not None:
        shown.update({key: record[key] for key in ('origin', 'interpreter', 'recorded_at', 'checked_at', 'ok', 'found')})
        shown['problems'] = record['problems'] if record['problems'] is not None else (
            ['It has not been checked yet.'] if record['checked_at'] is None else [])
    return shown


def listing(project):
    """Every environment definition (not removed), sorted by reference, with its record and last check."""
    definitions = project._execute("SELECT name, document FROM {schema}.definitions "
                                   "WHERE directory = 'environments' AND NOT removed ORDER BY name").fetchall()
    records = {row[0]: dict(zip(_COLUMNS, row)) for row in project._execute(_SELECT).fetchall()}
    return [_shown(documents.reference(DIRECTORY, name), document, records.get(name)) for name, document in definitions]


def show(project, reference):
    """One environment as listing() shows it."""
    reference = reference_of(reference)
    definition = _definition(project, reference)
    return _shown(reference, definition, _record(project, _name(reference)))


def recorded(project):
    """The references of every recorded environment, sorted."""
    return [documents.reference(DIRECTORY, name)
            for (name,) in project._execute('SELECT name FROM {schema}.environments ORDER BY name').fetchall()]


def _require_record(project, reference):
    record = _record(project, _name(reference))
    if record is None:
        raise store.ProjectError(f'{reference} is not set up on this machine; connect an interpreter or run set-up.',
                                 'not-set-up', references=[reference])
    return record


def _store(project, name, interpreter, origin):
    project._execute('''INSERT INTO {schema}.environments (name, interpreter, origin, recorded_at)
                        VALUES (%s, %s, %s, now())
                        ON CONFLICT (name) DO UPDATE SET interpreter = EXCLUDED.interpreter,
                            origin = EXCLUDED.origin, recorded_at = EXCLUDED.recorded_at,
                            checked_at = NULL, ok = NULL, found = NULL, problems = NULL''',
                     (name, interpreter, origin))


# ------------------------------------------------------------------ actions

def check(project, reference):
    """Run the check of a recorded environment, store its result and return the environment as show() does.

    Raises ProjectError only when no check can be attempted: there is no such
    environment (not-found) or nothing is recorded for it (not-set-up). A
    check that fails is returned with ok false and its problems.
    """
    reference = reference_of(reference)
    definition = _definition(project, reference)
    record = _require_record(project, reference)
    found, problems = probe(record['interpreter'], definition)
    ok = False
    if found is not None:
        ok, problems = compare(definition, found)
    project._execute('UPDATE {schema}.environments SET checked_at = now(), ok = %s, found = %s, problems = %s '
                     'WHERE name = %s AND interpreter = %s',
                     (ok, Jsonb(found) if found is not None else None, Jsonb(problems), record['name'],
                      record['interpreter']))
    return show(project, reference)


def connect(project, reference, interpreter):
    """Record an existing interpreter for the environment (origin connected), then check it.

    interpreter must be an absolute path to an executable regular file; it is
    stored exactly as given (a symbolic link is followed to test it, never
    resolved in what is stored). The record is kept whether or not the check
    passes. Raises ProjectError invalid for an unusable path.
    """
    reference = reference_of(reference)
    _definition(project, reference)
    if not isinstance(interpreter, str) or not os.path.isabs(interpreter):
        raise store.ProjectError(f'{interpreter!r} is not an absolute path; name the interpreter by its full path.',
                                 'invalid', references=[reference])
    if not os.path.isfile(interpreter) or not os.access(interpreter, os.X_OK):
        raise store.ProjectError(f'{interpreter} is not an executable file.', 'invalid', references=[reference])
    _store(project, _name(reference), interpreter, 'connected')
    return check(project, reference)


def _requirements(definition):
    install = definition.get('install')
    return install.get('requirements') if isinstance(install, dict) else None


def find_installer():
    """The uv program to run: $TULDOK_UV, else uv on PATH; None when there is neither.

    Raises ProjectError no-installer when TULDOK_UV names something that is not an executable file.
    """
    named = os.environ.get(UV_VARIABLE)
    if named:
        if not os.path.isfile(named) or not os.access(named, os.X_OK):
            raise store.ProjectError(f'{UV_VARIABLE} names {named}, which is not an executable file.', 'no-installer')
        return named
    return shutil.which('uv')


def _is_occupied(path):
    """True when path exists and is anything but an empty directory."""
    if not os.path.lexists(path):
        return False
    if os.path.islink(path) or not os.path.isdir(path):
        return True
    with os.scandir(path) as entries:
        return any(True for _ in entries)


def _remove(path):
    if os.path.islink(path) or (os.path.lexists(path) and not os.path.isdir(path)):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def _log_tail(log):
    try:
        with open(log, 'rb') as handle:
            lines = handle.read().decode('utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    return '\n'.join(lines[-LOG_LINES:])


def _run_logged(command, cwd, handle):
    """Run one install command with its output going to the open log; (ok, sentence)."""
    handle.write(f'$ {shlex.join(command)}\n'.encode('utf-8'))
    handle.flush()
    try:
        child = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                                 start_new_session=True)
    except OSError as exc:
        return False, f'{command[0]} could not be started: {exc.strerror or exc}.'
    try:
        status = child.wait(timeout=INSTALL_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait()
        return False, f'{shlex.join(command[:3])} did not finish within {INSTALL_SECONDS // 60} minutes.'
    if status != 0:
        return False, f'{shlex.join(command[:3])} exited with status {status}.'
    return True, ''


def set_up(project, reference, *, dry_run=False, replace=False):
    """Install the environment its definition describes with uv, record it (origin installed) and check it.

    Commands, run in order with the code root as the working directory:
    `uv venv --python <python> <target>`, then `uv pip install --python
    <target>/bin/python -r <code root>/<requirements>` with --extra-index-url
    for each install.index_urls. <target> is <local home>/environments/<name>;
    their output goes to <target>.log. With dry_run, returns the commands, the
    target and the log path and does nothing else.

    Raises ProjectError: no-install (no install.requirements), no-installer
    (no uv), target-exists (a non-empty target and replace false), and
    install-failed (a command failed; the half-made target is removed, the log
    kept, nothing recorded; the message ends with the last lines of the log).
    """
    reference = reference_of(reference)
    definition = _definition(project, reference)
    requirements = _requirements(definition)
    if requirements is None:
        raise store.ProjectError(f'{reference} has no install.requirements, so Tuldok cannot install it; '
                                 'connect an existing interpreter with connect instead.', 'no-install',
                                 references=[reference])
    installer = find_installer()
    if installer is None:
        raise store.ProjectError(f'No installer was found: uv is not on PATH and {UV_VARIABLE} is not set.',
                                 'no-installer', references=[reference])
    state = project._state()
    code_root = os.path.realpath(os.path.join(state['folder'], state['code_root']))
    name = _name(reference)
    target = local.environment_target(project.project_id, name)
    log = target + '.log'
    install = definition['install']
    commands = [
        [installer, 'venv', '--python', definition['python'], target],
        [installer, 'pip', 'install', '--python', os.path.join(target, 'bin', 'python'),
         '-r', os.path.join(code_root, requirements),
         *(part for url in install.get('index_urls', []) for part in ('--extra-index-url', url))],
    ]
    occupied = _is_occupied(target)
    if occupied and not replace:
        raise store.ProjectError(f'{target} already exists and is not empty; set it up again with replace '
                                 'to remove it first.', 'target-exists', references=[reference])
    planned = {'reference': reference, 'commands': commands, 'cwd': code_root, 'target': target, 'log': log,
               'replaces': occupied, 'dry_run': dry_run}
    if dry_run:
        return planned
    local.environments_directory(project.project_id, create=True)
    if occupied:
        _remove(target)
    with open(log, 'wb') as handle:
        for command in commands:
            ok, sentence = _run_logged(command, code_root, handle)
            if not ok:
                break
    if not ok:
        _remove(target)
        tail = _log_tail(log)
        raise store.ProjectError(f'Setting up {reference} failed: {sentence} The target was removed; '
                                 f'the log is {log}.' + (f' Its last lines:\n{tail}' if tail else ''),
                                 'install-failed', references=[reference])
    _store(project, name, os.path.join(target, 'bin', 'python'), 'installed')
    return {**planned, **check(project, reference)}


def disconnect(project, reference):
    """Remove the record of an environment; an installed directory is kept and its path returned.

    Returns {reference, origin, interpreter, directory}, directory being the
    installed environment's directory when the origin was installed, else
    None. Raises ProjectError not-found or not-set-up.
    """
    reference = reference_of(reference)
    _definition(project, reference)
    record = _require_record(project, reference)
    forget(project._connection, project.schema, record['name'])
    directory = None
    if record['origin'] == 'installed':
        directory = os.path.dirname(os.path.dirname(record['interpreter']))
    return {'reference': reference, 'origin': record['origin'], 'interpreter': record['interpreter'],
            'directory': directory}
