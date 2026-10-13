"""Read-only project inspection; catalog registration never executes project code."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from workbench import WorkbenchError, encode

ID = re.compile(r'[a-f0-9]{32}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}')
SHA = re.compile(r'[a-f0-9]{64}')
MANIFEST_LIMIT = 64 * 1024
FILE_LIMIT = 8 * 1024 * 1024
DATA_LIMIT = 40 * 1024 * 1024
INSPECTION_LIMIT = 64 * 1024 * 1024
TEXT_LIMIT = 64 * 1024
GROUPS = ('data', 'recipes', 'evidence', 'requirements')


def closed(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise WorkbenchError('Invalid project fields.')


def text(value, label, limit=160):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise WorkbenchError(label + ' must be bounded, nonempty text without control characters.')
    return value


def relative_path(value):
    text(value, 'Project-relative path', 512)
    if '\\' in value or value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')):
        raise WorkbenchError('Use a relative path with no traversal or empty components.')
    if len(value.split('/')) > 16:
        raise WorkbenchError('Project path is too deep.')
    return value


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate field')
            result[key] = value
        return result
    def constant(_value):
        raise ValueError('Nonfinite value')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError):
        raise WorkbenchError('Project JSON must be bounded UTF-8 with unique fields and finite values.') from None


def manifest(value):
    closed(value, ('schema_version', 'id', 'name', *GROUPS))
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise WorkbenchError('Only project schema 1 is supported.', 'unsupported', 400)
    if not isinstance(value['id'], str) or not ID.fullmatch(value['id']):
        raise WorkbenchError('Project ID must be 32 lowercase hexadecimal characters.')
    text(value['name'], 'Project name', 120)
    for group in GROUPS:
        entries = value[group]
        if not isinstance(entries, list) or len(entries) > 64:
            raise WorkbenchError('Each project section permits at most 64 references.')
        seen = set()
        for entry in entries:
            closed(entry, ('id', 'label') if group == 'requirements' else ('id', 'label', 'path'),
                   ('path',) if group == 'requirements' else ('sha256',))
            key = entry['id']
            if not isinstance(key, str) or not NAME.fullmatch(key) or key in seen:
                raise WorkbenchError('Reference IDs must be bounded and unique within their section.')
            seen.add(key)
            text(entry['label'], 'Reference label')
            if 'path' in entry:
                relative_path(entry['path'])
            if 'sha256' in entry and (not isinstance(entry['sha256'], str) or not SHA.fullmatch(entry['sha256'])):
                raise WorkbenchError('Expected SHA256 must be lowercase hexadecimal.')
    return value


class Projects:
    """One catalog's immutable project snapshots and explicitly configured root handles."""

    def __init__(self, dataset, roots=None):
        self.db, self.lock = dataset.db, dataset.lock
        self.roots = {}
        try:
            for alias, location in (roots or {}).items():
                if not isinstance(alias, str) or not NAME.fullmatch(alias):
                    raise WorkbenchError('Project root aliases use 1–64 letters, digits, dot, dash or underscore.')
                path = Path(location).expanduser().resolve(strict=True)
                # Root selection is a local startup action, not a browser-supplied filesystem path.
                fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                info = os.fstat(fd)
                self.roots[alias] = (fd, [info.st_dev, info.st_ino])
        except (OSError, ValueError, TypeError, WorkbenchError):
            self.close()
            raise WorkbenchError('Cannot open configured project roots; check aliases and local directories.') from None

    def close(self):
        for fd, _identity in self.roots.values():
            os.close(fd)
        self.roots.clear()

    @contextmanager
    def _file(self, root, path):
        """Walk open directory handles; refuse symlinks, special files and path races."""
        parts = relative_path(path).split('/')
        entry = self.roots.get(root)
        if entry is None:
            raise WorkbenchError('Project root is not configured on this server.', 'unavailable', 409)
        descriptors = []
        directory = entry[0]
        try:
            for part in parts[:-1]:
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                descriptors.append(directory)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            descriptors.append(fd)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise WorkbenchError('Only regular project files can be inspected.', 'unsupported', 400)
            yield fd, info
        finally:
            for fd in reversed(descriptors):
                os.close(fd)

    def _read(self, root, path, limit):
        with self._file(root, path) as (fd, before):
            if before.st_size > limit:
                raise WorkbenchError('File exceeds this inspection limit.', 'too_large', 400)
            chunks, remaining = [], limit + 1
            while remaining:
                chunk = os.read(fd, min(remaining, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(fd)
            raw = b''.join(chunks)
            if len(raw) > limit:
                raise WorkbenchError('File exceeds this inspection limit.', 'too_large', 400)
            if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != after.st_size):
                raise WorkbenchError('Project file changed during inspection. Retry.', 'conflict', 409)
            return raw

    def _saved(self, project_id):
        if not isinstance(project_id, str) or not ID.fullmatch(project_id):
            raise WorkbenchError('Invalid project ID.')
        with self.lock:
            row = self.db.execute('SELECT document FROM workspace_projects WHERE id=%s', (project_id,)).fetchone()
        if row is None:
            raise WorkbenchError('Project not found.', 'not_found', 404)
        result = json.loads(row[0])
        return result

    @staticmethod
    def _summary(saved):
        return {key: saved[key] for key in ('id', 'name', 'root', 'manifest_path', 'manifest_sha256')}

    def list(self):
        with self.lock:
            rows = self.db.execute('SELECT document FROM workspace_projects ORDER BY id').fetchall()
        return {'mode': 'inspection', 'roots': sorted(self.roots),
                'projects': [self._summary(json.loads(row[0])) for row in rows]}

    def open(self, body):
        closed(body, ('root', 'manifest_path'))
        root, path = body['root'], relative_path(body['manifest_path'])
        if not isinstance(root, str) or root not in self.roots:
            raise WorkbenchError('Choose a configured project root.', 'unavailable', 409)
        try:
            raw = self._read(root, path, MANIFEST_LIMIT)
        except OSError:
            raise WorkbenchError('Project manifest is missing or cannot be safely read.', 'unavailable', 400) from None
        value = manifest(decode(raw))
        saved = {'id': value['id'], 'name': value['name'], 'root': root,
                 'root_identity': self.roots[root][1], 'manifest_path': path,
                 'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'manifest': value}
        document = encode(saved)
        with self.lock, self.db.transaction():
            existing = self.db.execute('SELECT document FROM workspace_projects WHERE id=%s', (value['id'],)).fetchone()
            if existing and existing[0] != document:
                raise WorkbenchError('This project ID already names a different snapshot or root. Keep the original or use a new project ID.', 'conflict', 409)
            if not existing:
                self.db.execute('INSERT INTO workspace_projects VALUES (%s,%s)', (value['id'], document))
        return self.get(value['id'])

    def _bound(self, saved):
        entry = self.roots.get(saved['root'])
        return bool(entry and entry[1] == saved['root_identity'])

    def _inspect(self, root, ref, budget, limit=FILE_LIMIT):
        result = {**ref, 'status': 'available', 'integrity': 'unverified'}
        try:
            with self._file(root, ref['path']) as (_fd, info):
                result['bytes'] = info.st_size
            if info.st_size > limit or info.st_size > budget[0]:
                result['reason'] = 'Present; content exceeds the bounded hash inspection budget.'
                return result
            raw = self._read(root, ref['path'], min(limit, budget[0]))
            budget[0] -= len(raw)
            result['bytes'] = len(raw)
            result['observed_sha256'] = hashlib.sha256(raw).hexdigest()
            if 'sha256' in ref:
                result['integrity'] = 'verified' if ref['sha256'] == result['observed_sha256'] else 'mismatch'
            else:
                result['reason'] = 'No expected hash declared; scientific meaning is not verified.'
        except FileNotFoundError:
            result.update(status='missing', reason='Referenced file is missing.')
        except (OSError, WorkbenchError):
            result.update(status='unavailable', reason='File cannot be safely inspected or changed during inspection.')
        return result

    def get(self, project_id):
        saved = self._saved(project_id)
        result = {**self._summary(saved), 'mode': 'inspection', 'execution': 'unsupported',
                  'manifest_status': 'unavailable'}
        bound = self._bound(saved)
        if bound:
            try:
                raw = self._read(saved['root'], saved['manifest_path'], MANIFEST_LIMIT)
                result['manifest_status'] = 'unchanged' if hashlib.sha256(raw).hexdigest() == saved['manifest_sha256'] else 'changed'
            except FileNotFoundError:
                result['manifest_status'] = 'missing'
            except (OSError, WorkbenchError):
                pass
        budget = [INSPECTION_LIMIT]
        for group in GROUPS:
            result[group] = []
            for ref in saved['manifest'][group]:
                if not bound:
                    item = {**ref, 'status': 'unavailable', 'integrity': 'unverified',
                            'reason': 'Original project root is not configured; snapshot retained.'}
                elif 'path' not in ref:
                    item = {**ref, 'status': 'unverified', 'reason': 'Declared requirement; no runtime probe is executed.'}
                elif group == 'requirements':
                    item = {**ref, 'status': 'present_unqualified', 'reason': 'File presence does not establish runtime compatibility.'}
                    try:
                        with self._file(saved['root'], ref['path']):
                            pass
                    except FileNotFoundError:
                        item.update(status='missing', reason='Required file is missing.')
                    except (OSError, WorkbenchError):
                        item.update(status='unavailable', reason='Required file cannot be safely inspected.')
                else:
                    item = self._inspect(saved['root'], ref, budget, DATA_LIMIT if group == 'data' else FILE_LIMIT)
                result[group].append(item)
        return result

    def read_data_reference(self, project_id, reference_id, expected_sha256, limit):
        """Capture a selected saved reference; source owners interpret its bytes."""
        if not isinstance(expected_sha256, str) or not SHA.fullmatch(expected_sha256):
            raise WorkbenchError('Import requires the observed source SHA256.')
        if type(limit) is not int or not 0 < limit <= DATA_LIMIT:
            raise WorkbenchError('Invalid bounded data read limit.')
        saved = self._saved(project_id)
        if not self._bound(saved):
            raise WorkbenchError('Original project root is not configured.', 'unavailable', 409)
        ref = next((entry for entry in saved['manifest']['data'] if entry['id'] == reference_id), None)
        if ref is None:
            raise WorkbenchError('Data reference not found.', 'not_found', 404)
        try:
            raw = self._read(saved['root'], ref['path'], limit)
        except OSError:
            raise WorkbenchError('Data reference cannot be safely read.', 'unavailable', 409) from None
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256 or ref.get('sha256', digest) != digest:
            raise WorkbenchError('Data changed or differs from its declared SHA256. Inspect again before importing.', 'conflict', 409)
        return raw, {'project_id': project_id, 'manifest_sha256': saved['manifest_sha256'],
                     'reference_id': reference_id, 'path': ref['path'], 'measured_sha256': digest}

    def evidence(self, project_id, reference_id):
        saved = self._saved(project_id)
        if not self._bound(saved):
            raise WorkbenchError('Original project root is not configured.', 'unavailable', 409)
        ref = next((entry for entry in saved['manifest']['evidence'] if entry['id'] == reference_id), None)
        if ref is None:
            raise WorkbenchError('Evidence reference not found.', 'not_found', 404)
        if Path(ref['path']).suffix.lower() not in ('.json', '.txt', '.md'):
            raise WorkbenchError('Only bounded plain text, Markdown and JSON evidence can be previewed.', 'unsupported', 400)
        try:
            raw = self._read(saved['root'], ref['path'], TEXT_LIMIT)
            value = raw.decode('utf-8')
        except (OSError, UnicodeError):
            raise WorkbenchError('Evidence is unavailable or is not UTF-8 text.', 'unavailable', 409) from None
        digest = hashlib.sha256(raw).hexdigest()
        if ref.get('sha256', digest) != digest:
            raise WorkbenchError('Evidence differs from its declared SHA256.', 'conflict', 409)
        if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise WorkbenchError('Evidence contains non-text control characters.', 'unsupported', 400)
        return {'id': ref['id'], 'label': ref['label'], 'text': value, 'sha256': digest,
                'external': True, 'scientific_verification': 'not_performed'}
