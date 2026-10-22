"""Canonical POSIX-local project checkpoints; domain codecs own document meaning.

Only the inventory in .tuldok/project.json confers authority. Immutable revisions
are durable before its atomic replacement. The directory flock excludes cooperating
writers by physical root identity, including alternate spellings of the same root.
Uncooperative checkout/edit operations are forbidden while open and detected before
publication. An uncertain publication is reconciled by reopening and its receipt.
"""
import copy
import ctypes
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import uuid

FORMAT = 'tuldok_project_v1'
GITIGNORE = b'/artifacts/\n/.tuldok-local/\n/.venv/\n/__pycache__/\n/PGDATA/\n/output/\n'
MAX_RECORD_BYTES = 40 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
# Coordinated internal codecs; adding a family requires its owning decoder.
SUPPORTED_FORMATS = {
    'workbench_text': 'workbench_text_v1',
    'workbench_record': 'workbench_record_v1',
    'workbench_response': 'workbench_response_v1',
    'workbench_preference': 'workbench_preference_v1',
    'saved_selection': 'saved_selection_v1',
    'saved_search': 'saved_search_v1',
    'dataset_release': 'dataset_release_v1',
    'dataset_exposure': 'dataset_exposure_v1',
    'model_definition': 'model_definition_history_v1',
    'pipeline_graph': 'pipeline_graph_history_v1',
    'recipe_definition': 'recipe_definition_history_v1',
    'model_material': 'retained_model_material_v1',
    'recipe_material': 'retained_recipe_material_v1',
    'project_snapshot': 'retained_project_snapshot_v1',
    'runtime_material': 'retained_runtime_material_v1',
    'study_history': 'project_study_history_v1',
    'trial_history': 'project_trial_history_v1',
    'run_history': 'project_run_history_v1',
    'candidate_history': 'project_candidate_history_v1',
    'project_artifact': 'project_artifact_v1',
    'project_operation': 'project_operation_v1',
    'project_fork': 'project_fork_v1',
    'project_file': 'project_file_v1',
    'project_extraction': 'project_extraction_v1',
    'generation_history': 'project_generation_history_v1',
    'grounded_history': 'project_grounded_history_v1',
    'caption_proposal_history': 'project_caption_proposal_history_v1',
    'text_proposal_history': 'project_text_proposal_history_v1',
}
MAX_RECORDS = 100_000
MAX_TOTAL_BYTES = 256 * 1024 * 1024
IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
REQUEST_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$')
DOMAIN_FORMAT = re.compile(r'^[a-z][a-z0-9_]{0,95}_v([1-9][0-9]*)$')
SHA256 = re.compile(r'^[a-f0-9]{64}$')
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class ProjectStoreError(ValueError):
    def __init__(self, message, code='invalid', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def _fail(message, code='invalid', status=400):
    raise ProjectStoreError(message, code, status)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json_value(value, depth=0):
    if depth > 64:
        _fail('Project JSON exceeds its nesting limit.')
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if not -(2 ** 63) <= value < 2 ** 63:
            _fail('Project JSON integer exceeds signed 64-bit range.')
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is str:
        if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
            _fail('Project JSON contains an invalid Unicode surrogate.')
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for key, item in value.items():
            _json_value(key, depth + 1)
            _json_value(item, depth + 1)
        return
    _fail('Project value must contain finite JSON values.')


def _encode(value):
    _json_value(value)
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('Project JSON contains duplicate object keys.')
        result[key] = value
    return result


def _decode(raw):
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda _: _fail('Project JSON contains a nonfinite number.'))
        if _encode(value) != raw:
            _fail('Project JSON must use canonical UTF-8, sorted keys, two-space indentation and LF.')
        return value
    except ProjectStoreError:
        raise
    except (ValueError, RecursionError, OverflowError) as exc:
        raise ProjectStoreError('Malformed project JSON.') from exc


def _keys(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        _fail(f'{label} has invalid or unknown fields.')


def _identifier(value, label):
    if type(value) is not str or not IDENTIFIER.fullmatch(value) or value in ('.', '..'):
        _fail(f'{label} must be a bounded path-free identifier.')


def _digest(value, label):
    if type(value) is not str or not SHA256.fullmatch(value):
        _fail(f'{label} must be a SHA256 digest.')


def _domain_format(value, family):
    match = DOMAIN_FORMAT.fullmatch(value) if type(value) is str else None
    if not match:
        _fail('Domain document requires a versioned format.')
    if value != SUPPORTED_FORMATS[family] and not (family == 'project_operation' and value == 'project_operation_v2'):
        _fail('Unsupported domain document format.', 'unsupported', 422)


def _records(records):
    if type(records) is not list or len(records) > MAX_RECORDS:
        _fail('Project records must be a bounded list.')
    result, seen, total = [], set(), 0
    for record in records:
        _keys(record, ('family', 'id', 'document'), 'Project record')
        family, identity, document = (record[k] for k in ('family', 'id', 'document'))
        _identifier(family, 'Record family')
        if family not in SUPPORTED_FORMATS:
            _fail('Unsupported project record family.', 'unsupported', 422)
        _identifier(identity, 'Record ID')
        if (family, identity) in seen:
            _fail('Duplicate project record identity.')
        seen.add((family, identity))
        if type(document) is not dict:
            _fail('Domain document must be an object.')
        _domain_format(document.get('format'), family)
        document = copy.deepcopy(document)
        raw = _encode(document)
        total += len(raw)
        if len(raw) > MAX_RECORD_BYTES or total > MAX_TOTAL_BYTES:
            _fail('Project records exceed the synchronous byte limit.')
        result.append((family, identity, document, raw))
    return sorted(result, key=lambda item: (item[0], item[1]))


def _request(key, digest):
    if type(key) is not str or not REQUEST_KEY.fullmatch(key):
        _fail('Request key must contain 1–128 supported characters.')
    _digest(digest, 'Request body digest')


def _path_string(path):
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise ProjectStoreError('Project path must be text.') from exc
    if type(value) is not str:
        _fail('Project path must be text.')
    return value


def _open_directory_path(path):
    """Walk every component without following symlinks, retaining the final fd."""
    try:
        raw = _path_string(path)
        if type(raw) is not str or '\x00' in raw or '..' in raw.split('/'):
            _fail('Unsafe project root path.')
        absolute = os.path.abspath(raw)
        fd = os.open('/', DIR_FLAGS)
        try:
            for component in absolute.split('/'):
                if not component:
                    continue
                next_fd = os.open(component, DIR_FLAGS, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return absolute, fd
        except BaseException:
            os.close(fd)
            raise
    except OSError as exc:
        _io_error(exc, 'resolve project root')


def _relative_parts(relative):
    if type(relative) is not str or not relative or len(relative) > 4096 or '\x00' in relative:
        _fail('Invalid relative project directory.')
    parts = relative.split('/')
    if any(part in ('', '.', '..') for part in parts):
        _fail('Project directory must remain beneath its configured root.')
    return parts


def _walk(root_fd, parts):
    fd = os.dup(root_fd)
    try:
        for component in parts:
            next_fd = _directory(fd, component)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _verify_origin(root_fd, root_path):
    absolute, check = _open_directory_path(root_path)
    try:
        if _physical(check) != _physical(root_fd):
            _fail('Configured project root changed.', 'stale', 409)
    finally:
        os.close(check)
    return absolute


@contextmanager
def anchored_directory(trusted_root_fd, relative='', *, root_path):
    """Borrow a rooted no-follow directory capability; caller retains root fd."""
    parts = _relative_parts(relative) if relative else []
    descriptor = None
    try:
        _verify_origin(trusted_root_fd, root_path)
        descriptor = _walk(trusted_root_fd, parts)
        yield descriptor
        _verify_origin(trusted_root_fd, root_path)
        current = _walk(trusted_root_fd, parts)
        try:
            if _physical(current) != _physical(descriptor):
                _fail('Anchored directory changed during use.', 'stale', 409)
        finally:
            os.close(current)
    except OSError as exc:
        _io_error(exc, 'access anchored directory')
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _rename_noreplace(parent_fd, staging, destination):
    # Linux's RENAME_NOREPLACE provides the required atomic no-overwrite promise.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None:
        _fail('Atomic no-replace publication is unsupported.', 'unsupported', 422)
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(parent_fd, os.fsencode(staging), parent_fd, os.fsencode(destination), 1):
        number = ctypes.get_errno()
        if number in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            _fail('Filesystem lacks atomic no-replace publication.', 'unsupported', 422)
        raise OSError(number, os.strerror(number))


def _publish_directory(parent_fd, staging, destination):
    _rename_noreplace(parent_fd, staging, destination)


def _io_error(exc, operation, unknown=False):
    if unknown:
        raise ProjectStoreError(f'Project publication outcome is unknown ({operation}); reopen and reconcile the request.',
                                'unknown', 503) from exc
    if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENXIO):
        raise ProjectStoreError(f'Unsafe filesystem object during {operation}.') from exc
    raise ProjectStoreError(f'Cannot {operation}.', 'unavailable', 503) from exc


def _physical(fd):
    info = os.fstat(fd)
    return info.st_dev, info.st_ino


def _regular(fd):
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        _fail('Project files must be ordinary files with no hard-link aliases.')
    return info


def _read(directory, name, maximum):
    fd = os.open(name, FILE_FLAGS, dir_fd=directory)
    try:
        info = _regular(fd)
        if info.st_size > maximum:
            _fail('Project file exceeds its byte limit.')
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                _fail('Project file exceeds its byte limit.')
        after = _regular(fd)
        if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            _fail('Project file changed while reading.', 'stale', 409)
        return b''.join(chunks)
    finally:
        os.close(fd)


def _sync_file(directory, name):
    fd = os.open(name, FILE_FLAGS, dir_fd=directory)
    try:
        _regular(fd)
        os.fsync(fd)
    finally:
        os.close(fd)


def _directory(parent, name, create=False):
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
    return os.open(name, DIR_FLAGS, dir_fd=parent)


def _write_file(directory, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=directory)
    try:
        _regular(fd)
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if not written:
                raise OSError(errno.EIO, 'short project write')
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


class ProjectStore:
    """Own one writable physical project root until close().

    commit replaces the complete current record set. Retained unreferenced
    revisions are never pruned. Callers validate domain semantics before commit
    and after Open; this owner validates only the generic JSON/inventory contract.
    """
    def __init__(self, path, root_fd, origin_fd, relative_parts, origin_path):
        self.path = Path(path)
        self._root_fd = root_fd
        self._origin_fd = origin_fd
        self._relative_parts = relative_parts
        self._origin_path = Path(origin_path)
        self._meta_fd = None
        self._manifest = None
        self._mutex = threading.RLock()
        self._unknown = False
        try:
            fcntl.flock(root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(root_fd)
            os.close(origin_fd)
            self._origin_fd = None
            self._root_fd = None
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise ProjectStoreError('Project already has a writer.', 'busy', 409) from exc
            _io_error(exc, 'lock project root')

    @classmethod
    def create(cls, path, name, request_key, request_sha256):
        raw = _path_string(path)
        if type(raw) is not str or '\x00' in raw or '..' in raw.split('/'):
            _fail('Unsafe project destination.')
        absolute = os.path.abspath(raw)
        parent, leaf = os.path.split(absolute)
        _, parent_fd = _open_directory_path(parent)
        try:
            return cls.create_at(parent_fd, leaf, name, request_key, request_sha256, root_path=parent)
        finally:
            os.close(parent_fd)

    @classmethod
    def create_at(cls, trusted_root_fd, relative, name, request_key, request_sha256, *, root_path):
        """Create under a configured root capability; duplicate its fd for store lifetime."""
        _request(request_key, request_sha256)
        if type(name) is not str or not name.strip() or len(name) > 200:
            _fail('Project name must contain 1–200 characters.')
        _json_value(name)
        parts = _relative_parts(relative)
        absolute = _verify_origin(trusted_root_fd, root_path)
        origin_fd = os.dup(trusted_root_fd)
        parent_fd = None
        store = None
        published = False
        try:
            parent_fd = _walk(origin_fd, parts[:-1])
            # Existing destinations, including symlinks, are never merged or replaced.
            try:
                os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                _fail('Project destination already exists.', 'conflict', 409)
            staging = '.tuldok-new-' + uuid.uuid4().hex
            os.mkdir(staging, 0o700, dir_fd=parent_fd)
            root_fd = _directory(parent_fd, staging)
            owned_origin, origin_fd = origin_fd, None
            store = cls(Path(absolute).joinpath(*parts), root_fd, owned_origin,
                        parts[:-1] + [staging], absolute)
            store._meta_fd = _directory(root_fd, '.tuldok', create=True)
            records_fd = _directory(store._meta_fd, 'records', create=True)
            os.close(records_fd)
            _write_file(root_fd, '.gitignore', GITIGNORE)
            os.fsync(root_fd)
            manifest = dict(format=FORMAT, project_id=uuid.uuid4().hex, name=name,
                            roots=[], inventory=[], receipts=[dict(request_key=request_key,
                            request_sha256=request_sha256, records_sha256=_sha(_encode([])))])
            manifest['checkpoint'] = _sha(_encode(manifest))
            store._publish(manifest, creating=True)
            store._manifest = manifest
            store._binding()
            _publish_directory(parent_fd, staging, parts[-1])
            published = True
            store._relative_parts = parts
            os.fsync(parent_fd)
            store._binding()
            return store
        except FileExistsError as exc:
            if store is not None:
                store.close()
            raise ProjectStoreError('Project destination already exists.', 'conflict', 409) from exc
        except ProjectStoreError as exc:
            if store is not None:
                store.close()
            if published:
                raise ProjectStoreError('Project destination was published but its binding changed; reopen and reconcile the request.',
                                        'unknown', 503) from exc
            raise
        except OSError as exc:
            if store is not None:
                store.close()
            _io_error(exc, 'create project', unknown=published)
        except BaseException:
            if store is not None:
                store.close()
            raise
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
            if origin_fd is not None:
                os.close(origin_fd)

    @classmethod
    def open(cls, path):
        raw = _path_string(path)
        if type(raw) is not str or '\x00' in raw or '..' in raw.split('/'):
            _fail('Unsafe project root path.')
        absolute = os.path.abspath(raw)
        parent, leaf = os.path.split(absolute)
        _, parent_fd = _open_directory_path(parent)
        try:
            return cls.open_at(parent_fd, leaf, root_path=parent)
        finally:
            os.close(parent_fd)

    @classmethod
    def open_at(cls, trusted_root_fd, relative, *, root_path):
        """Open a descendant without following any configured-root or child alias."""
        parts = _relative_parts(relative)
        absolute = _verify_origin(trusted_root_fd, root_path)
        origin_fd = os.dup(trusted_root_fd)
        store = None
        try:
            fd = _walk(origin_fd, parts)
            owned_origin, origin_fd = origin_fd, None
            store = cls(Path(absolute).joinpath(*parts), fd, owned_origin, parts, absolute)
            store._meta_fd = _directory(fd, '.tuldok')
            store._manifest, _ = store._load()
            return store
        except OSError as exc:
            if store is not None:
                store.close()
            _io_error(exc, 'open project')
        except BaseException:
            if store is not None:
                store.close()
            raise
        finally:
            if origin_fd is not None:
                os.close(origin_fd)

    def _binding(self):
        if self._root_fd is None:
            _fail('Project store is closed.', 'unavailable', 409)
        if self._unknown:
            _fail('Reopen project to reconcile an unknown publication.', 'unknown', 503)
        _verify_origin(self._origin_fd, self._origin_path)
        check = _walk(self._origin_fd, self._relative_parts)
        try:
            if _physical(check) != _physical(self._root_fd):
                _fail('Project root changed; close and reopen.', 'stale', 409)
            meta = _directory(check, '.tuldok')
            try:
                if _physical(meta) != _physical(self._meta_fd):
                    _fail('Project metadata directory changed.', 'stale', 409)
            finally:
                os.close(meta)
        finally:
            os.close(check)

    @contextmanager
    def root_directory(self):
        """Borrow this project's physical root while its writer binding is pinned."""
        with self._mutex:
            self.snapshot()
            descriptor = os.dup(self._root_fd)
            try:
                yield descriptor
                self._binding()
            finally:
                os.close(descriptor)

    def _load(self):
        self._binding()
        raw = _read(self._meta_fd, 'project.json', MAX_MANIFEST_BYTES)
        manifest = _decode(raw)
        if type(manifest) is not dict:
            _fail('Project checkpoint must be an object.')
        if manifest.get('format') != FORMAT:
            if type(manifest.get('format')) is str and re.fullmatch(r'tuldok_project_v[1-9][0-9]*', manifest['format']):
                _fail('Unsupported project format.', 'unsupported', 422)
            _fail('Invalid project format.')
        _keys(manifest, ('format', 'project_id', 'name', 'checkpoint', 'roots', 'inventory', 'receipts'), 'Project checkpoint')
        identity = manifest['project_id']
        if type(identity) is not str or not re.fullmatch('[a-f0-9]{32}', identity):
            _fail('Invalid project UUID.')
        if type(manifest['name']) is not str or not manifest['name'].strip() or len(manifest['name']) > 200:
            _fail('Invalid project display name.')
        _digest(manifest['checkpoint'], 'Checkpoint')
        core = {k: v for k, v in manifest.items() if k != 'checkpoint'}
        if _sha(_encode(core)) != manifest['checkpoint']:
            _fail('Project checkpoint digest does not match its contents.')
        inventory = manifest['inventory']
        if type(inventory) is not list or len(inventory) > MAX_RECORDS:
            _fail('Invalid project inventory.')
        loaded, roots, total, previous = [], [], 0, None
        for entry in inventory:
            _keys(entry, ('family', 'id', 'format', 'namespace', 'path', 'bytes', 'sha256'), 'Inventory entry')
            family, record_id, digest = entry['family'], entry['id'], entry['sha256']
            _identifier(family, 'Record family')
            if family not in SUPPORTED_FORMATS:
                _fail('Unsupported project record family.', 'unsupported', 422)
            _identifier(record_id, 'Record ID')
            _digest(digest, 'Record digest')
            _domain_format(entry['format'], family)
            key = (family, record_id)
            if previous is not None and key <= previous:
                _fail('Inventory must have unique sorted record identities.')
            previous = key
            if entry['namespace'] != identity or entry['path'] != f'records/{family}/{record_id}/{digest}.json':
                _fail('Invalid inventory namespace or rooted record path.')
            if type(entry['bytes']) is not int or not 0 < entry['bytes'] <= MAX_RECORD_BYTES:
                _fail('Invalid inventory record byte count.')
            total += entry['bytes']
            if total > MAX_TOTAL_BYTES:
                _fail('Project records exceed their total byte limit.')
            record_raw = self._record_file(family, record_id, digest)
            if len(record_raw) != entry['bytes'] or _sha(record_raw) != digest:
                _fail('Canonical record bytes changed or are corrupt.', 'stale' if self._manifest else 'invalid', 409 if self._manifest else 400)
            document = _decode(record_raw)
            if type(document) is not dict or document.get('format') != entry['format']:
                _fail('Domain document format disagrees with its inventory.')
            loaded.append(dict(family=family, id=record_id, document=document))
            roots.append(dict(family=family, id=record_id))
        if manifest['roots'] != roots:
            _fail('Project membership roots disagree with the inventory.')
        if type(manifest['receipts']) is not list or not manifest['receipts']:
            _fail('Project requires operation receipts.')
        seen = set()
        for receipt in manifest['receipts']:
            _keys(receipt, ('request_key', 'request_sha256', 'records_sha256'), 'Operation receipt')
            _request(receipt['request_key'], receipt['request_sha256'])
            _digest(receipt['records_sha256'], 'Receipt records digest')
            if receipt['request_key'] in seen:
                _fail('Duplicate operation receipt key.')
            seen.add(receipt['request_key'])
        if manifest['receipts'][-1]['records_sha256'] != _sha(_encode(loaded)):
            _fail('Latest operation receipt disagrees with the current record set.')
        # A second pointer read detects checkout/replacement during closure validation.
        if _read(self._meta_fd, 'project.json', MAX_MANIFEST_BYTES) != raw:
            _fail('Project checkpoint changed while reading.', 'stale', 409)
        self._binding()
        return manifest, loaded

    def _record_file(self, family, record_id, digest, raw=None, sync=False):
        fds = []
        try:
            parent = self._meta_fd
            for part in ('records', family, record_id):
                parent = _directory(parent, part, create=raw is not None)
                fds.append(parent)
            name = digest + '.json'
            if raw is not None:
                temporary = '.record-' + uuid.uuid4().hex + '.tmp'
                _write_file(parent, temporary, raw)
                try:
                    _rename_noreplace(parent, temporary, name)
                except FileExistsError:
                    if _read(parent, name, MAX_RECORD_BYTES) != raw:
                        _fail('Immutable project revision already has different bytes.')
                    os.unlink(temporary, dir_fd=parent)
                sync = True
            if sync:
                _sync_file(parent, name)
                for fd in reversed(fds):
                    os.fsync(fd)
                os.fsync(self._meta_fd)
            return _read(parent, name, MAX_RECORD_BYTES)
        finally:
            for fd in reversed(fds):
                os.close(fd)

    def _publish(self, manifest, creating=False):
        raw = _encode(manifest)
        if len(raw) > MAX_MANIFEST_BYTES:
            _fail('Project checkpoint exceeds its byte limit.')
        temporary = '.checkpoint-' + uuid.uuid4().hex + '.tmp'
        replaced = False
        try:
            _write_file(self._meta_fd, temporary, raw)
            self._binding()
            if not creating:
                current, _ = self._load()
                if current != self._manifest:
                    _fail('Project checkpoint changed before publication.', 'stale', 409)
            # Creation owns a new exclusive directory; commit owns its root flock.
            if creating:
                _rename_noreplace(self._meta_fd, temporary, 'project.json')
                replaced = True
            else:
                os.replace(temporary, 'project.json', src_dir_fd=self._meta_fd, dst_dir_fd=self._meta_fd)
                replaced = True
            os.fsync(self._meta_fd)
            os.fsync(self._root_fd)
        except OSError as exc:
            self._unknown = replaced
            _io_error(exc, 'publish checkpoint', unknown=replaced)
        # Temporary/orphan files remain inert after failures and process interruption.

    def _snapshot(self, manifest, records):
        return dict(project_id=manifest['project_id'], name=manifest['name'],
                    checkpoint=manifest['checkpoint'], records=copy.deepcopy(records))

    def snapshot(self):
        with self._mutex:
            try:
                manifest, records = self._load()
                if manifest != self._manifest:
                    _fail('Project checkpoint changed; close and reopen.', 'stale', 409)
                return self._snapshot(manifest, records)
            except OSError as exc:
                _io_error(exc, 'read project snapshot')

    def reconcile(self, request_key, request_sha256):
        """Inspect retry identity before a domain mutation; never repeat effects."""
        _request(request_key, request_sha256)
        with self._mutex:
            snapshot = self.snapshot()
            for receipt in self._manifest['receipts']:
                if receipt['request_key'] == request_key:
                    if receipt['request_sha256'] != request_sha256:
                        _fail('Request key was already used with different input.', 'conflict', 409)
                    return snapshot
            return None

    def commit(self, records, expected_checkpoint, request_key, request_sha256):
        _request(request_key, request_sha256)
        _digest(expected_checkpoint, 'Expected checkpoint')
        prepared = _records(records)
        normalized = [dict(family=f, id=i, document=d) for f, i, d, _ in prepared]
        records_digest = _sha(_encode(normalized))
        with self._mutex:
            try:
                current, loaded = self._load()
                if current != self._manifest:
                    _fail('Project checkpoint changed; close and reopen.', 'stale', 409)
                for receipt in current['receipts']:
                    if receipt['request_key'] == request_key:
                        if receipt['request_sha256'] != request_sha256 or receipt['records_sha256'] != records_digest:
                            _fail('Request key was already used with different input.', 'conflict', 409)
                        return self._snapshot(current, loaded)
                if expected_checkpoint != current['checkpoint']:
                    _fail('Expected project checkpoint is stale.', 'stale', 409)
                manifest = copy.deepcopy(current)
                inventory = []
                for family, identity, document, raw in prepared:
                    digest = _sha(raw)
                    self._record_file(family, identity, digest, raw)
                    inventory.append(dict(family=family, id=identity, format=document['format'],
                        namespace=current['project_id'], path=f'records/{family}/{identity}/{digest}.json',
                        bytes=len(raw), sha256=digest))
                manifest['inventory'] = inventory
                manifest['roots'] = [dict(family=f, id=i) for f, i, _, _ in prepared]
                manifest['receipts'].append(dict(request_key=request_key,
                    request_sha256=request_sha256, records_sha256=records_digest))
                del manifest['checkpoint']
                manifest['checkpoint'] = _sha(_encode(manifest))
                self._publish(manifest)
                self._manifest = manifest
                return self._snapshot(manifest, normalized)
            except OSError as exc:
                _io_error(exc, 'commit project records')

    def save(self, expected_checkpoint):
        _digest(expected_checkpoint, 'Expected checkpoint')
        with self._mutex:
            snapshot = self.snapshot()
            if expected_checkpoint != snapshot['checkpoint']:
                _fail('Expected project checkpoint is stale.', 'stale', 409)
            try:
                for entry in self._manifest['inventory']:
                    self._record_file(entry['family'], entry['id'], entry['sha256'], sync=True)
                _sync_file(self._meta_fd, 'project.json')
                os.fsync(self._meta_fd)
                os.fsync(self._root_fd)
                # Imported/copied roots may not yet have a durable directory entry.
                parent_fd = _walk(self._origin_fd, self._relative_parts[:-1])
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
                if self.snapshot() != snapshot:
                    _fail('Project changed during Save.', 'stale', 409)
            except OSError as exc:
                _io_error(exc, 'save project checkpoint')
            return snapshot

    def recover_checkpoint(self):
        """Explicitly re-read and sync this retained physical writer binding.

        Execution callers must first fence dispatch and drain actual local
        custody. This method resolves only filesystem publication uncertainty;
        it does not select a SQL outcome or authorize any work to resume.
        """
        with self._mutex:
            self._unknown = False
            try:
                manifest, records = self._load()
                self._manifest = manifest
                return self.save(self._snapshot(manifest, records)['checkpoint'])
            except BaseException:
                self._unknown = True
                raise

    def close(self):
        with self._mutex:
            if self._meta_fd is not None:
                os.close(self._meta_fd)
                self._meta_fd = None
            if self._root_fd is not None:
                # Closing releases the flock. Explicit unlock would release it in
                # an inherited descriptor shared by a forked process too.
                os.close(self._root_fd)
                self._root_fd = None
            if self._origin_fd is not None:
                os.close(self._origin_fd)
                self._origin_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
