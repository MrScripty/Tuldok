"""Real HTTP model/template/Study/Run one-fit workflow, with retained evidence."""
import copy
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import time
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

import agent_api
from app import Dataset, make_handler
import audio_training
import text_training
from test_text_training import TextCase
from test_audio_training import AudioCase


class StudyChecks:
    def test_actual_http_study_publishes_one_fit_and_reopens_without_execution(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.dataset))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = 'http://127.0.0.1:' + str(server.server_port)
        def call(operation, arguments):
            version = 3 if operation in ('graphs.create', 'graphs.save') else 1
            method, path, body = agent_api.project_request(operation, arguments, version=version)
            headers = dict(self.actor.headers, Origin=endpoint)
            headers[agent_api.CONTRACT_HEADER] = agent_api.selected_header(operation, version)
            if body is not None:
                headers['Content-Type'] = 'application/json'
            request = Request(endpoint + path, method=method, headers=headers,
                              data=None if body is None else json.dumps(body).encode())
            try:
                response = urlopen(request, timeout=90)
            except HTTPError as error:
                self.fail(operation + ': ' + error.read().decode())
            with response:
                result = json.load(response)
                agent_api.validate_output(operation, dict(status=response.status, result=result), version=version)
                return result
        try:
            definitions = call('recipes.list', {})
            recipe = next(item for item in definitions['recipes'] if item['id'] == self.training.MODEL_RECIPE)
            model = call('models.create', recipe['model_template'])
            published = call('models.publish', dict(model_id=model['id'], revision=model['revision']))
            graph = call('graphs.create', dict(name='Actual one-fit Study', recipe=recipe['id'], release_id=self.release['id']))
            validation = call('graphs.validate', dict(graph_id=graph['id'], revision=graph['revision']))
            self.assertTrue(validation['valid'], validation)
            study = call('studies.create', dict(name='Finite one-fit qualification', policy=validation['selection_policy'],
                   limits=dict(attempt_slots=1, admitted_wall_seconds=1000, retained_bytes=256*1024**2, peak_staging_bytes=512*1024**2)))
            trial = call('studies.prepare_trial', dict(study_id=study['id'], request_key='prepare-one-fit-study', revision=study['revision'],
                  graph_id=graph['id'], graph_revision=graph['revision'], model=published['ref'], replicate=0))
            current = call('studies.get', dict(study_id=study['id']))['study']
            call('studies.continue', dict(study_id=study['id'], request_key='continue-one-fit-study', revision=current['revision'],
                  admission_epoch=current['admission_epoch']))
            current = call('studies.get', dict(study_id=study['id']))['study']
            admitted = call('studies.admit', dict(study_id=study['id'], request_key='admit-one-fit-study', revision=current['revision'],
                        admission_epoch=current['admission_epoch'], trial_id=trial['id']))
            run = admitted['run']
            deadline = time.monotonic() + 120
            while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
                time.sleep(.1)
                run = call('runs.get', dict(run_id=run['id']))
            self.assertEqual(run['state'], 'completed', run.get('error'))
            result = call('runs.model_evidence', dict(run_id=run['id']))
            self.assertEqual(result['state'], 'verified')
            self.assertEqual(len(result['checkpoint_index']['entries']), 1)
            entry = result['checkpoint_index']['entries'][0]
            self.assertEqual(entry['clocks']['fit_pass'], 1)
            self.assertIsNone(entry['clocks']['epoch'])
            self.assertNotIn('history', run['metrics'])
            selected = call('runs.model_evidence', dict(run_id=run['id'], checkpoint_sha256=entry['checkpoint']['sha256']))
            self.assertEqual(selected['predictions']['checkpoint_sha256'], entry['checkpoint']['sha256'])
            self.assertFalse(run['test_exposure']['exposed'])
            server.shutdown(); server.server_close(); thread.join(timeout=5)
            path = self.dataset.path
            self.dataset.close()
            reopened = Dataset(path)
            self.addCleanup(reopened.close)
            original = Path(self.release_path)
            hidden = original.with_suffix('.temporarily-unavailable')
            original.rename(hidden)
            try:
                with self.actor.bound(reopened), patch('subprocess.Popen', side_effect=AssertionError('Evidence query must not execute')):
                    self.assertEqual(reopened.runs.model_evidence(run['id']), result)
                    self.assertEqual(reopened.runs.compare_model_evidence(run['id'], run['id'])['state'], 'compatible')
                    evaluation = next(item['sha256'] for item in run['artifacts'] if item['name'] == 'model-evidence.json')
                    exact = dict(checkpoint_sha256=entry['checkpoint']['sha256'], other_checkpoint_sha256=entry['checkpoint']['sha256'],
                                 evaluation_sha256=evaluation, other_evaluation_sha256=evaluation, metric_id='loss',
                                 metric_definition_sha256=result['metric_definition_hashes']['loss'],
                                 other_metric_definition_sha256=result['metric_definition_hashes']['loss'], mode='paired')
                    compared = reopened.runs.compare_model_evidence(run['id'], run['id'], exact)
                    self.assertEqual(compared['state'], 'compatible')
                    self.assertEqual(compared['delta']['value'], 0)
            finally:
                hidden.rename(original)
        finally:
            if thread.is_alive():
                server.shutdown(); server.server_close(); thread.join(timeout=5)


class TextStudyTests(StudyChecks, TextCase):
    training = text_training


class AudioStudyTests(StudyChecks, AudioCase):
    training = audio_training
