"""Build requests: builds asked for through the service, approved by the owner and run by its worker.

Owns section 4 of docs/plans/definition-first-projects/spec-m7.md, except the
worker's thread and lock, which service.py owns. One table of a project
schema, build_requests, holds every request: what was asked (targets, every,
scratch), what it covers (the build steps, their subjects, the commit and the
SHA-256 of every definition in the plan) and the SHA-256 of that, who asked
and who decided, and how its build ended. The owner's request is queued at
once; an agent's waits for the owner's approval, which is refused (stale) when
what the request covers has changed since it was shown. The functions the
worker needs are here too: reap_orphans, take, started, stop_asked,
ask_to_stop and finish. The few the worker calls while a build runs, with the
project closed, use a connection of their own and never the project lock.
store.py creates the table with the project schema.
"""
import datetime
import hashlib
import json
import os
import re
import uuid

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from . import builds, snapshot, store

STATES = ('awaiting-approval', 'queued', 'running', 'succeeded', 'failed', 'cancelled', 'declined', 'expired')
PENDING = ('awaiting-approval', 'queued')
PENDING_LIMIT = 20          # at most this many requests may await approval or be queued
EXPIRY_SECONDS = 3600       # a queued request not started within this long after its approval expires
PREFIX_MINIMUM = 6          # a request may be named by at least this many of its first characters
CHANGES_NAMED = 5
ORPHAN_PROBLEM = 'Tuldok stopped while this was running.'
_TEXT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')

TABLES = (
    '''CREATE TABLE IF NOT EXISTS {schema}.build_requests (
           id text PRIMARY KEY,
           state text NOT NULL,
           targets jsonb NOT NULL, every boolean NOT NULL, scratch boolean NOT NULL,
           covers jsonb NOT NULL, covers_sha256 text NOT NULL,
           requested_at timestamptz NOT NULL, requested_by jsonb NOT NULL,
           decided_at timestamptz, decided_by jsonb,
           started_at timestamptz, finished_at timestamptz,
           owner_pid integer, owner_boot text,
           plan_id text, cancel_requested boolean NOT NULL DEFAULT false,
           result jsonb, problem text)''',
)

_COLUMNS = ('id', 'state', 'targets', 'every', 'scratch', 'covers', 'requested_at', 'requested_by', 'decided_at',
            'decided_by', 'started_at', 'finished_at', 'plan_id', 'cancel_requested', 'result', 'problem')
_LISTED = tuple(column for column in _COLUMNS if column != 'covers')


def _q(schema, template):
    return sql.SQL(template).format(schema=sql.Identifier(schema))


def _who(actor):
    return {key: actor.get(key) for key in ('actor_id', 'kind', 'label')}


def _sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ------------------------------------------------------------------- covers

def covers_sha256(covers):
    """The SHA-256 of covers as JSON with sorted keys and no spaces (UTF-8, characters as they are)."""
    return _sha256(json.dumps(covers, sort_keys=True, separators=(',', ':'), ensure_ascii=False))


def _head(project, scratch):
    """HEAD of the code root, or None when scratch or when the code root is not in Git (or has no commit)."""
    if scratch:
        return None
    code_root = builds._code_root(project)
    try:
        snapshot._repository(code_root)
        return snapshot._head(code_root)
    except snapshot.SnapshotError:
        return None


def covers(project, made, targets, *, every, scratch):
    """What a build of made (plan.build_plan's result for targets) covers now (section 4).

    steps are the plan's build steps in order, each with the benchmark
    subjects execute would run (those to run that are not built yet);
    definitions has the SHA-256 of the text of every reference in the plan's
    steps, whatever its action.
    """
    status = builds.status(project)
    steps = []
    for step in made['steps']:
        if step['action'] != 'build':
            continue
        subjects = []
        if step['kind'] == 'benchmark':
            held = (status.get(step['reference']) or {}).get('subjects') or {}
            subjects = [name for name in step['subjects']['run'] if (held.get(name) or {}).get('state') != 'built']
        steps.append({'reference': step['reference'], 'subjects': subjects})
    references = sorted({step['reference'] for step in made['steps']})
    texts = dict(project._execute(f'SELECT {store._REFERENCE_SQL}, text FROM {{schema}}.definitions '
                                  f'WHERE NOT removed AND {store._REFERENCE_SQL} = ANY(%s)', (references,)).fetchall())
    return {'targets': list(targets), 'every': bool(every), 'scratch': bool(scratch),
            'commit': _head(project, scratch), 'steps': steps,
            'definitions': {reference: _sha256(texts[reference]) for reference in references if reference in texts}}


def _changed(before, now):
    """Words naming what differs between two covers: the commit, or up to five references."""
    words = []
    if before.get('commit') != now.get('commit'):
        words.append(f'the commit (was {(before.get("commit") or "none")[:12]}, '
                     f'now {(now.get("commit") or "none")[:12]})')
    old, new = before.get('definitions') or {}, now.get('definitions') or {}
    references = sorted(reference for reference in set(old) | set(new) if old.get(reference) != new.get(reference))
    if references:
        more = len(references) - CHANGES_NAMED
        words.append(', '.join(references[:CHANGES_NAMED]) + (f' and {more} more' if more > 0 else ''))
    if not words:
        words.append('the steps to build')
    return ' and '.join(words)


def _current(project, row):
    """(covers now, plan now, None) for a stored request, or (None, None, why it cannot be planned now)."""
    from . import plan as planning

    try:
        made = planning.build_plan(project, row['targets'], every=row['every'])
    except store.ProjectError as exc:
        return None, None, str(exc)
    return covers(project, made, row['targets'], every=row['every'], scratch=row['scratch']), made, None


def _stale_problem(row, now, why, verb):
    if now is None:
        return f'It can no longer be planned as asked, so it was {verb}: {why}'
    return f'What it covers changed since it was asked for, so it was {verb}: {_changed(row["covers"], now)}.'


# --------------------------------------------------------------- reading

def _row(project, request_id):
    row = project._execute('SELECT ' + ', '.join(_COLUMNS) + ', covers_sha256 FROM {schema}.build_requests '
                           'WHERE id = %s', (request_id,)).fetchone()
    return dict(zip(_COLUMNS + ('covers_sha256',), row))


def _with_expiry(shown):
    """shown with expires_at: when a queued request expires if it has not started; None in any other state."""
    queued = shown['state'] == 'queued' and shown['decided_at'] is not None
    shown['expires_at'] = shown['decided_at'] + datetime.timedelta(seconds=EXPIRY_SECONDS) if queued else None
    return shown


def _shown(row):
    return _with_expiry({column: row[column] for column in _COLUMNS})


def find(project, text):
    """The id of the request named by text: its id, or an unambiguous prefix of at least PREFIX_MINIMUM characters.

    Raises ProjectError not-found or ambiguous, as builds.find_run does for runs.
    """
    if not isinstance(text, str) or not _TEXT.fullmatch(text):
        raise store.ProjectError(f'{text!r} is not a build request id.', 'not-found')
    if project._execute('SELECT 1 FROM {schema}.build_requests WHERE id = %s', (text,)).fetchone() is not None:
        return text
    if len(text) < PREFIX_MINIMUM:
        raise store.ProjectError(f'There is no build request {text}; name a request by its id or at least its first '
                                 f'{PREFIX_MINIMUM} characters.', 'not-found')
    rows = project._execute('SELECT id, state, targets FROM {schema}.build_requests WHERE left(id, %s) = %s '
                            'ORDER BY requested_at DESC, id', (len(text), text)).fetchall()
    if not rows:
        raise store.ProjectError(f'There is no build request {text}.', 'not-found')
    if len(rows) > 1:
        listed = '\n'.join(f'  {request_id}  {state}  {" ".join(targets) or "-"}'
                            for request_id, state, targets in rows)
        raise store.ProjectError(f'{text} is the start of {len(rows)} build requests; give more of the id:\n{listed}',
                                 'ambiguous', references=[request_id for request_id, *_ in rows])
    return rows[0][0]


def listing(project, *, state=None, limit=100):
    """The requests, newest first, without their covers (with expires_at); only those in state when it is given."""
    query = 'SELECT ' + ', '.join(_LISTED) + ' FROM {schema}.build_requests'
    parameters = ()
    if state is not None:
        query += ' WHERE state = %s'
        parameters = (state,)
    query += ' ORDER BY requested_at DESC, id LIMIT %s'
    return [_with_expiry(dict(zip(_LISTED, row)))
            for row in project._execute(query, (*parameters, limit)).fetchall()]


def show(project, request_id):
    """One request with its covers, and runs: the runs of its build (its plan), oldest first."""
    shown = _shown(_row(project, find(project, request_id)))
    builds.reap_orphans(project._connection, project.schema)
    rows = [] if shown['plan_id'] is None else project._execute(
        'SELECT ' + ', '.join(builds._RUN_COLUMNS) + ' FROM {schema}.runs WHERE plan_id = %s ORDER BY queued_at, id',
        (shown['plan_id'],)).fetchall()
    shown['runs'] = [dict(zip(builds._RUN_COLUMNS, row)) for row in rows]
    return shown


# -------------------------------------------------------------- requests

def request(project, targets, *, every, scratch, actor):
    """Ask for a build of targets; return the request (with covers).

    Refused (ProjectError): not-found for a target that is not a definition,
    blocked when a target cannot be built, nothing-to-build when the plan has
    no build step, too-many when PENDING_LIMIT requests await approval or are
    queued. The owner's request is queued, decided by the owner; an agent's
    awaits approval.
    """
    from . import plan as planning

    made = planning.build_plan(project, list(targets), every=every)
    if made['blocked_targets']:
        raise store.ProjectError('These targets cannot be built: ' + ', '.join(made['blocked_targets'])
                                 + '. See plan for why.', 'blocked', references=made['blocked_targets'])
    if made['counts']['build'] == 0:
        raise store.ProjectError('Nothing would be built: everything asked for is built already.', 'nothing-to-build')
    pending = project._execute('SELECT count(*) FROM {schema}.build_requests WHERE state = ANY(%s)',
                               (list(PENDING),)).fetchone()[0]
    if pending >= PENDING_LIMIT:
        raise store.ProjectError(f'{pending} build requests already await approval or are queued; at most '
                                 f'{PENDING_LIMIT} may. Wait for them, or cancel some.', 'too-many')
    covered = covers(project, made, targets, every=every, scratch=scratch)
    owner = actor.get('kind') == 'owner'
    request_id = uuid.uuid4().hex
    project._execute('''INSERT INTO {schema}.build_requests (id, state, targets, every, scratch, covers, covers_sha256,
                            requested_at, requested_by, decided_at, decided_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s, CASE WHEN %s THEN now() END, %s)''',
                     (request_id, 'queued' if owner else 'awaiting-approval', Jsonb(list(targets)), bool(every),
                      bool(scratch), Jsonb(covered), covers_sha256(covered), Jsonb(_who(actor)), owner,
                      Jsonb(_who(actor)) if owner else None))
    return _shown(_row(project, request_id))


def _awaiting(project, text):
    row = _row(project, find(project, text))
    if row['state'] != 'awaiting-approval':
        raise store.ProjectError(f'Build request {row["id"]} is {row["state"]}; only a request awaiting approval can '
                                 'be approved or declined.', 'not-awaiting')
    return row


def approve(project, request_id, *, actor):
    """Queue a request awaiting approval, when what it covers is unchanged; return it.

    Refused: not-awaiting for a request in another state; stale when its covers,
    computed again now, has another SHA-256 (the request is then declined, its
    problem naming what changed).
    """
    row = _awaiting(project, request_id)
    now, _made, why = _current(project, row)
    if now is None or covers_sha256(now) != row['covers_sha256']:
        problem = _stale_problem(row, now, why, 'declined')
        project._execute('''UPDATE {schema}.build_requests SET state = 'declined', decided_at = now(),
                                decided_by = %s, finished_at = now(), problem = %s WHERE id = %s''',
                         (Jsonb(_who(actor)), problem, row['id']))
        raise store.ProjectError(problem + ' Ask for the build again to see what it covers now.', 'stale',
                                 references=[row['id']])
    project._execute('''UPDATE {schema}.build_requests SET state = 'queued', decided_at = now(), decided_by = %s
                        WHERE id = %s''', (Jsonb(_who(actor)), row['id']))
    return _shown(_row(project, row['id']))


def decline(project, request_id, *, actor, reason=''):
    """Decline a request awaiting approval (not-awaiting otherwise); the reason becomes its problem."""
    row = _awaiting(project, request_id)
    project._execute('''UPDATE {schema}.build_requests SET state = 'declined', decided_at = now(), decided_by = %s,
                            finished_at = now(), problem = %s WHERE id = %s''',
                     (Jsonb(_who(actor)), reason or None, row['id']))
    return _shown(_row(project, row['id']))


def cancel(project, request_id, *, actor):
    """Cancel a request: one awaiting approval or queued is cancelled; a running one is asked to stop.

    For a running request cancel_requested is set (the worker's stop function
    reads it) and every queued or running run of its plan is cancelled with
    builds.cancel; the worker records it cancelled when its build ends. Any
    other state is refused (not-cancellable).
    """
    row = _row(project, find(project, request_id))
    if row['state'] in PENDING:
        project._execute('''UPDATE {schema}.build_requests SET state = 'cancelled', finished_at = now(), problem = %s
                            WHERE id = %s''', (f'Cancelled by {actor.get("label") or actor.get("kind")}.', row['id']))
    elif row['state'] == 'running':
        project._execute('UPDATE {schema}.build_requests SET cancel_requested = true WHERE id = %s', (row['id'],))
        if row['plan_id'] is not None:
            active = project._execute('SELECT id FROM {schema}.runs WHERE plan_id = %s AND state = ANY(%s)',
                                      (row['plan_id'], list(builds.ACTIVE))).fetchall()
            for (run_id,) in active:
                try:
                    builds.cancel(project, run_id)
                except store.ProjectError as exc:
                    if exc.code != 'not-active':  # it ended meanwhile
                        raise
    else:
        raise store.ProjectError(f'Build request {row["id"]} is {row["state"]}; only a request awaiting approval, '
                                 'queued or running can be cancelled.', 'not-cancellable')
    return _shown(_row(project, row['id']))


# ------------------------------------------------------------- the worker

def reap_orphans(project, *, worker_pid=None):
    """Mark failed every running request whose owner process is gone (or ran before this boot).

    worker_pid, given by the worker between requests while it holds the
    worker lock, counts a running request of that process as gone too: the
    worker runs one request at a time, so one still running then was left
    unrecorded. Returns the ids marked.
    """
    rows = project._execute("SELECT id, owner_pid, owner_boot FROM {schema}.build_requests "
                            "WHERE state = 'running'").fetchall()
    boot = builds.boot_id()
    gone = [request_id for request_id, pid, owner_boot in rows
            if owner_boot != boot or pid is None or pid == worker_pid or not builds._alive(pid)]
    for request_id in gone:
        project._execute('''UPDATE {schema}.build_requests SET state = 'failed', finished_at = now(), problem = %s
                            WHERE id = %s AND state = 'running' ''', (ORPHAN_PROBLEM, request_id))
    return gone


def take(project):
    """The oldest queued request that may run, marked running by this process: (request, plan), or None.

    Requests are taken in the order they were queued (decided_at). One
    queued more than EXPIRY_SECONDS ago becomes expired; one whose covers,
    computed again, has another SHA-256 becomes failed, naming what changed.
    Each is passed over and the next one looked at.
    """
    while True:
        found = project._execute(f'''SELECT id, now() - decided_at > make_interval(secs => %s)
                                     FROM {{schema}}.build_requests WHERE state = 'queued'
                                     ORDER BY decided_at, requested_at, id LIMIT 1''', (EXPIRY_SECONDS,)).fetchone()
        if found is None:
            return None
        request_id, expired = found
        row = _row(project, request_id)
        if expired:
            project._execute('''UPDATE {schema}.build_requests SET state = 'expired', finished_at = now(), problem = %s
                                WHERE id = %s''',
                             (f'It was approved more than {EXPIRY_SECONDS / 3600:g} h ago and had not started; '
                              'ask for the build again.', request_id))
            continue
        try:
            now, made, why = _current(project, row)
        except Exception as exc:  # not a refusal: this request fails and the worker goes on
            project._execute('''UPDATE {schema}.build_requests SET state = 'failed', finished_at = now(), problem = %s
                                WHERE id = %s''', (f'{type(exc).__name__}: {exc}', request_id))
            continue
        if now is None or covers_sha256(now) != row['covers_sha256']:
            project._execute('''UPDATE {schema}.build_requests SET state = 'failed', finished_at = now(), problem = %s
                                WHERE id = %s''', (_stale_problem(row, now, why, 'not run'), request_id))
            continue
        project._execute('''UPDATE {schema}.build_requests SET state = 'running', started_at = now(),
                                owner_pid = %s, owner_boot = %s WHERE id = %s''',
                         (os.getpid(), builds.boot_id(), request_id))
        return _shown(_row(project, request_id)), made


def _connect(dsn):
    return psycopg.connect(store.connection_info(dsn), autocommit=True)


def started(dsn, schema, request_id, run_id):
    """Record the plan of a running request from its first run (once); return whether it is asked to stop.

    Called while a build runs, with the project closed: uses its own connection.
    """
    with _connect(dsn) as connection:
        connection.execute(_q(schema, '''UPDATE {schema}.build_requests
                                             SET plan_id = (SELECT plan_id FROM {schema}.runs WHERE id = %s)
                                         WHERE id = %s AND plan_id IS NULL'''), (run_id, request_id))
        row = connection.execute(_q(schema, 'SELECT cancel_requested FROM {schema}.build_requests WHERE id = %s'),
                                 (request_id,)).fetchone()
    return bool(row and row[0])


def stop_asked(dsn, schema, request_id):
    """Whether cancelling was asked for the request; its own connection, for the build's stop function."""
    with _connect(dsn) as connection:
        row = connection.execute(_q(schema, 'SELECT cancel_requested FROM {schema}.build_requests WHERE id = %s'),
                                 (request_id,)).fetchone()
    return bool(row and row[0])


def ask_to_stop(dsn, schema, request_id):
    """Set cancel_requested on a running request without opening the project (the service closing)."""
    with _connect(dsn) as connection:
        connection.execute(_q(schema, "UPDATE {schema}.build_requests SET cancel_requested = true "
                                      "WHERE id = %s AND state = 'running'"), (request_id,))


def waiting(dsn, schema):
    """Whether any request is queued or running: the worker's cheap look before it opens the project."""
    with _connect(dsn) as connection:
        return connection.execute(_q(schema, "SELECT EXISTS (SELECT 1 FROM {schema}.build_requests "
                                             "WHERE state IN ('queued', 'running'))")).fetchone()[0]


def finish(project, request_id, *, done=None, problem=None, plan_id=None, steps=None):
    """Record how a running request's build ended; return the request.

    done is what builds.execute returned, or None when it raised; problem is
    then the refusal's message. succeeded when done is ok; cancelled when
    cancel was requested; otherwise failed, with the problem of the step that
    did not succeed (or problem). result is the steps (done's, or steps: those
    that ended before it raised).
    """
    row = _row(project, request_id)
    if done is not None:
        steps, plan_id = done['steps'], done['plan_id']
    if done is not None and done['ok']:
        state, problem = 'succeeded', None
    elif row['cancel_requested']:
        state, problem = 'cancelled', 'It was cancelled while it ran.' + (f' {problem}' if problem else '')
    else:
        state = 'failed'
        if done is not None:
            bad = [item for item in done['steps'] if item['state'] != 'succeeded']
            problem = (f'{bad[-1]["reference"]}' + (f' {bad[-1]["subject"]}' if bad[-1]['subject'] else '')
                       + f' ended {bad[-1]["state"]}: {bad[-1]["problem"]}') if bad else \
                'The build stopped before it was done.'
    project._execute('''UPDATE {schema}.build_requests SET state = %s, finished_at = now(), problem = %s,
                            plan_id = coalesce(%s, plan_id), result = %s WHERE id = %s''',
                     (state, problem, plan_id, Jsonb(list(steps or [])), request_id))
    return _shown(_row(project, request_id))
