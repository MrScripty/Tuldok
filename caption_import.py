"""One native image_caption_v1 decoder; asset/target owners remain canonical."""
import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3

from PIL import Image

from bulk_import import find_result, invalid_constant, leaf_name, result, unique_object
from dataset_releases import CAPTION_CONSUMER, CAPTION_FORMAT, CAPTION_SPLITS, SPLITS, connected_components
from workbench import IDENTIFIER, WorkbenchError, encode, strings, validate_annotation

MAX_SOURCE = 8 * 1024 * 1024
MAX_CONTEXT = 256 * 1024
MAX_PREPARED = 16 * 1024 * 1024
MAX_LINES = 1000
HASH = re.compile(r'^[a-f0-9]{64}$')
SNAPSHOT_KEYS = {'id', 'kind', 'revision', 'source_revision', 'content_hash', 'pixel_hash',
                 'groups', 'parents', 'source_available', 'source_lineage_known',
                 'source_split', 'source_sha256', 'book_id', 'session_id'}
RECORD_KEYS = SNAPSHOT_KEYS | {'annotation', 'asset', 'asset_sha256', 'corner_annotation',
    'created_at', 'export_group', 'export_split', 'exported_pixel_sha256', 'height', 'name',
    'provenance', 'review', 'split', 'task', 'text', 'updated_at', 'width'}
MANIFEST_KEYS = {'consumer', 'format', 'limitations', 'protected_components', 'records',
                 'schema_version', 'seed', 'split_mapping', 'split_report', 'warnings'}


def invalid(message):
    raise WorkbenchError(message)


def source_bytes(value):
    if not isinstance(value, str):
        invalid('Manifest and metadata must be UTF-8 JSON text.')
    try:
        return value.encode('utf-8')
    except UnicodeEncodeError:
        invalid('Source JSON contains invalid Unicode.')


def decode(value):
    try:
        return json.loads(value, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (json.JSONDecodeError, RecursionError):
        invalid('Source must contain complete finite JSON with unique fields.')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def is_hash(value):
    return isinstance(value, str) and bool(HASH.fullmatch(value))


def snapshot(row):
    if not isinstance(row, dict) or set(row) != SNAPSHOT_KEYS:
        invalid('Invalid protected source snapshot fields.')
    if not isinstance(row['id'], str) or not IDENTIFIER.fullmatch(row['id']):
        invalid('Invalid origin source ID.')
    if row['kind'] not in ('image', 'text', 'sequence', 'mesh', 'pointcloud') or type(row['revision']) is not int or row['revision'] < 1:
        invalid('Invalid origin kind or revision.')
    if type(row['source_available']) is not bool or row['source_lineage_known'] is not True:
        invalid('Protected source lineage must be known, including deleted members.')
    if row['kind'] == 'image' and row['source_available']:
        if type(row['source_revision']) is not int or row['source_revision'] < 1:
            invalid('Invalid image source revision.')
        if not all(is_hash(row[key]) for key in ('source_sha256', 'content_hash', 'pixel_hash')):
            invalid('Invalid image source hashes.')
    else:
        for key in ('source_sha256', 'content_hash', 'pixel_hash'):
            if row[key] not in (None, '') and not is_hash(row[key]):
                invalid('Invalid retained source hash.')
    if row['source_split'] not in (*SPLITS, 'unassigned'):
        invalid('Invalid retained source split.')
    if strings(row['groups'], 'Origin groups') != row['groups'] or not row['groups']:
        invalid('Origin groups must be canonical nonempty values.')
    if not isinstance(row['parents'], list) or len(row['parents']) > 30:
        invalid('Invalid origin parent list.')
    if any(not isinstance(parent, str) or not IDENTIFIER.fullmatch(parent) for parent in row['parents']):
        invalid('Invalid origin parent ID.')
    if len(set(row['parents'])) != len(row['parents']):
        invalid('Origin parent IDs must be unique.')
    if row['kind'] == 'image' and any(not isinstance(row[key], str) or len(row[key]) > 200 for key in ('book_id', 'session_id')):
        invalid('Invalid retained book/session links.')
    if row['kind'] == 'text' and (row['book_id'] is not None or row['session_id'] is not None or not is_hash(row['content_hash']) or not is_hash(row['source_sha256']) or row['pixel_hash'] is not None):
        invalid('Invalid protected text source snapshot.')
    if row['kind'] in ('sequence', 'mesh', 'pointcloud') and (row['book_id'] is not None or row['session_id'] is not None
            or not is_hash(row['content_hash']) or row['source_sha256'] != row['content_hash']
            or row['pixel_hash'] is not None or type(row['source_revision']) is not int
            or row['source_revision'] != 1 or row['kind'] != 'pointcloud' and row['source_split'] != 'unassigned'):
        invalid('Invalid protected ' + row['kind'] + ' source snapshot.')


def origin_groups(family):
    links = set()
    retained = set()
    for row in family:
        links.add('id:' + row['id'])
        links.update('id:' + parent for parent in row['parents'])
        for group in row['groups']:
            if group.startswith('caption-origin:') and is_hash(group.removeprefix('caption-origin:')):
                retained.add(group)
            else:
                links.add('group:' + group)
        if row['kind'] == 'image':
            links.add('legacy:' + ('book:' + row['book_id'] if row['book_id'] else 'session:' + row['session_id']))
    groups = sorted(retained | {'caption-origin:' + digest(link.encode()) for link in links})
    if not 0 < len(groups) <= 30:
        invalid('Protected component exceeds the existing 30-group import bound; no lineage can be truncated.')
    return groups


class CaptionImports:
    def __init__(self, workbench):
        self.workbench = workbench
        # Process-local integrity only. Restart invalidates preparation; no corpus
        # registry, persistent job, external credential or authenticity claim.
        self._key = secrets.token_bytes(32)

    def _seal(self, payload):
        raw = source_bytes(encode(payload))
        if len(raw) > MAX_CONTEXT:
            invalid('One protected row context exceeds 256 KiB.')
        return base64.urlsafe_b64encode(raw).decode() + '.' + hmac.new(self._key, raw, 'sha256').hexdigest()

    def _open(self, token):
        if not isinstance(token, str) or len(token) > (MAX_CONTEXT + 2) * 4 // 3 + 65:
            invalid('Invalid caption preparation envelope.')
        try:
            data, signature = token.split('.')
            raw = base64.b64decode(data, altchars=b'-_', validate=True)
            if len(raw) > MAX_CONTEXT or not is_hash(signature) or not hmac.compare_digest(signature, hmac.new(self._key, raw, 'sha256').hexdigest()):
                invalid('Caption preparation changed or expired. Choose the source folder again.')
            return json.loads(raw)
        except (ValueError, UnicodeError):
            invalid('Invalid or expired caption preparation envelope.')

    def prepare(self, body):
        if set(body) != {'manifest', 'metadata'} or not isinstance(body['metadata'], dict) or set(body['metadata']) != set(CAPTION_SPLITS.values()):
            invalid('Supply native manifest and exactly train/val/test metadata.')
        raw_manifest = source_bytes(body['manifest'])
        raw_metadata = {split: source_bytes(value) for split, value in body['metadata'].items()}
        if len(raw_manifest) + sum(map(len, raw_metadata.values())) > MAX_SOURCE:
            invalid('Combined manifest and metadata must be at most 8 MiB.')
        manifest = decode(body['manifest'])
        if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
            invalid('Supply the native image_caption_v1 manifest fields.')
        if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1 or manifest['format'] != CAPTION_FORMAT:
            invalid('Only native image_caption_v1 schema version 1 is supported.')
        if manifest['consumer'] != CAPTION_CONSUMER or manifest['split_mapping'] != CAPTION_SPLITS:
            invalid('Native consumer or split mapping does not match the supported contract.')
        records, components = manifest['records'], manifest['protected_components']
        if not isinstance(records, list) or not 3 <= len(records) <= MAX_LINES or not isinstance(components, dict):
            invalid('Supply 3–1,000 caption records and complete protected components.')
        all_members, member_ids, groups = [], set(), {}
        for group, family in components.items():
            if not isinstance(family, list) or not family or len(family) > 30:
                invalid('Invalid or oversized protected component.')
            for member in family:
                snapshot(member)
                if member['id'] in member_ids:
                    invalid('An origin member occurs more than once across components.')
                member_ids.add(member['id']); all_members.append(member)
            expected = 'component:' + digest(encode(sorted(member['id'] for member in family)).encode())
            if group != expected:
                invalid('Protected component identity does not match its complete members.')
            ids = {member['id'] for member in family}
            if any(parent not in ids for member in family for parent in member['parents']):
                invalid('A protected parent is missing from its component snapshot.')
            groups[group] = origin_groups(family)
        roots = connected_components(all_members)
        seen_roots = set()
        for family in components.values():
            family_roots = {roots[member['id']] for member in family}
            if len(family_roots) != 1 or seen_roots & family_roots:
                invalid('Protected snapshots are disconnected or cross components.')
            seen_roots.update(family_roots)
        by_asset, pixels, splits = {}, set(), {}
        for record in records:
            if not isinstance(record, dict) or set(record) != RECORD_KEYS:
                invalid('Invalid native caption record fields.')
            snapshot({key: record[key] for key in SNAPSHOT_KEYS})
            if record['kind'] != 'image' or record['task'] != 'image_caption' or record['review'] != 'human_reviewed' or record['source_available'] is not True:
                invalid('Native exports must contain available reviewed caption images; imports still become drafts.')
            if not isinstance(record['provenance'], dict) or record['text'] is not None:
                invalid('Invalid native image source provenance/text shape.')
            annotation = validate_annotation('image_caption', record['annotation'], record)
            if annotation != record['annotation']:
                invalid('Native caption is not canonical.')
            if any(type(record[key]) is not int or record[key] <= 0 for key in ('width', 'height')) or record['width'] * record['height'] > 40_000_000:
                invalid('Invalid native pixel geometry.')
            if record['split'] not in SPLITS or record['export_split'] != CAPTION_SPLITS[record['split']]:
                invalid('Native split mapping is inconsistent.')
            asset = record['export_split'] + '/' + record['id'] + '.png'
            if record['asset'] != asset or asset in by_asset:
                invalid('Native asset path is invalid or duplicated.')
            if not is_hash(record['asset_sha256']) or record['asset_sha256'] != record['content_hash'] or record['exported_pixel_sha256'] != record['pixel_hash']:
                invalid('Native asset/pixel hash claims disagree.')
            if record['pixel_hash'] in pixels:
                invalid('Native caption release contains exact pixel duplicates.')
            pixels.add(record['pixel_hash'])
            group = record['export_group']
            if not isinstance(group, str) or group not in components:
                invalid('Caption component snapshot is missing.')
            family = components[group]
            selected = next((member for member in family if member['id'] == record['id']), None)
            if selected != {key: record[key] for key in SNAPSHOT_KEYS}:
                invalid('Selected source and component snapshot disagree.')
            fixed = {member['source_split'] for member in family if member['source_split'] in SPLITS}
            if fixed - {record['split']} or group in splits and splits[group] != record['split']:
                invalid('Protected family has conflicting split assignments.')
            splits[group] = record['split']
            by_asset[asset] = record
        if set(splits) != set(components):
            invalid('Native snapshot includes a component without any selected record.')
        rows, seen_assets, physical, prepared_bytes = [], set(), 0, 0
        for split in CAPTION_SPLITS.values():
            lines = body['metadata'][split].split('\n')
            if lines[-1] == '': lines.pop()
            physical += len(lines)
            if physical > MAX_LINES:
                invalid('At most 1,000 combined physical metadata lines are supported.')
            count = 0
            for number, line in enumerate(lines, 1):
                if not line.strip(): continue
                projection = decode(line)
                if not isinstance(projection, dict) or set(projection) != {'file_name', 'text', 'group'}:
                    invalid('Metadata rows require exactly file_name, text and group.')
                filename = leaf_name(projection['file_name'], 'Caption image reference')
                asset = split + '/' + filename
                record = by_asset.get(asset)
                if not record or asset in seen_assets:
                    invalid('Metadata asset is missing, repeated or assigned to a different split.')
                if projection['text'] != record['annotation']['caption'] or projection['group'] != record['export_group']:
                    invalid('Metadata caption/group disagrees with the frozen manifest.')
                seen_assets.add(asset); count += 1
                context = dict(format=CAPTION_FORMAT, row_sha256=digest(source_bytes(line)),
                    observed={'manifest_sha256': digest(raw_manifest), 'metadata_sha256': digest(raw_metadata[split])},
                    declared={'manifest_name': 'manifest.json', 'metadata_path': split + '/metadata.jsonl',
                        'row_number': number, 'image_file': asset, 'origin_record': record,
                        'protected_component': components[record['export_group']]})
                token = self._seal(dict(context=context, groups=groups[record['export_group']]))
                prepared_bytes += len(token)
                if prepared_bytes > MAX_PREPARED:
                    invalid('Prepared caption row evidence exceeds the 16 MiB batch bound.')
                rows.append(dict(asset=asset, row_number=number, row_sha256=context['row_sha256'], token=token))
            if not count:
                invalid('Native caption import requires nonempty train, val and test metadata.')
        if seen_assets != set(by_asset):
            invalid('Manifest and metadata do not contain the same exact asset set.')
        return {'format': CAPTION_FORMAT, 'rows': rows}

    def admit(self, body):
        if set(body) != {'token', 'asset', 'image', 'request_id'}:
            invalid('Unsupported caption admission fields.')
        if not isinstance(body['request_id'], str) or not IDENTIFIER.fullmatch(body['request_id']):
            invalid('Invalid import request marker.')
        payload = self._open(body['token'])
        context, groups = payload['context'], payload['groups']
        origin = context['declared']['origin_record']
        if body['asset'] != origin['asset']:
            invalid('Selected image path does not match the prepared row.')
        try:
            if not isinstance(body['image'], str) or len(body['image']) > (25 * 1024 * 1024 + 2) * 4 // 3:
                invalid('Choose an image smaller than 25 MB.')
            raw = base64.b64decode(body['image'], validate=True)
        except ValueError:
            invalid('Invalid image data.')
        if not raw or len(raw) > 25 * 1024 * 1024 or digest(raw) != origin['asset_sha256']:
            invalid('Selected image bytes do not match the frozen asset hash.')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'PNG' or image.mode != 'RGB' or image.getexif().get(274, 1) != 1 or image.size != (origin['width'], origin['height']):
                    invalid('Native assets must be normalized RGB PNGs with matching geometry and EXIF orientation 1.')
                image.load()
                pixel_hash = digest(str(image.size).encode() + image.tobytes())
                if pixel_hash != origin['exported_pixel_sha256']:
                    invalid('Selected image pixels do not match the frozen pixel hash.')
        except (OSError, Image.DecompressionBombError):
            invalid('Unsupported or damaged caption image.')
        context['request_id'] = body['request_id']
        context['observed']['asset_sha256'] = digest(raw)
        context['observed']['pixel_sha256'] = pixel_hash
        try:
            with self.workbench.lock, self.workbench.db:
                if find_result(self.workbench, body['request_id'])['found']:
                    raise WorkbenchError('This import marker was already admitted; inspect its saved result.', 'conflict', 409)
                # Corner-studio acquisitions can arrive after the workbench was
                # opened. Enroll them before checking derived pixel identity;
                # a rejection rolls this lazy metadata/history back as well.
                universe = self.workbench._all()
                if self.workbench.db.execute('SELECT 1 FROM workbench_records WHERE id=? OR pixel_hash=?', (origin['id'], pixel_hash)).fetchone():
                    raise WorkbenchError('This source identity or exact image pixels already exist; existing records are unchanged.', 'conflict', 409)
                # A new acquisition session prevents Dataset's existing session
                # split propagation from updating older unassigned assets.
                session = 'caption-import:' + body['request_id']
                if self.workbench.db.execute("SELECT 1 FROM samples WHERE book_id='' AND session_id=?", (session,)).fetchone():
                    raise WorkbenchError('Import acquisition session already exists; existing records are unchanged.', 'conflict', 409)
                candidate = dict(id='caption-candidate:' + body['request_id'], kind='image',
                    groups=groups, parents=[], content_hash=digest(raw), pixel_hash=pixel_hash,
                    book_id='', session_id=session, source_available=True, source_lineage_known=True)
                roots = connected_components([*universe, candidate])
                related = [row for row in universe if roots[row['id']] == roots[candidate['id']]]
                if any(not row['source_lineage_known'] or row['source_split'] in SPLITS and row['source_split'] != origin['split'] for row in related):
                    raise WorkbenchError('Existing protected lineage has an unknown or conflicting source split.', 'conflict', 409)
                row = self.workbench.import_asset(dict(kind='image', image=body['image'],
                    name=origin['id'] + '.png', groups=groups, parents=[], rights='unknown'),
                    acquisition=context, annotation=origin['annotation'], source_split=origin['split'], source_session=session)
                return result(row)
        except (OSError, sqlite3.Error):
            raise WorkbenchError('Caption import storage failed. Inspect the saved result before retrying.', 'storage', 500) from None
