"""Run the unchanged published Chapter 11 reader, trainer and held-out evaluator.

Authored fixture data only. No network, weights or model downloads. Source hashes
are pinned independently; tensor/shift assertions are not a replacement reader.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))
from app import Dataset
from text_corpus_fixture import populate
import text_corpus_export as projection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'tests/fixtures/tiny_transformer'
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in ('train.py', 'model.py', 'use_model.py')}
    assert hashes == {'train.py': projection.CONSUMER['sha256'], 'model.py': projection.CONSUMER['model_sha256'],
                      'use_model.py': projection.CONSUMER['use_model_sha256']}, hashes
    import torch
    assert torch.__version__.split('+')[0] == '2.8.0', torch.__version__
    torch.set_num_threads(1)
    sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location('published_corpus_trainer', source / 'train.py')
    trainer = importlib.util.module_from_spec(spec); spec.loader.exec_module(trainer)
    assert trainer.Config().vocab == 256 and trainer.Config().context == 128
    with tempfile.TemporaryDirectory(prefix='corpus-consumer-', dir=args.output) as temporary:
        folder = Path(temporary)
        dataset = Dataset(str(folder / 'source'))
        try:
            rows = populate(dataset)
            request = dict(format=projection.FORMAT, seed=42, ratios=dict(train=67, validation=17, test=16),
                           items=[{key: row[key] for key in ('id', 'revision', 'source_revision')} for row in rows])
            preview = dataset.releases.preview(request)
            assert preview['eligible'], preview
            result = dataset.releases.create(dict(request, preview_token=preview['preview_token']))
            archive_path = args.output / 'corpus-consumer.zip'
            shutil.copyfile(dataset.releases.locate(result['id']), archive_path)
        finally:
            dataset.close()
        data = folder / 'export'
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(data)
            manifest = json.loads(archive.read('manifest.json'))
            mapping = [json.loads(line) for line in archive.read('documents.jsonl').splitlines()]
        files = {}
        for split in projection.SPLITS:
            path = data / (split + '.txt')
            raw = path.read_bytes()
            tensor, digest = trainer.read_bytes(path)
            assert tensor.dtype == torch.long and tensor.ndim == 1
            assert tensor.tolist() == list(raw)
            assert digest == hashlib.sha256(raw).hexdigest() == manifest['files'][path.name]['sha256']
            items = [r for r in mapping if r['split'] == split]
            assert raw == b''.join((data / 'assets' / (r['id'] + '.txt')).read_bytes() + b'\n\n' for r in items)
            for item in items:
                assert raw[item['byte_start']:item['byte_end']] == (data / 'assets' / (item['id'] + '.txt')).read_bytes()
                assert raw[item['separator_start']:item['separator_end']] == b'\n\n'
            files[split] = {'bytes': len(raw), 'sha256': digest}
        # All 256 input byte values are raw IDs, including invalid standalone UTF-8.
        all_bytes = folder / 'byte-values.txt'; all_bytes.write_bytes(bytes(range(256)))
        assert trainer.read_bytes(all_bytes)[0].tolist() == list(range(256))
        train_data, _ = trainer.read_bytes(data / 'train.txt')
        raw = (data / 'train.txt').read_bytes()
        seed, context, size = 9182, 128, 512
        starts = torch.randint(len(raw) - context, (size,), generator=torch.Generator().manual_seed(seed)).tolist()
        x, y = trainer.batch(train_data, context, size, torch.Generator().manual_seed(seed), 'cpu')
        assert x.tolist() == [list(raw[start:start + context]) for start in starts]
        assert y.tolist() == [list(raw[start + 1:start + context + 1]) for start in starts]
        assert torch.equal(x[:, 1:], y[:, :-1])
        boundaries = [r['separator_end'] for r in mapping if r['split'] == 'train'][:-1]
        assert boundaries and any(start < boundary < start + context for start in starts for boundary in boundaries)
        assert any(raw[start] & 0xC0 == 0x80 for start in starts), 'Sampled windows include UTF-8 continuation-byte starts'
        try:
            trainer.batch(torch.zeros(128, dtype=torch.long), 128, 1, torch.Generator(), 'cpu')
        except ValueError as error:
            assert 'more bytes than context' in str(error)
        else:
            raise AssertionError('Unchanged batch reader must reject len == context')
        model = trainer.ByteTransformer(trainer.Config(context=128, width=16, layers=1, heads=2, dropout=0))
        two_bytes = trainer.evaluate(model, torch.tensor([65, 10]), 'cpu', False)
        assert two_bytes['evaluated_bytes'] == 1
        for count in (0, 1):
            try:
                trainer.evaluate(model, torch.zeros(count, dtype=torch.long), 'cpu', False)
            except ValueError as error:
                assert 'empty' in str(error)
            else:
                raise AssertionError('Unchanged evaluator must reject fewer than two bytes')
        env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
        output = args.output / 'tiny-smoke'
        command = [sys.executable, str(source / 'train.py'), '--data', str(data), '--output', str(output),
                   '--device', 'cpu', '--steps', '2', '--warmup', '0', '--eval-every', '1', '--batch-size', '2',
                   '--context', '128', '--width', '16', '--layers', '1', '--heads', '2', '--dropout', '0']
        training_started = time.perf_counter()
        trained = subprocess.run(command, capture_output=True, text=True, env=env, timeout=90)
        training_seconds = time.perf_counter() - training_started
        (args.output / 'trainer.log').write_text(trained.stdout + trained.stderr)
        assert trained.returncode == 0, trained.stdout + trained.stderr
        metrics = [json.loads(line) for line in (output / 'metrics.jsonl').read_text().splitlines()]
        assert [row['step'] for row in metrics] == [1, 2]
        checkpoint = torch.load(output / 'checkpoint.pt', map_location='cpu', weights_only=True)
        assert checkpoint['step'] == 2 and checkpoint['run']['train_sha256'] == files['train']['sha256']
        model.load_state_dict(checkpoint['model'])
        test_data, _ = trainer.read_bytes(data / 'test.txt')
        independent = trainer.evaluate(model, test_data, 'cpu', False, max_chunks=len(test_data))
        used = subprocess.run([sys.executable, str(source / 'use_model.py'), str(output / 'checkpoint.pt'),
            '--device', 'cpu', '--evaluate-file', str(data / 'test.txt')], capture_output=True, text=True, env=env, timeout=60)
        (args.output / 'held-out.log').write_text(used.stdout + used.stderr)
        assert used.returncode == 0, used.stdout + used.stderr
        heldout = ast.literal_eval(used.stdout.strip())
        assert heldout['sha256'] == files['test']['sha256']
        assert heldout['evaluated_bytes'] == files['test']['bytes'] - 1
        assert abs(heldout['loss_nats_per_byte'] - independent['loss_nats_per_byte']) < 1e-6
    report = dict(torch=str(torch.__version__), source_sha256=hashes, release_id=result['id'], files=files,
                  raw_byte_tensor_identity=True, independently_checked_shifted_windows=512,
                  cross_document_windows=True, utf8_boundary_windows=True, unchanged_cpu_training_steps=2,
                  training_seconds=training_seconds, checkpoint_reloaded=True, heldout=heldout,
                  qualification='Authored compatibility fixtures only; no model-quality claim.')
    (args.output / 'consumer-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
