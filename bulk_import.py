"""Native raw-asset JSONL row admission; storage/normalization stay with Workbench."""
import hashlib
import json
import re
import sqlite3

from workbench import WorkbenchError, text_value

MAX_ROW_BYTES = 3 * 1024 * 1024
MAX_ROWS = 1000
REQUEST_ID = re.compile(r'^[a-f0-9]{32}$')


def leaf_name(value, label):
    name = text_value(value, label, 200)
    if name != value or name in ('.', '..') or any(c in name for c in '/\\') or any(ord(c) < 32 for c in name):
        raise WorkbenchError(f'{label} must be an exact filename without a directory or surrounding whitespace.')
    return name


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkbenchError('Duplicate JSON fields are not accepted.')
        result[key] = value
    return result


def invalid_constant(value):
    raise WorkbenchError('JSON constants must be finite.')


def decode_row(line):
    if not isinstance(line, str):
        raise WorkbenchError('Source row must be JSON text.')
    try:
        raw = line.encode('utf-8')
    except UnicodeEncodeError:
        raise WorkbenchError('Source row contains invalid Unicode.') from None
    if not 0 < len(raw) <= MAX_ROW_BYTES:
        raise WorkbenchError('Each source row must be at most 3 MiB of UTF-8 JSON.')
    if '\n' in line or '\r' in line.removesuffix('\r'):
        raise WorkbenchError('Each source row must occupy one physical JSONL line.')
    try:
        row = json.loads(line, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (json.JSONDecodeError, RecursionError):
        raise WorkbenchError('Source row must be one complete JSON object.') from None
    if not isinstance(row, dict) or row.get('kind') not in ('text', 'image'):
        raise WorkbenchError('Source row kind must be text or image.')
    fields = {'kind', 'name', 'groups', 'parents', 'rights', 'text' if row['kind'] == 'text' else 'file'}
    if set(row) - fields:
        raise WorkbenchError('Unsupported source fields. Import raw assets first; annotate and review afterward.')
    if 'name' in row:
        row['name'] = text_value(row['name'], 'Name')
    if row['kind'] == 'image':
        row['file'] = leaf_name(row.get('file'), 'Image reference')
    return row, hashlib.sha256(raw).hexdigest()


def result(record):
    context = record['provenance']['acquisition']
    return dict(record_id=record['id'], name=record['name'], kind=record['kind'],
                revision=record['revision'], source_revision=record['source_revision'],
                request_id=context['request_id'], row_number=context['declared']['row_number'],
                row_sha256=context['row_sha256'], review=record['review'])


def find_result(workbench, request_id):
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise WorkbenchError('Invalid import request marker.')
    with workbench.lock:
        matches = workbench.db.execute("SELECT id FROM workbench_records WHERE json_extract(provenance_json, '$.acquisition.request_id')=?",
                                       (request_id,)).fetchall()
        if len(matches) > 1:
            raise WorkbenchError('Import marker is ambiguous; inspect the collection.', 'conflict', 409)
        return dict(found=True, **result(workbench._get(matches[0][0]))) if matches else {'found': False}


def import_row(workbench, body):
    if set(body) - {'source_name', 'row_number', 'line', 'request_id', 'image_name', 'image'}:
        raise WorkbenchError('Unsupported row admission fields.')
    source_name = leaf_name(body.get('source_name'), 'Manifest name')
    number, request_id = body.get('row_number'), body.get('request_id')
    if type(number) is not int or not 1 <= number <= MAX_ROWS:
        raise WorkbenchError('Source row number must be an integer from 1 through 1000.')
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise WorkbenchError('Invalid import request marker.')
    row, digest = decode_row(body.get('line'))
    declared = dict(manifest_name=source_name, row_number=number)
    asset = {key: value for key, value in row.items() if key != 'file'}
    if row['kind'] == 'image':
        if body.get('image_name') != row['file'] or not isinstance(body.get('image'), str):
            raise WorkbenchError('Supply the explicitly selected image matching this row filename.')
        declared['image_file'] = row['file']
        asset.update(name=row.get('name', row['file']), image=body['image'])
    elif 'image' in body or 'image_name' in body:
        raise WorkbenchError('Text rows cannot include image data.')
    context = dict(format='tuldok_assets_jsonl_v1', request_id=request_id,
                   row_sha256=digest, declared=declared)
    try:
        with workbench.lock:
            if find_result(workbench, request_id)['found']:
                raise WorkbenchError('This import request marker was already admitted; inspect its saved result.', 'conflict', 409)
            record = workbench.import_asset(asset, acquisition=context)
            return result(record)
    except WorkbenchError as error:
        if error.status == 404:
            raise WorkbenchError('A declared parent record was not found.') from None
        raise
    except (OSError, sqlite3.Error):
        raise WorkbenchError('Import stopped because storage failed. Inspect the collection before retrying.', 'storage', 500) from None
