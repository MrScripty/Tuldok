"""Whole-cloud/grid validation uses the existing durable graph/run supervisor."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from app import Dataset
import release_validation
import spatial_release
import test_mesh_runs
import test_spatial_release
from workbench import WorkbenchError


class SpatialRuns(unittest.TestCase):
    kind = 'pointcloud'
    setUp = test_spatial_release.SpatialRelease.setUp
    freeze = test_spatial_release.SpatialRelease.freeze
    wait = test_mesh_runs.MeshRuns.wait
    queued = test_mesh_runs.MeshRuns.queued
    test_cancel_during_validation_never_publishes_and_retry_is_fresh = test_mesh_runs.MeshRuns.test_cancel_during_validation_never_publishes_and_retry_is_fresh
    test_interrupted_in_process_work_is_not_replayed = test_mesh_runs.MeshRuns.test_interrupted_in_process_work_is_not_replayed

    def recipe(self):
        self.freeze()
        graph = self.dataset.pipelines.create(dict(name='Spatial integrity', release_id=self.path.stem,
                                                   recipe=release_validation.KINDS[self.kind]))
        validation = self.dataset.pipelines.validate(graph['id'], {'revision': graph['revision']})
        self.assertTrue(validation['valid'], validation)
        return graph, dict(request_key='spatial-request-0001', graph_id=graph['id'], graph_revision=graph['revision'],
                           validation_token=validation['validation_token'])

    def test_both_native_reports_download_custody_and_reopen(self):
        for kind in ('pointcloud', 'volume'):
            self.kind = kind
            with self.subTest(kind=kind), patch('pipeline.subprocess.run', side_effect=AssertionError('No model probe')):
                graph, body = self.recipe()
                body['request_key'] += kind
                run = self.dataset.runs.submit(body)
                result = self.wait(run['id'])
                self.assertEqual(result['state'], 'completed', result)
                self.assertEqual(result['result_kind'], 'release_validation')
                self.assertIsNone(result['metrics'])
                self.assertFalse(result['quality_claim'])
                self.assertEqual(result['parameters'], {})
                raw_report, _ = self.dataset.runs.artifact(run['id'], 'validation-report.json')
                report = json.loads(raw_report)
                self.assertEqual(report['adapter']['id'], release_validation.KINDS[kind])
                archive, _ = self.dataset.runs.artifact(run['id'], 'release.zip')
                self.assertEqual(hashlib.sha256(archive).hexdigest(), self.path.stem)
                self.assertEqual(archive, self.path.read_bytes())
                self.assertEqual(spatial_release.validate_bytes(archive, self.path.stem, kind=kind), report['validation_summary'])
                wrong = copy.deepcopy(graph)
                wrong['recipe'] = release_validation.VOLUME_RECIPE if kind == 'pointcloud' else release_validation.POINTCLOUD_RECIPE
                self.assertFalse(self.dataset.pipelines.validate_graph(wrong)['valid'])
                bad = copy.deepcopy(graph)
                bad['nodes'].append(dict(id='train', type='train', definition_version=1, parameters={}))
                self.assertFalse(self.dataset.pipelines.validate_graph(bad)['valid'])
                reopened = Dataset(self.temporary.name)
                try:
                    self.assertEqual(reopened.runs.get(run['id'])['validation_summary'], report['validation_summary'])
                finally:
                    reopened.close()

    def test_summary_tampering_cannot_be_downloaded_or_projected(self):
        _, body = self.recipe()
        run = self.dataset.runs.submit(body)
        self.assertEqual(self.wait(run['id'])['state'], 'completed')
        path = self.dataset.runs.path / run['id'] / 'validation-report.json'
        raw = path.read_bytes()
        path.write_bytes(raw.replace(b'"point_count":3', b'"point_count":4'))
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.artifact(run['id'], 'validation-report.json')
        self.assertNotIn('validation_summary', self.dataset.runs.list()[0])
