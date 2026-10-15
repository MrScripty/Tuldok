"""Actual single-fit producers and independent cold, data-only reconstruction."""
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import re
import zipfile

from test_text_training import TextCase
from test_audio_training import AudioCase
import audio_training
import text_training
import one_fit_evidence as evidence


class OneFitChecks:
    def produce(self, version=2):
        self.output = Path(self.tmp.name) / ('output-' + str(version))
        self.output.mkdir()
        release_id = self.release['id']
        self.job = dict(schema_version=version, dataset_id=self.dataset.db.dataset_id, run_id='a' * 32,
                        graph_sha256='b' * 64, release_id=release_id, release_sha256=release_id,
                        release_path=str(self.release_path), output_dir=str(self.output),
                        parameters=self.parameters, parent_pid=os.getpid())
        if version == 2:
            catalog = self.dataset.db.dataset_id
            self.job.update(adapter=dict(self.training.ADAPTER, version=2), evidence=dict(catalog_id=catalog,
                 material_sha256='c' * 64, model_sha256='d' * 64,
                 task=dict(kind='task', catalog_id=catalog, id=self.task, revision=2, sha256='e' * 64),
                 profile_sha256='f' * 64, selection_policy_sha256='1' * 64, output_policy_sha256='2' * 64))
        path = Path(self.tmp.name) / ('job-' + str(version) + '.json')
        path.write_text(json.dumps(self.job))
        env = dict(os.environ)
        for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[name] = '1'
        result = subprocess.run([os.environ.get('TULDOK_TRAINING_PYTHON', sys.executable),
                    str(Path(self.training.__file__)), '--job', str(path)], capture_output=True, text=True, env=env, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def frozen(self):
        manifest = copy.deepcopy(self.manifest)
        if self.training is text_training:
            manifest['records'] = [dict(row, content_sha256=row['content_hash']) for row in manifest['records']]
            inputs = [row['text'] for row in manifest['records'] if row['split'] == 'validation']
        else:
            with zipfile.ZipFile(self.release_path) as archive:
                inputs = [audio_training.extract_features(archive.read(row['asset']), row['start_frame'], row['end_frame'], row['channel'])
                          for row in manifest['records'] if row['split'] == 'validation']
        return manifest, inputs

    def verify(self):
        return self.training.verify_evidence(self.output, self.job)

    def read(self, name):
        return json.loads((self.output / name).read_bytes())

    def write(self, name, value):
        (self.output / name).write_text(json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')

    def test_actual_fit_has_one_checkpoint_and_no_artificial_curve(self):
        self.produce()
        result = self.verify()
        self.assertEqual(result['format'], 'model_evidence_v1')
        metrics = self.read('metrics.json')
        self.assertNotIn('history', metrics)
        self.assertNotIn('best_epoch', metrics)
        self.assertEqual(metrics['clocks']['fit_pass'], 1)
        self.assertIsNone(metrics['clocks']['epoch'])
        self.assertIsNone(metrics['clocks']['optimizer_update'])
        self.assertIsNone(metrics['clocks']['physical_time'])
        self.assertGreaterEqual(metrics['clocks']['wall_elapsed_ms'], 0)
        index = self.read('checkpoints.json')
        self.assertEqual(len(index['entries']), 1)
        fitted = self.read('fitted-transform.json')
        expected = [row['id'] for row in self.manifest['records'] if row['split'] == 'train']
        self.assertEqual([row['id'] for row in fitted['fit_members']], expected)
        saved = self.read('model.json')
        if self.training is text_training:
            documents = [set(re.findall(r'(?u)\b\w\w+\b', row['text'].lower()))
                         for row in self.manifest['records'] if row['split'] == 'train']
            for token, index in saved['vocabulary'].items():
                count = sum(token in document for document in documents)
                self.assertGreater(count, 0)
                self.assertAlmostEqual(saved['idf'][index], 1 + math.log((1 + len(documents)) / (1 + count)), places=12)
        else:
            import numpy as np
            with zipfile.ZipFile(self.release_path) as archive:
                train = np.array([audio_training.extract_features(archive.read(row['asset']), row['start_frame'], row['end_frame'], row['channel'])
                                  for row in self.manifest['records'] if row['split'] == 'train'])
            np.testing.assert_allclose(saved['mean'], train.mean(axis=0), rtol=1e-12, atol=1e-12)
            expected_scale = train.std(axis=0)
            expected_scale[expected_scale == 0] = 1
            np.testing.assert_allclose(saved['scale'], expected_scale, rtol=1e-12, atol=1e-12)
        outer = self.read('artifact-manifest.json')
        self.assertEqual({row['name'] for row in outer['artifacts']}, evidence.payload_names())
        for item in outer['artifacts']:
            raw = (self.output / item['name']).read_bytes()
            self.assertEqual((hashlib.sha256(raw).hexdigest(), len(raw)), (item['sha256'], item['bytes']))
        # Independent inference in an isolated interpreter: it cannot import
        # either adapter or any live checkout code. Only frozen JSON and a
        # compatible numerical runtime are needed, not the original release.
        _, inputs = self.frozen()
        script = '''
import json, sys
from pathlib import Path
import numpy as np
from scipy.special import expit, logsumexp
m=json.loads(Path(sys.argv[1]).read_bytes()); x=json.loads(sys.argv[2])
if 'vocabulary' in m:
 from sklearn.feature_extraction.text import TfidfVectorizer
 t=m['transform']
 v=TfidfVectorizer(vocabulary=m['vocabulary'], max_features=m['parameters']['max_features'],
   lowercase=t['lowercase'], token_pattern=t['token_pattern'], ngram_range=tuple(t['ngram_range']),
   norm=t['norm'], use_idf=t['use_idf'], smooth_idf=t['smooth_idf'], sublinear_tf=t['sublinear_tf'])
 v.idf_=np.array(m['idf'])
 s=v.transform(x)@np.array(m['feature_log_prob']).T+np.array(m['class_log_prior'])
 p=np.exp(s-logsumexp(s,axis=1)[:,None])
else:
 s=((np.array(x)-np.array(m['mean']))/np.array(m['scale']))@np.array(m['coefficients']).T+np.array(m['intercepts'])
 if s.shape[1]==1:
  q=expit(s[:,0]); p=np.column_stack((1-q,q))
 else:
  p=np.exp(s-logsumexp(s,axis=1)[:,None])
assert 'text_training' not in sys.modules and 'audio_training' not in sys.modules
print(json.dumps(p.tolist()))
'''
        child = subprocess.run([os.environ.get('TULDOK_TRAINING_PYTHON', sys.executable), '-I', '-c', script,
                                str(self.output / 'model.json'), json.dumps(inputs)], cwd=self.tmp.name,
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        import numpy as np
        np.testing.assert_allclose(json.loads(child.stdout), [row['probabilities'] for row in self.read('probes-fit-0001.json')['rows']], rtol=1e-12, atol=1e-12)

    def test_v1_inventory_and_history_remain_unchanged(self):
        self.produce(version=1)
        self.assertFalse((self.output / 'model-evidence.json').exists())
        self.assertEqual(self.read('metrics.json')['best_epoch'], 1)
        self.assertEqual(len(self.read('artifact-manifest.json')['artifacts']), 5)

    def test_checkpoint_clock_and_weights_tampering_rejected(self):
        self.produce()
        checkpoint = self.read('checkpoint-fit-0001.json')
        changed = copy.deepcopy(checkpoint)
        changed['clocks']['epoch'] = 1
        self.write('checkpoint-fit-0001.json', changed)
        with self.assertRaisesRegex(self.training.TrainingError, 'differs'):
            self.verify()
        self.write('checkpoint-fit-0001.json', checkpoint)
        saved = self.read('model.json')
        if self.training is text_training:
            saved['feature_log_prob'][0][0] -= .1
        else:
            saved['intercepts'][0] += .1
        self.write('model.json', saved)
        with self.assertRaisesRegex(self.training.TrainingError, 'binding differs'):
            self.verify()

    def test_frozen_probe_input_and_population_tampering_rejected(self):
        self.produce()
        value = self.read('probe-inputs.json')
        value['inputs'].reverse()
        self.write('probe-inputs.json', value)
        with self.assertRaisesRegex(self.training.TrainingError, 'Probe inputs'):
            self.verify()

    def test_unknown_adapter_refused_before_training(self):
        self.produce()
        bad = copy.deepcopy(self.job)
        bad['adapter']['version'] = 3
        with self.assertRaises(self.training.TrainingError) as caught:
            self.training._checked_job(bad)
        self.assertEqual(caught.exception.outcome, 'unsupported')


class TextEvidenceTests(OneFitChecks, TextCase):
    training = text_training
    task = 'text_classification'
    parameters = dict(max_features=64, alpha=1)


class AudioEvidenceTests(OneFitChecks, AudioCase):
    training = audio_training
    task = 'audio_classification'
    parameters = dict(C=1)
