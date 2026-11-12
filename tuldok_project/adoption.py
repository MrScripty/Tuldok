"""Adopting files made before Tuldok could build them as the products of their definitions.

Owns section 3 of docs/plans/definition-first-projects/spec-m8.md. A manifest
(tuldok_adoption_v1) names, for some datasets, recipes and steps, the files
that are their outputs (or, for a definition that declares none, the
directory that is its product as a whole). read_manifest reads it; make_plan checks every entry
against the project and says what adopting would do, refusing the whole
manifest (AdoptionError, with every problem) when one entry is refused; adopt
does it: for each entry to adopt it makes <local home>/runs/<run id>/output/
holding the files as hard links to the sources (copies when a source is on
another filesystem, or always with copy), under a temporary name renamed into
place, then records a run in state adopted and its product, current. Nothing
is ever written to a source file, and no checksum is taken; the size of each
file is recorded. Adoption is a command-line action only.
"""
import errno
import os
import shutil
import stat
import uuid

from psycopg.types.json import Jsonb

from . import builds, documents, local

FORMAT = 'tuldok_adoption_v1'
MANIFEST_LIMIT = 16 * 1024 * 1024
ENTRY_LIMIT = 5000
FILE_LIMIT = 200
NOTE_CHARACTERS = 400
ADOPTABLE = ('datasets', 'recipes', 'steps')
_TOP_FIELDS = ('format', 'products')
_ENTRY_FIELDS = ('reference', 'note', 'files')


class AdoptionError(Exception):
    """A manifest that is refused; problems lists every reason, and nothing was adopted."""

    def __init__(self, message, problems=()):
        super().__init__(message)
        self.problems = list(problems)


def read_manifest(path):
    """The manifest's object; OSError when it cannot be read, AdoptionError when it is not strict JSON or too large."""
    with open(path, 'rb') as handle:
        raw = handle.read(MANIFEST_LIMIT + 1)
    if len(raw) > MANIFEST_LIMIT:
        raise AdoptionError(f'The manifest {path} is larger than {MANIFEST_LIMIT // 1024 // 1024} MiB.')
    try:
        return documents.decode(raw)
    except documents.DocumentError as exc:
        raise AdoptionError(f'The manifest {path} is not valid: {exc}') from None


def _under(path, output):
    return path == output or path.startswith(output + '/')


def _device(path):
    """st_dev of path, or of its nearest existing parent."""
    while not os.path.exists(path) and os.path.dirname(path) != path:
        path = os.path.dirname(path)
    return os.stat(path).st_dev


def _check_files(files, declared, where, problems):
    """[(key, source, bytes, st_dev)] of an entry's files; problems gains a line for each one refused.

    A key must lie under one of the declared outputs; a definition that
    declares none has the directory as a whole as its product, and any key in
    normal form is accepted.
    """
    found = []
    if not isinstance(files, dict) or not 1 <= len(files) <= FILE_LIMIT:
        problems.append(f'{where}: files must be an object of 1 to {FILE_LIMIT} entries.')
        return found
    keys = sorted(files)
    for key in keys:
        source = files[key]
        wrong = documents.relative_path_problem(key)
        if wrong is not None:
            problems.append(f'{where}: the key {key!r} {wrong}.')
            continue
        if declared and not any(_under(key, output['path']) for output in declared.values()):
            problems.append(f'{where}: {key} is not a declared output of the definition, nor under one.')
            continue
        if any(other != key and _under(other, key) for other in keys):
            problems.append(f'{where}: {key} is a file, so nothing can be under it.')
            continue
        if not isinstance(source, str) or not os.path.isabs(source) or '\x00' in source:
            problems.append(f'{where}: the source of {key} must be an absolute path.')
            continue
        try:
            status = os.lstat(source)
        except OSError as exc:
            problems.append(f'{where}: the source of {key}, {source}, cannot be read: {exc.strerror}.')
            continue
        if stat.S_ISLNK(status.st_mode):
            problems.append(f'{where}: the source of {key}, {source}, is a link; name the file itself.')
        elif not stat.S_ISREG(status.st_mode):
            problems.append(f'{where}: the source of {key}, {source}, is not a regular file.')
        elif not os.access(source, os.R_OK):
            problems.append(f'{where}: the source of {key}, {source}, cannot be read by this user.')
        else:
            found.append((key, source, status.st_size, status.st_dev))
    return found


def make_plan(project, manifest, *, copy=False, replace=False):
    """What adopting manifest would do in the open project; raises AdoptionError when an entry is refused.

    Returns {entries: [{reference, action (adopt or skip), note, files: [{path,
    source, bytes, how (link or copy)}], outputs: {name: {path, role, bytes}},
    missing: [{name, path}], bytes, current_run}], counts: {adopt, skip,
    missing, files, bytes, linked, copied}, copy, replace}. An entry whose
    definition has a current product is skipped unless replace. Nothing is
    read but the manifest, the definitions and the sources' metadata.
    """
    problems = []
    unknown = sorted(set(manifest) - set(_TOP_FIELDS))
    if unknown:
        problems.append(f'The manifest has the unknown field {unknown[0]!r}.')
    if manifest.get('format') != FORMAT:
        problems.append(f'The manifest\'s format must be "{FORMAT}".')
    products = manifest.get('products')
    if not isinstance(products, list) or not 1 <= len(products) <= ENTRY_LIMIT:
        problems.append(f'products must be a list of 1 to {ENTRY_LIMIT} entries.')
        products = []
    definitions = project._documents(removed=False)
    target = _device(os.path.join(local.home(project.project_id), builds.RUNS))
    seen, entries = set(), []
    for index, entry in enumerate(products):
        where = f'products[{index}]'
        if not isinstance(entry, dict):
            problems.append(f'{where} must be an object.')
            continue
        reference = entry.get('reference')
        where += f' ({reference})' if isinstance(reference, str) else ''
        unknown = sorted(set(entry) - set(_ENTRY_FIELDS))
        if unknown:
            problems.append(f'{where}: the unknown field {unknown[0]!r}.')
        parsed = documents.parse_reference(reference)
        if parsed is None:
            problems.append(f'{where}: reference must be a reference such as recipes/<name>.')
            continue
        if reference in seen:
            problems.append(f'{where}: {reference} appears more than once.')
            continue
        seen.add(reference)
        if parsed[0] not in ADOPTABLE:
            problems.append(f'{where}: only a dataset, recipe or step can be adopted.')
            continue
        if reference not in definitions:
            problems.append(f'{where}: there is no definition {reference}.')
            continue
        note = entry.get('note')
        if 'note' in entry and not (isinstance(note, str) and 1 <= len(note) <= NOTE_CHARACTERS):
            problems.append(f'{where}: note must be 1 to {NOTE_CHARACTERS} characters.')
        outputs = builds._run_block(definitions[reference]).get('outputs')
        declared = {name: output for name, output in (outputs.items() if isinstance(outputs, dict) else ())
                    if isinstance(output, dict) and isinstance(output.get('path'), str)}
        files = _check_files(entry.get('files'), declared, where, problems)
        if not isinstance(entry.get('files'), dict) or len(files) != len(entry['files']):
            continue
        sizes = {}
        for key, _source, size, _device_ in files:
            for name, output in declared.items():
                if _under(key, output['path']):
                    sizes[name] = sizes.get(name, 0) + size
        # Every key lies under a declared output (when there are any) and files is not empty, so an entry
        # whose definition declares outputs always has a file for at least one of them.
        current = builds._current_product(project, reference)
        entries.append({
            'reference': reference, 'note': note,
            'action': 'skip' if current is not None and not replace else 'adopt',
            'current_run': current and current['run_id'],
            'files': [{'path': key, 'source': source, 'bytes': size,
                       'how': 'copy' if copy or device != target else 'link'}
                      for key, source, size, device in files],
            'outputs': {name: {'path': output['path'], 'role': output.get('role'), 'bytes': sizes[name]}
                        for name, output in declared.items() if name in sizes},
            'missing': [{'name': name, 'path': output['path']} for name, output in declared.items()
                        if name not in sizes],
            'bytes': sum(size for _key, _source, size, _device_ in files)})
    if problems:
        raise AdoptionError(f'Nothing was adopted: {len(problems)} problem' + ('' if len(problems) == 1 else 's')
                            + ' in the manifest.', problems)
    adopting = [entry for entry in entries if entry['action'] == 'adopt']
    files = [item for entry in adopting for item in entry['files']]
    return {'entries': entries, 'copy': copy, 'replace': replace,
            'counts': {'adopt': len(adopting), 'skip': len(entries) - len(adopting),
                       'missing': sum(len(entry['missing']) for entry in adopting), 'files': len(files),
                       'bytes': sum(item['bytes'] for item in files),
                       'linked': sum(item['how'] == 'link' for item in files),
                       'copied': sum(item['how'] == 'copy' for item in files)}}


def _place(source, target, how):
    """Link (or copy) source to target; return how it was done. A link across filesystems becomes a copy."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if how == 'link':
        try:
            os.link(source, target, follow_symlinks=False)
            return 'link'
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
    shutil.copyfile(source, target, follow_symlinks=False)
    return 'copy'


def adopt(project, plan):
    """Do what plan (make_plan's result) says, entry by entry; return plan with run_id and directory per adopted entry.

    Each entry's directory is complete and renamed into place before its run
    and product are recorded in one transaction; a product that was current
    stays in the database, no longer current. The counts linked and copied
    say what was done.
    """
    runs = os.path.join(local.home(project.project_id, create=True), builds.RUNS)
    os.makedirs(runs, exist_ok=True)
    for entry in plan['entries']:
        if entry['action'] != 'adopt':
            continue
        run_id = uuid.uuid4().hex
        directory = os.path.join(runs, run_id)
        temporary = os.path.join(runs, f'.{run_id}.adopting')
        for item in entry['files']:
            item['how'] = _place(item['source'], os.path.join(temporary, builds.OUTPUT, item['path']), item['how'])
        os.rename(temporary, directory)
        output = os.path.join(directory, builds.OUTPUT)
        with project._connection.transaction():
            project._execute('''INSERT INTO {schema}.runs (id, reference, subject, plan_id, state, scratch, commit,
                                    definition, settings, inputs, environment, argv, env, directory, queued_at,
                                    started_at, finished_at, bytes, problem)
                                SELECT %s, %s, '', '', %s, false, '', text, NULL, '{{}}'::jsonb, NULL,
                                       '[]'::jsonb, '{{}}'::jsonb, %s, now(), now(), now(), %s, %s
                                FROM {schema}.definitions
                                WHERE directory || '/' || name = %s AND NOT removed''',
                             (run_id, entry['reference'], builds.ADOPTED, directory, entry['bytes'], entry['note'],
                              entry['reference']))
            project._execute('UPDATE {schema}.products SET current = false '
                             "WHERE reference = %s AND subject = '' AND current", (entry['reference'],))
            project._execute("INSERT INTO {schema}.products (run_id, reference, subject, directory, outputs, current) "
                             "VALUES (%s, %s, '', %s, %s, true)",
                             (run_id, entry['reference'], output, Jsonb(entry['outputs'])))
        entry.update(run_id=run_id, directory=output)
    files = [item for entry in plan['entries'] if entry['action'] == 'adopt' for item in entry['files']]
    plan['counts'].update(linked=sum(item['how'] == 'link' for item in files),
                          copied=sum(item['how'] == 'copy' for item in files))
    return plan
