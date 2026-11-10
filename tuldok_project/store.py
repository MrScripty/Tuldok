"""The database copy of an opened project folder: import, read, edit and save.

Owns sections 4.1, 4.2, 4.4 and 4.5 of
docs/plans/definition-first-projects/spec-m1-m2.md. Each project lives in its own
Postgres schema, project_<id>, holding the exact text and decoded document of
every definition, the uses-graph as an edge table, and which folder the copy is
bound to. Opening imports what changed on disk (after the checker passes) in
one transaction; an unchanged folder attaches by comparing SHA-256 digests
alone. Edits are validated with the checker's own rules and kept in the
database until save() writes them back. States are never stored: they are
computed by graph.states from the documents. A Project keeps no copy of the
definitions in memory and holds a session advisory lock on its project for as
long as it is open, so one Project at a time owns a project's copy.
"""
from dataclasses import dataclass
import hashlib
import os
import re
import tempfile

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from metadata import connection_info

from . import check, documents, folder as folder_reader, graph
from .documents import Problem

PROJECT_ID = re.compile(r'^[a-f0-9]{32}$')
CONFLICT_CHOICES = (None, 'keep', 'discard')

_TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.state (
           singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
           project_id text NOT NULL, name text NOT NULL,
           folder text NOT NULL, code_root text NOT NULL,
           imported_at timestamptz NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS {schema}.definitions (
           directory text NOT NULL, name text NOT NULL,
           kind text NOT NULL, title text NOT NULL,
           text text NOT NULL, document jsonb NOT NULL,
           file_sha256 text,
           unsaved boolean NOT NULL DEFAULT false,
           removed boolean NOT NULL DEFAULT false,
           PRIMARY KEY (directory, name))''',
    '''CREATE TABLE IF NOT EXISTS {schema}.edges (
           from_ref text NOT NULL, to_ref text NOT NULL, role text NOT NULL,
           PRIMARY KEY (from_ref, to_ref, role))''',
    'CREATE INDEX IF NOT EXISTS edges_to ON {schema}.edges (to_ref)',
)
# Later additive changes go here as ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
_MIGRATIONS = ()

_UPSERT = '''INSERT INTO {schema}.definitions
                 (directory, name, kind, title, text, document, file_sha256, unsaved, removed)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false)
             ON CONFLICT (directory, name) DO UPDATE SET
                 kind = EXCLUDED.kind, title = EXCLUDED.title, text = EXCLUDED.text,
                 document = EXCLUDED.document, file_sha256 = EXCLUDED.file_sha256,
                 unsaved = EXCLUDED.unsaved, removed = false'''
_REFERENCE_SQL = "directory || '/' || name"


class ProjectError(Exception):
    """An open, edit or save that was refused; nothing was changed.

    code is one of: invalid (the folder or the edit breaks the format; problems
    lists why), conflict (files changed on disk where the database has unsaved
    edits), bound-elsewhere, busy, in-use, changed-on-disk, not-found.
    references names the definitions concerned.
    """

    def __init__(self, message, code, *, problems=(), references=()):
        super().__init__(message)
        self.code = code
        self.problems = list(problems)
        self.references = list(references)


# ------------------------------------------------------------ small helpers

def _lock_key(schema):
    """The advisory lock key of one project schema (the first 8 bytes of its SHA-256, signed)."""
    return int.from_bytes(hashlib.sha256(schema.encode()).digest()[:8], 'big', signed=True)


def _schema(project_id):
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise ValueError('A project id is 32 lowercase hex characters.')
    return f'project_{project_id}'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _split(reference):
    parsed = documents.parse_reference(reference)
    if parsed is None:
        raise ProjectError(f'{reference!r} is not a reference such as datasets/<name>.', 'not-found',
                           references=[reference])
    return parsed


def _definition(reference, text, document):
    """A folder.Definition built from database content, so the checker's functions accept it."""
    directory, name = documents.parse_reference(reference)
    raw = text.encode('utf-8')
    return folder_reader.Definition(path=f'{reference}.json', raw=raw, sha256=_sha(raw), text=text,
                                    document=document, kind=documents.KINDS[directory], name=name)


def _errors(problems):
    return [problem for problem in problems if problem.severity == 'error']


def _open_root(root):
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)


def _read_project_file(root):
    """Return tuldok.json decoded and schema-valid, or None when the checker must explain why not."""
    try:
        root_fd = _open_root(root)
    except OSError:
        return None
    try:
        raw = folder_reader._read(root_fd, folder_reader.PROJECT_FILE, folder_reader.PROJECT_LIMIT)
        document = documents.decode(raw)
    except (folder_reader._Unsafe, documents.DocumentError):
        return None
    finally:
        os.close(root_fd)
    return None if documents.schema_problems('project', document) else document


@dataclass(frozen=True)
class DiskListing:
    """The definition files on disk: reference -> SHA-256, and paths that are not plain definition files."""
    files: dict
    irregular: tuple


def _list_definitions(root):
    """List the definition files with their SHA-256, without decoding or judging their content.

    Anything the layout rules would refuse (a link, a non-.json entry, a bad
    name, an oversize file) is put in irregular, which sends open() to the checker.
    """
    files, irregular = {}, []
    root_fd = _open_root(root)
    try:
        top = dict(folder_reader._entries(root_fd))
        for directory in documents.KINDS:
            if directory not in top:
                continue
            if top[directory] != 'directory':
                irregular.append(directory)
                continue
            fd = os.open(directory, folder_reader._DIRECTORY_FLAGS, dir_fd=root_fd)
            try:
                for name, entry_kind in folder_reader._entries(fd):
                    path = f'{directory}/{name}'
                    stem = name[:-len('.json')] if name.endswith('.json') else None
                    if entry_kind != 'file' or stem is None or not documents.is_name(stem):
                        irregular.append(path)
                        continue
                    try:
                        raw = folder_reader._read(fd, name, folder_reader.DEFINITION_LIMIT)
                    except folder_reader._Unsafe:
                        irregular.append(path)
                        continue
                    files[documents.reference(directory, stem)] = _sha(raw)
            finally:
                os.close(fd)
    finally:
        os.close(root_fd)
    return DiskListing(files, tuple(irregular))


def _notes(root):
    """The set of note paths, as the checker's card rule needs them."""
    found = folder_reader.Folder(root)
    try:
        root_fd = _open_root(root)
    except OSError:
        return frozenset()
    try:
        if os.path.isdir(os.path.join(root, folder_reader.NOTES)):
            folder_reader._read_notes(found, root_fd)
    finally:
        os.close(root_fd)
    return found.notes


def _cross_problems(merged, unsound=frozenset()):
    """Problems across files (references, named outputs, charts, cycles) for {reference: Definition}."""
    problems = []

    def add(severity, path, pointer, message):
        problems.append(Problem(severity, path, pointer, message))

    check._check_references(merged, add)
    check._check_charts(merged, set(unsound), add)
    check._check_cycles(merged, add)
    return problems


# --------------------------------------------------------------- the store

def drop_project(project_id, dsn=None):
    """Drop a project's schema and everything in it; refused while the project is open."""
    schema = _schema(project_id)
    with psycopg.connect(connection_info(dsn), autocommit=True) as connection:
        if not connection.execute('SELECT pg_try_advisory_lock(%s)', (_lock_key(schema),)).fetchone()[0]:
            raise ProjectError('The project is open in another session; close it first.', 'busy')
        connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))


def open_project(folder, *, rebind=False, on_conflict=None, dsn=None):
    """Open the project folder: attach or import it (section 4.2) and return a Project.

    Raises ProjectError when the folder has check errors (problems carries
    them), when it is bound to another folder and rebind is false, when files
    changed on disk where the database holds unsaved edits and on_conflict is
    neither 'keep' nor 'discard', or when the project is open elsewhere.
    The database is unchanged whenever it raises.
    """
    if on_conflict not in CONFLICT_CHOICES:
        raise ValueError("on_conflict must be None, 'keep' or 'discard'.")
    root = os.path.realpath(os.fspath(folder))
    project = _read_project_file(root)
    if project is None:
        report = check.check_folder(root)
        raise ProjectError(f'The project folder {root} has errors; fix them and open it again.', 'invalid',
                           problems=_errors(report.problems) or report.problems)
    schema = _schema(project['id'])
    connection = psycopg.connect(connection_info(dsn), autocommit=True)
    try:
        if not connection.execute('SELECT pg_try_advisory_lock(%s)', (_lock_key(schema),)).fetchone()[0]:
            raise ProjectError('This project is already open in another session.', 'busy')
        opened = Project(connection, schema)
        opened._attach(root, project, rebind=rebind, on_conflict=on_conflict)
        return opened
    except BaseException:
        connection.close()
        raise


class Project:
    """One open project, bound to one connection; every read goes to the database."""

    def __init__(self, connection, schema):
        self._connection = connection
        self.schema = schema
        self.project_id = schema[len('project_'):]

    # ----------------------------------------------------------- plumbing

    def _sql(self, template):
        return sql.SQL(template).format(schema=sql.Identifier(self.schema))

    def _execute(self, template, parameters=None):
        return self._connection.execute(self._sql(template), parameters)

    def _schema_exists(self):
        return self._connection.execute('SELECT 1 FROM pg_namespace WHERE nspname = %s',
                                        (self.schema,)).fetchone() is not None

    def _create_schema(self):
        self._connection.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
        for statement in (*_TABLES, *_MIGRATIONS):
            self._execute(statement)

    def _state(self):
        row = self._execute('SELECT project_id, name, folder, code_root, imported_at FROM {schema}.state').fetchone()
        if row is None:
            return None
        return dict(zip(('project_id', 'name', 'folder', 'code_root', 'imported_at'), row))

    def _documents(self, *, removed=True):
        """{reference: document} for every row (with removed=False, only rows not removed)."""
        where = '' if removed else ' WHERE NOT removed'
        rows = self._execute(f'SELECT {_REFERENCE_SQL}, document FROM {{schema}}.definitions{where}').fetchall()
        return dict(rows)

    def _merged_definitions(self):
        """{reference: folder.Definition} for every row not removed, decoded from the exact text."""
        rows = self._execute(f'SELECT {_REFERENCE_SQL}, text FROM {{schema}}.definitions WHERE NOT removed').fetchall()
        return {reference: _definition(reference, text, documents.decode(text)) for reference, text in rows}

    def _write_edges(self, rows, references=None):
        """Replace the edges of these source references (all when None) with rows of graph.Edge."""
        if references is None:
            self._execute('DELETE FROM {schema}.edges')
        else:
            self._execute('DELETE FROM {schema}.edges WHERE from_ref = ANY(%s)', (list(references),))
        if rows:
            with self._connection.cursor() as cursor:
                cursor.executemany(self._sql('INSERT INTO {schema}.edges (from_ref, to_ref, role) VALUES (%s, %s, %s)'),
                                   [(edge.from_ref, edge.to_ref, edge.role) for edge in rows])

    # --------------------------------------------------------------- open

    def _attach(self, root, project, *, rebind, on_conflict):
        exists = self._schema_exists()
        if exists:
            with self._connection.transaction():
                self._create_schema()  # brings an older schema up to date; additive only
        state = self._state() if exists else None
        if state is not None and state['folder'] != root and not rebind:
            raise ProjectError(f'This project is bound to {state["folder"]}, not {root}; '
                               'open it with rebind to move it here.', 'bound-elsewhere')
        rows = {}
        if exists:
            for reference, file_sha256, unsaved, removed in self._execute(
                    f'SELECT {_REFERENCE_SQL}, file_sha256, unsaved, removed FROM {{schema}}.definitions'):
                rows[reference] = (file_sha256, unsaved or removed)
        listing = _list_definitions(root)
        on_disk = {reference: sha for reference, (sha, _) in rows.items() if sha is not None}
        code_root = project.get('code_root', '.')
        if (state is not None and not listing.irregular and listing.files == on_disk
                and state['name'] == project['name'] and state['code_root'] == code_root):
            if state['folder'] != root:
                self._execute('UPDATE {schema}.state SET folder = %s', (root,))
            return
        self._import(root, rows, on_conflict)

    def _import(self, root, rows, on_conflict):
        report = check.check_folder(root)
        if not report.ok:
            raise ProjectError(f'The project folder {root} has errors; fix them and open it again.', 'invalid',
                               problems=report.problems)
        if report.project.get('id') != self.project_id:
            raise ProjectError('tuldok.json changed while the folder was being opened; open it again.', 'invalid')
        disk = report.definitions
        take, delete, reseat, conflicts = [], [], [], []
        for reference in sorted(set(disk) | set(rows)):
            disk_sha = disk[reference].sha256 if reference in disk else None
            row_sha, pending = rows.get(reference, (None, False))
            if disk_sha == row_sha:
                continue
            if pending:
                conflicts.append(reference)
                if on_conflict == 'keep':
                    reseat.append((reference, disk_sha))
                    continue
            (take if disk_sha is not None else delete).append(reference)
        if conflicts and on_conflict is None:
            raise ProjectError('These definitions changed on disk and also have unsaved edits here: '
                               + ', '.join(conflicts) + '. Open again keeping or discarding the edits.',
                               'conflict', references=conflicts)

        # The project as it will be: the folder, with the unsaved edits the database keeps.
        merged = dict(disk)
        kept = self._execute(f'SELECT {_REFERENCE_SQL}, text, removed FROM {{schema}}.definitions '
                             'WHERE unsaved OR removed').fetchall() if self._schema_exists() else []
        kept = [(reference, text, removed) for reference, text, removed in kept if reference not in take
                and reference not in delete]
        for reference, text, removed in kept:
            if removed:
                merged.pop(reference, None)
            else:
                merged[reference] = _definition(reference, text, documents.decode(text))
        if kept:
            problems = _errors(_cross_problems(merged))
            if problems:
                raise ProjectError('The folder no longer fits the unsaved edits held here; '
                                   'save or discard them first.', 'invalid', problems=problems)

        project = report.project
        with self._connection.transaction():
            self._create_schema()
            with self._connection.cursor() as cursor:
                if take:
                    cursor.executemany(self._sql(_UPSERT), [
                        (*documents.parse_reference(reference), disk[reference].kind, disk[reference].document['title'],
                         disk[reference].text, Jsonb(disk[reference].document), disk[reference].sha256, False)
                        for reference in take])
                if delete:
                    cursor.executemany(self._sql('DELETE FROM {schema}.definitions WHERE directory = %s AND name = %s'),
                                       [documents.parse_reference(reference) for reference in delete])
                if reseat:
                    cursor.executemany(self._sql('UPDATE {schema}.definitions SET file_sha256 = %s '
                                                 'WHERE directory = %s AND name = %s'),
                                       [(sha, *documents.parse_reference(reference)) for reference, sha in reseat])
            self._write_edges(graph.edges({reference: d.document for reference, d in merged.items()}))
            self._execute('''INSERT INTO {schema}.state (singleton, project_id, name, folder, code_root, imported_at)
                             VALUES (true, %s, %s, %s, %s, now())
                             ON CONFLICT (singleton) DO UPDATE SET project_id = EXCLUDED.project_id,
                                 name = EXCLUDED.name, folder = EXCLUDED.folder,
                                 code_root = EXCLUDED.code_root, imported_at = EXCLUDED.imported_at''',
                          (self.project_id, project['name'], root, project.get('code_root', '.')))

    # ------------------------------------------------------------ reading

    def summary(self):
        """Project id, name, folder, code root, and counts per kind and per state (removed rows not counted)."""
        state = self._state()
        rows = self._execute('SELECT kind, count(*) FROM {schema}.definitions WHERE NOT removed GROUP BY kind').fetchall()
        states = {}
        for value in graph.states(self._documents(removed=False)).values():
            states[value] = states.get(value, 0) + 1
        return {'project_id': state['project_id'], 'name': state['name'], 'folder': state['folder'],
                'code_root': state['code_root'], 'kinds': dict(sorted(rows)), 'states': dict(sorted(states.items()))}

    def definitions(self, kind=None):
        """One row per definition, sorted by reference: reference, kind, title, state, unsaved, removed."""
        states = graph.states(self._documents())
        query = f'SELECT {_REFERENCE_SQL}, kind, title, unsaved, removed FROM {{schema}}.definitions'
        rows = (self._execute(query + ' WHERE kind = %s', (kind,)) if kind is not None else self._execute(query)).fetchall()
        return [{'reference': reference, 'kind': row_kind, 'title': title, 'state': states[reference],
                 'unsaved': unsaved, 'removed': removed}
                for reference, row_kind, title, unsaved, removed in sorted(rows)]

    def definition(self, reference):
        """The text, document and state of one definition, what it uses and what uses it (with roles)."""
        directory, name = _split(reference)
        row = self._execute('SELECT kind, title, text, document, unsaved, removed FROM {schema}.definitions '
                            'WHERE directory = %s AND name = %s', (directory, name)).fetchone()
        if row is None:
            raise ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
        kind, title, text, document, unsaved, removed = row
        uses = self._execute('SELECT to_ref, role FROM {schema}.edges WHERE from_ref = %s ORDER BY to_ref, role',
                             (reference,)).fetchall()
        used_by = self._execute('SELECT from_ref, role FROM {schema}.edges WHERE to_ref = %s ORDER BY from_ref, role',
                                (reference,)).fetchall()
        return {'reference': reference, 'kind': kind, 'title': title, 'text': text, 'document': document,
                'state': graph.states(self._documents())[reference], 'unsaved': unsaved, 'removed': removed,
                'uses': [{'reference': target, 'role': role} for target, role in uses],
                'used_by': [{'reference': source, 'role': role} for source, role in used_by]}

    def graph(self):
        """The definitions not removed, with kind and state, and the edges between them."""
        nodes = self._execute(f'SELECT {_REFERENCE_SQL}, kind FROM {{schema}}.definitions WHERE NOT removed').fetchall()
        states = graph.states(self._documents(removed=False))
        edges = self._execute('SELECT from_ref, to_ref, role FROM {schema}.edges ORDER BY 1, 2, 3').fetchall()
        return {'nodes': [{'reference': reference, 'kind': kind, 'state': states[reference]}
                          for reference, kind in sorted(nodes)],
                'edges': [{'from': source, 'to': target, 'role': role} for source, target, role in edges]}

    def order(self):
        """The references not removed, each after everything it uses (graph.order)."""
        return graph.order(self._documents(removed=False))

    def status(self):
        """Unsaved and removed definitions, and files added, changed or missing on disk since the last import or save."""
        state = self._state()
        rows = self._execute(f'SELECT {_REFERENCE_SQL}, file_sha256, unsaved, removed FROM {{schema}}.definitions').fetchall()
        listing = _list_definitions(state['folder'])
        recorded = {reference: sha for reference, sha, _, _ in rows if sha is not None}
        return {'unsaved': sorted(reference for reference, _, unsaved, removed in rows if unsaved and not removed),
                'removed': sorted(reference for reference, _, _, removed in rows if removed),
                'added': sorted(set(listing.files) - set(recorded)),
                'changed': sorted(reference for reference, sha in listing.files.items()
                                  if reference in recorded and recorded[reference] != sha),
                'missing': sorted(set(recorded) - set(listing.files)),
                'irregular': list(listing.irregular)}

    # ------------------------------------------------------------ editing

    def set_definition(self, reference, text):
        """Validate text as the definition at reference and store it as an unsaved edit (4.4).

        It is checked alone (strict JSON, schema, kind against directory, card,
        placeholders, paths into the code root) and against the project as it
        would then be (references, named outputs, charts, cycles). Raises
        ProjectError with code 'invalid' and the problems, changing nothing,
        when any error is found.
        """
        directory, name = _split(reference)
        path = f'{reference}.json'
        try:
            document = documents.decode(text)
        except documents.DocumentError as exc:
            raise ProjectError(f'{reference} is not valid: {exc}', 'invalid',
                               problems=[Problem('error', path, '', str(exc))]) from None
        state = self._state()
        candidate = _definition(reference, text, document)
        problems = []

        def add(severity, where, pointer, message):
            problems.append(Problem(severity, where, pointer, message))

        check._check_definition(candidate, _notes(state['folder']), add)
        code_root = os.path.realpath(os.path.join(state['folder'], state['code_root']))
        check._check_code_paths(candidate, code_root if os.path.isdir(code_root) else None, add)
        alone = _errors(problems)
        with self._connection.transaction():
            merged = self._merged_definitions()
            merged[reference] = candidate
            errors = alone + _errors(_cross_problems(merged, {path} if alone else ()))
            if errors:
                raise ProjectError(f'{reference} cannot be set; see the problems.', 'invalid', problems=errors,
                                   references=[reference])
            self._execute('''INSERT INTO {schema}.definitions
                                 (directory, name, kind, title, text, document, unsaved, removed)
                             VALUES (%s, %s, %s, %s, %s, %s, true, false)
                             ON CONFLICT (directory, name) DO UPDATE SET
                                 kind = EXCLUDED.kind, title = EXCLUDED.title, text = EXCLUDED.text,
                                 document = EXCLUDED.document, removed = false,
                                 unsaved = {schema}.definitions.unsaved OR {schema}.definitions.removed
                                           OR {schema}.definitions.text IS DISTINCT FROM EXCLUDED.text''',
                          (directory, name, candidate.kind, document['title'], text, Jsonb(document)))
            self._write_edges(graph.edges({reference: document}), [reference])

    def remove_definition(self, reference):
        """Mark a definition removed, to be deleted from disk by save(); refused while anything uses it."""
        directory, name = _split(reference)
        with self._connection.transaction():
            row = self._execute('SELECT file_sha256 FROM {schema}.definitions '
                                'WHERE directory = %s AND name = %s AND NOT removed FOR UPDATE',
                                (directory, name)).fetchone()
            if row is None:
                raise ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
            users = [source for (source,) in self._execute(
                'SELECT DISTINCT from_ref FROM {schema}.edges WHERE to_ref = %s ORDER BY 1', (reference,))]
            if users:
                raise ProjectError(f'{reference} is used by {", ".join(users)}; change those first.', 'in-use',
                                   references=users)
            if row[0] is None:
                # Never written to disk: there is no file for save() to delete.
                self._execute('DELETE FROM {schema}.definitions WHERE directory = %s AND name = %s', (directory, name))
            else:
                self._execute('UPDATE {schema}.definitions SET removed = true WHERE directory = %s AND name = %s',
                              (directory, name))
            self._write_edges([], [reference])

    def save(self):
        """Write unsaved definitions to their files and delete the files of removed ones (4.4).

        Before anything is written, every file to be replaced or deleted must
        still have the SHA-256 recorded at import or last save (or already hold
        exactly the text to be written, which is what an interrupted save
        leaves). Otherwise nothing is written and ProjectError (code
        changed-on-disk) names them. Returns the references written and deleted.
        """
        root = self._state()['folder']
        rows = self._execute(f'SELECT {_REFERENCE_SQL}, text, file_sha256, removed FROM {{schema}}.definitions '
                             'WHERE unsaved OR removed ORDER BY 1').fetchall()
        changed = []
        for reference, text, file_sha256, removed in rows:
            current = _file_sha(root, reference)
            done = None if removed else _sha(text.encode('utf-8'))
            if current != file_sha256 and current != done:
                changed.append(reference)
        if changed:
            raise ProjectError('These files changed on disk since they were imported: ' + ', '.join(changed)
                               + '. Open the project again to take or keep the changes.', 'changed-on-disk',
                               references=changed)
        written, deleted = [], []
        for reference, text, _, removed in rows:
            if removed:
                _delete_file(root, reference)
                deleted.append(reference)
            else:
                _write_file(root, reference, text.encode('utf-8'))
                written.append(reference)
        with self._connection.transaction():
            with self._connection.cursor() as cursor:
                if written:
                    cursor.executemany(self._sql('UPDATE {schema}.definitions SET unsaved = false, '
                                                 'file_sha256 = encode(sha256(convert_to(text, \'UTF8\')), \'hex\') '
                                                 'WHERE directory = %s AND name = %s'),
                                       [documents.parse_reference(reference) for reference in written])
                if deleted:
                    cursor.executemany(self._sql('DELETE FROM {schema}.definitions WHERE directory = %s AND name = %s'),
                                       [documents.parse_reference(reference) for reference in deleted])
        return {'written': written, 'deleted': deleted}

    def close(self):
        """Close the connection, which also releases the project's lock."""
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --------------------------------------------------------------- files

def _file_sha(root, reference):
    """SHA-256 of the definition file on disk, None when it does not exist, 'unreadable' when it is not a plain file."""
    directory, name = documents.parse_reference(reference)
    try:
        fd = os.open(os.path.join(root, directory), folder_reader._DIRECTORY_FLAGS)
    except FileNotFoundError:
        return None
    except OSError:
        return 'unreadable'
    try:
        return _sha(folder_reader._read(fd, f'{name}.json', folder_reader.DEFINITION_LIMIT))
    except folder_reader._Unsafe:
        if not os.path.lexists(os.path.join(root, directory, f'{name}.json')):
            return None
        return 'unreadable'
    finally:
        os.close(fd)


def _write_file(root, reference, data):
    """Replace the file atomically: a temporary file in the same directory, fsync, rename, fsync the directory."""
    directory, name = documents.parse_reference(reference)
    target_directory = os.path.join(root, directory)
    os.makedirs(target_directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target_directory, prefix=f'.{name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, os.path.join(target_directory, f'{name}.json'))
    except BaseException:
        if os.path.lexists(temporary):
            os.unlink(temporary)
        raise
    _sync_directory(target_directory)


def _delete_file(root, reference):
    directory, name = documents.parse_reference(reference)
    target_directory = os.path.join(root, directory)
    try:
        os.unlink(os.path.join(target_directory, f'{name}.json'))
    except FileNotFoundError:
        return
    _sync_directory(target_directory)


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
