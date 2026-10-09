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

TASKS = ('image_detection', 'image_classification', 'image_caption', 'text_classification', 'text_entities', 'text_corpus', 'text_retrieval', 'sequence_transport', 'mesh_geometry')
REVIEWS = ('draft', 'human_reviewed', 'programmatically_verified')
MAX_TEXT = 200_000  # Code points per synchronous text import.
MAX_SELECTED_TEXT_BYTES = 40 * 1024 * 1024  # Existing synchronous JSON envelope.
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


def query_criteria(options):
    """Validate metadata criteria without enumerating or enrolling any assets."""
    query = text_value(options.get('q', ''), 'Search', 200, empty=True)
    kind, review, sort, task = (options.get(k, '') for k in ('kind', 'review', 'sort', 'task'))
    if any(not isinstance(value, str) for value in (kind, review, sort, task)):
        raise WorkbenchError('Filter and sort values must be strings.')
    if kind not in ('', 'image', 'text', 'sequence', 'mesh') or review not in ('', *REVIEWS) or sort not in ('', 'newest', 'oldest', 'name', 'review'):
        raise WorkbenchError('Invalid filter or sort.')
    if task not in ('', *TASKS):
        raise WorkbenchError('Invalid task filter.')
    return dict(q=query, kind=kind, review=review, sort=sort, task=task,
                label=text_value(options.get('label', ''), 'Label filter', 80, empty=True),
                group=text_value(options.get('group', ''), 'Protected source/group filter', 120, empty=True),
                rights=text_value(options.get('rights', ''), 'Rights-note filter', 1000, empty=True))


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
    if task == 'text_retrieval':
        from retrieval_export import annotation
        return annotation(value, record)
    if task == 'text_corpus':
        if set(value) != {'note'}:
            raise WorkbenchError('Text corpus review requires exactly one note.')
        return {'note': text_value(value['note'], 'Corpus review note', 4000)}
    if task == 'sequence_transport' and 'temporal_labels' in value:
        from sequence_temporal_labels import validate
        return validate(value, record)
    if task in ('sequence_transport', 'mesh_geometry'):
        if set(value) != {'note'}:
            raise WorkbenchError(record['kind'].title() + ' review requires exactly one note; fields stay immutable.')
        return {'note': text_value(value['note'], record['kind'].title() + ' review note', 4000, empty=True)}
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
            try:
                finite = all(type(n) in (int, float) and math.isfinite(n) for n in (x, y, width, height))
            except OverflowError:
                finite = False
            if not finite:
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
    if record.get('task') == 'sequence_transport':
        from sequence_temporal_labels import labels as temporal_labels
        return temporal_labels(annotation)
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
            from immutable_assets import migrate_records
            from sequence_assets import SequenceAssets
            from meshes import MeshAssets
            self.db.execute('SAVEPOINT immutable_setup')
            try:
                migrate_records(self.db)
                self.sequences = SequenceAssets(self)
                self.meshes = MeshAssets(self)
                self.db.execute('RELEASE immutable_setup')
            except BaseException:
                self.db.execute('ROLLBACK TO immutable_setup')
                self.db.execute('RELEASE immutable_setup')
                raise
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id, revision))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_rights_notes (
                id TEXT PRIMARY KEY, note TEXT NOT NULL, revision INTEGER NOT NULL)''')
            self.db.execute('CREATE TABLE IF NOT EXISTS workbench_target_proposals (id TEXT PRIMARY KEY, evidence TEXT NOT NULL)')
            self.db.execute('CREATE INDEX IF NOT EXISTS workbench_content ON workbench_records(content_hash)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_responses (
                id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, revision INTEGER NOT NULL,
                completion TEXT NOT NULL, review TEXT NOT NULL, provenance_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS workbench_response_prompt ON workbench_responses(prompt_id)')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_response_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id,revision))''')
            self.db.execute('''CREATE TABLE IF NOT EXISTS workbench_deleted_sources (
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL, session_id TEXT NOT NULL,
                split TEXT NOT NULL)''')

            self.db.execute('CREATE TABLE IF NOT EXISTS workbench_deleted_text (id TEXT PRIMARY KEY)')
            from grounded_instructions import setup
            setup(self)

        from preferences import Preferences
        self.preferences = Preferences(self)

    def _sync_images(self, record_id=None):
        # Enrol only new images. Hashing is streaming and never rewrites originals.
        query = '''SELECT s.* FROM samples s LEFT JOIN workbench_records w
            ON w.id=s.id WHERE w.id IS NULL'''
        if record_id is not None:
            query += ' AND s.id=?'
        rows = self.db.execute(query, () if record_id is None else (record_id,)).fetchall()
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
        elif result['kind'] in ('sequence', 'mesh'):
            result.pop('image_name')
            owner = self.sequences if result['kind'] == 'sequence' else self.meshes
            result[result['kind']] = owner.metadata(record_id)
            result['source_available'] = result[result['kind']] is not None
            result['source_lineage_known'] = True
            result['source_revision'] = 1
            result['source_split'] = 'unassigned'
            result['source_sha256'] = result['content_hash']
        else:
            result.pop('image_name')
            result['source_revision'] = 1
            result['source_split'] = 'unassigned'
            result['source_sha256'] = hashlib.sha256(result['original_text'].encode()).hexdigest()
        if result['kind'] == 'text':
            result['source_available'] = self.db.execute('SELECT 1 FROM workbench_deleted_text WHERE id=?', (record_id,)).fetchone() is None
            result['source_lineage_known'] = True
        current_binding = self.db.execute('SELECT data FROM instruction_context_bindings WHERE prompt_id=?', (record_id,)).fetchone()
        if current_binding is not None:
            result['grounded_context_binding'] = json.loads(current_binding[0])
        for field in ('groups', 'parents', 'provenance', 'annotation'):
            raw = result.pop(field + '_json')
            result[field] = json.loads(raw) if raw is not None else None
        correction = self.db.execute('SELECT note,revision FROM workbench_rights_notes WHERE id=?', (record_id,)).fetchone()
        if correction is not None:
            result['provenance']['rights_note_correction'] = dict(correction)
        proposal = self.db.execute('SELECT evidence FROM workbench_target_proposals WHERE id=?', (record_id,)).fetchone()
        if proposal is not None:
            result['target_proposal'] = json.loads(proposal[0])
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

    def _filtered(self, options):
        """Shared current metadata criteria; caller owns lock and transaction."""
        criteria = query_criteria(options)
        query = criteria['q'].casefold()
        kind, review, sort, task, label, group, rights = (criteria[k] for k in ('kind', 'review', 'sort', 'task', 'label', 'group', 'rights'))
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
        criteria['q'] = query
        return filtered, criteria

    def query(self, options):
        """Page metadata and excerpts. Asset bytes are never loaded for browsing."""
        try:
            offset, limit = int(options.get('offset', 0)), int(options.get('limit', PAGE_SIZE))
        except (ValueError, TypeError):
            raise WorkbenchError('Invalid pagination.') from None
        if offset < 0 or not 1 <= limit <= 100:
            raise WorkbenchError('Page size must be 1–100 and offset nonnegative.')
        with self.lock, self.db:
            filtered, criteria = self._filtered(options)
            summary = analyze(filtered)
            page = []
            for record in filtered[offset:offset + limit]:
                record = dict(record)
                record['excerpt'] = (record.pop('text') or '')[:180]
                record.pop('corner_annotation')
                record['rights_note'] = rights_note(record)
                page.append(record)
            return {'items': page, 'total': len(filtered), 'offset': offset, 'limit': limit,
                    'analysis': summary, 'criteria': criteria}

    def import_asset(self, body, *, acquisition=None, annotation=None, annotation_task='image_caption', source_split='unassigned', source_session=None):
        kind = body.get('kind')
        groups = strings(body.get('groups', []), 'Protected groups')
        if not groups:
            raise WorkbenchError('Supply at least one protected source/group ID.')
        rights = text_value(body.get('rights', 'unknown'), 'Rights / permission note', 1000)
        parents = strings(body.get('parents', []), 'Parent IDs')
        if annotation is not None:
            if kind != 'image' or annotation_task not in ('image_caption', 'image_detection'):
                raise WorkbenchError('Unsupported initial image annotation task.')
            if annotation_task == 'image_caption':
                annotation = validate_annotation(annotation_task, annotation, {'kind': kind})
            # Detection requires the measured oriented geometry. Enrollment
            # validates it inside Dataset's existing acquisition transaction.
        if kind != 'image' and source_split != 'unassigned':
            raise WorkbenchError('Only image acquisition owns source splits.')
        with self.lock, self.db:
            self._sync_images()
            for parent in parents:
                self._get(parent)
            if kind == 'image':
                # Reuse the existing normalizer, original storage and dedup contract.
                row = self.dataset.add({'image': body.get('image'), 'filename': body.get('name', 'image.png'),
                                        'session_id': groups[0] if source_session is None else source_session,
                                        'book_id': '', 'split': source_split},
                                       enrollment=(groups, parents, rights, acquisition, annotation, annotation_task))
                return self._get(row['id'])
            if kind != 'text':
                raise WorkbenchError('Asset kind must be image or text.')
            return self._insert_text(body.get('text'), body.get('name', 'Text record'), groups, parents, rights,
                                     provenance={'acquisition': acquisition} if acquisition is not None else None)

    def _enroll_import(self, sample_id, groups, parents, rights, acquisition=None, annotation=None, annotation_task='image_caption'):
        """Called only inside Dataset.add's acquisition transaction and lock."""
        self._sync_images()
        record = self._get(sample_id)
        origin = dict(record['provenance'], rights=rights)
        if acquisition is not None:
            origin['acquisition'] = acquisition
        self.db.execute('UPDATE workbench_records SET groups_json=?,parents_json=?,provenance_json=? WHERE id=?',
                        (encode(groups), encode(parents), encode(origin), sample_id))
        if annotation is not None:
            if annotation_task not in ('image_caption', 'image_detection'):
                raise WorkbenchError('Unsupported initial image annotation task.')
            annotation = validate_annotation(annotation_task, annotation, record)
            self.db.execute("UPDATE workbench_records SET task=?,annotation_json=?,review='draft' WHERE id=?",
                            (annotation_task, encode(annotation), sample_id))
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
            return self._save_annotation(record_id, body, verified_provenance=verified_provenance)

    def _save_annotation(self, record_id, body, *, verified_provenance=None, proposal_evidence=None):
        """Trusted caller owns the lock/transaction, including proposal linkage."""
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
        if task == 'text_retrieval':
            from retrieval_export import check_positives
            if review not in ('draft', 'human_reviewed') or verified_provenance:
                raise WorkbenchError('Retrieval data requires explicit human review.')
            if annotation['role'] == 'query':
                check_positives(self, annotation['positive_refs'])
        if task == 'text_corpus' and (review not in ('draft', 'human_reviewed') or verified_provenance):
            raise WorkbenchError('Text corpus data requires an explicit human review decision.')
        if before['kind'] in ('sequence', 'mesh'):
            if not set(before[before['kind']]['protected_groups']) <= set(groups):
                raise WorkbenchError('Keep the whole trajectory and initial-family protected groups.' if before['kind'] == 'sequence' else 'Keep the immutable mesh source and family protected groups.')
            if review not in ('draft', 'human_reviewed') or verified_provenance:
                raise WorkbenchError(before['kind'].title() + ' data requires a human review decision.')
        if review not in ('draft', 'human_reviewed') and not (review == 'programmatically_verified' and verified_provenance):
            raise WorkbenchError('Only an owned verifier can grant programmatic verification.')
        if task == 'sequence_transport' and 'temporal_labels' in annotation:
            from sequence_temporal_labels import verify_source
            verify_source(self, before)
        # A trusted verifier may replace origin, but never persist or alter the note owner's projection.
        origin = json.loads(self.db.execute('SELECT provenance_json FROM workbench_records WHERE id=?', (record_id,)).fetchone()[0])
        provenance = dict(verified_provenance) if verified_provenance else origin
        if verified_provenance:
            reserved = 'rights_note_correction'
            if reserved in origin:
                if reserved not in provenance or provenance[reserved] != origin[reserved]:
                    raise WorkbenchError('Cannot replace reserved origin evidence through verifier provenance.', 'conflict', 409)
            elif reserved in provenance:
                if reserved not in before['provenance'] or provenance[reserved] != before['provenance'][reserved]:
                    raise WorkbenchError('Verifier provenance cannot change the owned rights correction. Reload before saving.', 'conflict', 409)
                provenance.pop(reserved)
        self.db.execute('''UPDATE workbench_records SET task=?,annotation_json=?,review=?,groups_json=?,
            provenance_json=?,revision=revision+1,updated_at=? WHERE id=?''',
                        (task, encode(annotation), review, encode(groups), encode(provenance), timestamp(), record_id))
        if proposal_evidence is not None:
            self.db.execute('INSERT INTO workbench_target_proposals VALUES (?,?) ON CONFLICT(id) DO UPDATE SET evidence=excluded.evidence',
                            (record_id, encode(proposal_evidence)))
        elif before['task'] != task or before['annotation'] != annotation:
            self.db.execute('DELETE FROM workbench_target_proposals WHERE id=?', (record_id,))
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
    def delete_text(self, record_id, body):
        """Retain immutable bytes/history/lineage; refuse further source use."""
        if not isinstance(body, dict) or set(body) != {'revision', 'source_revision'}:
            raise WorkbenchError('Supply exact text record/source revisions.')
        with self.lock, self.db:
            before = self._get(record_id)
            if before['kind'] != 'text':
                raise WorkbenchError('Only text sources use this deletion owner.')
            for key in ('revision', 'source_revision'):
                if type(body[key]) is not int or body[key] != before[key]:
                    raise WorkbenchError('Source changed. Reload before deleting.', 'conflict', 409)
            if not before['source_available']:
                return {'record': before, 'changed': False}
            self.db.execute('INSERT INTO workbench_deleted_text VALUES (?)', (record_id,))
            self.db.execute("UPDATE workbench_records SET revision=revision+1,review='draft',updated_at=? WHERE id=?", (timestamp(), record_id))
            record = self._get(record_id)
            self._history(record)
            return {'record': record, 'changed': True}

    def _response(self, response_id):
        row = self.db.execute('SELECT * FROM workbench_responses WHERE id=?', (response_id,)).fetchone()
        if row is None:
            raise WorkbenchError('Response not found.', 'unavailable', 404)
        response = dict(row)
        response['provenance'] = json.loads(response.pop('provenance_json'))
        saved_binding = self.db.execute('SELECT digest FROM instruction_response_bindings WHERE response_id=?', (response_id,)).fetchone()
        if saved_binding is not None:
            response['grounded_binding_sha256'] = saved_binding[0]
        return response

    def responses(self, prompt_id):
        with self.lock:
            parent = self._get(prompt_id)
            if parent['kind'] != 'text':
                raise WorkbenchError('Instruction responses require a text prompt.')
            ids = self.db.execute('SELECT id FROM workbench_responses WHERE prompt_id=? ORDER BY created_at,id', (prompt_id,))
            return {'parent': parent, 'responses': [self._response(row['id']) for row in ids]}

    def response_history(self, response_id):
        with self.lock:
            self._response(response_id)
            return {'history': [json.loads(row[0]) for row in self.db.execute(
                'SELECT snapshot FROM workbench_response_history WHERE id=? ORDER BY revision', (response_id,))]}

    def save_response(self, body):
        """An independent target with immutable prompt identity and explicit CAS."""
        fields = {'id', 'prompt_id', 'revision', 'parent_revision', 'source_revision', 'completion', 'review'}
        if not isinstance(body, dict) or set(body) != fields:
            raise WorkbenchError('Supply only response identity, exact revisions, completion and review.')
        if any(not isinstance(body[key], str) or not IDENTIFIER.fullmatch(body[key]) for key in ('id', 'prompt_id')):
            raise WorkbenchError('Invalid response or prompt ID.')
        if type(body['revision']) is not int or body['revision'] < 0:
            raise WorkbenchError('Response revision must be a nonnegative integer.')
        completion = body['completion']
        # Check using the shared bounded text policy, but never return its stripped value.
        text_value(completion, 'Completion', MAX_TEXT)
        if body['review'] not in ('draft', 'human_reviewed'):
            raise WorkbenchError('Explicitly choose draft or review this exact completion.')
        with self.lock, self.db:
            parent = self._get(body['prompt_id'])
            if parent['kind'] != 'text' or not parent['source_available']:
                raise WorkbenchError('Instruction responses require an available text prompt.')
            for request_key, parent_key in (('parent_revision', 'revision'), ('source_revision', 'source_revision')):
                if type(body[request_key]) is not int or body[request_key] != parent[parent_key]:
                    raise WorkbenchError('The prompt changed. Reload before saving the response.', 'conflict', 409)
            from grounded_instructions import check_answer
            context_digest = check_answer(self, parent, completion=completion)
            existing = self.db.execute('SELECT id FROM workbench_responses WHERE id=?', (body['id'],)).fetchone()
            created = timestamp()
            if existing:
                before = self._response(body['id'])
                if before['prompt_id'] != body['prompt_id'] or body['revision'] != before['revision']:
                    raise WorkbenchError('The response changed or belongs to another prompt. Reload before saving.', 'conflict', 409)
                if before['completion'] == completion and before['review'] == body['review'] and (context_digest is None or before.get('grounded_binding_sha256') == context_digest):
                    return {'response': before, 'parent': parent, 'changed': False}
                self.db.execute('''UPDATE workbench_responses SET completion=?,review=?,revision=revision+1,
                    updated_at=? WHERE id=?''', (completion, body['review'], created, body['id']))
            else:
                if body['revision'] != 0:
                    raise WorkbenchError('Response no longer exists.', 'unavailable', 409)
                origin = {'method': 'human_authored', 'prompt_id': parent['id'],
                          'prompt_sha256': parent['content_hash'], 'source_sha256': parent['source_sha256']}
                if context_digest is not None:
                    origin['grounded_creation_binding_sha256'] = context_digest
                self.db.execute('INSERT INTO workbench_responses VALUES (?,?,?,?,?,?,?,?)',
                                (body['id'], parent['id'], 1, completion, body['review'], encode(origin), created, created))
            if context_digest is not None:
                self.db.execute('INSERT INTO instruction_response_bindings VALUES (?,?) ON CONFLICT(response_id) DO UPDATE SET digest=excluded.digest', (body['id'], context_digest))
            response = self._response(body['id'])
            self.db.execute('INSERT INTO workbench_response_history VALUES (?,?,?)',
                            (response['id'], response['revision'], encode({'response': response, 'parent': parent})))
            return {'response': response, 'parent': parent, 'changed': True}

    def response_selection(self, items):
        if not isinstance(items, list) or not 1 <= len(items) <= 5000:
            raise WorkbenchError('Select 1–5,000 explicit response revisions per synchronous release.')
        fields = {'id', 'revision', 'prompt_id', 'parent_revision', 'source_revision'}
        responses, parents, seen, size = [], {}, set(), 0
        for item in items:
            if not isinstance(item, dict) or set(item) != fields or any(
                    not isinstance(item[key], str) or not IDENTIFIER.fullmatch(item[key]) for key in ('id', 'prompt_id')):
                raise WorkbenchError('Select exact response IDs, revisions and parent/source pairs.')
            if item['id'] in seen:
                raise WorkbenchError('Repeated response selection.')
            seen.add(item['id'])
            response = self._response(item['id'])
            parent = parents.get(response['prompt_id']) or self._get(response['prompt_id'])
            if response['prompt_id'] != item['prompt_id'] or type(item['revision']) is not int or item['revision'] != response['revision']:
                raise WorkbenchError('Selected response changed. Explicitly reselect its current revision.', 'conflict', 409)
            for request_key, parent_key in (('parent_revision', 'revision'), ('source_revision', 'source_revision')):
                if type(item[request_key]) is not int or item[request_key] != parent[parent_key]:
                    raise WorkbenchError('Selected prompt changed. Explicitly reselect current parent revisions.', 'conflict', 409)
            if parent['kind'] != 'text' or not parent['source_available']:
                raise WorkbenchError('Selected response requires an available text prompt.')
            if response['review'] != 'human_reviewed':
                raise WorkbenchError('Every selected response needs explicit human review.')
            from grounded_instructions import check_answer
            check_answer(self, parent, response=response)
            text_value(response['completion'], 'Completion', MAX_TEXT)
            size += len(response['completion'].encode('utf-8'))
            if parent['id'] not in parents:
                size += len(parent['text'].encode('utf-8'))
                parents[parent['id']] = parent
            if size > MAX_SELECTED_TEXT_BYTES:
                raise WorkbenchError('Selected prompt/response text exceeds the 40 MiB synchronous resource bound.')
            responses.append(response)
        return sorted(responses, key=lambda row: row['id']), sorted(parents.values(), key=lambda row: row['id'])

    def check_immutable_selection(self, records):
        from immutable_assets import check_selection
        check_selection(records)

    def asset(self, record_id):
        """Return a trusted source handle; the caller holds the shared lock while reading."""
        record = self._get(record_id)
        if record['kind'] in ('sequence', 'mesh'):
            return (self.sequences if record['kind'] == 'sequence' else self.meshes).asset(record)
        if record['kind'] == 'text':
            if not record['source_available']:
                raise WorkbenchError('Text source was deleted.', 'unavailable', 404)
            return record['text'].encode(), 'text/plain; charset=utf-8'
        if not record['source_available']:
            raise WorkbenchError('Source image unavailable.', 'unavailable', 404)
        path = self.dataset.path / 'images' / record_id / 'image.png'
        if not path.is_file():
            raise WorkbenchError('Source image unavailable.', 'unavailable', 404)
        return path, 'image/png'

    def selection(self, items, *, max_snapshot_bytes=None):
        if not isinstance(items, list) or not 1 <= len(items) <= 5000:
            raise WorkbenchError('Select 1–5,000 records per synchronous release.')
        self._sync_images()
        result, seen, snapshot_bytes = [], set(), 0
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in seen:
                raise WorkbenchError('Selection contains an invalid or repeated record.')
            record = self._get(item['id'])
            for key in ('revision', 'source_revision'):
                if type(item.get(key)) is not int or item[key] != record[key]:
                    raise WorkbenchError('Selection changed. Refresh and select the current revisions.', 'conflict', 409)
            if max_snapshot_bytes is not None:
                snapshot_bytes += len(encode(record).encode('utf-8'))
                if snapshot_bytes > max_snapshot_bytes:
                    raise WorkbenchError('Selected snapshots exceed the 40 MiB complete logical archive bound.')
            seen.add(item['id'])
            result.append(record)
        return sorted(result, key=lambda row: row['id'])


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def diagnostic_members(rows):
    """Contributors to existing quality counts; exact matching stays owner-defined."""
    hashes = Counter(r['pixel_hash'] or r['content_hash'] for r in rows if r['pixel_hash'] or r['content_hash'])
    return {'duplicates': [r for r in rows if hashes[r['pixel_hash'] or r['content_hash']] > 1],
            'unlabeled': [r for r in rows if r['annotation'] is None],
            'missing_sources': [r for r in rows if not r['source_available']],
            'unknown_rights': [r for r in rows if rights_note(r) == 'unknown']}, hashes


def analyze(rows):
    counts = lambda values: dict(sorted(Counter(values).items()))
    members, _ = diagnostic_members(rows)
    return {'records': len(rows), 'kinds': counts(r['kind'] for r in rows),
            'reviews': counts(r['review'] for r in rows), 'tasks': counts(r['task'] for r in rows),
            'labels': counts(label for r in rows for label in labels(r)),
            'protected_groups': len({group for r in rows for group in r['groups']}),
            'duplicate_content_records': len(members['duplicates']),
            'unlabeled': len(members['unlabeled']),
            'missing_sources': len(members['missing_sources']),
            'unknown_rights': len(members['unknown_rights']),
            'empty_targets': sum(r['annotation'] in ({'boxes': []}, {'spans': []}) for r in rows),
            'image_size': {'min_width': min((r['width'] for r in rows if r['width']), default=None),
                           'min_height': min((r['height'] for r in rows if r['height']), default=None)},
            'limits': ['Exact decoded-content matches only; semantic/near duplicates are not measured.',
                       'Class balance does not establish coverage or downstream model quality.',
                       'Rights notes and source independence require human judgment.']}
