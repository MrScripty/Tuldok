"""Cold canonical custody for generic scientific field sequences.

The source parser owns the scientific contract. This reader binds its complete
metadata and original bytes to frozen review, revision and selected-family data.
It contains no producer-specific interpretation or physics qualification.
"""
import argparse
import json
from pathlib import Path
import re
import sys

import canonical_release
from canonical_release import MAX_RELEASE_BYTES, SPLITS, require, sha
from caption_import import SNAPSHOT_KEYS, snapshot
from native_text_import import RECORD_KEYS
import scientific_fields
from workbench import IDENTIFIER, WorkbenchError, encode, text_value, validate_annotation

LIMITATIONS = [
    'Family checks cover selected records only. Canonical v1 does not retain every omitted ancestor or bridge.',
    'Review, rights, units, geometry, temporal meaning and provenance are frozen declarations, not independently certified claims.',
    'Field integrity does not establish physical validity, independent trajectories, model quality or training suitability.',
]


def validate_row(row, release, used_ids):
    require(type(row) is dict and set(row) == RECORD_KEYS | {'field_sequence'},
            'unexpected canonical field-sequence record fields.')
    require(row['kind'] == 'field_sequence' and row['task'] == 'field_sequence_fields',
            'only field-sequence canonical v1 releases are supported.', 'unsupported')
    require(type(row['id']) is str and IDENTIFIER.fullmatch(row['id']) and row['id'] not in used_ids,
            'field-sequence record IDs must be unique.')
    used_ids.add(row['id'])
    snapshot({key: row[key] for key in SNAPSHOT_KEYS})
    require(row['source_available'] is True and row['source_lineage_known'] is True
            and row['review'] == 'human_reviewed', 'available, human-reviewed field snapshots are required.')
    require(all(row[key] is None for key in ('text', 'width', 'height', 'corner_annotation')),
            'field-sequence record contains another modality.')
    require(row['split'] in SPLITS, 'invalid frozen split.')
    for field, cap in (('name', 200), ('created_at', 120), ('updated_at', 120)):
        text_value(row[field], field, cap)
    require(validate_annotation('field_sequence_fields', row['annotation'], row) == row['annotation'],
            'canonical human inspection annotation required.')
    require(type(row['provenance']) is dict, 'record provenance must be an object.')
    text_value(row['provenance'].get('rights'), 'Rights note', 1000)
    filename = 'assets/' + row['id'] + '.zip'
    require(row['asset'] == filename and filename in release.namelist(), 'exact whole-field-sequence asset path required.')
    require(0 < release.getinfo(filename).file_size <= scientific_fields.MAX_BUNDLE_BYTES,
            'field-sequence bundle exceeds its bound.')
    raw = release.read(filename)
    require(sha(raw) == row['asset_sha256'] == row['content_hash'] == row['source_sha256'],
            'whole-field-sequence asset hash mismatch.')
    metadata = scientific_fields.parse_bundle(raw)
    require(type(row['field_sequence']) is dict and encode(row['field_sequence']) == encode(metadata),
            'field-sequence metadata differs from exact source.')
    provenance = row['provenance']
    require(provenance.get('method') == 'project_data_import'
            and type(provenance.get('field_sequence')) is dict
            and encode(provenance['field_sequence']) == encode(metadata)
            and provenance.get('source_sha256') == sha(raw),
            'field-sequence provenance differs from exact source.')
    source = provenance.get('project_source')
    require(type(source) is dict
            and set(source) == {'project_id', 'manifest_sha256', 'reference_id', 'path', 'measured_sha256'},
            'invalid declared project source receipt.')
    require(type(source['project_id']) is str and re.fullmatch('[a-f0-9]{32}', source['project_id'])
            and type(source['manifest_sha256']) is str and re.fullmatch('[a-f0-9]{64}', source['manifest_sha256'])
            and source['measured_sha256'] == sha(raw), 'declared project source identity differs from retained bytes.')
    scientific_fields.text(source['reference_id'], 64, 'Project reference')
    scientific_fields.text(source['path'], 512, 'Project source path')
    require(set(metadata['protected_groups']) <= set(row['groups']),
            'protected field source, state or family is missing.')
    result = {key: row[key] for key in ('id', 'name', 'revision', 'source_revision', 'split', 'review')}
    result.update(asset_sha256=sha(raw), rights=row['provenance']['rights'],
                  manifest=metadata['manifest'], frame_count=metadata['frame_count'],
                  field_count=metadata['field_count'], source_bytes=metadata['source_bytes'],
                  first_observed_state_sha256=metadata['first_observed_state_sha256'])
    return result


def validate_bytes(raw, expected_sha256=None):
    result = canonical_release.validate_bytes(raw, expected_sha256, kind='field_sequence', validate_row=validate_row)
    rows = result['summaries']
    return {'schema_version': 1, 'validation': 'field_sequence_release_integrity',
            'release_sha256': result['release_sha256'], 'field_sequence_count': len(rows),
            'frame_count': sum(row['frame_count'] for row in rows),
            'split_counts': result['split_counts'], 'family_scope': 'selected_records_only',
            'limitations': list(LIMITATIONS), 'field_sequences': rows}


def validate_release(path, expected_sha256=None):
    try:
        with Path(path).open('rb') as source:
            raw = source.read(MAX_RELEASE_BYTES + 1)
    except OSError as error:
        raise WorkbenchError('Field-sequence release file is unavailable.', 'unavailable', 404) from error
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
