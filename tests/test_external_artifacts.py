"""Bounded artifact copies and real neutral custody, never model qualification."""
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import make_handler
from runs import Runs
from test_external_runs import ExternalCase
from workbench import WorkbenchError


class BoundedCopyTests(unittest.TestCase):
    def test_chunk_bound_same_size_mutation_and_link_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'payload'
            raw = b'01234567' * 32768
            path.write_bytes(raw)
            item = {'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
            directory = os.open(temporary, os.O_RDONLY | os.O_DIRECTORY)
            self.addCleanup(os.close, directory)
            reads = []
            original = os.read
            def read(fd, count):
                reads.append(count)
                return original(fd, count)
            output = io.BytesIO()
            with patch('runs.os.read', side_effect=read):
                Runs._copy_verified(directory, 'payload', item, output)
            self.assertEqual(output.getvalue(), raw)
            self.assertLessEqual(max(reads), 65536)
            class MutatingOutput(io.BytesIO):
                def write(self, value):
                    path.write_bytes(b'x'*len(raw))
                    return super().write(value)
            with self.assertRaises(ValueError):
                Runs._copy_verified(directory, 'payload', item, MutatingOutput())
            path.unlink()
            path.symlink_to('/dev/zero')
            with self.assertRaises(OSError):
                Runs._copy_verified(directory, 'payload', item)
            path.unlink(); os.mkfifo(path)
            with self.assertRaises(ValueError):
                Runs._copy_verified(directory, 'payload', item)


class ExternalArtifactTests(ExternalCase):
    def complete(self):
        with self.owner.bound(self.dataset):
            run = self.dataset.runs.submit_external(self.body())
        self.await_state(run['id'], {'completed'})
        with self.owner.bound(self.dataset):
            return self.dataset.runs._load(run['id'])

    def test_selected_spool_survives_source_mutation_and_releases_capacity(self):
        run = self.complete()
        with self.owner.bound(self.dataset):
            expected, _ = self.dataset.runs.artifact(run['id'], 'result.txt')
            with patch.object(self.dataset.runs, '_large_outputs', return_value=True), patch.object(self.dataset.runs, '_verify_external_artifacts', side_effect=AssertionError('No all-payload scan')):
                with self.dataset.runs.open_artifact(run['id'], 'result.txt') as (stream, metadata):
                    with self.assertRaises(WorkbenchError):
                        with self.dataset.runs.open_artifact(run['id'], 'result.txt'):
                            pass
                    (self.dataset.runs.path/run['id']/'result.txt').write_bytes(b'x'*len(expected))
                    self.assertEqual(stream.read(), expected)
                    self.assertEqual(metadata['sha256'], hashlib.sha256(expected).hexdigest())
                with self.assertRaises(WorkbenchError):
                    with self.dataset.runs.open_artifact(run['id'], 'result.txt'):
                        pass
            # Failure returned the single permit; restore exact bytes for next read.
            (self.dataset.runs.path/run['id']/'result.txt').write_bytes(expected)
            with self.dataset.runs.open_artifact(run['id'], 'result.txt') as (stream, _):
                self.assertEqual(stream.read(), expected)

    def test_capture_bound_before_payload_and_receipt_candidates(self):
        run = self.complete()
        item = run['artifacts'][0]
        with self.owner.bound(self.dataset):
            with patch.object(self.dataset.runs, '_external_bytes', side_effect=AssertionError('Oversize was read')):
                with self.assertRaises(WorkbenchError):
                    self.dataset.runs.capture_artifact(run['id'],item['name'],item['sha256'],max_bytes=1)
            raw, source = self.dataset.runs.capture_artifact(run['id'],item['name'],item['sha256'],max_bytes=4096)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), source['measured_sha256'])
            with patch.object(self.dataset.runs, '_copy_verified', side_effect=AssertionError('Candidates read payload')):
                candidates = self.dataset.runs.input_candidates()
            self.assertEqual(candidates['runs'][0]['status'], 'receipt_verified')
            self.assertEqual(candidates['runs'][0]['artifacts'][0]['artifact_name'], item['name'])
            original = self.dataset.runs._external_inventory
            with patch.object(self.dataset.runs, '_external_inventory', wraps=original), patch.object(self.dataset.runs, '_large_outputs', return_value=True), patch.object(self.dataset.runs, '_verify_external_artifacts', side_effect=AssertionError('Large detail read payload')):
                detail = self.dataset.runs.get(run['id'])
                self.assertEqual(detail['artifact_status'], {'status':'receipt_verified','payloads':'not_checked'})
            (self.dataset.runs.path/run['id']/item['name']).write_bytes(b'x'*len(raw))
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.get(run['id'])  # Historical small-profile complete verification.

    def test_http_stream_exact_bytes_and_no_200_for_tamper(self):
        run = self.complete()
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(self.dataset))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:'+str(server.server_port)
        route = '/api/workspace/runs/'+run['id']+'/artifacts/result.txt'
        with self.owner.bound(self.dataset):
            expected, _ = self.dataset.runs.artifact(run['id'], 'result.txt')
        with urlopen(Request(base+route,headers=self.owner.headers),timeout=10) as response:
            self.assertEqual(int(response.headers['Content-Length']), len(expected))
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(response.read(), expected)
        with urlopen(Request(base+'/api/workspace/run-artifact-inputs',headers=self.owner.headers),timeout=10) as response:
            self.assertEqual(json.load(response)['runs'][0]['run_id'], run['id'])
        with self.assertRaises(HTTPError) as denied:
            urlopen(base+route,timeout=10)
        self.assertEqual(denied.exception.code, 401)
        (self.dataset.runs.path/run['id']/'result.txt').write_bytes(b'x'*len(expected))
        with self.assertRaises(HTTPError) as corrupt:
            urlopen(Request(base+route,headers=self.owner.headers),timeout=10)
        self.assertEqual(corrupt.exception.code, 409)

    def test_spool_disk_failures_do_not_leak_permit_or_change_receipt(self):
        run = self.complete()
        before = (self.dataset.runs.path/run['id']/'artifact-manifest.json').read_bytes()
        with self.owner.bound(self.dataset):
            with patch('runs.tempfile.TemporaryFile', side_effect=OSError('authored disk full')):
                with self.assertRaises(WorkbenchError):
                    with self.dataset.runs.open_artifact(run['id'], 'result.txt'):
                        pass
            with self.dataset.runs.open_artifact(run['id'], 'result.txt') as (stream, metadata):
                self.assertEqual(len(stream.read()), metadata['bytes'])
        self.assertEqual((self.dataset.runs.path/run['id']/'artifact-manifest.json').read_bytes(), before)

    def test_large_admission_capacity_refuses_before_grant_consumption_and_cleans_capture(self):
        # Keep the legacy receipt case independent. The capacity case must bind
        # a complete valid large material/spec, rather than mutating only spec
        # after capture (the admission seam correctly refuses that contradiction).
        body = self.body(approval=self.approve())
        import recipe_contract
        from test_cpu_recipe_contract import CpuRecipeContract
        definition = dict(self.definition, runtime=recipe_contract.CPU_PROFILE,
                          runtime_snapshot_sha256='a'*64,
                          resources={'profile':recipe_contract.LARGE_OUTPUT_PROFILE,
                                     'wall_seconds':10,'max_output_bytes':3500000000})
        raw = json.dumps(definition).encode()
        manifest = dict(self.manifest,id=uuid.uuid4().hex,
                        recipes=[{'id':'neutral','label':'Large capacity contract fixture',
                                  'path':'large-recipe.json','sha256':hashlib.sha256(raw).hexdigest()}])
        (self.project_path/'large-recipe.json').write_bytes(raw)
        (self.project_path/'large-project.json').write_text(json.dumps(manifest))
        descriptor = CpuRecipeContract.descriptor(self)
        # This existing authored descriptor qualifies contract/admission only;
        # there is no installed snapshot, allocation, child or numerical claim.
        with self.owner.bound(self.dataset),patch('runtime_snapshots.RuntimeSnapshots.get',return_value=descriptor):
            self.dataset.projects.open({'root':'fixture','manifest_path':'large-project.json'})
            graph = self.dataset.pipelines.create_external(dict(self.graph_body(),project_id=manifest['id'],
                                                                 expected_sha256=hashlib.sha256(raw).hexdigest()))
            preflight = self.dataset.pipelines.preflight_external(graph['id'],graph['revision'])
            grant = self.dataset.runs.approve_external({'graph_id':graph['id'],'graph_revision':graph['revision'],
                'expected_digest':preflight['material_sha256'],'consumer_actor_id':self.agent['identity']['actor_id']})
        large_body = {'request_key':'capacity-'+uuid.uuid4().hex,'graph_id':graph['id'],'graph_revision':graph['revision'],
                      'expected_digest':preflight['material_sha256'],'approval_id':grant['id']}
        disk = type('Disk', (), {'free':8073741823})()  # one byte under 2D+1GiB
        with self.dataset.access.bind(self.agent['token']), patch('runtime_snapshots.RuntimeSnapshots.get',return_value=descriptor), patch('runs.shutil.disk_usage', return_value=disk) as capacity, patch.object(self.dataset.runs, '_start') as start, patch.object(self.dataset.access, '_consume_external_run', wraps=self.dataset.access._consume_external_run) as consume:
            with self.assertRaises(WorkbenchError) as caught:
                self.dataset.runs.submit_external(large_body)
            self.assertEqual(caught.exception.code, 'unavailable')
            self.assertIn('Insufficient storage for declared outputs',str(caught.exception))
            capacity.assert_called_once_with(self.dataset.runs.path)
            start.assert_not_called()
            consume.assert_not_called()
        with self.owner.bound(self.dataset):
            self.assertEqual(self.dataset.runs.list(), [])
        self.assertEqual(list(self.dataset.runs.path.glob('.external-*')), [])
        # Old profile still admits and exact-key reconciliation does not query
        # capacity or recapture, even when the filesystem reports no free space.
        with patch('runs.shutil.disk_usage', side_effect=AssertionError('Legacy/reconcile checked capacity')):
            admitted = self.queued(body)
            with patch.object(self.dataset.pipelines, 'capture_external', side_effect=AssertionError('Reconciled capture')):
                self.assertEqual(self.queued(body)['id'], admitted['id'])
