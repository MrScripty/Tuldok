"""Consumer invariants; simulated segments are byte-integrity fault fixtures only."""
import copy
from contextlib import contextmanager
import time
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent_api import AgentAPIError, AgentClient, encoded
from test_agent_project_cli import SegmentFixture
from tuldok_client import WorkflowClient, _manifest

CATALOG, RUN = 'a' * 32, 'b' * 32


class ConsumerFixture(SegmentFixture):
    catalog_id = CATALOG
    timeout = 10

    def __init__(self, raw=b'consumer exact segmented bytes'):
        super().__init__(raw)
        self.requests = []
        self.state = 'completed'
        self.failure = None
        self.after_segment = None

    @contextmanager
    def read_budget(self, deadline, cancelled=None):
        original = self.timeout
        self.timeout = original if deadline is None else min(original, max(.000001, deadline-time.monotonic()))
        try:
            yield self
        finally:
            self.timeout = original

    def selected_contracts(self):
        return {'runs.submit_external': 1, 'runs.artifact_chunk': 1, 'runs.get': 1}

    def call(self, operation, arguments):
        self.requests.append((operation, copy.deepcopy(arguments)))
        if operation == 'runs.get':
            return {'status': 200, 'result': {'id': RUN, 'dataset_id': CATALOG,
                'state': self.state, 'custody_phase': 'drained', 'artifacts': [
                    {'name': 'one.bin', 'sha256': hashlib.sha256(self.raw).hexdigest(), 'bytes': len(self.raw)},
                    {'name': 'two.bin', 'sha256': hashlib.sha256(self.raw).hexdigest(), 'bytes': len(self.raw)}]}}
        if self.failure is not None:
            raise self.failure
        if operation == 'runs.submit_external':
            return {'status': 201, 'result': {'id': RUN, 'state': 'queued', 'dataset_id': CATALOG,
                'request_key': arguments['request_key'], 'graph': {'id': arguments['graph_id']},
                'graph_revision': arguments['graph_revision'], 'material_sha256': arguments['expected_digest'],
                'approval_id': arguments['approval_id']}}
        if operation == 'runs.cancel':
            return {'status': 200, 'result': {'id': RUN, 'state': 'cancelling', 'custody_phase': 'go_intent'}}
        value = super().call(operation, arguments)
        if self.after_segment is not None:
            self.after_segment(arguments)
        return value


class WorkflowClientTests(unittest.TestCase):
    def manifest(self):
        return _manifest(CATALOG, 'runs.submit_external', {'graph_id': RUN, 'graph_revision': 1,
            'expected_digest': 'c'*64, 'approval_id': 'd'*32, 'request_key': 'workflow-stable-key'},
            'workflow_submission_manifest_v1')

    def test_import_is_stdlib_only_with_startup_tripwires_in_clean_python(self):
        code = '''
import importlib.abc, sys, socket, subprocess
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, *args):
  if fullname.split('.')[0] in {'app','metadata','torch','psycopg','jsonschema'}:
   raise AssertionError(fullname)
sys.meta_path.insert(0, Guard())
def blocked(*args, **kwargs): raise AssertionError('startup')
class GuardSocket(socket.socket):
 def __new__(cls, *args, **kwargs): return blocked()
socket.socket = GuardSocket
subprocess.Popen = blocked
import tuldok_client
assert 'jsonschema' not in sys.modules
'''
        result = subprocess.run([sys.executable, '-S', '-c', code], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_submission_never_retries_and_explicit_reconcile_keeps_identity(self):
        client = ConsumerFixture()
        workflow = WorkflowClient(client)
        manifest = self.manifest()
        client.failure = AgentAPIError('Lost successful reply', 'transport', 503)
        unknown = workflow.submit(manifest)
        self.assertEqual(unknown['state'], 'unknown')
        self.assertEqual(client.requests, [('runs.submit_external', manifest['arguments'])])
        client.failure = None
        acknowledged = workflow.reconcile(json.loads(json.dumps(unknown)))
        self.assertEqual(acknowledged['state'], 'acknowledged')
        self.assertEqual(client.requests[0], client.requests[1])
        changed = copy.deepcopy(manifest)
        changed['arguments']['request_key'] += '-changed'
        with self.assertRaises(AgentAPIError):
            workflow.submit(changed)
        self.assertEqual(len(client.requests), 2)

    def test_read_budget_refuses_mutation_and_cleans_thread_local_context(self):
        client = AgentClient('http://127.0.0.1:12345', 'x'*32, CATALOG)
        with patch.object(client, '_request') as request:
            with client.read_budget(time.monotonic()+10):
                with self.assertRaises(AgentAPIError):
                    client.call('runs.cancel', {'run_id': RUN})
                with self.assertRaises(AgentAPIError):
                    with client.read_budget(time.monotonic()+10):
                        pass
            request.assert_not_called()
        self.assertIsNone(client._check_read_budget())
        self.assertFalse(any(thread.name == 'agent-read-budget' for thread in threading.enumerate()))

    def test_missing_selected_submission_capability_refuses_without_dispatch(self):
        client = ConsumerFixture(); workflow = WorkflowClient(client)
        client.selected_contracts = lambda: {}
        with self.assertRaises(AgentAPIError) as caught:
            workflow.submit(self.manifest())
        self.assertEqual(caught.exception.code, 'operation_unsupported')
        self.assertEqual(client.requests, [])

    def test_material_digest_uses_domain_utf8_canonical_json_for_unicode(self):
        client = ConsumerFixture(); workflow = WorkflowClient(client)
        material = {'catalog_id': CATALOG, 'note': 'Unicode λ 😀'}
        expected = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
            separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        prepared = {'material': material, 'graph_revision': 1, 'material_sha256': expected}
        client.call = lambda *args: {'status': 200, 'result': prepared}
        manifest = workflow.submission_manifest(RUN, 1, approval_id='d'*32, request_key='unicode-material')
        self.assertEqual(manifest['arguments']['expected_digest'], expected)
        prepared['material']['note'] += 'changed'
        with self.assertRaises(AgentAPIError):
            workflow.submission_manifest(RUN, 1, approval_id='d'*32, request_key='unicode-material')

    def test_5xx_and_negative_reconciliation_preserve_original_unknown_identity(self):
        client = ConsumerFixture(); workflow = WorkflowClient(client)
        client.call = lambda *args: {'status': 503, 'result': {'code': 'commit_unknown', 'error': 'Acknowledgement uncertain'}}
        unknown = workflow.submit(self.manifest())
        self.assertEqual(unknown['state'], 'unknown')
        for status, code in ((401, 'unauthenticated'), (403, 'forbidden'), (409, 'conflict'), (503, 'unavailable')):
            client.call = lambda *args: {'status': status, 'result': {'code': code, 'error': 'Later refusal'}}
            current = workflow.reconcile(unknown)
            self.assertEqual(current['state'], 'unknown')
            self.assertEqual(current['manifest'], unknown['manifest'])
            self.assertEqual(current['error'], unknown['error'])
            self.assertEqual(current['reconciliation']['state'], 'unknown' if status == 503 else 'refused')
        client.call = lambda *args: {'status': 201, 'result': {'id': RUN, 'state': 'queued'}}
        self.assertEqual(workflow.reconcile(unknown)['state'], 'unknown')

    def test_monitor_deadline_and_stop_never_call_cancel_and_restore_transport_budget(self):
        client = ConsumerFixture()
        client.state = 'running'
        workflow = WorkflowClient(client)
        observed = []
        original = client.call
        def call(*args):
            observed.append(client.timeout)
            return original(*args)
        client.call = call
        value = workflow.monitor(RUN, timeout=.03, interval=.01, max_interval=.02)
        self.assertEqual(value['state'], 'deadline')
        self.assertFalse(value['compute_cancel_requested'])
        self.assertTrue(all(0 < budget <= .03 for budget in observed))
        self.assertEqual(client.timeout, 10)
        stop = threading.Event(); stop.set()
        self.assertEqual(workflow.monitor(RUN, cancelled=stop)['state'], 'stopped')
        self.assertTrue(all(operation == 'runs.get' for operation, _ in client.requests))
        for timeout in (float('nan'), float('inf'), 0, -1, True):
            with self.assertRaises(AgentAPIError):
                workflow.monitor(RUN, timeout=timeout)

    def test_cancel_reports_request_without_claiming_drain(self):
        value = WorkflowClient(ConsumerFixture()).cancel(RUN)
        self.assertEqual(value['state'], 'requested')
        self.assertFalse(value['drained'])

    def test_pre_stopped_collection_never_bootstraps_and_retains_prior_item_proofs(self):
        client = ConsumerFixture(); workflow = WorkflowClient(client)
        manifest = workflow.collection_manifest(run_id=RUN, names=['one.bin'])
        stop = threading.Event(); stop.set()
        client.requests.clear()
        fresh = workflow.collect(manifest, '.', cancelled=stop)
        self.assertEqual(fresh['state'], 'stopped')
        self.assertEqual(fresh['items'], [{'name': 'one.bin', 'state': 'outstanding'}])
        self.assertEqual(client.requests, [])
        with tempfile.TemporaryDirectory() as directory:
            receipt = workflow.collect(manifest, directory)
            client.requests.clear()
            stopped = workflow.collect(manifest, directory, resume=receipt, cancelled=stop)
            self.assertEqual(stopped['state'], 'stopped')
            self.assertEqual(stopped['items'], receipt['items'])
            self.assertEqual(client.requests, [])

    def test_interrupted_segments_resume_at_zero_with_whole_hash_and_current_authority(self):
        client = ConsumerFixture()
        workflow = WorkflowClient(client)
        manifest = workflow.collection_manifest(run_id=RUN, names=['two.bin', 'one.bin'])
        self.assertEqual(manifest, workflow.collection_manifest(run_id=RUN, names=['one.bin', 'two.bin']))
        stop = threading.Event()
        client.after_segment = lambda request: stop.set() if request['name'] == 'two.bin' else None
        with tempfile.TemporaryDirectory() as directory:
            first = workflow.collect(manifest, directory, chunk_bytes=4, cancelled=stop)
            self.assertEqual(first['state'], 'stopped')
            self.assertEqual([item['state'] for item in first['items']], ['verified', 'outstanding'])
            self.assertEqual([path.name for path in Path(directory).iterdir()], ['one.bin'])
            self.assertEqual((Path(directory)/'one.bin').stat().st_mode & 0o777, 0o600)
            client.after_segment = None
            client.requests.clear()
            resumed = workflow.collect(manifest, directory, resume=json.loads(json.dumps(first)), chunk_bytes=4)
            self.assertEqual(resumed['state'], 'complete')
            self.assertEqual(client.requests[0][0], 'runs.get')
            parts = [args for op, args in client.requests if op == 'runs.artifact_chunk']
            self.assertEqual(parts[0]['name'], 'one.bin')  # Fresh per-artifact disclosure.
            self.assertEqual(next(part['offset'] for part in parts if part['name'] == 'two.bin'), 0)
            self.assertEqual((Path(directory)/'two.bin').read_bytes(), client.raw)
            self.assertFalse(any(path.name.startswith('.tuldok') for path in Path(directory).iterdir()))

    def test_failure_preserves_success_and_outstanding_without_alternate_dispatch(self):
        client = ConsumerFixture()
        workflow = WorkflowClient(client)
        manifest = workflow.collection_manifest(run_id=RUN, names=['one.bin', 'two.bin'])
        with tempfile.TemporaryDirectory() as directory:
            client.failure = AgentAPIError('Revoked', 'forbidden', 403)
            receipt = workflow.collect(manifest, directory)
            self.assertEqual(receipt['state'], 'partial')
            self.assertEqual(receipt['items'][0]['error']['code'], 'forbidden')
            self.assertEqual(receipt['items'][1]['state'], 'outstanding')
            self.assertEqual(len([op for op, _ in client.requests if op != 'runs.get']), 1)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_hash_mismatch_and_no_clobber_race_keep_partial_typed_and_remove_provisional(self):
        for fault in ('hash', 'race', 'malformed'):
            client = ConsumerFixture(); workflow = WorkflowClient(client)
            manifest = workflow.collection_manifest(run_id=RUN, names=['one.bin'])
            original = client.call
            def call(operation, args):
                envelope = original(operation, args)
                if operation == 'runs.artifact_chunk':
                    if fault == 'hash':
                        envelope['result']['data_base64'] = 'Y2hhbmdlZA=='
                    elif fault == 'malformed':
                        del envelope['result']['offset']
                return envelope
            client.call = call
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)/'one.bin'
                link = os.link
                def race(source, destination, **kwargs):
                    target.write_bytes(b'concurrent work')
                    return link(source, destination, **kwargs)
                with patch('tuldok_client.os.link', side_effect=race if fault == 'race' else link):
                    receipt = workflow.collect(manifest, directory)
                self.assertEqual(receipt['state'], 'partial')
                self.assertEqual(receipt['items'][0]['error']['code'], 'conflict' if fault == 'race' else 'artifact_mismatch')
                if fault == 'race':
                    self.assertEqual(target.read_bytes(), b'concurrent work')
                else:
                    self.assertFalse(target.exists())
                self.assertFalse(any(path.name.startswith('.tuldok') for path in Path(directory).iterdir()))

    def test_resume_rejects_destination_replacement_during_whole_hash_verification(self):
        client = ConsumerFixture(); workflow = WorkflowClient(client)
        manifest = workflow.collection_manifest(run_id=RUN, names=['one.bin'])
        with tempfile.TemporaryDirectory() as directory:
            receipt = workflow.collect(manifest, directory)
            target = Path(directory)/'one.bin'
            read = os.read
            changed = []
            def replace(descriptor, size):
                raw = read(descriptor, size)
                if not changed:
                    replacement = Path(directory)/'replacement'
                    replacement.write_bytes(b'preserved concurrent replacement')
                    replacement.replace(target)
                    changed.append(True)
                return raw
            with patch('tuldok_client.os.read', side_effect=replace):
                resumed = workflow.collect(manifest, directory, resume=receipt)
            self.assertEqual(resumed['state'], 'partial')
            self.assertEqual(resumed['items'][0]['error']['code'], 'artifact_mismatch')
            self.assertEqual(target.read_bytes(), b'preserved concurrent replacement')

    def test_changed_inventory_local_success_and_closed_manifests_refuse(self):
        client = ConsumerFixture(); workflow = WorkflowClient(client)
        manifest = workflow.collection_manifest(run_id=RUN, names=['one.bin'])
        with tempfile.TemporaryDirectory() as directory:
            receipt = workflow.collect(manifest, directory)
            (Path(directory)/'one.bin').write_bytes(b'changed local work')
            resumed = workflow.collect(manifest, directory, resume=receipt)
            self.assertEqual(resumed['items'][0]['error']['code'], 'artifact_mismatch')
            client.raw += b'changed source'
            with self.assertRaises(AgentAPIError) as caught:
                workflow.collect(manifest, directory, resume=receipt)
            self.assertEqual(caught.exception.code, 'stale')
        for changed in (dict(manifest, token='not permitted'), dict(manifest, items=[])):
            with self.assertRaises(AgentAPIError):
                workflow.collect(changed, '.')


if __name__ == '__main__':
    unittest.main()
