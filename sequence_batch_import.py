"""Bounded per-trajectory acquisition; Rheon meaning and storage stay with owners."""
import json
import re
import sqlite3

import rheon_sequences as rheon
from workbench import WorkbenchError, text_value

FORMAT = 'tuldok_rheon_batch_v1'
CONTROLS_FORMAT = 'tuldok_rheon_batch_v2'
MAX_ITEMS = 32
REQUEST_ID = re.compile(r'^[a-f0-9]{32}$')


def parse_request(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise WorkbenchError('Duplicate trajectory request fields are not accepted.')
            result[key] = value
        return result

    def invalid(value):
        raise WorkbenchError('Trajectory request constants must be finite.')

    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)
    except (json.JSONDecodeError, UnicodeError, RecursionError):
        raise WorkbenchError('Trajectory request must be complete bounded UTF-8 JSON.') from None


def marker(value):
    if type(value) is not str or not REQUEST_ID.fullmatch(value):
        raise WorkbenchError('Invalid trajectory import request marker.')
    return value


def label(value, name):
    result = text_value(value, name)
    if result != value or result in ('.', '..') or any(c in result for c in '/\\') or any(ord(c) < 32 for c in result):
        raise WorkbenchError(f'{name} must be an exact flat label without paths or surrounding whitespace.')
    return result


def receipt(record):
    context = record['provenance']['sequence_acquisition']
    return dict(context, record_id=record['id'], kind=record['kind'], name=record['name'])


def find_result(workbench, request_id):
    """Confirm committed acquisition, not current bytes, review or scientific validity."""
    marker(request_id)
    with workbench.lock:
        matches = workbench.db.execute("""SELECT id FROM workbench_records WHERE kind='sequence'
            AND json_extract(provenance_json, '$.sequence_acquisition.format') IN (?,?)
            AND json_extract(provenance_json, '$.sequence_acquisition.request_id')=? LIMIT 2""",
            (FORMAT, CONTROLS_FORMAT, request_id)).fetchall()
        if len(matches) > 1:
            raise WorkbenchError('Trajectory import marker is ambiguous; inspect the collection.', 'conflict', 409)
        return dict(found=True, **receipt(workbench._get(matches[0][0]))) if matches else {'found': False}


def import_item(workbench, body):
    allowed = {'files', 'request_id', 'batch_name', 'item_name', 'item_index', 'name', 'groups', 'parents', 'rights'}
    if type(body) is not dict or set(body) - allowed or type(body.get('files')) is not dict or set(body['files']) not in ({'run.json', 'frames.jsonl'}, {'run.json', 'frames.jsonl', 'controls.json'}):
        raise WorkbenchError('Supply one complete run/frame trajectory with optional original producer-v2 controls and bounded item metadata.')
    request_id = marker(body.get('request_id'))
    batch_name, item_name = label(body.get('batch_name'), 'Batch label'), label(body.get('item_name'), 'Trajectory label')
    index = body.get('item_index')
    if type(index) is not int or not 1 <= index <= MAX_ITEMS:
        raise WorkbenchError('Trajectory index must be an integer from 1 through 32.')
    try:
        run = rheon.decode_file(body['files']['run.json'], rheon.contract.MANIFEST_LIMIT, 'run.json')
        frames = rheon.decode_file(body['files']['frames.jsonl'], rheon.contract.FRAMES_LIMIT, 'frames.jsonl')
        controls = rheon.decode_file(body['files']['controls.json'], rheon.controls_contract.CONTROLS_LIMIT, 'controls.json') if 'controls.json' in body['files'] else None
        prepared = rheon.prepare(run, frames, controls)
        context = dict(format=FORMAT, request_id=request_id, batch_name=batch_name, item_name=item_name,
                       item_index=index, run_sha256=prepared['metadata']['run_sha256'],
                       frames_sha256=prepared['metadata']['manifest']['frames_sha256'])
        if prepared['metadata']['manifest']['version'] == 2:
            context.update(format=CONTROLS_FORMAT, sequence_version=2, controls_sha256=prepared['metadata']['controls']['sha256'])
        metadata = {key: body[key] for key in ('name', 'groups', 'parents', 'rights') if key in body}
        metadata.setdefault('name', item_name)
        # Validation is outside the lock; marker check and atomic publication share it.
        with workbench.lock:
            if find_result(workbench, request_id)['found']:
                raise WorkbenchError('This trajectory request marker was already admitted; check its saved result.', 'conflict', 409)
            return receipt(workbench.sequences.admit(prepared, metadata, acquisition=context))
    except WorkbenchError as error:
        if error.status == 404:
            raise WorkbenchError('A declared parent record was not found.') from None
        raise
    except (OSError, sqlite3.Error):
        raise WorkbenchError('Trajectory import stopped because storage failed. Check its saved result and the collection before retrying.', 'storage', 500) from None
