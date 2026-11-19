"""The product of the curation check's dataset (tests/browser_project_workspace_curation.cjs), standard library only.

Run as the fixture dataset's command: python make_curated.py --out <output>. It writes records.jsonl (244 texts
with splits, a topic and a length in meta) and the embeddings a project's own script would write beside them,
embeddings/curated.npy and .json (16 dimensions; six topics spread around a circle in the two leading ones). Planted:
d001 and d002 are near-copies of r010 and r020 in train; v001, in validation, is a near-copy of r040 in train (the
leak); far01 lies far from every topic.
"""
import argparse
import json
import math
import os
import random
import struct
import sys

TOPICS = ('boats', 'birds', 'bread', 'bridges', 'bees', 'books')
DIMENSIONS = 16


def write_npy(path, rows):
    header = "{'descr': '<f4', 'fortran_order': False, 'shape': (%d, %d), }" % (len(rows), DIMENSIONS)
    text = (header + ' ' * (64 - (10 + len(header) + 1) % 64) + '\n').encode('latin-1')
    with open(path, 'wb') as handle:
        handle.write(b'\x93NUMPY\x01\x00' + struct.pack('<H', len(text)) + text)
        for row in rows:
            handle.write(struct.pack(f'<{DIMENSIONS}f', *row))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    out = parser.parse_args(argv).out
    generator = random.Random(19)
    centres = []
    for k in range(len(TOPICS)):
        angle = 2 * math.pi * k / len(TOPICS)
        centre = [4 * math.cos(angle), 4 * math.sin(angle)] + [generator.gauss(0, 0.4) for _ in range(DIMENSIONS - 2)]
        centre[2] += 3.0     # every row leans one way, so cosines between topics stay below the thresholds
        centres.append(centre)
    records, rows = [], []
    for i in range(240):
        k = i % len(TOPICS)
        split = 'validation' if i % 10 == 3 else 'test' if i % 10 == 7 else 'train'
        records.append({'id': f'r{i:03d}', 'kind': 'text', 'text': f'Note {i} about {TOPICS[k]}.', 'split': split,
                        'meta': {'topic': TOPICS[k], 'length': 10 + i % 17}})
        rows.append([value + generator.gauss(0, 1.0) for value in centres[k]])
    for name, copy_of, split in (('d001', 10, 'train'), ('d002', 20, 'train'), ('v001', 40, 'validation')):
        records.append({'id': name, 'kind': 'text', 'text': records[copy_of]['text'] + ' (again)', 'split': split,
                        'meta': {'topic': records[copy_of]['meta']['topic'], 'length': 12}})
        rows.append([value + generator.gauss(0, 0.002) for value in rows[copy_of]])
    records.append({'id': 'far01', 'kind': 'text', 'text': 'Something else entirely.', 'split': 'train',
                    'meta': {'topic': 'other', 'length': 30}})
    rows.append([generator.gauss(0, 1) for _ in range(DIMENSIONS - 3)] + [-6.0, 5.0, -4.0])
    os.makedirs(os.path.join(out, 'embeddings'), exist_ok=True)
    with open(os.path.join(out, 'records.jsonl'), 'w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record) + '\n')
    write_npy(os.path.join(out, 'embeddings', 'curated.npy'), rows)
    with open(os.path.join(out, 'embeddings', 'curated.json'), 'w', encoding='utf-8') as handle:
        json.dump({'format': 'tuldok_embeddings_v1', 'records': [record['id'] for record in records],
                   'dimensions': DIMENSIONS, 'metric': 'cosine', 'model': {'name': 'stand-in', 'via': 'a script'},
                   'prefix': None, 'source': {'dataset': None, 'run': None}}, handle)
    print(f'{len(records)} records and their embeddings written.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
