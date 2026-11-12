"""Run one build command and stay with it until every process it started is gone.

Owns section 3 of docs/plans/definition-first-projects/spec-m6.md. run() starts
the command in a new session with PR_SET_PDEATHSIG set to SIGKILL and
TULDOK_RUN_ID=<run id> in its environment, watches the wall-time limit, the
disk limit and the run directory's cancel file, stops the process group when
one of them (or SIGINT or SIGTERM to this process) asks for it, and then
sweeps: every process of this user whose environment carries the run id, or
that is still in the command's process group or session, is killed and reaped
before run() returns. While a run is in progress this process is a child
subreaper, so descendants orphaned by the run are reparented here and reaped.
strays() and stop_strays() do the sweep alone for a run whose launcher is gone.
progress() reads the bounded tail of a run's two logs and its latest
tuldok_progress_v1 line. Linux only.
"""
import ctypes
from dataclasses import dataclass
import json
import math
import os
import re
import select
import signal
import stat
import subprocess
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
LOGS = ('stdout', 'stderr')
STATES = ('succeeded', 'failed', 'timed-out', 'over-disk', 'cancelled', 'unknown')

PR_SET_PDEATHSIG = 1
PR_SET_CHILD_SUBREAPER = 36
PR_GET_CHILD_SUBREAPER = 37

_RUN_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
_CONTROL = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f]')


@dataclass(frozen=True)
class Outcome:
    """How a run ended. exit_status is the Popen return code (negative for a
    signal), or None when the command could not be reaped; strays counts the
    processes the final sweep had to kill; bytes is the run directory's size."""
    state: str
    exit_status: int | None
    seconds: float
    strays: int
    bytes: int


# --- prctl ------------------------------------------------------------------

_libc = None
_subreaper_lock = threading.Lock()
_subreaper_users = 0
_subreaper_before = 0


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


def _subreaper_value():
    value = ctypes.c_int(0)
    _prctl(PR_GET_CHILD_SUBREAPER, ctypes.addressof(value))
    return value.value


def _acquire_subreaper():
    """Make this process a child subreaper; nested and concurrent runs share it."""
    global _subreaper_users, _subreaper_before
    with _subreaper_lock:
        if _subreaper_users == 0:
            _subreaper_before = _subreaper_value()
            _prctl(PR_SET_CHILD_SUBREAPER, 1)
        _subreaper_users += 1


def _release_subreaper():
    global _subreaper_users
    with _subreaper_lock:
        _subreaper_users -= 1
        if _subreaper_users == 0 and not _subreaper_before:
            _prctl(PR_SET_CHILD_SUBREAPER, 0)


def _child_setup(parent):
    """Runs in the child between fork and exec: die with the launcher."""
    def setup():
        _prctl(PR_SET_PDEATHSIG, signal.SIGKILL)
        if os.getppid() != parent:  # the launcher died before prctl took effect
            os.kill(os.getpid(), signal.SIGKILL)
    return setup


# --- /proc --------------------------------------------------------------------

def _stat(pid):
    """(state, ppid, pgrp, session) of a process, or None when it is gone."""
    try:
        with open(f'/proc/{pid}/stat', 'rb') as file:
            data = file.read()
        fields = data[data.rindex(b')') + 2:].split()
        return fields[0].decode('ascii'), int(fields[1]), int(fields[2]), int(fields[3])
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


def _needle(run_id):
    return f'{RUN_ID_VARIABLE}={run_id}'.encode()


def _check_run_id(run_id):
    if type(run_id) is not str or not _RUN_ID.fullmatch(run_id):
        raise ValueError('A run id is 1 to 128 letters, digits, ".", "_" or "-", starting with a letter or digit.')


class _Sweeper:
    """Finds, signals and reaps the processes of one run.

    A process belongs to the run when its environment carries the run id or,
    while the command's leader is held unreaped (so its id cannot be reused),
    when it is still in the leader's process group or session.
    """

    def __init__(self, run_id, leader=None):
        self.needle = _needle(run_id)
        self.leader = leader
        self.me = os.getpid()
        self.uid = os.getuid()
        self.seen = set()  # pids observed alive as members; their zombies are ours to reap

    def _member(self, pid, info):
        if self.leader is not None and self.leader in (info[2], info[3]):
            return True
        return _carries(pid, self.needle, self.uid)

    def scan(self, *, children_only=False):
        """Live members (excluding the leader), after reaping members' zombies that are our children."""
        alive = []
        for pid in _pids():
            if pid in (self.me, self.leader):
                continue
            info = _stat(pid)
            if info is None or (children_only and info[1] != self.me):
                continue
            if info[0] in 'ZX':
                # Only a launcher reaps: its children of the run are orphans it adopted.
                # stop_strays() leaves a caller's own children for the caller to wait on.
                if self.leader is not None and info[1] == self.me and (
                        pid in self.seen or self.leader in (info[2], info[3])):
                    self._reap(pid)
                continue
            if self._member(pid, info):
                self.seen.add(pid)
                alive.append(pid)
        return alive

    @staticmethod
    def _reap(pid):
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass

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

    def sweep(self, limit):
        """Kill members until none is alive or limit seconds pass: (killed pids, survivors)."""
        deadline = time.monotonic() + limit
        killed = set()
        while True:
            alive = self.scan()
            if not alive or time.monotonic() >= deadline:
                return killed, alive
            for pid in alive:
                if self.signal(pid, signal.SIGKILL):
                    killed.add(pid)
            time.sleep(SWEEP_PAUSE)


def strays(run_id):
    """Pids of live processes of this user whose environment carries TULDOK_RUN_ID=<run_id>."""
    _check_run_id(run_id)
    return sorted(_Sweeper(run_id).scan())


def stop_strays(run_id):
    """Kill every stray of a run whose launcher is gone, for up to SWEEP_LIMIT seconds.

    Returns {'killed': number of processes signalled, 'remaining': pids still alive}.
    """
    _check_run_id(run_id)
    killed, remaining = _Sweeper(run_id).sweep(SWEEP_LIMIT)
    return {'killed': len(killed), 'remaining': sorted(remaining)}


# --- run ----------------------------------------------------------------------

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
                except StopIteration:
                    break
                except OSError:
                    break
                try:
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    return total


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


def _open_log(directory, name):
    return os.open(os.path.join(directory, f'{name}.log'),
                   os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)


def _install_stop_handlers(requests):
    """Route SIGINT and SIGTERM to requests while a run is in progress; main thread only."""
    if threading.current_thread() is not threading.main_thread():
        return {}
    previous = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            before = signal.getsignal(signum)
            if before is None:  # installed outside Python; cannot be restored, so left alone
                continue
            signal.signal(signum, lambda number, frame: requests.append(number))
            previous[signum] = before
    except BaseException:
        _restore_handlers(previous)
        raise
    return previous


def _restore_handlers(previous):
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def run(argv, *, cwd, env, run_id, directory, limits, on_tick=None):
    """Run argv until it and every process it started are gone; return its Outcome.

    env is the child's whole environment; TULDOK_RUN_ID is added. Standard
    output and error are appended to <directory>/stdout.log and stderr.log.
    on_tick(elapsed_seconds) is called about every WATCH_INTERVAL. Called from
    the main thread, SIGINT and SIGTERM to this process cancel the run and the
    previous handlers are restored before returning. Called from another
    thread, Python cannot install handlers there, so those signals keep their
    existing handlers: an exception they raise in the main thread does not
    reach this thread, and if they end the process the child dies by its
    parent-death signal and its strays are left for stop_strays(). An exception
    from on_tick stops the run, sweeps it, and is then raised.
    """
    _check_arguments(argv, env, run_id, directory, limits)
    child_env = dict(env)
    child_env[RUN_ID_VARIABLE] = run_id
    cancel_path = os.path.join(directory, CANCEL_FILE)
    requests = []
    _acquire_subreaper()
    try:
        previous = _install_stop_handlers(requests)
        try:
            return _run(argv, cwd, child_env, run_id, directory, limits, on_tick,
                        cancel_path, requests)
        finally:
            _restore_handlers(previous)
    finally:
        _release_subreaper()


def _run(argv, cwd, env, run_id, directory, limits, on_tick, cancel_path, requests):
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
    # The leader is never reaped until the sweep is over, so its pid, process
    # group and session ids cannot be reused while they are used to find members.
    sweeper = _Sweeper(run_id, child.pid)
    exited = select.poll()
    pidfd = os.pidfd_open(child.pid)
    exited.register(pidfd, select.POLLIN)
    try:
        try:
            reason = _watch(exited, sweeper, started, directory, limits, on_tick,
                            cancel_path, requests)
        except BaseException:
            _stop(exited, sweeper)
            _finish(child, sweeper)
            raise
        leader_gone = True
        if reason is not None:
            leader_gone = _stop(exited, sweeper)
        killed, survivors, status = _finish(child, sweeper) if leader_gone else (set(), [child.pid], None)
    finally:
        os.close(pidfd)
    size = _directory_size(directory)
    if survivors or status is None:
        state = 'unknown'
    elif reason is not None:
        state = reason
    elif status != 0:
        state = 'failed'
    elif size > limits['disk_bytes']:
        state = 'over-disk'  # finished between two measurements but over the limit
    else:
        state = 'succeeded'
    return Outcome(state, status, round(time.monotonic() - started, 3), len(killed), size)


def _leader_exited(exited, timeout=0.0):
    return bool(exited.poll(int(timeout * 1000)))


def _watch(exited, sweeper, started, directory, limits, on_tick, cancel_path, requests):
    """Wait for the leader to exit or for a reason to stop it; return that reason or None."""
    next_disk = started + DISK_INTERVAL
    while not _leader_exited(exited):
        now = time.monotonic()
        elapsed = now - started
        if requests or os.path.lexists(cancel_path):
            return 'cancelled'
        if elapsed > limits['wall_seconds']:
            return 'timed-out'
        if now >= next_disk:
            next_disk = now + DISK_INTERVAL
            if _directory_size(directory) > limits['disk_bytes']:
                return 'over-disk'
        sweeper.scan(children_only=True)  # reap orphans adopted as subreaper
        if on_tick is not None:
            on_tick(elapsed)
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
    """Sweep the exited run, then reap the leader: (killed pids, survivors, exit status)."""
    killed, survivors = sweeper.sweep(SWEEP_LIMIT)
    try:
        status = child.wait(timeout=SWEEP_LIMIT)
    except subprocess.TimeoutExpired:
        status = None
    return killed, survivors, status


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
