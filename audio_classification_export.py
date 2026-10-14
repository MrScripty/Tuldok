"""Frozen one-interval-per-record audio classification projection.

Releases owns selection, split allocation and publication. Original timed
annotations remain unchanged; the explicit projection never crops source WAVs.
"""
from collections import Counter
import hashlib

import audio_assets
from workbench import WorkbenchError, encode

FORMAT = 'audio_classification_v1'
CONSUMER = {'name': 'audio_features_logistic_cpu', 'version': 1, 'scikit-learn': '1.7.2'}
SPLITS = ('train', 'validation', 'test')
MAX_RECORDS, MAX_CLASSES = 256, 8
MIN_FRAMES, MAX_FRAMES, MAX_TOTAL_FRAMES = 128, 65536, 4194304
MAX_SOURCE_BYTES, MAX_METADATA_BYTES = 40 * 1024**2, 7 * 1024**2
CONTRACT = 'One reviewed labelled source-channel interval [start_frame,end_frame) per original PCM16 WAV; no resampling or downmix.'


def target(row):
    if (row.get('kind') != 'audio' or row.get('task') != 'audio_timed'
            or row.get('review') != 'human_reviewed' or row.get('source_available') is not True):
        raise WorkbenchError('Audio classification requires available, human-reviewed WAV interval records.')
    annotation = audio_assets.validate_annotation(row['annotation'], row)
    if annotation != row['annotation'] or len(annotation['segments']) != 1 or not annotation['segments'][0]['label']:
        raise WorkbenchError('Audio classification v1 requires exactly one reviewed class-labelled interval per recording.')
    segment = annotation['segments'][0]
    frames = segment['end_frame'] - segment['start_frame']
    if not MIN_FRAMES <= frames <= MAX_FRAMES or frames > 10 * row['audio']['sample_rate_hz']:
        raise WorkbenchError('Each classified audio interval requires 128–65,536 source frames and at most 10 seconds.')
    return segment


def validate_records(rows):
    for row in rows:
        target(row)


def inspect_projection(rows, assignments):
    segments = {row['id']: target(row) for row in rows}
    labels = sorted({segment['label'] for segment in segments.values()})
    vocabulary = [{'label': label, 'index': index} for index, label in enumerate(labels)]
    counts = {split: Counter(segments[row['id']]['label'] for row in rows if assignments.get(row['id']) == split)
              for split in SPLITS}
    coverage = [dict(item, counts={split: counts[split][item['label']] for split in SPLITS}) for item in vocabulary]
    blockers = []
    if not 6 <= len(rows) <= MAX_RECORDS:
        blockers.append('The bounded audio trainer requires 6–256 reviewed recordings.')
    if not 2 <= len(labels) <= MAX_CLASSES:
        blockers.append('The bounded audio trainer requires 2–8 exact class labels.')
    if any(not counts[split][label] for split in SPLITS for label in labels):
        blockers.append('Every audio class must occur in train, validation and test; no recordings are dropped or reassigned.')
    if sum(s['end_frame'] - s['start_frame'] for s in segments.values()) > MAX_TOTAL_FRAMES:
        blockers.append('The audio selection exceeds 4,194,304 analyzed source frames.')
    if sum(row['audio']['source_bytes'] for row in rows) > MAX_SOURCE_BYTES:
        blockers.append('Original WAVs exceed the 40 MiB audio release bound.')
    return vocabulary, coverage, blockers


def manifest(prepared, body):
    preview, vocabulary = prepared['preview'], prepared['preview']['class_vocabulary']
    mapping = {item['label']: item['index'] for item in vocabulary}
    rows = []
    for row in prepared['rows']:
        segment, meta = target(row), row['audio']
        family_hash = hashlib.sha256(encode([meta['sample_rate_hz'], meta['channels'], meta['pcm_sha256']]).encode()).hexdigest()
        rows.append(dict(row, split=preview['assignments'][row['id']],
            export_group=prepared['groups'][prepared['roots'][row['id']]],
            target_label=segment['label'], class_index=mapping[segment['label']],
            asset='assets/' + row['id'] + '.wav', asset_sha256=row['content_hash'],
            pcm_sha256=meta['pcm_sha256'], audio_family_sha256=family_hash,
            sample_rate_hz=meta['sample_rate_hz'], channels=meta['channels'],
            **{key: segment[key] for key in ('channel', 'start_frame', 'end_frame')}))
    return {'schema_version': 1, 'format': FORMAT, 'consumer': CONSUMER,
        'audio_contract': CONTRACT, 'seed': body['seed'], 'split_report': preview['split_report'],
        'class_vocabulary': vocabulary, 'class_to_idx': mapping,
        'protected_components': prepared['snapshots'], 'records': rows,
        'limitations': ['One interval is one existing recording, not an independent cropped source.',
                       'Human review and tiny authored examples do not establish useful accuracy or semantic independence.',
                       'ASR, resampling and downmix are unavailable.']}


def metadata_entries(value):
    yield 'manifest.json', encode(value).encode('utf-8')
    for split in SPLITS:
        yield split + '/records.jsonl', ''.join(encode(row) + '\n' for row in value['records'] if row['split'] == split).encode('utf-8')
    yield 'README.txt', (f'Tuldok {FORMAT}.\n{CONTRACT}\n'
        'Original whole WAV files and complete protected families are retained.\n'
        'Features/scaling/logistic regression are separate train-only model transforms; no ASR or pretrained model.\n').encode('utf-8')
