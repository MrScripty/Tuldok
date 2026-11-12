"""Looking at runs, cancelling and stopping them, and estimates (spec-m6.md, sections 3, 4, 7 and 8).

Every test needs a database and runs only when TULDOK_DATABASE_URL names a
disposable cluster. Each one starts from the committed copy of
tests/fixtures/tuldok_project/buildable that test_tuldok_project_builds.BuildCase
makes, with TULDOK_PROJECT_HOME pointing at a temporary directory. A build
"in another process" is the command line started with BUILDABLE_HOLD, which
makes a stand-in script wait for a release file. Whatever a test starts is
stopped in its cleanup: the release file is written, a build still running is
killed, and every process that carries one of the project's run ids is killed,
so no process outlives a test even when it fails.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import builds, launcher, plan  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
import test_tuldok_project_builds as base  # noqa: E402

REPOSITORY = base.REPOSITORY
WAIT = 30


class CommandCase(base.BuildCase):
    """BuildCase with the command line, builds in another process, and a cleanup that leaves no process behind."""

    def setUp(self):
        super().setUp()
        self.hold = self.temporary / 'hold'
        self.hold.mkdir()
        self.children = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        (self.hold / 'release').touch()
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=60)
        try:
            with builds.opened(self.folder) as project:
                run_ids = [row[0] for row in project._execute('SELECT id FROM {schema}.runs').fetchall()]
        except Exception:  # the schema may be gone; the processes still carry the run ids found below
            run_ids = []
        for run_id in run_ids:
            launcher.stop_strays(run_id)

    def environment(self, extra=None):
        return {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', **(extra or {})}

    def cli(self, *arguments, stdin=''):
        return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                              env=self.environment(), input=stdin, capture_output=True, text=True, timeout=120)

    def start(self, *arguments):
        child = subprocess.Popen([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                                 env=self.environment(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        return child

    def start_held_build(self, target, script):
        """A build in another process, waiting inside script until release; returns (process, run row)."""
        child = self.start('build', self.folder, target, '--yes', '--env', f'BUILDABLE_HOLD={script}:{self.hold}')
        deadline = time.monotonic() + WAIT
        while not (self.hold / 'started').exists():
            if child.poll() is not None:
                self.fail(f'The build ended before {script} started: {child.communicate()}')
            self.assertLess(time.monotonic(), deadline, f'{script} did not start')
            time.sleep(0.05)
        with builds.opened(self.folder) as project:
            running = [row for row in builds.runs(project) if row['state'] == 'running']
        self.assertEqual(len(running), 1)
        return child, running[0]

    def run_of(self, reference):
        return self.runs(reference)[0]


class Looking(CommandCase):
    """run and progress, on a finished run and on one running in another process."""

    def test_a_finished_run(self):
        self.assertTrue(self.build('recipes/fit-a')['ok'])
        fit = self.run_of('recipes/fit-a')
        prefix = fit['id'][:8]

        shown = self.cli('run', self.folder, prefix)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        rows = {line.split('  ')[0]: line.split('  ', 1)[1].strip() for line in shown.stdout.splitlines() if line}
        self.assertEqual(rows['run'], fit['id'])
        self.assertEqual(rows['state'], 'succeeded')
        self.assertEqual(rows['exit status'], '0')
        self.assertTrue(rows['code'].startswith(f'commit {fit["commit"][:12]}'))
        self.assertTrue(rows['output weights'].startswith('weights.json  weights  '))
        self.assertEqual(rows['progress'].split('  ')[0], 'fit 4 of 4 (100%)')
        self.assertEqual(rows['builder'], f'process {os.getpid()}')  # this process built it; the run is over
        listed = json.loads(self.cli('run', self.folder, prefix, '--json').stdout)
        self.assertEqual((listed['id'], listed['state'], listed['event']['completed']), (fit['id'], 'succeeded', 4))
        self.assertEqual(listed['product']['outputs']['weights']['path'], 'weights.json')
        self.assertTrue(listed['product']['current'])
        self.assertFalse(listed['builder_alive'])
        self.assertIn('"estimate"', listed['definition'])

        watched = self.cli('progress', self.folder, prefix)
        self.assertEqual(watched.returncode, 0, watched.stderr)
        lines = watched.stdout.splitlines()
        self.assertEqual(lines[2].split(), ['state', 'succeeded'])
        self.assertTrue(lines[4].startswith('stdout.log: '))
        self.assertEqual(sum('"tuldok_progress_v1"' in line for line in lines), 4)
        self.assertEqual(lines[-1], 'stderr.log: empty')
        found = json.loads(self.cli('progress', self.folder, prefix, '--json').stdout)
        self.assertEqual((found['state'], found['event']['stage'], found['stderr_bytes']), ('succeeded', 'fit', 0))
        self.assertEqual(found['stdout_bytes'], len(found['stdout'].encode()))

        started = time.monotonic()
        followed = self.cli('progress', self.folder, prefix, '--follow')
        self.assertLess(time.monotonic() - started, 10)  # an ended run is shown once
        self.assertEqual(followed.returncode, 0, followed.stderr)
        lines = followed.stdout.splitlines()
        self.assertEqual(lines[0], f'run {fit["id"]}  recipes/fit-a  succeeded')
        self.assertEqual(sum(line.startswith('out  ') for line in lines), 4)
        self.assertTrue(lines[-1].startswith(f'Run {fit["id"]} ended succeeded after '))
        passes = [json.loads(line) for line in self.cli('progress', self.folder, prefix, '--follow',
                                                         '--json').stdout.splitlines()]
        self.assertEqual(len(passes), 1)
        self.assertTrue(passes[0]['ended'])

    def test_a_run_in_another_process(self):
        child, row = self.start_held_build('datasets/numbers', 'make_data')
        prefix = row['id'][:6]
        started = time.monotonic()
        shown = self.cli('run', self.folder, prefix)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        rows = {line.split('  ')[0]: line.split('  ', 1)[1].strip() for line in shown.stdout.splitlines() if line}
        self.assertEqual((rows['builder'], rows['state'], rows['progress'], rows['finished']),
                         (f'process {child.pid} (running)', 'running', 'none yet', '-'))
        found = json.loads(self.cli('progress', self.folder, prefix, '--json').stdout)
        self.assertEqual((found['state'], found['event'], found['stdout']), ('running', None, ''))
        self.assertLess(time.monotonic() - started, 20)

        follower = self.start('progress', self.folder, prefix, '--follow')
        self.assertEqual(follower.stdout.readline(), f'run {row["id"]}  datasets/numbers  running\n')
        (self.hold / 'release').touch()
        rest, errors = follower.communicate(timeout=WAIT)
        self.assertEqual(follower.returncode, 0, errors)
        lines = rest.splitlines()
        self.assertIn(f'out  numbers in {row["directory"]}/output', lines)  # printed after the release
        self.assertEqual(lines.count(f'out  numbers in {row["directory"]}/output'), 1)  # once, never repeated
        self.assertTrue(lines[-1].startswith(f'Run {row["id"]} ended succeeded'), lines)
        child.communicate(timeout=WAIT)
        self.assertEqual(child.returncode, 0)

    def test_follow_yields_only_what_is_new(self):
        child, row = self.start_held_build('datasets/numbers', 'make_data')
        passes = []
        for item in builds.follow(self.folder, row['id'], interval=0.2):
            passes.append(item)
            if len(passes) == 2:
                (self.hold / 'release').touch()
            self.assertLess(len(passes), 200)
        self.assertTrue(passes[-1]['ended'])
        self.assertEqual(passes[-1]['run']['state'], 'succeeded')
        self.assertFalse(any(item['ended'] for item in passes[:-1]))
        written = ''.join(item['stdout'] for item in passes)
        self.assertEqual(written, f'numbers in {row["directory"]}/output\n')
        child.communicate(timeout=WAIT)


class Prefixes(CommandCase):

    def insert(self, run_id, state='succeeded', pid=None, boot=None):
        with builds.opened(self.folder) as project:
            project._execute('''INSERT INTO {schema}.runs (id, reference, plan_id, state, scratch, commit,
                                    definition, inputs, argv, env, directory, owner_pid, owner_boot, queued_at)
                                VALUES (%s, 'steps/gpu-one', 'p', %s, false, '', '{{}}', '{{}}', '[]', '{{}}',
                                        %s, %s, %s, now())''',
                             (run_id, state, str(self.temporary / 'runs' / run_id), pid, boot))

    def test_unique_ambiguous_and_too_short(self):
        first, second = 'abcdef' + '0' * 25 + '1', 'abcdef' + '0' * 25 + '2'
        self.insert(first)
        self.insert(second)
        with builds.opened(self.folder) as project:
            self.assertEqual(builds.find_run(project, first), first)
            self.assertEqual(builds.find_run(project, first[:-1] + '1'), first)
            self.assertEqual(builds.find_run(project, 'abcdef' + '0' * 25 + '2'), second)
            with self.assertRaises(ProjectError) as raised:
                builds.find_run(project, 'abcdef0')
            self.assertEqual((raised.exception.code, sorted(raised.exception.references)), ('ambiguous', [first, second]))
            for text in ('abcde', 'ffffff', 'a b', ''):
                with self.assertRaises(ProjectError) as raised:
                    builds.find_run(project, text)
                self.assertEqual(raised.exception.code, 'not-found')
        ambiguous = self.cli('run', self.folder, 'abcdef')
        self.assertEqual(ambiguous.returncode, 1)
        self.assertTrue(ambiguous.stderr.startswith('abcdef is the start of 2 runs; give more of the id:'))
        self.assertIn(f'  {first}  steps/gpu-one  -  succeeded', ambiguous.stderr)
        self.assertIn(f'  {second}  steps/gpu-one  -  succeeded', ambiguous.stderr)
        short = self.cli('progress', self.folder, 'abcde')
        self.assertEqual(short.returncode, 1)
        self.assertIn('at least its first 6 characters', short.stderr)
        exact = self.cli('run', self.folder, second, '--json')
        self.assertEqual(json.loads(exact.stdout)['id'], second)
        missing = self.cli('progress', self.folder, second)  # a run whose directory was never made
        self.assertEqual(missing.returncode, 0, missing.stderr)
        self.assertIn('stdout.log: not written', missing.stdout)


class Cancelling(CommandCase):

    def test_cancel_stops_a_running_build(self):
        child, row = self.start_held_build('benchmarks/score', 'train')
        self.assertEqual(row['reference'], 'recipes/fit-a')
        started = time.monotonic()
        asked = self.cli('cancel', self.folder, row['id'][:10])
        self.assertEqual(asked.returncode, 0, asked.stderr)
        self.assertEqual(asked.stdout, f'Asked run {row["id"]} (recipes/fit-a) to stop: its build stops it within '
                                       'a second or so and records it as cancelled.\n')
        self.assertTrue(os.path.exists(os.path.join(row['directory'], 'cancel')))
        output, errors = child.communicate(timeout=WAIT)
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(child.returncode, 1, errors)
        self.assertIn(f'end    recipes/fit-a  run {row["id"]}  cancelled', output)
        self.assertEqual(output.splitlines()[-1], 'Stopped: recipes/fit-a did not succeed; later steps were not run.')
        fit = self.run_of('recipes/fit-a')
        self.assertEqual((fit['state'], fit['problem']), ('cancelled', 'It was cancelled.'))
        self.assertEqual(self.runs('benchmarks/score'), [])
        self.assertEqual(launcher.strays(row['id']), [])

        finished = self.cli('cancel', self.folder, row['id'][:6])
        self.assertEqual(finished.returncode, 1)
        self.assertEqual(finished.stderr, f'Run {row["id"]} (recipes/fit-a) is cancelled; only a queued or running '
                                          'run can be cancelled.\n')

    def test_cancel_in_json(self):
        child, row = self.start_held_build('datasets/numbers', 'make_data')
        asked = json.loads(self.cli('cancel', self.folder, row['id'], '--json').stdout)
        self.assertEqual(asked, {'id': row['id'], 'reference': 'datasets/numbers', 'subject': '', 'state': 'running',
                                 'cancel_file': os.path.join(row['directory'], 'cancel'), 'already_asked': False})
        child.communicate(timeout=WAIT)
        self.assertEqual(child.returncode, 1)
        self.assertEqual(self.run_of('datasets/numbers')['state'], 'cancelled')
        self.assertEqual(self.states()['datasets/numbers'], 'not-built')

    def test_cancel_refuses_a_finished_run(self):
        self.assertTrue(self.build('datasets/numbers')['ok'])
        run = self.run_of('datasets/numbers')
        refused = self.cli('cancel', self.folder, run['id'])
        self.assertEqual(refused.returncode, 1)
        self.assertIn('is succeeded; only a queued or running run can be cancelled.', refused.stderr)
        self.assertFalse(os.path.exists(os.path.join(run['directory'], 'cancel')))


class Stopping(CommandCase):

    def test_stop_is_refused_while_the_builder_lives(self):
        child, row = self.start_held_build('datasets/numbers', 'make_data')
        refused = self.cli('stop', self.folder, row['id'][:8])
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(refused.stderr, f'Run {row["id"]} (datasets/numbers) is still being run by its build '
                                         f'(process {child.pid}); use cancel to stop it.\n')
        (self.hold / 'release').touch()
        child.communicate(timeout=WAIT)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(self.run_of('datasets/numbers')['state'], 'succeeded')

    def test_stop_after_the_builder_was_killed(self):
        child, row = self.start_held_build('datasets/numbers', 'make_data')
        child.send_signal(signal.SIGKILL)
        child.communicate(timeout=WAIT)
        # The custodian sees its caller die, stops the run and writes its outcome.
        deadline = time.monotonic() + WAIT
        while not os.path.exists(os.path.join(row['directory'], launcher.OUTCOME_FILE)):
            self.assertLess(time.monotonic(), deadline, 'the custodian did not finish')
            time.sleep(0.1)
        self.assertEqual(launcher.strays(row['id']), [])
        stopped = self.cli('stop', self.folder, row['id'][:8])
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(stopped.stdout, f'No process of the run was left running: run {row["id"]} (datasets/numbers).\n'
                                         'It was running; it is now unknown, and is never restarted.\n')
        run = self.run_of('datasets/numbers')
        self.assertEqual(run['state'], 'unknown')
        self.assertTrue(run['problem'].startswith(f'Stopped with stop: the build that ran it (process {child.pid}) '
                                                  'was gone; 0 stray processes killed.'), run['problem'])
        self.assertEqual(self.states()['datasets/numbers'], 'failed')

    def orphan(self):
        """A running row whose builder is gone, and a stray process carrying its run id (this test's child)."""
        gone = subprocess.Popen([sys.executable, '-c', 'pass'])
        gone.wait()
        run_id = uuid.uuid4().hex
        with builds.opened(self.folder) as project:
            project._execute('''INSERT INTO {schema}.runs (id, reference, plan_id, state, scratch, commit,
                                    definition, inputs, argv, env, directory, owner_pid, owner_boot, queued_at,
                                    started_at)
                                VALUES (%s, 'steps/gpu-one', 'p', 'running', false, '', '{{}}', '{{}}', '[]', '{{}}',
                                        %s, %s, %s, now(), now())''',
                             (run_id, str(self.temporary / 'runs' / run_id), gone.pid, builds.boot_id()))
        stray = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                                 env={**os.environ, launcher.RUN_ID_VARIABLE: run_id})

        def end_stray():
            if stray.poll() is None:
                stray.kill()
            stray.wait(timeout=30)
        self.addCleanup(end_stray)
        deadline = time.monotonic() + WAIT
        while launcher.strays(run_id) != [stray.pid]:  # its environment is readable once it has started
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.02)
        return run_id, gone.pid, stray

    def test_stop_kills_the_strays_of_an_orphaned_row(self):
        run_id, gone, stray = self.orphan()
        stopped = self.cli('stop', self.folder, run_id[:7])
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(stopped.stdout, f'Killed 1 process of the run: run {run_id} (steps/gpu-one).\n'
                                         'It was running; it is now unknown, and is never restarted.\n')
        self.assertEqual(stray.wait(timeout=WAIT), -signal.SIGKILL)
        run = self.runs('steps/gpu-one')[0]
        self.assertEqual((run['state'], run['strays']), ('unknown', 1))
        self.assertEqual(run['problem'], f'Stopped with stop: the build that ran it (process {gone}) was gone; '
                                         '1 stray process killed.')
        again = json.loads(self.cli('stop', self.folder, run_id, '--json').stdout)
        self.assertEqual({key: again[key] for key in ('was', 'state', 'killed', 'remaining', 'marked_unknown')},
                         {'was': 'unknown', 'state': 'unknown', 'killed': 0, 'remaining': [], 'marked_unknown': False})

    def test_stop_in_process_and_a_live_builder(self):
        run_id, _gone, stray = self.orphan()
        with builds.opened(self.folder) as project:
            project._execute('UPDATE {schema}.runs SET owner_pid = %s WHERE id = %s', (os.getpid(), run_id))
        with self.assertRaises(ProjectError) as raised:
            builds.stop(self.folder, run_id)
        self.assertEqual(raised.exception.code, 'builder-alive')
        self.assertIsNone(stray.poll())
        with builds.opened(self.folder) as project:
            project._execute("UPDATE {schema}.runs SET owner_boot = 'another-boot' WHERE id = %s", (run_id,))
        done = builds.stop(self.folder, run_id)
        self.assertEqual((done['was'], done['state'], done['killed'], done['marked_unknown']),
                         ('running', 'unknown', 1, True))
        self.assertEqual(stray.wait(timeout=WAIT), -signal.SIGKILL)


class Estimates(CommandCase):

    def step(self, made, reference):
        return next(step for step in made['steps'] if step['reference'] == reference)

    def test_skipped_measured_shown_and_stale(self):
        done = builds.estimate(self.folder, ['recipes/fit-a'])
        self.assertEqual([(item['reference'], item['result']) for item in done['steps']],
                         [('datasets/numbers', 'skipped'), ('recipes/fit-a', 'skipped')])
        self.assertEqual(done['steps'][0]['reason'], 'It has no estimate command.')
        self.assertIn('its input data (datasets/numbers) has no current product', done['steps'][1]['reason'])
        self.assertIsNone(self.step(self.plan('recipes/fit-a'), 'recipes/fit-a')['estimate'])

        self.assertTrue(self.build('datasets/numbers')['ok'])
        runs_before = len(self.runs())
        done = builds.estimate(self.folder, ['recipes/fit-a'])
        self.assertEqual(len(done['steps']), 1)
        item = done['steps'][0]
        self.assertEqual((item['result'], item['values']), ('measured', {'disk_bytes': 4800, 'wall_seconds': 2.0,
                                                                         'items': 6}))
        self.assertEqual(len(self.runs()), runs_before)  # an estimate is not a run
        self.assertEqual(os.listdir(self.home / self.project_id / builds.ESTIMATES), [])  # thrown away
        made = self.plan('recipes/fit-a')
        shown = self.step(made, 'recipes/fit-a')['estimate']
        self.assertEqual({key: shown[key] for key in builds.ESTIMATE_FIELDS},
                         {'disk_bytes': 4800, 'wall_seconds': 2.0, 'items': 6})
        self.assertEqual((made['estimated_disk_gb'], made['estimated_disk_steps']), (4.8e-06, 1))
        self.assertEqual((made['estimated_wall_hours'] * 3600, made['estimated_wall_steps']), (2.0, 1))
        self.assertEqual((made['disk_gb'], made['disk_unknown']), (0, 1))  # the declared sums are unchanged

        text = self.cli('plan', self.folder, 'benchmarks/score')
        lines = text.stdout.splitlines()
        self.assertIn('3  build   -    ? ~4.8 KB est.  ? ~2 s est.  recipes/fit-a', lines)
        self.assertIn('4  build   -    ?               ?            benchmarks/score', lines)
        self.assertIn('Disk: no step declares it.', lines)
        self.assertIn('Estimated: disk ~4.8 KB (1 of 2 steps); time ~2 s (1 of 2 steps).', lines)
        self.assertEqual(lines[-3], 'Declared figures are as the definitions declare them; figures marked est. are')
        listed = json.loads(self.cli('plan', self.folder, 'recipes/fit-a', '--json').stdout)
        self.assertEqual(self.step(listed, 'recipes/fit-a')['estimate']['items'], 6)

        self.edit('recipes/fit-a', lambda document: document.update(description='Described now.'))
        made = self.plan('recipes/fit-a')
        self.assertIsNone(self.step(made, 'recipes/fit-a')['estimate'])  # measured for another text
        self.assertEqual(made['estimated_disk_steps'], 0)
        self.assertEqual(self.cli('plan', self.folder, 'recipes/fit-a').stdout.splitlines()[-1],
                         'Figures are as the definitions declare them; no command was run.')

    def test_a_command_that_prints_no_json_object(self):
        self.assertTrue(self.build('datasets/numbers')['ok'])
        self.assertEqual(builds.estimate(self.folder, ['recipes/fit-a'])['steps'][0]['result'], 'measured')
        refused = self.cli('estimate', self.folder, 'recipes/fit-a', '--env', 'BUILDABLE_ESTIMATE=text')
        self.assertEqual(refused.returncode, 1, refused.stderr)
        lines = refused.stdout.splitlines()
        self.assertTrue(lines[0].startswith('Ran from the code at commit '))
        self.assertEqual(lines[2].split(), ['step', 'estimate', 'disk', 'time', 'items'])
        self.assertEqual(lines[3].split(), ['recipes/fit-a', 'failed', '-', '-', '-'])
        self.assertTrue(lines[4].startswith('  Its standard output is not one JSON object'), lines)
        self.assertEqual(lines[-1], '0 measured, 0 skipped, 1 failed. plan shows each estimate while its '
                                    'definition is unchanged.')
        # The failed measurement left the earlier estimate in place.
        self.assertEqual(self.step(self.plan('recipes/fit-a'), 'recipes/fit-a')['estimate']['items'], 6)
        for document in ('[1, 2]', '{"disk_bytes": -1}', '{"items": "six"}', '{"other": 1}', '{"a": 1} {"b": 2}',
                         '{"items": NaN}'):
            directory = self.temporary / 'printed'
            directory.mkdir(exist_ok=True)
            (directory / 'stdout.log').write_text(document + '\n')
            values, reason = builds._estimate_values(launcher.Outcome('succeeded', 0, 0.1, 0, 0), directory)
            self.assertIsNone(values, document)
            self.assertTrue(reason, document)

    def test_the_commands_text_and_json(self):
        listed = json.loads(self.cli('estimate', self.folder, 'recipes/fit-a', '--json').stdout)
        self.assertEqual([(item['reference'], item['result']) for item in listed['steps']],
                         [('datasets/numbers', 'skipped'), ('recipes/fit-a', 'skipped')])
        self.assertTrue(self.build('datasets/numbers')['ok'])
        measured = self.cli('estimate', self.folder, 'recipes/fit-a')
        self.assertEqual(measured.returncode, 0, measured.stderr)
        self.assertEqual(measured.stdout.splitlines()[2:], [
            'step           estimate  disk    time  items',
            'recipes/fit-a  measured  4.8 KB  2 s   6',
            '',
            '1 measured, 0 skipped, 0 failed. plan shows each estimate while its definition is unchanged.'])
        nothing = self.cli('estimate', self.folder, 'datasets/numbers')
        self.assertEqual((nothing.returncode, nothing.stdout),
                         (0, 'Nothing would be built, so there is nothing to estimate.\n'))
        self.assertEqual(self.cli('estimate', self.folder).returncode, 2)

    def test_a_dirty_tree_needs_scratch(self):
        self.assertTrue(self.build('datasets/numbers')['ok'])
        self.write_code('estimate.py', (self.code / 'estimate.py').read_text() + '# not committed\n')
        with self.assertRaises(ProjectError) as raised:
            builds.estimate(self.folder, ['recipes/fit-a'])
        self.assertEqual((raised.exception.code, raised.exception.files), ('dirty', ['estimate.py']))
        done = builds.estimate(self.folder, ['recipes/fit-a'], scratch=True)
        self.assertEqual((done['scratch'], done['steps'][0]['result']), (True, 'measured'))

    def test_removing_the_definition_drops_its_estimate(self):
        self.assertTrue(self.build('datasets/numbers')['ok'])
        self.edit('recipes/fit-b', lambda document: document['run'].update(
            estimate={'command': ['python', 'estimate.py', '--data', '{inputs.data}/numbers.json',
                                  '--settings', '{settings}', '--out', '{output}']}))
        self.commit('An estimate for fit-b.')
        self.assertEqual(builds.estimate(self.folder, ['recipes/fit-b'])['steps'][0]['values']['wall_seconds'], 1.5)
        with builds.opened(self.folder) as project:
            self.assertIn('recipes/fit-b', builds.stored_estimates(project))
            project.remove_definition('recipes/fit-b')
            count = project._execute('SELECT count(*) FROM {schema}.estimates').fetchone()[0]
        self.assertEqual(count, 0)


class PlanFigures(unittest.TestCase):
    """make_plan with estimates, without a database."""

    def test_estimates_beside_declared_figures(self):
        documents = base._documents()
        local = {'environments/test-python': 'ready'}
        estimates = {'recipes/fit-a': {'disk_bytes': 3e9, 'wall_seconds': 5400, 'items': 6, 'measured_at': 'x'},
                     'datasets/numbers': {'disk_bytes': None, 'wall_seconds': 60, 'items': None, 'measured_at': 'x'}}
        made = plan.make_plan(documents, ['recipes/fit-a'], local=local, estimates=estimates)
        self.assertEqual((made['estimated_disk_gb'], made['estimated_disk_steps']), (3.0, 1))
        self.assertEqual((made['estimated_wall_hours'], made['estimated_wall_steps']), (1.5 + 60 / 3600, 2))
        self.assertEqual((made['disk_gb'], made['wall_hours']), (0.01, 0.05))
        from tuldok_project import __main__ as cli
        lines = cli._plan_lines(made)
        self.assertIn('2  build   -    0.01 GB       0.05 h ~60 s est.  datasets/numbers', lines)
        self.assertIn('3  build   -    ? ~3 GB est.  ? ~90 min est.     recipes/fit-a', lines)
        self.assertIn('Estimated: disk ~3 GB (1 of 2 steps); time ~91 min (2 of 2 steps).', lines)


if __name__ == '__main__':
    unittest.main()
