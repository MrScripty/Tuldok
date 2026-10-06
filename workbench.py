"""Image/text dataset lifecycle, sharing Tuldok's existing image authority."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import unicodedata
import uuid

from PIL import Image

TASKS = ('image_detection', 'image_classification', 'image_caption', 'text_classification', 'text_entities')
REVIEWS = ('draft', 'human_reviewed', 'programmatically_verified')
MAX_TEXT = 200_000  # Code points per synchronous text import.
MAX_CAPTION = 4_000  # Human-authored target, separate from generation provenance.
MAX_TARGETS = 500  # Bound annotation decoding and editor work per record.
PAGE_SIZE = 40
IDENTIFIER = re.compile(r'^[a-f0-9]{32}$')


class WorkbenchError(ValueError):
    def __init__(self, message, code='invalid', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def text_value(value, name, maximum=200, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()):
        raise WorkbenchError(f'{name} must be text, 1–{maximum} characters.')
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise WorkbenchError(f'{name} contains an invalid Unicode surrogate.')
    return value.strip()


def strings(value, name, maximum=30):
    if not isinstance(value, list) or len(value) > maximum:
        raise WorkbenchError(f'{name} must be a list of at most {maximum} values.')
    result = [text_value(item, name, 120) for item in value]
    if len(set(result)) != len(result):
        raise WorkbenchError(f'{name} contains duplicates.')
    return result


def validate_annotation(task, value, record):
    """Canonical target semantics; imported unknown fields are rejected."""
    if task not in TASKS or not task.startswith(record['kind'] + '_'):
        raise WorkbenchError('Choose a task matching the asset type.')
    if not isinstance(value, dict):
        raise WorkbenchError('Annotation must be an object.')
    if task == 'image_caption':
        if set(value) != {'caption'}:
            raise WorkbenchError('Image caption requires exactly one caption field.')
        return {'caption': text_value(value['caption'], 'Caption', MAX_CAPTION)}
    if task.endswith('_classification'):
        if set(value) != {'label'}:
            raise WorkbenchError('Classification requires exactly one label.')
        return {'label': text_value(value['label'], 'Class label', 80)}
    key = 'boxes' if task == 'image_detection' else 'spans'
    if set(value) != {key} or not isinstance(value[key], list) or len(value[key]) > MAX_TARGETS:
        raise WorkbenchError(f'Provide {key}, with at most {MAX_TARGETS} targets; an empty list means a reviewed negative.')
    targets = []
    for target in value[key]:
        expected = {'label', 'x', 'y', 'width', 'height'} if key == 'boxes' else {'label', 'start', 'end'}
        if not isinstance(target, dict) or set(target) != expected:
            raise WorkbenchError(f'Invalid {key} fields.')
        label = text_value(target['label'], 'Target label', 80)
        if key == 'boxes':
            x, y, width, height = (target[k] for k in ('x', 'y', 'width', 'height'))
            if any(type(n) not in (int, float) or not math.isfinite(n) for n in (x, y, width, height)):
                raise WorkbenchError('Box coordinates must be finite numbers.')
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > record['width'] or y + height > record['height']:
                raise WorkbenchError('Boxes must fit oriented image pixel edges, with positive width and height.')
            targets.append(dict(label=label, x=x, y=y, width=width, height=height))
        else:
            start, end = target['start'], target['end']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(record['text']):
                raise WorkbenchError('Spans use Unicode code-point offsets: 0 ≤ start < end ≤ text length.')
            targets.append(dict(label=label, start=start, end=end))
    if len({encode(item) for item in targets}) != len(targets):
        raise WorkbenchError('Duplicate annotation targets are not allowed.')
    return {key: targets}


def labels(record):
    annotation = record.get('annotation')
    if not annotation:
        return []
    if 'label' in annotation:
        return [annotation['label']]
    return [item['label'] for item in annotation.get('boxes', annotation.get('spans', []))]


def rights_note(record):
    """Display/query metadata only; a present note is not evidence of permission."""
    correction = record['provenance'].get('rights_note_correction')
    note = correction['note'] if isinstance(correction, dict) and isinstance(correction.get('note'), str) else record['provenance'].get('rights')
    return note.strip() if isinstance(note, str) and note.strip() else 'unknown'


class Workbench:
    """Own generic targets/text; Dataset retains original images and corners.

    All SQLite access uses the Dataset lock. Image state is joined at read time,
    not copied into a competing asset database. Annotation history is append-only.
    """
    def __init__(self, dataset):
        self.dataset = dataset
        self.db, self.lock = dataset.db, dataset.lock
        with self.lock, self.db:
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_records (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('image','text')),
                name TEXT, text TEXT, original_text TEXT,
                content_hash TEXT NOT NULL, pixel_hash TEXT,
                groups_json TEXT NOT NULL, parents_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL, task TEXT NOT NULL,
                annotation_json TEXT, review TEXT NOT NULL,
                revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id, revision))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_rights_notes (
                id TEXT PRIMARY KEY, note TEXT NOT NULL, revision INTEGER NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS workbench_content ON workbench_records(content_hash)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_deleted_sources (
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL, session_id TEXT NOT NULL,
                split TEXT NOT NULL)''')

    def _sync_images(self):
        # Enrol only new images. Hashing is streaming and never rewrites originals.
        rows = self.db.execute('''SELECT s.* FROM samples s LEFT JOIN workbench_records w
            ON w.id=s.id WHERE w.id IS NULL''').fetchall()
        for row in rows:
            path = self.dataset.path / 'images' / row['id'] / 'image.png'
            try:
                content_hash = file_hash(path)
                with Image.open(path) as image:
                    pixel_hash = hashlib.sha256(str(image.size).encode() + image.convert('RGB').tobytes()).hexdigest()
            except (OSError, ValueError):
                # The record stays visible and release validation reports missing bytes.
                content_hash, pixel_hash = '', ''
            group = 'book:' + row['book_id'] if row['book_id'] else 'session:' + row['session_id']
            generation = self.dataset.db.execute('SELECT data FROM generation_entries WHERE data LIKE ?', ('%' + row['id'] + '%',)).fetchall()
            origin = {'method': 'import', 'source_sha256': row['sha256'], 'rights': 'unknown'}
            for item in generation:
                entry = json.loads(item[0])
                if entry.get('sample_id') == row['id']:
                    origin = {'method': 'model_generated', 'source_sha256': row['sha256'], 'rights': 'unknown',
                              'generation': {k: entry[k] for k in ('job_id', 'ordinal', 'prompt', 'metadata', 'model', 'size', 'width', 'height', 'requested_seed') if k in entry}}
            self.db.execute('INSERT INTO workbench_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (row['id'], 'image', None, None, None, content_hash, pixel_hash,
                             encode([group]), '[]', encode(origin), 'image_detection', None,
                             'draft', 1, row['created_at'], row['created_at']))
            self._history(self._get(row['id']))

    def preserve_deleted_source(self, record_id):
        """Called in Dataset's deletion transaction before removing source authority."""
        self.db.execute('''INSERT INTO workbench_deleted_sources
            SELECT id, book_id, session_id, split FROM samples WHERE id=?''', (record_id,))

    def _get(self, record_id):
        row = self.db.execute('''SELECT w.*, s.filename AS image_name, s.width, s.height,
            s.revision AS source_revision, s.sha256 AS source_sha256,
            s.book_id, s.session_id, s.split AS source_split, s.annotation AS corner_annotation
            FROM workbench_records w LEFT JOIN samples s ON s.id=w.id
            WHERE w.id=?''', (record_id,)).fetchone()
        if not row:
            raise WorkbenchError('Record not found.', 'unavailable', 404)
        result = dict(row)
        result['source_available'] = result['kind'] == 'text' or result['source_revision'] is not None
        result['source_lineage_known'] = result['source_available']
        if result['kind'] == 'image':
            if not result['source_available']:
                retained = self.db.execute('SELECT book_id, session_id, split AS source_split FROM workbench_deleted_sources WHERE id=?', (record_id,)).fetchone()
                if retained:
                    result.update(dict(retained))
                    result['source_lineage_known'] = True
            result['name'] = result.pop('image_name') or '(source image deleted)'
        else:
            result.pop('image_name')
            result['source_revision'] = 1
            result['source_split'] = 'unassigned'
            result['source_sha256'] = hashlib.sha256(result['original_text'].encode()).hexdigest()
        for field in ('groups', 'parents', 'provenance', 'annotation'):
            raw = result.pop(field + '_json')
            result[field] = json.loads(raw) if raw is not None else None
        correction = self.db.execute('SELECT note,revision FROM workbench_rights_notes WHERE id=?', (record_id,)).fetchone()
        if correction is not None:
            result['provenance']['rights_note_correction'] = dict(correction)
        result.pop('original_text')
        if result['corner_annotation']:
            result['corner_annotation'] = json.loads(result['corner_annotation'])
        return result

    def get(self, record_id):
        if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
            raise WorkbenchError('Invalid record ID.')
        with self.lock, self.db:
            self._sync_images()
            return self._get(record_id)

    def _history(self, record):
        self.db.execute('INSERT INTO workbench_history VALUES (?,?,?)',
                        (record['id'], record['revision'], encode(record)))

    def history(self, record_id):
        self.get(record_id)
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute(
                'SELECT snapshot FROM workbench_history WHERE id=? ORDER BY revision DESC', (record_id,))]

    def _all(self):
        self._sync_images()
        return [self._get(row[0]) for row in self.db.execute('SELECT id FROM workbench_records').fetchall()]

    def query(self, options):
        """Page metadata and excerpts. Asset bytes are never loaded for browsing."""
        query = text_value(options.get('q', ''), 'Search', 200, empty=True).casefold()
        kind, review, sort, task = (options.get(k, '') for k in ('kind', 'review', 'sort', 'task'))
        if kind not in ('', 'image', 'text') or review not in ('', *REVIEWS) or sort not in ('', 'newest', 'oldest', 'name', 'review'):
            raise WorkbenchError('Invalid filter or sort.')
        if task not in ('', *TASKS):
            raise WorkbenchError('Invalid task filter.')
        label = text_value(options.get('label', ''), 'Label filter', 80, empty=True)
        group = text_value(options.get('group', ''), 'Protected source/group filter', 120, empty=True)
        rights = text_value(options.get('rights', ''), 'Rights-note filter', 1000, empty=True)
        try:
            offset, limit = int(options.get('offset', 0)), int(options.get('limit', PAGE_SIZE))
        except (ValueError, TypeError):
            raise WorkbenchError('Invalid pagination.') from None
        if offset < 0 or not 1 <= limit <= 100:
            raise WorkbenchError('Page size must be 1–100 and offset nonnegative.')
        with self.lock, self.db:
            rows = self._all()
            filtered = [r for r in rows if (not kind or r['kind'] == kind) and (not review or r['review'] == review)
                        and (not task or r['task'] == task)
                        and (not label or label in labels(r))
                        and (not group or group in r['groups'])
                        and (not rights or rights_note(r) == rights)
                        and (not query or query in ' '.join([r['name'], r.get('text') or '',
                            (r['annotation'] or {}).get('caption', ''), *r['groups'], *labels(r)]).casefold())]
            key = {'name': lambda r: (r['name'].casefold(), r['id']),
                   'review': lambda r: (r['review'], r['created_at'], r['id'])}.get(sort, lambda r: (r['created_at'], r['id']))
            filtered.sort(key=key, reverse=sort in ('', 'newest'))
            summary = analyze(filtered)
            page = []
            for record in filtered[offset:offset + limit]:
                record = dict(record)
                record['excerpt'] = (record.pop('text') or '')[:180]
                record.pop('corner_annotation')
                record['rights_note'] = rights_note(record)
                page.append(record)
            return {'items': page, 'total': len(filtered), 'offset': offset, 'limit': limit, 'analysis': summary}

    def import_asset(self, body, *, acquisition=None):
        kind = body.get('kind')
        groups = strings(body.get('groups', []), 'Protected groups')
        if not groups:
            raise WorkbenchError('Supply at least one protected source/group ID.')
        rights = text_value(body.get('rights', 'unknown'), 'Rights / permission note', 1000)
        parents = strings(body.get('parents', []), 'Parent IDs')
        with self.lock, self.db:
            self._sync_images()
            for parent in parents:
                self._get(parent)
            if kind == 'image':
                # Reuse the existing normalizer, original storage and dedup contract.
                row = self.dataset.add({'image': body.get('image'), 'filename': body.get('name', 'image.png'),
                                        'session_id': groups[0], 'book_id': '', 'split': 'unassigned'},
                                       enrollment=(groups, parents, rights, acquisition))
                return self._get(row['id'])
            if kind != 'text':
                raise WorkbenchError('Asset kind must be image or text.')
            return self._insert_text(body.get('text'), body.get('name', 'Text record'), groups, parents, rights,
                                     provenance={'acquisition': acquisition} if acquisition is not None else None)

    def _enroll_import(self, sample_id, groups, parents, rights, acquisition=None):
        """Called only inside Dataset.add's acquisition transaction and lock."""
        self._sync_images()
        record = self._get(sample_id)
        origin = dict(record['provenance'], rights=rights)
        if acquisition is not None:
            origin['acquisition'] = acquisition
        self.db.execute('UPDATE workbench_records SET groups_json=?,parents_json=?,provenance_json=? WHERE id=?',
                        (encode(groups), encode(parents), encode(origin), sample_id))
        # Initial enrollment is internal, not a second user-visible revision.
        self.db.execute('DELETE FROM workbench_history WHERE id=?', (sample_id,))
        self._history(self._get(sample_id))

    def _insert_text(self, source, name, groups, parents, rights, *, provenance=None, annotation=None):
        """Insert inside the caller's lock/transaction, including candidate admission."""
        text_value(source, 'Text', MAX_TEXT)
        text = unicodedata.normalize('NFC', source.replace('\r\n', '\n').replace('\r', '\n'))
        name = text_value(name, 'Name')
        digest = hashlib.sha256(text.encode()).hexdigest()
        if self.db.execute("SELECT 1 FROM workbench_records WHERE kind='text' AND content_hash=?", (digest,)).fetchone():
            raise WorkbenchError('This canonical text already exists.', 'conflict', 409)
        if annotation is not None:
            annotation = validate_annotation('text_classification', annotation, {'kind': 'text', 'text': text})
        origin = {'method': 'import', 'rights': rights, 'normalization': 'NFC; LF newlines'}
        if provenance is not None:
            origin.update(provenance)
        record_id, created = uuid.uuid4().hex, timestamp()
        self.db.execute('INSERT INTO workbench_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (record_id, 'text', name, text, source, digest, None, encode(groups), encode(parents),
                         encode(origin), 'text_classification', encode(annotation) if annotation is not None else None,
                         'draft', 1, created, created))
        record = self._get(record_id)
        self._history(record)
        return record

    def save(self, record_id, body, *, verified_provenance=None):
        with self.lock, self.db:
            self._sync_images()
            before = self._get(record_id)
            for key in ('revision', 'source_revision'):
                if type(body.get(key)) is not int or body[key] != before[key]:
                    raise WorkbenchError('This record or source changed. Reload before saving.', 'conflict', 409)
            if not before['source_available']:
                raise WorkbenchError('The source image was deleted.', 'unavailable', 409)
            task = body.get('task')
            annotation = validate_annotation(task, body.get('annotation'), before)
            groups = strings(body.get('groups'), 'Protected groups')
            if not groups:
                raise WorkbenchError('Keep at least one protected group.')
            review = body.get('review')
            if review not in ('draft', 'human_reviewed') and not (review == 'programmatically_verified' and verified_provenance):
                raise WorkbenchError('Only an owned verifier can grant programmatic verification.')
            # The read projection includes owned rights corrections; preserve stored origin separately.
            provenance = verified_provenance or json.loads(self.db.execute(
                'SELECT provenance_json FROM workbench_records WHERE id=?', (record_id,)).fetchone()[0])
            self.db.execute('''UPDATE workbench_records SET task=?,annotation_json=?,review=?,groups_json=?,
                provenance_json=?,revision=revision+1,updated_at=? WHERE id=?''',
                            (task, encode(annotation), review, encode(groups), encode(provenance), timestamp(), record_id))
            record = self._get(record_id)
            self._history(record)
            return record

    def correct_rights_note(self, record_id, body):
        """One note correction, CAS-bound to record/source revisions; no annotation grant."""
        if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
            raise WorkbenchError('Invalid record ID.')
        if not isinstance(body, dict) or set(body) != {'revision', 'source_revision', 'note'}:
            raise WorkbenchError('Supply only current record/source revisions and a rights note.')
        note = text_value(body['note'], 'Rights note', 1000, empty=True) or 'unknown'
        with self.lock, self.db:
            before = self._get(record_id)
            for key in ('revision', 'source_revision'):
                if type(body[key]) is not int or body[key] != before[key]:
                    raise WorkbenchError('This record or source changed. Reload before correcting the note.', 'conflict', 409)
            if not before['source_available']:
                raise WorkbenchError('The source image was deleted.', 'unavailable', 409)
            if note == rights_note(before):
                return {'record': before, 'changed': False}
            origin = json.loads(self.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (record_id,)).fetchone()[0])
            if 'rights_note_correction' in origin:
                raise WorkbenchError('Stored origin uses the reserved correction field; cannot replace origin evidence.', 'conflict', 409)
            self.db.execute('INSERT INTO workbench_rights_notes VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET note=excluded.note,revision=excluded.revision',
                            (record_id, note, before['revision'] + 1))
            self.db.execute('UPDATE workbench_records SET revision=revision+1,updated_at=? WHERE id=?', (timestamp(), record_id))
            record = self._get(record_id)
            self._history(record)
            return {'record': record, 'changed': True}

    def asset(self, record_id):
        """Return a trusted source handle; the caller holds the shared lock while reading."""
        record = self._get(record_id)
        if record['kind'] == 'text':
            return record['text'].encode(), 'text/plain; charset=utf-8'
        if not record['source_available']:
            raise WorkbenchError('Source image unavailable.', 'unavailable', 404)
        path = self.dataset.path / 'images' / record_id / 'image.png'
        if not path.is_file():
            raise WorkbenchError('Source image unavailable.', 'unavailable', 404)
        return path, 'image/png'

    def selection(self, items):
        if not isinstance(items, list) or not 1 <= len(items) <= 5000:
            raise WorkbenchError('Select 1–5,000 records per synchronous release.')
        self._sync_images()
        result, seen = [], set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in seen:
                raise WorkbenchError('Selection contains an invalid or repeated record.')
            record = self._get(item['id'])
            for key in ('revision', 'source_revision'):
                if type(item.get(key)) is not int or item[key] != record[key]:
                    raise WorkbenchError('Selection changed. Refresh and select the current revisions.', 'conflict', 409)
            seen.add(item['id'])
            result.append(record)
        return sorted(result, key=lambda row: row['id'])


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def analyze(rows):
    counts = lambda values: dict(sorted(Counter(values).items()))
    hashes = Counter(r['pixel_hash'] or r['content_hash'] for r in rows if r['pixel_hash'] or r['content_hash'])
    return {'records': len(rows), 'kinds': counts(r['kind'] for r in rows),
            'reviews': counts(r['review'] for r in rows), 'tasks': counts(r['task'] for r in rows),
            'labels': counts(label for r in rows for label in labels(r)),
            'protected_groups': len({group for r in rows for group in r['groups']}),
            'duplicate_content_records': sum(n for n in hashes.values() if n > 1),
            'unlabeled': sum(r['annotation'] is None for r in rows),
            'missing_sources': sum(not r['source_available'] for r in rows),
            'unknown_rights': sum(rights_note(r) == 'unknown' for r in rows),
            'empty_targets': sum(r['annotation'] in ({'boxes': []}, {'spans': []}) for r in rows),
            'image_size': {'min_width': min((r['width'] for r in rows if r['width']), default=None),
                           'min_height': min((r['height'] for r in rows if r['height']), default=None)},
            'limits': ['Exact decoded-content matches only; semantic/near duplicates are not measured.',
                       'Class balance does not establish coverage or downstream model quality.',
                       'Rights notes and source independence require human judgment.']}
