"""The code a run sees: a read-only copy of one commit, or the code root in place for a scratch run.

Owns section 2 of docs/plans/definition-first-projects/spec-m6.md. prepare()
finds the commit the code root is at, refuses a tree whose tracked files under
the code paths differ from that commit (unless a scratch run was asked for),
and makes <local home>/code/<commit>/ (or <commit>-<digest of the code paths>/
when code_paths limits it) from `git archive` once: extracted into
a temporary directory beside it, made read-only, then renamed into place, so a
directory under that name is always a complete snapshot of exactly those paths
and is shared by every run at that commit with those paths. The snapshot keeps the repository's layout; the
snapshot's code root is <snapshot>/<prefix of the code root in the
repository>. changed_since() lists what changed under the code root since a
commit, for the out-of-date state. Git is only read, never written: every
call is `git -C <dir>` with a fixed argument list, no shell, optional locks
off, literal pathspecs and a time limit.
"""
from dataclasses import dataclass
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

from . import documents

CODE = 'code'
GIT_SECONDS = 60
ARCHIVE_SECONDS = 600
DIGEST_CHARACTERS = 12
MAX_CODE_PATHS = 64
NAMED_CHANGES = 10
_COMMIT = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')
_PARTIAL = '.partial-'
# Variables that would point Git at another repository, index or object store than the one under -C.
_REPOSITORY_VARIABLES = (
    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
    'GIT_COMMON_DIR', 'GIT_NAMESPACE', 'GIT_PREFIX', 'GIT_IMPLICIT_WORK_TREE', 'GIT_GRAFT_FILE',
    'GIT_REPLACE_REF_BASE', 'GIT_NO_REPLACE_OBJECTS', 'GIT_SHALLOW_FILE', 'GIT_QUARANTINE_PATH',
    'GIT_CONFIG', 'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT', 'GIT_GLOB_PATHSPECS', 'GIT_NOGLOB_PATHSPECS',
    'GIT_ICASE_PATHSPECS',
)


class SnapshotError(Exception):
    """The code for a run could not be prepared or compared; nothing was left half-made.

    code is one of: not-in-git (the code root is not inside a Git work tree;
    only a scratch run can use it), no-commit (the repository has no commit
    yet), dirty (tracked files under the code paths differ from the commit;
    files names them, relative to the code root), unknown-commit (Git no longer
    has the commit), invalid (bad code paths or commit id), git-failed (a Git command failed or timed out), unsafe-archive
    (the archive held an entry that would land outside the snapshot).
    """

    def __init__(self, message, code, *, files=(), detail=''):
        super().__init__(message)
        self.code = code
        self.files = list(files)
        self.detail = detail


@dataclass(frozen=True)
class Snapshot:
    """The code one run sees.

    code_root is the directory the command runs in: <directory>/<prefix> for a
    clean run, the code root itself for a scratch run. directory is
    <local home>/code/<snapshot_name> for a clean run and None for a scratch run.
    commit is HEAD of the code root's repository ('' for a scratch run outside
    Git); prefix is the code root's path inside the repository ('' at its top).
    """
    commit: str
    scratch: bool
    code_root: str
    directory: str | None
    prefix: str


# ------------------------------------------------------------------- Git

def _environment():
    environment = {key: value for key, value in os.environ.items() if key not in _REPOSITORY_VARIABLES}
    environment['GIT_OPTIONAL_LOCKS'] = '0'
    environment['GIT_LITERAL_PATHSPECS'] = '1'
    environment['GIT_TERMINAL_PROMPT'] = '0'
    environment['LC_ALL'] = 'C'
    return environment


def _git(directory, purpose, *arguments, stdout=None, code='git-failed', seconds=GIT_SECONDS):
    """Run `git -C directory arguments...` and return its standard output (bytes, or None when stdout is a file).

    purpose completes the sentence "Git could not ..." in the error raised on failure.
    """
    command = ['git', '-C', os.fspath(directory), *arguments]
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout or subprocess.PIPE,
                              stderr=subprocess.PIPE, env=_environment(), timeout=seconds, check=False)
    except FileNotFoundError:
        raise SnapshotError(f'Git could not {purpose}: the git program was not found on PATH.', 'git-failed') from None
    except subprocess.TimeoutExpired:
        raise SnapshotError(f'Git could not {purpose}: it did not finish within {seconds} seconds.',
                            'git-failed') from None
    if done.returncode != 0:
        lines = done.stderr.decode('utf-8', 'replace').strip().splitlines()
        first = lines[0].strip() if lines else f'exit status {done.returncode}'
        raise SnapshotError(f'Git could not {purpose} in {directory}: {first}', code, detail=first)
    return done.stdout


def _text(output):
    return output.decode('utf-8', 'surrogateescape').rstrip('\n')


def _repository(code_root):
    """Return (top level, prefix) of the work tree holding code_root; prefix is '' or ends without '/'."""
    try:
        inside = _text(_git(code_root, 'tell whether the code root is in a work tree', 'rev-parse', '--is-inside-work-tree'))
    except SnapshotError as exc:
        inside, reason = 'false', exc.detail or str(exc)
    else:
        reason = 'it is inside a Git directory, not a work tree'
    if inside != 'true':
        raise SnapshotError(f'The code root {code_root} is not inside a Git work tree ({reason}); '
                            f'only a scratch run can use it.', 'not-in-git')
    top = _text(_git(code_root, 'find the top of the repository', 'rev-parse', '--show-toplevel'))
    prefix = _text(_git(code_root, "find the code root's place in the repository", 'rev-parse', '--show-prefix'))
    return top, prefix.rstrip('/')


def _head(code_root):
    output = _git(code_root, 'read the commit HEAD names', 'rev-parse', '--verify', '--end-of-options', 'HEAD^{commit}',
                  code='no-commit')
    return _text(output)


def _changed_tracked(code_root, pathspecs):
    """Return the repository-relative paths of tracked files under pathspecs that differ from HEAD (staged or not)."""
    output = _git(code_root, 'list changed tracked files', 'status', '--porcelain=v1', '-z', '--untracked-files=no',
                  '--no-renames', '--ignore-submodules=none', '--', *pathspecs)
    entries = output.decode('utf-8', 'surrogateescape').split('\0')
    paths, index = [], 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in 'RC':  # only without --no-renames; the original path follows
            paths.append(entries[index])
            index += 1
    return paths


def _under(prefix, path):
    """path (repository-relative) relative to the code root at prefix, or None when it is outside."""
    if not prefix:
        return path
    return path[len(prefix) + 1:] if path.startswith(prefix + '/') else None


# -------------------------------------------------------------- prepare

def _validated(code_paths):
    if code_paths is None:
        return None
    paths = list(code_paths)
    if not 1 <= len(paths) <= MAX_CODE_PATHS:
        raise SnapshotError(f'code_paths must list 1 to {MAX_CODE_PATHS} paths; it lists {len(paths)}.', 'invalid')
    for value in paths:
        wrong = documents.relative_path_problem(value)
        if wrong:
            raise SnapshotError(f'The code path {value!r} {wrong}.', 'invalid')
    if len(set(paths)) != len(paths):
        raise SnapshotError('code_paths names a path more than once; list each path once.', 'invalid')
    return paths


def prepare(code_root, code_paths=None, *, home, scratch=False):
    """Return the Snapshot a run at code_root sees; code_paths (relative to the code root) limits it, None is all.

    home is the project's local home (local.home). A clean run reuses or makes
    <home>/code/<snapshot_name(commit, code_paths)>/. A scratch run uses code_root in place and writes nothing.
    Raises SnapshotError when the code cannot be prepared.
    """
    code_root = os.path.abspath(os.fspath(code_root))
    paths = _validated(code_paths)
    if scratch:
        try:
            _repository(code_root)
            commit = _head(code_root)
        except SnapshotError:
            commit = ''  # a scratch run needs no commit; outside Git it simply has none
        return Snapshot(commit, True, code_root, None, '')

    top, prefix = _repository(code_root)
    commit = _head(code_root)
    changed = _changed_tracked(code_root, paths or ['.'])
    if changed:
        shown = [_under(prefix, path) or path for path in changed]
        listed = ', '.join(shown[:NAMED_CHANGES]) + (f' and {len(shown) - NAMED_CHANGES} more' if len(shown) > NAMED_CHANGES else '')
        raise SnapshotError(f'The code has changes that are not committed: {listed}. '
                            f'Commit or discard them, or ask for a scratch run.', 'dirty', files=shown)

    directory = os.path.join(os.fspath(home), CODE, snapshot_name(commit, paths))
    if not os.path.isdir(directory):
        _build(top, commit, _pathspecs(prefix, paths), directory)
    snapshot_root = os.path.join(directory, prefix) if prefix else directory
    return Snapshot(commit, False, snapshot_root, directory, prefix)


def snapshot_name(commit, code_paths):
    """<commit> for the whole code root; <commit>-<first 12 hex of SHA-256 of the sorted paths, one per line>."""
    if code_paths is None:
        return commit
    digest = hashlib.sha256('\n'.join(sorted(code_paths)).encode('utf-8', 'surrogateescape')).hexdigest()
    return f'{commit}-{digest[:DIGEST_CHARACTERS]}'


def _pathspecs(prefix, paths):
    """Repository-relative pathspecs for git archive run at the top level."""
    if paths is None:
        return [prefix] if prefix else []
    return [f'{prefix}/{path}' if prefix else path for path in paths]


def _build(top, commit, pathspecs, directory):
    """Make directory from `git archive commit -- pathspecs`, atomically; a concurrent build's result wins quietly."""
    parent = os.path.dirname(directory)
    os.makedirs(parent, exist_ok=True)
    # Partial names start with '.', so they are never a snapshot name (<commit> or <commit>-<digest>).
    partial = tempfile.mkdtemp(prefix=f'{_PARTIAL}{os.path.basename(directory)}-', dir=parent)
    try:
        with tempfile.TemporaryFile(dir=parent) as archive:
            # commit is a full id from rev-parse; '--' keeps the paths from being read as options.
            _git(top, f'archive commit {commit}', 'archive', '--format=tar', commit, '--',
                 *pathspecs, stdout=archive, seconds=ARCHIVE_SECONDS)
            archive.seek(0)
            _extract(archive, partial)
        _make_read_only(partial)
        try:
            os.rename(partial, directory)
        except OSError:
            if not os.path.isdir(directory):
                raise
            # Another build put the same snapshot in place first; ours is discarded below.
        else:
            partial = None
    finally:
        if partial is not None:
            _remove(partial)


def _safe_member(member, destination):
    """tarfile filter: the data filter (nothing outside, no devices, links inside only), and no absolute names at all."""
    if member.name.startswith('/') or os.path.isabs(member.name):
        raise tarfile.AbsolutePathError(member)  # the data filter would strip the '/'; an archive of a commit never has one
    if not (member.isfile() or member.isdir() or member.issym()):
        raise tarfile.SpecialFileError(member)
    return tarfile.data_filter(member, destination)


def _extract(archive, destination):
    try:
        with tarfile.open(fileobj=archive, mode='r:') as tar:
            tar.extractall(destination, filter=_safe_member)
    except tarfile.FilterError as exc:
        raise SnapshotError(f'The archive of the commit holds an entry Tuldok will not extract: {exc}.',
                            'unsafe-archive') from None
    except tarfile.TarError as exc:
        raise SnapshotError(f'The archive of the commit could not be read: {exc}.', 'git-failed') from None


def _make_read_only(root):
    """Directories 0555; files 0444, or 0555 when the owner may execute them; links are left alone."""
    for current, directories, files in os.walk(root, topdown=False):
        for name in files:
            path = os.path.join(current, name)
            mode = os.lstat(path).st_mode
            if stat.S_ISREG(mode):
                os.chmod(path, 0o555 if mode & stat.S_IXUSR else 0o444)
        for name in directories:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def _remove(root):
    """Remove a (possibly read-only) directory tree that this module made."""
    if not os.path.lexists(root):
        return
    os.chmod(root, 0o755)
    for current, directories, _files in os.walk(root):
        for name in directories:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                os.chmod(path, 0o755)
    shutil.rmtree(root)


# --------------------------------------------------------- changed_since

def changed_since(code_root, commit):
    """Return the paths, relative to code_root, changed since commit: committed up to HEAD, or not yet committed.

    Only tracked files count. Raises SnapshotError (unknown-commit) when Git
    no longer has the commit.
    """
    code_root = os.path.abspath(os.fspath(code_root))
    if not isinstance(commit, str) or not _COMMIT.match(commit):
        raise SnapshotError(f'{commit!r} is not a full commit id.', 'invalid')
    _top, prefix = _repository(code_root)
    try:
        _git(code_root, f'find commit {commit}', 'rev-parse', '--verify', '--quiet', '--end-of-options',
             f'{commit}^{{commit}}')
    except SnapshotError:
        raise SnapshotError(f'The repository of {code_root} no longer has commit {commit} (a rebase or clean-up '
                            f'may have removed it), so Tuldok cannot tell what changed since it.',
                            'unknown-commit') from None
    committed = _git(code_root, f'compare commit {commit} with HEAD', 'diff', '--name-only', '--no-renames', '-z',
                     '--relative', '--end-of-options', commit, 'HEAD', '--')
    changed = {path for path in committed.decode('utf-8', 'surrogateescape').split('\0') if path}
    for path in _changed_tracked(code_root, ['.']):
        inside = _under(prefix, path)
        if inside:
            changed.add(inside)
    return changed


# ------------------------------------------------------------- file_at

def file_at(directory, commit, path, limit):
    """(blob id, bytes) of path, relative to directory, in commit of directory's repository; None when it has no such file.

    The blob id alone is returned with None for the bytes when limit is None
    (to compare without reading). Raises SnapshotError: not-in-git,
    git-failed, and too-large when the file is over limit bytes.
    """
    directory = os.path.abspath(os.fspath(directory))
    if not isinstance(commit, str) or not _COMMIT.match(commit):
        raise SnapshotError(f'{commit!r} is not a full commit id.', 'invalid')
    _repository(directory)
    listed = _git(directory, f'find {path} in commit {commit[:12]}', 'ls-tree', '-z', '-l', commit, '--', path)
    for entry in listed.split(b'\0'):
        if not entry:
            continue
        head, _, name = entry.partition(b'\t')
        words = head.split()
        if name.decode('utf-8', 'surrogateescape') != path:   # ls-tree names it relative to directory
            continue
        if len(words) != 4 or words[1] != b'blob':
            return None
        blob, size = words[2].decode('ascii'), int(words[3])
        if limit is None:
            return blob, None
        if size > limit:
            raise SnapshotError(f'{path} is {size} bytes in commit {commit[:12]}; at most {limit} are read.',
                                'too-large')
        return blob, _git(directory, f'read {path} in commit {commit[:12]}', 'cat-file', 'blob', blob)
    return None
