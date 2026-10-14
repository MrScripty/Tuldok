"""Durable receipts, real process cessation, immutable outputs and holdout custody."""
from auth_helpers import bind_owner
import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import patch

from test_pipeline import WorkspaceCase
from app import Dataset
from runs import process_identity
from metadata import CommitOutcomeUnknown
from workbench import WorkbenchError, encode, timestamp


class RunTests(WorkspaceCase):
    def body(self, key='contract-request-0001'):
        return {'request_key': key, 'graph_id': self.graph['id'], 'graph_revision': self.graph['revision'],
                'validation_token': self.validate()['validation_token']}

    def submit_queued(self, body=None):
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), patch.object(self.dataset.runs, '_start'):
            return self.dataset.runs.submit(body or self.body())

    def await_state(self, run_id, states, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            run = self.dataset.runs.get(run_id)
            if run['state'] in states:
                return run
            time.sleep(.05)
        self.fail(f'Run did not reach {states}: {run}')

    def test_lost_ack_repeated_key_returns_receipt_before_new_graph_validation(self):
        body = self.body()
        run = self.submit_queued(body)
        edited = copy.deepcopy(self.graph)
        edited['nodes'][2]['parameters']['seed'] += 1
        self.pipelines.save(self.graph['id'], {'revision': 1, 'document': edited})
        with patch.object(self.dataset.runs, '_start') as wake:
            receipt = self.dataset.runs.submit(body)
            wake.assert_called_once()
        self.assertEqual(receipt['id'], run['id'])
        self.assertEqual(receipt['graph'], run['graph'])
        self.assertEqual(len(self.dataset.runs.list()), 1)
        with self.assertRaises(WorkbenchError) as failure:
            self.dataset.runs.submit(dict(body, graph_revision=2))
        self.assertEqual(failure.exception.code, 'conflict')
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(dict(body, request_key='bad'))

    def test_lost_commit_ack_reconciliation_wakes_exact_committed_queue(self):
        body = self.body()
        transaction = self.dataset.db.transaction
        @contextmanager
        def commit_then_lose_ack(*args, **kwargs):
            with transaction(*args, **kwargs):
                yield
            raise CommitOutcomeUnknown('Injected lost commit response after a real successful commit.')
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), patch.object(self.dataset.db, 'transaction', side_effect=commit_then_lose_ack):
            with self.assertRaises(CommitOutcomeUnknown):
                self.dataset.runs.submit(body)
        self.assertIsNone(self.dataset.runs._thread)
        with patch.object(self.dataset.runs, '_start') as wake:
            receipt = self.dataset.runs.submit(body)
            wake.assert_called_once()
        self.assertEqual(receipt['state'], 'queued')
        self.assertEqual(len(self.dataset.runs.list()), 1)

    def test_current_exposure_refreshes_without_mutating_admission_evidence(self):
        run = self.submit_queued()
        self.assertFalse(run['prior_test_exposure']['exposed'])
        with self.dataset.lock, self.dataset.db.transaction():
            record = self.dataset.runs._load(run['id'])['source_records'][-1]
            self.dataset.db.execute('INSERT INTO workspace_exposures(id,record_id,source_hash,reason,run_id,release_id,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                (uuid.uuid4().hex, record['id'], record['exported_pixel_sha256'], 'Prior run inspection test evidence.',
                 uuid.uuid4().hex, run['release_id'], timestamp()))
        current = self.dataset.runs.get(run['id'])
        self.assertFalse(current['prior_test_exposure']['exposed'])
        self.assertTrue(current['current_test_exposure']['exposed'])

    def test_queued_cancel_and_peer_supervisor_are_honest(self):
        run = self.submit_queued()
        contents, media = self.dataset.runs.artifact(run['id'], 'release.zip')
        self.assertEqual(media, 'application/zip')
        self.assertEqual(contents, self.dataset.releases.locate(self.release['id']).read_bytes())
        self.assertEqual(run['input_artifacts'][0]['sha256'], self.release['id'])
        peer = Dataset(self.tmp.name)
        try:
            self.assertFalse(peer.runs.runtime_owner)
            self.assertEqual(peer.runs.get(run['id'])['state'], 'queued')
            with self.assertRaises(WorkbenchError) as failure:
                peer.runs.submit(dict(self.body(), request_key='different-request'))
            self.assertEqual(failure.exception.code, 'unavailable')
        finally:
            peer.close()
        self.assertEqual(self.dataset.runs.cancel(run['id'])['state'], 'cancelled')
        self.assertEqual(self.dataset.runs.cancel(run['id'])['state'], 'cancelled')
        self.assertFalse((self.dataset.runs.path / run['id']).exists())

    def test_running_cancel_confirms_real_process_group_drain(self):
        run = self.submit_queued()
        original = subprocess.Popen
        def sleeping_worker(*args, **kwargs):
            return original([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), patch('runs.subprocess.Popen', side_effect=sleeping_worker):
            self.dataset.runs._start()
            until = time.monotonic() + 10
            worker = None
            while time.monotonic() < until:
                with self.dataset.lock:
                    worker = self.dataset.runs._load(run['id'])['worker']
                if worker:
                    break
                time.sleep(.02)
            self.assertIsNotNone(worker)
            self.assertEqual(self.dataset.runs.cancel(run['id'])['state'], 'cancelling')
            cancelled = self.await_state(run['id'], ('cancelled', 'unknown'))
            self.assertEqual(cancelled['state'], 'cancelled')
            self.assertIsNone(process_identity(worker['pid']))
            self.assertEqual(cancelled['artifacts'], [])

    def test_database_disconnect_still_drains_child_before_shutdown_returns(self):
        run = self.submit_queued()
        original = subprocess.Popen
        def sleeping_worker(*args, **kwargs):
            return original([sys.executable, '-c', 'import time; time.sleep(60)'], **kwargs)
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), patch('runs.subprocess.Popen', side_effect=sleeping_worker):
            self.dataset.runs._start()
            until = time.monotonic() + 10
            worker = None
            while time.monotonic() < until:
                with self.dataset.lock:
                    worker = self.dataset.runs._load(run['id'])['worker']
                if worker:
                    break
                time.sleep(.02)
            self.assertIsNotNone(worker)
            self.dataset.db.connection.close()
            self.dataset.close()
            self.assertFalse(self.dataset.runs._thread.is_alive())
            self.assertIsNone(process_identity(worker['pid']))
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')

    def test_unknown_attempt_fences_already_queued_work(self):
        first = self.submit_queued()
        second = self.submit_queued(self.body('second-queued-request'))
        self.dataset.runs._finish(first['id'], 'unknown', 'Injected unconfirmed process cessation.', 'unknown')
        with patch.object(self.dataset.runs, '_execute') as execute:
            self.dataset.runs._start()
            time.sleep(.35)
            self.assertEqual(self.dataset.runs.get(second['id'])['state'], 'queued')
            execute.assert_not_called()
        self.dataset.runs.close()

    def test_worker_failure_retry_preserves_frozen_parent_and_reuses_no_checkpoint(self):
        run = self.submit_queued()
        original = subprocess.Popen
        def failed_worker(*args, **kwargs):
            return original([sys.executable, '-c', 'import time; time.sleep(.1); raise SystemExit(3)'], **kwargs)
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), patch('runs.subprocess.Popen', side_effect=failed_worker):
            self.dataset.runs._start()
            failed = self.await_state(run['id'], ('failed',))
        self.assertEqual(failed['artifacts'], [])
        edited = copy.deepcopy(self.graph)
        edited['nodes'][2]['parameters']['seed'] += 1
        self.pipelines.save(self.graph['id'], {'revision': 1, 'document': edited})
        with patch.object(self.pipelines, 'probe', return_value=self.ready()), patch.object(self.dataset.runs, '_start'):
            retry = self.dataset.runs.retry(run['id'], {'request_key': 'retry-request-0001'})
            again = self.dataset.runs.retry(run['id'], {'request_key': 'retry-request-0001'})
        self.assertNotEqual(retry['id'], run['id'])
        self.assertEqual(retry['id'], again['id'])
        self.assertEqual(retry['parent_run_id'], run['id'])
        self.assertEqual(retry['attempt'], 2)
        self.assertEqual(retry['graph'], run['graph'])
        self.assertEqual(retry['artifacts'], [])
        self.dataset.runs.cancel(retry['id'])

    def test_restart_does_not_replay_queue_or_signal_reused_pid(self):
        run = self.submit_queued()
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        with self.dataset.lock, self.dataset.db.transaction():
            retained = self.dataset.runs._load(run['id'])
            retained['state'] = 'running'
            retained['process_phase'] = 'started'
            retained['worker'] = dict(process_identity(os.getpid()), start_ticks='not-the-original-process')
            self.dataset.runs._save(retained)
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')
        self.assertIsNone(self.dataset.runs._thread)
        self.assertFalse((self.dataset.runs.path / run['id']).exists())

    def test_recovery_keeps_observed_live_prior_process_unknown(self):
        run = self.submit_queued()
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        with self.dataset.lock, self.dataset.db.transaction():
            retained = self.dataset.runs._load(run['id'])
            retained['state'] = 'running'
            retained['process_phase'] = 'started'
            retained['worker'] = process_identity(os.getpid())
            self.dataset.runs._save(retained)
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'unknown')
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.retry(run['id'], {'request_key': 'retry-unknown-request'})
        self.assertTrue(self.dataset.runs._blocked)

    def test_restart_during_proven_pre_spawn_validation_is_interrupted(self):
        run = self.submit_queued()
        with self.dataset.lock, self.dataset.db.transaction():
            retained = self.dataset.runs._load(run['id'])
            retained['state'] = 'running'
            retained['progress']['stage'] = 'validate'
            self.assertEqual(retained['process_phase'], 'not_started')
            self.dataset.runs._save(retained)
        for _ in range(2):
            self.dataset.close()
            self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
            self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')
            self.assertFalse(self.dataset.runs._blocked)

    def test_ambiguous_spawn_reconciles_only_after_matching_process_ceases(self):
        run = self.submit_queued()
        stage = self.dataset.runs.path / ('.staging-' + run['id'])
        stage.mkdir()
        worker = stage / 'image_training.py'
        worker.write_text('import time\ntime.sleep(60)\n')
        job = stage / 'job.json'
        job.write_text('{}')
        command = [sys.executable, str(worker), '--job', str(job)]
        child = subprocess.Popen(command, start_new_session=True)
        def cleanup():
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        self.addCleanup(cleanup)
        with self.dataset.lock, self.dataset.db.transaction():
            retained = self.dataset.runs._load(run['id'])
            retained.update(state='running', process_phase='starting', worker=None, worker_command=command,
                            supervisor=dict(process_identity(os.getpid()), boot_id='previous-boot'))
            self.dataset.runs._save(retained)
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'unknown')
        self.assertTrue(self.dataset.runs._blocked)
        self.assertIsNone(child.poll(), 'Recovery must never signal a remembered/discovered PID.')
        cleanup()
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')
        self.assertFalse(self.dataset.runs._blocked)


class RealCPURunTests(WorkspaceCase):
    def test_real_cpu_results_holdout_exposure_correction_restart_and_tamper(self):
        validation = self.pipelines.validate(self.graph['id'], {'revision': 1})
        self.assertTrue(validation['valid'], validation['errors'])
        body = {'request_key': 'real-tinycnn-request', 'graph_id': self.graph['id'], 'graph_revision': 1,
                'validation_token': validation['validation_token']}
        run = self.dataset.runs.submit(body)
        until = time.monotonic() + 90
        while time.monotonic() < until:
            result = self.dataset.runs.get(run['id'])
            if result['state'] not in ('queued', 'running', 'cancelling'):
                break
            time.sleep(.1)
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['metrics']['validation']['examples'], 2)
        self.assertEqual(len(result['artifacts']), 6)
        self.assertFalse(result['test_exposure']['exposed'])
        self.assertNotIn('test', result['metrics'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.artifact(run['id'], 'test-metrics.json')
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.predictions(run['id'], 'test')
        predictions = self.dataset.runs.predictions(run['id'])
        first = predictions['rows'][0]
        old = self.dataset.workbench.get(first['id'])
        self.dataset.workbench.save(old['id'], dict(revision=old['revision'], source_revision=old['source_revision'],
            task='image_classification', annotation={'label': 'new corrected draft'}, groups=old['groups'], review='draft'))
        changed = self.dataset.runs.predictions(run['id'])['rows'][0]
        self.assertTrue(changed['current_record']['changed'])
        self.assertEqual(changed['truth_label'], first['truth_label'])
        self.assertEqual(changed['frozen_reference'], first['frozen_reference'])
        exposure = self.dataset.runs.expose_test(run['id'], {'reason': 'Final reporting of this explicitly generated test corpus.'})
        self.assertTrue(exposure['test_exposure']['exposed'])
        self.assertEqual(len(self.dataset.runs.predictions(run['id'], 'test')['rows']), 2)
        release = self.pipelines.inspect_release(self.release['id'])
        self.assertTrue(release['prior_test_exposure']['exposed'])
        self.assertEqual(len(release['prior_test_exposure']['events']), 2)
        frozen = self.dataset.runs.artifact(run['id'], 'metrics.json')[0]
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.artifact(run['id'], 'metrics.json')[0], frozen)
        self.assertEqual(self.dataset.runs.submit(body)['id'], run['id'])
        self.assertTrue(self.dataset.runs.get(run['id'])['test_exposure']['exposed'])
        artifact = self.dataset.runs.path / run['id'] / 'metrics.json'
        artifact.write_bytes(artifact.read_bytes() + b'changed')
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.artifact(run['id'], 'metrics.json')
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.get(run['id'])
        self.assertIsNone(self.dataset.runs.list()[0]['metrics'])


if __name__ == '__main__':
    unittest.main()
