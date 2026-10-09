"""Exercise the actual pinned ImageFolder and unchanged Chapter 8 CPU trainer.

No weights, datasets or models are downloaded. The six authored solid images
test transport/reader compatibility only; their metrics do not measure quality.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))
from app import Dataset
from image_classification_fixture import populate
import image_classification_export as projection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    trainer = ROOT / 'tests/fixtures/train_image_classifier.py'
    assert hashlib.sha256(trainer.read_bytes()).hexdigest() == projection.CONSUMER['sha256']
    versions = {name: importlib.metadata.version(name) for name in ('torch', 'torchvision', 'scikit-learn')}
    assert versions['torch'].split('+')[0] == '2.8.0', versions
    assert versions['torchvision'].split('+')[0] == '0.23.0', versions
    import torch
    import torchvision
    torch.set_num_threads(1)
    reader = Path(torchvision.__file__).parent / 'datasets/folder.py'
    reader_sha = hashlib.sha256(reader.read_bytes()).hexdigest()
    assert reader_sha == 'b2a36e520cf451d82b993e6fdaa1266d8526ef6a402dcf401f23f0c9cd0a8efa', reader_sha
    with tempfile.TemporaryDirectory(prefix='classifier-reader-', dir=args.output) as folder:
        folder = Path(folder)
        dataset = Dataset(str(folder / 'source'))
        try:
            rows = populate(dataset)
            request = dict(format=projection.FORMAT, seed=42, ratios={'train': 34, 'validation': 33, 'test': 33},
                           items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows])
            preview = dataset.releases.preview(request)
            assert preview['eligible'], preview
            result = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
            archive_path = args.output / 'classification-consumer.zip'
            shutil.copyfile(dataset.releases.locate(result['id']), archive_path)
        finally:
            dataset.close()
        data = folder / 'export'
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(data)
            manifest = json.loads(archive.read('manifest.json'))
        records = {str(data / row['asset']): row for row in manifest['records']}
        loaded = {split: torchvision.datasets.ImageFolder(data / split) for split in ('train', 'val', 'test')}
        for split, corpus in loaded.items():
            assert corpus.class_to_idx == manifest['class_to_idx']
            assert len(corpus) == 2
            for index, (name, label_index) in enumerate(corpus.samples):
                image, target = corpus[index]
                assert target == label_index == records[name]['class_index']
                assert image.size == (16, 12) and image.mode == 'RGB'
                assert manifest['class_vocabulary'][target]['label'] == records[name]['annotation']['label']
        # Execute the unchanged trainer, including validation, checkpoint load and test reader.
        env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
        command = [sys.executable, str(trainer), '--data', str(data), '--out', str(args.output / 'tiny-smoke'),
                   '--backbone', 'tiny', '--epochs', '1', '--batch-size', '2', '--device', 'cpu']
        trained = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        (args.output / 'trainer.log').write_text(trained.stdout + trained.stderr)
        assert trained.returncode == 0, trained.stdout + trained.stderr
        metrics = json.loads((args.output / 'tiny-smoke/metrics.json').read_text())
        assert metrics['class_to_idx'] == manifest['class_to_idx']
        assert len(metrics['history']) == 1 and len(metrics['test']['confusion_matrix']) == 2
        # Actual upstream reader enforces missing-class coverage; no inferred mock contract.
        missing_class = data / 'val/class_000001'
        for image in missing_class.iterdir():
            image.unlink()
        try:
            torchvision.datasets.ImageFolder(data / 'val')
        except FileNotFoundError:
            pass
        else:
            raise AssertionError('The pinned default reader must reject an empty class directory')
        # The consumer itself, not canonical export, owns its two-class requirement.
        for split in ('train', 'val', 'test'):
            shutil.rmtree(data / split / 'class_000001')
        rejected = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
        assert rejected.returncode != 0 and 'Need at least two classes' in rejected.stderr
    report = dict(versions=versions, reader_sha256=reader_sha, trainer_sha256=projection.CONSUMER['sha256'],
                  release_id=result['id'], reader_records=6, reader_splits=['train', 'val', 'test'],
                  exact_class_mapping=True, unchanged_cpu_trainer_one_epoch=True,
                  rejected_empty_class=True, rejected_one_class=True,
                  qualification='Authored compatibility fixture only; no training-quality claim.')
    (args.output / 'consumer-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
