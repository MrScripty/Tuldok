"""Where a project keeps what belongs to this machine alone: its local home.

Owns section 1 of docs/plans/definition-first-projects/spec-m5.md. The local
home of a project is $TULDOK_PROJECT_HOME/<project id>/, with
TULDOK_PROJECT_HOME defaulting to ~/.local/share/tuldok/projects. Nothing in
it is part of the project folder. Environments that Tuldok installs go to
<local home>/environments/<name>/. Working out a path never creates anything;
a directory is made only when a caller asks for it with create=True.
"""
import os

HOME_VARIABLE = 'TULDOK_PROJECT_HOME'
DEFAULT_HOME = os.path.join('~', '.local', 'share', 'tuldok', 'projects')
ENVIRONMENTS = 'environments'


def projects_home():
    """The directory that holds every project's local home, as an absolute path."""
    configured = os.environ.get(HOME_VARIABLE) or DEFAULT_HOME
    return os.path.abspath(os.path.expanduser(configured))


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
