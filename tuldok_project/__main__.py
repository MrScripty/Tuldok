"""Command line for project folders: `python -m tuldok_project <command> FOLDER ...`.

Owns the command-line surface of the package: parsing arguments, printing
reports as aligned text for a person or as one JSON document, and the exit
status (0 done, 1 refused or failed, 2 usage error). `check` reads the folder
alone (check.check_folder). Every other command works on the folder's database
copy through store.open_project: it opens the project (importing what changed
on disk), does its one piece of work and closes the Project before exiting, so
the project's lock is never held past the command.
"""
import argparse
import json
import os
import sys
import time

from . import documents, folder as folder_reader
from .check import check_folder

DATABASE_VARIABLE = 'TULDOK_DATABASE_URL'
KINDS = tuple(sorted(documents.KINDS.values()))


class UsageError(Exception):
    """A command that cannot start as given; exit status 2."""


# ------------------------------------------------------------- arguments

def _parser():
    parser = argparse.ArgumentParser(prog='python -m tuldok_project',
                                     description='Work with a Tuldok project folder.')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check', help='check a project folder against the format')
    check.add_argument('folder', help='the project folder (the one holding tuldok.json)')
    check.add_argument('--no-code', action='store_true', help='do not look up paths in the code root')
    check.add_argument('--json', action='store_true', help='print the report as one JSON object')

    database = argparse.ArgumentParser(add_help=False)
    database.add_argument('folder', help='the project folder (the one holding tuldok.json)')
    database.add_argument('--database-url', help=f'the Postgres database; default ${DATABASE_VARIABLE}')

    opening = argparse.ArgumentParser(add_help=False, parents=[database])
    opening.add_argument('--rebind', action='store_true',
                         help='take the copy over from the folder it is bound to and bind it to this one')
    conflict = opening.add_mutually_exclusive_group()
    conflict.add_argument('--keep', dest='on_conflict', action='store_const', const='keep',
                          help='where a file changed on disk and has unsaved edits here, keep the edits')
    conflict.add_argument('--discard', dest='on_conflict', action='store_const', const='discard',
                          help='where a file changed on disk and has unsaved edits here, take the file')

    reading = argparse.ArgumentParser(add_help=False, parents=[opening])
    reading.add_argument('--json', action='store_true', help='print one JSON document')

    def add(name, parents, help_text):
        return commands.add_parser(name, parents=parents, help=help_text, description=help_text)

    add('open', [reading], 'import the folder into the database, or attach to it when nothing changed')
    listing = add('list', [reading], 'list the definitions with their state')
    listing.add_argument('--kind', choices=KINDS, help='only definitions of this kind')
    show = add('show', [reading], 'show one definition, what it uses and what uses it')
    show.add_argument('reference', help='for example recipes/pilot-dense-k1')
    graph = add('graph', [reading], 'print the definitions with their state and the uses between them')
    graph.add_argument('--order', action='store_true', help='print the build order instead')
    add('status', [reading], 'list unsaved edits and files changed on disk since the last import')
    setting = add('set', [opening], 'replace or add a definition in the database (not saved to the folder)')
    setting.add_argument('reference', help='for example recipes/pilot-dense-k1')
    setting.add_argument('file', help='the file holding the new definition text')
    removing = add('remove', [opening], 'remove a definition in the database (not saved to the folder)')
    removing.add_argument('reference', help='for example recipes/pilot-dense-k1')
    add('save', [reading], 'write the unsaved edits to the folder')
    add('forget', [database], "drop this project's copy from the database; the folder is not touched")
    return parser


# ----------------------------------------------------------------- output

def _plural(count, word):
    return f'{count} {word}' + ('' if count == 1 else 's')


def _columns(rows):
    """Print rows of strings as columns separated by two spaces, the last column unpadded."""
    rows = [[str(cell) for cell in row] for row in rows]
    if not rows:
        return
    widths = [max((len(row[index]) for row in rows if index < len(row) - 1), default=0)
              for index in range(max(map(len, rows)))]
    for row in rows:
        cells = [cell.ljust(widths[index]) for index, cell in enumerate(row[:-1])] + row[-1:]
        print('  '.join(cells).rstrip())


def _json(value):
    json.dump(value, sys.stdout, indent=2, ensure_ascii=False, default=str)
    sys.stdout.write('\n')


def _problem_line(problem):
    return f'{problem.severity}  {problem.path}  {problem.pointer or "-"}  {problem.message}'


def _marks(row):
    return ' (removed)' if row['removed'] else ' (unsaved)' if row['unsaved'] else ''


# --------------------------------------------------------------- commands

def _check(arguments):
    report = check_folder(arguments.folder, code=not arguments.no_code)
    errors, warnings = report.count('error'), report.count('warning')
    if arguments.json:
        _json({'folder': report.folder, 'ok': report.ok, 'errors': errors, 'warnings': warnings,
               'problems': [problem.as_dict() for problem in report.problems]})
    else:
        for problem in report.problems:
            print(_problem_line(problem))
        print(f'{_plural(errors, "error")}, {_plural(warnings, "warning")} in {report.folder}')
    return 0 if report.ok else 1


def _open(project, arguments):
    summary = project.summary()
    if arguments.json:
        _json({**summary, 'seconds': round(arguments.seconds, 3)})
        return 0
    total = sum(summary['kinds'].values())
    print(f'Opened {summary["name"]} ({summary["project_id"]}) from {summary["folder"]} in {arguments.seconds:.2f} s.')
    print()
    _columns([('kind', 'count'), *summary['kinds'].items(), ('total', total)])
    print()
    _columns([('state', 'count'), *summary['states'].items()])
    return 0


def _list(project, arguments):
    rows = project.definitions(kind=arguments.kind)
    if arguments.json:
        _json(rows)
    else:
        _columns([(row['reference'], row['state'] + _marks(row), row['title']) for row in rows])
    return 0


def _show(project, arguments):
    shown = project.definition(arguments.reference)
    if arguments.json:
        _json(shown)
        return 0
    rows = [('reference', shown['reference']), ('title', shown['title']), ('kind', shown['kind']),
            ('state', shown['state'] + _marks(shown))]
    rows += [('uses', use['reference'], use['role']) for use in shown['uses']] or [('uses', 'nothing')]
    rows += [('used by', user['reference'], user['role']) for user in shown['used_by']] or [('used by', 'nothing')]
    _columns(rows)
    print()
    sys.stdout.write(shown['text'] if shown['text'].endswith('\n') else shown['text'] + '\n')
    return 0


def _graph(project, arguments):
    if arguments.order:
        states = {node['reference']: node['state'] for node in project.graph()['nodes']}
        order = [{'reference': reference, 'state': states[reference]} for reference in project.order()]
        if arguments.json:
            _json(order)
        else:
            _columns([(item['reference'], item['state']) for item in order])
        return 0
    drawn = project.graph()
    if arguments.json:
        _json(drawn)
        return 0
    _columns([(node['reference'], node['kind'], node['state']) for node in drawn['nodes']])
    print()
    _columns([(edge['from'], edge['role'], edge['to']) for edge in drawn['edges']])
    return 0


_STATUS_WORDS = (
    ('unsaved', 'unsaved'), ('removed', 'removed'), ('added', 'added on disk'),
    ('changed', 'changed on disk'), ('missing', 'missing on disk'), ('irregular', 'not a definition file'),
)


def _status(project, arguments):
    status = project.status()
    if arguments.json:
        _json(status)
        return 0
    rows = [(word, reference) for key, word in _STATUS_WORDS for reference in status[key]]
    if rows:
        _columns(rows)
    else:
        print('Nothing is unsaved and no file changed on disk since the last import.')
    return 0


def _set(project, arguments):
    project.set_definition(arguments.reference, arguments.text)
    print(f'Set {arguments.reference} in the database; run save to write it to the folder.')
    return 0


def _remove(project, arguments):
    project.remove_definition(arguments.reference)
    print(f'Removed {arguments.reference} in the database; run save to apply it to the folder.')
    return 0


def _save(project, arguments):
    saved = project.save()
    if arguments.json:
        _json(saved)
        return 0
    rows = [('wrote', reference) for reference in saved['written']]
    rows += [('deleted', reference) for reference in saved['deleted']]
    if rows:
        _columns(rows)
    else:
        print('Nothing to save.')
    return 0


_STORE_COMMANDS = {'open': _open, 'list': _list, 'show': _show, 'graph': _graph, 'status': _status,
                   'set': _set, 'remove': _remove, 'save': _save}


def _project_id(folder):
    """The id in the folder's tuldok.json, without opening or checking anything else."""
    from .store import PROJECT_ID

    path = os.path.join(os.fspath(folder), folder_reader.PROJECT_FILE)
    try:
        root_fd = os.open(os.fspath(folder), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as exc:
        raise UsageError(f'The project folder {folder} cannot be opened: {exc.strerror}.') from None
    try:
        document = documents.decode(folder_reader.read(root_fd, folder_reader.PROJECT_FILE, folder_reader.PROJECT_LIMIT))
    except (folder_reader.Unsafe, documents.DocumentError) as exc:
        raise UsageError(f'{path} cannot be read: {exc}') from None
    finally:
        os.close(root_fd)
    project_id = document.get('id')
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise UsageError(f'{path} has no valid id; run check on the folder.')
    return project_id


def _forget(arguments, dsn):
    from . import store

    project_id = _project_id(arguments.folder)
    store.drop_project(project_id, dsn)
    print(f'The database holds no copy of project {project_id} now; the folder was not touched.')
    return 0


def _run_store(arguments, dsn):
    from . import store

    if arguments.command == 'set':
        try:
            with open(arguments.file, 'rb') as handle:
                arguments.text = handle.read().decode('utf-8')
        except OSError as exc:
            raise UsageError(f'{arguments.file} cannot be read: {exc.strerror}.') from None
        except UnicodeDecodeError as exc:
            raise UsageError(f'{arguments.file} is not UTF-8 text (bad byte at offset {exc.start}).') from None
    started = time.monotonic()
    project = store.open_project(arguments.folder, rebind=arguments.rebind, on_conflict=arguments.on_conflict,
                                 dsn=dsn)
    arguments.seconds = time.monotonic() - started
    try:
        return _STORE_COMMANDS[arguments.command](project, arguments)
    finally:
        project.close()


def _database_command(arguments):
    import psycopg
    from metadata import StorageError
    from .store import ProjectError

    dsn = arguments.database_url or os.environ.get(DATABASE_VARIABLE)
    if not dsn:
        print(f'No database is set: pass --database-url or set {DATABASE_VARIABLE}.', file=sys.stderr)
        return 2
    try:
        if arguments.command == 'forget':
            return _forget(arguments, dsn)
        return _run_store(arguments, dsn)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except StorageError as exc:
        print(f'The database setting is not usable: {exc}', file=sys.stderr)
        return 2
    except ProjectError as exc:
        print(str(exc), file=sys.stderr)
        for problem in exc.problems:
            print(_problem_line(problem), file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        print(f'The database failed: {str(exc).strip() or type(exc).__name__}', file=sys.stderr)
        return 1


def main(argv=None):
    arguments = _parser().parse_args(argv)  # exits with status 2 on a usage error
    if arguments.command == 'check':
        return _check(arguments)
    return _database_command(arguments)


if __name__ == '__main__':
    sys.exit(main())
