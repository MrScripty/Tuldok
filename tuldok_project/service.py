"""The operations of one served project folder, called with an actor and JSON arguments.

Owns section 3 of docs/plans/definition-first-projects/spec-m7.md. Service.call
checks a call against the table in operations.py (the operation exists, the
actor satisfies its who rule from kind and scopes alone, the arguments match
its schema), runs it with the project open only for the moment it needs, and
returns a JSON-plain object. Calls are answered one at a time under one lock
of the service. Every mutating call that passed the actor check writes one
activity row, done or refused. The six operations on build requests are
passed to build_requests. The five reads inside a product (spec-d1.md) find
the finished run with the project open for a moment and read its output
directory through inside.py after closing it; product_file does the same for
the file route; those reads run outside the lock, so a long one holds up no
other call. Nothing here knows of HTTP or of the app's access layer.

The worker (section 4) is one thread per service, started by start() and
stopped by close(). It runs queued build requests one at a time while it
holds a non-blocking flock on <local home>/<project id>/build-requests.lock,
so one process on the machine runs a project's requests; a service whose
worker finds the lock taken reports worker "elsewhere" and tries again every
pass. About every POLL_SECONDS it looks, on a connection of its own, whether
any request is queued or running; only then does it open the project, mark
orphaned requests failed and take the oldest queued one, and it runs that
one with builds.execute with the project closed. It does not take the
service's call lock. close() asks a running build to stop and waits up to
CLOSE_SECONDS for the thread.
"""
import dataclasses
import datetime
import fcntl
import logging
import math
import os
import threading

import jsonschema
import psycopg

from . import (activity, build_requests, builds, charts, check, environments, inside, launcher, local, operations,
               plan, store, workspace)
from .documents import Problem

CHECK_PROBLEMS = 200

# The reads inside a product (spec-d1.md), each a function of (inside.Product, arguments). call() finds the product
# under the service's lock and reads outside it: decompressing a large member or parsing a large mesh takes seconds,
# and the other calls (the page's own readings among them) must not wait for it. inside.py guards what it keeps.
INSIDE_READS = {
    'records': lambda product, a: inside.records(product, offset=a.get('offset', 0), limit=a.get('limit', 50),
                                                 kind=a.get('kind'), split=a.get('split')),
    'record': lambda product, a: inside.record(product, a['id']),
    'inside': lambda product, a: inside.inside(product, path=a.get('path', ''), offset=a.get('offset', 0),
                                               limit=a.get('limit', 200)),
    'array_slice': lambda product, a: inside.array_slice(product, path=a['path'], array=a.get('array'),
                                                         axes=a.get('axes'), index=a.get('index'),
                                                         most=a.get('most', 256)),
    'array_summary': lambda product, a: inside.array_summary(product, path=a['path'], array=a.get('array'),
                                                             bins=a.get('bins', 64)),
}
POLL_SECONDS = 1.0          # how often the worker looks for a queued request
CLOSE_SECONDS = 30.0        # how long close() waits for the worker
WORKER_LOCK = 'build-requests.lock'
_LOG = logging.getLogger(__name__)
_TARGET_ARGUMENTS = ('reference', 'run', 'request')


def _plain(value):
    """value as plain JSON: datetimes as ISO 8601 text in UTC, non-finite numbers as None, tuples as lists."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(datetime.timezone.utc)
        return value.isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    raise TypeError(f'{type(value).__name__} is not plain JSON.')


def _allowed(who, actor):
    """Whether actor ({kind, scopes, ...}) satisfies the who rule, as the host's access.require calls would."""
    kind, scopes = actor.get('kind'), actor.get('scopes')
    if kind not in ('owner', 'agent') or not isinstance(scopes, (list, tuple)):
        return False
    if who in ('inspect', 'edit', 'cancel'):
        return who in scopes
    if who == 'request':
        return 'inspect' in scopes and (kind == 'owner' or 'execute' in scopes)
    if who == 'owner':
        return kind == 'owner' and 'approve-execution' in scopes
    return False


def _argument_problems(operation, arguments):
    validator = jsonschema.Draft202012Validator(operation.arguments)
    return [Problem('error', '', '/' + '/'.join(str(part) for part in error.absolute_path), error.message)
            for error in sorted(validator.iter_errors(arguments), key=lambda error: list(error.absolute_path))]


def _bare(text, directory):
    """The name of a bare name or a <directory>/<name> reference (left for the reader to refuse when it is neither)."""
    return text[len(directory) + 1:] if text.startswith(directory + '/') else text


def _target(arguments):
    if isinstance(arguments, dict):
        for key in _TARGET_ARGUMENTS:
            if isinstance(arguments.get(key), str):
                return arguments[key]
    return ''


def _write_cancel_file(directory):
    """Ask the launcher running in directory to cancel its run (builds.cancel does the same with a run's row)."""
    try:
        os.close(os.open(os.path.join(directory, launcher.CANCEL_FILE),
                         os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644))
    except OSError:
        pass  # the run ended and its directory went, or it was asked already


class Service:
    """One project folder served by one process; see the module docstring."""

    def __init__(self, folder, *, dsn=None):
        """Open the folder once (importing what changed) and close it; raises ProjectError when it does not open."""
        self.folder = os.path.realpath(os.fspath(folder))
        self.dsn = dsn
        self._lock = threading.Lock()
        self._worker = 'stopped'
        self._thread = None
        self._stopping = threading.Event()
        self._running = None        # (request id, run directory or None) while the worker runs a request
        with builds.opened(self.folder, dsn) as project:
            self.project_id = project.project_id
            self.schema = project.schema

    # ------------------------------------------------------------ lifecycle

    def start(self):
        """Start the worker that runs queued build requests (section 4); does nothing when it is started."""
        if self._thread is not None:
            return
        self._stopping = threading.Event()
        descriptor = self._take_worker_lock()
        self._thread = threading.Thread(target=self._work, args=(self._stopping, descriptor),
                                        name=f'tuldok-build-requests-{self.project_id[:8]}', daemon=True)
        self._thread.start()

    def close(self):
        """Stop the worker: ask a running build to stop, wait up to CLOSE_SECONDS, return. Safe to call twice.

        The request being run is marked cancel_requested and its current run's
        cancel file is written; the worker records it cancelled when the build
        ends. When the thread does not end in time it is left to finish (and
        to release the worker lock) on its own.
        """
        thread, self._thread = self._thread, None
        self._worker = 'stopped'
        if thread is None:
            return
        self._stopping.set()
        running = self._running
        if running is not None:
            try:
                build_requests.ask_to_stop(self.dsn, self.schema, running[0])
            except psycopg.Error:
                _LOG.exception('Could not mark build request %s to stop.', running[0])
            if running[1] is not None:
                _write_cancel_file(running[1])
        thread.join(CLOSE_SECONDS)
        self._worker = 'stopped'  # again: a lock taken while close began must not show as running

    # --------------------------------------------------------------- worker

    def _take_worker_lock(self):
        """Take the worker lock without waiting: its descriptor (worker running), or None (elsewhere).

        The descriptor belongs to the thread that runs with it; closing it
        releases the lock.
        """
        path = os.path.join(local.home(self.project_id, create=True), WORKER_LOCK)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            self._worker = 'elsewhere'
            return None
        self._worker = 'running'
        return descriptor

    def _work(self, stopping, descriptor):
        failure = None  # the last pass's failure, so a failure that repeats every pass is logged once
        try:
            while not stopping.is_set():
                try:
                    if descriptor is None:
                        descriptor = self._take_worker_lock()
                    if descriptor is not None:
                        self._pass(stopping)
                    failure = None
                except Exception as exc:  # the worker goes on; the next pass tries again
                    if f'{type(exc).__name__}: {exc}' != failure:
                        failure = f'{type(exc).__name__}: {exc}'
                        _LOG.exception('The build request worker of %s failed in a pass; it will keep trying.',
                                       self.folder)
                stopping.wait(POLL_SECONDS)
        finally:
            if descriptor is not None:
                os.close(descriptor)  # releases the flock

    def _pass(self, stopping):
        """One look: mark orphans failed, take the oldest queued request that may run, run it, record it."""
        if not build_requests.waiting(self.dsn, self.schema):
            return
        with self._open() as project:
            build_requests.reap_orphans(project, worker_pid=os.getpid())
            taken = None if stopping.is_set() else build_requests.take(project)
        if taken is None:
            return
        request, made = taken
        request_id = request['id']
        self._running = (request_id, None)
        ended = []

        def on_event(kind, item):
            if kind == 'end':
                ended.append(item)
                return
            self._running = (request_id, item['directory'])
            asked = build_requests.started(self.dsn, self.schema, request_id, item['run_id'])
            if asked or stopping.is_set():
                _write_cancel_file(item['directory'])

        def stop():
            return stopping.is_set() or build_requests.stop_asked(self.dsn, self.schema, request_id)

        outcome = {}
        try:
            outcome['done'] = builds.execute(self.folder, made, confirm=lambda _plan: True,
                                             scratch=request['scratch'], dsn=self.dsn, expect=request['covers'],
                                             stop=stop, on_event=on_event)
        except store.ProjectError as exc:
            outcome['problem'] = str(exc)
        except Exception as exc:
            _LOG.exception('Build request %s failed in the worker.', request_id)
            outcome['problem'] = f'{type(exc).__name__}: {exc}'
        try:
            with self._open() as project:
                build_requests.finish(project, request_id, steps=ended, **outcome)
        finally:
            self._running = None

    # ---------------------------------------------------------------- calls

    def call(self, name, arguments, actor):
        """Run the operation name (without the project. prefix) for actor; return its JSON-plain result.

        Raises ProjectError: not-found for an unknown operation, forbidden when
        actor does not satisfy its who rule, invalid (one problem per schema
        error) for arguments that do not match, or the operation's own refusal.
        """
        operation = operations.by_name(name)
        if operation is None:
            raise store.ProjectError(f'There is no operation project.{name}.', 'not-found')
        if not _allowed(operation.who, actor):
            raise store.ProjectError(f'This credential may not call project.{name}.', 'forbidden')
        if name in INSIDE_READS:
            problems = _argument_problems(operation, arguments)
            if problems:
                raise store.ProjectError(f'The arguments of project.{name} do not match its schema.', 'invalid',
                                         problems=problems)
            with self._lock:
                product = self._product(arguments['run'])
            return _plain(INSIDE_READS[name](product, dict(arguments)))
        with self._lock:
            try:
                problems = _argument_problems(operation, arguments)
                if problems:
                    raise store.ProjectError(f'The arguments of project.{name} do not match its schema.', 'invalid',
                                             problems=problems)
                result = _plain(getattr(self, f'_{name}')(dict(arguments), actor))
            except store.ProjectError as exc:
                if operation.mutation:
                    self._record_activity(actor, name, _target(arguments), exc.code, str(exc))
                raise
            except Exception as exc:
                if operation.mutation:
                    self._record_activity(actor, name, _target(arguments), 'error', f'{type(exc).__name__}: {exc}')
                raise
            if operation.mutation:
                target = result.get('id', '') if name == 'request_build' else _target(arguments)
                self._record_activity(actor, name, target, 'done')
            return result

    def _record_activity(self, actor, name, target, outcome, detail=''):
        # Its own connection: the row is written even when the project would not open.
        with psycopg.connect(store.connection_info(self.dsn), autocommit=True) as connection:
            activity.record(connection, self.schema, actor, name, target, outcome, detail)

    def _open(self, **options):
        return builds.opened(self.folder, self.dsn, **options)

    def _summary_of(self, project):
        return {**project.summary(), 'worker': self._worker}

    # ----------------------------------------------------------------- reads

    def _summary(self, arguments, actor):
        with self._open() as project:
            return self._summary_of(project)

    def _status(self, arguments, actor):
        with self._open() as project:
            return project.status()

    def _check(self, arguments, actor):
        report = check.check_folder(self.folder)
        return {'ok': report.ok, 'errors': report.count('error'), 'warnings': report.count('warning'),
                'problems': [problem.as_dict() for problem in report.problems[:CHECK_PROBLEMS]]}

    def _definitions(self, arguments, actor):
        with self._open() as project:
            return {'definitions': project.definitions(arguments.get('kind'))}

    def _definition(self, arguments, actor):
        with self._open() as project:
            return project.definition(arguments['reference'])

    def _graph(self, arguments, actor):
        with self._open() as project:
            return project.graph()

    def _results_overview(self, arguments, actor):
        with self._open() as project:
            return {'benchmarks': project.results_overview()}

    def _results(self, arguments, actor):
        offset, limit = arguments.get('offset', 0), arguments.get('limit', 500)
        with self._open() as project:
            stored = project.result_summaries(_bare(arguments['benchmark'], 'benchmarks'),
                                              subject=arguments.get('subject'), metric=arguments.get('metric'),
                                              group=arguments.get('group'))
        return {'rows': [{**dataclasses.asdict(item.row), 'origin': item.origin}
                         for item in stored[offset:offset + limit]],
                'total': len(stored)}

    def _values(self, arguments, actor):
        with self._open() as project:
            held = project.result_values(_bare(arguments['benchmark'], 'benchmarks'), arguments['subject'],
                                         metric=arguments.get('metric'), offset=arguments.get('offset', 0),
                                         limit=arguments.get('limit', 200))
        return {'rows': held['values'], 'total': held['total']}

    def _chart(self, arguments, actor):
        reference = charts.chart_reference(arguments['chart'])
        if reference is None:
            raise store.ProjectError(f'{arguments["chart"]!r} is not a chart name or a reference such as '
                                     'charts/<name>.', 'not-found', references=[arguments['chart']])
        with self._open() as project:
            data = charts.chart_data(project, reference)
        result = {'data': data}
        if arguments.get('svg'):
            result['svg'] = charts.render_svg(data, theme=arguments.get('theme', 'light'))
        return result

    def _report(self, arguments, actor):
        with self._open() as project:
            return {'html': charts.render_report(project, theme=arguments.get('theme', 'light'))}

    def _plan(self, arguments, actor):
        with self._open() as project:
            return plan.build_plan(project, arguments['targets'], every=arguments.get('every', False))

    def _estimates(self, arguments, actor):
        with self._open() as project:
            return {'estimates': builds.stored_estimates(project)}

    def _environments(self, arguments, actor):
        with self._open() as project:
            return {'environments': environments.listing(project)}

    def _environment(self, arguments, actor):
        with self._open() as project:
            return environments.show(project, arguments['reference'])

    def _runs(self, arguments, actor):
        with self._open() as project:
            found = builds.runs(project, arguments.get('reference'))
        return {'runs': found[:arguments.get('limit', 100)]}

    def _run(self, arguments, actor):
        with self._open() as project:
            row = builds.run_details(project, arguments['run'])
        env = row.pop('env') or {}
        row['env_names'] = sorted(env)  # the values may be secrets: they are never sent
        return row

    def _progress(self, arguments, actor):
        with self._open() as project:
            row = builds.run_details(project, arguments['run'])
        ended = row['state'] not in builds.ACTIVE
        result = {'run': builds.run_summary(row), 'event': launcher.progress(row['directory'])['event'],
                  'ended': ended}
        for name in launcher.LOGS:
            # Offset 0 reads the last part of the log: read_log skips what is more than one tail back.
            result[name] = builds.read_log(row['directory'], name, arguments.get(f'{name}_offset', 0), final=ended)
        return result

    def _products(self, arguments, actor):
        with self._open() as project:
            return {'products': builds.products(project, arguments.get('reference'))}

    def _build_requests(self, arguments, actor):
        with self._open() as project:
            return {'requests': build_requests.listing(project, state=arguments.get('state'),
                                                       limit=arguments.get('limit', 100))}

    def _build_request(self, arguments, actor):
        with self._open() as project:
            return build_requests.show(project, arguments['request'])

    def _activity(self, arguments, actor):
        with self._open() as project:
            return activity.items(project._connection, project.schema, arguments.get('offset', 0),
                                  arguments.get('limit', 100))

    def _map(self, arguments, actor):
        with self._open() as project:
            return workspace.project_map(project)

    def _note(self, arguments, actor):
        return workspace.read_note(self.folder, arguments['path'])  # from disk; the project is not opened

    def _recipe_results(self, arguments, actor):
        recipe = 'recipes/' + _bare(arguments['recipe'], 'recipes')
        with self._open() as project:
            return workspace.recipe_results(project, recipe, arguments.get('group'))

    def _draft_branch(self, arguments, actor):
        recipe = 'recipes/' + _bare(arguments['recipe'], 'recipes')
        with self._open() as project:
            return workspace.draft_branch(project, recipe, arguments['title'], name=arguments.get('name'),
                                          change=arguments.get('change'), description=arguments.get('description'))

    # ------------------------------------------------------ inside a product

    def _product(self, run):
        """The inside.Product of a finished run (succeeded or adopted), read with the project open for a moment."""
        with self._open() as project:
            run_id = builds.find_run(project, run)
            state, directory, reference = project._execute(
                'SELECT state, directory, reference FROM {schema}.runs WHERE id = %s', (run_id,)).fetchone()
            view = None
            if reference.startswith('datasets/'):
                row = project._execute('SELECT document FROM {schema}.definitions WHERE directory = %s AND name = %s '
                                       'AND NOT removed', ('datasets', reference.split('/', 1)[1])).fetchone()
                view = row[0].get('view') if row and isinstance(row[0], dict) else None
        if state not in ('succeeded', builds.ADOPTED) or not directory:
            raise store.ProjectError(f'Run {run_id} is {state}; only a finished run has a product to look inside.',
                                     'not-found')
        return inside.Product(run_id, os.path.join(directory, builds.OUTPUT), view)

    def product_file(self, run, address, range_header=None):
        """The inside.FileResponse of GET /api/project/file; the caller has checked the right to inspect."""
        with self._lock:
            product = self._product(run)
        return inside.file_response(product, address, range_header)

    # ------------------------------------------------------------- changes

    def _set_definition(self, arguments, actor):
        with self._open() as project:
            project.set_definition(arguments['reference'], arguments['text'])
            return project.definition(arguments['reference'])

    def _remove_definition(self, arguments, actor):
        with self._open() as project:
            project.remove_definition(arguments['reference'])
        return {'removed': arguments['reference']}

    def _revert_definition(self, arguments, actor):
        with self._open() as project:
            return project.revert_definition(arguments['reference'])

    def _save(self, arguments, actor):
        with self._open() as project:
            return project.save()

    def _resolve_conflict(self, arguments, actor):
        with self._open(on_conflict=arguments['choice']) as project:
            return self._summary_of(project)

    def _import_values(self, arguments, actor):
        with self._open() as project:
            return project.import_values(arguments['text'])

    def _check_environment(self, arguments, actor):
        with self._open() as project:
            return environments.check(project, arguments['reference'])

    def _connect_environment(self, arguments, actor):
        with self._open() as project:
            return environments.connect(project, arguments['reference'], arguments['interpreter'])

    def _disconnect_environment(self, arguments, actor):
        with self._open() as project:
            done = environments.disconnect(project, arguments['reference'])
        return {'disconnected': done['reference'], **done}

    def _request_build(self, arguments, actor):
        with self._open() as project:
            return build_requests.request(project, arguments['targets'], every=arguments.get('every', False),
                                          scratch=arguments.get('scratch', False), actor=actor)

    def _approve_build(self, arguments, actor):
        with self._open() as project:
            return build_requests.approve(project, arguments['request'], actor=actor)

    def _decline_build(self, arguments, actor):
        with self._open() as project:
            return build_requests.decline(project, arguments['request'], actor=actor,
                                          reason=arguments.get('reason', ''))

    def _cancel_build(self, arguments, actor):
        with self._open() as project:
            return build_requests.cancel(project, arguments['request'], actor=actor)

    def _cancel_run(self, arguments, actor):
        with self._open() as project:
            return builds.cancel(project, arguments['run'])

    def _stop_run(self, arguments, actor):
        return builds.stop(self.folder, arguments['run'], dsn=self.dsn)
