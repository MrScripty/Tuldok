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
Benchmark results (spec-m3.md) live in three more tables owned by result_rows:
results files are part of what open compares and imports, and save writes
them back when the database's summaries make a different text.
Which interpreter fulfils each environment on this machine (spec-m5.md) lives
in one more table owned by environments; the states reported here take the
environments' stored check results, and an environment's record goes when
its definition does.
What was built (spec-m6.md) lives in three more tables owned by builds: the
states reported here take the build states (built, out-of-date, running,
failed) from them, and a definition's runs and products records go when the
definition does (the files on disk are left).
The record of changes asked through the service (spec-m7.md section 5) lives
in one more table owned by activity, and the build requests (section 4) in
one owned by build_requests.
Annotations (spec-d4.md sections 3 and 4) live in three more tables owned by
annotation_rows and follow the definitions' pattern row by row: a task's line
file is imported when it changed on disk (its size and time are compared
before it is hashed), an unsaved row whose saved line the file changes is a
conflict, status counts the unsaved rows without writing a file, and save
writes each task's file that has unsaved rows, whole.
The state row also keeps tuldok.json as last imported (spec-w1.md: the map's
groups and track are read from it); a change to it alone imports the folder
again, and the chart its map.chart names cannot be removed.
revert_definition (spec-w3.md section 2) undoes an unsaved edit or a removed
mark from the folder's file, and definition_problems says what set_definition
would say of a text without storing it; both check with set_definition's code.
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

from . import (activity, annotation_rows, annotations, build_requests, builds, check, documents, environments,
               folder as folder_reader, graph, result_rows, results)
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
    *result_rows.TABLES,
    *annotation_rows.TABLES,
)
# Later additive changes go here as ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
# state.project: tuldok.json as last imported, for the map's groups and track (spec-w1.md).
_MIGRATIONS = ('ALTER TABLE {schema}.state ADD COLUMN IF NOT EXISTS project jsonb',)

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
    edits), bound-elsewhere, busy, in-use, changed-on-disk, not-found,
    nothing-to-revert (revert_definition); and for
    environments (environments.py): not-set-up (nothing is recorded for it),
    no-install, no-installer, target-exists, install-failed; and for builds
    (builds.py): blocked, running, not-ready, and a snapshot.SnapshotError's
    code (dirty, not-in-git, ...), whose files names the changed files; and
    settings, which host.py raises for a local.SettingsError. references names the definitions concerned.
    """

    def __init__(self, message, code, *, problems=(), references=(), files=()):
        super().__init__(message)
        self.code = code
        self.problems = list(problems)
        self.references = list(references)
        self.files = list(files)


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
        raw = folder_reader.read(root_fd, folder_reader.PROJECT_FILE, folder_reader.PROJECT_LIMIT)
        document = documents.decode(raw)
    except (folder_reader.Unsafe, documents.DocumentError):
        return None
    finally:
        os.close(root_fd)
    return None if documents.schema_problems('project', document) else document


@dataclass(frozen=True)
class DiskListing:
    """The definition files on disk: reference -> SHA-256, paths that are not plain definition files, and the
    tasks' line files: task name -> (size, mtime in nanoseconds), which are not read here."""
    files: dict
    irregular: tuple
    lines: dict


def _list_definitions(root):
    """List the definition files with their SHA-256, without decoding or judging their content.

    Anything the layout rules would refuse (a link, a non-.json entry, a bad
    name, an oversize file) is put in irregular, which sends open() to the checker.
    A task's annotations/<name>.jsonl beside its <name>.json is not a
    definition file: its size and time go in lines; one without its task is
    irregular.
    """
    files, irregular, lines = {}, [], {}
    root_fd = _open_root(root)
    try:
        top = dict(folder_reader.entries(root_fd))
        for directory in documents.KINDS:
            if directory not in top:
                continue
            if top[directory] != 'directory':
                irregular.append(directory)
                continue
            fd = os.open(directory, folder_reader.DIRECTORY_FLAGS, dir_fd=root_fd)
            try:
                listed = folder_reader.entries(fd)
                tasks = {name for name, entry_kind in listed if entry_kind == 'file'}
                for name, entry_kind in listed:
                    path = f'{directory}/{name}'
                    if (directory == folder_reader.ANNOTATIONS and name.endswith(folder_reader.LINES_SUFFIX)
                            and entry_kind == 'file'
                            and name[:-len(folder_reader.LINES_SUFFIX)] + '.json' in tasks):
                        # a task's annotations (spec-d4.md section 2): not a definition file, and not read here
                        try:
                            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                        except FileNotFoundError:
                            continue
                        lines[name[:-len(folder_reader.LINES_SUFFIX)]] = (info.st_size, info.st_mtime_ns)
                        continue
                    stem = name[:-len('.json')] if name.endswith('.json') else None
                    if entry_kind != 'file' or stem is None or not documents.is_name(stem):
                        irregular.append(path)
                        continue
                    try:
                        raw = folder_reader.read(fd, name, folder_reader.DEFINITION_LIMIT)
                    except folder_reader.Unsafe:
                        irregular.append(path)
                        continue
                    files[documents.reference(directory, stem)] = _sha(raw)
            finally:
                os.close(fd)
    finally:
        os.close(root_fd)
    return DiskListing(files, tuple(irregular), lines)


def _list_results(root):
    """The results files on disk: ({benchmark name: bytes}, paths that are not plain results files)."""
    files, irregular = {}, []
    root_fd = _open_root(root)
    try:
        top = dict(folder_reader.entries(root_fd))
        if folder_reader.RESULTS not in top:
            return files, ()
        if top[folder_reader.RESULTS] != 'directory':
            return files, (folder_reader.RESULTS,)
        fd = os.open(folder_reader.RESULTS, folder_reader.DIRECTORY_FLAGS, dir_fd=root_fd)
        try:
            for name, entry_kind in folder_reader.entries(fd):
                stem = name[:-len('.csv')] if name.endswith('.csv') else None
                if entry_kind != 'file' or stem is None or not documents.is_name(stem):
                    irregular.append(f'{folder_reader.RESULTS}/{name}')
                    continue
                try:
                    files[stem] = folder_reader.read(fd, name, folder_reader.RESULTS_LIMIT)
                except folder_reader.Unsafe:
                    irregular.append(f'{folder_reader.RESULTS}/{name}')
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)
    return files, tuple(irregular)


def _results_path(benchmark):
    return f'{folder_reader.RESULTS}/{benchmark}.csv'


def _notes(root):
    """The set of note paths, as the checker's card rule needs them."""
    found = folder_reader.Folder(root)
    try:
        root_fd = _open_root(root)
    except OSError:
        return frozenset()
    try:
        if os.path.isdir(os.path.join(root, folder_reader.NOTES)):
            folder_reader.read_notes(found, root_fd)
    finally:
        os.close(root_fd)
    return found.notes


def _cross_problems(merged, unsound=frozenset(), project=None):
    """Problems across files (references, named outputs, charts, cycles, the map's fields) for {reference: Definition}.

    project is the decoded tuldok.json; without it the map rules that need it are skipped.
    """
    problems = []

    def add(severity, path, pointer, message):
        problems.append(Problem(severity, path, pointer, message))

    check.check_references(merged, add)
    check.check_serve(merged, add)
    check.check_charts(merged, set(unsound), add)
    check.check_cycles(merged, add)
    check.check_map(project, merged, add)
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
        for statement in (*_TABLES, *environments.TABLES, *builds.TABLES, *activity.TABLES, *build_requests.TABLES,
                          *_MIGRATIONS):
            self._execute(statement)

    def _state(self):
        row = self._execute('SELECT project_id, name, folder, code_root, imported_at, project '
                            'FROM {schema}.state').fetchone()
        if row is None:
            return None
        return dict(zip(('project_id', 'name', 'folder', 'code_root', 'imported_at', 'project'), row))

    def _documents(self, *, removed=True):
        """{reference: document} for every row (with removed=False, only rows not removed)."""
        where = '' if removed else ' WHERE NOT removed'
        rows = self._execute(f'SELECT {_REFERENCE_SQL}, document FROM {{schema}}.definitions{where}').fetchall()
        return dict(rows)

    def _local_states(self):
        """{reference: state} recorded on this machine, for graph.states(local=...).

        The environments' check results, and the build states of datasets,
        recipes, steps and benchmarks (builds.local_states).
        """
        return {**environments.recorded_states(self._connection, self.schema), **builds.local_states(self)}

    def _states(self, *, removed=True):
        return graph.states(self._documents(removed=removed), self._local_states())

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
        rows, recorded_results, recorded_lines = {}, {}, {}
        if exists:
            for reference, file_sha256, unsaved, removed in self._execute(
                    f'SELECT {_REFERENCE_SQL}, file_sha256, unsaved, removed FROM {{schema}}.definitions'):
                rows[reference] = (file_sha256, unsaved or removed)
            recorded_results = dict(self._execute('SELECT benchmark, file_sha256 FROM {schema}.results_files'))
            recorded_lines = annotation_rows.recorded_files(self._connection, self.schema)
        listing = _list_definitions(root)
        results_on_disk, results_irregular = _list_results(root)
        on_disk = {reference: sha for reference, (sha, _) in rows.items() if sha is not None}
        code_root = project.get('code_root', '.')
        if (state is not None and not listing.irregular and listing.files == on_disk
                and not results_irregular
                and {name: _sha(raw) for name, raw in results_on_disk.items()} == recorded_results
                and state['name'] == project['name'] and state['code_root'] == code_root
                and state['project'] == project):
            touched = _touched_lines(root, listing.lines, recorded_lines)
            if touched is not None:
                with self._connection.transaction():
                    for name, (sha, size, mtime) in touched.items():
                        annotation_rows.record_file(self._connection, self.schema, name, sha, size, mtime)
                    if state['folder'] != root:
                        self._execute('UPDATE {schema}.state SET folder = %s', (root,))
                return
        self._import(root, rows, on_conflict, results_on_disk, recorded_results, recorded_lines, listing.lines)

    def _import(self, root, rows, on_conflict, results_on_disk, recorded_results, recorded_lines, disk_lines):
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
        exists = self._schema_exists()
        lines_plan, touched = self._lines_to_import(root, disk, recorded_lines, disk_lines, exists)
        unsaved_rows = annotation_rows.unsaved_counts(self._connection, self.schema) if exists else {}
        line_conflicts = []
        for name, item in lines_plan.items():
            if item['lines'] is not None and item['comparison'].contested:
                line_conflicts.append(annotation_rows.path(name))
        tasks_gone = sorted(documents.parse_reference(reference)[1] for reference in delete
                            if reference.startswith(annotation_rows.DIRECTORY + '/'))
        for name in tasks_gone:
            if unsaved_rows.get(name) and annotation_rows.path(name) not in line_conflicts:
                line_conflicts.append(annotation_rows.path(name))
        line_conflicts.sort()
        if (conflicts or line_conflicts) and on_conflict is None:
            named = conflicts + line_conflicts
            raise ProjectError('These definitions or annotations changed on disk and also have unsaved edits here: '
                               + ', '.join(named) + '. Open again keeping or discarding the edits.',
                               'conflict', references=named)
        kept_gone = [annotation_rows.path(name) for name in tasks_gone if unsaved_rows.get(name)]
        if kept_gone and on_conflict == 'keep':
            raise ProjectError('These annotations have unsaved edits here, but their task was removed from the '
                               'folder: ' + ', '.join(kept_gone) + '. Open again discarding the edits, or put the '
                               'task back in the folder.', 'invalid', references=kept_gone)

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
            problems = _errors(_cross_problems(merged, project=report.project))
            if problems:
                raise ProjectError('The folder no longer fits the unsaved edits held here; '
                                   'save or discard them first.', 'invalid', problems=problems)

        changed_results, gone_results = self._results_to_import(disk, merged, results_on_disk, recorded_results)

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
            for reference in delete:
                directory, name = documents.parse_reference(reference)
                builds.forget(self._connection, self.schema, reference)
                if directory == 'benchmarks':
                    result_rows.remove_benchmark(self._connection, self.schema, name)
                if directory == environments.DIRECTORY:
                    environments.forget(self._connection, self.schema, name)
                if directory == annotation_rows.DIRECTORY:
                    annotation_rows.forget_task(self._connection, self.schema, name)
            for name, (sha, size, mtime) in touched.items():
                annotation_rows.record_file(self._connection, self.schema, name, sha, size, mtime)
            for name, item in lines_plan.items():
                if name in tasks_gone:
                    continue
                comparison, lines = item['comparison'], item['lines']
                taken, reseated = list(comparison.take), []
                if lines is None or on_conflict == 'keep':
                    reseated = comparison.contested
                else:
                    taken += [record for record, _ in comparison.contested]
                task = merged.get(annotation_rows.reference(name))
                annotation_rows.apply_import(self._connection, self.schema, name, lines,
                                             task.document if task is not None else None, taken, reseated)
                if lines is None:
                    annotation_rows.forget_file(self._connection, self.schema, name)
                else:
                    annotation_rows.record_file(self._connection, self.schema, name, *item['stamp'])
            for reference in take:
                directory, name = documents.parse_reference(reference)
                if directory == 'benchmarks' and reference in merged:
                    result_rows.prune(self._connection, self.schema, name, merged[reference].document)
            for name in gone_results:
                result_rows.forget_file(self._connection, self.schema, name)
            for name, text in changed_results.items():
                result_rows.import_file(self._connection, self.schema, name, text,
                                        merged[documents.reference('benchmarks', name)].document)
            self._execute('''INSERT INTO {schema}.state (singleton, project_id, name, folder, code_root, imported_at,
                                                         project)
                             VALUES (true, %s, %s, %s, %s, now(), %s)
                             ON CONFLICT (singleton) DO UPDATE SET project_id = EXCLUDED.project_id,
                                 name = EXCLUDED.name, folder = EXCLUDED.folder,
                                 code_root = EXCLUDED.code_root, imported_at = EXCLUDED.imported_at,
                                 project = EXCLUDED.project''',
                          (self.project_id, project['name'], root, project.get('code_root', '.'), Jsonb(project)))

    def _lines_to_import(self, root, disk, recorded, disk_lines, exists):
        """({task name: {lines, comparison, stamp}} of line files new, changed or gone, {name: (sha, size, mtime)}
        of those whose size or time alone changed).

        A file whose size and time are those recorded is not read. One that is
        read is checked again against its task in the folder (it may have
        changed since the checker read it); an error refuses the open invalid.
        lines is {record: (the line as it is in the file, its row)}, or None
        for a file that is gone; stamp is (sha256, size, mtime_ns).
        """
        plan, touched, problems = {}, {}, []
        for name in sorted(set(disk_lines) | set(recorded)):
            known = recorded.get(name)
            if name not in disk_lines:
                plan[name] = {'lines': None, 'stamp': None,
                              'comparison': annotation_rows.compare(self._connection, self.schema, name, None)}
                continue
            if known is not None and tuple(known[1:]) == disk_lines[name]:
                continue
            where = annotation_rows.path(name)
            try:
                found = _read_lines(root, name)
            except folder_reader.Unsafe as exc:
                raise ProjectError(f'{where} cannot be read; fix it and open the project again.', 'invalid',
                                   problems=[Problem('error', where, '', str(exc))]) from None
            if found is None:
                if known is not None:
                    plan[name] = {'lines': None, 'stamp': None,
                                  'comparison': annotation_rows.compare(self._connection, self.schema, name, None)}
                continue
            raw, size, mtime = found
            sha = _sha(raw)
            if known is not None and sha == known[0]:
                touched[name] = (sha, size, mtime)
                continue
            task = disk.get(annotation_rows.reference(name))
            if task is None or not isinstance(task.document, dict):
                problems.append(Problem('error', where, '', f'There is no {annotation_rows.reference(name)}.json, '
                                                            'the task of these annotations.'))
                continue
            parsed = annotations.read(raw, task.document.get('task'), task.document.get('vocabulary', []))
            errors = [Problem(item.severity, where, item.pointer, item.message)
                      for item in parsed.reported() if item.severity == 'error']
            if errors:
                problems.extend(errors)
                continue
            pieces = raw.decode('utf-8').split('\n')
            lines = {}
            for number, row in parsed.rows:
                if annotation_rows.has_nul(row):
                    problems.append(Problem('error', where, f'line {number}', 'The line holds the character U+0000, '
                                                                              'which Tuldok cannot keep; remove it.'))
                lines[row['record']] = (pieces[number - 1], row)
            comparison = (annotation_rows.compare(self._connection, self.schema, name, lines) if exists
                          else annotation_rows.Comparison(take=list(lines)))
            plan[name] = {'lines': lines, 'stamp': (sha, size, mtime), 'comparison': comparison}
        if problems:
            raise ProjectError('A file of annotations changed while the folder was being opened, or holds what '
                               'Tuldok cannot keep; fix it and open the project again.', 'invalid', problems=problems)
        return plan, touched

    def _results_to_import(self, disk, merged, results_on_disk, recorded_results):
        """({benchmark: text} of new or changed results files, [benchmarks whose file is gone]).

        The files were read after the checker ran, so each is checked again
        against its benchmark; a file that changed in between and is now wrong
        refuses the open. A file whose benchmark is removed in the database
        (not yet saved) is not imported.
        """
        changed, problems = {}, []
        for name, raw in sorted(results_on_disk.items()):
            reference = documents.reference('benchmarks', name)
            if _sha(raw) == recorded_results.get(name) or reference not in merged:
                continue
            found = [Problem(severity, _results_path(name), pointer, message)
                     for severity, pointer, message in results.check_results(
                         raw, disk[reference].document if reference in disk else None)]
            if reference not in disk:
                found.append(Problem('error', _results_path(name), '', f'There is no {reference}.json for this summary.'))
            if _errors(found):
                problems.extend(_errors(found))
                continue
            changed[name] = raw.decode('utf-8')
        if problems:
            raise ProjectError('A results file changed while the folder was being opened; open it again.', 'invalid',
                               problems=problems)
        gone = sorted(set(recorded_results) - set(results_on_disk))
        return changed, gone

    # ------------------------------------------------------------ reading

    def summary(self):
        """Project id, name, folder, code root, and counts per kind and per state (removed rows not counted)."""
        state = self._state()
        rows = self._execute('SELECT kind, count(*) FROM {schema}.definitions WHERE NOT removed GROUP BY kind').fetchall()
        states = {}
        for value in self._states(removed=False).values():
            states[value] = states.get(value, 0) + 1
        return {'project_id': state['project_id'], 'name': state['name'], 'folder': state['folder'],
                'code_root': state['code_root'], 'kinds': dict(sorted(rows)), 'states': dict(sorted(states.items()))}

    def definitions(self, kind=None):
        """One row per definition, sorted by reference: reference, kind, title, state, unsaved, removed."""
        states = self._states()
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
                'state': self._states()[reference], 'unsaved': unsaved, 'removed': removed,
                'uses': [{'reference': target, 'role': role} for target, role in uses],
                'used_by': [{'reference': source, 'role': role} for source, role in used_by]}

    def graph(self):
        """The definitions not removed, with kind and state, and the edges between them."""
        nodes = self._execute(f'SELECT {_REFERENCE_SQL}, kind FROM {{schema}}.definitions WHERE NOT removed').fetchall()
        states = self._states(removed=False)
        edges = self._execute('SELECT from_ref, to_ref, role FROM {schema}.edges ORDER BY 1, 2, 3').fetchall()
        return {'nodes': [{'reference': reference, 'kind': kind, 'state': states[reference]}
                          for reference, kind in sorted(nodes)],
                'edges': [{'from': source, 'to': target, 'role': role} for source, target, role in edges]}

    def order(self):
        """The references not removed, each after everything it uses (graph.order)."""
        return graph.order(self._documents(removed=False))

    def status(self):
        """Unsaved and removed definitions, and files added, changed or missing on disk since the last import or save.

        results_unsaved names the benchmarks whose summaries in the database
        are not the results file as last imported or saved (save would write
        or remove it); results_changed names the results files added, changed
        or removed on disk since then.
        annotations_unsaved is [{task, records}]: per task (its reference), how
        many records have an unsaved change; annotations_changed names the line
        files added, changed or removed on disk since then, by size and time
        alone. Neither renders nor reads a line file.
        """
        state = self._state()
        rows = self._execute(f'SELECT {_REFERENCE_SQL}, file_sha256, unsaved, removed FROM {{schema}}.definitions').fetchall()
        listing = _list_definitions(state['folder'])
        recorded = {reference: sha for reference, sha, _, _ in rows if sha is not None}
        texts = result_rows.file_texts(self._connection, self.schema)
        results_on_disk, results_irregular = _list_results(state['folder'])
        results_recorded = {name: recorded_sha for name, (_, recorded_sha) in texts.items() if recorded_sha is not None}
        results_changed = sorted(
            _results_path(name) for name in set(results_on_disk) | set(results_recorded)
            if (_sha(results_on_disk[name]) if name in results_on_disk else None) != results_recorded.get(name))
        return {'unsaved': sorted(reference for reference, _, unsaved, removed in rows if unsaved and not removed),
                'removed': sorted(reference for reference, _, _, removed in rows if removed),
                'added': sorted(set(listing.files) - set(recorded)),
                'changed': sorted(reference for reference, sha in listing.files.items()
                                  if reference in recorded and recorded[reference] != sha),
                'missing': sorted(set(recorded) - set(listing.files)),
                'irregular': list(listing.irregular) + list(results_irregular),
                'results_unsaved': [name for name, (text, recorded_sha) in texts.items()
                                    if result_rows.differs(text, recorded_sha)],
                'results_changed': results_changed,
                'annotations_unsaved': [{'task': annotation_rows.reference(name), 'records': count}
                                        for name, count in annotation_rows.unsaved_counts(self._connection,
                                                                                          self.schema).items()],
                'annotations_changed': _lines_changed(listing.lines, annotation_rows.recorded_files(
                    self._connection, self.schema))}

    # ------------------------------------------------------------ editing

    def _text_problems(self, reference, text, state):
        """(document, problems): every error and warning set_definition finds in text at reference.

        document is None when text is not a strict JSON object (problems then
        holds that one error). It is checked alone (strict JSON, schema, kind
        against directory, card, placeholders, paths into the code root) and
        against the project as it would then be (references, named outputs,
        charts, cycles); the caller holds the transaction that reads the project.
        """
        path = f'{reference}.json'
        try:
            document = documents.decode(text)
        except documents.DocumentError as exc:
            return None, [Problem('error', path, '', str(exc))]
        candidate = _definition(reference, text, document)
        problems = []

        def add(severity, where, pointer, message):
            problems.append(Problem(severity, where, pointer, message))

        check.check_definition(candidate, _notes(state['folder']), add)
        code_root = os.path.realpath(os.path.join(state['folder'], state['code_root']))
        check.check_code_paths(candidate, code_root if os.path.isdir(code_root) else None, add)
        alone = bool(_errors(problems))
        merged = self._merged_definitions()
        merged[reference] = candidate
        return document, problems + _cross_problems(merged, {path} if alone else (), state['project'])

    def definition_problems(self, reference, text):
        """The errors and warnings set_definition would find in text at reference; nothing is stored."""
        _split(reference)
        state = self._state()
        with self._connection.transaction():
            return self._text_problems(reference, text, state)[1]

    def set_definition(self, reference, text):
        """Validate text as the definition at reference and store it as an unsaved edit (4.4).

        It is checked by _text_problems. Raises ProjectError with code
        'invalid' and the errors, changing nothing, when any error is found.
        """
        directory, name = _split(reference)
        state = self._state()
        with self._connection.transaction():
            document, problems = self._text_problems(reference, text, state)
            errors = _errors(problems)
            if document is None:
                raise ProjectError(f'{reference} is not valid: {errors[0].message}', 'invalid', problems=errors)
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
                          (directory, name, documents.KINDS[directory], document['title'], text, Jsonb(document)))
            self._write_edges(graph.edges({reference: document}), [reference])
            if directory == 'benchmarks':
                result_rows.prune(self._connection, self.schema, name, document)

    def remove_definition(self, reference):
        """Mark a definition removed, to be deleted from disk by save(); refused while anything uses it.

        The chart that tuldok.json names in map.chart counts as used.

        Removing an environment also drops its record on this machine (an
        installed directory is left where it is); removing anything drops its
        runs and products records (their directories are left where they are).
        """
        directory, name = _split(reference)
        with self._connection.transaction():
            row = self._execute('SELECT file_sha256 FROM {schema}.definitions '
                                'WHERE directory = %s AND name = %s AND NOT removed FOR UPDATE',
                                (directory, name)).fetchone()
            if row is None:
                raise ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
            self._refuse_in_use(reference)
            if directory == annotation_rows.DIRECTORY:
                held = annotation_rows.held_count(self._connection, self.schema, name)
                if held:
                    raise ProjectError(f'{reference} has {held} annotation{"s" if held != 1 else ""}; remove '
                                       f'{"them" if held != 1 else "it"} first.', 'in-use', references=[reference])
            if row[0] is None:
                # Never written to disk: there is no file for save() to delete.
                self._drop(reference)
            else:
                self._execute('UPDATE {schema}.definitions SET removed = true WHERE directory = %s AND name = %s',
                              (directory, name))
                self._forget(reference)

    def _refuse_in_use(self, reference):
        """Raise ProjectError in-use naming what uses reference; the chart in map.chart counts as used."""
        users = [source for (source,) in self._execute(
            'SELECT DISTINCT from_ref FROM {schema}.edges WHERE to_ref = %s ORDER BY 1', (reference,))]
        project = self._state()['project'] or {}
        if isinstance(project.get('map'), dict) and project['map'].get('chart') == reference:
            users.append(folder_reader.PROJECT_FILE)  # its map.chart (spec-w1.md section 1)
        if users:
            raise ProjectError(f'{reference} is used by {", ".join(users)}; change those first.', 'in-use',
                               references=users)

    def _drop(self, reference):
        """Delete a definition's row outright (there is no file for save() to delete) and forget its records."""
        directory, name = documents.parse_reference(reference)
        self._execute('DELETE FROM {schema}.definitions WHERE directory = %s AND name = %s', (directory, name))
        self._forget(reference)
        if directory == annotation_rows.DIRECTORY:
            annotation_rows.forget_task(self._connection, self.schema, name)

    def _forget(self, reference):
        """Drop what a definition that is gone leaves: its edges, runs and products, results, environment record."""
        directory, name = documents.parse_reference(reference)
        self._write_edges([], [reference])
        builds.forget(self._connection, self.schema, reference)
        if directory == 'benchmarks':
            result_rows.remove_benchmark(self._connection, self.schema, name)
        if directory == environments.DIRECTORY:
            environments.forget(self._connection, self.schema, name)

    def revert_definition(self, reference):
        """Undo a definition's unsaved edit or removed mark (spec-w3.md section 2); returns {reference, dropped}.

        When the folder holds the definition's file, its text takes the row's
        place as an import of that file would put it (text, document, title,
        kind, file digest, edges), checked as set_definition checks; a file that
        no longer checks, or cannot be read, is refused invalid with nothing
        changed. A benchmark's result rows are pruned as set_definition prunes
        them, and its results file is imported again when it is still the file
        last imported, since removing the benchmark dropped its rows. When the
        folder holds no file, the row is dropped as remove_definition drops one
        never saved (refused in-use while anything uses it). Refused
        nothing-to-revert for a definition with neither, not-found for none.
        """
        directory, name = _split(reference)
        state = self._state()
        with self._connection.transaction():
            row = self._execute('SELECT unsaved, removed FROM {schema}.definitions '
                                'WHERE directory = %s AND name = %s FOR UPDATE', (directory, name)).fetchone()
            if row is None:
                raise ProjectError(f'There is no definition {reference}.', 'not-found', references=[reference])
            if not (row[0] or row[1]):
                raise ProjectError(f'{reference} has no unsaved edit and is not marked removed; there is nothing '
                                   'to revert.', 'nothing-to-revert', references=[reference])
            path = f'{reference}.json'
            try:
                raw = _read_path(state['folder'], directory, f'{name}.json', folder_reader.DEFINITION_LIMIT)
            except folder_reader.Unsafe as exc:
                raise ProjectError(f'{reference} cannot be reverted: its file cannot be read.', 'invalid',
                                   problems=[Problem('error', path, '', str(exc))], references=[reference]) from None
            if raw is None:
                self._refuse_in_use(reference)
                self._drop(reference)
                return {'reference': reference, 'dropped': True}
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError as exc:
                raise ProjectError(f'{reference} cannot be reverted: its file is not UTF-8 text.', 'invalid',
                                   problems=[Problem('error', path, '', f'The file is not UTF-8 text (bad byte at '
                                                                        f'offset {exc.start}).')],
                                   references=[reference]) from None
            document, problems = self._text_problems(reference, text, state)
            errors = _errors(problems)
            if errors:
                raise ProjectError(f'{reference} cannot be reverted: its file in the folder no longer checks; see '
                                   'the problems.', 'invalid', problems=errors, references=[reference])
            self._execute('''UPDATE {schema}.definitions SET kind = %s, title = %s, text = %s, document = %s,
                                 file_sha256 = %s, unsaved = false, removed = false
                             WHERE directory = %s AND name = %s''',
                          (documents.KINDS[directory], document['title'], text, Jsonb(document), _sha(raw),
                           directory, name))
            self._write_edges(graph.edges({reference: document}), [reference])
            if directory == 'benchmarks':
                result_rows.prune(self._connection, self.schema, name, document)
                self._import_results_again(name, document)
        return {'reference': reference, 'dropped': False}

    def _import_results_again(self, benchmark, document):
        """Import results/<benchmark>.csv again when it is still the file last imported and fits the benchmark."""
        recorded = self._execute('SELECT file_sha256 FROM {schema}.results_files WHERE benchmark = %s',
                                 (benchmark,)).fetchone()
        if recorded is None:
            return
        try:
            raw = _read_path(self._state()['folder'], folder_reader.RESULTS, f'{benchmark}.csv',
                             folder_reader.RESULTS_LIMIT)
        except folder_reader.Unsafe:
            return
        if raw is None or _sha(raw) != recorded[0]:
            return  # gone or changed on disk: the next open takes it as it takes any results file
        if any(severity == 'error' for severity, _, _ in results.check_results(raw, document)):
            return
        result_rows.import_file(self._connection, self.schema, benchmark, raw.decode('utf-8'), document)

    def save(self):
        """Write unsaved definitions and changed results files, and delete the files of removed ones.

        Definitions follow section 4.4 of spec-m1-m2.md; results/<benchmark>.csv
        is written with results.write_results when the database's summaries
        make a text other than the file on disk, and removed when the
        benchmark has no summary rows (spec-m3.md section 3). Before anything
        is written, every file to be replaced or deleted must still have the
        SHA-256 recorded at import or last save (or already hold exactly what
        is to be written, which is what an interrupted save leaves).
        Otherwise nothing is written and ProjectError (code changed-on-disk)
        names them. Returns the references written and deleted, and the
        benchmarks whose results files were written and deleted.
        Each task with an unsaved annotation (or removed, with a line file)
        has annotations/<name>.jsonl written whole from all its rows through
        annotations.write, or deleted when no annotation is left
        (spec-d4.md section 4), under the same rule; annotations_written and
        annotations_deleted name those files.
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
        results_plan = []   # (benchmark, text to write or None to delete, whether the file must change)
        for name, (text, recorded) in result_rows.file_texts(self._connection, self.schema).items():
            current = _path_sha(root, folder_reader.RESULTS, f'{name}.csv', folder_reader.RESULTS_LIMIT)
            target = None if text is None else result_rows.sha256_text(text)
            if current == target:
                if recorded != target:
                    results_plan.append((name, text, False))
            elif current != recorded:
                changed.append(_results_path(name))
            else:
                results_plan.append((name, text, True))
        lines_plan = self._lines_to_save(root, changed)
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
        results_written, results_deleted = [], []
        for name, text, must_change in results_plan:
            if text is None:
                if must_change:
                    _delete_path(root, folder_reader.RESULTS, f'{name}.csv')
                    results_deleted.append(name)
            else:
                if must_change:
                    _write_path(root, folder_reader.RESULTS, f'{name}.csv', text.encode('utf-8'))
                    results_written.append(name)
        annotations_written, annotations_deleted = [], []
        for name, data, must_change, _ in lines_plan:
            if must_change and data is None:
                _delete_path(root, folder_reader.ANNOTATIONS, name + folder_reader.LINES_SUFFIX)
                annotations_deleted.append(annotation_rows.path(name))
            elif must_change:
                _write_path(root, folder_reader.ANNOTATIONS, name + folder_reader.LINES_SUFFIX, data)
                annotations_written.append(annotation_rows.path(name))
        with self._connection.transaction():
            for name, data, _, lines in lines_plan:
                annotation_rows.mark_saved(self._connection, self.schema, name, lines)
                if data is None:
                    annotation_rows.forget_file(self._connection, self.schema, name)
                else:  # the file now holds data: its digest is known, its size and time are read
                    info = os.stat(os.path.join(root, folder_reader.ANNOTATIONS, name + folder_reader.LINES_SUFFIX),
                                   follow_symlinks=False)
                    annotation_rows.record_file(self._connection, self.schema, name, _sha(data), info.st_size,
                                                info.st_mtime_ns)
            for name, text, _ in results_plan:
                if text is None:
                    result_rows.forget_file(self._connection, self.schema, name)
                else:
                    result_rows.record_file(self._connection, self.schema, name, result_rows.sha256_text(text))
            with self._connection.cursor() as cursor:
                if written:
                    cursor.executemany(self._sql('UPDATE {schema}.definitions SET unsaved = false, '
                                                 'file_sha256 = encode(sha256(convert_to(text, \'UTF8\')), \'hex\') '
                                                 'WHERE directory = %s AND name = %s'),
                                       [documents.parse_reference(reference) for reference in written])
                if deleted:
                    cursor.executemany(self._sql('DELETE FROM {schema}.definitions WHERE directory = %s AND name = %s'),
                                       [documents.parse_reference(reference) for reference in deleted])
        return {'written': written, 'deleted': deleted,
                'results_written': results_written, 'results_deleted': results_deleted,
                'annotations_written': annotations_written, 'annotations_deleted': annotations_deleted}

    def _lines_to_save(self, root, changed):
        """[(task name, bytes to write or None to delete, whether the file must change, [(record, line)])].

        The tasks are those with an unsaved row, and removed tasks whose line
        file is recorded. A file whose content is neither the one recorded nor
        the one to be written is added to changed by its path.
        """
        recorded = annotation_rows.recorded_files(self._connection, self.schema)
        names = set(annotation_rows.unsaved_counts(self._connection, self.schema))
        names |= {name for (name,) in self._execute('SELECT name FROM {schema}.definitions WHERE directory = %s '
                                                    'AND removed', (annotation_rows.DIRECTORY,))
                  if name in recorded}
        plan = []
        for name in sorted(names):
            data, lines = annotation_rows.file_text(self._connection, self.schema, name)
            if not lines:
                data = None
            known = recorded.get(name)
            current = _lines_sha(root, name, known)
            target = None if data is None else _sha(data)
            if current == target:
                plan.append((name, data, False, lines))
            elif current != (known[0] if known else None):
                changed.append(annotation_rows.path(name))
            else:
                plan.append((name, data, True, lines))
        return plan

    # -------------------------------------------------------- annotations

    def annotation_tasks(self):
        """{task name: document} of every task not removed, by name."""
        return dict(self._execute('SELECT name, document FROM {schema}.definitions WHERE directory = %s '
                                  'AND NOT removed ORDER BY name', (annotation_rows.DIRECTORY,)).fetchall())

    def annotation_task(self, task):
        """(name, document) of a task given by name or reference; refused not-found when the project has none."""
        name = task[len(annotation_rows.DIRECTORY) + 1:] if task.startswith(annotation_rows.DIRECTORY + '/') else task
        row = self._execute('SELECT document FROM {schema}.definitions WHERE directory = %s AND name = %s '
                            'AND NOT removed', (annotation_rows.DIRECTORY, name)).fetchone() \
            if documents.is_name(name) else None
        if row is None:
            raise ProjectError(f'There is no task {annotation_rows.reference(name)}.', 'not-found',
                               references=[annotation_rows.reference(name)])
        return name, row[0]

    def set_annotations(self, name, given, removals, document):
        """Store checked rows and removals of task name as unsaved, in one transaction (annotation_rows.set_rows).

        Returns (set, removed, how many records of the task are now unsaved).
        """
        with self._connection.transaction():
            done = annotation_rows.set_rows(self._connection, self.schema, name, given, removals, document)
        return (*done, annotation_rows.unsaved_counts(self._connection, self.schema).get(name, 0))

    def revert_annotations(self, name, records, document):
        """Put back the saved lines of the task's unsaved records (all when records is None); returns how many."""
        with self._connection.transaction():
            return annotation_rows.revert(self._connection, self.schema, name, records, document)

    # ------------------------------------------------------------ results

    def _benchmark_document(self, name):
        row = self._execute("SELECT document FROM {schema}.definitions "
                            "WHERE directory = 'benchmarks' AND name = %s AND NOT removed", (name,)).fetchone()
        return None if row is None else row[0]

    def _require_benchmark(self, benchmark, subject=None):
        document = self._benchmark_document(benchmark) if documents.is_name(benchmark) else None
        if document is None:
            raise ProjectError(f'There is no benchmark benchmarks/{benchmark}.', 'not-found',
                               references=[f'benchmarks/{benchmark}'])
        if subject is not None and subject not in {item.get('name') for item in document.get('subjects', [])}:
            raise ProjectError(f'{subject!r} is not a subject of benchmarks/{benchmark}.', 'not-found',
                               references=[f'benchmarks/{benchmark}'])
        return document

    def check_values(self, text, *, path=''):
        """The problems of a tuldok_results_v1 values file against its benchmark (spec-m3.md section 1)."""
        return result_rows.check_values(text, self._benchmark_document, path=path)[1]

    def import_values(self, text, *, path=''):
        """Check a values file, then replace its (benchmark, subject)'s values and summaries in one transaction.

        Raises ProjectError (code invalid, with the problems) and changes
        nothing when the file has any problem. Returns the benchmark, the
        subject, and how many values and summary rows it now holds.
        """
        with self._connection.transaction():
            found, problems = result_rows.check_values(text, self._benchmark_document, path=path)
            if problems:
                raise ProjectError(f'{path or "The values file"} cannot be imported; see the problems.', 'invalid',
                                   problems=problems)
            return result_rows.replace_values(self._connection, self.schema, found)

    def result_summaries(self, benchmark, subject=None, metric=None, group=None):
        """The summary rows of a benchmark as result_rows.StoredSummary (a results.SummaryRow and its origin)."""
        self._require_benchmark(benchmark)
        return result_rows.summaries(self._connection, self.schema, benchmark, subject, metric, group)

    def result_values(self, benchmark, subject, metric=None, offset=0, limit=200):
        """{'total', 'values'}: one page of a subject's per-case values; total 0 when this machine holds none."""
        self._require_benchmark(benchmark, subject)
        return result_rows.values(self._connection, self.schema, benchmark, subject, metric, offset, limit)

    def results_overview(self):
        """Per benchmark: subjects with results, subjects with values, rows, and whether it differs from its file."""
        return result_rows.overview(self._connection, self.schema)

    def close(self):
        """Release the project's lock, then close the connection.

        The lock is released by a statement, so the project can be opened
        again the moment this returns. Closing alone would leave it held
        until the server noticed the session had ended.
        """
        try:
            if not self._connection.closed:
                self._connection.execute('SELECT pg_advisory_unlock(%s)', (_lock_key(self.schema),))
        except psycopg.Error:
            pass  # a connection that is already broken gives the lock up when the server ends its session
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --------------------------------------------------------------- files

def _touched_lines(root, disk_lines, recorded):
    """None when a task's line file is new, gone or changed in content; else {name: (sha, size, mtime)} of the
    files whose size or time alone differ from those recorded (they are read and hashed; the others are not)."""
    if set(disk_lines) != set(recorded):
        return None
    touched = {}
    for name, stamp in disk_lines.items():
        if tuple(recorded[name][1:]) == stamp:
            continue
        try:
            found = _read_lines(root, name)
        except folder_reader.Unsafe:
            return None
        if found is None or _sha(found[0]) != recorded[name][0]:
            return None
        touched[name] = (recorded[name][0], found[1], found[2])
    return touched


def _read_lines(root, name):
    """(bytes, size, mtime_ns) of annotations/<name>.jsonl; None when there is none, folder.Unsafe when it is not
    a plain file. The size and time are taken before the bytes are read, so a change while reading shows next time."""
    filename = name + folder_reader.LINES_SUFFIX
    try:
        fd = os.open(os.path.join(root, folder_reader.ANNOTATIONS), folder_reader.DIRECTORY_FLAGS)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise folder_reader.Unsafe(f'The directory {folder_reader.ANNOTATIONS} cannot be opened: {exc.strerror}.') \
            from None
    try:
        try:
            info = os.stat(filename, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        return folder_reader.read(fd, filename, folder_reader.LINES_LIMIT), info.st_size, info.st_mtime_ns
    finally:
        os.close(fd)


def _lines_sha(root, name, known):
    """SHA-256 of a task's line file, None when there is none, 'unreadable' when it is not a plain file; the
    recorded digest when its size and time are those recorded in known ((sha, size, mtime) or None)."""
    try:
        info = os.stat(os.path.join(root, folder_reader.ANNOTATIONS, name + folder_reader.LINES_SUFFIX),
                       follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError:
        return 'unreadable'
    if known is not None and (info.st_size, info.st_mtime_ns) == tuple(known[1:]):
        return known[0]
    try:
        found = _read_lines(root, name)
    except folder_reader.Unsafe:
        return 'unreadable'
    return None if found is None else _sha(found[0])


def _lines_changed(disk_lines, recorded):
    """The paths of the line files added, removed, or whose size or time differ from those recorded."""
    def differs(name):
        disk, known = disk_lines.get(name), recorded.get(name)
        if disk is None or known is None:
            return disk is not known
        # A file recorded while its time was still fresh was compared by content when the project was opened for
        # this call (annotation_rows.UNSETTLED): only its size can say more here.
        return disk[0] != known[1] or (known[2] != annotation_rows.UNSETTLED and disk[1] != known[2])
    return sorted(annotation_rows.path(name) for name in set(disk_lines) | set(recorded) if differs(name))


def _file_sha(root, reference):
    """SHA-256 of the definition file on disk, None when it does not exist, 'unreadable' when it is not a plain file."""
    directory, name = documents.parse_reference(reference)
    return _path_sha(root, directory, f'{name}.json', folder_reader.DEFINITION_LIMIT)


def _path_sha(root, directory, filename, limit):
    """SHA-256 of directory/filename on disk, None when it does not exist, 'unreadable' when it is not a plain file."""
    try:
        raw = _read_path(root, directory, filename, limit)
    except folder_reader.Unsafe:
        return 'unreadable'
    return None if raw is None else _sha(raw)


def _read_path(root, directory, filename, limit):
    """The bytes of directory/filename on disk; None when it does not exist, folder.Unsafe when not a plain file."""
    try:
        fd = os.open(os.path.join(root, directory), folder_reader.DIRECTORY_FLAGS)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise folder_reader.Unsafe(f'The directory {directory} cannot be opened: {exc.strerror}.') from None
    try:
        return folder_reader.read(fd, filename, limit)
    except folder_reader.Unsafe:
        if not os.path.lexists(os.path.join(root, directory, filename)):
            return None
        raise
    finally:
        os.close(fd)


def _write_file(root, reference, data):
    directory, name = documents.parse_reference(reference)
    _write_path(root, directory, f'{name}.json', data)


def _write_path(root, directory, filename, data):
    """Replace the file atomically: a temporary file in the same directory, fsync, rename, fsync the directory."""
    target_directory = os.path.join(root, directory)
    os.makedirs(target_directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target_directory, prefix=f'.{filename}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, os.path.join(target_directory, filename))
    except BaseException:
        if os.path.lexists(temporary):
            os.unlink(temporary)
        raise
    _sync_directory(target_directory)


def _delete_file(root, reference):
    directory, name = documents.parse_reference(reference)
    _delete_path(root, directory, f'{name}.json')


def _delete_path(root, directory, filename):
    target_directory = os.path.join(root, directory)
    try:
        os.unlink(os.path.join(target_directory, filename))
    except FileNotFoundError:
        return
    _sync_directory(target_directory)


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
