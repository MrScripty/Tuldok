"""Actual retained Rheon producer bytes through real graph/run/export custody."""
from auth_helpers import bind_owner
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
import zipfile

from app import Dataset
import release_validation
import sequence_release
import test_mesh_runs
import test_sequence_release
from pipeline import execution_digest
from workbench import WorkbenchError


class SequenceRuns(unittest.TestCase):
    setUp = test_sequence_release.SequenceRelease.setUp
    freeze = test_sequence_release.SequenceRelease.freeze
    wait = test_mesh_runs.MeshRuns.wait
    queued = test_mesh_runs.MeshRuns.queued
    test_cancel_during_validation_never_publishes_and_retry_is_fresh = test_mesh_runs.MeshRuns.test_cancel_during_validation_never_publishes_and_retry_is_fresh
    test_interrupted_in_process_work_is_not_replayed = test_mesh_runs.MeshRuns.test_interrupted_in_process_work_is_not_replayed
    test_imported_definition_mismatch_blocks_admission = test_mesh_runs.MeshRuns.test_imported_definition_mismatch_blocks_admission

    def recipe(self):
        self.freeze()
        graph = self.dataset.pipelines.create({'name': 'Sequence integrity', 'release_id': self.path.stem,
                                               'recipe': release_validation.SEQUENCE_RECIPE})
        validation = self.dataset.pipelines.validate(graph['id'], {'revision': graph['revision']})
        self.assertTrue(validation['valid'], validation)
        self.assertEqual(validation['runtime']['adapter']['id'], release_validation.SEQUENCE_RECIPE)
        return graph, {'request_key': 'sequence-request-0001', 'graph_id': graph['id'],
                       'graph_revision': graph['revision'], 'validation_token': validation['validation_token']}

    def test_actual_sequence_report_source_bits_units_times_and_reopen(self):
        with patch('pipeline.subprocess.run', side_effect=AssertionError('No training probe')):
            graph, body = self.recipe()
            self.assertEqual([node['type'] for node in graph['nodes']], ['release', 'validate', 'publish'])
            run = self.dataset.runs.submit(body)
            result = self.wait(run['id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertIsNone(result['metrics'])
        self.assertFalse(result['quality_claim'])
        self.assertEqual(result['parameters'], {})
        raw_report, _ = self.dataset.runs.artifact(run['id'], 'validation-report.json')
        report = json.loads(raw_report)
        self.assertEqual(report['adapter']['id'], release_validation.SEQUENCE_RECIPE)
        self.assertEqual(report['source_identity']['graph_sha256'], execution_digest(graph))
        summary = report['validation_summary']
        self.assertEqual((summary['sequence_count'], summary['frame_count']), (1, 9))
        row = summary['sequences'][0]
        self.assertEqual(row['geometry']['counts'], [16, 8, 4])
        self.assertEqual(row['units']['time'], 's')
        self.assertEqual([frame['time_s'] for frame in row['frame_index']], [i / 16 for i in range(9)])
        self.assertEqual(row['run_sha256'], hashlib.sha256(self.sources[0]).hexdigest())
        self.assertEqual(row['frames_sha256'], hashlib.sha256(self.sources[1]).hexdigest())
        raw, _ = self.dataset.runs.artifact(run['id'], 'release.zip')
        self.assertEqual(raw, self.path.read_bytes())
        self.assertEqual(sequence_release.validate_bytes(raw, self.path.stem), summary)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            with zipfile.ZipFile(io.BytesIO(archive.read(manifest['records'][0]['asset']))) as bundle:
                self.assertEqual([bundle.read(name) for name in ('run.json', 'frames.jsonl')], self.sources)
        self.assertEqual(self.dataset.runs.submit(body)['id'], run['id'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.predictions(run['id'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.expose_test(run['id'], {'reason': 'No model evaluation'})
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_exposures').fetchone()[0], 0)
        self.dataset.close()
        self.dataset = Dataset(self.temporary.name); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        self.assertEqual(self.dataset.runs.get(run['id'])['validation_summary'], summary)
        self.assertEqual(self.dataset.runs.artifact(run['id'], 'validation-report.json')[0], raw_report)

    def test_mesh_recipe_cannot_accept_sequence_and_stale_graph_token_rejected(self):
        graph, body = self.recipe()
        wrong = copy.deepcopy(graph)
        wrong['recipe'] = release_validation.RECIPE
        self.assertFalse(self.dataset.pipelines.validate_graph(wrong)['valid'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(dict(body, validation_token='0' * 64))
        wrong = copy.deepcopy(graph)
        wrong['nodes'].append({'id': 'train', 'type': 'train', 'definition_version': 1, 'parameters': {}})
        self.assertFalse(self.dataset.pipelines.validate_graph(wrong)['valid'])
        edited = copy.deepcopy(graph)
        edited['name'] = 'Changed sequence'
        self.dataset.pipelines.save(graph['id'], {'revision': 1, 'document': edited})
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(body)

    def test_report_adapter_and_frame_summary_tampering_rejected(self):
        _, body = self.recipe()
        run = self.dataset.runs.submit(body)
        self.assertEqual(self.wait(run['id'])['state'], 'completed')
        path = self.dataset.runs.path / run['id'] / 'validation-report.json'
        original = path.read_bytes()
        for corrupted in (original.replace(b'"frame_count":9', b'"frame_count":8'),
                          original.replace(b'sequence_validate_export', b'mesh_validate_export')):
            path.write_bytes(corrupted)
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.artifact(run['id'], 'validation-report.json')
            self.assertNotIn('validation_summary', self.dataset.runs.list()[0])
        path.write_bytes(original)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'completed')
