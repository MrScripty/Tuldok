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
import unittest
import zipfile

from test_text_training import TextCase
from test_audio_training import AudioCase
import audio_training
import text_training
import one_fit_evidence as evidence


class ContractIsolationTests(unittest.TestCase):
    def test_editing_template_projection_cannot_change_the_task_transform(self):
        for adapter in (text_training, audio_training):
            parameters = {name: rule['default'] for name, rule in adapter.PARAMETER_BOUNDS.items()}
            owner = evidence.contract(adapter)
            original = copy.deepcopy(adapter.TRANSFORM)
            projected = owner.model_definition(parameters)
            projected['preprocessing_policy']['fit_scope'] = 'validation'
            projected['output_policy']['class_order'] = 'reversed'
            self.assertEqual(adapter.TRANSFORM, original)
            self.assertEqual(owner.model_definition(parameters)['preprocessing_policy'], original)
            self.assertEqual(owner.OUTPUT_POLICY['class_order'], 'frozen_vocabulary')

    def test_source_stat_oracle_matches_pinned_vectorizer_frequency_cap(self):
        documents = [' '.join('token' + str(index) for index in range(150)),
                     ' '.join('token' + str(index) for index in range(75, 200))]
        vectorizer = text_training._vectorizer(64)
        vectorizer.fit_transform(documents)
        model = dict(parameters=dict(max_features=64, alpha=1), vocabulary={key:int(value) for key,value in vectorizer.vocabulary_.items()},
                     idf=vectorizer.idf_.tolist())
        text_training._verify_fit_statistics(model, documents)
        import numpy as np
        model['idf'][0] = float(np.nextafter(model['idf'][0], np.inf))
        with self.assertRaises(text_training.TrainingError):
            text_training._verify_fit_statistics(model, documents)

    def test_source_stat_oracle_matches_near_constant_population_scaling(self):
        import numpy as np
        from sklearn.preprocessing import StandardScaler
        features = np.array([[.5 + row*1e-16, 0, row*.01, .1, .2, .3, .4, .5] for row in range(4)])
        scaler = StandardScaler().fit(features)
        model = dict(mean=scaler.mean_.tolist(), scale=scaler.scale_.tolist())
        audio_training._verify_fit_statistics(model, features)
        model['mean'][0] = float(np.nextafter(model['mean'][0], np.inf))
        with self.assertRaises(audio_training.TrainingError):
            audio_training._verify_fit_statistics(model, features)


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
            owner = evidence.contract(self.training)
            profile = owner.profile(catalog, 'd' * 64, self.parameters,
                                    sum(row['split'] == 'validation' for row in self.manifest['records']))
            self.job.update(adapter=dict(self.training.ADAPTER, version=2), evidence=dict(catalog_id=catalog,
                 material_sha256='c' * 64, adapter_sha256='e'*64, model_sha256='d' * 64,
                 task=owner.task_ref(catalog), profile_sha256=evidence.digest(profile),
                 selection_policy_sha256=evidence.digest(profile['probe_selection']), output_policy_sha256=evidence.digest(evidence.OUTPUT_POLICY)))
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
        cold = Path(self.tmp.name) / 'independent'
        cold.mkdir()
        oracle = Path(__file__).parent / 'fixtures/model_development/one_fit_inference.py'
        (cold / 'infer.py').write_bytes(oracle.read_bytes())
        (cold / 'model.json').write_bytes((self.output / 'model.json').read_bytes())
        (cold / 'inputs.json').write_text(json.dumps({'inputs': inputs}))
        child = subprocess.run([os.environ.get('TULDOK_TRAINING_PYTHON', sys.executable), '-I', str(cold / 'infer.py'),
                                str(cold / 'model.json'), str(cold / 'inputs.json')], cwd=cold,
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
        # Rebind the exact new bytes so the oracle isolates the boolean clock,
        # rather than accidentally testing a stale hash at an earlier boundary.
        original_index = self.read('checkpoints.json')
        original_manifest = self.read('model-evidence.json')
        changed = copy.deepcopy(checkpoint)
        changed['clocks']['fit_pass'] = True
        self.write('checkpoint-fit-0001.json', changed)
        index = copy.deepcopy(original_index)
        index['entries'][0]['checkpoint'] = evidence._ref(self.output / 'checkpoint-fit-0001.json')
        self.write('checkpoints.json', index)
        manifest = copy.deepcopy(original_manifest)
        manifest['checkpoints'] = evidence._ref(self.output / 'checkpoints.json')
        self.write('model-evidence.json', manifest)
        with self.assertRaisesRegex(self.training.TrainingError, 'descriptor/index binding'):
            self.verify()
        self.write('checkpoint-fit-0001.json', checkpoint)
        self.write('checkpoints.json', original_index)
        self.write('model-evidence.json', original_manifest)
        invalid_blob = copy.deepcopy(original_manifest)
        invalid_blob['checkpoints']['bytes'] = float(invalid_blob['checkpoints']['bytes'])
        self.write('model-evidence.json', invalid_blob)
        with self.assertRaisesRegex(self.training.TrainingError, 'blob differs'):
            self.verify()
        self.write('model-evidence.json', original_manifest)
        original_metrics = self.read('metrics.json')
        invalid_metrics = copy.deepcopy(original_metrics)
        invalid_metrics['clocks']['fit_pass'] = True
        self.write('metrics.json', invalid_metrics)
        with self.assertRaisesRegex(self.training.TrainingError, 'artificial training curve'):
            self.verify()
        self.write('metrics.json', original_metrics)
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
        for changes in ('catalog', 'task'):
            bad = copy.deepcopy(self.job)
            if changes == 'catalog':
                bad['evidence']['catalog_id'] = '0'*32
                bad['evidence']['task']['catalog_id'] = '0'*32
            else:
                bad['evidence']['task']['sha256'] = '0'*64
            with self.subTest(changes=changes), self.assertRaises(self.training.TrainingError) as caught:
                self.training._checked_job(bad)
            self.assertEqual(caught.exception.outcome, 'invalid')

    def test_initial_worker_verifier_rejects_self_consistent_wrong_fit_statistics(self):
        self.produce()
        saved = self.read('model.json')
        if self.training is text_training:
            saved['idf'][0] += .01
        else:
            saved['mean'][0] += .01
        self.write('model.json', saved)
        # Rebuild all evidence from the altered state and its new predictions.
        # This leaves fit-member IDs honest while falsifying their statistics.
        manifest, inputs = self.frozen()
        if self.training is text_training:
            scores = self.training.predict_model(saved, inputs)
        else:
            import numpy as np
            scores = np.array(self.training.predict_features(saved, inputs))
        from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss
        sources = [row for row in manifest['records'] if row['split'] == 'validation']
        truth = [row['class_index'] for row in sources]
        predicted = scores.argmax(axis=1)
        labels = list(range(len(saved['class_vocabulary'])))
        validation = dict(split='validation', examples=len(sources), loss=float(log_loss(truth, scores, labels=labels)),
                accuracy=float(accuracy_score(truth, predicted)), macro_f1=float(f1_score(truth, predicted, labels=labels, average='macro', zero_division=0)),
                confusion_matrix=confusion_matrix(truth, predicted, labels=labels).tolist())
        rows = [dict(truth_index=row['class_index'], predicted_index=int(index), probabilities=probability.tolist())
                for row, index, probability in zip(sources, predicted, scores, strict=True)]
        metrics = self.read('metrics.json')
        metrics['validation'] = validation
        self.write('metrics.json', metrics)
        for name in evidence.CAPTURE_NAMES:
            (self.output / name).unlink()
        evidence.capture(self.output, job=self.job, adapter=self.training.ADAPTER, manifest=manifest,
                         reference_keys=self.training.REFERENCE_KEYS, saved=saved, inputs=inputs, validation=validation, rows=rows, clocks=metrics['clocks'])
        # Plain reconstruction/cross-file checks succeed: only source-owned
        # numerical verification of the declared training population rejects it.
        evidence.verify_directory(self.output, job=self.job, adapter=self.training.ADAPTER, manifest=manifest,
                                  reference_keys=self.training.REFERENCE_KEYS, expected_inputs=inputs)
        with self.assertRaisesRegex(self.training.TrainingError, 'training-only statistics'):
            self.verify()


class TextEvidenceTests(OneFitChecks, TextCase):
    training = text_training
    task = 'text_classification'
    parameters = dict(max_features=64, alpha=1)


class AudioEvidenceTests(OneFitChecks, AudioCase):
    training = audio_training
    task = 'audio_classification'
    parameters = dict(C=1)
