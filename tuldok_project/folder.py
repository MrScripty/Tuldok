"""Reading a project folder safely: the layout, file types and size caps of the format.

Owns section 2.1 of docs/plans/definition-first-projects/spec-m1-m2.md. It walks
the folder through directory descriptors without following symbolic links,
accepts only regular files and directories, enforces the size caps, and returns
every file it could read together with the problems it found. It decodes
tuldok.json and the definitions (documents.decode) but judges nothing else
about their content; that is check.py's work.
"""
from dataclasses import dataclass, field
import errno
import hashlib
import os
import stat

from . import documents
from .documents import Problem

DEFINITION_LIMIT = 1024 * 1024
PROJECT_LIMIT = 64 * 1024
RESULTS_LIMIT = 16 * 1024 * 1024

PROJECT_FILE = 'tuldok.json'
OPTIONAL_FILES = ('README.md', '.gitignore')
RESULTS = 'results'
NOTES = 'notes'

# Flags for opening a directory without following a symbolic link.
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


@dataclass(frozen=True)
class File:
    """One file read from the folder. document is the decoded JSON object, or None."""
    path: str
    raw: bytes
    sha256: str
    text: str | None
    document: dict | None


@dataclass(frozen=True)
class Definition(File):
    kind: str = ''
    name: str = ''

    @property
    def directory(self):
        return documents.DIRECTORIES[self.kind]

    @property
    def reference(self):
        return documents.reference(self.directory, self.name)


@dataclass
class Folder:
    """What read_folder found. root is the absolute path of the folder."""
    root: str
    project: File | None = None
    definitions: list = field(default_factory=list)
    results: list = field(default_factory=list)
    notes: frozenset = frozenset()
    problems: list = field(default_factory=list)


class Unsafe(Exception):
    """A file that the format does not allow; the message is one sentence for the owner."""


def read(directory_fd, name, limit):
    """Return the bytes of a regular file, refusing links, other file types and oversize files."""
    try:
        fd = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise Unsafe('This is a symbolic link; replace it with a regular file.') from None
        raise Unsafe(f'The file cannot be opened: {exc.strerror}.') from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Unsafe('This is not a regular file; replace it with one.')
        if info.st_size > limit:
            raise Unsafe(f'The file is {info.st_size} bytes; the limit for this file is {limit} bytes.')
        chunks, size = [], 0
        while size <= limit:
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > limit:
            raise Unsafe(f'The file grew past the limit of {limit} bytes while it was read.')
        return b''.join(chunks)
    finally:
        os.close(fd)


def entries(directory_fd):
    """Return (name, kind) for each entry, sorted; kind is 'file', 'directory', 'link' or 'other'."""
    found = []
    with os.scandir(directory_fd) as listing:
        for entry in listing:
            if entry.is_symlink():
                kind = 'link'
            elif entry.is_dir(follow_symlinks=False):
                kind = 'directory'
            elif entry.is_file(follow_symlinks=False):
                kind = 'file'
            else:
                kind = 'other'
            found.append((entry.name, kind))
    return sorted(found)


def _wrong_type(kind, wanted):
    if kind == 'link':
        return f'This is a symbolic link; replace it with a regular {wanted}.'
    return f'This must be a {wanted}.'


def _load(folder, directory_fd, name, path, limit, *, decode):
    """Read one file into a File, or record why not and return None."""
    try:
        raw = read(directory_fd, name, limit)
    except Unsafe as exc:
        folder.problems.append(Problem('error', path, '', str(exc)))
        return None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        folder.problems.append(Problem('error', path, '', f'The file is not UTF-8 text (bad byte at offset {exc.start}).'))
        return File(path, raw, digest, None, None)
    document = None
    if decode:
        try:
            document = documents.decode(text)
        except documents.DocumentError as exc:
            folder.problems.append(Problem('error', path, '', str(exc)))
    return File(path, raw, digest, text, document)


def _open_directory(folder, parent_fd, name, path):
    try:
        return os.open(name, DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        folder.problems.append(Problem('error', path, '', f'The directory cannot be opened: {exc.strerror}.'))
        return None


def _read_definitions(folder, root_fd, directory):
    fd = _open_directory(folder, root_fd, directory, directory)
    if fd is None:
        return
    kind = documents.KINDS[directory]
    try:
        for name, entry_kind in entries(fd):
            path = f'{directory}/{name}'
            if entry_kind != 'file' or not name.endswith('.json'):
                message = (_wrong_type(entry_kind, 'file') if entry_kind == 'link'
                           else f'{directory}/ may hold only <name>.json files, one definition each; move or remove this.')
                folder.problems.append(Problem('error', path, '', message))
                continue
            stem = name[:-len('.json')]
            if not documents.is_name(stem):
                folder.problems.append(Problem('error', path, '', f'{stem!r} is not a valid name; use lowercase letters, digits, ".", "_" or "-", starting with a letter or digit.'))
                continue
            loaded = _load(folder, fd, name, path, DEFINITION_LIMIT, decode=True)
            if loaded is not None:
                folder.definitions.append(Definition(**vars(loaded), kind=kind, name=stem))
    finally:
        os.close(fd)


def _read_results(folder, root_fd):
    fd = _open_directory(folder, root_fd, RESULTS, RESULTS)
    if fd is None:
        return
    try:
        for name, entry_kind in entries(fd):
            path = f'{RESULTS}/{name}'
            stem = name[:-len('.csv')] if name.endswith('.csv') else None
            if entry_kind != 'file' or stem is None or not documents.is_name(stem):
                message = (_wrong_type(entry_kind, 'file') if entry_kind == 'link'
                           else 'results/ may hold only <benchmark name>.csv files; move or remove this.')
                folder.problems.append(Problem('error', path, '', message))
                continue
            loaded = _load(folder, fd, name, path, RESULTS_LIMIT, decode=False)
            if loaded is not None:
                folder.results.append(loaded)
    finally:
        os.close(fd)


def read_notes(folder, root_fd):
    """Collect the relative paths of every regular file under notes/; contents are not read."""
    found = set()
    top = _open_directory(folder, root_fd, NOTES, NOTES)
    if top is None:
        return
    pending = [(top, NOTES)]
    while pending:
        fd, prefix = pending.pop()
        try:
            for name, entry_kind in entries(fd):
                path = f'{prefix}/{name}'
                if entry_kind == 'file':
                    found.add(path)
                elif entry_kind == 'directory':
                    child = _open_directory(folder, fd, name, path)
                    if child is not None:
                        pending.append((child, path))
                else:
                    folder.problems.append(Problem('error', path, '', _wrong_type(entry_kind, 'file or directory')))
        finally:
            os.close(fd)
    folder.notes = frozenset(found)


def read_folder(path):
    """Read the project folder at path; return a Folder with every file read and every layout problem."""
    root = os.path.abspath(os.fspath(path))
    folder = Folder(root)
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as exc:
        folder.problems.append(Problem('error', '.', '', f'The project folder {root} cannot be opened: {exc.strerror}.'))
        return folder
    try:
        top = dict(entries(root_fd))
        for name, entry_kind in sorted(top.items()):
            if name == PROJECT_FILE or name in OPTIONAL_FILES:
                # README.md and .gitignore are allowed but not read; a link is still refused.
                if entry_kind != 'file':
                    folder.problems.append(Problem('error', name, '', _wrong_type(entry_kind, 'file')))
                elif name == PROJECT_FILE:
                    folder.project = _load(folder, root_fd, name, name, PROJECT_LIMIT, decode=True)
            elif name in documents.KINDS or name in (RESULTS, NOTES):
                if entry_kind != 'directory':
                    folder.problems.append(Problem('error', name, '', _wrong_type(entry_kind, 'directory')))
                elif name == RESULTS:
                    _read_results(folder, root_fd)
                elif name == NOTES:
                    read_notes(folder, root_fd)
                else:
                    _read_definitions(folder, root_fd, name)
            else:
                folder.problems.append(Problem('error', name, '', 'This entry is not part of the project folder format; move it into notes/ or out of the folder.'))
        if PROJECT_FILE not in top:
            folder.problems.append(Problem('error', PROJECT_FILE, '', 'The folder has no tuldok.json; add one with format, id and name.'))
    finally:
        os.close(root_fd)
    return folder
