"""Bounded canonical_v1 classification ZIP ingestion; Workbench owns insertion."""
import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
import zipfile

from bulk_import import MAX_ROW_BYTES, REQUEST_ID, find_result, invalid_constant, leaf_name, result, unique_object
from workbench import IDENTIFIER, MAX_TEXT, WorkbenchError, encode, strings, text_value, validate_annotation

MAX_ARCHIVE = 8 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024
MAX_ROWS = 1000
MAX_OUTCOMES = 2 * MAX_ROWS  # Physical-row errors plus absent manifest records.
MAX_ENVELOPE = 4 * 1024 * 1024
SPLITS = ('train', 'validation', 'test')
HASH = re.compile(r'^[a-f0-9]{64}$')
MANIFEST_KEYS = {'schema_version', 'seed', 'split_report', 'coordinate_contract', 'limitations', 'records', 'vocabulary'}
RECORD_KEYS = {'annotation', 'asset', 'asset_sha256', 'book_id', 'content_hash', 'corner_annotation',
    'created_at', 'groups', 'height', 'id', 'kind', 'name', 'parents', 'pixel_hash', 'provenance',
    'review', 'revision', 'session_id', 'source_available', 'source_lineage_known', 'source_revision',
    'source_sha256', 'source_split', 'split', 'task', 'text', 'updated_at', 'width'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except WorkbenchError:
        raise
    except (ValueError, RecursionError):
        # Includes UTF-8/JSON syntax and the runtime's integer conversion limit;
        # callers retain their archive-level or individual-row failure boundary.
        raise WorkbenchError('Native JSON must be complete UTF-8 with unique fields, finite values and bounded numbers.') from None


def valid_hash(value):
    return isinstance(value, str) and bool(HASH.fullmatch(value))


class NativeTextImports:
    def __init__(self, workbench):
        self.workbench = workbench
        self._key = secrets.token_bytes(32)

    def _seal(self, payload):
        try:
            raw = encode(payload).encode('utf-8')
        except UnicodeError:
            raise WorkbenchError('Declared row metadata must contain valid Unicode without lone surrogates.') from None
        except ValueError:
            raise WorkbenchError('Declared row metadata must contain finite JSON values.') from None
        if len(raw) > MAX_ROW_BYTES:
            raise WorkbenchError('Prepared row exceeds the 3 MiB bound.')
        return base64.urlsafe_b64encode(raw).decode() + '.' + hmac.new(self._key, raw, 'sha256').hexdigest()

    def _open(self, token):
        try:
            if not isinstance(token, str) or len(token) > MAX_ENVELOPE + 65:
                raise ValueError()
            data, signature = token.split('.')
            raw = base64.b64decode(data, altchars=b'-_', validate=True)
            if len(raw) > MAX_ROW_BYTES or not valid_hash(signature) or not hmac.compare_digest(signature, hmac.new(self._key, raw, 'sha256').hexdigest()):
                raise ValueError()
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise WorkbenchError('Native text preparation changed or expired. Choose the archive again.') from None

    def prepare(self, body):
        if set(body) != {'source_name', 'archive'}:
            raise WorkbenchError('Supply exactly one selected native release ZIP and its filename.')
        source_name = leaf_name(body['source_name'], 'Archive name')
        try:
            value = body['archive']
            if not isinstance(value, str) or len(value) > (MAX_ARCHIVE + 2) * 4 // 3:
                raise ValueError()
            raw = base64.b64decode(value, validate=True)
            if not 0 < len(raw) <= MAX_ARCHIVE:
                raise ValueError()
        except ValueError:
            raise WorkbenchError('Select a base64 native ZIP of at most 8 MiB.') from None
        archive_hash = digest(raw)
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                required = {'manifest.json', 'README.txt'} | {f'{split}/{name}' for split in SPLITS for name in ('records.jsonl', 'coco.json')}
                if len(entries) > 1010 or len(names) != len(set(names)) or not required <= set(names):
                    raise WorkbenchError('Native ZIP entries are missing, ambiguous or exceed the bound.')
                if any(name not in required and not re.fullmatch(r'assets/[a-f0-9]{32}\.(txt|png|zip)', name) for name in names):
                    raise WorkbenchError('ZIP contains unsupported native paths.')
                if any(entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 1 for entry in entries):
                    raise WorkbenchError('Only unencrypted stored entries from the native exporter are supported.')
                if sum(entry.file_size for entry in entries) > MAX_EXPANDED:
                    raise WorkbenchError('Expanded native ZIP exceeds 16 MiB.')
                manifest_raw = archive.read('manifest.json')
                manifest_hash = digest(manifest_raw)
                manifest = decode(manifest_raw)
                if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
                    raise WorkbenchError('Supply the native canonical_v1 manifest with schema_version 1.')
                if not isinstance(manifest['records'], list) or not 0 < len(manifest['records']) <= MAX_ROWS:
                    raise WorkbenchError('Native manifest requires 1–1,000 records.')
                origins = {}
                for row in manifest['records']:
                    if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not IDENTIFIER.fullmatch(row['id']) or row['id'] in origins:
                        raise WorkbenchError('Native manifest record identities must be valid and unique.')
                    origins[row['id']] = row
                rows, physical_count, seen = [], 0, set()
                for split in SPLITS:
                    metadata_path = f'{split}/records.jsonl'
                    metadata_raw = archive.read(metadata_path)
                    metadata_hash = digest(metadata_raw)
                    lines = metadata_raw.split(b'\n')
                    if lines[-1] == b'':
                        lines.pop()
                    physical_count += len(lines)
                    if physical_count > MAX_ROWS:
                        raise WorkbenchError('Native metadata exceeds 1,000 physical lines.')
                    for number, line in enumerate(lines, 1):
                        if not line.strip():
                            continue
                        outcome = {'metadata_path': metadata_path, 'row_number': number, 'row_sha256': digest(line)}
                        try:
                            if len(line) > MAX_ROW_BYTES:
                                raise WorkbenchError('Native metadata row exceeds 3 MiB.')
                            row = decode(line)
                            if isinstance(row, dict) and isinstance(row.get('id'), str) and row['id'] in origins:
                                identified = row['id']
                            else:
                                identified = None
                            if not isinstance(row, dict) or set(row) != RECORD_KEYS or row.get('kind') != 'text' or row.get('task') != 'text_classification':
                                if identified:
                                    seen.add(identified)
                                raise WorkbenchError('Only exact native text_classification record fields are supported.')
                            if not isinstance(row['id'], str) or not IDENTIFIER.fullmatch(row['id']):
                                raise WorkbenchError('Invalid native text record ID.')
                            if row['id'] in seen or origins.get(row['id']) != row or row['split'] != split:
                                raise WorkbenchError('Native row is repeated or differs from its manifest/split binding.')
                            seen.add(row['id'])
                            payload = self._row(archive, row)
                            context = {'format': 'canonical_v1', 'archive_sha256': archive_hash,
                                'manifest_sha256': manifest_hash, 'metadata_sha256': metadata_hash,
                                'row_sha256': digest(line), 'asset_sha256': digest(payload['text'].encode('utf-8')),
                                'input_sha256': digest(payload['text'].encode('utf-8')),
                                'input_basis': 'consumed_exported_text',
                                'declared': {'archive_name': source_name, 'metadata_path': metadata_path,
                                    'row_number': number, 'asset': row['asset'],
                                    'upstream': {'record': row, 'original_status': 'unavailable'}}}
                            payload['context'] = context
                            outcome.update(asset=row['asset'], token=self._seal(payload))
                        except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as error:
                            outcome['error'] = 'Referenced native text asset is damaged.'
                        except WorkbenchError as error:
                            outcome['error'] = str(error)
                        rows.append(outcome)
                for identifier, origin in origins.items():
                    if origin.get('kind') == 'text' and origin.get('task') == 'text_classification' and identifier not in seen:
                        rows.append({'metadata_path': str(origin.get('split')) + '/records.jsonl',
                            'row_number': None, 'error': 'Manifest classification record has no matching metadata row: ' + identifier})
                if len(rows) > MAX_OUTCOMES:
                    raise WorkbenchError('Native preparation exceeds the bounded outcome count.')
                if not rows:
                    raise WorkbenchError('Native archive has no classification metadata rows.')
                return {'format': 'canonical_v1', 'schema_version': 1, 'archive_sha256': archive_hash, 'rows': rows,
                        'input_basis': 'consumed_exported_text', 'upstream_original': 'unavailable'}
        except (zipfile.BadZipFile, EOFError, KeyError, RuntimeError, OSError, NotImplementedError):
            raise WorkbenchError('Native ZIP is damaged or a referenced asset is missing.') from None

    def _row(self, archive, row):
        if not IDENTIFIER.fullmatch(row['id']) or row['asset'] != 'assets/' + row['id'] + '.txt':
            raise WorkbenchError('Text asset must exactly match its native record ID.')
        text_value(row['text'], 'Exported text', MAX_TEXT)
        name = text_value(row['name'], 'Name')
        groups = strings(row['groups'], 'Protected groups')
        if not groups or groups != row['groups']:
            raise WorkbenchError('Native protected groups must be canonical and nonempty.')
        parents = strings(row['parents'], 'Declared parents')
        if any(not IDENTIFIER.fullmatch(parent) for parent in parents):
            raise WorkbenchError('Invalid declared upstream parent ID.')
        # Stable foreign identity links preserve relationships without interpreting
        # upstream UUIDs as local parents or inheriting source split authority.
        links = ['native-text-origin:' + digest(identifier.encode()) for identifier in (row['id'], *parents)]
        groups = strings(list(dict.fromkeys([*groups, *links])), 'Protected groups')
        if not isinstance(row['provenance'], dict) or not valid_hash(row['source_sha256']):
            raise WorkbenchError('Invalid declared native provenance or original hash.')
        if row['source_available'] is not True or row['source_lineage_known'] is not True or type(row['revision']) is not int or row['revision'] < 1 or type(row['source_revision']) is not int or row['source_revision'] != 1:
            raise WorkbenchError('Invalid native text revision/source status.')
        if row['source_split'] != 'unassigned' or any(row[key] is not None for key in ('book_id', 'session_id', 'pixel_hash', 'width', 'height', 'corner_annotation')):
            raise WorkbenchError('Unsupported native text source fields.')
        target = validate_annotation('text_classification', row['annotation'], {'kind': 'text', 'text': row['text']})
        if target != row['annotation']:
            raise WorkbenchError('Native classification target must already be canonical.')
        if row['asset'] not in archive.namelist():
            raise WorkbenchError('Referenced native text asset is missing.')
        asset = archive.read(row['asset'])
        if asset != row['text'].encode('utf-8') or not valid_hash(row['asset_sha256']) or digest(asset) != row['asset_sha256'] or row['content_hash'] != digest(asset):
            raise WorkbenchError('Text asset, exported text and canonical hashes must match exactly.')
        return {'text': row['text'], 'name': name, 'groups': groups, 'annotation': target}

    def admit(self, body):
        if set(body) != {'token', 'request_id'} or not isinstance(body['request_id'], str) or not REQUEST_ID.fullmatch(body['request_id']):
            raise WorkbenchError('Supply one prepared native text token and request marker.')
        payload = self._open(body['token'])
        context = dict(payload['context'], request_id=body['request_id'])
        w = self.workbench
        try:
            with w.lock, w.db:
                if find_result(w, body['request_id'])['found']:
                    raise WorkbenchError('This import request marker was already admitted; inspect its saved result.', 'conflict', 409)
                record = w._insert_text(payload['text'], payload['name'], payload['groups'], [], 'unknown',
                    provenance={'acquisition': context}, annotation=payload['annotation'])
                receipt = result(record)
            return receipt
        except (OSError, sqlite3.Error):
            raise WorkbenchError('Import stopped because storage failed. Inspect the collection before retrying.', 'storage', 500) from None
