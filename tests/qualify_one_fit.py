"""Real HTTP Study/Run qualification for one-fit text and audio adapters."""
import base64
import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from urllib.request import Request, urlopen

import agent_api
from app import Dataset, make_handler
from auth_helpers import ExplicitOwnerFixture

ROOT = Path(__file__).resolve().parents[1]


def qualify(args):
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    fixture_raw = (args.fixture / (args.task + '.json')).read_bytes()
    fixture = json.loads(fixture_raw)
    expected = dict(format='authored_one_fit_fixture_v1', task=args.task, count=18,
                    generator='canonical_intents_v1' if args.task == 'text' else 'source_channel_tones_v1',
                    purpose='Evidence plumbing only; no accuracy or independence claim')
    if fixture != expected:
        raise ValueError('Fixture differs from the selected authored one-fit source protocol.')
    def save(name, body):
        (output / name).write_text(json.dumps(body, ensure_ascii=True, sort_keys=True, indent=2) + '\n')
    dataset = Dataset(output / 'catalog')
    owner = ExplicitOwnerFixture.bootstrap(dataset)
    rows = []
    generator_sha = None
    with owner.bound(dataset):
        if args.task == 'audio':
            path = ROOT / 'tests/fixtures/workspaces/audio/classification_fixture.py'
            generator_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            spec = importlib.util.spec_from_file_location('authored_audio_source', path)
            source = importlib.util.module_from_spec(spec); spec.loader.exec_module(source)
        for index in range(18):
            if args.task == 'text':
                label = 'schedule' if index % 2 else 'cancel'
                text = ('Arrange meeting schedule tomorrow' if index % 2 else 'Cancel appointment reservation tomorrow') + f' authoredmarker{index} cafe\u0301\r\n'
                row = dataset.workbench.import_asset(dict(kind='text', text=text, name=f'Authored text {index}',
                         groups=[f'authored-text-{index}'], parents=[], rights='Authored mathematical contract fixture.'))
                task, annotation = 'text_classification', {'label': label}
            else:
                row = dataset.workbench.audio.admit(dict(wav=base64.b64encode(source.wav(index)).decode(),
                         name=f'Authored tone {index}', groups=[f'authored-audio-{index}'], rights='CC0 authored mathematical PCM contract fixture.'))
                task, annotation = 'audio_timed', {'segments': [source.segment(index)]}
            rows.append(dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
                         task=task, annotation=annotation, groups=row['groups'], review='human_reviewed')))
        body = dict(format=args.task + '_classification_v1', items=[{key:row[key] for key in ('id','revision','source_revision')} for row in rows],
                    ratios=dict(train=50, validation=25, test=25), seed=42)
        for seed in range(42, 100):
            body['seed'] = seed
            preview = dataset.releases.preview(body)
            if preview['eligible']: break
        if not preview['eligible']: raise ValueError(str(preview['blockers']))
        release = dataset.releases.create(dict(body, preview_token=preview['preview_token']))
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(dataset))
    endpoint = 'http://127.0.0.1:' + str(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    calls = []
    def call(operation, arguments):
        version = 3 if operation in ('graphs.create', 'graphs.save') else 1
        method, path, body = agent_api.project_request(operation, arguments, version=version)
        headers = dict(owner.headers, Origin=endpoint)
        headers[agent_api.CONTRACT_HEADER] = agent_api.selected_header(operation, version)
        if body is not None: headers['Content-Type'] = 'application/json'
        request = Request(endpoint + path, method=method, headers=headers, data=None if body is None else json.dumps(body).encode())
        with urlopen(request, timeout=120) as response:
            value = json.load(response)
            agent_api.validate_output(operation, dict(status=response.status, result=value), version=version)
            calls.append(dict(operation=operation, version=version, status=response.status))
            return value
    started = time.monotonic()
    try:
        definition = next(item for item in call('recipes.list', {})['recipes'] if item['id'] == args.task + '_classification_model_v2')
        model = call('models.create', definition['model_template'])
        material = call('models.publish', dict(model_id=model['id'], revision=model['revision']))
        graph = call('graphs.create', dict(name='Actual one-fit qualification', release_id=release['id'], recipe=definition['id']))
        validation = call('graphs.validate', dict(graph_id=graph['id'], revision=graph['revision']))
        study = call('studies.create', dict(name='Finite one-fit qualification', policy=validation['selection_policy'],
                     limits=dict(attempt_slots=1, admitted_wall_seconds=1000, retained_bytes=256*1024**2, peak_staging_bytes=512*1024**2)))
        trial = call('studies.prepare_trial', dict(study_id=study['id'], request_key='prepare-one-fit-qualification', revision=study['revision'],
                     graph_id=graph['id'], graph_revision=graph['revision'], model=material['ref'], replicate=0))
        current = call('studies.get', dict(study_id=study['id']))['study']
        call('studies.continue', dict(study_id=study['id'], request_key='continue-one-fit-qualification', revision=current['revision'], admission_epoch=current['admission_epoch']))
        current = call('studies.get', dict(study_id=study['id']))['study']
        admitted = call('studies.admit', dict(study_id=study['id'], request_key='admit-one-fit-qualification', revision=current['revision'],
                        admission_epoch=current['admission_epoch'], trial_id=trial['id']))
        run = admitted['run']; deadline = time.monotonic() + 180
        while run['state'] in ('queued', 'running', 'cancelling') and time.monotonic() < deadline:
            time.sleep(.15); run = call('runs.get', dict(run_id=run['id']))
        if run['state'] != 'completed': raise ValueError('Actual one-fit Run failed: ' + str(run.get('error')))
        evidence = call('runs.model_evidence', dict(run_id=run['id']))
        entries = evidence['checkpoint_index']['entries']
        if len(entries) != 1 or entries[0]['clocks']['fit_pass'] != 1 or entries[0]['clocks']['epoch'] is not None or 'history' in run['metrics']:
            raise ValueError('One-fit evidence invented a curve or clock.')
        checkpoint = call('runs.model_evidence', dict(run_id=run['id'], checkpoint_sha256=entries[0]['checkpoint']['sha256']))
        save('run.json', run); save('evidence.json', evidence); save('checkpoint.json', checkpoint); save('trial.json', trial)
        with owner.bound(dataset):
            private = dataset.runs._load(run['id'])
            source = dataset.runs.path / run['id']
            cold = output / 'independent'; cold.mkdir(mode=0o700)
            for name in ('model.json', 'probe-inputs.json'):
                shutil.copyfile(source / name, cold / name)
        oracle_source = args.fixture / 'one_fit_inference.py'
        oracle_raw = oracle_source.read_bytes(); (cold / 'infer.py').write_bytes(oracle_raw)
        replay = subprocess.run([os.environ['TULDOK_TRAINING_PYTHON'], '-I', str(cold / 'infer.py'), str(cold / 'model.json'),
                                 str(cold / 'probe-inputs.json')], cwd=cold, capture_output=True, text=True, timeout=60)
        if replay.returncode: raise ValueError('Independent JSON reconstruction failed: ' + replay.stderr)
        import numpy as np
        actual = np.array(json.loads(replay.stdout)); expected_values = np.array([row['probabilities'] for row in checkpoint['predictions']['rows']])
        np.testing.assert_allclose(actual, expected_values, rtol=1e-12, atol=1e-12)
        server.shutdown(); server.server_close(); thread.join(timeout=5); dataset.close()
        dataset = Dataset(output / 'catalog')
        with owner.bound(dataset):
            if dataset.runs.model_evidence(run['id']) != evidence: raise ValueError('Cold evidence reopen changed.')
        receipt = dict(task=args.task, source_fixture_sha256=hashlib.sha256(fixture_raw).hexdigest(), source_generator_sha256=generator_sha,
             independent_oracle_sha256=hashlib.sha256(oracle_raw).hexdigest(), run_id=run['id'], study_id=study['id'], trial_id=trial['id'],
             checkpoints=1, clocks=entries[0]['clocks'], fabricated_curve=False, probe_members=len(evidence['probe']['members']),
             retained_bytes=sum(item['bytes'] for item in run['artifacts']), wall_elapsed_seconds=time.monotonic()-started,
             peak_rss_bytes=run['metrics']['runtime']['peak_rss_bytes'], runtime=run['runtime']['runtime'],
             actual_training=True, actual_http_study=True, cold_reopen=True, independent_fixed_inference=True,
             independent_maximum_error=float(np.max(np.abs(actual-expected_values))), http_operations=calls,
             limitations=['Authored fixtures qualify evidence plumbing, not generalization.', 'UI qualification is separate.',
                          'No generic inference-package claim; scientific physical qualification is separate.'])
        save('receipt.json', receipt)
        return receipt
    finally:
        if thread.is_alive(): server.shutdown(); server.server_close(); thread.join(timeout=5)
        dataset.close()
