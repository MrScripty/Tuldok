"""Build requests and their worker (spec-m7.md, section 4), execute's expect and stop, and the three commands.

Everything needs a database and runs only when TULDOK_DATABASE_URL names a
disposable cluster. Each test starts from test_tuldok_project_builds.BuildCase
(a Git-committed copy of the buildable fixture with its environment connected,
dropped afterwards) and opens the project with builds.opened, which waits
while the worker has it open for a moment. The worker looks every 0.1 s here
instead of every second. A build that must still be running when the test
acts holds datasets/numbers through the fixture's BUILDABLE_HOLD hook, set in
the definition's run.env so the worker's build sees it; every test touches
the release file and stops what any run of the project left behind. The
commands are the fixture's stand-in scripts; no GPU is used.
"""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tuldok_project import activity, build_requests, builds, launcher, local, service as service_module  # noqa: E402
from tuldok_project.service import Service  # noqa: E402
from tuldok_project.store import ProjectError  # noqa: E402
import test_tuldok_project_builds as builds_base  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
ALL_SCOPES = ['admin', 'approve-execution', 'approve-review', 'cancel', 'edit', 'execute', 'expose-holdout',
              'freeze', 'inspect']
OWNER = {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner', 'scopes': ALL_SCOPES}
AGENT = {'actor_id': 'agent-1', 'kind': 'agent', 'label': 'An agent', 'scopes': ['inspect', 'execute', 'cancel']}
SCORE = {'targets': ['benchmarks/score']}
ENDED = ('succeeded', 'failed', 'cancelled', 'declined', 'expired')


class RequestCase(builds_base.BuildCase):
    """BuildCase with services, a quick worker and a hold directory."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(service_module, 'POLL_SECONDS', 0.1)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.hold = self.temporary / 'hold'
        self.hold.mkdir()
        self.addCleanup(self.stop_everything)   # runs after every service is closed

    def stop_everything(self):
        (self.hold / 'release').touch()
        try:
            with builds.opened(self.folder) as project:
                run_ids = [row[0] for row in project._execute('SELECT id FROM {schema}.runs').fetchall()]
        except Exception:  # the folder may not open; nothing is then known of its runs
            run_ids = []
        for run_id in run_ids:
            launcher.stop_strays(run_id)

    def opened(self):
        return builds.opened(self.folder)

    def service(self, start=True):
        made = Service(self.folder)
        self.addCleanup(made.close)
        if start:
            made.start()
        return made

    def call(self, service, name, arguments, actor=OWNER):
        result = service.call(name, arguments, actor)
        json.dumps(result, allow_nan=False)
        return result

    def refused(self, service, name, arguments, actor=OWNER):
        with self.assertRaises(ProjectError) as caught:
            service.call(name, arguments, actor)
        return caught.exception

    def shown(self, request_id):
        with self.opened() as project:
            return build_requests.show(project, request_id)

    def wait_for(self, request_id, states=ENDED, seconds=60):
        deadline = time.monotonic() + seconds
        while True:
            shown = self.shown(request_id)
            if shown['state'] in states:
                return shown
            self.assertLess(time.monotonic(), deadline, f'request still {shown["state"]}')
            time.sleep(0.05)

    def wait_until(self, condition, seconds=30):
        deadline = time.monotonic() + seconds
        while not condition():
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)

    def hold_numbers(self):
        """Make datasets/numbers wait for the release file (saved to the folder, so a request covers it)."""
        self.edit('datasets/numbers', lambda document: document['run']['env'].update(
            BUILDABLE_HOLD=f'make_data:{self.hold}'))

    def activity(self):
        with self.opened() as project:
            return activity.items(project._connection, project.schema, 0, 500)['items']


class Requesting(RequestCase):

    def test_an_owners_request_runs_through_a_started_service(self):
        served = self.service()
        self.assertEqual(self.call(served, 'summary', {})['worker'], 'running')
        asked = self.call(served, 'request_build', SCORE)
        self.assertEqual(tuple(asked), tuple(service_module.operations.REQUEST))
        self.assertEqual((asked['state'], asked['decided_by'], asked['requested_by']),
                         ('queued', {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner'},
                          {'actor_id': 'owner-1', 'kind': 'owner', 'label': 'The owner'}))
        covers = asked['covers']
        commit = subprocess.run(['git', '-C', str(self.root), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                check=True).stdout.strip()
        self.assertEqual((covers['targets'], covers['every'], covers['scratch'], covers['commit']),
                         (['benchmarks/score'], False, False, commit))
        self.assertEqual(covers['steps'], [{'reference': 'datasets/numbers', 'subjects': []},
                                           {'reference': 'recipes/fit-a', 'subjects': []},
                                           {'reference': 'benchmarks/score', 'subjects': ['fit-a', 'zero']}])
        self.assertEqual(sorted(covers['definitions']), ['benchmarks/score', 'datasets/numbers',
                                                         'environments/test-python', 'recipes/fit-a'])
        text = (self.folder / 'recipes' / 'fit-a.json').read_text(encoding='utf-8')
        self.assertEqual(covers['definitions']['recipes/fit-a'], builds._sha256_text(text))

        done = self.wait_for(asked['id'])
        self.assertEqual(done['state'], 'succeeded', done['problem'])
        self.assertIsNone(done['problem'])
        self.assertEqual([(run['reference'], run['subject'], run['state']) for run in done['runs']],
                         [('datasets/numbers', '', 'succeeded'), ('recipes/fit-a', '', 'succeeded'),
                          ('benchmarks/score', 'fit-a', 'succeeded'), ('benchmarks/score', 'zero', 'succeeded')])
        self.assertTrue(all(run['plan_id'] == done['plan_id'] for run in done['runs']))
        self.assertEqual([item['run_id'] for item in done['result']], [run['id'] for run in done['runs']])
        self.assertEqual(len(self.products()), 4)
        self.assertIsNotNone(done['started_at'])
        self.assertIsNotNone(done['finished_at'])
        listed = self.call(served, 'build_requests', {})['requests']
        self.assertEqual([(row['id'], 'covers' in row) for row in listed], [(asked['id'], False)])
        self.assertEqual(self.call(served, 'build_request', {'request': asked['id'][:6]})['id'], asked['id'])
        self.assertEqual(self.call(served, 'build_requests', {'state': 'queued'})['requests'], [])
        rows = [(row['operation'], row['target'], row['outcome']) for row in self.activity()]
        self.assertEqual(rows, [('request_build', asked['id'], 'done')])
        self.assertEqual(self.refused(served, 'request_build', SCORE).code, 'nothing-to-build')

    def test_an_agents_request_waits_until_approved(self):
        served = self.service()
        asked = self.call(served, 'request_build', SCORE, actor=AGENT)
        self.assertEqual((asked['state'], asked['decided_at'], asked['decided_by']), ('awaiting-approval', None, None))
        time.sleep(0.5)  # five passes of the worker
        self.assertEqual(self.shown(asked['id'])['state'], 'awaiting-approval')
        self.assertEqual(self.runs(), [])
        self.assertEqual(self.refused(served, 'approve_build', {'request': asked['id']}, actor=AGENT).code,
                         'forbidden')
        approved = self.call(served, 'approve_build', {'request': asked['id'][:8]})
        self.assertEqual((approved['state'], approved['decided_by']['kind']), ('queued', 'owner'))
        self.assertIsNone(asked['expires_at'])
        self.assertTrue(approved['expires_at'] > approved['decided_at'])
        done = self.wait_for(asked['id'])
        self.assertIsNone(done['expires_at'])
        self.assertEqual(done['state'], 'succeeded', done['problem'])
        self.assertEqual(len(done['runs']), 4)
        self.assertEqual(self.refused(served, 'approve_build', {'request': asked['id']}).code, 'not-awaiting')
        rows = [(row['operation'], row['outcome'], row['actor']['kind']) for row in self.activity()]
        self.assertEqual(rows, [('approve_build', 'not-awaiting', 'owner'), ('approve_build', 'done', 'owner'),
                                ('request_build', 'done', 'agent')])

    def test_decline(self):
        served = self.service()
        asked = self.call(served, 'request_build', SCORE, actor=AGENT)
        declined = self.call(served, 'decline_build', {'request': asked['id'], 'reason': 'Not now.'})
        self.assertEqual((declined['state'], declined['problem'], declined['decided_by']['actor_id']),
                         ('declined', 'Not now.', 'owner-1'))
        self.assertEqual(self.refused(served, 'decline_build', {'request': asked['id']}).code, 'not-awaiting')
        self.assertEqual(self.refused(served, 'approve_build', {'request': asked['id']}).code, 'not-awaiting')
        self.assertEqual(self.runs(), [])

    def test_approval_is_refused_when_a_definition_or_the_commit_changed(self):
        served = self.service()
        asked = self.call(served, 'request_build', SCORE, actor=AGENT)
        document = self.call(served, 'definition', {'reference': 'recipes/fit-a'})['document']
        document['title'] = 'Fit a, changed after the request'
        self.call(served, 'set_definition', {'reference': 'recipes/fit-a', 'text': json.dumps(document) + '\n'})
        refused = self.refused(served, 'approve_build', {'request': asked['id']})
        self.assertEqual(refused.code, 'stale')
        shown = self.shown(asked['id'])
        self.assertEqual(shown['state'], 'declined')
        self.assertIn('recipes/fit-a', shown['problem'])
        self.assertEqual(shown['decided_by']['kind'], 'owner')

        again = self.call(served, 'request_build', SCORE, actor=AGENT)
        self.write_code('train.py', (self.code / 'train.py').read_text() + '# a change\n')
        self.commit('Change the code.')
        self.assertEqual(self.refused(served, 'approve_build', {'request': again['id']}).code, 'stale')
        self.assertIn('the commit', self.shown(again['id'])['problem'])
        self.assertEqual(self.runs(), [])

    def test_refusals_when_asking(self):
        served = self.service()
        self.assertEqual(self.refused(served, 'request_build', {'targets': ['recipes/none']}).code, 'not-found')
        self.edit('recipes/fit-a', lambda document: document.update(
            earlier_work={'rebuild': 'needs-work', 'reason': 'Its command needs a change.'}))
        self.assertEqual(self.refused(served, 'request_build', {'targets': ['recipes/fit-a']}).code, 'blocked')
        for _ in range(build_requests.PENDING_LIMIT):
            self.call(served, 'request_build', {'targets': ['recipes/fit-b']}, actor=AGENT)
        refused = self.refused(served, 'request_build', {'targets': ['recipes/fit-b']}, actor=AGENT)
        self.assertEqual(refused.code, 'too-many')
        self.assertEqual(len(self.call(served, 'build_requests', {'limit': 500})['requests']),
                         build_requests.PENDING_LIMIT)
        outcomes = [row['outcome'] for row in self.activity()]
        self.assertEqual((outcomes[0], outcomes[-2:]), ('too-many', ['blocked', 'not-found']))

    def test_nothing_to_build(self):
        self.build_all()
        served = self.service()
        self.assertEqual(self.refused(served, 'request_build', SCORE).code, 'nothing-to-build')
        self.assertEqual(self.refused(served, 'request_build', {'targets': []}, actor=AGENT).code, 'nothing-to-build')


class Worker(RequestCase):

    def test_a_queued_request_whose_covers_changed_fails(self):
        served = self.service(start=False)
        asked = self.call(served, 'request_build', SCORE)
        self.edit('datasets/numbers', lambda document: document['run']['settings'].update(count=5))
        served.start()
        done = self.wait_for(asked['id'])
        self.assertEqual(done['state'], 'failed')
        self.assertIn('datasets/numbers', done['problem'])
        self.assertEqual(self.runs(), [])

    def test_an_approval_expires_after_an_hour(self):
        served = self.service(start=False)
        late = self.call(served, 'request_build', SCORE)
        with self.opened() as project:
            project._execute("UPDATE {schema}.build_requests SET decided_at = now() - interval '3601 seconds' "
                             'WHERE id = %s', (late['id'],))
        served.start()
        done = self.wait_for(late['id'])
        self.assertEqual(done['state'], 'expired')
        self.assertIn('ask for the build again', done['problem'])
        self.assertEqual(self.runs(), [])

    def test_cancelling_in_each_state(self):
        served = self.service(start=False)
        waiting = self.call(served, 'request_build', SCORE, actor=AGENT)
        queued = self.call(served, 'request_build', SCORE)
        for asked in (waiting, queued):
            cancelled = self.call(served, 'cancel_build', {'request': asked['id']}, actor=AGENT)
            self.assertEqual((cancelled['state'], cancelled['problem']), ('cancelled', 'Cancelled by An agent.'))
        self.assertEqual(self.refused(served, 'cancel_build', {'request': waiting['id']}).code, 'not-cancellable')

        self.hold_numbers()
        running = self.call(served, 'request_build', SCORE)
        served.start()
        self.wait_until(lambda: (self.hold / 'started').exists())
        self.assertEqual(self.shown(running['id'])['state'], 'running')
        asked = self.call(served, 'cancel_build', {'request': running['id']}, actor=AGENT)
        self.assertEqual((asked['state'], asked['cancel_requested']), ('running', True))
        done = self.wait_for(running['id'])
        self.assertEqual(done['state'], 'cancelled', done['problem'])
        self.assertEqual([(run['reference'], run['state']) for run in done['runs']], [('datasets/numbers', 'cancelled')])
        self.assertEqual(launcher.strays(done['runs'][0]['id']), [])
        self.assertEqual(self.refused(served, 'cancel_build', {'request': running['id']}).code, 'not-cancellable')
        rows = [(row['operation'], row['outcome']) for row in self.activity()]
        self.assertEqual(rows[:2], [('cancel_build', 'not-cancellable'), ('cancel_build', 'done')])

    def test_a_running_request_whose_process_is_gone_fails(self):
        served = self.service(start=False)
        asked = self.call(served, 'request_build', SCORE)
        other = self.call(served, 'request_build', {'targets': ['recipes/fit-b']}, actor=AGENT)
        gone = subprocess.Popen([sys.executable, '-c', 'pass'])
        gone.wait()
        with self.opened() as project:
            for request_id, pid, boot in ((asked['id'], gone.pid, builds.boot_id()),
                                          (other['id'], os.getpid(), 'another-boot')):
                project._execute("UPDATE {schema}.build_requests SET state = 'running', started_at = now(), "
                                 'owner_pid = %s, owner_boot = %s WHERE id = %s', (pid, boot, request_id))
        served.start()
        for request_id in (asked['id'], other['id']):
            done = self.wait_for(request_id, ('failed',))
            self.assertEqual(done['problem'], build_requests.ORPHAN_PROBLEM)
        self.assertEqual(self.runs(), [])

    def test_a_second_service_on_the_project_runs_nothing(self):
        first = self.service()
        second = self.service()
        self.assertEqual((first.call('summary', {}, OWNER)['worker'], second.call('summary', {}, OWNER)['worker']),
                         ('running', 'elsewhere'))
        first.close()
        self.assertEqual(first.call('summary', {}, OWNER)['worker'], 'stopped')

        # Another process holds the lock: a started service runs nothing until it is let go.
        path = os.path.join(local.home(self.project_id), service_module.WORKER_LOCK)
        self.wait_until(lambda: second.call('summary', {}, OWNER)['worker'] == 'running')  # it took it over
        second.close()
        descriptor = os.open(path, os.O_RDWR)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            third = self.service()
            self.assertEqual(third.call('summary', {}, OWNER)['worker'], 'elsewhere')
            asked = self.call(third, 'request_build', SCORE)
            time.sleep(0.6)
            self.assertEqual(self.shown(asked['id'])['state'], 'queued')
            self.assertEqual(self.runs(), [])
        finally:
            os.close(descriptor)
        self.assertEqual(self.wait_for(asked['id'])['state'], 'succeeded')

    def test_close_stops_a_running_request_in_time(self):
        self.hold_numbers()
        served = self.service()
        asked = self.call(served, 'request_build', SCORE)
        self.wait_until(lambda: (self.hold / 'started').exists())
        run_id = self.runs()[0]['id']
        self.assertTrue(launcher.strays(run_id))
        started = time.monotonic()
        served.close()
        self.assertLess(time.monotonic() - started, service_module.CLOSE_SECONDS)
        self.assertEqual(served.call('summary', {}, OWNER)['worker'], 'stopped')
        self.assertEqual(launcher.strays(run_id), [])
        done = self.shown(asked['id'])
        self.assertEqual((done['state'], done['cancel_requested']), ('cancelled', True))
        self.assertEqual([run['state'] for run in done['runs']], ['cancelled'])
        served.close()  # twice is fine

    def test_an_exception_in_the_worker_fails_the_request_and_the_worker_goes_on(self):
        served = self.service(start=False)
        broken = self.call(served, 'request_build', {'targets': ['datasets/numbers']})
        later = self.call(served, 'request_build', {'targets': ['recipes/fit-b']})
        calls = []
        real = builds.execute

        def execute(*arguments, **options):
            calls.append(arguments)
            if len(calls) == 1:
                raise RuntimeError('a fault')
            return real(*arguments, **options)

        with mock.patch.object(builds, 'execute', execute), self.assertLogs(service_module.__name__, 'ERROR'):
            served.start()
            failed = self.wait_for(broken['id'])
            done = self.wait_for(later['id'])
        self.assertEqual((failed['state'], failed['problem']), ('failed', 'RuntimeError: a fault'))
        self.assertEqual(done['state'], 'succeeded', done['problem'])


class Expect(RequestCase):
    """builds.execute's expect and stop."""

    def approved(self, *targets):
        with self.opened() as project:
            made = builds_base.plan.build_plan(project, list(targets))
            return made, build_requests.covers(project, made, list(targets), every=False, scratch=False)

    def test_a_definition_changed_after_approval_stops_the_build_before_its_step(self):
        for where in ('database', 'disk'):
            with self.subTest(where):
                with self.opened() as project:
                    project._execute('UPDATE {schema}.products SET current = false')
                made, covers = self.approved('recipes/fit-a')
                original = (self.folder / 'recipes' / 'fit-a.json').read_text(encoding='utf-8')
                changed = original.replace('Fit a, from a settings file', f'Fit a, changed in the {where}')

                def on_event(kind, item):
                    if kind == 'end' and item['reference'] == 'datasets/numbers':
                        if where == 'database':
                            with self.opened() as project:
                                project.set_definition('recipes/fit-a', changed)
                        else:
                            (self.folder / 'recipes' / 'fit-a.json').write_text(changed, encoding='utf-8')

                before = len(self.runs('recipes/fit-a'))
                with self.assertRaises(ProjectError) as raised:
                    builds.execute(self.folder, made, confirm=lambda _plan: True, expect=covers, on_event=on_event)
                self.assertEqual((raised.exception.code, raised.exception.references), ('stale', ['recipes/fit-a']))
                self.assertEqual(self.runs('datasets/numbers')[0]['state'], 'succeeded')  # finished steps stay
                self.assertEqual(len(self.runs('recipes/fit-a')), before)                 # never started
                with self.opened() as project:  # put it back for the next round
                    if where == 'database':
                        project.set_definition('recipes/fit-a', original)
                        project.save()
                (self.folder / 'recipes' / 'fit-a.json').write_text(original, encoding='utf-8')

    def test_another_commit_is_refused_before_anything_runs(self):
        made, covers = self.approved('datasets/numbers')
        self.write_code('make_data.py', (self.code / 'make_data.py').read_text() + '# later\n')
        self.commit('Later.')
        asked = []
        with self.assertRaises(ProjectError) as raised:
            builds.execute(self.folder, made, confirm=lambda given: asked.append(given) or True, expect=covers)
        self.assertEqual(raised.exception.code, 'stale')
        self.assertEqual((asked, self.runs()), ([], []))

    def test_unchanged_runs_and_stop_ends_the_build(self):
        made, covers = self.approved('benchmarks/score')
        calls = []

        def stop():
            calls.append(len(calls))
            return len(calls) > 2

        done = builds.execute(self.folder, made, confirm=lambda _plan: True, expect=covers, stop=stop)
        self.assertFalse(done['ok'])
        self.assertEqual(self.ran(done), [('datasets/numbers', '', 'succeeded'), ('recipes/fit-a', '', 'succeeded')])
        done = builds.execute(self.folder, self.plan('benchmarks/score'), confirm=lambda _plan: True,
                              expect=self.approved('benchmarks/score')[1])
        self.assertTrue(done['ok'])
        self.assertEqual(len(done['steps']), 2)  # the two subjects

    def test_estimates_are_given_in_utc(self):
        text = (self.folder / 'recipes' / 'fit-a.json').read_text(encoding='utf-8')
        with self.opened() as project:
            project._connection.execute("SET TIME ZONE 'Asia/Manila'")
            project._execute('''INSERT INTO {schema}.estimates (reference, definition_sha256, "values", measured_at)
                                VALUES ('recipes/fit-a', %s, '{{"items": 6}}', '2026-11-12 08:00:00+08')''',
                             (builds._sha256_text(text),))
            found = builds.stored_estimates(project)
        self.assertEqual(found['recipes/fit-a']['measured_at'], '2026-11-12T00:00:00+00:00')


class Commands(RequestCase):
    """requests, approve and decline on the command line."""

    def run_cli(self, *arguments, stdin=''):
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-m', 'tuldok_project', *map(str, arguments)], cwd=REPOSITORY,
                              env=environment, input=stdin, capture_output=True, text=True, timeout=120)

    def test_requests_approve_and_decline(self):
        empty = self.run_cli('requests', self.folder)
        self.assertEqual((empty.returncode, empty.stdout), (0, 'No build has been requested.\n'), empty.stderr)
        served = self.service(start=False)
        first = self.call(served, 'request_build', SCORE, actor=AGENT)
        second = self.call(served, 'request_build', {'targets': ['recipes/fit-b']}, actor=AGENT)

        listed = self.run_cli('requests', self.folder)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        table = listed.stdout.splitlines()
        self.assertEqual(table[0].split(), ['request', 'state', 'asked', 'by', 'targets'])
        self.assertEqual([line.split()[0] for line in table[1:]], [second['id'], first['id']])
        self.assertIn('awaiting-approval', table[1])
        rows = json.loads(self.run_cli('requests', self.folder, '--json').stdout)
        self.assertEqual([row['id'] for row in rows], [second['id'], first['id']])
        self.assertNotIn('covers', rows[0])

        refused = self.run_cli('approve', self.folder, first['id'][:8], stdin='n\n')
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn('benchmarks/score  subjects fit-a, zero', refused.stdout)
        self.assertTrue(refused.stdout.endswith('Approve this? [y/N] \nNothing was approved.\n'), refused.stdout)
        self.assertEqual(self.shown(first['id'])['state'], 'awaiting-approval')

        approved = self.run_cli('approve', self.folder, first['id'][:8], stdin='y\n')
        self.assertEqual(approved.returncode, 0, approved.stderr)
        self.assertIn(f'Approved: request {first["id"]} is queued.', approved.stdout)
        shown = self.shown(first['id'])
        self.assertEqual((shown['state'], shown['decided_by']),
                         ('queued', {'actor_id': None, 'kind': 'owner', 'label': 'command line'}))

        again = self.run_cli('approve', self.folder, first['id'], '--yes')
        self.assertEqual(again.returncode, 1)
        self.assertIn('only a request awaiting approval', again.stderr)
        missing = self.run_cli('decline', self.folder, 'abcdef12')
        self.assertEqual(missing.returncode, 1)
        declined = self.run_cli('decline', self.folder, second['id'], '--reason', 'Fit b is not wanted.')
        self.assertEqual(declined.returncode, 0, declined.stderr)
        shown = self.shown(second['id'])
        self.assertEqual((shown['state'], shown['problem']), ('declined', 'Fit b is not wanted.'))
        usage = self.run_cli('decline', self.folder, second['id'], '--reason', 'x' * 401)
        self.assertEqual(usage.returncode, 2)

        rows = [(row['operation'], row['target'], row['outcome'], row['actor']['label']) for row in self.activity()]
        self.assertEqual(rows[:4], [('decline_build', second['id'], 'done', 'command line'),
                                    ('decline_build', 'abcdef12', 'not-found', 'command line'),
                                    ('approve_build', first['id'], 'not-awaiting', 'command line'),
                                    ('approve_build', first['id'][:8], 'done', 'command line')])
        self.assertEqual(len(rows), 6)  # and the two requests; the refused confirmation wrote nothing

        served.start()  # the app serving the folder runs what was approved on the command line
        self.assertEqual(self.wait_for(first['id'])['state'], 'succeeded')


if __name__ == '__main__':
    unittest.main()
