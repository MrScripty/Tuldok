"""Real frozen-release decoder and optional pinned CPU subprocess evidence.

TULDOK_TRAINING_PYTHON selects the separately installed runtime. The real epoch
test is skipped explicitly when absent; the M2 qualification job must set it.
"""
from auth_helpers import bind_owner
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures'))
from app import Dataset
from image_classification_fixture import populate
import image_training as training

ROOT = Path(__file__).resolve().parents[1]


class ParameterAndRuntimeTests(unittest.TestCase):
    def test_closed_numeric_parameters_and_boundaries(self):
        good = {key: rule['default'] for key, rule in training.PARAMETER_BOUNDS.items()}
        self.assertEqual(training.validate_parameters(good), good)
        for key, rule in training.PARAMETER_BOUNDS.items():
            for edge in (rule['minimum'], rule['maximum']):
                self.assertEqual(training.validate_parameters(dict(good, **{key: edge}))[key], edge)
            for bad in (True, '1', None, rule['minimum'] - 1, rule['maximum'] + 1, 10**1000):
                with self.subTest(key=key, value=str(bad)[:20]), self.assertRaises(training.TrainingError) as caught:
                    training.validate_parameters(dict(good, **{key: bad}))
                self.assertEqual(caught.exception.outcome, 'invalid')
                self.assertTrue(str(caught.exception).startswith(key + ' must be '))
        for bad in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(training.TrainingError):
                training.validate_parameters(dict(good, learning_rate=bad))
        with self.assertRaisesRegex(training.TrainingError, 'exactly'):
            training.validate_parameters(dict(good, backbone='mobilenet'))

    def test_probe_reports_missing_runtime_without_installation_or_torch_import(self):
        result = subprocess.run([sys.executable, '-S', str(ROOT / 'image_training.py'), '--probe'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2, result.stderr)
        probe = json.loads(result.stdout)
        self.assertFalse(probe['available'])
        self.assertTrue(any('torch==2.8.0+cpu' in item['message'] for item in probe['problems']))
        self.assertEqual(result.stderr, '')

    def test_pure_module_does_not_import_torch(self):
        result = subprocess.run([sys.executable, '-S', '-c',
                                 'import image_training,sys; assert "torch" not in sys.modules'],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_job_rejects_unknown_fields_and_wrong_parent_before_training(self):
        value = dict(schema_version=1, dataset_id='1' * 32, run_id='2' * 32,
                     graph_sha256='3' * 64, release_id='4' * 64, release_sha256='4' * 64,
                     release_path='/tmp/release.zip', output_dir='/tmp/output', parent_pid=os.getpid(),
                     parameters={key: rule['default'] for key, rule in training.PARAMETER_BOUNDS.items()})
        self.assertEqual(training._checked_job(value), value)
        for bad in (dict(value, command='echo'), dict(value, release_sha256='5' * 64),
                    dict(value, schema_version=True), dict(value, run_id='../escape')):
            with self.assertRaises(training.TrainingError):
                training._checked_job(bad)
        with patch('image_training.ctypes.CDLL') as library, patch('image_training.os.getppid', return_value=100):
            library.return_value.prctl.return_value = 0
            with self.assertRaisesRegex(training.TrainingError, 'owning training process has already changed'):
                training.guard_parent(200)
            library.return_value.prctl.assert_called_once()

    def test_cli_rejects_duplicate_job_json_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / 'job.json'
            job.write_text('{"schema_version":1,"schema_version":2}')
            result = subprocess.run([sys.executable, str(ROOT / 'image_training.py'), '--job', str(job)],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout), {'schema_version': 1, 'event': 'failed',
                         'outcome': 'invalid', 'message': 'Training job contains duplicate fields.'})


class FrozenReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='image-training-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dataset = Dataset(self.root / 'data'); self.actor = bind_owner(self, self.dataset)
        self.addCleanup(self.dataset.close)
        self.records = populate(self.dataset)
        request = dict(format='image_classification_v1', seed=42,
                       ratios={'train': 34, 'validation': 33, 'test': 33},
                       items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in self.records])
        preview = self.dataset.releases.preview(request)
        self.assertTrue(preview['eligible'], preview)
        release = self.dataset.releases.create(dict(request, preview_token=preview['preview_token']))
        self.release_id = release['id']
        self.release_path = self.dataset.releases.locate(self.release_id)
        with zipfile.ZipFile(self.release_path) as source:
            self.members = {info.filename: source.read(info) for info in source.infolist()}
        self.manifest = json.loads(self.members['manifest.json'])

    def altered(self, mutate_manifest=None, mutate_members=None):
        members = dict(self.members)
        manifest = json.loads(members['manifest.json'])
        if mutate_manifest:
            mutate_manifest(manifest)
        members['manifest.json'] = json.dumps(manifest, ensure_ascii=True).encode()
        if mutate_members:
            mutate_members(members)
        path = self.root / 'altered.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, raw in members.items():
                archive.writestr(name, raw)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def assert_rejected(self, message, mutate_manifest=None, mutate_members=None):
        path, digest = self.altered(mutate_manifest, mutate_members)
        with self.assertRaises(training.TrainingError) as caught:
            training.inspect_release(path, digest)
        self.assertEqual(caught.exception.outcome, 'invalid')
        self.assertEqual(str(caught.exception), message)

    def test_real_release_decoder_preserves_unsafe_unicode_labels_and_all_refs(self):
        result = training.inspect_release(self.release_path, self.release_id)
        self.assertEqual(result, self.manifest)
        self.assertEqual({row['id'] for row in result['records']}, {row['id'] for row in self.records})
        self.assertEqual(len(result['records']), 6)
        self.assertNotIn('torch', sys.modules)

    def test_release_bytes_are_hash_verified_before_zip_decoding(self):
        with self.assertRaisesRegex(training.TrainingError, 'SHA-256 does not match'):
            training.inspect_release(self.release_path, '0' * 64)

    def test_zip_traversal_and_undeclared_files_are_refused(self):
        self.assert_rejected('Frozen release contains an unsafe ZIP entry.',
                             mutate_members=lambda values: values.update({'../escape': b'x'}))
        self.assert_rejected('Frozen release contains undeclared or missing files.',
                             mutate_members=lambda values: values.update({'extra.txt': b'x'}))

    def test_duplicate_zip_members_are_refused(self):
        import warnings
        path = self.root / 'duplicate.zip'
        with warnings.catch_warnings(), zipfile.ZipFile(path, 'w') as archive:
            warnings.simplefilter('ignore', UserWarning)
            for name, raw in self.members.items():
                archive.writestr(name, raw)
            archive.writestr('README.txt', b'duplicate')
        with self.assertRaisesRegex(training.TrainingError, 'duplicate or too many ZIP entries'):
            training.inspect_release(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_record_review_and_revision_remain_frozen_requirements(self):
        self.assert_rejected('Every frozen image requires human-reviewed classification.',
                             lambda value: value['records'][0].update(review='draft'))
        self.assert_rejected('Frozen record revisions must be positive integers.',
                             lambda value: value['records'][0].update(revision=True))

    def test_index_boolean_and_asset_bytes_cannot_masquerade_as_valid(self):
        self.assert_rejected('Frozen class vocabulary is invalid.',
                             lambda value: value['class_vocabulary'][0].update(index=False))
        asset = self.manifest['records'][0]['asset']
        self.assert_rejected('Frozen image asset SHA-256 does not match its manifest.',
                             mutate_members=lambda values: values.update({asset: values[asset] + b'changed'}))
        self.assert_rejected('Frozen decoded pixels or dimensions do not match their manifest.',
                             lambda value: value['records'][0].update(pixel_hash='0' * 64, exported_pixel_sha256='0' * 64))

    def test_class_coverage_and_resource_limits_are_enforced(self):
        removed = self.manifest['records'][-1]
        def remove(value):
            value['records'] = value['records'][:-1]
        # Record floor is itself actionable; no silent dropping or reassignment.
        self.assert_rejected('Training requires 6–128 frozen image records.', remove,
                             lambda values: values.pop(removed['asset']))
        with patch('image_training.MAX_ZIP_BYTES', 20):
            with self.assertRaisesRegex(training.TrainingError, '40 MiB training limit'):
                training.inspect_release(self.release_path, self.release_id)
        with patch('image_training.MAX_EXPANDED_BYTES', 20):
            with self.assertRaisesRegex(training.TrainingError, '64 MiB expanded limit'):
                training.inspect_release(self.release_path, self.release_id)
        with patch('image_training.MAX_IMAGE_PIXELS', 10):
            with self.assertRaisesRegex(training.TrainingError, 'single PNG dimension/pixel limits'):
                training.inspect_release(self.release_path, self.release_id)

    def test_missing_one_class_in_a_split_is_not_silently_reassigned(self):
        row = next(record for record in self.manifest['records']
                   if record['split'] == 'train' and record['class_index'] == 0)
        destination = f'train/class_000001/{row["id"]}.png'
        def reclassify(value):
            target = next(record for record in value['records'] if record['id'] == row['id'])
            target.update(class_index=1, class_folder='class_000001',
                annotation={'label': value['class_vocabulary'][1]['label']}, asset=destination)
        def move(values):
            values[destination] = values.pop(row['asset'])
        self.assert_rejected('Every frozen split must contain every class; no records are dropped or reassigned.',
                             reclassify, move)

    def test_shared_family_cannot_cross_frozen_splits(self):
        first = next(row for row in self.manifest['records'] if row['split'] == 'train')
        other = next(row for row in self.manifest['records'] if row['split'] == 'validation')
        def join(value):
            source = next(row for row in value['records'] if row['id'] == other['id'])
            source['export_group'] = first['export_group']
            value['protected_components'][first['export_group']].append({'id': source['id']})
        self.assert_rejected('Frozen family or duplicate pixels cross split boundaries.', join)

    @unittest.skipUnless(os.environ.get('TULDOK_TRAINING_PYTHON'), 'Optional pinned CPU runtime not selected; M2 qualification must set TULDOK_TRAINING_PYTHON.')
    def test_real_epoch_checkpoint_and_predictions_use_frozen_bytes_after_current_edit(self):
        runtime = os.environ['TULDOK_TRAINING_PYTHON']
        probe = subprocess.run([runtime, str(ROOT / 'image_training.py'), '--probe'],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        self.assertTrue(json.loads(probe.stdout)['available'])
        current = self.records[2]
        self.dataset.workbench.save(current['id'], dict(revision=current['revision'], source_revision=current['source_revision'],
            task='image_classification', annotation={'label': 'A later draft'}, groups=current['groups'], review='draft'))
        output = self.root / 'output'
        output.mkdir()
        job = dict(schema_version=1, dataset_id=self.dataset.db.dataset_id, run_id='2' * 32,
                   graph_sha256='3' * 64, release_id=self.release_id, release_sha256=self.release_id,
                   release_path=str(self.release_path), output_dir=str(output), parent_pid=os.getpid(),
                   parameters={'epochs': 1, 'batch_size': 2, 'learning_rate': 0.001, 'seed': 42})
        job_path = self.root / 'job.json'
        job_path.write_text(json.dumps(job))
        result = subprocess.run([runtime, str(ROOT / 'image_training.py'), '--job', str(job_path)],
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([row['event'] for row in events], ['started', 'epoch', 'completed'])
        self.assertNotIn('"test"', result.stdout)
        artifacts = json.loads((output / 'artifact-manifest.json').read_text())
        self.assertEqual(len(artifacts['artifacts']), 5)
        self.assertEqual({path.name for path in output.iterdir()},
                         {row['name'] for row in artifacts['artifacts']} | {'artifact-manifest.json'})
        for artifact in artifacts['artifacts']:
            raw = (output / artifact['name']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), artifact['sha256'])
            self.assertEqual(len(raw), artifact['bytes'])
        metrics = json.loads((output / 'metrics.json').read_text())
        self.assertEqual(metrics['class_vocabulary'], self.manifest['class_vocabulary'])
        self.assertNotIn('test', metrics)
        self.assertEqual(metrics['best_epoch'], 1)
        self.assertEqual(metrics['validation']['examples'], 2)
        self.assertGreater(metrics['runtime']['peak_rss_bytes'], 0)
        self.assertEqual(metrics['runtime']['torch'], '2.8.0+cpu')
        frozen = {row['id']: row for row in self.manifest['records']}
        for split in ('validation', 'test'):
            prediction = json.loads((output / f'predictions-{split}.json').read_text())
            self.assertEqual(prediction['source_identity'], artifacts['source_identity'])
            self.assertEqual(len(prediction['rows']), 2)
            for row in prediction['rows']:
                source = frozen[row['id']]
                for key in ('id', 'revision', 'source_revision', 'asset_sha256', 'source_sha256', 'exported_pixel_sha256'):
                    self.assertEqual(row[key], source[key])
                self.assertEqual(row['truth_label'], source['annotation']['label'])
                self.assertEqual(row['truth_index'], source['class_index'])
                self.assertEqual(row['predicted_label'], self.manifest['class_vocabulary'][row['predicted_index']]['label'])
                self.assertAlmostEqual(sum(row['probabilities']), 1, places=6)
                self.assertEqual(row['predicted_index'], max(range(2), key=row['probabilities'].__getitem__))
            actual_metrics = metrics['validation'] if split == 'validation' else json.loads((output / 'test-metrics.json').read_text())['metrics']
            matrix = [[0, 0], [0, 0]]
            loss = 0.0
            for row in prediction['rows']:
                matrix[row['truth_index']][row['predicted_index']] += 1
                loss -= math.log(row['probabilities'][row['truth_index']])
            self.assertEqual(actual_metrics['confusion_matrix'], matrix)
            self.assertEqual(actual_metrics['accuracy'], (matrix[0][0] + matrix[1][1]) / 2)
            self.assertAlmostEqual(actual_metrics['loss'], loss / 2, places=6)
            f1 = sum((2 * matrix[index][index]) / (2 * matrix[index][index] + matrix[1-index][index]
                     + matrix[index][1-index]) if 2 * matrix[index][index] + matrix[1-index][index]
                     + matrix[index][1-index] else 0 for index in range(2)) / 2
            self.assertAlmostEqual(actual_metrics['macro_f1'], f1)
        self.assertEqual(hashlib.sha256(self.release_path.read_bytes()).hexdigest(), self.release_id)
        # Load only the just-produced checkpoint with Torch's restricted loader,
        # and independently reproduce predictions through the pinned reader.
        verifier = '''import io,json,sys,zipfile,tempfile
from pathlib import Path
import torch
from torch import nn
from torchvision import datasets,transforms
out,release=map(Path,sys.argv[1:]); torch.set_num_threads(1)
saved=torch.load(out/'checkpoint.pt',map_location='cpu',weights_only=True)
torch.manual_seed(42)
model=nn.Sequential(nn.Conv2d(3,16,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),nn.Conv2d(16,32,3,padding=1),nn.ReLU(),nn.MaxPool2d(2),nn.Conv2d(32,64,3,padding=1),nn.ReLU(),nn.AdaptiveAvgPool2d(1),nn.Flatten(),nn.Linear(64,2))
assert any(not torch.equal(value,saved['state_dict'][key]) for key,value in model.state_dict().items())
model.load_state_dict(saved['state_dict']); model.eval()
with tempfile.TemporaryDirectory() as directory:
 with zipfile.ZipFile(release) as source: source.extractall(directory)
 data=datasets.ImageFolder(Path(directory)/'val',transform=transforms.Compose([transforms.Resize((96,96)),transforms.ToTensor()]))
 rows=json.loads((out/'predictions-validation.json').read_text())['rows']
 for index,row in enumerate(rows):
  image,label=data[index]
  with torch.no_grad(): scores=model(image.unsqueeze(0)).softmax(1)[0]
  assert label==row['truth_index']
  assert torch.allclose(scores,torch.tensor(row['probabilities']),atol=1e-7)
print('actual checkpoint predictions verified')
'''
        check = subprocess.run([runtime, '-c', verifier, str(output), str(self.release_path)],
                               capture_output=True, text=True, timeout=30)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == '__main__':
    unittest.main()
