"""Reviewed, frozen text classification projection for the bounded CPU recipe.

Releases owns selection, connected-family allocation, freshness and publication.
This module owns the versioned payload and the trainer's eligibility bounds.
"""
from collections import Counter
import hashlib

from workbench import WorkbenchError, encode, validate_annotation

FORMAT = 'text_classification_v1'
CONSUMER = {'name': 'tfidf_multinomial_nb_cpu', 'version': 1, 'scikit-learn': '1.7.2'}
SPLITS = ('train', 'validation', 'test')
MAX_RECORDS, MAX_CLASSES, MAX_TEXT_BYTES = 512, 8, 16 * 1024
MAX_PAYLOAD_BYTES = 7 * 1024**2  # Reserve ZIP framing within the 8 MiB archive bound.
TEXT_CONTRACT = 'UTF-8 canonical NFC/LF text; original source SHA-256 remains distinct.'


def validate_records(rows):
    for row in rows:
        if (row['kind'] != 'text' or row['task'] != 'text_classification'
                or row['review'] != 'human_reviewed' or not row['source_available']):
            raise WorkbenchError('Text classification training requires available, human-reviewed text class records.')
        if validate_annotation(row['task'], row['annotation'], row) != row['annotation']:
            raise WorkbenchError('Save the exact canonical text label before export.')
        if len(row['text'].encode('utf-8')) > MAX_TEXT_BYTES:
            raise WorkbenchError('Each training text must be at most 16 KiB of UTF-8.')


def inspect_projection(rows, assignments):
    validate_records(rows)
    labels = sorted({row['annotation']['label'] for row in rows})
    vocabulary = [{'label': label, 'index': index} for index, label in enumerate(labels)]
    counts = {split: Counter(row['annotation']['label'] for row in rows if assignments.get(row['id']) == split)
              for split in SPLITS}
    coverage = [dict(item, counts={split: counts[split][item['label']] for split in SPLITS}) for item in vocabulary]
    blockers = []
    if not 6 <= len(rows) <= MAX_RECORDS:
        blockers.append('The bounded text trainer requires 6–512 reviewed records.')
    if not 2 <= len(labels) <= MAX_CLASSES:
        blockers.append('The bounded text trainer requires 2–8 exact class labels.')
    if any(not counts[split][label] for split in SPLITS for label in labels):
        blockers.append('Every text class must occur in train, validation and test. Add independent reviewed examples or adjust split settings; no records are dropped or reassigned.')
    return vocabulary, coverage, blockers


def entries(prepared, body):
    preview, vocabulary = prepared['preview'], prepared['preview']['class_vocabulary']
    mapping = {item['label']: item['index'] for item in vocabulary}
    rows = [dict(row, split=preview['assignments'][row['id']],
                 export_group=prepared['groups'][prepared['roots'][row['id']]],
                 class_index=mapping[row['annotation']['label']], asset='assets/' + row['id'] + '.txt',
                 asset_sha256=hashlib.sha256(row['text'].encode('utf-8')).hexdigest()) for row in prepared['rows']]
    manifest = {'schema_version': 1, 'format': FORMAT, 'consumer': CONSUMER, 'seed': body['seed'],
                'text_contract': TEXT_CONTRACT, 'split_report': preview['split_report'],
                'class_vocabulary': vocabulary, 'class_to_idx': mapping,
                'protected_components': prepared['snapshots'], 'records': rows,
                'limitations': ['Human review is evidence, not a quality guarantee.',
                                'Protected families and exact content hashes do not prove semantic independence.']}
    yield 'manifest.json', encode(manifest).encode('utf-8')
    for row in rows:
        yield row['asset'], row['text'].encode('utf-8')
    for split in SPLITS:
        yield split + '/records.jsonl', ''.join(encode(row) + '\n' for row in rows if row['split'] == split).encode('utf-8')
    yield 'README.txt', (f'Tuldok {FORMAT}.\n{TEXT_CONTRACT}\n'
                       'Each split records.jsonl binds exact reviewed revisions, label indices, assets and protected families.\n'
                       'Use the explicitly selected local TF-IDF + MultinomialNB recipe; no pretrained model is included.\n').encode('utf-8')
