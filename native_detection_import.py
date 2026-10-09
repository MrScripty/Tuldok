"""Consume bounded native canonical COCO box/polygon ZIPs through image ownership."""
import base64
import hashlib
import hmac
import io
import secrets
import sqlite3
import zipfile

from PIL import Image

from bulk_import import REQUEST_ID, find_result, leaf_name, result
from dataset_releases import SPLITS, connected_components
from native_text_import import MANIFEST_KEYS, RECORD_KEYS, decode, valid_hash
from workbench import IDENTIFIER, WorkbenchError, encode, strings, validate_annotation
import image_segmentation as segmentation

MAX_ARCHIVE = 8 * 1024 * 1024
MAX_EXPANDED = 16 * 1024 * 1024
MAX_RECORDS = 100
MAX_ROW = 3 * 1024 * 1024
MAX_PREPARED = 16 * 1024 * 1024
MAX_REQUEST = 4 * 1024 * 1024 + 1024
MAX_PREPARE_REQUEST = (MAX_ARCHIVE + 2) * 4 // 3 + 1024
COORDINATES = ('Oriented image pixel-edge xywh; text spans are NFC/LF Unicode code-point [start,end). '
    'Sequence bundles preserve original named staggered fields and accepted intervals; each whole trajectory is indivisible. '
    'Static mesh bundles preserve native xyz/topology and declared units/frame; each whole mesh is indivisible.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    try:
        return encode(value).encode('utf-8')
    except (ValueError, UnicodeError, RecursionError):
        raise WorkbenchError('Native JSON must contain bounded finite values and valid Unicode.') from None


def same(actual, expected):
    # Preserve primitive types: Python equality alone equates True with 1.
    return canonical(actual) == canonical(expected)


def parse_request(raw):
    value = decode(raw)
    canonical(value)
    return value


def foreign_groups(row):
    retained = strings(row['groups'], 'Native groups')
    if not retained or retained != row['groups']:
        raise WorkbenchError('Native groups must be canonical and nonempty.')
    parents = strings(row['parents'], 'Native parents')
    if parents != row['parents'] or any(not IDENTIFIER.fullmatch(parent) for parent in parents):
        raise WorkbenchError('Native parent IDs must be valid.')
    # Reuse the existing canonical text import's foreign-ID links, including
    # cross-task parents. Upstream IDs are never installed as local parents.
    links = ['native-text-origin:' + digest(identifier.encode()) for identifier in (row['id'], *parents)]
    legacy = 'book:' + row['book_id'] if row['book_id'] else 'session:' + row['session_id']
    links.append('native-image-origin:' + digest(legacy.encode()))
    return strings(list(dict.fromkeys([*retained, *links])), 'Retained native family links')


def png(raw, row):
    if digest(raw) != row['asset_sha256'] or row['asset_sha256'] != row['content_hash']:
        raise WorkbenchError('Native image bytes do not match the asset/content hashes.')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if (image.format != 'PNG' or image.mode != 'RGB' or image.size != (row['width'], row['height'])
                    or image.width * image.height > 40_000_000 or image.getexif().get(274, 1) != 1):
                raise WorkbenchError('Native images require normalized RGB PNGs and exact oriented geometry.')
            image.load()
            measured = digest(str(image.size).encode() + image.tobytes())
            if measured != row['pixel_hash']:
                raise WorkbenchError('Native image pixels do not match the pixel hash.')
            return measured
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise WorkbenchError('Native image is damaged or exceeds the geometry bound.') from None


class NativeDetectionImports:
    def __init__(self, workbench):
        self.workbench = workbench
        self._key = secrets.token_bytes(32)

    def _seal(self, value):
        raw = canonical(value)
        if len(raw) > MAX_ROW:
            raise WorkbenchError('Prepared detection row exceeds 3 MiB.')
        return base64.urlsafe_b64encode(raw).decode() + '.' + hmac.new(self._key, raw, 'sha256').hexdigest()

    def _open(self, token):
        try:
            if not isinstance(token, str) or len(token) > (MAX_ROW + 2) * 4 // 3 + 65:
                raise ValueError()
            value, signature = token.split('.')
            raw = base64.b64decode(value, altchars=b'-_', validate=True)
            if len(raw) > MAX_ROW or not valid_hash(signature) or not hmac.compare_digest(signature, hmac.new(self._key, raw, 'sha256').hexdigest()):
                raise ValueError()
            return decode(raw)
        except ValueError:
            raise WorkbenchError('Detection preparation changed or expired. Choose the archive again.') from None

    def prepare(self, body):
        if set(body) != {'source_name', 'archive'}:
            raise WorkbenchError('Supply one selected native detection ZIP and its filename.')
        name = leaf_name(body['source_name'], 'Archive name')
        try:
            if not isinstance(body['archive'], str) or len(body['archive']) > (MAX_ARCHIVE + 2) * 4 // 3:
                raise ValueError()
            raw = base64.b64decode(body['archive'], validate=True)
            if not 0 < len(raw) <= MAX_ARCHIVE:
                raise ValueError()
        except ValueError:
            raise WorkbenchError('Choose one native detection ZIP of at most 8 MiB.') from None
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                required = {'manifest.json', 'README.txt'} | {f'{split}/{file}' for split in SPLITS for file in ('coco.json', 'records.jsonl')}
                if (len(entries) > MAX_RECORDS + 8 or len(names) != len(set(names)) or not required <= set(names)
                        or any(entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 1 for entry in entries)
                        or sum(entry.file_size for entry in entries) > MAX_EXPANDED):
                    raise WorkbenchError('Native ZIP entries are missing, ambiguous, compressed or oversized.')
                manifest_raw = archive.read('manifest.json')
                manifest = decode(manifest_raw)
                canonical(manifest)
                if (not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS
                        or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1
                        or manifest['coordinate_contract'] not in (COORDINATES,segmentation.COORDINATES)):
                    raise WorkbenchError('Only the existing native canonical_v1 coordinate/schema contract is supported.')
                records = manifest['records']
                if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
                    raise WorkbenchError('Choose a native release with 1–100 detection records.')
                report = manifest['split_report']
                if (type(manifest['seed']) is not int or not 0 <= manifest['seed'] <= 2**32 - 1
                        or not isinstance(report, dict) or set(report) != {'requested_percentages', 'actual_counts', 'independent_components', 'note'}
                        or type(report['independent_components']) is not int or not 1 <= report['independent_components'] <= len(records)
                        or not isinstance(report['requested_percentages'], dict) or set(report['requested_percentages']) != set(SPLITS)
                        or any(type(value) is not int or not 0 <= value <= 100 for value in report['requested_percentages'].values())
                        or sum(report['requested_percentages'].values()) != 100
                        or not isinstance(report['actual_counts'], dict) or not set(report['actual_counts']) <= set(SPLITS)
                        or any(type(value) is not int or not 0 <= value <= len(records) for value in report['actual_counts'].values())
                        or not isinstance(report['note'], str) or len(report['note']) > 1000):
                    raise WorkbenchError('Invalid bounded native split report or seed.')
                ids, groups = set(), {}
                for row in records:
                    if (not isinstance(row, dict) or set(row) != RECORD_KEYS or row['kind'] != 'image'
                            or row['task'] not in ('image_detection',segmentation.TASK) or not isinstance(row['id'], str)
                            or not IDENTIFIER.fullmatch(row['id']) or row['id'] in ids):
                        raise WorkbenchError('Only unique exact native detection/segmentation record fields are supported.')
                    ids.add(row['id'])
                    if (row['asset'] != 'assets/' + row['id'] + '.png' or row['split'] not in SPLITS
                            or row['source_split'] not in (*SPLITS, 'unassigned')
                            or row['source_split'] not in ('unassigned', row['split'])
                            or row['review'] not in ('human_reviewed', 'programmatically_verified')
                            or row['source_available'] is not True or row['source_lineage_known'] is not True
                            or any(type(row[key]) is not int or row[key] < 1 for key in ('revision', 'source_revision', 'width', 'height'))
                            or row['width'] * row['height'] > 40_000_000 or row['text'] is not None
                            or not isinstance(row['provenance'], dict)
                            or any(not valid_hash(row[key]) for key in ('source_sha256', 'content_hash', 'pixel_hash', 'asset_sha256'))):
                        raise WorkbenchError('Invalid native detection geometry, source status, hashes or split binding.')
                    for key in ('book_id', 'session_id'):
                        if not isinstance(row[key], str) or len(row[key]) > 200:
                            raise WorkbenchError('Invalid declared native book/session link.')
                    if row['task'] == segmentation.TASK and row['review'] != 'human_reviewed':
                        raise WorkbenchError('Native polygon evidence requires declared human review; local approval is still separate.')
                    target = validate_annotation(row['task'], row['annotation'], row)
                    if not same(target, row['annotation']):
                        raise WorkbenchError('Native detection targets must already be canonical.')
                    groups[row['id']] = foreign_groups(row)
                if manifest['coordinate_contract'] != (segmentation.COORDINATES if segmentation.present(records) else COORDINATES):
                    raise WorkbenchError('Native coordinate contract differs from its exact target tasks.')
                if segmentation.present(records):
                    segmentation.selection_bounds(records)
                counts = {split: sum(row['split'] == split for row in records) for split in SPLITS}
                if report['actual_counts'] != {split: count for split, count in counts.items() if count}:
                    raise WorkbenchError('Native split counts differ from the selected records.')
                if set(names) != required | {row['asset'] for row in records}:
                    raise WorkbenchError('Native archive paths must exactly match the detection assets.')
                # Check exactly the foreign links that admissions will retain,
                # including aliases between declared groups and generated links.
                retained = [dict(row, groups=groups[row['id']], parents=[], book_id='',
                    session_id='native-candidate:' + row['id']) for row in records]
                roots = connected_components(retained)
                partitions = {}
                for row in records:
                    root = roots[row['id']]
                    if root in partitions and partitions[root] != row['split']:
                        raise WorkbenchError('Retained native family links conflict across exported splits.')
                    partitions[root] = row['split']
                vocabulary = sorted({target['label'] for row in records for target in segmentation.targets(row)})
                if not same(manifest['vocabulary'], vocabulary):
                    raise WorkbenchError('Native vocabulary differs from its detection targets.')
                categories = {label: number + 1 for number, label in enumerate(vocabulary)}
                projections = {split: dict(info=dict(description='Tuldok detection release', version='1'), licenses=[],
                    images=[], annotations=[], categories=[dict(id=number, name=label) for label, number in categories.items()]) for split in SPLITS}
                for number, row in enumerate(records, 1):
                    projection = projections[row['split']]
                    projection['images'].append(dict(id=number, file_name=row['asset'], width=row['width'], height=row['height']))
                    for target in segmentation.targets(row):
                        projection['annotations'].append(segmentation.coco_target(target,row['task'],len(projection['annotations'])+1,number,categories[target['label']]))
                hashes = {}
                for split in SPLITS:
                    coco_raw = archive.read(split + '/coco.json')
                    if archive.read(split + '/records.jsonl') != b'' or not same(decode(coco_raw), projections[split]):
                        raise WorkbenchError('Native COCO projection differs from its manifest or contains unsupported metadata rows.')
                    hashes[split] = digest(coco_raw)
                rows, total = [], 0
                for number, row in enumerate(records, 1):
                    asset = archive.read(row['asset'])
                    measured = png(asset, row)
                    row_hash = digest(canonical(row))
                    context = dict(format='canonical_v1', archive_sha256=digest(raw), manifest_sha256=digest(manifest_raw),
                        coco_sha256=hashes, row_sha256=row_hash, row_hash_basis='canonical_parsed_manifest_record',
                        asset_sha256=digest(asset), input_sha256=digest(asset), pixel_sha256=measured,
                        input_basis='consumed_exported_png', upstream_graph='selected_declared_links_only',
                        declared=dict(archive_name=name, metadata_path='manifest.json', row_number=number,
                            asset=row['asset'], upstream=dict(record=row, original_status='unavailable',
                                category_table=projections[row['split']]['categories'],
                                annotation_category_ids=[categories[target['label']] for target in segmentation.targets(row)])))
                    token = self._seal(dict(image=base64.b64encode(asset).decode(), groups=groups[row['id']], context=context))
                    total += len(token)
                    if total > MAX_PREPARED:
                        raise WorkbenchError('Combined prepared detection evidence exceeds 16 MiB.')
                    rows.append(dict(metadata_path='manifest.json', row_number=number, row_sha256=row_hash, token=token))
                return dict(format='canonical_v1', schema_version=1, archive_sha256=digest(raw), rows=rows,
                    input_basis='consumed_exported_png', upstream_original='unavailable', upstream_graph='selected_declared_links_only')
        except (zipfile.BadZipFile, EOFError, KeyError, RuntimeError, OSError, NotImplementedError):
            raise WorkbenchError('Native detection ZIP is damaged or incomplete.') from None

    def admit(self, body):
        if set(body) != {'token', 'request_id'} or not isinstance(body['request_id'], str) or not REQUEST_ID.fullmatch(body['request_id']):
            raise WorkbenchError('Supply one prepared detection row and request marker.')
        payload = self._open(body['token'])
        context = dict(payload['context'], request_id=body['request_id'])
        origin = context['declared']['upstream']['record']
        w = self.workbench
        try:
            with w.lock, w.db:
                if find_result(w, body['request_id'])['found']:
                    raise WorkbenchError('This marker was already admitted; inspect its saved result.', 'conflict', 409)
                universe = w._all()
                if w.db.execute('SELECT 1 FROM workbench_records WHERE id=? OR pixel_hash=?', (origin['id'], context['pixel_sha256'])).fetchone():
                    raise WorkbenchError('Native source identity or exact pixels already exist; existing records are unchanged.', 'conflict', 409)
                session = 'native-detection:' + body['request_id']
                if w.db.execute("SELECT 1 FROM samples WHERE book_id='' AND session_id=?", (session,)).fetchone():
                    raise WorkbenchError('Import acquisition session already exists.', 'conflict', 409)
                candidate = dict(id='detection-candidate:' + body['request_id'], kind='image', groups=payload['groups'],
                    parents=[], content_hash=context['input_sha256'], pixel_hash=context['pixel_sha256'], book_id='',
                    session_id=session, source_available=True, source_lineage_known=True)
                roots = connected_components([*universe, candidate])
                related = [row for row in universe if roots[row['id']] == roots[candidate['id']]]
                if any(not row['source_lineage_known'] or row['source_split'] in SPLITS and row['source_split'] != origin['split'] for row in related):
                    raise WorkbenchError('Existing protected lineage has an unknown or conflicting source split.', 'conflict', 409)
                row = w.import_asset(dict(kind='image', image=payload['image'], name=origin['id'] + '.png',
                    groups=payload['groups'], parents=[], rights='unknown'), acquisition=context,
                    annotation=origin['annotation'], annotation_task=origin['task'], source_split=origin['split'], source_session=session)
                return result(row)
        except (OSError, sqlite3.Error):
            raise WorkbenchError('Detection import storage failed. Inspect the saved result before retrying.', 'storage', 500) from None
