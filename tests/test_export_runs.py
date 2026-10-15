"""Actual PostgreSQL classification exports run without a training interpreter."""
from auth_helpers import bind_owner, execute_admitted
import copy
import hashlib
import json
import os
import time
from unittest.mock import patch

from app import Dataset
import release_validation
from pipeline import execution_digest
from test_pipeline import WorkspaceCase
from test_text_training import TextCase
from test_audio_training import AudioCase
from workbench import WorkbenchError


class ExportRunChecks:
    def recipe(self):
        pipelines = self.dataset.pipelines
        release_id = self.release['id']
        summary = pipelines.inspect_release(release_id)
        self.assertEqual(summary['recipe'], self.kind + '_classification')
        allowed_recipes = [self.kind + '_classification', self.kind + '_validate_export']
        if self.kind == 'image':
            allowed_recipes.append('image_classification_model_v2')
        self.assertEqual(summary['allowed_recipes'], allowed_recipes)
        original_digest = execution_digest(self.graph)
        graph = pipelines.create(dict(name='Export integrity', release_id=release_id, recipe=self.kind + '_validate_export'))
        self.assertEqual(execution_digest(pipelines.get(self.graph['id'])), original_digest)
        self.assertEqual([node['type'] for node in graph['nodes']], ['release', 'validate', 'publish'])
        clone = pipelines.clone(graph['id'], {'name': 'Editable export recipe'})
        clone['layout'] = {'validate': {'x': 120, 'y': 80}}
        graph = pipelines.save(clone['id'], {'revision': 1, 'document': clone})
        validation = pipelines.validate(graph['id'], {'revision': graph['revision']})
        self.assertTrue(validation['valid'], validation)
        self.assertEqual(validation['release']['recipe'], self.kind + '_validate_export')
        return graph, dict(request_key=self.kind + '-export-run-0001', graph_id=graph['id'],
                          graph_revision=graph['revision'], validation_token=validation['validation_token'])

    def wait(self, run_id):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            result = self.dataset.runs.get(run_id)
            if result['state'] not in ('queued', 'running', 'cancelling'):
                return result
            time.sleep(.02)
        self.fail('Export run did not complete.')

    def test_real_export_without_training_runtime_and_reopen(self):
        with patch.dict(os.environ, TULDOK_TRAINING_PYTHON='/does/not/exist'), \
                patch('pipeline.subprocess.run', side_effect=AssertionError('No model probe')), \
                patch('runs.subprocess.Popen', side_effect=AssertionError('No model worker')):
            graph, body = self.recipe()
            run = self.dataset.runs.submit(body)
            result = self.wait(run['id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['result_kind'], 'release_validation')
        self.assertIsNone(result['metrics'])
        self.assertFalse(result['quality_claim'])
        self.assertEqual(result['parameters'], {})
        self.assertEqual({a['name'] for a in result['artifacts']}, {'validation-report.json', 'artifact-manifest.json'})
        report = json.loads(self.dataset.runs.artifact(run['id'], 'validation-report.json')[0])
        self.assertEqual(report['adapter']['id'], self.kind + '_validate_export')
        self.assertEqual(report['validation_summary']['record_count'], len(self.rows))
        self.assertEqual(report['source_identity']['graph_sha256'], execution_digest(graph))
        raw, _ = self.dataset.runs.artifact(run['id'], 'release.zip')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.release['id'])
        self.assertEqual(raw, self.dataset.releases.locate(self.release['id']).read_bytes())
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.predictions(run['id'])
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.expose_test(run['id'], {'reason': 'No model exists'})
        self.assertEqual(self.dataset.db.execute('SELECT count(*) FROM workspace_exposures').fetchone()[0], 0)
        self.dataset.close()
        self.dataset = Dataset(self.tmp.name); self.actor = bind_owner(self, self.dataset)
        self.assertEqual(self.dataset.runs.get(run['id'])['artifacts'], result['artifacts'])
        self.assertEqual(json.loads(self.dataset.runs.artifact(run['id'], 'validation-report.json')[0]), report)

    def test_stale_graph_wrong_recipe_connection_and_changed_release(self):
        graph, body = self.recipe()
        wrong = copy.deepcopy(graph)
        wrong['recipe'] = 'text_validate_export' if self.kind != 'text' else 'image_validate_export'
        self.assertFalse(self.dataset.pipelines.validate_graph(wrong)['valid'])
        broken = copy.deepcopy(graph)
        broken['edges'].pop()
        self.assertFalse(self.dataset.pipelines.validate_graph(broken)['valid'])
        graph['name'] = 'Edited after validation'
        self.dataset.pipelines.save(graph['id'], dict(revision=graph['revision'], document=graph))
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(body)
        path = self.dataset.releases.locate(self.release['id'])
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaises(WorkbenchError):
            self.dataset.pipelines.inspect_release(self.release['id'], recipe=self.kind + '_validate_export')

    def test_changed_source_after_admission_and_stale_definitions_do_not_publish(self):
        graph, body = self.recipe()
        with self.assertRaises(WorkbenchError):
            self.dataset.runs.submit(dict(body, validation_token='0' * 64))
        with patch.object(release_validation, 'IMPORTED_DEFINITION_FILES', {}):
            validation = self.dataset.pipelines.validate_graph(graph)
        self.assertFalse(validation['valid'])
        self.assertEqual(validation['status'], 'stale')
        with patch.object(self.dataset.runs, '_start'):
            run = self.dataset.runs.submit(body)
        path = self.dataset.releases.locate(self.release['id'])
        path.write_bytes(path.read_bytes() + b'changed-after-admission')
        execute_admitted(self.dataset, run['id'])
        result = self.dataset.runs.get(run['id'])
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['artifacts'], [])
        self.assertFalse((self.dataset.runs.path / run['id']).exists())

    def test_cancel_during_read_then_retry_fresh(self):
        _, body = self.recipe()
        with patch.object(self.dataset.runs, '_start'):
            run = self.dataset.runs.submit(body)
        inspect = self.dataset.pipelines.inspect_release
        def cancel_after_read(*args, **kwargs):
            result = inspect(*args, **kwargs)
            with self.actor.bound(self.dataset):
                self.dataset.runs.cancel(run['id'])
            return result
        with patch.object(self.dataset.pipelines, 'inspect_release', side_effect=cancel_after_read):
            execute_admitted(self.dataset, run['id'])
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'cancelled')
        self.assertFalse((self.dataset.runs.path / run['id']).exists())
        retry = self.dataset.runs.retry(run['id'], {'request_key': self.kind + '-export-retry-0001'})
        self.assertEqual(self.wait(retry['id'])['state'], 'completed')
        self.assertEqual(retry['attempt'], 2)


class ImageExportRuns(ExportRunChecks, WorkspaceCase):
    kind = 'image'


class TextExportRuns(ExportRunChecks, TextCase):
    kind = 'text'


class AudioExportRuns(ExportRunChecks, AudioCase):
    kind = 'audio'
