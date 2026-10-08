"""Exact reviewed document projection for the published Chapter 11 byte reader."""
import hashlib

from workbench import WorkbenchError, MAX_SELECTED_TEXT_BYTES, encode, strings, validate_annotation

FORMAT = 'text_corpus_v1'
SPLITS = ('train', 'validation', 'test')
REFERENCE_CONTEXT = 128
SEPARATOR = b'\n\n'
CONSUMER = {
    'name': 'Training Your Own Models, Chapter 11 byte transformer',
    'repository': 'https://github.com/bc-ai-ecosystem/training-your-own-models',
    'commit': 'fb895e1a3e08fac86738106e6122bdcafb124e65',
    'source_kind': 'published companion archive',
    'companion': 'training-models-companion.zip',
    'companion_sha256': 'e924589b152f68bb15d89b8f95e3b52005bbe4a9f7770f2d0550b5422d3a11d6',
    'checksums': 'https://github.com/bc-ai-ecosystem/training-your-own-models/blob/fb895e1a3e08fac86738106e6122bdcafb124e65/docs/downloads/checksums.json',
    'path': 'training-models-companion/examples/tiny-transformer/train.py',
    'sha256': '8d2b908007dabbbd609312f1a22a697b40534b6c5ab07e3d540fd5833295e47d',
    'model_sha256': 'd304e951615f3bcb9cd5f4158b7348c5ecfd68731d8a5d62bd0d98e837dd1784',
    'use_model_sha256': '34b94d2be0a870fc470d27e61738e7ff193b586122b72724f7a33f2688099957',
    'torch': '2.8.0', 'vocabulary_size': 256, 'reference_context': REFERENCE_CONTEXT,
}
TEXT_CONTRACT = ('Existing canonical NFC/LF text encoded as UTF-8 without further normalization or trimming. '
                 'Sort record IDs within each split; append exactly two LF bytes after every document, including the last. '
                 'Existing trailing newlines are retained. Offsets are zero-based half-open byte ranges.')
WINDOW_WARNING = ('The unchanged reader uses raw bytes, a 256-value vocabulary and one-byte-shifted windows. '
                  'Windows can cross document and UTF-8 character boundaries. Two LF bytes are ordinary training bytes, '
                  'not EOS tokens or attention resets. Larger training contexts require more train bytes.')
README = ('Tuldok text_corpus_v1 for the published Chapter 11 byte transformer.\n' + TEXT_CONTRACT + '\n' + WINDOW_WARNING + '\n'
          'train.txt must exceed 128 bytes; validation.txt and test.txt must each have at least 2 bytes.\n'
          'Each split must contain an independent connected family. Allocation weights documents, not bytes.\n'
          'documents.jsonl maps exact document and separator byte ranges to record/source revisions and families.\n'
          'manifest.json freezes review notes, rights/provenance, source hashes and connected-family evidence.\n'
          'assets/ contains duplicated canonical document bytes, not original pre-normalization source backups.\n'
          'No documents are dropped, truncated, split, rebalanced by byte count or automatically reviewed.\n'
          'Review evidence and exact-family isolation do not establish quality, semantic independence or permission.\n').encode('utf-8')


def validate_records(rows):
    for row in rows:
        if (row['kind'] != 'text' or row['task'] != 'text_corpus' or row['review'] != 'human_reviewed'
                or not row['source_available']):
            raise WorkbenchError('Chapter 11 corpus export requires available text_corpus documents with explicit human review and a review note.')
        if validate_annotation('text_corpus', row['annotation'], row) != row['annotation']:
            raise WorkbenchError('Stored corpus review note is not canonical. Review and save it explicitly.')
        if not strings(row['groups'], 'Protected groups'):
            raise WorkbenchError('Every corpus document needs at least one protected group.')


def inspect_projection(rows, assignments, roots):
    """Describe the existing record-weighted allocation; never repair its quotas."""
    counts = {}
    blockers = []
    for split in SPLITS:
        selected = [row for row in rows if assignments.get(row['id']) == split]
        source_bytes = sum(len(row['text'].encode('utf-8')) for row in selected)
        counts[split] = dict(documents=len(selected), families=len({roots[row['id']] for row in selected}),
                             document_bytes=source_bytes, separator_bytes=2 * len(selected),
                             bytes=source_bytes + 2 * len(selected))
        if not selected:
            blockers.append(f'Chapter 11 corpus export requires nonempty train, validation and test groups; {split} is empty.')
        elif (split == 'train' and counts[split]['bytes'] <= REFERENCE_CONTEXT) or (split != 'train' and counts[split]['bytes'] < 2):
            minimum = 'more than 128' if split == 'train' else 'at least 2'
            blockers.append(f'Chapter 11 {split}.txt requires {minimum} bytes; allocation produced {counts[split]["bytes"]}. '
                            'Add reviewed independent documents or explicitly change split settings; no records were moved or split.')
    return counts, blockers


def entries(prepared, body):
    """One deterministic logical archive owns sizing, mapping and publication."""
    rows = prepared['rows']  # Workbench selection is sorted by stable record ID.
    preview = prepared['preview']
    mapping, records, files = [], [], {}
    for split in SPLITS:
        offset = 0
        digest = hashlib.sha256()
        for row in rows:
            if preview['assignments'][row['id']] != split:
                continue
            raw = row['text'].encode('utf-8')
            family = prepared['groups'][prepared['roots'][row['id']]]
            item = {key: row[key] for key in ('id', 'revision', 'source_revision', 'content_hash', 'source_sha256')}
            item.update(split=split, file=split + '.txt', byte_start=offset, byte_end=offset + len(raw),
                        separator_start=offset + len(raw), separator_end=offset + len(raw) + 2, family=family)
            mapping.append(item)
            records.append(dict(row, split=split, export_group=family, asset='assets/' + row['id'] + '.txt',
                                asset_sha256=row['content_hash']))
            digest.update(raw); digest.update(SEPARATOR)
            offset += len(raw) + 2
        files[split + '.txt'] = {'bytes': offset, 'sha256': digest.hexdigest()}
    manifest = dict(schema_version=1, format=FORMAT, consumer=CONSUMER, seed=body['seed'],
                    split_report=preview['split_report'], corpus_counts=preview['corpus_counts'],
                    files=files, text_contract=TEXT_CONTRACT, warnings=preview['warnings'],
                    records=records, protected_components=prepared['snapshots'],
                    limits={'selected_records': 5000, 'archive_uncompressed_bytes': MAX_SELECTED_TEXT_BYTES})
    yield 'manifest.json', encode(manifest).encode('utf-8'), None
    yield 'documents.jsonl', ''.join(encode(row) + '\n' for row in mapping).encode('utf-8'), None
    for row in rows:
        yield 'assets/' + row['id'] + '.txt', row['text'].encode('utf-8'), row['content_hash']
    for split in SPLITS:
        # Stream documents individually: never construct a second concatenated corpus in memory.
        yield split + '.txt', b'', None
        for row in rows:
            if preview['assignments'][row['id']] == split:
                yield None, row['text'].encode('utf-8'), row['content_hash']
                yield None, SEPARATOR, None
    yield 'README.txt', README, None
