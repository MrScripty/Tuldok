"""Read-only canonical release validation for the bounded Rheon sequence pilot."""
import argparse
import json
from pathlib import Path
import sys

import canonical_release
from canonical_release import MAX_RELEASE_BYTES, MAX_METADATA_BYTES, SPLITS, archive, require, sha
from caption_import import SNAPSHOT_KEYS, snapshot
from native_text_import import RECORD_KEYS
import rheon_sequence_contract as contract
import rheon_sequences
from sequence_assets import MAX_BUNDLE_BYTES
from workbench import IDENTIFIER, WorkbenchError, encode, text_value, validate_annotation

LIMITATIONS = [
    'Family checks cover selected records only. Canonical v1 does not retain every omitted ancestor or bridge.',
    'Review, rights and source provenance are frozen declarations, not independently certified claims.',
    'Validation covers the pinned nine-frame Rheon dense3D transport pilot, not arbitrary sequences or training suitability.',
    *contract.LIMITATIONS,
]


def validate_row(row, release, used_ids):
    require(type(row) is dict and set(row) == RECORD_KEYS | {'sequence'}, 'unexpected canonical sequence record fields.')
    require(row['kind'] == 'sequence' and row['task'] == 'sequence_transport',
            'only sequence-only canonical v1 releases are supported.', 'unsupported')
    require(type(row['id']) is str and IDENTIFIER.fullmatch(row['id']) and row['id'] not in used_ids,
            'sequence record IDs must be unique.')
    used_ids.add(row['id'])
    snapshot({key: row[key] for key in SNAPSHOT_KEYS})
    require(row['source_available'] is True and row['source_lineage_known'] is True
            and row['review'] == 'human_reviewed', 'available, human-reviewed sequence snapshots are required.')
    require(all(row[key] is None for key in ('text', 'width', 'height', 'corner_annotation')),
            'sequence record contains another modality.')
    require(row['split'] in SPLITS, 'invalid frozen split.')
    for field, cap in (('name', 200), ('created_at', 120), ('updated_at', 120)):
        text_value(row[field], field, cap)
    require(validate_annotation('sequence_transport', row['annotation'], row) == row['annotation'],
            'canonical human inspection annotation required.')
    require(type(row['provenance']) is dict, 'record provenance must be an object.')
    text_value(row['provenance'].get('rights'), 'Rights note', 1000)
    filename = 'assets/' + row['id'] + '.zip'
    require(row['asset'] == filename and filename in release.namelist(), 'exact whole-sequence asset path required.')
    require(0 < release.getinfo(filename).file_size <= MAX_BUNDLE_BYTES, 'sequence bundle exceeds its bound.')
    raw = release.read(filename)
    require(sha(raw) == row['asset_sha256'] == row['content_hash'] == row['source_sha256'],
            'whole-sequence asset hash mismatch.')
    with archive(raw, 2, MAX_BUNDLE_BYTES) as bundle:
        require(bundle.namelist() == ['run.json', 'frames.jsonl'],
                'sequence bundle must retain exactly run.json and frames.jsonl.')
        require(0 < bundle.getinfo('run.json').file_size <= contract.MANIFEST_LIMIT
                and 0 < bundle.getinfo('frames.jsonl').file_size <= contract.FRAMES_LIMIT,
                'sequence source member exceeds its bound.')
        prepared = rheon_sequences.prepare(bundle.read('run.json'), bundle.read('frames.jsonl'))
    metadata = prepared['metadata']
    require(type(row['sequence']) is dict and encode(row['sequence']) == encode(dict(metadata, bundle_bytes=len(raw))),
            'sequence metadata differs from exact source.')
    require(set(metadata['protected_groups']) <= set(row['groups']), 'protected trajectory or initial family is missing.')
    manifest = metadata['manifest']
    return {
        'id': row['id'], 'name': row['name'], 'revision': row['revision'], 'source_revision': row['source_revision'],
        'split': row['split'], 'asset_sha256': sha(raw), 'run_sha256': metadata['run_sha256'],
        'frames_sha256': manifest['frames_sha256'], 'frame_count': manifest['frame_count'],
        'geometry': manifest['geometry'], 'field_types': manifest['field_types'], 'units': manifest['units'],
        'frame_index': metadata['frame_index'], 'technical_validation': metadata['technical_validation'],
        'pressure_semantics': manifest['pressure_semantics'], 'provenance': manifest['provenance'],
        'review': row['review'], 'rights': row['provenance']['rights'],
    }


def validate_bytes(raw, expected_sha256=None):
    """Verify immutable archive and native pilot semantics, without catalog access."""
    result = canonical_release.validate_bytes(raw, expected_sha256, kind='sequence', validate_row=validate_row)
    return {'schema_version': 1, 'validation': 'sequence_release_integrity',
            'release_sha256': result['release_sha256'], 'sequence_count': len(result['summaries']),
            'frame_count': sum(row['frame_count'] for row in result['summaries']),
            'split_counts': result['split_counts'], 'family_scope': 'selected_records_only',
            'limitations': list(LIMITATIONS), 'sequences': result['summaries']}


def validate_release(path, expected_sha256=None):
    """Capture bounded bytes without extracting archive-controlled paths."""
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_RELEASE_BYTES + 1)
    except OSError as error:
        raise WorkbenchError('Sequence release validation: release file is unavailable.', 'unavailable', 404) from error
    return validate_bytes(raw, expected_sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    args = parser.parse_args()
    try:
        print(encode(validate_release(args.release)))
    except WorkbenchError as error:
        print(json.dumps({'error': str(error), 'code': error.code}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
