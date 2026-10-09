"""Actual NumPy/NPZ reader, retained data only; optional Torch iteration, no training."""
import argparse
import hashlib
import importlib.metadata
import inspect
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
import numpy as np
import native_sequence_dataset as native
from test_native_sequence_dataset import packet

LEGACY_SHA = '6951fd0166a83881cce116232fdaa6a1bd0aa5d078122c774909f3affdcde76e'


def preserve_samples(samples):
    """Variable human ranges and None intervals have no automatic minibatch target."""
    return samples


def verify(path, expected, output, *, torch_probe=True):
    output.mkdir(parents=True, exist_ok=True)
    assert importlib.metadata.version('numpy') == '2.5.3'
    dataset = native.NativeSequenceDataset(path, sha256=expected, split='train')
    source_fields = 0
    with zipfile.ZipFile(path) as release:
        for n in range(len(dataset)):
            sample = dataset[n]; row = sample['metadata']['record']
            with zipfile.ZipFile(io.BytesIO(release.read(row['asset']))) as bundle:
                raw = bundle.read('frames.jsonl'); lines = raw.splitlines(keepends=True)
            original = [json.loads(line) for line in lines]
            assert native.sha(raw) == row['sequence']['manifest']['frames_sha256']
            for name, kind in native.contract.FIELD_TYPES.items():
                field = sample['fields'][name]
                assert field.shape == (9, *native.contract.GEOMETRY['field_shapes'][name])
                for k, frame in enumerate(original):
                    # Independent byte projection of source-pinned x-fastest wire values.
                    exact = b''.join(struct.pack('<f' if kind == 'f32' else '<d', value) for value in frame['fields'][name])
                    assert field[k].tobytes(order='F') == exact
                    anchor = sample['metadata']['frame_index'][k]
                    assert anchor['sha256'] == native.sha(lines[k])
                    assert anchor['time_s'] == frame['time_s'] == sample['time_s'][k]
                    assert anchor['carrier_stamp'] == frame['carrier_stamp'] and anchor['liquid_stamp'] == frame['liquid_stamp']
                    source_fields += 1
            ranges = row['annotation'].get('temporal_labels', {}).get('ranges', [])
            for n, target in enumerate(ranges):
                assert sample['range_frame_mask'][n].tolist() == [target['start_frame'] <= k <= target['end_frame'] for k in range(9)]
                for name in ('start', 'end'):
                    k = target[name+'_frame']; anchor = target[name]
                    assert anchor['sha256'] == native.sha(lines[k]) and anchor['time_s'] == original[k]['time_s']
            assert sample['metadata']['accepted_intervals'][0] is None
    windows = native.NativeSequenceDataset(path, sha256=expected, split='train', window_frames=3)
    assert len(windows) == len(dataset)*7
    npz = output/'native-sample.npz'; windows.write_npz(npz, 0)
    with np.load(npz, allow_pickle=False) as loaded:
        assert set(loaded.files) == native.NPZ_KEYS
        for name in native.contract.FIELD_TYPES:
            assert loaded[name].dtype == windows[0]['fields'][name].dtype
            assert loaded[name].tobytes() == windows[0]['fields'][name].tobytes()
        assert loaded['metadata_utf8'].dtype == np.uint8
        assert json.loads(loaded['metadata_utf8'].tobytes()) == windows[0]['metadata']
        assert all(loaded[k].dtype.kind != 'O' for k in loaded.files)
    torch_report = {'executed': False, 'scope': 'optional iteration only; no model, trainer or default target collator'}
    if torch_probe:
        try:
            version = importlib.metadata.version('torch')
        except importlib.metadata.PackageNotFoundError:
            torch_report['reason'] = 'Torch not installed; NumPy/NPZ consumer is independently exercised'
        else:
            assert version == '2.8.0+cpu'
            from torch.utils.data import DataLoader
            loader = DataLoader(windows, batch_size=2, num_workers=0, collate_fn=preserve_samples)
            batch = next(iter(loader)); assert len(batch) == 2
            assert batch[0]['metadata'] == windows[0]['metadata']
            assert batch[0]['fields']['pressure'].tobytes() == windows[0]['fields']['pressure'].tobytes()
            torch_report.update(executed=True, version=version, preserve_sample_collate=True)
    report = {'result':'PASS', 'release_sha256':expected, 'whole_sequences':len(dataset),
        'three_frame_windows':len(windows), 'original_native_field_frames_compared':source_fields,
        'numpy_version':np.__version__, 'numpy_io_source_sha256':native.sha(Path(inspect.getsourcefile(np.load)).read_bytes()),
        'npz_sha256':native.sha(npz.read_bytes()), 'npz_allow_pickle':False,
        'exact_native_axes_bits_dtypes_times_stamps_human_coverage':True,
        'declared_family_context_members':len(dataset[0]['metadata']['declared_family_context']),
        'limitations':dataset[0]['metadata']['limitations'], 'torch':torch_report,
        'producer_execution':False, 'model_training_or_download':False}
    (output/'native-consumer-report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='native-consumer-') as temporary:
        raw = packet(Path(temporary)/'source')
    path = args.output/'current-release.zip'; path.write_bytes(raw)
    current = verify(path,native.sha(raw),args.output)
    import os
    legacy_path = os.environ.get('TULDOK_NATIVE_LEGACY_RELEASE')
    result = {'current_release':current}
    if legacy_path:
        # An explicit input failure stops here; no source substitution/retry.
        result['retained_7e_frozen_data'] = verify(Path(legacy_path),LEGACY_SHA,args.output/'retained-legacy',torch_probe=False)
    else:
        result['retained_7e_frozen_data'] = {'executed':False,'reason':'No retained legacy input configured; unittest source-derived legacy-format coverage is separate.'}
    print(json.dumps(result))


if __name__ == '__main__': main()
