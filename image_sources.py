"""Image acquisition and source policy, shared by legacy and inert project contexts.

Constructing this owner creates no workers, jobs, scripts or runtime recovery.
The caller supplies current authority, Workbench enrollment and inert or live
producer-entry ownership. Canonical project publication remains the session's job.
"""
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import shutil
import uuid

import ai
from access import authorized
from metadata import CommitOutcomeUnknown
from PIL import Image, ImageOps
import workbench

CORNERS = ('top_left', 'top_right', 'bottom_right', 'bottom_left')

VISIBILITY = ('visible', 'occluded', 'out_of_frame')

SPLITS = ('unassigned', 'train', 'validation', 'test')

class Conflict(ValueError):
    pass

def now():
    return datetime.now(timezone.utc).isoformat()

def metadata(body):
    result = {}
    for key in ('book_id', 'session_id'):
        value = body.get(key, '')
        if not isinstance(value, str) or len(value) > 120:
            raise ValueError(key + ' must be text, up to 120 characters.')
        result[key] = value.strip()
    if not result['session_id']:
        raise ValueError('Enter a recording session ID.')
    result['split'] = body.get('split', 'unassigned')
    if result['split'] not in SPLITS:
        raise ValueError('Invalid dataset split.')
    return result


def decode_source_image(raw):
    """The acquisition owner's bounded EXIF/RGB interpretation, without writes."""
    if type(raw) is not bytes or not raw or len(raw) > 25 * 1024 * 1024:
        raise ValueError('Choose an image smaller than 25 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 40_000_000:
                raise ValueError('Images must be at most 40 megapixels.')
            source.load()
            return ImageOps.exif_transpose(source).convert('RGB')
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('Unsupported or damaged image. Use JPEG, PNG, or WebP.') from error


def validate_project_source(original_bytes, oriented_bytes, source_snapshot, pixel_sha256):
    """Prove retained geometry/pixels through the acquisition owner's policy.

    Reading and comparing captured bytes creates no thumbnail or replacement
    source. Missing payloads are handled separately by the projection owner.
    """
    source = decode_source_image(original_bytes)
    try:
        if hashlib.sha256(original_bytes).hexdigest() != source_snapshot['sha256']:
            raise ValueError('Original image bytes differ from their source identity.')
        with Image.open(io.BytesIO(oriented_bytes)) as captured:
            if captured.format != 'PNG' or captured.width * captured.height > 40_000_000:
                raise ValueError('Retained oriented image must be the bounded captured PNG.')
            captured.load()
            oriented = captured.convert('RGB')
        try:
            expected = (source_snapshot['width'], source_snapshot['height'])
            if source.size != expected or oriented.size != expected or source.tobytes() != oriented.tobytes():
                raise ValueError('Retained image geometry or orientation differs from its original source.')
            if hashlib.sha256(str(oriented.size).encode() + oriented.tobytes()).hexdigest() != pixel_sha256:
                raise ValueError('Retained image pixels differ from their Workbench identity.')
        finally:
            oriented.close()
    finally:
        source.close()

def validate_annotation(body):
    if not isinstance(body, dict):
        raise ValueError('Expected an annotation object.')
    suggested_by = body.get('suggested_by')
    extra = {}
    if suggested_by is not None:
        if not isinstance(suggested_by, dict) or suggested_by.get('provider') not in ai.PROVIDERS:
            raise ValueError('Invalid AI suggestion provenance.')
        model = ai.model_id(suggested_by.get('model'))
        timestamp = suggested_by.get('suggested_at')
        if not isinstance(timestamp, str) or len(timestamp) > 60:
            raise ValueError('Invalid AI suggestion timestamp.')
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            raise ValueError('Invalid AI suggestion timestamp.') from None
        extra['suggested_by'] = dict(provider=suggested_by['provider'], model=model, suggested_at=timestamp)
    reference = body.get('corner_reference', 'book')
    if reference not in ('book', 'image'):
        raise ValueError('Choose book or image orientation for corner labels.')
    present, suitable = body.get('book_present'), body.get('crop_suitable')
    if type(present) is not bool or type(suitable) is not bool:
        raise ValueError('Choose book presence and crop suitability.')
    if not present:
        if suitable:
            raise ValueError('A scene without a book cannot be suitable for cropping.')
        return dict(book_present=False, crop_suitable=False, corners=[], corner_reference=reference, **extra)
    corners = body.get('corners')
    if not isinstance(corners, list) or len(corners) != 4:
        raise ValueError('Label all four corners.')
    result = []
    for name, corner in zip(CORNERS, corners):
        if not isinstance(corner, dict) or corner.get('name') != name or corner.get('visibility') not in VISIBILITY:
            raise ValueError('Corners must be ordered top-left, top-right, bottom-right, bottom-left.')
        visible = corner['visibility'] == 'visible'
        x, y = corner.get('x'), corner.get('y')
        if visible:
            if any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in (x, y)):
                raise ValueError('Place every visible corner inside the image.')
        elif x is not None or y is not None:
            raise ValueError('Hidden or off-screen corners must not have guessed coordinates.')
        result.append(dict(name=name, visibility=corner['visibility'], x=x, y=y))
    if suitable and any(c['visibility'] != 'visible' for c in result):
        raise ValueError('A complete crop requires four visible corners.')
    if all(c['visibility'] == 'visible' for c in result):
        points = [(c['x'], c['y']) for c in result]
        crosses = []
        for i in range(4):
            a, b, c = points[i], points[(i+1) % 4], points[(i+2) % 4]
            crosses.append((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]))
        if any(c <= 0.00001 for c in crosses):
            raise ValueError('Corners must form a clockwise, non-crossing outline.')
        if reference == 'image' and (points[0][1] + points[1][1] >= points[2][1] + points[3][1] or points[0][0] + points[3][0] >= points[1][0] + points[2][0]):
            raise ValueError('Start at the image top-left and label clockwise.')
    return dict(book_present=present, crop_suitable=suitable, corners=result, corner_reference=reference, **extra)


class ImageSources:
    def __init__(self, context):
        self._context = context
        self.path, self.db = context.path, context.db
        self.lock, self.access = context.lock, context.access
        (self.path / 'images').mkdir(exist_ok=True)

    def __getattr__(self, name):
        context = self.__dict__.get('_context')
        if context is not None and name in ('workbench', 'generation_jobs'):
            return getattr(context, name)
        raise AttributeError(name)

    @authorized('inspect', 'dataset.rows')
    def rows(self):
        with self.lock:
            rows = [dict(r) for r in self.db.execute('SELECT * FROM samples ORDER BY created_at, id')]
            provenance = {}
            for record in self.db.execute('SELECT data FROM generation_entries'):
                entry = json.loads(record[0])
                if entry.get('sample_id'):
                    provenance[entry['sample_id']] = entry
            for row in rows:
                if row['id'] in provenance:
                    entry = provenance[row['id']]
                    row['generation'] = {key: entry[key] for key in ('job_id', 'ordinal', 'prompt', 'metadata', 'model', 'width', 'height', 'requested_seed') if key in entry}
                row['annotation'] = json.loads(row['annotation']) if row['annotation'] else None
                if row['annotation'] is not None:
                    row['annotation'].setdefault('corner_reference', 'image')
            return rows

    @authorized('inspect', 'dataset.sample')
    def sample(self, sample_id):
        return next((row for row in self.rows() if row['id'] == sample_id), None)

    def _resolve_split(self, meta, exclude=''):
        key = 'book_id' if meta['book_id'] else 'session_id'
        where = key + '=%s' + (" AND book_id=''" if key == 'session_id' else '')
        args = (meta[key], exclude)
        assigned = {r[0] for r in self.db.execute(
            'SELECT DISTINCT split FROM samples WHERE ' + where + " AND id<>%s AND split<>'unassigned'", args)}
        desired = meta['split']
        if assigned and desired != 'unassigned' and desired not in assigned:
            raise Conflict('This book/session already belongs to ' + next(iter(assigned)) + '. Keep the same split.')
        chosen = next(iter(assigned), desired)
        # Existing unassigned members move together. Each change invalidates stale editors.
        if chosen != 'unassigned':
            self.db.execute("UPDATE samples SET split=%s, revision=revision+1 WHERE " + where +
                            " AND id<>%s AND split='unassigned'", (chosen, *args))
        return chosen

    def add(self, body, generation=None, *, enrollment=None):
        if generation is None:
            self.access.require('edit', 'dataset.add')
        else:
            entry, job, generated_metadata = generation
            self.access.require_job('synthetic', job['id'], job.get('admission_id'),
                                    self.generation_jobs._request_digest(job))
            self.access.require('edit', 'dataset.add_generated', job['id'])
        meta = metadata(body)
        try:
            raw = base64.b64decode(body.get('image', ''), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError('Invalid image data.') from error
        image = decode_source_image(raw)
        digest = hashlib.sha256(raw).hexdigest()
        name = body.get('filename', 'camera.jpg')
        if not isinstance(name, str):
            raise ValueError('Invalid filename.')
        name = name.replace('\\', '/').rsplit('/', 1)[-1][:200]
        sample_id, timestamp = uuid.uuid4().hex, now()
        with self.lock:
            if self.db.execute('SELECT id FROM samples WHERE sha256=%s', (digest,)).fetchone():
                raise Conflict('This exact image is already in the dataset.')
            folder = self.path / 'images' / sample_id
            folder.mkdir()
            try:
                (folder / 'source').write_bytes(raw)
                image.save(folder / 'image.png', 'PNG')
                thumbnail = image.copy()
                thumbnail.thumbnail((160, 120))
                thumbnail.save(folder / 'thumb.jpg', 'JPEG', quality=85)
                with self.db.transaction():
                    self.db.on_rollback(lambda: shutil.rmtree(folder, ignore_errors=True))
                    split = self._resolve_split(meta)
                    self.db.execute('INSERT INTO samples VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                    (sample_id, digest, name, image.width, image.height, meta['book_id'],
                                     meta['session_id'], split, timestamp, timestamp, 1, None))
                    if generation is not None:
                        self.generation_jobs.record_output(sample_id, *generation)
                    if enrollment is not None:
                        # Imported Workbench source metadata shares acquisition's
                        # commit and original-file cleanup on admission failure.
                        self.workbench._enroll_import(sample_id, *enrollment)
                    self.access.audit('dataset.add_generated' if generation else 'dataset.add',
                                      job['id'] if generation else sample_id,
                                      {'sample_id': sample_id, 'revision': 1, 'source_sha256': digest})
                    if generation is not None:
                        # Return only this admitted publication, without catalog-wide reads.
                        generated = dict(self.db.execute('SELECT * FROM samples WHERE id=%s', (sample_id,)).fetchone())
                        generated['generation'] = {key: entry[key] for key in
                            ('job_id', 'ordinal', 'prompt', 'metadata', 'model', 'width', 'height', 'requested_seed') if key in entry}
            except CommitOutcomeUnknown:
                raise
            except Exception:
                shutil.rmtree(folder, ignore_errors=True)
                raise
        return generated if generation is not None else self.sample(sample_id)

    def _recover_deletions(self):
        staging = self.path / '.deleting-images'
        if not staging.exists():
            return
        for folder in staging.iterdir():
            if not folder.is_dir() or len(folder.name) != 32 or any(c not in '0123456789abcdef' for c in folder.name):
                continue
            if self.db.execute('SELECT 1 FROM samples WHERE id=%s', (folder.name,)).fetchone():
                folder.rename(self.path / 'images' / folder.name)
            else:
                shutil.rmtree(folder)

    @authorized('edit', 'dataset.delete')
    def delete(self, sample_id, body):
        with self.lock:
            row = self.db.execute('SELECT revision FROM samples WHERE id=%s', (sample_id,)).fetchone()
            if not row:
                raise ValueError('Image not found. It may already have been deleted.')
            if type(body.get('revision')) is not int or body['revision'] != row['revision']:
                raise Conflict('This image changed in another tab. Reload it before deleting.')
            # Enrol before moving bytes; retain lineage in the deletion transaction.
            with self.db.transaction():
                self.workbench._sync_images()
            folder = self.path / 'images' / sample_id
            staging = self.path / '.deleting-images'
            staging.mkdir(exist_ok=True)
            staged = staging / sample_id
            # Rename first, then commit the row deletion. Startup restores staged
            # files if a crash occurred before commit, or removes them afterwards.
            folder.rename(staged)
            cleanup_warning = []
            def restore_files():
                if staged.exists():
                    staged.rename(folder)
            def remove_files():
                try:
                    shutil.rmtree(staged)
                except OSError:
                    cleanup_warning.append('Image removed from the dataset. Remaining file cleanup will be retried when Tuldok restarts.')
            try:
                with self.db.transaction():
                    self.db.on_rollback(restore_files)
                    self.db.on_commit(remove_files)
                    for record in self.db.execute('SELECT data FROM generation_entries').fetchall():
                        entry = json.loads(record[0])
                        if entry.get('sample_id') == sample_id:
                            entry.update(status='deleted', sample_id=None, deleted_at=now())
                            self.generation_jobs._entry(entry)
                    self.workbench.preserve_deleted_source(sample_id)
                    self.db.execute('DELETE FROM samples WHERE id=%s', (sample_id,))
                    self.access.audit('dataset.delete', sample_id)
            except CommitOutcomeUnknown:
                raise
            except Exception:
                restore_files()
                raise
            return dict(self.generation_jobs.snapshot(), samples=self.rows(), deleted=sample_id,
                        warning=cleanup_warning[0] if cleanup_warning else '')

    @authorized('approve-review', 'dataset.save')
    def save(self, sample_id, body):
        annotation = validate_annotation(body.get('annotation', {}))
        meta = metadata(body)
        if annotation['book_present'] and not meta['book_id']:
            raise ValueError('Enter a book ID for images containing a book.')
        with self.lock, self.db.transaction():
            row = self.db.execute('SELECT revision FROM samples WHERE id=%s', (sample_id,)).fetchone()
            if not row:
                raise ValueError('Image not found.')
            if body.get('revision') != row['revision']:
                raise Conflict('This image changed in another tab. Reload it before saving.')
            split = self._resolve_split(meta, sample_id)
            self.db.execute('UPDATE samples SET annotation=%s,book_id=%s,session_id=%s,split=%s,updated_at=%s,revision=revision+1 WHERE id=%s',
                            (json.dumps(annotation), meta['book_id'], meta['session_id'], split, now(), sample_id))
            self.access.audit('dataset.save', sample_id, {'before_revision': body['revision'],
                              'revision': body['revision'] + 1, 'annotation_sha256': hashlib.sha256(workbench.encode(annotation).encode()).hexdigest()})
        return self.sample(sample_id)
