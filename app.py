"""Tuldok: local image capture and corner-label dataset workspace."""
import argparse
import ai
import ai_codex
import image_generation
import base64
import hashlib
import io
import json
import math
import shutil
import sqlite3
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
CORNERS = ('top_left', 'top_right', 'bottom_right', 'bottom_left')
VISIBILITY = ('visible', 'occluded', 'out_of_frame')
SPLITS = ('unassigned', 'train', 'validation', 'test')
MAX_BODY = 40 * 1024 * 1024


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


class Dataset:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / 'images').mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.ai_lock = threading.Lock()
        self.image_requests = image_generation.ImageRequests()
        self.db = sqlite3.connect(self.path / 'dataset.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute("""CREATE TABLE IF NOT EXISTS samples (
            id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL,
            book_id TEXT NOT NULL, session_id TEXT NOT NULL, split TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, annotation TEXT)""")
        self.db.commit()

    def close(self):
        self.db.close()

    def rows(self):
        with self.lock:
            rows = [dict(r) for r in self.db.execute('SELECT * FROM samples ORDER BY created_at, id')]
            for row in rows:
                row['annotation'] = json.loads(row['annotation']) if row['annotation'] else None
                if row['annotation'] is not None:
                    row['annotation'].setdefault('corner_reference', 'image')
            return rows

    def sample(self, sample_id):
        return next((row for row in self.rows() if row['id'] == sample_id), None)

    def resolve_split(self, meta, exclude=''):
        key = 'book_id' if meta['book_id'] else 'session_id'
        where = key + '=?' + (" AND book_id=''" if key == 'session_id' else '')
        args = (meta[key], exclude)
        assigned = {r[0] for r in self.db.execute(
            'SELECT DISTINCT split FROM samples WHERE ' + where + " AND id<>? AND split<>'unassigned'", args)}
        desired = meta['split']
        if assigned and desired != 'unassigned' and desired not in assigned:
            raise Conflict('This book/session already belongs to ' + next(iter(assigned)) + '. Keep the same split.')
        chosen = next(iter(assigned), desired)
        # Existing unassigned members move together. Each change invalidates stale editors.
        if chosen != 'unassigned':
            self.db.execute("UPDATE samples SET split=?, revision=revision+1 WHERE " + where +
                            " AND id<>? AND split='unassigned'", (chosen, *args))
        return chosen

    def add(self, body):
        meta = metadata(body)
        try:
            raw = base64.b64decode(body.get('image', ''), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError('Invalid image data.') from error
        if not raw or len(raw) > 25 * 1024 * 1024:
            raise ValueError('Choose an image smaller than 25 MB.')
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > 40_000_000:
                    raise ValueError('Images must be at most 40 megapixels.')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError('Unsupported or damaged image. Use JPEG, PNG, or WebP.') from error
        digest = hashlib.sha256(raw).hexdigest()
        name = body.get('filename', 'camera.jpg')
        if not isinstance(name, str):
            raise ValueError('Invalid filename.')
        name = name.replace('\\', '/').rsplit('/', 1)[-1][:200]
        sample_id, timestamp = uuid.uuid4().hex, now()
        with self.lock:
            if self.db.execute('SELECT id FROM samples WHERE sha256=?', (digest,)).fetchone():
                raise Conflict('This exact image is already in the dataset.')
            folder = self.path / 'images' / sample_id
            folder.mkdir()
            try:
                (folder / 'source').write_bytes(raw)
                image.save(folder / 'image.png', 'PNG')
                thumbnail = image.copy()
                thumbnail.thumbnail((160, 120))
                thumbnail.save(folder / 'thumb.jpg', 'JPEG', quality=85)
                with self.db:
                    split = self.resolve_split(meta)
                    self.db.execute('INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                                    (sample_id, digest, name, image.width, image.height, meta['book_id'],
                                     meta['session_id'], split, timestamp, timestamp, 1, None))
            except Exception:
                shutil.rmtree(folder)
                raise
        return self.sample(sample_id)

    def save(self, sample_id, body):
        annotation = validate_annotation(body.get('annotation', {}))
        meta = metadata(body)
        if annotation['book_present'] and not meta['book_id']:
            raise ValueError('Enter a book ID for images containing a book.')
        with self.lock, self.db:
            row = self.db.execute('SELECT revision FROM samples WHERE id=?', (sample_id,)).fetchone()
            if not row:
                raise ValueError('Image not found.')
            if body.get('revision') != row['revision']:
                raise Conflict('This image changed in another tab. Reload it before saving.')
            split = self.resolve_split(meta, sample_id)
            self.db.execute('UPDATE samples SET annotation=?,book_id=?,session_id=?,split=?,updated_at=?,revision=revision+1 WHERE id=?',
                            (json.dumps(annotation), meta['book_id'], meta['session_id'], split, now(), sample_id))
        return self.sample(sample_id)

    def suggest(self, body):
        sample_id = body.get('sample_id')
        before = self.sample(sample_id)
        if before is None:
            raise ValueError('Image not found.')
        if type(body.get('revision')) is not int or body['revision'] != before['revision']:
            raise Conflict('This image changed in another tab. Reload it before requesting a suggestion.')
        if not self.ai_lock.acquire(blocking=False):
            raise Conflict('Another AI suggestion is running. Wait for it to finish.')
        try:
            result, source = ai.suggest(self.path / 'images' / sample_id / 'image.png', body)
            if not {'book_present', 'crop_suitable', 'corner_reference', 'corners'}.issubset(result):
                raise ValueError('The model returned an incomplete corner label.')
            annotation = validate_annotation(result)
            annotation['suggested_by'] = source
            after = self.sample(sample_id)
            if after is None or after['revision'] != before['revision']:
                raise Conflict('This image changed while the model was running. Reload it before applying a suggestion.')
            return {'sample_id': sample_id, 'revision': before['revision'], 'annotation': annotation}
        finally:
            self.ai_lock.release()

    def export(self):
        rows = [row for row in self.rows() if row['annotation']]
        if not rows:
            raise ValueError('Label at least one image before exporting.')
        target = tempfile.TemporaryFile()
        try:
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED) as archive:
                manifest = []
                for row in rows:
                    image_path = 'images/' + row['id'] + '.png'
                    archive.write(self.path / 'images' / row['id'] / 'image.png', image_path)
                    manifest.append(dict(row, image=image_path, group_id=('book:' + row['book_id']) if row['book_id'] else ('session:' + row['session_id'])))
                archive.writestr('labels.jsonl', ''.join(json.dumps(r) + '\n' for r in manifest))
                archive.writestr('schema.json', json.dumps({
                    'version': 2, 'coordinates': 'Normalized 0..1 in EXIF-oriented image pixels: x/(width-1), y/(height-1).',
                    'corner_order': CORNERS, 'hidden_coordinates': None,
                    'corner_reference': 'Per annotation: book means corners as viewed with the book upright; image means screen-relative. Legacy labels are image-relative.',
                    'target': 'Outer corners of the whole open spread or closed cover, without padding.',
                    'samples': len(rows), 'unlabeled_excluded': len(self.rows()) - len(rows),
                }, indent=2))
            target.seek(0)
            return target
        except Exception:
            target.close()
            raise


def make_handler(dataset):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, status=200, content_type='application/json'):
            if content_type == 'application/json':
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == '/api/ai/config':
                    return self.reply(ai.codex_models())
                if path == '/api/samples':
                    return self.reply(dataset.rows())
                if path.startswith(('/api/image/', '/api/thumb/')):
                    sample = dataset.sample(path.rsplit('/', 1)[-1])
                    if not sample:
                        return self.reply({'error': 'Image not found.'}, 404)
                    thumb = path.startswith('/api/thumb/')
                    return self.reply((dataset.path / 'images' / sample['id'] / ('thumb.jpg' if thumb else 'image.png')).read_bytes(), content_type='image/jpeg' if thumb else 'image/png')
                if path == '/api/export':
                    with dataset.export() as archive:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/zip')
                        self.send_header('Content-Disposition', 'attachment; filename="tuldok-dataset.zip"')
                        self.send_header('Cache-Control', 'no-store')
                        self.end_headers()
                        shutil.copyfileobj(archive, self.wfile)
                    return
                assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
                if path in assets:
                    name, kind = assets[path]
                    return self.reply((ROOT / 'static' / name).read_bytes(), content_type=kind + '; charset=utf-8')
                return self.reply({'error': 'Not found.'}, 404)
            except ValueError as error:
                return self.reply({'error': str(error)}, 400)

        def do_POST(self):
            body = {}
            try:
                # Same-origin JSON only; no cross-site form submissions.
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                    return self.reply({'error': 'Cross-origin requests are not accepted.'}, 403)
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Send JSON.')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    raise ValueError('Request is too large or empty.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Expected an object.')
                path = urlsplit(self.path).path
                if path == '/api/generation/models':
                    return self.reply(image_generation.models(body))
                if path == '/api/generation/cancel':
                    return self.reply(dataset.image_requests.cancel(body.get('request_id')))
                if path == '/api/generation/generate':
                    return self.reply(dataset.image_requests.generate(body, self.connection))
                if path == '/api/ai/models':
                    return self.reply(ai.models(body))
                if path == '/api/ai/suggest':
                    return self.reply(dataset.suggest(body))
                if path == '/api/samples':
                    return self.reply(dataset.add(body), 201)
                if path.startswith('/api/labels/'):
                    return self.reply(dataset.save(path.rsplit('/', 1)[-1], body))
                return self.reply({'error': 'Not found.'}, 404)
            except Conflict as error:
                return self.reply({'error': str(error)}, 409)
            except FileNotFoundError:
                return self.reply({'error': 'Codex CLI or the selected image was not found. Check the installation and dataset.'}, 400)
            except (ValueError, TypeError, OSError, ai_codex.CodexError) as error:
                return self.reply({'error': ai.safe_error(error, body)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT / 'data')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8091)
    args = parser.parse_args()
    dataset = Dataset(args.data)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(dataset))
    print('Tuldok: http://' + args.host + ':' + str(server.server_port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        dataset.close()


if __name__ == '__main__':
    main()
