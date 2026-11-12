"""The launcher (spec-m6.md section 3): run, strays, stop_strays and progress.

Stand-in commands are small Python scripts run by the test interpreter. The
module's intervals are shortened so the file runs in seconds. Every test
kills whatever carries its run id when it ends, pass or fail, using its own
/proc scan rather than the code under test, and the run tests check that the
test process is left with no zombie child.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tuldok_project import launcher  # noqa: E402

FAST = {'WATCH_INTERVAL': 0.02, 'DISK_INTERVAL': 0.1, 'STOP_GRACE': 0.6,
        'SWEEP_LIMIT': 3.0, 'SWEEP_PAUSE': 0.02}
GENEROUS = {'wall_seconds': 30, 'disk_bytes': 10 ** 9}


def _carriers(run_id):
    """Pids of live processes with exactly TULDOK_RUN_ID=<run_id>, found independently of launcher."""
    needle = f'TULDOK_RUN_ID={run_id}'.encode()
    found = []
    for name in os.listdir('/proc'):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            with open(f'/proc/{name}/stat', 'rb') as file:
                state = file.read().rsplit(b')', 1)[1].split()[0]
            with open(f'/proc/{name}/environ', 'rb') as file:
                environ = file.read().split(b'\0')
        except OSError:
            continue
        if state != b'Z' and needle in environ:
            found.append(int(name))
    return found


def _kill_run(run_id):
    for _ in range(100):
        pids = _carriers(run_id)
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.02)


def _zombie_children():
    zombies = []
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            with open(f'/proc/{name}/stat', 'rb') as file:
                fields = file.read().rsplit(b')', 1)[1].split()
        except OSError:
            continue
        if fields[0] == b'Z' and int(fields[1]) == os.getpid():
            zombies.append(int(name))
    return zombies


def _alive(pid):
    try:
        with open(f'/proc/{pid}/stat', 'rb') as file:
            return file.read().rsplit(b')', 1)[1].split()[0] not in (b'Z', b'X')
    except OSError:
        return False


class LauncherCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.multiple(launcher, **FAST)
        patcher.start()
        self.addCleanup(patcher.stop)
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.scratch = Path(scratch.name)
        self.directory = self.scratch / 'run'
        self.directory.mkdir()
        self.run_id = 'test-' + uuid.uuid4().hex
        self.addCleanup(_kill_run, self.run_id)
        self.handlers = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))

    def script(self, body):
        path = self.scratch / f'command-{uuid.uuid4().hex[:8]}.py'
        path.write_text(textwrap.dedent(body))
        return path

    def env(self):
        return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'LANG': 'C.UTF-8',
                'PYTHONDONTWRITEBYTECODE': '1'}

    def run_script(self, body, *, limits=GENEROUS, on_tick=None, args=()):
        outcome = launcher.run([sys.executable, str(self.script(body)), *args],
                               cwd=str(self.scratch), env=self.env(), run_id=self.run_id,
                               directory=str(self.directory), limits=limits, on_tick=on_tick)
        self.assertEqual(_carriers(self.run_id), [], 'a process of the run outlived run()')
        self.assertEqual(_zombie_children(), [], 'run() left a zombie child')
        self.assertEqual((signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)),
                         self.handlers, 'signal handlers were not restored')
        return outcome

    def log(self, name):
        return (self.directory / f'{name}.log').read_text()

    def wait_for(self, path, timeout=10):
        deadline = time.monotonic() + timeout
        while not path.exists() or not path.read_text().strip():
            if time.monotonic() > deadline:
                self.fail(f'{path.name} was never written')
            time.sleep(0.01)
        return int(path.read_text())


class RunTests(LauncherCase):
    def test_success_logs_and_environment(self):
        outcome = self.run_script('''
            import json, os, sys
            print('hello out')
            print('hello err', file=sys.stderr)
            print(json.dumps(sorted(os.environ)))
            print(os.environ['TULDOK_RUN_ID'])
            print(sys.stdin.read() == '')
        ''')
        self.assertEqual(outcome.state, 'succeeded')
        self.assertEqual(outcome.exit_status, 0)
        self.assertEqual(outcome.strays, 0)
        self.assertGreater(outcome.bytes, 0)
        lines = self.log('stdout').splitlines()
        self.assertEqual(lines[0], 'hello out')
        self.assertEqual(json.loads(lines[1]), sorted([*self.env(), 'TULDOK_RUN_ID']))
        self.assertEqual(lines[2], self.run_id)
        self.assertEqual(lines[3], 'True')
        self.assertEqual(self.log('stderr'), 'hello err\n')

    def test_logs_are_appended(self):
        (self.directory / 'stdout.log').write_text('earlier\n')
        self.run_script('print("later")')
        self.assertEqual(self.log('stdout'), 'earlier\nlater\n')

    def test_new_session(self):
        self.run_script('import os; print(os.getsid(0) == os.getpid())')
        self.assertEqual(self.log('stdout'), 'True\n')

    def test_non_zero_exit(self):
        outcome = self.run_script('import sys; sys.exit(3)')
        self.assertEqual((outcome.state, outcome.exit_status), ('failed', 3))

    def test_wall_time_limit(self):
        started = time.monotonic()
        outcome = self.run_script('import time; time.sleep(30)',
                                  limits={'wall_seconds': 0.3, 'disk_bytes': 10 ** 9})
        self.assertEqual(outcome.state, 'timed-out')
        self.assertEqual(outcome.exit_status, -signal.SIGTERM)
        self.assertLess(time.monotonic() - started, 5)

    def test_disk_limit(self):
        outcome = self.run_script(f'''
            import os, time
            os.makedirs({str(self.directory / 'output' / 'deep')!r})
            with open({str(self.directory / 'output' / 'deep' / 'big')!r}, 'wb') as file:
                file.write(b'x' * 100000)
            time.sleep(30)
        ''', limits={'wall_seconds': 30, 'disk_bytes': 50000})
        self.assertEqual(outcome.state, 'over-disk')
        self.assertGreaterEqual(outcome.bytes, 100000)

    def test_disk_over_at_exit_is_not_success(self):
        outcome = self.run_script(f'''
            with open({str(self.directory / 'big')!r}, 'wb') as file:
                file.write(b'x' * 100000)
        ''', limits={'wall_seconds': 30, 'disk_bytes': 50000})
        self.assertEqual((outcome.state, outcome.exit_status), ('over-disk', 0))

    def test_cancel_file(self):
        def tick(elapsed):
            if elapsed > 0.2:
                (self.directory / 'cancel').touch()
        outcome = self.run_script('import time; time.sleep(30)', on_tick=tick)
        self.assertEqual(outcome.state, 'cancelled')

    def test_on_tick_is_given_elapsed_seconds(self):
        seen = []
        self.run_script('import time; time.sleep(0.3)', on_tick=seen.append)
        self.assertTrue(seen)
        self.assertEqual(seen, sorted(seen))

    def test_on_tick_exception_stops_the_run(self):
        def tick(elapsed):
            if elapsed > 0.1:
                raise RuntimeError('tick failed')
        pid_file = self.scratch / 'pid'
        with self.assertRaisesRegex(RuntimeError, 'tick failed'):
            launcher.run([sys.executable, str(self.script(f'''
                import os, time
                open({str(pid_file)!r}, 'w').write(str(os.getpid()))
                time.sleep(30)
            '''))], cwd=str(self.scratch), env=self.env(), run_id=self.run_id,
                directory=str(self.directory), limits=GENEROUS, on_tick=tick)
        self.assertEqual(_carriers(self.run_id), [])
        self.assertEqual(_zombie_children(), [])
        self.assertEqual((signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM)), self.handlers)

    def test_command_ignoring_sigterm_is_killed_after_grace(self):
        started = time.monotonic()
        outcome = self.run_script('''
            import signal, time
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            time.sleep(30)
        ''', limits={'wall_seconds': 0.3, 'disk_bytes': 10 ** 9})
        self.assertEqual(outcome.state, 'timed-out')
        self.assertEqual(outcome.exit_status, -signal.SIGKILL)
        self.assertGreaterEqual(time.monotonic() - started, 0.3 + FAST['STOP_GRACE'])

    def test_child_outliving_the_command_is_a_stray(self):
        pid_file = self.scratch / 'pid'
        outcome = self.run_script(f'''
            import os, time
            if os.fork() == 0:
                open({str(pid_file)!r}, 'w').write(str(os.getpid()))
                time.sleep(30)
                os._exit(0)
            while not os.path.exists({str(pid_file)!r}):
                time.sleep(0.01)
        ''')
        self.assertEqual(outcome.state, 'succeeded')
        self.assertEqual(outcome.strays, 1)
        self.assertFalse(_alive(int(pid_file.read_text())))

    def test_grandchild_in_own_session_ignoring_sigterm(self):
        pid_file = self.scratch / 'pid'
        body = f'''
            import os, signal, sys, time
            if os.fork() == 0:
                os.setsid()
                if os.fork() == 0:
                    signal.signal(signal.SIGTERM, signal.SIG_IGN)
                    open({str(pid_file)!r} + '.tmp', 'w').write(str(os.getpid()))
                    os.rename({str(pid_file)!r} + '.tmp', {str(pid_file)!r})
                    time.sleep(30)
                os._exit(0)
            os.wait()
            while not os.path.exists({str(pid_file)!r}):
                time.sleep(0.01)
            if sys.argv[1] == 'stay':
                time.sleep(30)
        '''
        for mode, state in (('exit', 'succeeded'), ('stay', 'timed-out')):
            with self.subTest(mode=mode):
                pid_file.unlink(missing_ok=True)
                outcome = self.run_script(body, args=(mode,),
                                          limits={'wall_seconds': 1.0, 'disk_bytes': 10 ** 9})
                self.assertEqual(outcome.state, state)
                grandchild = int(pid_file.read_text())
                self.assertFalse(_alive(grandchild))
                if mode == 'exit':
                    self.assertEqual(outcome.strays, 1)

    def test_sigterm_to_launcher_cancels_and_caller_continues(self):
        for signum in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=signum.name):
                timer = threading.Timer(0.3, os.kill, (os.getpid(), signum))
                timer.start()
                self.addCleanup(timer.cancel)
                outcome = self.run_script('import time; time.sleep(30)')
                timer.join()
                self.assertEqual(outcome.state, 'cancelled')
                self.assertEqual(outcome.exit_status, -signal.SIGTERM)

    def test_run_from_another_thread(self):
        results = []
        thread = threading.Thread(target=lambda: results.append(launcher.run(
            [sys.executable, '-c', 'print(1)'], cwd=str(self.scratch), env=self.env(),
            run_id=self.run_id, directory=str(self.directory), limits=GENEROUS)))
        thread.start()
        thread.join(30)
        self.assertEqual(results[0].state, 'succeeded')
        self.assertEqual(_zombie_children(), [])

    def test_run_id_prefix_is_not_a_match(self):
        neighbour = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                     env={**self.env(), 'TULDOK_RUN_ID': self.run_id + 'x'})
        self.addCleanup(neighbour.wait)
        self.addCleanup(neighbour.kill)
        outcome = self.run_script('print(1)')
        self.assertEqual((outcome.state, outcome.strays), ('succeeded', 0))
        self.assertIsNone(neighbour.poll())

    def test_prctl_failure_refuses_to_run(self):
        def failing(option, argument):
            raise OSError(1, 'refused')
        with mock.patch.object(launcher, '_prctl', failing):
            with self.assertRaises(OSError):
                launcher.run([sys.executable, '-c', 'print(1)'], cwd=str(self.scratch), env=self.env(),
                             run_id=self.run_id, directory=str(self.directory), limits=GENEROUS)
        self.assertFalse((self.directory / 'stdout.log').exists())

    def test_pdeathsig_failure_in_child_raises(self):
        real = launcher._prctl

        def failing_pdeathsig(option, argument):
            if option == launcher.PR_SET_PDEATHSIG:
                raise OSError(1, 'refused')
            return real(option, argument)
        with mock.patch.object(launcher, '_prctl', failing_pdeathsig):
            with self.assertRaises(subprocess.SubprocessError):
                launcher.run([sys.executable, '-c', 'print(1)'], cwd=str(self.scratch), env=self.env(),
                             run_id=self.run_id, directory=str(self.directory), limits=GENEROUS)
        self.assertEqual(_zombie_children(), [])

    def test_bad_arguments(self):
        good = dict(cwd=str(self.scratch), env=self.env(), run_id=self.run_id,
                    directory=str(self.directory), limits=GENEROUS)
        for change in ({'limits': {'wall_seconds': 0, 'disk_bytes': 1}},
                       {'limits': {'wall_seconds': 1, 'disk_bytes': 1.5}},
                       {'limits': {'wall_seconds': 1}},
                       {'run_id': ''}, {'run_id': 'a=b'},
                       {'directory': str(self.scratch / 'missing')}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                launcher.run([sys.executable, '-c', 'print(1)'], **{**good, **change})


class StrayTests(LauncherCase):
    def start_outside(self, run_id):
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                   env={**self.env(), 'TULDOK_RUN_ID': run_id})
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process

    def test_strays_and_stop_strays(self):
        process = self.start_outside(self.run_id)
        deadline = time.monotonic() + 10
        while process.pid not in launcher.strays(self.run_id):  # environ is set at exec
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        self.assertEqual(launcher.strays(self.run_id), [process.pid])
        result = launcher.stop_strays(self.run_id)
        self.assertEqual(result, {'killed': 1, 'remaining': []})
        self.assertEqual(process.wait(5), -signal.SIGKILL)
        self.assertEqual(launcher.strays(self.run_id), [])

    def test_prefix_and_extension_do_not_match(self):
        longer = self.start_outside(self.run_id + 'c')
        self.addCleanup(_kill_run, self.run_id + 'c')
        deadline = time.monotonic() + 10
        while longer.pid not in launcher.strays(self.run_id + 'c'):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        self.assertEqual(launcher.strays(self.run_id), [])
        self.assertEqual(launcher.stop_strays(self.run_id), {'killed': 0, 'remaining': []})
        self.assertIsNone(longer.poll())

    def test_run_id_is_checked(self):
        for bad in ('', 'a\0b', 'a=b', 7):
            with self.subTest(run_id=bad), self.assertRaises(ValueError):
                launcher.strays(bad)


def event(**change):
    value = {'format': 'tuldok_progress_v1', 'stage': 'train', 'completed': 5, 'total': 10,
             'metrics': {'loss': 0.5}}
    value.update(change)
    return json.dumps(value)


class ProgressTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)

    def write(self, name, data):
        (self.directory / f'{name}.log').write_bytes(data if type(data) is bytes else data.encode())

    def test_valid_event(self):
        self.write('stdout', 'starting\n' + event() + '\n' + 'plain text\n')
        self.write('stderr', 'a warning\n')
        result = launcher.progress(str(self.directory))
        self.assertEqual(result['event'], json.loads(event()))
        self.assertEqual(result['stderr'], 'a warning\n')
        self.assertEqual(result['stderr_bytes'], 10)
        self.assertEqual(result['stdout_bytes'], len(result['stdout']))

    def test_invalid_events_are_skipped(self):
        earlier = event(completed=1)
        for bad in (event(completed=11), event(stage='-bad'), event(total=1000001),
                    event(metrics={f'm{i}': 1 for i in range(9)}), event(completed=True),
                    event(extra=1), event(format='other'),
                    event()[:-1] + ', "stage": "x"}',
                    event(metrics={'loss': 1}).replace('1}', 'NaN}'), 'not json', '[]'):
            with self.subTest(line=bad):
                self.write('stdout', earlier + '\n' + bad + '\n')
                self.assertEqual(launcher.progress(str(self.directory))['event'], json.loads(earlier))

    def test_over_long_line_is_ignored(self):
        long_line = event(completed=9)[:-1] + ' ' * 4100 + '}'
        self.write('stdout', event() + '\n' + long_line + '\n')
        self.assertEqual(launcher.progress(str(self.directory))['event'], json.loads(event()))

    def test_incomplete_last_line_is_ignored(self):
        self.write('stdout', event() + '\n' + event(completed=9))
        self.assertEqual(launcher.progress(str(self.directory))['event'], json.loads(event()))

    def test_missing_logs(self):
        self.assertEqual(launcher.progress(str(self.directory)),
                         {'stdout': '', 'stderr': '', 'stdout_bytes': None, 'stderr_bytes': None,
                          'event': None})
        self.assertEqual(launcher.progress(str(self.directory / 'absent'))['event'], None)

    def test_symbolic_link_is_not_followed(self):
        target = self.directory / 'elsewhere.txt'
        target.write_text(event() + '\n')
        (self.directory / 'stdout.log').symlink_to(target)
        result = launcher.progress(str(self.directory))
        self.assertEqual((result['stdout'], result['stdout_bytes'], result['event']), ('', None, None))
        linked = self.directory.parent / (self.directory.name + '-link')
        linked.symlink_to(self.directory)
        self.addCleanup(linked.unlink)
        self.assertIsNone(launcher.progress(str(linked))['stdout_bytes'])

    def test_large_log_reads_only_the_tail(self):
        data = ('x' * 99 + '\n') * 20000 + event() + '\n'
        self.write('stdout', data)
        with mock.patch('os.pread', wraps=os.pread) as pread:
            result = launcher.progress(str(self.directory))
        self.assertTrue(all(call.args[1] <= 8192 for call in pread.call_args_list))
        self.assertEqual(result['stdout_bytes'], len(data))
        self.assertLessEqual(len(result['stdout'].encode()), 8192)
        self.assertEqual(result['event'], json.loads(event()))

    def test_cut_first_line_is_not_an_event(self):
        # The tail starts inside a long line whose remainder is itself a valid event.
        data = 'y' * 300 + event() + '\n' + 'z' * (8192 - len(event()) - 2) + '\n'
        self.assertEqual(len(data) - 8192, 300)  # the tail begins exactly at the '{'
        self.write('stdout', data)
        self.assertIsNone(launcher.progress(str(self.directory))['event'])

    def test_text_is_sanitised(self):
        self.write('stderr', b'ok\tline\n\x1b[31mred\x00\r\n\xff\xfe end\n')
        self.assertEqual(launcher.progress(str(self.directory))['stderr'],
                         'ok\tline\n[31mred\n�� end\n')


if __name__ == '__main__':
    unittest.main()
