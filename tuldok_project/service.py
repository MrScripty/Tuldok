"""The operations of one served project folder, called with an actor and JSON arguments.

Owns section 3 of docs/plans/definition-first-projects/spec-m7.md. Service.call
checks a call against the table in operations.py (the operation exists, the
actor satisfies its who rule from kind and scopes alone, the arguments match
its schema), runs it with the project open only for the moment it needs, and
returns a JSON-plain object. Calls are answered one at a time under one lock
of the service. Every mutating call that passed the actor check writes one
activity row, done or refused. The six operations on build requests are
passed to build_requests. The five reads inside a product (spec-d1.md), the
three reads of a model's weights (spec-d2.md), the two of the fields a run
kept (spec-d6.md), the three of a model's graph (spec-t2.md) and the five of
an embeddings set (docs/plans/training-and-curation/spec-t5.md) find the
finished run (and for weights_compare and the graph's overlay and comparison
the other run, for an embeddings set the run of its records) with the project
open for a moment and read its output directory through inside.py,
inside_weights.py, inside_fields.py, inside_graph.py and embeddings.py after
closing it; embeddings, which lists a dataset's sets, finds the products
under the lock and reads their indexes after;
product_file does the same for the file route; those reads run outside the
lock, so a long one holds up no other call. The five reads of what a
training script logged (docs/plans/training-and-curation/spec-t1.md) do the
same for a run in any state that has a directory (training.py), and
product_file serves a file under training/ of such a run. The five operations
on annotations (spec-d4.md section 5) work the same way: what the database
holds of a task (its rows, the hashes kept for its product) is read under the
lock, the product is read and hashed outside it (annotation_records), and
what was computed is kept under the lock again; set_annotation finds and
reads the records it names before it takes the lock to check and store them.
The five operations on the Pumas endpoint (spec-d5.md sections 2 and 4) call
it outside the lock, through pumas.py: endpoint, set_endpoint and
find_endpoints need no project at all (the address is a setting of the
machine, in local.py's settings file), and suggestion_models and
suggest_annotation find the task's product under the lock and read it and
ask the endpoint after releasing it. Two of the three comparisons of
spec-t3.md (intervals, model_compare) read the project under the lock and
resample its per-case values after releasing it (comparing.py). Nothing here knows of HTTP or of the
app's access layer.

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
import json
import logging
import math
import os
import threading

import jsonschema
import psycopg

from . import (activity, annotation_records, annotation_review, annotation_rows, annotations, build_requests, builds,
               charts, check, comparing, documents, embeddings, environments, inside, inside_fields, inside_graph,
               inside_weights, launcher, local, operations, plan, pumas, store, sweeps, training, workspace)
from .documents import Problem

CHECK_PROBLEMS = 200

# The reads inside a product (spec-d1.md, spec-d2.md, spec-d6.md, and spec-t2.md's model graph), each a function of
# ({argument: inside.Product}, arguments):
# the products of the arguments in PRODUCT_ARGUMENTS that the call gives. call() finds them under the service's lock
# and reads outside it: decompressing a large member, parsing a large mesh or comparing two large weights files takes
# seconds, and the other calls (the page's own readings among them) must not wait for it. inside.py guards what it
# keeps.
PRODUCT_ARGUMENTS = ('run', 'other_run', 'records_run')
INSIDE_READS = {
    'records': lambda found, a: inside.records(found['run'], offset=a.get('offset', 0), limit=a.get('limit', 50),
                                               kind=a.get('kind'), split=a.get('split')),
    'record': lambda found, a: inside.record(found['run'], a.get('id'), path=a.get('path')),
    'inside': lambda found, a: inside.inside(found['run'], path=a.get('path', ''), offset=a.get('offset', 0),
                                             limit=a.get('limit', 200)),
    'array_slice': lambda found, a: inside.array_slice(found['run'], path=a['path'], array=a.get('array'),
                                                       axes=a.get('axes'), index=a.get('index'),
                                                       most=a.get('most', 256)),
    'array_summary': lambda found, a: inside.array_summary(found['run'], path=a['path'], array=a.get('array'),
                                                           bins=a.get('bins', 64)),
    'weights': lambda found, a: inside_weights.weights(found['run']),
    'weights_compare': lambda found, a: inside_weights.weights_compare(found['run'], path=a['path'],
                                                                       other=found['other_run'],
                                                                       other_path=a['other_path']),
    'array_tiles': lambda found, a: inside_weights.array_tiles(found['run'], path=a['path'], array=a.get('array'),
                                                               across=a.get('across'), axes=a.get('axes'),
                                                               index=a.get('index'), first=a.get('first', 0),
                                                               most=a.get('most', 16)),
    'fields': lambda found, a: inside_fields.fields(found['run']),
    'field_compare': lambda found, a: inside_fields.field_compare(found['run'], entry=a['entry'], case=a['case'],
                                                                  axis=a.get('axis'), index=a.get('index'),
                                                                  mean_free=a.get('mean_free', False)),
    'model_graph': lambda found, a: inside_graph.model_graph(found['run'], depth=a.get('depth'),
                                                             opened=a.get('open', ()), closed=a.get('close', ())),
    'model_graph_overlay': lambda found, a: inside_graph.model_graph_overlay(
        found['run'], kind=a['kind'], against=a.get('against'), other=found.get('other_run'), path=a.get('path'),
        other_path=a.get('other_path')),
    'model_graph_compare': lambda found, a: inside_graph.model_graph_compare(found['run'], other=found['other_run']),
    # Curation by embeddings (docs/plans/training-and-curation/spec-t5.md section 4): a set in run's product, the
    # records it describes in records_run's (default run's).
    'embedding_map': lambda found, a: embeddings.embedding_map(
        found['run'], found.get('records_run', found['run']), a['name'], colour=a.get('colour'),
        cells=a.get('cells', 24), thin=a.get('thin', 0.25)),
    'embedding_neighbours': lambda found, a: embeddings.embedding_neighbours(
        found['run'], found.get('records_run', found['run']), a['name'], record=a['record'],
        limit=a.get('limit', 12)),
    'embedding_duplicates': lambda found, a: embeddings.embedding_duplicates(
        found['run'], found.get('records_run', found['run']), a['name'], threshold=a.get('threshold', 0.98),
        limit=a.get('limit', 200)),
    'embedding_outliers': lambda found, a: embeddings.embedding_outliers(
        found['run'], found.get('records_run', found['run']), a['name'], k=a.get('k', 5), limit=a.get('limit', 50)),
    'embedding_leakage': lambda found, a: embeddings.embedding_leakage(
        found['run'], found.get('records_run', found['run']), a['name'], threshold=a.get('threshold', 0.95),
        train=a.get('train', 'train'), limit=a.get('limit', 200)),
}
# The reads of what a training script logged (docs/plans/training-and-curation/spec-t1.md section 4), each a function
# of (training.Run, arguments): the run is found under the service's lock, whatever its state, and its files are read
# outside it, as the reads inside a product are.
TRAINING_READS = {
    'training': lambda run, a: training.overview(run),
    'training_series': lambda run, a: training.series(run, a['series'], most=a.get('most', 1000)),
    'training_histograms': lambda run, a: training.histograms(run, name=a['name'], kind=a['kind'],
                                                              most=a.get('most', 120), bins=a.get('bins', 48)),
    'training_samples': lambda run, a: training.samples(run, name=a.get('name'), offset=a.get('offset', 0),
                                                        limit=a.get('limit', 50)),
    'training_sample': lambda run, a: training.sample(run, index=a['index']),
}
# The reads of annotations (spec-d4.md section 5): each takes the service's lock itself, only for its database work.
ANNOTATION_READS = ('annotation_tasks', 'annotated_records', 'annotation',
                    'annotation_sets', 'annotation_agreement', 'annotation_compare')   # the last three: spec-t4
# The calls to the Pumas endpoint (spec-d5.md): each is made outside the service's lock; those that read a project
# take the lock themselves, only for their database work.
# The comparisons of spec-t3.md that resample per-case values: read under the lock, computed outside it.
COMPARING_READS = ('intervals', 'model_compare')
# keep_annotation reads the sets outside the lock, then keeps its decision as set_annotation does (spec-t4.md).
OUTSIDE_LOCK = ANNOTATION_READS + COMPARING_READS + ('keep_annotation', 'endpoint', 'set_endpoint', 'find_endpoints',
                                                     'suggestion_models', 'suggest_annotation',
                                                     'embeddings', 'set_embedder')
POLL_SECONDS = 1.0          # how often the worker looks for a queued request
CLOSE_SECONDS = 30.0        # how long close() waits for the worker
WORKER_LOCK = 'build-requests.lock'
_LOG = logging.getLogger(__name__)
_TARGET_ARGUMENTS = ('reference', 'run', 'request', 'task')


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
                if key == 'task':  # a task is named by its reference, given as a bare name or not
                    return annotation_rows.reference(_bare(arguments[key], annotation_rows.DIRECTORY))
                return arguments[key]
    return ''


def _detail(name, result):
    """The detail of a done activity row: how many records a change of annotations touched."""
    if name == 'set_annotation':
        return f'{result["set"]} set, {result["removed"]} removed'
    if name == 'revert_annotations':
        return f'{result["reverted"]} reverted'
    if name == 'set_endpoint':
        return 'set' if result['address'] else 'cleared'
    if name == 'keep_annotation':
        return f'{result["record"]} {result["state"]}'
    if name == 'set_embedder':
        return 'set' if result['model'] else 'default'
    return ''


def _now():
    """The time an annotation is made: UTC, to the second (spec-d4.md section 2)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


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
            if made.get('sweep'):   # a sweep's trials, one after another (spec-t7.md section 5)
                outcome['done'] = sweeps.execute(self.folder, made, request_id=request_id, scratch=request['scratch'],
                                                 dsn=self.dsn, expect=request['covers'], stop=stop, on_event=on_event)
            else:
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
                found = {key: self._product(arguments[key]) for key in PRODUCT_ARGUMENTS if key in arguments}
            return _plain(INSIDE_READS[name](found, dict(arguments)))
        if name in TRAINING_READS:
            problems = _argument_problems(operation, arguments)
            if problems:
                raise store.ProjectError(f'The arguments of project.{name} do not match its schema.', 'invalid',
                                         problems=problems)
            with self._lock:
                run = self._training_run(arguments['run'])
            return _plain(TRAINING_READS[name](run, dict(arguments)))
        if name in OUTSIDE_LOCK:
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
                self._record_activity(actor, name, _target(arguments), 'done', _detail(name, result))
            return result
        prepared = ()
        if name == 'set_annotation':  # the records are found and read before the lock is taken to store them
            try:
                problems = _argument_problems(operation, arguments)
                if problems:
                    raise store.ProjectError(f'The arguments of project.{name} do not match its schema.', 'invalid',
                                             problems=problems)
                prepared = (self._prepare_annotations(dict(arguments)),)
            except store.ProjectError as exc:
                self._record_activity(actor, name, _target(arguments), exc.code, str(exc))
                raise
            except Exception as exc:
                self._record_activity(actor, name, _target(arguments), 'error', f'{type(exc).__name__}: {exc}')
                raise
        with self._lock:
            try:
                problems = [] if prepared else _argument_problems(operation, arguments)  # prepared: checked above
                if problems:
                    raise store.ProjectError(f'The arguments of project.{name} do not match its schema.', 'invalid',
                                             problems=problems)
                result = _plain(getattr(self, f'_{name}')(dict(arguments), actor, *prepared))
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
                self._record_activity(actor, name, target, 'done', _detail(name, result))
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

    def _intervals(self, arguments, actor):
        with self._lock, self._open() as project:
            gathered = comparing.gather_intervals(project, arguments['benchmark'])
        return comparing.intervals(gathered)

    def _model_compare(self, arguments, actor):
        with self._lock, self._open() as project:
            gathered = comparing.gather_compare(project, arguments['recipes'])
        return comparing.model_compare(gathered, arguments.get('statistic', 'median'))

    def _benchmark_axes(self, arguments, actor):
        with self._open() as project:
            gathered = comparing.gather_axes(project, arguments['benchmark'])
        return comparing.benchmark_axes(gathered, arguments.get('statistic', 'median'))

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

    def _sweeps(self, arguments, actor):
        with self._open() as project:
            return sweeps.listing(project)

    def _sweep(self, arguments, actor):
        with self._open() as project:
            return sweeps.show(project, arguments['sweep'], arguments.get('run'))

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
        """The inside.Product of a finished run (succeeded or adopted), read with the project open for a moment.

        It carries the outputs its products row records (with their roles), so that inside_weights knows which
        files are the run's weights without opening the project.
        """
        with self._open() as project:
            run_id = builds.find_run(project, run)
            state, directory, reference = project._execute(
                'SELECT state, directory, reference FROM {schema}.runs WHERE id = %s', (run_id,)).fetchone()
            recorded = project._execute('SELECT outputs FROM {schema}.products WHERE run_id = %s',
                                        (run_id,)).fetchone()
            view = None
            if reference.startswith('datasets/'):
                row = project._execute('SELECT document FROM {schema}.definitions WHERE directory = %s AND name = %s '
                                       'AND NOT removed', ('datasets', reference.split('/', 1)[1])).fetchone()
                view = row[0].get('view') if row and isinstance(row[0], dict) else None
        if state not in ('succeeded', builds.ADOPTED) or not directory:
            raise store.ProjectError(f'Run {run_id} is {state}; only a finished run has a product to look inside.',
                                     'not-found')
        return inside.Product(run_id, os.path.join(directory, builds.OUTPUT), view,
                              recorded[0] if recorded else None)

    def _embeddings(self, arguments, actor):
        """A dataset's embeddings sets (spec-t5.md section 3): the products are found under the lock, read after."""
        reference = arguments['dataset']
        reference = reference if reference.startswith('datasets/') else f'datasets/{reference}'
        with self._lock:
            with self._open() as project:
                if project._execute('SELECT 1 FROM {schema}.definitions WHERE directory = %s AND name = %s AND '
                                    'NOT removed', ('datasets', reference.split('/', 1)[1])).fetchone() is None:
                    raise store.ProjectError(f'There is no dataset {reference}.', 'not-found')
                holders = [reference]
                for name, document in project._execute(
                        'SELECT name, document FROM {schema}.definitions WHERE directory = %s AND NOT removed '
                        'ORDER BY name', ('datasets',)).fetchall():
                    run = document.get('run') if isinstance(document, dict) else None
                    inputs = run.get('inputs') if isinstance(run, dict) else None
                    if isinstance(inputs, dict) and reference in inputs.values() and f'datasets/{name}' != reference:
                        holders.append(f'datasets/{name}')
                found = [(holder, product) for holder in holders for product in builds.products(project, holder)
                         if product['run_id']]
                recorded = {row[0]: row[1] or {} for row in project._execute(
                    'SELECT id, inputs FROM {schema}.runs WHERE id = ANY(%s)',
                    ([product['run_id'] for _, product in found],)).fetchall()}
        own = [product['run_id'] for holder, product in found if holder == reference]
        sets = []
        for holder, product in found:
            try:
                listed = embeddings.sets(inside.Product(product['run_id'], product['directory']))
            except store.ProjectError:
                continue
            for item in listed:
                entry = {'run': product['run_id'], 'holder': holder, 'name': item['name'], 'rows': None,
                         'dimensions': None, 'model': None, 'prefix': None, 'source': None, 'records_run': None,
                         'current': False, 'projection': None, 'notes': [], 'problem': item['problem']}
                if item['index'] is not None:
                    entry.update(embeddings.described(item['index']))
                    source = entry['source']
                    named = source['dataset'] or holder
                    if named != reference:
                        continue
                    if source['run']:
                        entry['records_run'] = source['run']
                    elif named == holder:
                        entry['records_run'] = product['run_id']
                    else:
                        used = [value.get('run_id') for value in recorded.get(product['run_id'], {}).values()
                                if isinstance(value, dict) and value.get('reference') == reference]
                        entry['records_run'] = used[0] if used else None
                        if not used:
                            entry['problem'] = (f'The run {product["run_id"][:12]} that holds it recorded no input '
                                                f'{reference}, so its records cannot be found.')
                    entry['current'] = entry['records_run'] in own
                elif holder != reference:
                    continue
                sets.append(entry)
        return {'dataset': reference, 'run': own[0] if own else None, 'sets': sets}

    def _training_run(self, run):
        """The training.Run of a run in any state, read with the project open for a moment (spec-t1.md)."""
        with self._open() as project:
            run_id = builds.find_run(project, run)
            state, directory = project._execute('SELECT state, directory FROM {schema}.runs WHERE id = %s',
                                                (run_id,)).fetchone()
        return training.Run(run_id, state, os.path.join(directory, builds.OUTPUT) if directory else None)

    def product_file(self, run, address, range_header=None):
        """The inside.FileResponse of GET /api/project/file; the caller has checked the right to inspect.

        A file under training/ is served for a run in any state that has an output directory (a running run's
        samples, spec-t1.md section 4); any other file only for a finished run's product.
        """
        with self._lock:
            if isinstance(address, str) and address.startswith(training.DIRECTORY + '/') and '!' not in address:
                product = self._training_run(run).product()
            else:
                product = self._product(run)
        return inside.file_response(product, address, range_header)

    # ---------------------------------------------------------- annotations

    def _located(self, project, document):
        """(run id, output directory, the dataset's view) of the current product of a task's dataset, or None."""
        dataset = document.get('dataset') if isinstance(document, dict) else None
        if not isinstance(dataset, str):
            return None
        row = project._execute('''SELECT p.run_id, r.state, r.directory FROM {schema}.products p
                                  JOIN {schema}.runs r ON r.id = p.run_id
                                  WHERE p.reference = %s AND p.subject = '' AND p.current''', (dataset,)).fetchone()
        if row is None or row[1] not in ('succeeded', builds.ADOPTED) or not row[2]:
            return None
        parsed = documents.parse_reference(dataset)
        held = project._execute('SELECT document FROM {schema}.definitions WHERE directory = %s AND name = %s '
                                'AND NOT removed', parsed).fetchone() if parsed else None
        view = held[0].get('view') if held and isinstance(held[0], dict) else None
        return row[0], os.path.join(row[2], builds.OUTPUT), view

    @staticmethod
    def _product_of(located):
        """(inside.Product, its record index) of what _located found, or (None, None) when there is none."""
        if located is None:
            return None, None
        try:
            product = inside.Product(*located)
        except store.ProjectError:
            return None, None  # its output directory is gone
        return product, annotation_records.index(product)

    def _gather(self, project, name, document):
        """What the database holds of one task for its counts and its records: read under the lock."""
        connection, schema = project._connection, project.schema
        annotation_rows.recheck(connection, schema, name, document)
        located = self._located(project, document)
        return {'name': name, 'document': document, 'located': located,
                'held': annotation_rows.held_rows(connection, schema, name),
                'unsaved': annotation_rows.unsaved_counts(connection, schema).get(name, 0),
                'kept': annotation_rows.cached_hashes(connection, schema, located[0]) if located else {}}

    @staticmethod
    def _judge(gathered):
        """Read the task's product outside the lock: its index, the hashes of the annotated records, what is stale."""
        product, index = Service._product_of(gathered['located'])
        held = gathered['held']
        hashes, computed, stale = {}, {}, set()
        if index is not None:
            hashes, computed = annotation_records.current_hashes(product, index, held, gathered['kept'])
            stale = {record for record, (sha, *_rest) in held.items()
                     if annotation_records.is_stale(record, sha, index, hashes)}
        counts = dict.fromkeys(operations.ANNOTATION_COUNTS, 0)
        for _sha, state, valid, _unsaved in held.values():
            counts[state] += 1
            counts['invalid'] += not valid
        counts['stale'] = len(stale)
        if index is not None:
            counts['unannotated'] = len(index.records) - sum(1 for record in held if record in index.by_id)
        return {**gathered, 'product': product, 'index': index, 'hashes': hashes, 'computed': computed,
                'stale': stale, 'counts': counts}

    def _keep_hashes(self, judged):
        """Keep the hashes computed outside the lock, per run and record."""
        if judged['computed']:
            with self._lock, self._open() as project:
                annotation_rows.keep_hashes(project._connection, project.schema, judged['located'][0],
                                            judged['computed'])

    def _annotation_tasks(self, arguments, actor):
        with self._lock, self._open() as project:
            gathered = [self._gather(project, name, document) for name, document in project.annotation_tasks().items()]
        tasks = []
        for item in gathered:
            judged = self._judge(item)
            self._keep_hashes(judged)
            document, index = judged['document'], judged['index']
            tasks.append({'task': annotation_rows.reference(judged['name']), 'title': document.get('title'),
                          'dataset': document.get('dataset'), 'type': document.get('task'),
                          'vocabulary': document.get('vocabulary') or [],
                          'run': judged['located'][0] if index is not None else None,
                          'records': len(index.records) if index is not None else None,
                          'counts': judged['counts'], 'unsaved': judged['unsaved']})
        return {'tasks': tasks}

    def _annotated_records(self, arguments, actor):
        with self._lock, self._open() as project:
            name, document = project.annotation_task(arguments['task'])
            gathered = self._gather(project, name, document)
        judged = self._judge(gathered)
        held, index, stale = judged['held'], judged['index'], judged['stale']
        wanted, kind = arguments.get('state'), arguments.get('kind')
        listed = [record for record in (index.records if index is not None else [])
                  if kind is None or record['kind'] == kind]
        gone = [] if kind is not None else sorted(
            (record for record in held if index is None or record not in index.by_id), key=annotations.sort_key)

        def chosen(record_id):
            if wanted is None:
                return True
            if wanted == 'unannotated':
                return record_id not in held
            if record_id not in held:
                return False
            if wanted == 'stale':
                return record_id in stale
            if wanted == 'invalid':
                return not held[record_id][2]
            return held[record_id][1] == wanted

        ids = [(record['id'], record) for record in listed if chosen(record['id'])]
        ids += [(record_id, None) for record_id in gone if wanted != 'unannotated' and chosen(record_id)]
        offset, limit = arguments.get('offset', 0), arguments.get('limit', 50)
        page = ids[offset:offset + limit]
        with self._lock, self._open() as project:
            if judged['computed']:
                annotation_rows.keep_hashes(project._connection, project.schema, judged['located'][0],
                                            judged['computed'])
            found = annotation_rows.rows(project._connection, project.schema, name, [record_id for record_id, _ in page])
        records = []
        for record_id, record in page:
            shown = (annotation_records.shown(judged['product'], record) if record is not None
                     else {'id': record_id, 'kind': None, 'path': None, 'split': None, 'rights': None,
                           'origin': None, 'meta': None, 'sha256': None, 'bytes': None})
            shown['in_product'] = record is not None
            current, _saved, unsaved = found.get(record_id, (None, None, False))
            shown['annotation'] = None if current is None else {
                'state': current['state'], 'value': current['value'], 'note': current.get('note'),
                'by': current['by'], 'at': current['at'],
                'stale': record_id in stale if index is not None else None, 'unsaved': unsaved}
            records.append(shown)
        return {'task': annotation_rows.reference(name), 'run': judged['located'][0] if index is not None else None,
                'records': records, 'total': len(ids), 'counts': judged['counts']}

    def _annotation(self, arguments, actor):
        record_id = arguments['record']
        with self._lock, self._open() as project:
            name, document = project.annotation_task(arguments['task'])
            located = self._located(project, document)
            kept = (annotation_rows.cached_hashes(project._connection, project.schema, located[0], [record_id])
                    if located else {})
            current, saved, unsaved = annotation_rows.rows(project._connection, project.schema, name,
                                                           [record_id]).get(record_id, (None, None, False))
        product, index = self._product_of(located)
        sha256, stale = None, None
        if index is not None:
            hashes, computed = annotation_records.current_hashes(product, index, [record_id], kept)
            sha256 = hashes.get(record_id)
            if current is not None:
                stale = annotation_records.is_stale(record_id, current['sha256'], index, hashes)
            self._keep_hashes({'computed': computed, 'located': located})
        return {'task': annotation_rows.reference(name), 'record': record_id, 'annotation': current,
                'saved': None if saved is None else json.loads(saved), 'unsaved': unsaved, 'stale': stale,
                'sha256': sha256}

    def _prepare_annotations(self, arguments):
        """Find the task and its product under the lock, then read the records the items set outside it.

        Returns what _set_annotation needs: the task as it was, the run, and
        for each record set, its facts and hash (None when the product does not
        have it), and the hashes computed here.
        """
        setting = [item['record'] for item in arguments['items'] if not item.get('remove')]
        with self._lock, self._open() as project:
            name, document = project.annotation_task(arguments['task'])
            located = self._located(project, document)
            kept = (annotation_rows.cached_hashes(project._connection, project.schema, located[0], setting)
                    if located and setting else {})
        known, computed = {}, {}
        if setting:
            product, index = self._product_of(located)
            if index is None:
                raise store.ProjectError(f'{document.get("dataset")} has no product to annotate; build it first.',
                                         'not-found', references=[document.get('dataset')])
            hashes, computed = annotation_records.current_hashes(product, index, setting, kept)
            for record_id in setting:
                position = index.by_id.get(record_id)
                if position is not None:
                    known[record_id] = (annotation_records.facts(product, index.records[position],
                                                                 document.get('task')), hashes.get(record_id))
        return {'name': name, 'document': document, 'run': located[0] if located else None, 'known': known,
                'computed': computed}

    def _set_annotation(self, arguments, actor, prepared):
        with self._open() as project:
            name, document = project.annotation_task(arguments['task'])
            located = self._located(project, document)
            if (annotation_rows.fingerprint(document) != annotation_rows.fingerprint(prepared['document'])
                    or document.get('dataset') != prepared['document'].get('dataset')
                    or (located[0] if located else None) != prepared['run']):
                raise store.ProjectError(f'{annotation_rows.reference(name)} or the product of its dataset changed '
                                         'while the annotations were being checked; try again.', 'busy',
                                         references=[annotation_rows.reference(name)])
            if prepared['computed']:
                annotation_rows.keep_hashes(project._connection, project.schema, prepared['run'],
                                            prepared['computed'])
            rows, removals, problems = annotation_records.check_items(
                document, arguments['items'], prepared['known'], by=annotation_records.by_of(actor), at=_now(),
                origin=arguments.get('from'))
            if problems:
                raise store.ProjectError(f'{len(problems)} of the items cannot be kept; nothing was changed.',
                                         'invalid', problems=[Problem('error', annotation_rows.path(name), pointer,
                                                                      message) for pointer, message in problems],
                                         references=[annotation_rows.reference(name)])
            done, removed, unsaved = project.set_annotations(name, rows, removals, document)
        return {'task': annotation_rows.reference(name), 'set': done, 'removed': removed, 'unsaved': unsaved}

    def _revert_annotations(self, arguments, actor):
        with self._open() as project:
            name, document = project.annotation_task(arguments['task'])
            reverted = project.revert_annotations(name, arguments.get('records'), document)
        return {'task': annotation_rows.reference(name), 'reverted': reverted}

    # ------------------------------------------------------- the endpoint

    @staticmethod
    def _embedder_setting():
        try:
            return local.embedder_settings()
        except local.SettingsError as exc:
            raise store.ProjectError(str(exc), 'invalid') from None

    def _endpoint(self, arguments, actor):
        return pumas.observe(local.pumas_endpoint(), self._embedder_setting())

    def _set_embedder(self, arguments, actor):
        """Keep the machine's embedder once the endpoint serves it with an embedding capability (spec-t5.md
        section 2); a null model is EmbeddingGemma 2, which needs no check."""
        model, profile, prefix = arguments['model'], arguments.get('profile'), arguments.get('prefix')
        if model is None and profile is not None:
            raise store.ProjectError('A profile goes with a model; name the model too, or clear both.', 'invalid')
        if model is not None:
            address = local.pumas_endpoint()
            if address is None:
                raise store.ProjectError(pumas.NO_ENDPOINT, 'unavailable')
            try:
                pumas.choose_embedder(pumas.served(address), model, profile)
            except pumas.PumasError as exc:
                raise store.ProjectError(str(exc), exc.code) from None
        local.set_embedder(model, profile, prefix)
        return self._endpoint({}, actor)['embedder']

    def _set_endpoint(self, arguments, actor):
        """Ask the address once what it serves and keep it when it answered; null clears the setting."""
        if arguments['address'] is None:
            local.set_pumas_endpoint(None)
            return pumas.observe(None, self._embedder_setting())
        try:
            address = pumas.normalize(arguments['address'])
        except pumas.PumasError as exc:
            raise store.ProjectError(str(exc), exc.code) from None
        seen = pumas.observe(address, self._embedder_setting())
        if not seen['answered']:
            raise store.ProjectError(f'The Pumas endpoint at {address} did not answer, so it was not set: '
                                     f'{seen["problem"]}', 'unavailable')
        local.set_pumas_endpoint(address)
        return seen

    def _find_endpoints(self, arguments, actor):
        try:
            return pumas.find()
        except pumas.PumasError as exc:
            raise store.ProjectError(str(exc), exc.code) from None

    def _task_product(self, task):
        """(name, document, inside.Product or None, its record index or None) of a task: found under the lock."""
        with self._lock, self._open() as project:
            name, document = project.annotation_task(task)
            located = self._located(project, document)
        product, index = self._product_of(located)
        return name, document, product, index

    def _suggestion_models(self, arguments, actor):
        name, document, _product, index = self._task_product(arguments['task'])
        task = document.get('task')
        kinds = sorted({record['kind'] for record in index.records} if index is not None else ())
        kinds = [kind for kind in kinds if annotations.allows_kind(task, kind)]
        result = {'task': annotation_rows.reference(name), 'type': task, 'address': local.pumas_endpoint(),
                  'kinds': {kind: [] for kind in kinds}, 'problem': None}
        if result['address'] is None:
            result['problem'] = pumas.NO_ENDPOINT
            return result
        try:
            listing = pumas.served(result['address'])
        except pumas.PumasError as exc:
            result['problem'] = str(exc)
            return result
        for kind in kinds:
            for entry in listing['models']:
                found = pumas.routes(entry, task, kind)
                if found:
                    result['kinds'][kind].append({'model': entry['model'], 'profile': entry['profile'],
                                                  'capability': found[0]['capability']})
        return result

    def _suggest_annotation(self, arguments, actor):
        """A value of the task for one record, asked of a served model; nothing is stored (spec-d5.md section 4)."""
        record_id = arguments['record']
        name, document, product, index = self._task_product(arguments['task'])
        reference = annotation_rows.reference(name)
        task, vocabulary = document.get('task'), document.get('vocabulary') or []
        if index is None:
            raise store.ProjectError(f'{document.get("dataset")} has no product to annotate; build it first.',
                                     'not-found', references=[document.get('dataset')])
        position = index.by_id.get(record_id)
        if position is None:
            raise store.ProjectError(f'The record {record_id!r} is not in the product of {document.get("dataset")}.',
                                     'not-found', references=[reference])
        record = index.records[position]
        if not annotations.allows_kind(task, record['kind']):
            raise store.ProjectError(f'A {task} task does not annotate records of kind {record["kind"]!r}.', 'invalid',
                                     references=[reference])
        address = local.pumas_endpoint()
        if address is None:
            raise store.ProjectError(pumas.NO_ENDPOINT, 'unavailable')
        facts = annotation_records.facts(product, record, task)

        def check(value):
            errors, unknown = annotations.value_problems(task, vocabulary, 'draft', value, kind=record['kind'],
                                                         size=facts['size'], length=facts['length'],
                                                         duration=facts['duration'])
            return errors + [f'The term {term!r} is not in the vocabulary of the task.' for term in unknown]

        try:
            listing = pumas.served(address)
            entry = pumas.choose(listing, arguments['model'], arguments.get('profile'))
            found = pumas.routes(entry, task, record['kind'])
            if not found:
                raise pumas.PumasError(f'{entry["model"]} ({entry["profile"]}) cannot suggest a value of a {task} task '
                                       f'for a {record["kind"]} record now.', 'unavailable')
            content = annotation_records.content(product, record, pumas.CONTENT_LIMIT)
            value = pumas.suggest(address, listing, entry, found[0], task, vocabulary, content,
                                  arguments.get('instruction'), request_id=f'tuldok-suggest:{os.urandom(8).hex()}',
                                  check=check)
        except pumas.PumasError as exc:
            raise store.ProjectError(str(exc), exc.code, references=[reference]) from None
        return {'task': reference, 'record': record_id,
                'suggestion': {'value': value, 'from': {'model': entry['model'], 'profile': entry['profile'],
                                                        'capability': found[0]['capability']}}}

    # --------------------------------------------- annotation sets (spec-t4.md)

    def _review(self, task):
        """What the database holds of a task's sets (annotation_review.gather), read under the lock."""
        with self._lock, self._open() as project:
            name, document = project.annotation_task(task)
            return annotation_review.gather(project, name, document, self._located(project, document))

    def _annotation_sets(self, arguments, actor):
        return annotation_review.sets_answer(self._review(arguments['task']))

    def _annotation_agreement(self, arguments, actor):
        return annotation_review.agreement_answer(self._review(arguments['task']), arguments)

    def _annotation_compare(self, arguments, actor):
        gathered = self._review(arguments['task'])
        product, index = self._product_of(gathered['located'])
        return annotation_review.compare_answer(gathered, arguments, product, index)

    def _keep_annotation(self, arguments, actor):
        """A decision on one record kept through set_annotation's own path, its sidecars staged first."""
        gathered = self._review(arguments['task'])
        item, origin, staged = annotation_review.keep_items(gathered, arguments)
        if staged:
            with self._lock, self._open() as project:
                for file, data in staged.items():
                    annotation_rows.stage_sidecar(project._connection, project.schema, gathered['name'], file, data)
        setting = {'task': arguments['task'], 'items': [item], 'from': origin}
        prepared = self._prepare_annotations(setting)
        with self._lock:
            done = self._set_annotation(setting, actor, prepared)
        return {'task': done['task'], 'record': arguments['record'], 'state': item['state'], 'unsaved': done['unsaved']}

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
