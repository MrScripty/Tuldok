"""Queue coordination must not revalidate terminal history while holding its lock."""
import json
import threading

from workbench import WorkbenchError, encode
from unittest.mock import patch

from test_pipeline import WorkspaceCase
from test_external_runs import ExternalCase


class RecordedWake:
    def __init__(self):
        self.event = threading.Event()
        self.waiting = threading.Event()
        self.timeouts = []

    def set(self):
        self.event.set()

    def clear(self):
        self.event.clear()

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        self.waiting.set()
        return self.event.wait(timeout)


class SchedulingReadTests(WorkspaceCase):
    def queued(self, key):
        body = {'request_key': key, 'graph_id': self.graph['id'],
                'graph_revision': self.graph['revision'],
                'validation_token': self.validate()['validation_token']}
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), \
                patch.object(self.dataset.runs, '_start'):
            return self.dataset.runs.submit(body)

    def test_idle_coordinator_never_loads_terminal_runs(self):
        owner = self.dataset.runs
        history = self.queued('terminal-history-0001')
        self.assertEqual(owner.cancel(history['id'])['state'], 'cancelled')
        wake = RecordedWake()
        owner._wake = wake
        with patch.object(owner, '_load', wraps=owner._load) as load:
            try:
                owner._start()
                self.assertTrue(wake.waiting.wait(5), 'coordinator never reached its wait')
                self.assertNotIn(history['id'], [call.args[0] for call in load.call_args_list],
                                 'idle coordination fully validated terminal history')
            finally:
                owner.close()
        self.assertFalse(owner._thread.is_alive())

    def test_empty_coordinator_waits_for_an_event_and_shutdown_wakes_it(self):
        owner = self.dataset.runs
        wake = RecordedWake()
        owner._wake = wake
        try:
            owner._start()
            self.assertTrue(wake.waiting.wait(5), 'coordinator never reached its wait')
            self.assertIsNone(wake.timeouts[0], 'an empty queue must not poll the catalog')
        finally:
            owner.close()
        self.assertFalse(owner._thread.is_alive())

    def test_new_admission_wakes_an_empty_coordinator(self):
        owner = self.dataset.runs
        wake, executed = RecordedWake(), threading.Event()
        owner._wake = wake

        def finish(run_id):
            owner._finish(run_id, 'cancelled', 'Fixture finishes without spawning a worker.')
            executed.set()

        with patch.object(owner, '_execute', side_effect=finish):
            try:
                owner._start()
                self.assertTrue(wake.waiting.wait(5))
                body = {'request_key': 'wake-idle-coordinator-0001', 'graph_id': self.graph['id'],
                        'graph_revision': self.graph['revision'],
                        'validation_token': self.validate()['validation_token']}
                with patch.object(self.pipelines, 'probe', return_value=self.ready()):
                    run = owner.submit(body)
                self.assertTrue(executed.wait(5), 'committed admission did not wake the idle coordinator')
                self.assertEqual(owner.get(run['id'])['state'], 'cancelled')
            finally:
                owner.close()

    def test_queued_resource_shortage_retries_without_a_new_admission(self):
        owner = self.dataset.runs
        run = self.queued('retry-headroom-0001')
        wake, executed = RecordedWake(), threading.Event()
        owner._wake = wake
        available = [0]

        def finish(run_id):
            owner._finish(run_id, 'cancelled', 'Fixture finishes after resource availability changes.')
            executed.set()

        with patch('run_capacity.available_memory', side_effect=lambda: available[0]), \
                patch.object(owner, '_execute', side_effect=finish):
            try:
                owner._start()
                self.assertTrue(wake.waiting.wait(5))
                self.assertEqual(wake.timeouts[0], .25)
                self.assertFalse(executed.is_set())
                available[0] = 64 * 1024**3
                self.assertTrue(executed.wait(5), 'queued work did not retry after headroom changed')
                self.assertEqual(owner.get(run['id'])['state'], 'cancelled')
            finally:
                owner.close()

    def test_builtin_admission_does_not_load_terminal_history_for_capacity(self):
        owner = self.dataset.runs
        history = self.queued('builtin-history-0001')
        owner.cancel(history['id'])
        with patch.object(owner, '_load', wraps=owner._load) as load:
            self.queued('builtin-after-history-0002')
        self.assertNotIn(history['id'], [call.args[0] for call in load.call_args_list])

    def test_selected_queued_run_still_rejects_a_corrupt_envelope(self):
        owner = self.dataset.runs
        run = self.queued('queued-integrity-0001')
        self.assertEqual([row['id'] for row in owner._in_states(('queued',))], [run['id']])
        with self.dataset.lock, self.dataset.db.transaction():
            row = self.dataset.db.execute('SELECT document FROM workspace_runs WHERE id=%s', (run['id'],)).fetchone()
            stored = json.loads(row[0])
            stored['graph_sha256'] = '0' * 64
            self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (encode(stored), run['id']))
        try:
            with self.assertRaises(WorkbenchError) as failure:
                owner._in_states(('queued',))
            self.assertEqual(failure.exception.code, 'unavailable')
            self.assertEqual(str(failure.exception), 'Stored run envelope is invalid; refusing to guess execution state.')
        finally:
            with self.dataset.lock, self.dataset.db.transaction():
                self.dataset.db.execute('UPDATE workspace_runs SET document=%s WHERE id=%s', (row[0], run['id']))



class ExternalSchedulingReads(ExternalCase):
    def test_external_admission_does_not_load_terminal_history_for_capacity(self):
        owner = self.dataset.runs
        history = self.queued(self.body(approval=self.approve()))
        with self.owner.bound(self.dataset):
            owner.cancel(history['id'])
        with patch.object(owner, '_load', wraps=owner._load) as load:
            self.queued(self.body(approval=self.approve()))
        self.assertNotIn(history['id'], [call.args[0] for call in load.call_args_list])
