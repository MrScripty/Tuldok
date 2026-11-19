"""Run one build command and stay with it until every process it started is gone.

Owns section 3 of docs/plans/definition-first-projects/spec-m6.md. run() does
not start the command itself: it writes the run's description to a private
file in the run directory and starts a custodian, `python -m
tuldok_project.launcher <file>`, then waits for it and reads
<directory>/outcome.json. The custodian is a child subreaper, so every child
it ever has belongs to the run and it reaps them all; this keeps orphans,
zombies and waitpid() out of the calling process, which may have children and
threads of its own. The custodian starts the command in a new session with
PR_SET_PDEATHSIG set to SIGKILL and TULDOK_RUN_ID=<run id> in its environment,
watches the wall-time limit, the disk limit and the run directory's cancel
file, stops the run when one of them (or SIGINT or SIGTERM to the custodian)
asks for it, and then sweeps: every process of this user whose environment
carries the run id, every process still in the command's process group or
session, and every child of the custodian is killed and reaped. The custodian
itself has PR_SET_PDEATHSIG set to SIGTERM, so a run whose caller dies is
stopped and swept. strays() and stop_strays() do the sweep alone for a run
whose custodian is gone. progress() reads the bounded tail of a run's two logs
and its latest tuldok_progress_v1 line. Linux only.
"""
import ctypes
from dataclasses import asdict, dataclass, fields
import json
import math
import os
import re
import select
import signal
import stat
import subprocess
import sys
import threading
import time

WATCH_INTERVAL = 0.5     # seconds between checks of exit, wall time and cancel
DISK_INTERVAL = 5.0      # seconds between measurements of the run directory
STOP_GRACE = 10.0        # seconds between SIGTERM and SIGKILL when a run is stopped
SWEEP_LIMIT = 10.0       # seconds the final sweep may take before the run is unknown
SWEEP_PAUSE = 0.05       # seconds between rounds of a sweep or a stop
LOG_TAIL = 8192          # bytes read from the end of each log by progress()
EVENT_LINE_LIMIT = 4096  # longer stdout lines are never progress events

RUN_ID_VARIABLE = 'TULDOK_RUN_ID'
CANCEL_FILE = 'cancel'
DESCRIPTION_FILE = 'custodian.json'
OUTCOME_FILE = 'outcome.json'
LOGS = ('stdout', 'stderr')
STATES = ('succeeded', 'failed', 'timed-out', 'over-disk', 'cancelled', 'unknown')

PR_SET_PDEATHSIG = 1
PR_SET_CHILD_SUBREAPER = 36

_TIMING = ('WATCH_INTERVAL', 'DISK_INTERVAL', 'STOP_GRACE', 'SWEEP_LIMIT', 'SWEEP_PAUSE')
_STOP_SIGNALS = {signal.SIGINT, signal.SIGTERM}
_DESCRIPTION_LIMIT = 16 * 1024 * 1024
_OUTCOME_LIMIT = 64 * 1024
_RUN_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
_CONTROL = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f]')


@dataclass(frozen=True)
class Outcome:
    """How a run ended. exit_status is the command's return code (negative for
    a signal), or None when it is not known; strays counts the processes the
    final sweep had to kill; bytes is the run directory's size; problem says
    why a run is unknown."""
    state: str
    exit_status: int | None
    seconds: float
    strays: int
    bytes: int
    problem: str | None = None


# --- prctl ------------------------------------------------------------------

_libc = None


def _prctl(option, argument):
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(None, use_errno=True)
        _libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                                ctypes.c_ulong, ctypes.c_ulong]
        _libc.prctl.restype = ctypes.c_int
    if _libc.prctl(option, argument, 0, 0, 0) != 0:
        number = ctypes.get_errno()
        raise OSError(number, f'prctl({option}) failed: {os.strerror(number)}')


def _child_setup(parent):
    """Runs in the command between fork and exec: die with the custodian."""
    def setup():
        _prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
        if os.getppid() != parent:  # the custodian died before prctl took effect
            os.kill(os.getpid(), signal.SIGKILL)
    return setup


# --- /proc --------------------------------------------------------------------

def _stat(pid):
    """(state, ppid, pgrp, session) of a process, or None when it is gone."""
    try:
        with open(f'/proc/{pid}/stat', 'rb') as file:
            data = file.read()
        fields_ = data[data.rindex(b')') + 2:].split()
        return fields_[0].decode('ascii'), int(fields_[1]), int(fields_[2]), int(fields_[3])
    except (OSError, ValueError, IndexError):
        return None


def _carries(pid, needle, uid):
    """Whether a live process of this user has exactly needle among its environment entries."""
    try:
        if os.stat(f'/proc/{pid}').st_uid != uid:
            return False
        with open(f'/proc/{pid}/environ', 'rb') as file:
            return needle in file.read().split(b'\0')
    except OSError:  # not ours, or gone between listing and reading
        return False


def _pids():
    try:
        names = os.listdir('/proc')
    except OSError:
        return []
    return [int(name) for name in names if name.isdigit()]


def _check_run_id(run_id):
    if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
        raise ValueError('A run id is 1 to 128 letters, digits, ".", "_" or "-", starting with a letter or digit.')


class _Sweeper:
    """Finds, signals and (in the custodian) reaps the processes of one run.

    A process belongs to the run when its environment carries the run id. In
    the custodian (leader given) it also belongs when it is in the leader's
    process group or session, which is safe because the leader is held
    unreaped until the sweep is over so those ids cannot be reused, and when
    it is a child of the custodian, since the custodian has no other children.
    """

    def __init__(self, run_id, leader=None):
        self.needle = f'{RUN_ID_VARIABLE}={run_id}'.encode()
        self.custodian = leader is not None
        self.leader = leader
        self.me = os.getpid()
        self.uid = os.getuid()

    def _member(self, pid, info):
        if self.custodian and (info[1] == self.me or (
                self.leader is not None and self.leader in (info[2], info[3]))):
            return True
        return _carries(pid, self.needle, self.uid)

    def scan(self, *, children_only=False):
        """Live members other than the leader; in the custodian, zombie children are reaped on the way."""
        alive = []
        for pid in _pids():
            if pid in (self.me, self.leader):
                continue
            info = _stat(pid)
            if info is None or (children_only and info[1] != self.me):
                continue
            if info[0] in 'ZX':
                if self.custodian and info[1] == self.me:
                    _reap(pid)
                continue
            if self._member(pid, info):
                alive.append(pid)
        return alive

    def signal(self, pid, signum):
        """Signal pid through a pidfd after checking, on that pidfd, that it is still a member."""
        try:
            descriptor = os.pidfd_open(pid)
        except (ProcessLookupError, PermissionError):
            return False
        try:
            info = _stat(pid)
            if info is None or info[0] in 'ZX' or not self._member(pid, info):
                return False
            signal.pidfd_send_signal(descriptor, signum)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        finally:
            os.close(descriptor)

    def sweep(self, limit, *, children_only=False):
        """Kill members until none is alive or limit seconds pass: (killed pids, survivors)."""
        deadline = time.monotonic() + limit
        killed = set()
        while True:
            alive = self.scan(children_only=children_only)
            if not alive or time.monotonic() >= deadline:
                return killed, alive
            for pid in alive:
                if self.signal(pid, signal.SIGKILL):
                    killed.add(pid)
            time.sleep(SWEEP_PAUSE)


def _reap(pid):
    try:
        os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        pass


def strays(run_id):
    """Pids of live processes of this user whose environment carries TULDOK_RUN_ID=<run_id>."""
    _check_run_id(run_id)
    return sorted(_Sweeper(run_id).scan())


def stop_strays(run_id):
    """Kill every stray of a run whose custodian is gone, for up to SWEEP_LIMIT seconds.

    Returns {'killed': number of processes signalled, 'remaining': pids still alive}.
    Never reaps: a stray that is the caller's own child is left for the caller to wait on.
    """
    _check_run_id(run_id)
    killed, remaining = _Sweeper(run_id).sweep(SWEEP_LIMIT)
    return {'killed': len(killed), 'remaining': sorted(remaining)}


# --- files --------------------------------------------------------------------

def _directory_size(path):
    """Total size of the regular files under path, not following links; tolerant of churn."""
    total = 0
    pending = [path]
    while pending:
        try:
            entries = os.scandir(pending.pop())
        except OSError:
            continue
        with entries:
            while True:
                try:
                    entry = next(entries)
                except (StopIteration, OSError):
                    break
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    return total


def _unlink(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _write_new(path, data, mode):
    """Write a new file without following links; it must not exist."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view):]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path, limit):
    """A JSON value from a regular file of at most limit bytes, not following links."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode) or status.st_size > limit:
            raise ValueError(f'{path} is not a regular file of at most {limit} bytes.')
        chunks = []
        while chunk := os.read(descriptor, limit + 1 - sum(map(len, chunks))):
            chunks.append(chunk)
            if sum(map(len, chunks)) > limit:
                raise ValueError(f'{path} is over {limit} bytes.')
    finally:
        os.close(descriptor)
    return json.loads(b''.join(chunks))


def _check_arguments(argv, env, run_id, directory, limits):
    if type(argv) not in (list, tuple) or not argv or any(type(part) is not str for part in argv):
        raise ValueError('argv must be a non-empty list of strings.')
    if not isinstance(env, dict) or any(type(key) is not str or type(value) is not str
                                        or not key or '=' in key for key, value in env.items()):
        raise ValueError('env must map variable names to strings.')
    _check_run_id(run_id)
    if not os.path.isdir(directory):
        raise ValueError(f'The run directory {directory} does not exist.')
    if not isinstance(limits, dict) or set(limits) != {'wall_seconds', 'disk_bytes'}:
        raise ValueError("limits must be {'wall_seconds': number, 'disk_bytes': integer}.")
    wall, disk = limits['wall_seconds'], limits['disk_bytes']
    if type(wall) not in (int, float) or not math.isfinite(wall) or wall <= 0:
        raise ValueError('wall_seconds must be a positive number.')
    if type(disk) is not int or disk < 0:
        raise ValueError('disk_bytes must be a non-negative integer.')


# --- the caller's side ----------------------------------------------------------

def run(argv, *, cwd, env, run_id, directory, limits, on_tick=None):
    """Run argv under a custodian until it and every process it started are gone.

    env is the command's whole environment; TULDOK_RUN_ID is added. Standard
    output and error are appended to <directory>/stdout.log and stderr.log.
    on_tick(elapsed_seconds) is called about every WATCH_INTERVAL. Called from
    the main thread, SIGINT and SIGTERM received by this process are forwarded
    to the custodian, which cancels the run, and the previous handlers are
    restored before returning. Called from another thread, nothing is
    installed: those signals keep their existing handlers, and the custodian
    still stops the run if this process dies. An exception from on_tick stops
    the run, waits for the custodian to sweep it, and is then raised. Problems
    the custodian meets before the command runs (prctl refused, the program
    not found) are raised here; a custodian that ends without an outcome gives
    'unknown' after stop_strays(run_id).
    """
    _check_arguments(argv, env, run_id, directory, limits)
    directory = os.path.abspath(directory)
    description_path = os.path.join(directory, DESCRIPTION_FILE)
    outcome_path = os.path.join(directory, OUTCOME_FILE)
    _unlink(description_path)
    _unlink(outcome_path)
    _write_description(description_path, argv, cwd, env, run_id, directory, limits)
    started = time.monotonic()
    target = {'pid': None, 'pending': []}
    try:
        previous = _install_forwarding(target)
        try:
            custodian = _start_custodian(description_path)
            target['pid'] = custodian.pid
            for signum in target['pending']:
                os.kill(custodian.pid, signum)
            try:
                _wait(custodian, started, on_tick)
            except BaseException:
                _abandon(custodian, run_id)
                raise
        finally:
            _restore_handlers(previous)
    finally:
        _unlink(description_path)
    return _read_outcome(outcome_path, custodian.returncode, run_id, directory, started)


def _write_description(path, argv, cwd, env, run_id, directory, limits):
    description = {
        'argv': list(argv), 'cwd': os.path.abspath(cwd), 'env': dict(env), 'run_id': run_id,
        'directory': os.path.abspath(directory), 'limits': dict(limits), 'parent': os.getpid(),
        'timing': {name: globals()[name] for name in _TIMING}}
    _write_new(path, json.dumps(description).encode(), 0o600)


def _start_custodian(description_path):
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {'PYTHONPATH': package_parent, 'PYTHONDONTWRITEBYTECODE': '1'}
    # Blocked here, SIGINT and SIGTERM stay blocked in the custodian until its
    # handlers are in place, so a forwarded signal is never lost at startup.
    before = signal.pthread_sigmask(signal.SIG_BLOCK, _STOP_SIGNALS)
    try:
        return subprocess.Popen(
            [sys.executable, '-P', '-s', '-m', 'tuldok_project.launcher', description_path],
            cwd='/', env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            start_new_session=True, close_fds=True)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, before)


def _install_forwarding(target):
    """Forward SIGINT and SIGTERM to the custodian while a run is in progress; main thread only."""
    if threading.current_thread() is not threading.main_thread():
        return {}

    def forward(signum, frame):
        if target['pid'] is None:
            target['pending'].append(signum)
        else:
            try:
                os.kill(target['pid'], signum)
            except ProcessLookupError:
                pass
    previous = {}
    try:
        for signum in sorted(_STOP_SIGNALS):
            before = signal.getsignal(signum)
            if before is None:  # installed outside Python; cannot be restored, so left alone
                continue
            signal.signal(signum, forward)
            previous[signum] = before
    except BaseException:
        _restore_handlers(previous)
        raise
    return previous


def _restore_handlers(previous):
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _wait(custodian, started, on_tick):
    while True:
        try:
            custodian.wait(timeout=WATCH_INTERVAL)
            return
        except subprocess.TimeoutExpired:
            pass
        if on_tick is not None:
            on_tick(time.monotonic() - started)


def _abandon(custodian, run_id):
    """Ask the custodian to stop the run and wait for its sweep; kill it if it does not finish."""
    try:
        custodian.send_signal(signal.SIGTERM)
        custodian.wait(timeout=STOP_GRACE + 3 * SWEEP_LIMIT + 5)
    except subprocess.TimeoutExpired:
        custodian.kill()
        custodian.wait()
        stop_strays(run_id)


_ERRORS = {'ValueError': ValueError, 'SubprocessError': subprocess.SubprocessError}


def _read_outcome(path, custodian_status, run_id, directory, started):
    try:
        record = _read_json(path, _OUTCOME_LIMIT)
    except (OSError, ValueError):
        record = None
    if type(record) is dict and set(record) == {'error'} and type(record['error']) is dict:
        error = record['error']
        message = str(error.get('message'))
        if type(error.get('errno')) is int:
            raise OSError(error['errno'], message)
        raise _ERRORS.get(error.get('type'), RuntimeError)(message)
    outcome = _outcome_from(record)
    if outcome is not None:
        return outcome
    result = stop_strays(run_id)
    problem = f'The custodian ended without an outcome (exit status {custodian_status}).'
    if result['remaining']:
        problem += f' Processes of the run still alive: {result["remaining"]}.'
    return Outcome('unknown', None, round(time.monotonic() - started, 3), result['killed'],
                   _directory_size(directory), problem)


def _outcome_from(record):
    names = {field.name for field in fields(Outcome)}
    if type(record) is not dict or set(record) != names or record['state'] not in STATES:
        return None
    if not (record['exit_status'] is None or type(record['exit_status']) is int) \
            or type(record['seconds']) not in (int, float) or type(record['strays']) is not int \
            or type(record['bytes']) is not int \
            or not (record['problem'] is None or type(record['problem']) is str):
        return None
    return Outcome(**record)


# --- the custodian ------------------------------------------------------------

def _custodian_main(arguments):
    """Entry point of `python -m tuldok_project.launcher <description file>`."""
    requests = []
    for signum in _STOP_SIGNALS:
        signal.signal(signum, lambda number, frame: requests.append(number))
    signal.pthread_sigmask(signal.SIG_UNBLOCK, _STOP_SIGNALS)
    if len(arguments) != 1:
        print('usage: python -m tuldok_project.launcher <description file>', file=sys.stderr)
        return 2
    try:
        description = _read_json(arguments[0], _DESCRIPTION_LIMIT)
        directory = description['directory']
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'custodian: cannot read {arguments[0]}: {error}', file=sys.stderr)
        return 2
    finally:
        _unlink_quietly(arguments[0])  # it may hold secrets from the environment
    try:
        _prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
        if os.getppid() != description['parent']:  # the caller died before prctl took effect
            requests.append(signal.SIGTERM)
        for name, value in description['timing'].items():
            if name in _TIMING and type(value) in (int, float) and value > 0:
                globals()[name] = value
        _prctl(PR_SET_CHILD_SUBREAPER, 1)
        _check_arguments(description['argv'], description['env'], description['run_id'],
                         directory, description['limits'])
        env = dict(description['env'])
        env[RUN_ID_VARIABLE] = description['run_id']
        record = asdict(_supervise(description['argv'], description['cwd'], env, description['run_id'],
                                   directory, description['limits'], requests))
    except Exception as error:
        record = {'error': {'type': type(error).__name__, 'message': str(error),
                            'errno': error.errno if isinstance(error, OSError) else None}}
    temporary = os.path.join(directory, f'.{OUTCOME_FILE}.{os.getpid()}')
    try:
        _write_new(temporary, json.dumps(record).encode(), 0o644)
        os.replace(temporary, os.path.join(directory, OUTCOME_FILE))
    except OSError as error:
        print(f'custodian: cannot write the outcome: {error}', file=sys.stderr)
        _unlink_quietly(temporary)
        return 3
    return 0


def _unlink_quietly(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _open_log(directory, name):
    return os.open(os.path.join(directory, f'{name}.log'),
                   os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)


def _supervise(argv, cwd, env, run_id, directory, limits, requests):
    """Start the command, watch it, stop it if asked, sweep, and return its Outcome."""
    started = time.monotonic()
    stdout = _open_log(directory, 'stdout')
    try:
        stderr = _open_log(directory, 'stderr')
        try:
            child = subprocess.Popen(
                list(argv), cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stdout,
                stderr=stderr, start_new_session=True, close_fds=True,
                preexec_fn=_child_setup(os.getpid()))
        finally:
            os.close(stderr)
    finally:
        os.close(stdout)
    sweeper = _Sweeper(run_id, child.pid)
    exited = select.poll()
    pidfd = os.pidfd_open(child.pid)
    exited.register(pidfd, select.POLLIN)
    try:
        try:
            reason = _watch(exited, sweeper, started, directory, limits, requests)
        except BaseException:
            _stop(exited, sweeper)
            _finish(child, sweeper)
            raise
        leader_gone = True
        if reason is not None:
            leader_gone = _stop(exited, sweeper)
        if leader_gone:
            killed, survivors, status = _finish(child, sweeper)
        else:
            killed, survivors, status = set(), [child.pid], None
    finally:
        os.close(pidfd)
    size = _directory_size(directory)
    problem = None
    if status is None:
        state, problem = 'unknown', 'The command could not be stopped.'
    elif survivors:
        state, problem = 'unknown', f'Processes of the run could not be stopped: {sorted(survivors)}.'
    elif reason is not None:
        state = reason
    elif status != 0:
        state = 'failed'
    elif size > limits['disk_bytes']:
        state = 'over-disk'  # finished between two measurements but over the limit
    else:
        state = 'succeeded'
    return Outcome(state, status, round(time.monotonic() - started, 3), len(killed), size, problem)


def _leader_exited(exited, timeout=0.0):
    return bool(exited.poll(int(timeout * 1000)))


def _watch(exited, sweeper, started, directory, limits, requests):
    """Wait for the leader to exit or for a reason to stop it; return that reason or None."""
    cancel_path = os.path.join(directory, CANCEL_FILE)
    next_disk = started + DISK_INTERVAL
    while not _leader_exited(exited):
        now = time.monotonic()
        if requests or os.path.lexists(cancel_path):
            return 'cancelled'
        if now - started > limits['wall_seconds']:
            return 'timed-out'
        if now >= next_disk:
            next_disk = now + DISK_INTERVAL
            if _directory_size(directory) > limits['disk_bytes']:
                return 'over-disk'
        sweeper.scan(children_only=True)  # reap adopted orphans as they exit
        _leader_exited(exited, WATCH_INTERVAL)
    return None


def _signal_run(sweeper, signum):
    try:
        os.killpg(sweeper.leader, signum)
    except (ProcessLookupError, PermissionError):
        pass
    for pid in sweeper.scan():
        sweeper.signal(pid, signum)


def _stop(exited, sweeper):
    """SIGTERM to the run, STOP_GRACE seconds, then SIGKILL; whether the leader has exited."""
    _signal_run(sweeper, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE
    while time.monotonic() < deadline:
        if _leader_exited(exited) and not sweeper.scan():
            return True
        time.sleep(SWEEP_PAUSE)
    _signal_run(sweeper, signal.SIGKILL)
    return _leader_exited(exited, SWEEP_LIMIT)


def _finish(child, sweeper):
    """Sweep the exited run, reap the leader, then reap every other child until none is left.

    Returns (killed pids, survivors, exit status).
    """
    deadline = time.monotonic() + SWEEP_LIMIT
    killed, survivors = sweeper.sweep(SWEEP_LIMIT)
    try:
        status = child.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        return killed, survivors, None
    sweeper.leader = None  # reaped: its ids may now be reused, so they no longer identify the run
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return killed, survivors, status
        if pid:
            continue
        alive = sweeper.scan(children_only=True)
        if time.monotonic() >= deadline:
            return killed, sorted(set(survivors) | set(alive)), status
        for pid in alive:
            if sweeper.signal(pid, signal.SIGKILL):
                killed.add(pid)
        time.sleep(SWEEP_PAUSE)


# --- progress -----------------------------------------------------------------

def _decode_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def refuse(constant):
        raise ValueError('non-finite number')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=refuse)


def _event(tail, starts_mid_file):
    """The last complete, valid tuldok_progress_v1 line in tail, or None."""
    lines = tail.splitlines(keepends=True)
    if starts_mid_file and lines:
        lines = lines[1:]  # the first line was cut by the tail and may be any suffix
    for line in reversed(lines):
        if len(line) > EVENT_LINE_LIMIT or not line.endswith(b'\n'):
            continue
        try:
            value = _decode_json(line)
            if type(value) is not dict or set(value) != {'format', 'stage', 'completed', 'total', 'metrics'}:
                continue
            if value['format'] != 'tuldok_progress_v1' or type(value['stage']) is not str \
                    or not _NAME.fullmatch(value['stage']):
                continue
            if not (type(value['completed']) is int and type(value['total']) is int
                    and 0 <= value['completed'] <= value['total'] <= 1000000):
                continue
            metrics = value['metrics']
            if type(metrics) is not dict or len(metrics) > 8 or any(
                    not _NAME.fullmatch(name) or type(number) not in (int, float)
                    or not math.isfinite(number) for name, number in metrics.items()):
                continue
            return value
        except (ValueError, TypeError, OverflowError, RecursionError):
            continue
    return None


def _tail(directory_fd, name):
    """(last LOG_TAIL bytes, total size) of a regular log file, or (b'', None)."""
    try:
        descriptor = os.open(f'{name}.log', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=directory_fd)
    except OSError:  # missing, a symbolic link, or unreadable
        return b'', None
    try:
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            return b'', None
        start = max(0, status.st_size - LOG_TAIL)
        return os.pread(descriptor, LOG_TAIL, start), status.st_size
    finally:
        os.close(descriptor)


def progress(directory):
    """Log tails and the latest progress event of a run directory.

    Returns {'stdout', 'stderr': text of at most the last LOG_TAIL bytes,
    'stdout_bytes', 'stderr_bytes': total sizes (None when the log is absent
    or not a regular file), 'event': the latest valid progress event or None}.
    Neither the directory nor the logs are followed when they are links.
    """
    result = {'event': None}
    for name in LOGS:
        result[name], result[f'{name}_bytes'] = '', None
    try:
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return result
    try:
        for name in LOGS:
            raw, size = _tail(directory_fd, name)
            result[name] = _CONTROL.sub('', raw.decode('utf-8', errors='replace'))
            result[f'{name}_bytes'] = size
            if name == 'stdout' and size is not None:
                result['event'] = _event(raw, size > len(raw))
    finally:
        os.close(directory_fd)
    return result


if __name__ == '__main__':
    sys.exit(_custodian_main(sys.argv[1:]))
