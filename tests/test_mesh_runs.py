"""Real mesh recipe admission, report custody and local supervisor lifecycle."""
from auth_helpers import bind_owner, execute_admitted
import copy
import hashlib
import json
import time
import unittest
from unittest.mock import patch

from app import Dataset
from pipeline import execution_digest
import release_validation
import test_mesh_release
from workbench import WorkbenchError


class MeshRuns(unittest.TestCase):
    setUp = test_mesh_release.MeshRelease.setUp
    freeze = test_mesh_release.MeshRelease.freeze

    def recipe(self):
        self.freeze()
        pipelines = self.dataset.pipelines
        graph = pipelines.create({'name': 'Mesh integrity', 'release_id': self.path.stem,
                                  'recipe': release_validation.RECIPE})
        validation = pipelines.validate(graph['id'], {'revision': graph['revision']})
        self.assertTrue(validation['valid'], validation)
        return graph, {'request_key': 'mesh-request-0001', 'graph_id': graph['id'],
                       'graph_revision': graph['revision'], 'validation_token': validation['validation_token']}

    def wait(self, run_id):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            result = self.dataset.runs.get(run_id)
            if result['state'] not in ('queued', 'running', 'cancelling'):
                return result
            time.sleep(.02)
        self.fail('Mesh run did not finish.')

    def queued(self, body):
        with patch.object(self.dataset.runs, '_start'):
            return self.dataset.runs.submit(body)

    def test_actual_three_stage_run_and_durable_download(self):
        with patch('pipeline.subprocess.run', side_effect=AssertionError('No training probe')):
            graph, body = self.recipe()
            self.assertEqual([node['type'] for node in graph['nodes']], ['release', 'validate', 'publish'])
            run = self.dataset.runs.submit(body)
            result = self.wait(run['id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['result_kind'], 'release_validation')
        self.assertIsNone(result['metrics'])
        self.assertEqual(result['parameters'], {})
        self.assertFalse(result['quality_claim'])
        self.assertEqual({item['name'] for item in result['artifacts']}, {'validation-report.json', 'artifact-manifest.json'})
        report, media = self.dataset.runs.artifact(run['id'], 'validation-report.json')
        report = json.loads(report)
        self.assertEqual(media, 'application/json')
        self.assertEqual(report['validation_summary']['vertex_count'], 6)
        self.assertEqual(report['validation_summary']['triangle_count'], 8)
        self.assertEqual(report['source_identity']['graph_sha256'], execution_digest(graph))
        raw, _ = self.dataset.runs.artifact(run['id'], 'release.zip')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.path.stem)
        self.assertEqual(raw, self.path.read_bytes())
        self.assertEqual(self.dataset.runs.submit(body)['id'], run['id'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.predictions(run['id'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.expose_test(run['id'], {'reason': 'Not applicable'})
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_exposures').fetchone()[0], 0)
        self.dataset.close()
        self.dataset = Dataset(self.temporary.name); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        self.assertEqual(self.dataset.runs.get(run['id'])['artifacts'], result['artifacts'])
        self.assertEqual(json.loads(self.dataset.runs.artifact(run['id'], 'validation-report.json')[0]), report)

    def test_stale_graph_release_and_wrong_shape_are_rejected(self):
        graph, body = self.recipe()
        edited = copy.deepcopy(graph)
        edited['nodes'].append({'id': 'train', 'type': 'train', 'definition_version': 1, 'parameters': {}})
        self.assertFalse(self.dataset.pipelines.validate_graph(edited)['valid'])
        edited = copy.deepcopy(graph)
        edited['name'] = 'Changed'
        self.dataset.pipelines.save(graph['id'], {'revision': 1, 'document': edited})
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(body)
        self.path.write_bytes(self.path.read_bytes() + b'changed')
        with self.assertRaises(WorkbenchError):
            self.dataset.pipelines.inspect_release(self.path.stem)

    def test_cancel_during_validation_never_publishes_and_retry_is_fresh(self):
        _, body = self.recipe()
        run = self.queued(body)
        inspect = self.dataset.pipelines.inspect_release
        def cancel_after_inspect(*args, **kwargs):
            result = inspect(*args, **kwargs)
            with self.actor.bound(self.dataset):
                self.dataset.runs.cancel(run['id'])
            return result
        with patch.object(self.dataset.pipelines, 'inspect_release', side_effect=cancel_after_inspect):
            execute_admitted(self.dataset, run['id'])
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'cancelled')
        self.assertFalse((self.dataset.runs.path / run['id']).exists())
        retry = self.dataset.runs.retry(run['id'], {'request_key': 'mesh-retry-0001'})
        self.assertEqual(self.wait(retry['id'])['state'], 'completed')
        self.assertEqual(retry['attempt'], 2)

    def test_interrupted_in_process_work_is_not_replayed(self):
        _, body = self.recipe()
        run = self.queued(body)
        with self.dataset.lock, self.dataset.db.transaction():
            stored = self.dataset.runs._load(run['id'])
            stored['state'] = 'running'
            self.dataset.runs._save(stored)
        self.dataset.close()
        self.dataset = Dataset(self.temporary.name); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'interrupted')
        self.assertFalse((self.dataset.runs.path / run['id']).exists())

    def test_tampered_report_and_symlink_are_unavailable(self):
        _, body = self.recipe()
        run = self.dataset.runs.submit(body)
        self.assertEqual(self.wait(run['id'])['state'], 'completed')
        path = self.dataset.runs.path / run['id'] / 'validation-report.json'
        original = path.read_bytes()
        path.write_bytes(original.replace(b'"triangle_count":8', b'"triangle_count":9'))
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.artifact(run['id'], 'validation-report.json')
        self.assertNotIn('validation_summary', self.dataset.runs.list()[0])
        path.unlink()
        target = self.dataset.path / 'copied-report.json'
        target.write_bytes(original)
        path.symlink_to(target)
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.get(run['id'])

    def test_stale_definition_fails_without_publication(self):
        _, body = self.recipe()
        run = self.queued(body)
        probe = self.dataset.pipelines.probe(release_validation.RECIPE)
        probe['adapter_definition_sha256'] = '0' * 64
        with patch.object(self.dataset.pipelines, 'probe', return_value=probe):
            execute_admitted(self.dataset, run['id'])
        result = self.dataset.runs.get(run['id'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error']['code'], 'stale')
        self.assertFalse((self.dataset.runs.path / run['id']).exists())

    def test_imported_definition_mismatch_blocks_admission(self):
        graph, _ = self.recipe()
        with patch.object(release_validation, 'IMPORTED_DEFINITION_FILES', {}):
            validation = self.dataset.pipelines.validate_graph(graph)
        self.assertFalse(validation['valid'])
        self.assertEqual(validation['errors'][0]['code'], 'stale')
        self.assertFalse(validation['runtime']['available'])

    def test_wrong_token_and_mixed_canonical_release_are_rejected(self):
        _, body = self.recipe()
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(dict(body, validation_token='0' * 64))
        raw = test_mesh_release.rewrite(self.path.read_bytes(), lambda entries:
            test_mesh_release.change_manifest(entries, lambda manifest:
                manifest['records'][0].update(kind='audio')))
        path = self.path.with_name(hashlib.sha256(raw).hexdigest() + '.zip')
        path.write_bytes(raw)
        with self.assertRaises(WorkbenchError) as caught:
            self.dataset.pipelines.inspect_release(path.stem)
        self.assertEqual(caught.exception.code, 'unsupported')
