"""Real frozen WAV classification, exact coordinates and durable run contract."""
import base64
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest
import uuid
import zipfile
from unittest.mock import patch

from app import Dataset
from workbench import WorkbenchError, encode
import audio_training as training

spec = importlib.util.spec_from_file_location('audio_classification_fixture', Path(__file__).parent / 'fixtures/workspaces/audio/classification_fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class AudioCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='workspace-audio-classification-')
        self.addCleanup(self.tmp.cleanup)
        self.dataset = Dataset(self.tmp.name)
        self.addCleanup(lambda: self.dataset.close())
        self.rows, self.originals = [], {}
        for index in range(18):
            raw = fixture.wav(index)
            row = self.dataset.workbench.audio.admit(dict(wav=base64.b64encode(raw).decode(),
                name=f'Authored tone {index}', groups=[f'authored-audio-{index}'],
                rights='CC0 authored mathematical PCM; no quality or independence claim.'))
            row = self.dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
                task='audio_timed', annotation={'segments': [fixture.segment(index)]}, groups=row['groups'], review='human_reviewed'))
            self.rows.append(row); self.originals[row['id']] = raw
        self.body = dict(format='audio_classification_v1',
            items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in self.rows],
            ratios={'train': 50, 'validation': 25, 'test': 25}, seed=42)
        for seed in range(42, 100):
            self.body['seed'] = seed
            preview = self.dataset.releases.preview(self.body)
            if preview['eligible']:
                break
        self.assertTrue(preview['eligible'], preview['blockers'])
        self.release = self.dataset.releases.create(dict(self.body, preview_token=preview['preview_token']))
        self.release_path = self.dataset.releases.locate(self.release['id'])
        with zipfile.ZipFile(self.release_path) as archive:
            self.members = {name: archive.read(name) for name in archive.namelist()}
        self.manifest = json.loads(self.members['manifest.json'])
        self.graph = self.dataset.pipelines.create(dict(name='Authored audio baseline', recipe='audio_classification', release_id=self.release['id']))

    def altered(self, mutate=None, members_mutate=None):
        value, members = copy.deepcopy(self.manifest), dict(self.members)
        if mutate: mutate(value)
        members['manifest.json'] = encode(value).encode()
        for split in ('train', 'validation', 'test'):
            members[split + '/records.jsonl'] = ''.join(encode(row) + '\n' for row in value['records'] if row['split'] == split).encode()
        if members_mutate: members_mutate(members)
        path = Path(self.tmp.name) / (uuid.uuid4().hex + '.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, contents in members.items(): archive.writestr(name, contents)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def submit(self, key):
        validation = self.dataset.pipelines.validate(self.graph['id'], {'revision': self.graph['revision']})
        self.assertTrue(validation['valid'], validation)
        body = dict(request_key=key, graph_id=self.graph['id'], graph_revision=self.graph['revision'],
                    validation_token=validation['validation_token'])
        return self.dataset.runs.submit(body), body

    def await_state(self, run_id, states=('completed', 'failed', 'unknown')):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            value = self.dataset.runs.get(run_id)
            if value['state'] in states:
                return value
            time.sleep(.03)
        self.fail('Audio run did not reach a terminal state.')


class AudioReleaseTests(AudioCase):
    def test_originals_and_source_coordinates_survive_real_release(self):
        value = training.inspect_release(self.release_path, self.release['id'])
        self.assertEqual(value, self.manifest)
        for row in value['records']:
            self.assertEqual(self.members[row['asset']], self.originals[row['id']])
            self.assertEqual(row['start_frame'], 256); self.assertEqual(row['end_frame'], 1280)
            self.assertEqual(row['target_label'], row['annotation']['segments'][0]['label'])
        self.assertEqual(self.dataset.pipelines.inspect_release(self.release['id'])['recipe'], 'audio_classification')

    def test_source_coordinate_hash_and_family_tampering_is_refused(self):
        for field, bad in [('start_frame', 255), ('channel', True), ('sample_rate_hz', 16000),
                           ('asset_sha256', '0' * 64), ('pcm_sha256', '0' * 64), ('audio_family_sha256', '0' * 64)]:
            with self.subTest(field=field), self.assertRaises(training.TrainingError):
                training.inspect_release(*self.altered(lambda value: value['records'][0].update({field: bad})))
        def cross(value):
            a = next(r for r in value['records'] if r['split'] == 'train')
            b = next(r for r in value['records'] if r['split'] == 'test')
            value['protected_components'][a['export_group']][0]['parents'].append('f' * 32)
            value['protected_components'][b['export_group']][0]['parents'].append('f' * 32)
        with self.assertRaisesRegex(training.TrainingError, 'bridge crosses'):
            training.inspect_release(*self.altered(cross))

    def test_draft_multiple_intervals_and_transcript_only_remain_ineligible(self):
        for mutate in (lambda r: r.update(review='draft'),
                       lambda r: r['annotation']['segments'].append(dict(r['annotation']['segments'][0], end_frame=1500)),
                       lambda r: r['annotation']['segments'][0].update(label='', transcript='Human words')):
            with self.subTest(mutate=mutate), self.assertRaises(training.TrainingError):
                training.inspect_release(*self.altered(lambda v: mutate(v['records'][0])))

    def test_unsafe_archive_and_jsonl_mapping_are_refused(self):
        for mutation in (lambda m: m.update({'../outside': b'x'}),
                         lambda m: m.update({'validation/records.jsonl': b''}),
                         lambda m: m.update({self.manifest['records'][0]['asset']: b'not WAV'})):
            with self.subTest(mutation=mutation), self.assertRaises(training.TrainingError):
                training.inspect_release(*self.altered(members_mutate=mutation))

    def test_editable_graph_runtime_and_missing_runtime_refusal(self):
        self.assertEqual(self.graph['edges'][1]['output'], 'audio_export')
        edited = copy.deepcopy(self.graph); edited['nodes'][2]['parameters']['C'] = .5
        saved = self.dataset.pipelines.save(edited['id'], {'revision': 1, 'document': edited})
        result = self.dataset.pipelines.validate(saved['id'], {'revision': 2})
        self.assertTrue(result['valid'], result)
        self.assertEqual(result['release']['records'], 18)
        self.assertEqual(result['release']['audio_summary']['analyzed_frames'], 18 * 1024)
        from unittest.mock import patch
        with patch.dict('os.environ', {'TULDOK_TRAINING_PYTHON': '/missing/audio-python'}):
            unavailable = self.dataset.pipelines.validate(saved['id'], {'revision': 2})
            self.assertFalse(unavailable['valid']); self.assertEqual(unavailable['status'], 'unavailable')
            with self.assertRaises(WorkbenchError):
                self.dataset.runs.submit(dict(request_key='audio-runtime-refused', graph_id=saved['id'], graph_revision=2, validation_token=result['validation_token']))
        self.assertEqual(self.dataset.runs.list(), [])


class AudioNumericTests(unittest.TestCase):
    def test_independent_analytic_pcm_features_and_interval_boundaries(self):
        # No FFT implementation is used by this oracle. These exact sequences
        # have analytic spectra: silence, DC, Nyquist and an exact quarter band.
        script = '''import audio_training as t,io,wave,struct,json
def features(samples, channel=0, start=0, end=None):
 b=io.BytesIO()
 with wave.open(b,'wb') as w:
  w.setparams((2,2,8000,0,'NONE','not compressed'))
  w.writeframes(b''.join(struct.pack('<hh',*p) for p in samples))
 return t.extract_features(b.getvalue(),start,len(samples) if end is None else end,channel)
zero=[(0,0)]*128
dc=[(16384,-8192)]*128
alternating=[(16384 if i%2==0 else -16384,0) for i in range(128)]
quarter=[([0,16384,0,-16384][i%4],0) for i in range(128)]
framed=[(30000,30000)]*16+dc+[(30000,30000)]*16
odd_impulse=[(16384,0)]+[(0,0)]*128
print(json.dumps([features(zero),features(dc),features(alternating),features(quarter),features(framed,1,16,144),features(odd_impulse)]))
'''
        from pipeline import training_environment
        values = json.loads(subprocess.check_output([os.environ['TULDOK_TRAINING_PYTHON'], '-c', script], env=training_environment()))
        expected = [[0] * 8, [.5, .5, 0, 0, 1, 0, 0, 0],
                    [0, .5, 1, 1, 0, 0, 0, 1],
                    [0, math.sqrt(.125), 63 / 127, .5, 0, 0, 1, 0],
                    [-.25, .25, 0, 0, 1, 0, 0, 0],
                    [.5/129, .5/math.sqrt(129), 0, 64/129, 17/65, 16/65, 16/65, 16/65]]
        for actual, oracle in zip(values, expected, strict=True):
            for value, reference in zip(actual, oracle, strict=True):
                self.assertAlmostEqual(value, reference, places=12)


class AudioExecutionTests(AudioCase):
    def test_path_replaced_after_verification_cannot_replace_training_samples(self):
        output = Path(self.tmp.name) / 'captured-output'; output.mkdir()
        checked_path = Path(self.tmp.name) / 'replaceable.zip'
        checked_path.write_bytes(self.release_path.read_bytes())
        job = dict(schema_version=1,dataset_id=self.dataset.db.dataset_id,run_id='c'*32,graph_sha256='d'*64,
            release_id=self.release['id'],release_sha256=self.release['id'],release_path=str(checked_path),
            output_dir=str(output),parameters={'C':1},parent_pid=os.getpid())
        # This is an actual trainer, with a bounded boundary hook only. A second
        # path read would see valid ZIP/WAV structure containing zero samples.
        script = '''import io,json,sys,zipfile,wave
from pathlib import Path
import audio_training as t
job=json.loads(sys.argv[1]);original=t.probe_runtime
def replace_after_verification():
 with zipfile.ZipFile(job['release_path']) as z:
  members={name:z.read(name) for name in z.namelist()}
 for name,data in list(members.items()):
  if name.endswith('.wav'):
   with wave.open(io.BytesIO(data)) as r:params=r.getparams()
   b=io.BytesIO()
   with wave.open(b,'wb') as w:
    w.setparams(params);w.writeframes(b'\\0'*(params.nframes*params.nchannels*params.sampwidth))
   members[name]=b.getvalue()
 with zipfile.ZipFile(job['release_path'],'w') as z:
  for name,data in members.items():z.writestr(name,data)
 return original()
t.probe_runtime=replace_after_verification
t.train(job)
'''
        from pipeline import training_environment
        subprocess.check_output([os.environ['TULDOK_TRAINING_PYTHON'],'-c',script,json.dumps(job)],env=training_environment(),timeout=30)
        self.assertNotEqual(hashlib.sha256(checked_path.read_bytes()).hexdigest(),self.release['id'])
        model=json.loads((output/'model.json').read_text())
        self.assertEqual(model['source_identity']['release_sha256'],self.release['id'])
        self.assertGreater(model['mean'][1],.15)
        self.assertTrue((output/'artifact-manifest.json').is_file())

    def test_nonconvergent_fit_has_no_published_model_or_artifact_manifest(self):
        output = Path(self.tmp.name) / 'nonconvergent-output'; output.mkdir()
        job = dict(schema_version=1,dataset_id=self.dataset.db.dataset_id,run_id='a'*32,graph_sha256='b'*64,
            release_id=self.release['id'],release_sha256=self.release['id'],release_path=str(self.release_path),
            output_dir=str(output),parameters={'C':.5},parent_pid=os.getpid())
        script = '''import json,sys,warnings,audio_training as t
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
original=LogisticRegression.fit
def fail_candidate(self,*args,**kwargs):
 if self.C==.5: warnings.warn('Injected real estimator nonconvergence',ConvergenceWarning)
 return original(self,*args,**kwargs)
LogisticRegression.fit=fail_candidate
try:t.train(json.loads(sys.argv[1]))
except t.TrainingError as error:print(json.dumps({'outcome':error.outcome,'message':str(error)}))
'''
        from pipeline import training_environment
        lines = subprocess.check_output([os.environ['TULDOK_TRAINING_PYTHON'],'-c',script,json.dumps(job)],env=training_environment()).splitlines()
        error = json.loads(lines[-1])
        self.assertEqual(error['outcome'],'failed');self.assertIn('did not converge',error['message'])
        self.assertEqual(list(output.iterdir()),[])

    def test_multiclass_json_reader_matches_actual_three_class_fit(self):
        revised = []
        for index, row in enumerate(self.rows):
            annotation = copy.deepcopy(row['annotation'])
            annotation['segments'][0]['label'] = 'class-' + str(index % 3)
            revised.append(self.dataset.workbench.save(row['id'], dict(revision=row['revision'], source_revision=row['source_revision'],
                task='audio_timed', annotation=annotation, groups=row['groups'], review='human_reviewed')))
        body = dict(self.body, items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in revised])
        for seed in range(100):
            body['seed'] = seed
            preview = self.dataset.releases.preview(body)
            if preview['eligible']: break
        self.assertTrue(preview['eligible'], preview)
        release = self.dataset.releases.create(dict(body, preview_token=preview['preview_token']))
        self.graph = self.dataset.pipelines.create(dict(name='Three-class audio', recipe='audio_classification', release_id=release['id']))
        run, _ = self.submit('audio-three-class-001')
        result = self.await_state(run['id'])
        self.assertEqual(result['state'], 'completed', result)
        model = json.loads(self.dataset.runs.artifact(run['id'], 'model.json')[0])
        self.assertEqual(len(model['coefficients']), 3)
        self.assertTrue(all(len(row['probabilities']) == 3 for row in self.dataset.runs.predictions(run['id'])['rows']))

    def test_real_fit_train_only_json_results_correction_exposure_and_reopen(self):
        run, body = self.submit('audio-real-fit-001')
        self.assertEqual(self.dataset.runs.submit(body)['id'], run['id'])
        result = self.await_state(run['id'])
        self.assertEqual(result['state'], 'completed', result)
        model = json.loads(self.dataset.runs.artifact(run['id'], 'model.json')[0])
        predictions = self.dataset.runs.predictions(run['id'])
        self.assertTrue(predictions['rows'])
        self.assertEqual(model['transform']['fit_scope'], 'train')
        # Independently recover the train mean and binary probabilities using
        # scalar PCM/DFT, without sklearn, NumPy or the production feature reader.
        def scalar_features(row):
            import io, wave, cmath
            with wave.open(io.BytesIO(self.members[row['asset']])) as reader:
                pairs = list(struct.iter_unpack('<hh', reader.readframes(reader.getnframes())))
            x = [pair[row['channel']] / 32768 for pair in pairs[row['start_frame']:row['end_frame']]]
            n = len(x)
            power = [abs(sum(value * cmath.exp(-2j * math.pi * k * i / n) for i, value in enumerate(x))) ** 2 for k in range(n // 2 + 1)]
            frequencies = [2 * k / n for k in range(len(power))]
            total = sum(power)
            return [sum(x) / n, math.sqrt(sum(v*v for v in x) / n), sum((a<0)!=(b<0) for a,b in zip(x,x[1:]))/(n-1),
                    sum(f*p for f,p in zip(frequencies,power))/total if total else 0,
                    *[sum(p for f,p in zip(frequencies,power) if low<=f and (f<high or high==1 and f<=1))/total if total else 0
                      for low,high in zip([0,.25,.5,.75],[.25,.5,.75,1])]]
        train = [row for row in self.manifest['records'] if row['split'] == 'train']
        features = [scalar_features(row) for row in train]
        for index, mean in enumerate(model['mean']):
            self.assertAlmostEqual(mean, sum(row[index] for row in features)/len(features), places=10)
        source = next(row for row in self.manifest['records'] if row['id'] == predictions['rows'][0]['id'])
        x = scalar_features(source)
        score = sum((v-m)/s*w for v,m,s,w in zip(x,model['mean'],model['scale'],model['coefficients'][0]))+model['intercepts'][0]
        positive = 1/(1+math.exp(-score))
        self.assertAlmostEqual(predictions['rows'][0]['probabilities'][1],positive,places=9)
        self.assertEqual({key: predictions['rows'][0][key] for key in training.REFERENCE_KEYS}, {key: source[key] for key in training.REFERENCE_KEYS})
        with self.assertRaises(WorkbenchError): self.dataset.runs.artifact(run['id'], 'test-metrics.json')
        self.dataset.runs.expose_test(run['id'], {'reason': 'Authored acceptance exposure; not fresh holdout.'})
        current = self.dataset.workbench.get(source['id'])
        annotation = copy.deepcopy(current['annotation']); annotation['segments'][0]['label'] = 'corrected draft'
        self.dataset.workbench.save(current['id'], dict(revision=current['revision'],source_revision=current['source_revision'],
            task='audio_timed',annotation=annotation,groups=current['groups'],review='draft'))
        old_bytes = self.release_path.read_bytes()
        self.dataset.close(); self.dataset = Dataset(self.tmp.name)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'], 'completed')
        reopened = self.dataset.runs.predictions(run['id'])
        self.assertEqual(reopened['rows'][0]['frozen_reference'],predictions['rows'][0]['frozen_reference'])
        self.assertTrue(reopened['rows'][0]['current_record']['changed'])
        self.assertEqual(old_bytes,self.release_path.read_bytes())
        # Another RIFF wrapper/interval for exposed PCM keeps exposure visible.
        exposed = next(row for row in self.manifest['records'] if row['split']=='test')
        raw = self.originals[exposed['id']]
        chunk = b'JUNK'+struct.pack('<I',4)+b'test'
        wrapped = raw[:4]+struct.pack('<I',len(raw)+len(chunk)-8)+raw[8:12]+chunk+raw[12:]
        imported = self.dataset.workbench.audio.admit(dict(wav=base64.b64encode(wrapped).decode(),name='Same PCM changed RIFF',groups=[],rights='Authored test wrapper'))
        projected = dict(exposed,id=imported['id'],content_hash=imported['content_hash'],source_sha256=imported['source_sha256'])
        self.assertTrue(self.dataset.pipelines.exposures([projected])['exposed'])
        self.assertNotEqual(imported['content_hash'],exposed['content_hash'])
        for field,value in [('scale',[0]*8),('coefficients',[[float('nan')]*8])]:
            with self.assertRaises(training.TrainingError): training.validate_model(dict(model,**{field:value}))
        artifact = self.dataset.runs.path / run['id'] / 'model.json'
        artifact.write_bytes(artifact.read_bytes()+b' ')
        with self.assertRaisesRegex(WorkbenchError,'hash'): self.dataset.runs.get(run['id'])

    def test_actual_worker_cancel_drains_and_explicit_retry_is_fresh(self):
        run,_ = self.submit('audio-real-cancel-001')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            with self.dataset.lock:
                worker=self.dataset.runs._load(run['id']).get('worker')
            if worker:break
            time.sleep(.005)
        self.assertTrue(worker,'Actual audio child never started')
        self.dataset.runs.cancel(run['id'])
        stopped=self.await_state(run['id'],('cancelled','failed','unknown'))
        self.assertEqual(stopped['state'],'cancelled',stopped)
        from runs import process_status
        self.assertEqual(process_status(worker),'ceased');self.assertEqual(stopped['artifacts'],[])
        retried=self.dataset.runs.retry(run['id'],{'request_key':'audio-real-retry-001'})
        self.assertNotEqual(run['id'],retried['id']);self.assertEqual(retried['attempt'],2)
        self.assertEqual(self.await_state(retried['id'])['state'],'completed')

    def test_reopen_interrupted_queue_never_replays(self):
        with patch.object(self.dataset.runs,'_start'):
            run,_=self.submit('audio-interrupted-001')
        # Abrupt catalog-connection loss, without the graceful close that
        # deliberately cancels pending work. No worker was ever started.
        self.dataset.db.close();self.dataset=Dataset(self.tmp.name)
        self.assertEqual(self.dataset.runs.get(run['id'])['state'],'interrupted')
        self.assertEqual(len(self.dataset.runs.list()),1)
        self.assertIsNone(self.dataset.runs._thread)

    def test_actual_supervisor_death_drains_audio_child_and_requires_restart(self):
        self.dataset.close()
        code = '''import json,os,sys,time
from app import Dataset
d=Dataset(sys.argv[1]);g=d.pipelines.get(sys.argv[2])
v=d.pipelines.validate(g['id'],{'revision':g['revision']})
assert v['valid'],v
r=d.runs.submit(dict(request_key='audio-parent-death-001',graph_id=g['id'],graph_revision=g['revision'],validation_token=v['validation_token']))
deadline=time.monotonic()+20
while time.monotonic()<deadline:
 with d.lock:
  r=d.runs._load(r['id'])
 if r['worker']:
  print(json.dumps({'run_id':r['id'],'worker':r['worker']}),flush=True)
  os._exit(0)
 time.sleep(.002)
raise RuntimeError('Audio child never became owned')
'''
        import sys
        evidence = json.loads(subprocess.check_output([sys.executable, '-c', code, self.tmp.name, self.graph['id']], timeout=35))
        from runs import process_status
        deadline = time.monotonic() + 10
        while process_status(evidence['worker']) != 'ceased' and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(process_status(evidence['worker']), 'ceased')
        self.dataset = Dataset(self.tmp.name)
        result = self.dataset.runs.get(evidence['run_id'])
        self.assertEqual(result['state'], 'interrupted', result)
        self.assertEqual(result['artifacts'], [])
        self.assertIsNone(self.dataset.runs._thread)
        retry = self.dataset.runs.retry(result['id'], {'request_key': 'audio-parent-death-restart-001'})
        self.assertEqual(retry['parent_run_id'], result['id'])
        self.assertEqual(self.await_state(retry['id'])['state'], 'completed')
