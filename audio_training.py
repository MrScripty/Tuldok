"""Bounded source-channel PCM feature classification, with data-only models.

Runs owns admission and process lifecycle. This adapter owns checked frozen
audio, fixed measurements and train-only scaling/classification. No ASR.
"""
import argparse
import hashlib
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import sys
import time
import zipfile

import audio_assets
import audio_classification_export as projection
from frozen_classification import validate_families
from image_training import TrainingError, HASH, IDENTIFIER, _json, _invalid, guard_parent, _emit, _write_json
from workbench import WorkbenchError, encode

ADAPTER = {'name': 'audio_features_logistic_cpu', 'version': 1}
PARAMETER_BOUNDS = {'C': {'minimum': 0.01, 'maximum': 100, 'default': 1, 'type': 'number'}}
FEATURE_NAMES = ['mean', 'rms', 'zero_crossing_fraction', 'spectral_centroid_nyquist',
                 'power_0_25', 'power_25_50', 'power_50_75', 'power_75_100']
TRANSFORM = {'name': 'pcm_interval_features', 'version': 1, 'fit_scope': 'train',
             'features': FEATURE_NAMES, 'sample_scale': 32768, 'window': 'rectangular',
             'spectrum': 'numpy_rfft_power', 'band_edges_nyquist': [0, .25, .5, .75, 1],
             'standardization': 'train_mean_population_std', 'solver': 'lbfgs', 'max_iter': 200, 'tol': 1e-6}
MAX_ZIP_BYTES = MAX_EXPANDED_BYTES = 48 * 1024**2
MAX_JOB_BYTES = 16 * 1024
REFERENCE_KEYS = ('id', 'revision', 'source_revision', 'source_sha256', 'asset_sha256',
                  'pcm_sha256', 'audio_family_sha256', 'sample_rate_hz', 'channels',
                  'channel', 'start_frame', 'end_frame')


def validate_parameters(value):
    if not isinstance(value, dict) or set(value) != {'C'}:
        _invalid('Supply exactly C for the audio classifier.')
    number = value['C']
    if type(number) not in (int, float) or not math.isfinite(number) or not .01 <= number <= 100:
        _invalid('C must be a finite number from 0.01 to 100.')
    return dict(value)


def inspect_release(path, expected_sha256):
    if not isinstance(expected_sha256, str) or not HASH.fullmatch(expected_sha256):
        _invalid('Expected audio release SHA-256 is invalid.')
    try:
        with Path(path).open('rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                _invalid('Frozen release must be a regular file.')
            raw = handle.read(MAX_ZIP_BYTES + 1)
    except OSError as error:
        raise TrainingError('unavailable', 'Frozen audio release bytes are unavailable.') from error
    if len(raw) > MAX_ZIP_BYTES:
        _invalid('Frozen audio release exceeds the 48 MiB archive limit.')
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _invalid('Frozen audio release SHA-256 does not match its identity.')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(infos) > projection.MAX_RECORDS + 5 or len(names) != len(set(names)):
                _invalid('Audio release has duplicate or too many ZIP entries.')
            if sum(item.file_size for item in infos) > MAX_EXPANDED_BYTES:
                _invalid('Frozen audio release exceeds the 48 MiB expanded limit.')
            for item in infos:
                name, mode = PurePosixPath(item.filename), item.external_attr >> 16
                if (name.is_absolute() or '..' in name.parts or '\\' in item.filename or str(name) != item.filename
                        or item.is_dir() or item.flag_bits & 1 or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                    _invalid('Audio release contains an unsafe ZIP entry.')
            metadata_names = {'manifest.json', 'README.txt'} | {split + '/records.jsonl' for split in projection.SPLITS}
            if not metadata_names <= set(names) or sum(archive.getinfo(name).file_size for name in metadata_names) > projection.MAX_METADATA_BYTES:
                _invalid('Frozen audio metadata is absent or exceeds 7 MiB.')
            value = _json(archive.read('manifest.json'), 'Audio release manifest')
            if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
                raise TrainingError('unsupported', 'Only audio release schema 1 is supported.')
            if value.get('format') != projection.FORMAT:
                raise TrainingError('unsupported', 'Choose a frozen audio_classification_v1 release.')
            if value.get('consumer') != projection.CONSUMER or value.get('audio_contract') != projection.CONTRACT:
                _invalid('Frozen audio consumer or source-coordinate contract differs.')
            records = value.get('records')
            if not isinstance(records, list) or not 6 <= len(records) <= projection.MAX_RECORDS:
                _invalid('Audio training requires 6–256 frozen recordings.')
            seen, assets, families = set(), set(), {}
            total_bytes = total_frames = 0
            for row in records:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not IDENTIFIER.fullmatch(row['id']) or row['id'] in seen:
                    _invalid('Frozen audio identifiers must be canonical and unique.')
                seen.add(row['id'])
                if row.get('source_lineage_known') is not True:
                    _invalid('Frozen audio requires known source lineage.')
                if any(type(row.get(key)) is not int or row[key] < 1 for key in ('revision', 'source_revision')):
                    _invalid('Frozen audio revisions must be positive integers.')
                if any(not isinstance(row.get(key), str) or not HASH.fullmatch(row[key]) for key in
                       ('content_hash', 'source_sha256', 'asset_sha256', 'pcm_sha256', 'audio_family_sha256')):
                    _invalid('Frozen audio requires original and decoded PCM hashes.')
                segment = projection.target(row)
                asset = 'assets/' + row['id'] + '.wav'
                if row.get('asset') != asset or archive.getinfo(asset).file_size > audio_assets.MAX_WAV_BYTES:
                    _invalid('Frozen audio asset reference or size is invalid.')
                source = archive.read(asset)
                meta, _ = audio_assets.parse_wav(source)
                digest = hashlib.sha256(source).hexdigest()
                family = hashlib.sha256(encode([meta['sample_rate_hz'], meta['channels'], meta['pcm_sha256']]).encode()).hexdigest()
                mandatory = ['audio-source:' + digest, 'audio-family:' + family]
                if any(row[key] != digest for key in ('source_sha256', 'asset_sha256', 'content_hash')):
                    _invalid('Frozen audio original bytes differ from their source references.')
                if row.get('audio') != dict(meta, protected_groups=mandatory) or not set(mandatory) <= set(row['groups']):
                    _invalid('Frozen audio metadata or mandatory protected families differ from decoded WAV.')
                if (row['pcm_sha256'] != meta['pcm_sha256'] or row['audio_family_sha256'] != family
                        or any(type(row.get(key)) is not int or row[key] != meta[key] for key in ('sample_rate_hz', 'channels'))
                        or any(type(row.get(key)) is not int or row[key] != segment[key] for key in ('channel', 'start_frame', 'end_frame'))
                        or row.get('target_label') != segment['label']):
                    _invalid('Frozen audio projection differs from its reviewed source interval.')
                split = row.get('split')
                if split not in projection.SPLITS:
                    _invalid('Frozen audio split is invalid.')
                if family in families and families[family] != split:
                    _invalid('Identical decoded PCM crosses split boundaries.')
                families[family] = split
                assets.add(asset)
                total_bytes += len(source)
                total_frames += segment['end_frame'] - segment['start_frame']
            if total_bytes > projection.MAX_SOURCE_BYTES or total_frames > projection.MAX_TOTAL_FRAMES:
                _invalid('Frozen audio exceeds the total source-byte or analyzed-frame bound.')
            vocabulary, _, blockers = projection.inspect_projection(records, {row['id']: row['split'] for row in records})
            if blockers:
                _invalid(blockers[0])
            mapping = {item['label']: item['index'] for item in vocabulary}
            if (value.get('class_vocabulary') != vocabulary or value.get('class_to_idx') != mapping
                    or any(type(item.get('index')) is not int for item in value['class_vocabulary'])
                    or any(type(index) is not int for index in value['class_to_idx'].values())):
                _invalid('Frozen audio vocabulary differs from its exact labels.')
            if any(type(row.get('class_index')) is not int or row['class_index'] != mapping[row['target_label']] for row in records):
                _invalid('Frozen audio class indices differ from their labels.')
            for split in projection.SPLITS:
                actual = [_json(line, 'Audio split row') for line in archive.read(split + '/records.jsonl').splitlines()]
                if actual != [row for row in records if row['split'] == split]:
                    _invalid('Frozen audio JSONL differs from its manifest mapping.')
            validate_families(value, 'audio')
            if set(names) != assets | metadata_names:
                _invalid('Audio release contains undeclared or missing files.')
            return value
    except (zipfile.BadZipFile, KeyError, OSError, ValueError, TypeError, UnicodeError, NotImplementedError) as error:
        if isinstance(error, TrainingError):
            raise
        if isinstance(error, WorkbenchError):
            raise TrainingError('invalid', str(error)) from None
        raise TrainingError('invalid', 'Frozen audio ZIP or metadata cannot be decoded.') from error


def probe_runtime():
    # First runnable checkpoint admits real release/graph inspection only.
    return {'schema_version': 1, 'available': False, 'adapter': dict(ADAPTER), 'runtime': {},
            'problems': [{'code': 'unavailable', 'message': 'Audio release and graph inspection are implemented; the CPU trainer is not available in this checkpoint.'}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(probe_runtime(), allow_nan=False), flush=True)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
