"""Serving a trained model: sessions, their processes, their requests and their log.

Owns sections 2 to 4 of docs/plans/training-and-curation/spec-t6.md. A
Supervisor holds the sessions of one project while Tuldok runs: a session is
created awaiting approval (an agent's start) or starting (the owner's), and is
started from a Launch, everything its process needs, which service.py works
out with the project open (the product, the environment's interpreter, the
code snapshot). How a session is run is its backend's: BACKENDS maps the
`backend` of a recipe's `serve` to an object with start(session, launch),
stop(session) and exchange(session, inputs, deadline); "local" (LocalBackend)
is the one built, the project's own entry point run by serve_adapter.py in
its environment. The Supervisor owns everything that does not depend on the
backend: the states, the limit of the machine, the approval's expiry, the idle
stop, the queue of one model's requests, the timings and the files under
<local home>/serving/<session>/.

LocalBackend starts the adapter from a thread that lives as long as the
process (PR_SET_PDEATHSIG follows the thread that forked), in a session of
its own, with two private pipes for the protocol and one pipe for its output,
which another thread writes to output.log (bounded) and keeps the tail of.
Stopping closes the request pipe, sends SIGTERM to the process group, SIGKILL
after STOP_GRACE, and sweeps every process carrying the session's run id
(launcher.stop_strays). Nothing here imports the project's code.
"""
import collections
import dataclasses
import datetime
import errno
import fcntl
import json
import os
import select
import signal
import subprocess
import threading
import time
import uuid

from . import builds, launcher, local, serve_protocol
from .serve_protocol import ServeError

SERVING = 'serving'                 # <local home>/serving/<session>/
ADAPTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serve_adapter.py')
STATES = ('awaiting-approval', 'starting', 'ready', 'failed', 'stopped', 'declined', 'expired')
LIVE = ('starting', 'ready')
OPEN = ('awaiting-approval',) + LIVE
APPROVAL_SECONDS = 3600.0           # how long an agent's start waits for the owner
QUEUE_MOST = 8                      # requests waiting for one served model
STOP_GRACE = 5.0                    # seconds between SIGTERM and SIGKILL
WATCH_SECONDS = 1.0                 # how often a session's thread looks at idleness
LOG_LIMIT = 4 * 1024 * 1024         # bytes of output.log
TAIL_BYTES = 4096                   # bytes of output kept for a failure
REQUEST_LINES = 100_000             # lines of requests.jsonl a session
RECENT = 20                         # request lines in serve_session
LISTED = 50                         # sessions on disk listed by served
DEFAULTS = {'start_seconds': 120.0, 'request_seconds': 60.0}
BACKEND = 'local'


@dataclasses.dataclass(frozen=True)
class Launch:
    """What a session's process needs, worked out with the project open (service.py)."""
    model: str
    serve: dict
    product: str
    product_run: str
    environment: str
    interpreter: str
    code_root: str
    commit: str
    scratch: bool


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _text(moment):
    return None if moment is None else moment.isoformat()


def _who(actor):
    return {key: actor.get(key) for key in ('actor_id', 'kind', 'label')} if actor else None


class Session:
    """One start of one model; its fields are what to_dict answers, the rest is its process's."""

    def __init__(self, model, title, *, actor, scratch, backend, idle_minutes, directory):
        self.id = uuid.uuid4().hex
        self.model, self.title, self.backend = model, title, backend
        self.state, self.reason, self.problem = 'awaiting-approval', None, None
        self.requested_by, self.requested_at = _who(actor), _now()
        self.decided_by = None
        self.expires_at = self.requested_at + datetime.timedelta(seconds=APPROVAL_SECONDS)
        self.started_at = self.ready_at = self.ended_at = self.last_request_at = None
        self.scratch, self.idle_minutes = scratch, idle_minutes
        self.launch = None
        self.pid = None
        self.requests = self.failed_requests = self.unlogged = 0
        self.ready = {}                  # the adapter's ready line
        self.directory = os.path.join(directory, self.id)
        self.slot = threading.Lock()     # one request in the process at a time
        self.waiting = 0
        self.last_activity = time.monotonic()
        self.in_flight = False
        self.number = 0
        self.tail = collections.deque()  # (bytes) of the output's last TAIL_BYTES
        self.tail_size = 0
        self.exited = threading.Event()
        self.stopping = threading.Event()   # set by a stop; a process started after it is stopped at once
        self.runtime_lock = threading.Lock()
        self.runtime = {}                # the backend's own: process, pipes, threads

    def output_tail(self):
        return b''.join(self.tail).decode('utf-8', 'replace')

    def to_dict(self):
        launch = self.launch
        return {'id': self.id, 'model': self.model, 'title': self.title, 'backend': self.backend,
                'state': self.state, 'reason': self.reason, 'problem': self.problem,
                'requested_by': self.requested_by, 'requested_at': _text(self.requested_at),
                'decided_by': self.decided_by,
                'expires_at': _text(self.expires_at) if self.state == 'awaiting-approval' else None,
                'started_at': _text(self.started_at), 'ready_at': _text(self.ready_at),
                'ended_at': _text(self.ended_at), 'last_request_at': _text(self.last_request_at),
                'commit': launch.commit if launch else None, 'scratch': self.scratch,
                'product_run': launch.product_run if launch else None,
                'product': launch.product if launch else None,
                'environment': launch.environment if launch else None,
                'interpreter': launch.interpreter if launch else None,
                'pid': self.pid if self.state in LIVE else None, 'idle_minutes': self.idle_minutes,
                'requests': self.requests, 'failed_requests': self.failed_requests,
                'load_seconds': self.ready.get('load_seconds'), 'python': self.ready.get('python'),
                'numpy': self.ready.get('numpy'), 'output_tail': self.output_tail()}


# ----------------------------------------------------------------- local backend

def _read_line(session, fd, deadline, limit):
    """One line (without its newline) from fd by deadline (monotonic); ServeError timed-out or serve-failed."""
    buffer = session.runtime.setdefault('buffer', bytearray())
    while True:
        cut = buffer.find(b'\n')
        if cut >= 0:
            line = bytes(buffer[:cut])
            del buffer[:cut + 1]
            return line
        if len(buffer) > limit:
            raise ServeError(f'The served process wrote a line longer than {limit} bytes.', 'serve-failed')
        left = deadline - time.monotonic()
        if left <= 0:
            raise ServeError('The served process did not answer in time.', 'timed-out')
        ready, _, _ = select.select([fd], [], [], min(left, 1.0))
        if not ready:
            continue
        try:
            chunk = os.read(fd, 1 << 20)
        except BlockingIOError:
            continue
        except OSError as error:
            raise ServeError(f'The served process could not be read: {error.strerror}.', 'serve-failed') from None
        if not chunk:
            raise ServeError('The served process ended.', 'serve-failed')
        buffer += chunk


def _write_all(fd, data, deadline):
    view = memoryview(data)
    while view:
        left = deadline - time.monotonic()
        if left <= 0:
            raise ServeError('The served process did not take the request in time.', 'timed-out')
        _, ready, _ = select.select([], [fd], [], min(left, 1.0))
        if not ready:
            continue
        try:
            written = os.write(fd, view)
        except BlockingIOError:
            continue
        except OSError as error:
            if error.errno == errno.EPIPE:
                raise ServeError('The served process ended.', 'serve-failed') from None
            raise ServeError(f'The served process could not be written to: {error.strerror}.',
                             'serve-failed') from None
        view = view[written:]


def _close(fd):
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass


class LocalBackend:
    """The project's own serve entry point, run by serve_adapter.py in its environment (spec-t6.md section 2)."""
    name = 'local'

    def start(self, session, launch, on_ready, on_exit):
        """Start the process from a thread of its own; on_ready(ready line or ServeError), on_exit(status)."""
        thread = threading.Thread(target=self._run, args=(session, launch, on_ready, on_exit),
                                  name=f'tuldok-serve-{session.id[:8]}', daemon=True)
        session.runtime['thread'] = thread
        thread.start()

    def _run(self, session, launch, on_ready, on_exit):
        requests_read, requests_write = os.pipe()
        answers_read, answers_write = os.pipe()
        output_read, output_write = os.pipe()
        serve = launch.serve
        argv = [launch.interpreter, '-I', ADAPTER, '--requests', str(requests_read), '--answers', str(answers_write),
                '--code', launch.code_root, '--module', serve['module_file'],
                '--function', serve.get('function', 'predict'), '--product', launch.product]
        if serve.get('load'):
            argv += ['--load', serve['load']]
        env = {key: os.environ[key] for key in builds.PASSED_VARIABLES if key in os.environ}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1', TULDOK_PRODUCT=launch.product,
                   TULDOK_SERVE_MODEL=launch.model, **{launcher.RUN_ID_VARIABLE: 'serve-' + session.id})
        if not serve.get('gpu'):
            env['CUDA_VISIBLE_DEVICES'] = ''
        elif 'CUDA_VISIBLE_DEVICES' in os.environ:
            env['CUDA_VISIBLE_DEVICES'] = os.environ['CUDA_VISIBLE_DEVICES']
        try:
            process = subprocess.Popen(argv, cwd=launch.code_root, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output_write, stderr=output_write,
                                       pass_fds=(requests_read, answers_write), start_new_session=True,
                                       preexec_fn=launcher._child_setup(os.getpid()), close_fds=True)
        except OSError as error:
            for fd in (requests_read, requests_write, answers_read, answers_write, output_read, output_write):
                _close(fd)
            on_ready(ServeError(f'The served process could not be started: {error.strerror or error}.',
                                'serve-failed'))
            session.exited.set()
            on_exit(None)
            return
        for fd in (requests_read, answers_write, output_write):
            _close(fd)
        fcntl.fcntl(requests_write, fcntl.F_SETFL, fcntl.fcntl(requests_write, fcntl.F_GETFL) | os.O_NONBLOCK)
        session.pid = process.pid
        with session.runtime_lock:
            session.runtime.update(process=process, requests=requests_write, answers=answers_read)
            stopping = session.stopping.is_set()
        if stopping:   # stopped while it was being started
            _close(session.runtime.pop('requests', None))
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        logger = threading.Thread(target=self._log, args=(session, output_read),
                                  name=f'tuldok-serve-log-{session.id[:8]}', daemon=True)
        logger.start()
        deadline = time.monotonic() + float(serve.get('start_seconds', DEFAULTS['start_seconds']))
        try:
            line = _read_line(session, answers_read, deadline, serve_protocol.ANSWER_LIMIT)
            ready = serve_protocol.check_ready(line)
        except ServeError as error:
            if error.code == 'timed-out':
                error = ServeError(f'The model did not load within {serve.get("start_seconds", 120)} seconds.',
                                   'timed-out')
            ready = error
        on_ready(ready)
        # This thread started the process, so it stays until the process is gone (spec-t6.md section 2).
        while True:
            try:
                status = process.wait(timeout=WATCH_SECONDS)
                break
            except subprocess.TimeoutExpired:
                on_exit(...)   # a tick: the supervisor looks at idleness
        _close(session.runtime.pop('requests', None))
        logger.join(5)
        _close(answers_read)
        session.exited.set()
        on_exit(status)

    def _log(self, session, fd):
        path = os.path.join(session.directory, 'output.log')
        written = 0
        with open(path, 'ab') as log:
            while True:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                session.tail.append(chunk)
                session.tail_size += len(chunk)
                while session.tail_size - len(session.tail[0]) >= TAIL_BYTES:
                    session.tail_size -= len(session.tail.popleft())
                if written < LOG_LIMIT:
                    part = chunk[:LOG_LIMIT - written]
                    log.write(part)
                    log.flush()
                    written += len(part)
                    if written >= LOG_LIMIT:
                        log.write(b'\n[Tuldok: the output past 4 MiB is not kept.]\n')
                        log.flush()
        _close(fd)
        if session.tail_size > TAIL_BYTES and session.tail:
            joined = b''.join(session.tail)[-TAIL_BYTES:]
            session.tail.clear()
            session.tail.append(joined)
            session.tail_size = len(joined)

    def exchange(self, session, inputs, deadline):
        """Send one request and read its answer (serve_protocol.check_answer), by deadline."""
        session.number += 1
        number = session.number
        requests = session.runtime.get('requests')
        if requests is None:
            raise ServeError('The served process has ended.', 'serve-failed')
        line = json.dumps({'id': number, 'inputs': inputs}, allow_nan=False, separators=(',', ':')).encode() + b'\n'
        _write_all(requests, line, deadline)
        return serve_protocol.check_answer(
            _read_line(session, session.runtime['answers'], deadline, serve_protocol.ANSWER_LIMIT), number)

    def stop(self, session):
        """Close the request pipe, SIGTERM the group, SIGKILL after STOP_GRACE, sweep the run id."""
        with session.runtime_lock:
            session.stopping.set()
            _close(session.runtime.pop('requests', None))
            process = session.runtime.get('process')
        if process is not None:
            if not session.exited.wait(0.5):
                for signum, wait in ((signal.SIGTERM, STOP_GRACE), (signal.SIGKILL, STOP_GRACE)):
                    try:
                        os.killpg(process.pid, signum)
                    except (ProcessLookupError, PermissionError):
                        pass
                    if session.exited.wait(wait):
                        break
            try:
                launcher.stop_strays('serve-' + session.id)
            except Exception:  # a sweep that cannot finish leaves nothing worse than before
                pass
        thread = session.runtime.get('thread')
        if thread is not None and thread is not threading.current_thread():
            thread.join(STOP_GRACE)


BACKENDS = {'local': LocalBackend()}


# --------------------------------------------------------------------- supervisor

class Supervisor:
    """The sessions of one project while Tuldok runs; see the module docstring."""

    def __init__(self, project_id):
        self.project_id = project_id
        self._lock = threading.Lock()
        self._sessions = {}             # id -> Session
        self._closing = False

    # ---------------------------------------------------------------- paths

    def directory(self, create=False):
        path = os.path.join(local.home(self.project_id, create=create), SERVING)
        if create:
            os.makedirs(path, exist_ok=True)
        return path

    def _write(self, session):
        """session.json, written again through a temporary file."""
        os.makedirs(session.directory, exist_ok=True)
        path = os.path.join(session.directory, 'session.json')
        temporary = path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as handle:
            json.dump(session.to_dict(), handle, indent=1)
        os.replace(temporary, path)

    # ---------------------------------------------------------------- reading

    def _expire(self, session):
        if session.state == 'awaiting-approval' and _now() >= session.expires_at:
            session.state, session.reason, session.ended_at = 'expired', 'nobody approved it within an hour', _now()
            self._write(session)

    def get(self, session_id):
        """The session as a dict, from memory or from its file; ServeError not-found."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._expire(session)
                return session.to_dict()
        found = self._on_disk(session_id)
        if found is None:
            raise ServeError(f'There is no serving session {session_id}.', 'not-found')
        return found

    def _on_disk(self, session_id):
        if not (isinstance(session_id, str) and len(session_id) == 32 and all(c in '0123456789abcdef'
                                                                              for c in session_id)):
            return None
        try:
            with open(os.path.join(self.directory(), session_id, 'session.json'), encoding='utf-8') as handle:
                found = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(found, dict):
            return None
        if found.get('state') in OPEN:   # left by a Tuldok that is gone
            found.update(state='stopped', reason='Tuldok stopped', pid=None, expires_at=None)
        return found

    def sessions(self):
        """Every session in memory and the newest LISTED on disk, newest first."""
        with self._lock:
            for session in self._sessions.values():
                self._expire(session)
            held = {session.id: session.to_dict() for session in self._sessions.values()}
        try:
            entries = sorted(os.scandir(self.directory()), key=lambda e: e.stat().st_mtime, reverse=True)
        except OSError:
            entries = []
        for entry in entries[:LISTED]:
            if entry.name not in held:
                found = self._on_disk(entry.name)
                if found is not None:
                    held[entry.name] = found
        return sorted(held.values(), key=lambda s: s.get('requested_at') or '', reverse=True)

    def requests(self, session_id, most=None):
        """The request lines of a session (all, or the newest most)."""
        path = os.path.join(self.directory(), session_id, 'requests.jsonl')
        lines = []
        try:
            with open(path, encoding='utf-8') as handle:
                for text in handle:
                    try:
                        lines.append(json.loads(text))
                    except ValueError:
                        continue
        except OSError:
            return []
        return lines[-most:] if most else lines

    # ---------------------------------------------------------------- starting

    def open_session(self, model, model_title, *, actor, scratch, backend, idle_minutes, most, awaiting):
        """A new session of model, awaiting approval or not; ServeError already-served or limit."""
        with self._lock:
            if self._closing:
                raise ServeError('Tuldok is stopping.', 'unavailable')
            for session in self._sessions.values():
                self._expire(session)
                if session.model == model and session.state in OPEN:
                    raise ServeError(f'{model} is {session.state} already (session {session.id}).',
                                     'already-served')
            if not awaiting:
                self._check_limit(most)
            session = Session(model, model_title, actor=actor, scratch=scratch, backend=backend,
                              idle_minutes=idle_minutes, directory=self.directory(create=True))
            self._sessions[session.id] = session
            if not awaiting:
                session.state, session.decided_by = 'starting', _who(actor)
            self._write(session)
            return session.to_dict()

    def _check_limit(self, most):
        live = [s for s in self._sessions.values() if s.state in LIVE]
        if len(live) >= most:
            raise ServeError(f'This machine serves at most {most} models at once; '
                             + ', '.join(s.model for s in live) + ' are served. Stop one first.', 'limit')

    def awaiting(self, session_id):
        """The model and scratch of a session awaiting approval; ServeError not-found or not-awaiting."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ServeError(f'There is no serving session {session_id} awaiting approval.', 'not-found')
            self._expire(session)
            if session.state != 'awaiting-approval':
                raise ServeError(f'Session {session_id} is {session.state}, not awaiting approval.', 'not-awaiting')
            return session.model, session.scratch

    def approve(self, session_id, actor, most):
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.state != 'awaiting-approval':
                raise ServeError(f'Session {session_id} is not awaiting approval.', 'not-awaiting')
            self._check_limit(most)
            session.state, session.decided_by = 'starting', _who(actor)
            self._write(session)

    def fail_start(self, session_id, problem):
        """A starting session whose launch could not be worked out: failed, with the problem."""
        with self._lock:
            session = self._sessions[session_id]
            session.state, session.problem, session.reason, session.ended_at = 'failed', problem, problem, _now()
            self._write(session)
            return session.to_dict()

    def launch(self, session_id, launch):
        """Start the process of a starting session; returns the session as it is then (starting)."""
        with self._lock:
            session = self._sessions[session_id]
            if session.state != 'starting':   # stopped while its launch was worked out
                return session.to_dict()
            session.launch, session.started_at = launch, _now()
            backend = BACKENDS[session.backend]
            self._write(session)
        backend.start(session, launch, lambda ready: self._on_ready(session, ready),
                      lambda status: self._on_exit(session, status))
        return session.to_dict()

    def _on_ready(self, session, ready):
        with self._lock:
            if session.state != 'starting':
                return
            if isinstance(ready, ServeError) or not ready.get('ready'):
                problem = str(ready) if isinstance(ready, ServeError) else ('The model did not load: '
                                                                             + str(ready.get('error') or '?'))
                session.state, session.problem, session.reason, session.ended_at = 'failed', problem, problem, _now()
                self._write(session)
                stop = True
            else:
                session.ready = ready
                session.state, session.ready_at = 'ready', _now()
                session.last_activity = time.monotonic()
                self._write(session)
                stop = False
        if stop:
            threading.Thread(target=BACKENDS[session.backend].stop, args=(session,), daemon=True).start()

    def _on_exit(self, session, status):
        if status is ...:   # a tick of the process's thread: is it idle?
            with self._lock:
                idle = (session.state == 'ready' and not session.in_flight and session.waiting == 0
                        and time.monotonic() - session.last_activity >= 60.0 * session.idle_minutes)
            if idle:
                threading.Thread(target=self.stop, args=(session.id, None, 'idle'), daemon=True).start()
            return
        with self._lock:
            if session.state in LIVE:
                word = 'signal ' + str(-status) if isinstance(status, int) and status < 0 else f'exit status {status}'
                problem = f'The served process ended ({word}).'
                session.state, session.problem, session.reason, session.ended_at = 'failed', problem, problem, _now()
            self._write(session)

    # ---------------------------------------------------------------- stopping

    def stop(self, session_id, actor, reason='asked'):
        """Stop a session: decline one awaiting approval, stop one starting or ready; the session after."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise ServeError(f'There is no serving session {session_id} that runs.', 'not-found')
            self._expire(session)
            if session.state == 'awaiting-approval':
                session.state, session.decided_by, session.ended_at = 'declined', _who(actor), _now()
                session.reason = 'declined by ' + ((actor or {}).get('label') or (actor or {}).get('kind') or '?')
                self._write(session)
                return session.to_dict()
            if session.state not in LIVE:
                raise ServeError(f'Session {session_id} is {session.state}; there is nothing to stop.', 'not-running')
            session.state, session.reason, session.ended_at = 'stopped', reason, _now()
            self._write(session)
        if session.launch is not None:
            BACKENDS[session.backend].stop(session)
        with self._lock:
            self._write(session)
            return session.to_dict()

    def close(self):
        """Stop every session (reason closing); called when the service closes."""
        with self._lock:
            self._closing = True
            live = [s for s in self._sessions.values() if s.state in OPEN]
        for session in live:
            try:
                self.stop(session.id, None, 'closing')
            except ServeError:
                pass
        for session in list(self._sessions.values()):   # a failed one may still be being stopped
            if session.launch is not None and not session.exited.is_set():
                BACKENDS[session.backend].stop(session)

    # ---------------------------------------------------------------- requests

    def predict(self, model, inputs, received, size=None):
        """Pass inputs to the served model; {model, session, outputs, timing}.

        received is time.perf_counter() when Tuldok had read the request; size its bytes (computed when None).
        """
        if size is None:
            size = len(json.dumps(inputs, separators=(',', ':')))
        with self._lock:
            found = [s for s in self._sessions.values() if s.model == model and s.state in OPEN]
            if not found:
                raise ServeError(f'{model} is not being served.', 'not-served')
            session = found[0]
            if session.state != 'ready':
                raise ServeError(f'{model} is {session.state}, not ready yet.', 'not-ready')
            if session.waiting >= QUEUE_MOST:
                raise ServeError(f'{QUEUE_MOST} requests are waiting for {model} already; try again.', 'busy')
            session.waiting += 1
        try:
            session.slot.acquire()
        finally:
            with self._lock:
                session.waiting -= 1
        try:
            queued = time.perf_counter()
            with self._lock:
                if session.state != 'ready':
                    raise ServeError(f'{model} stopped while the request waited.', 'not-served')
                session.in_flight = True
            seconds = float(session.launch.serve.get('request_seconds', DEFAULTS['request_seconds']))
            failure = None
            answer = None
            try:
                answer = BACKENDS[session.backend].exchange(session, inputs, time.monotonic() + seconds)
            except ServeError as error:
                failure = error
            done = time.perf_counter()
            timing = {'queue_ms': 1000 * (queued - received),
                      'model_ms': 1000 * answer['model_seconds'] if answer else None,
                      'total_ms': 1000 * (done - received)}
            ok = failure is None and answer['ok']
            self._log(session, ok, timing, size, answer, failure)
            if failure is not None:
                self._broken(session, failure, seconds)
                raise failure
            if not answer['ok']:
                raise ServeError(answer['error'], 'predict-failed')
            return {'model': model, 'session': session.id, 'outputs': answer['outputs'], 'timing': timing}
        finally:
            with self._lock:
                session.in_flight = False
                session.last_activity = time.monotonic()
            session.slot.release()

    def _broken(self, session, failure, seconds):
        problem = (f'A request took more than {seconds:g} seconds; the process was stopped.'
                   if failure.code == 'timed-out' else str(failure))
        with self._lock:
            if session.state not in LIVE:
                return
            session.state, session.problem, session.reason, session.ended_at = 'failed', problem, problem, _now()
            self._write(session)
        BACKENDS[session.backend].stop(session)

    def _log(self, session, ok, timing, size, answer, failure):
        with self._lock:
            session.requests += 1
            session.failed_requests += 0 if ok else 1
            session.last_request_at = _now()
            if session.requests > REQUEST_LINES:
                session.unlogged += 1
                return
            line = {'n': session.requests, 'at': time.time(), 'ok': ok,
                    'status': 200 if ok else serve_protocol.STATUS.get(
                        failure.code if failure else 'predict-failed', 500),
                    **timing,
                    'bytes_in': size,
                    'bytes_out': len(json.dumps(answer.get('outputs'), separators=(',', ':')))
                    if answer and answer.get('ok') else 0}
            if not ok:
                line['error'] = (str(failure) if failure else answer.get('error', ''))[:400]
            with open(os.path.join(session.directory, 'requests.jsonl'), 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(line, separators=(',', ':')) + '\n')
            self._write(session)
