"""Real catalog and custodians: independent attempts overlap and drain separately."""
import copy
import os
import time
from unittest.mock import patch

from test_external_runs import ExternalCase
from runs import process_status
from run_capacity import Capacity


class ConcurrentRuns(ExternalCase):
    def sleeping(self):
        graph = copy.deepcopy(self.graph)
        graph['nodes'][1]['parameters']['mode'] = 'sleep'
        self.graph = self.dataset.pipelines.save(graph['id'],
            {'revision': graph['revision'], 'document': graph})
        self.preflight = self.dataset.pipelines.preflight_external(self.graph['id'], self.graph['revision'])

    def test_two_cpu_custodians_overlap_and_cancel_independently(self):
        with self.owner.bound(self.dataset):
            self.sleeping()
        runs = [self.queued(self.body(approval=self.approve())) for _ in range(2)]
        owners = []
        self.dataset.runs._start()
        try:
            until = time.monotonic() + 5
            while time.monotonic() < until:
                with self.owner.bound(self.dataset):
                    current = [self.dataset.runs.get(run['id']) for run in runs]
                if all(run.get('custody_phase') == 'go_intent' for run in current):
                    break
                time.sleep(.03)
            self.assertTrue(all(run['state'] == 'running' and run['custody_phase'] == 'go_intent'
                                for run in current), [(r['state'], r.get('custody_phase')) for r in current])
            with self.dataset.lock:
                owners = [self.dataset.runs._load(r['id'])['custody_identity']['helper'] for r in current]
            self.assertNotEqual(owners[0], owners[1])
            assigned = [set(r['execution_resources']['cpu_affinity']) for r in current]
            self.assertFalse(assigned[0] & assigned[1])
            for owner, cpus in zip(owners, assigned):
                self.assertEqual(set(os.sched_getaffinity(owner['pid'])), cpus)
            with self.owner.bound(self.dataset):
                self.dataset.runs.cancel(runs[0]['id'])
            self.assertEqual(self.await_state(runs[0]['id'], ('cancelled', 'unknown'))['state'], 'cancelled')
            with self.owner.bound(self.dataset):
                self.assertEqual(self.dataset.runs.get(runs[1]['id'])['state'], 'running')
        finally:
            self.dataset.close()
        for owner in owners:
            self.assertEqual(process_status(owner), 'ceased')

    def test_busy_cuda_slot_does_not_block_cpu_and_next_cuda_waits(self):
        with self.owner.bound(self.dataset):
            self.sleeping()
        runs = [self.queued(self.body(approval=self.approve())) for _ in range(3)]
        gpu = {run['id'] for run in runs[:2]}
        capacity = Capacity(1, 1024, 1024, 1024)
        # Real custodians exercise dispatch; device classification is explicitly
        # simulated here. Actual CUDA computation is qualified by the lab fit.
        with patch.object(self.dataset.runs, '_capacity', capacity), patch.object(Capacity, 'claim',
                side_effect=lambda run: ('cuda' if run['id'] in gpu else 'cpu', 1024, 1)):
            self.dataset.runs._start()
            try:
                for index in (0, 2):
                    self.await_state(runs[index]['id'], ('running',))
                with self.owner.bound(self.dataset):
                    self.assertEqual(self.dataset.runs.get(runs[1]['id'])['state'], 'queued')
                    self.dataset.runs.cancel(runs[0]['id'])
                self.assertEqual(self.await_state(runs[0]['id'], ('cancelled', 'unknown'))['state'], 'cancelled')
                self.await_state(runs[1]['id'], ('running',))
                with self.owner.bound(self.dataset):
                    self.assertEqual(self.dataset.runs.get(runs[2]['id'])['state'], 'running')
            finally:
                self.dataset.close()
        self.assertFalse(self.dataset.runs._thread.is_alive())

    def test_memory_shortage_preserves_queue_and_queued_cancel_creates_no_child(self):
        run = self.queued(self.body(approval=self.approve()))
        with patch('run_capacity.available_memory', return_value=0), patch('recipe_process.launch') as launch:
            self.dataset.runs._start()
            time.sleep(.3)
            with self.owner.bound(self.dataset):
                self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'queued')
                self.assertEqual(self.dataset.runs.cancel(run['id'])['state'], 'cancelled')
            self.dataset.close()
            launch.assert_not_called()
