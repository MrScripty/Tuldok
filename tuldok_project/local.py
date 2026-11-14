"""Where a project keeps what belongs to this machine alone: its local home, and the setting that places it.

Owns section 1 of docs/plans/definition-first-projects/spec-m5.md and section 1
of spec-m8.md. The local home of a project is <projects home>/<project id>/.
The projects home is, first that applies: $TULDOK_PROJECT_HOME when set and
not empty; project_home of the settings file (~/.local/share/tuldok/settings.json,
or the file $TULDOK_SETTINGS names); ~/.local/share/tuldok/projects. The
settings file is read only when the variable does not decide, and a file that
cannot be read or is not valid raises SettingsError: it never falls back to
the default. Nothing in a local home is part of the project folder.
Environments that Tuldok installs go to <local home>/environments/<name>/.
The settings file also holds pumas_endpoint, the address of the Pumas endpoint
this machine uses (spec-d5.md section 2), or nothing; it is never part of a
project folder. pumas.py checks an address before set_pumas_endpoint keeps it.
Working out a path never creates anything; a directory is made only when a
caller asks for it with create=True, or by set_project_home.
"""
import json
import os
import re
import shutil
import tempfile

from . import documents

HOME_VARIABLE = 'TULDOK_PROJECT_HOME'
SETTINGS_VARIABLE = 'TULDOK_SETTINGS'
DEFAULT_HOME = os.path.join('~', '.local', 'share', 'tuldok', 'projects')
DEFAULT_SETTINGS = os.path.join('~', '.local', 'share', 'tuldok', 'settings.json')
SETTINGS_FORMAT = 'tuldok_settings_v1'
SETTINGS_LIMIT = 64 * 1024
SETTINGS_FIELDS = ('format', 'project_home', 'pumas_endpoint')
ENDPOINT_LIMIT = 2048          # characters of pumas_endpoint
ENVIRONMENTS = 'environments'
_PROJECT_DIRECTORY = re.compile(r'^[a-f0-9]{32}$')


class SettingsError(Exception):
    """The settings file cannot be read or is not valid; the message names the file and the fault."""


def settings_path():
    """The settings file: $TULDOK_SETTINGS when set and not empty, else ~/.local/share/tuldok/settings.json."""
    return os.path.abspath(os.path.expanduser(os.environ.get(SETTINGS_VARIABLE) or DEFAULT_SETTINGS))


def read_settings():
    """The settings file's object; {} when there is no file. Raises SettingsError for anything else wrong."""
    path = settings_path()
    try:
        with open(path, 'rb') as handle:
            raw = handle.read(SETTINGS_LIMIT + 1)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SettingsError(f'The settings file {path} cannot be read: {exc.strerror}.') from None
    if len(raw) > SETTINGS_LIMIT:
        raise SettingsError(f'The settings file {path} is larger than {SETTINGS_LIMIT // 1024} KiB.')
    try:
        settings = documents.decode(raw)
    except documents.DocumentError as exc:
        raise SettingsError(f'The settings file {path} is not valid: {exc}') from None
    unknown = sorted(set(settings) - set(SETTINGS_FIELDS))
    if unknown:
        raise SettingsError(f'The settings file {path} is not valid: it has the unknown field {unknown[0]!r}.')
    if settings.get('format') != SETTINGS_FORMAT:
        raise SettingsError(f'The settings file {path} is not valid: its format must be "{SETTINGS_FORMAT}".')
    home = settings.get('project_home')
    if 'project_home' in settings and not (isinstance(home, str) and os.path.isabs(home) and '\x00' not in home):
        raise SettingsError(f'The settings file {path} is not valid: its project_home must be an absolute path.')
    if 'pumas_endpoint' in settings and endpoint_problem(settings['pumas_endpoint']):
        raise SettingsError(f'The settings file {path} is not valid: its pumas_endpoint '
                            f'{endpoint_problem(settings["pumas_endpoint"])}.')
    return settings


def endpoint_problem(value):
    """Why value cannot be a pumas_endpoint (an http or https address), or None."""
    if not isinstance(value, str) or not 1 <= len(value) <= ENDPOINT_LIMIT:
        return f'must be an address of 1 to {ENDPOINT_LIMIT} characters'
    if not value.startswith(('http://', 'https://')) or any(char.isspace() or ord(char) < 32 for char in value):
        return 'must be an http or https address without spaces'
    return None


def pumas_endpoint():
    """The Pumas endpoint this machine uses (pumas_endpoint of the settings file), or None; raises SettingsError."""
    return read_settings().get('pumas_endpoint')


def set_pumas_endpoint(address):
    """Keep address as pumas_endpoint in the settings file, or remove the key when address is None.

    The caller has checked the address (pumas.py asks it once); a value that
    is not an http or https address raises ValueError. A settings file that is
    not valid is not replaced (SettingsError). Returns the settings file's path.
    """
    if address is not None and endpoint_problem(address):
        raise ValueError(f'{address!r} {endpoint_problem(address)}.')
    settings = {key: value for key, value in read_settings().items() if key != 'pumas_endpoint'}
    if address is not None:
        settings['pumas_endpoint'] = address
    return _write_settings(settings)


def _write_settings(settings):
    """Write settings (with its format) through a temporary file renamed into place, mode 0600; the file's path."""
    file = settings_path()
    os.makedirs(os.path.dirname(file), exist_ok=True)
    text = json.dumps({'format': SETTINGS_FORMAT, **settings}, indent=2, ensure_ascii=False) + '\n'
    descriptor, temporary = tempfile.mkstemp(prefix='.settings.', suffix='.tmp', dir=os.path.dirname(file))
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(text)
        os.replace(temporary, file)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return file


def projects_home_source():
    """(the directory that holds every project's local home, where it came from: environment, settings or default)."""
    configured = os.environ.get(HOME_VARIABLE)
    if configured:
        return os.path.abspath(os.path.expanduser(configured)), 'environment'
    settings = read_settings()
    if 'project_home' in settings:
        return os.path.normpath(settings['project_home']), 'settings'
    return os.path.abspath(os.path.expanduser(DEFAULT_HOME)), 'default'


def projects_home():
    """The directory that holds every project's local home, as an absolute path; raises SettingsError."""
    return projects_home_source()[0]


def project_directories(path):
    """How many project directories (named by a project id) path holds; 0 when it cannot be listed."""
    try:
        with os.scandir(path) as entries:
            return sum(1 for entry in entries
                       if _PROJECT_DIRECTORY.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False))
    except OSError:
        return 0


def free_bytes(path):
    """The free bytes on the disk of path, or of its nearest existing parent; None when that cannot be told."""
    while not os.path.exists(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def set_project_home(path):
    """Save path as project_home in the settings file; return {project_home, settings, before, before_projects, overridden}.

    path must be absolute (ValueError otherwise). It is made with its parents
    when missing and must then be a directory this user can write (ValueError).
    A settings file that is not valid is not replaced (SettingsError). The file
    is written through a temporary file renamed into place, mode 0600. before is
    the directory the settings file or the default gave until now (the
    variable aside), before_projects how many project directories it holds
    (they are not moved), and overridden whether TULDOK_PROJECT_HOME is set and
    so overrides the setting.
    """
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError(f'{path!r} is not an absolute path.')
    path = os.path.normpath(path)
    settings = read_settings()
    before = (os.path.normpath(settings['project_home']) if 'project_home' in settings
              else os.path.abspath(os.path.expanduser(DEFAULT_HOME)))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise ValueError(f'{path} cannot be made: {exc.strerror}.') from None
    if not os.path.isdir(path) or not os.access(path, os.W_OK | os.X_OK):
        raise ValueError(f'{path} is not a directory this user can write.')
    file = _write_settings({**settings, 'project_home': path})
    return {'project_home': path, 'settings': file, 'before': before,
            'before_projects': project_directories(before) if before != path else 0,
            'overridden': bool(os.environ.get(HOME_VARIABLE))}


def home(project_id, *, create=False):
    """The local home of one project; made (with its parents) when create is true."""
    path = os.path.join(projects_home(), project_id)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def environments_directory(project_id, *, create=False):
    """<local home>/environments, where installed environments go; made when create is true."""
    path = os.path.join(home(project_id), ENVIRONMENTS)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def environment_target(project_id, name):
    """<local home>/environments/<name>: the directory an installed environment lives in. Creates nothing."""
    return os.path.join(environments_directory(project_id), name)
