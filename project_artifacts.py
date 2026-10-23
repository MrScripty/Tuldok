"""Exact project payload custody, separate from domain role and retention policy.

Declarations contain intrinsic byte identity only. Domain records own origin,
media type, unique/regenerable policy and permission. Publishing never deletes a
final payload on SQL rollback: unreferenced immutable bytes remain inert. Local
resolution capabilities never enter portable records, and no source is executed.
"""
from contextlib import contextmanager
import copy
import errno
import hashlib
import os
import re
import stat
import threading
import uuid

from project_store import (ProjectStoreError, anchored_directory, DIR_FLAGS, FILE_FLAGS,
                           _directory, _physical, _relative_parts, _rename_noreplace, _walk)

FORMAT = 'project_artifact_v1'
MAX_BYTES = 2 ** 63 - 1
DEFAULT_READ_BYTES = 40 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024


class ProjectArtifactError(ProjectStoreError):
    pass


class _Missing(Exception):
    pass


def _fail(message, code='invalid', status=400):
    raise ProjectArtifactError(message, code, status)


def validate_declaration(value):
    if type(value) is not dict:
        _fail('Artifact declaration must be an object.')
    if value.get('format') != FORMAT:
        if type(value.get('format')) is str and re.fullmatch(r'project_artifact_v[1-9][0-9]*', value['format']):
            _fail('Unsupported artifact declaration format.', 'unsupported', 422)
        _fail('Invalid artifact declaration format.')
    if set(value) != {'format', 'sha256', 'bytes'}:
        _fail('Artifact declarations contain only format, SHA256 and byte count.')
    digest, size = value['sha256'], value['bytes']
    if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        _fail('Artifact requires a SHA256 digest.')
    if type(size) is not int or not 0 <= size <= MAX_BYTES:
        _fail('Artifact byte count must fit a nonnegative signed 64-bit integer.')
    return dict(format=FORMAT, sha256=digest, bytes=size)


def _maximum(declaration, maximum_bytes):
    if maximum_bytes is not None:
        if type(maximum_bytes) is not int or not 0 <= maximum_bytes <= MAX_BYTES:
            _fail('Artifact caller byte bound must be a nonnegative integer.')
        if declaration['bytes'] > maximum_bytes:
            _fail('Artifact exceeds the consuming operation byte bound.', 'too_large', 413)


def _info(fd, *, rooted=False):
    info = os.fstat(fd)
    # An explicit caller fd or our unlinked private snapshot can have no name.
    # Rooted selected files must have exactly one name; aliases are never accepted.
    if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1 or (rooted and info.st_nlink != 1):
        _fail('Artifact source must be an ordinary file without hard-link aliases.')
    return info


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _write(fd, raw):
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        if not written:
            raise OSError(errno.EIO, 'short artifact write')
        view = view[written:]


def _observe(fd, declaration, *, output=None):
    """Observe one bounded source and optionally capture the exact observed bytes."""
    before = _info(fd)
    if before.st_size != declaration['bytes']:
        return dict(state='corrupt', expected_sha256=declaration['sha256'], expected_bytes=declaration['bytes'],
                    observed_sha256=None, observed_bytes=before.st_size)
    digest, count = hashlib.sha256(), 0
    while True:
        raw = os.pread(fd, min(CHUNK_BYTES, declaration['bytes'] + 1 - count), count)
        if not raw:
            break
        count += len(raw)
        digest.update(raw)
        if output is not None:
            _write(output, raw)
        if count > declaration['bytes']:
            break
    after = _info(fd)
    if _identity(before) != _identity(after):
        _fail('Artifact source changed during observation.', 'stale', 409)
    observed = digest.hexdigest()
    return dict(state='verified' if count == declaration['bytes'] and observed == declaration['sha256'] else 'corrupt',
                expected_sha256=declaration['sha256'], expected_bytes=declaration['bytes'],
                observed_sha256=observed, observed_bytes=count)


def _verified(observation):
    if observation['state'] != 'verified':
        failure = ProjectArtifactError('Artifact bytes disagree with their exact declaration.', 'invalid', 400)
        failure.observation = observation
        raise failure


def _io(error, *, published=False):
    if published:
        raise ProjectArtifactError('Artifact publication durability is unknown; retain bytes and retry the same identity.',
                                   'unknown', 503) from error
    if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENXIO):
        raise ProjectArtifactError('Unsafe artifact filesystem object.') from error
    if error.errno in (errno.EXDEV, errno.ENOSYS, errno.EOPNOTSUPP):
        raise ProjectArtifactError('Required artifact filesystem mechanism is unsupported.', 'unsupported', 422) from error
    raise ProjectArtifactError('Artifact bytes are unavailable.', 'unavailable', 503) from error


class ProjectArtifacts:
    def __init__(self, store, *, resolutions=None):
        """Bind optional explicit SHA -> {root_fd, root_path, relative} locations.

        Overrides choose one local source explicitly; a corrupt selected source
        never silently falls back to another copy. The caller retains its fds;
        this owner duplicates and releases only its own root capabilities.
        """
        self.store = store
        self._mutex = threading.RLock()
        self._closed = False
        self._resolutions = {}
        try:
            if resolutions is not None and type(resolutions) is not dict:
                _fail('Artifact resolutions must be an explicit mapping.')
            for digest, location in (resolutions or {}).items():
                validate_declaration(dict(format=FORMAT, sha256=digest, bytes=0))
                if type(location) is not dict or set(location) != {'root_fd', 'root_path', 'relative'}:
                    _fail('Invalid local artifact resolution fields.')
                if type(location['root_fd']) is not int or location['root_fd'] < 0:
                    _fail('Local artifact resolution needs a directory capability.')
                parts = _relative_parts(location['relative'])
                with anchored_directory(location['root_fd'], root_path=location['root_path']):
                    owned = os.dup(location['root_fd'])
                    self._resolutions[digest] = dict(root_fd=owned, root_path=location['root_path'], parts=parts)
        except OSError as error:
            self.close()
            _io(error)
        except BaseException:
            self.close()
            raise

    def _ensure_open(self):
        if self._closed:
            _fail('Artifact owner is closed.', 'unavailable', 409)

    @contextmanager
    def _source(self, root_fd, declaration):
        override = self._resolutions.get(declaration['sha256'])
        if override is None:
            parts = ['artifacts', 'sha256', declaration['sha256']]
            yield from self._source_at(root_fd, parts)
        else:
            with anchored_directory(override['root_fd'], root_path=override['root_path']) as external:
                yield from self._source_at(external, override['parts'])

    def _source_at(self, root_fd, parts):
        parent = source = None
        try:
            try:
                parent = _walk(root_fd, parts[:-1])
                source = os.open(parts[-1], FILE_FLAGS, dir_fd=parent)
            except FileNotFoundError as error:
                raise _Missing() from error
            _info(source, rooted=True)
            yield source
            # Path replacement cannot redirect a pinned fd, but it invalidates
            # the selected source location and must not be called current.
            current = _walk(root_fd, parts[:-1])
            try:
                if _physical(current) != _physical(parent):
                    _fail('Artifact source directory changed.', 'stale', 409)
                selected = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
                if (selected.st_dev, selected.st_ino) != _physical(source):
                    _fail('Artifact source location changed.', 'stale', 409)
            finally:
                os.close(current)
        finally:
            if source is not None:
                os.close(source)
            if parent is not None:
                os.close(parent)

    def inspect(self, declaration):
        """Presence is unverified; it never claims a hash was checked."""
        declaration = validate_declaration(declaration)
        with self._mutex:
            self._ensure_open()
            try:
                with self.store.root_directory() as root:
                    try:
                        with self._source(root, declaration) as source:
                            observed = _info(source, rooted=True).st_size
                            state = 'unverified'
                    except _Missing:
                        observed, state = None, 'missing'
                return dict(state=state, expected_sha256=declaration['sha256'], expected_bytes=declaration['bytes'],
                            observed_sha256=None, observed_bytes=observed)
            except OSError as error:
                _io(error)

    def status(self, declaration):
        declaration = validate_declaration(declaration)
        with self._mutex:
            self._ensure_open()
            try:
                with self.store.root_directory() as root:
                    try:
                        with self._source(root, declaration) as source:
                            return _observe(source, declaration)
                    except _Missing:
                        return dict(state='missing', expected_sha256=declaration['sha256'], expected_bytes=declaration['bytes'],
                                    observed_sha256=None, observed_bytes=None)
            except OSError as error:
                _io(error)

    @contextmanager
    def _payload_directory(self, root):
        artifacts = payloads = None
        try:
            artifacts = _directory(root, 'artifacts', create=True)
            payloads = _directory(artifacts, 'sha256', create=True)
            yield artifacts, payloads
        finally:
            if payloads is not None:
                os.close(payloads)
            if artifacts is not None:
                os.close(artifacts)

    def _publish(self, declaration, capture):
        with self._mutex:
            self._ensure_open()
            published = False
            try:
                with self.store.root_directory() as root, self._payload_directory(root) as (artifacts, payloads):
                    temporary = '.artifact-' + uuid.uuid4().hex + '.tmp'
                    output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                     0o600, dir_fd=payloads)
                    try:
                        capture(output)
                        os.fchmod(output, 0o400)
                        os.fsync(output)
                    finally:
                        os.close(output)
                    try:
                        _rename_noreplace(payloads, temporary, declaration['sha256'])
                        published = True
                    except FileExistsError:
                        existing = os.open(declaration['sha256'], FILE_FLAGS, dir_fd=payloads)
                        try:
                            _info(existing, rooted=True)
                            _verified(_observe(existing, declaration))
                            os.fsync(existing)
                        finally:
                            os.close(existing)
                        os.unlink(temporary, dir_fd=payloads)
                        published = True
                    os.fsync(payloads)
                    os.fsync(artifacts)
                    os.fsync(root)
                return copy.deepcopy(declaration)
            except OSError as error:
                _io(error, published=published)
            # Failed staging remains inert. No callback owns deletion of final bytes.

    def publish_bytes(self, raw, declaration, *, maximum_bytes=None):
        declaration = validate_declaration(declaration)
        _maximum(declaration, maximum_bytes)
        if type(raw) is not bytes:
            _fail('Artifact publication requires exact bytes.')
        if len(raw) != declaration['bytes'] or hashlib.sha256(raw).hexdigest() != declaration['sha256']:
            _fail('Artifact input differs from its declaration.')
        return self._publish(declaration, lambda output: _write(output, raw))

    def publish_fd(self, source_fd, declaration, *, maximum_bytes=None):
        declaration = validate_declaration(declaration)
        _maximum(declaration, maximum_bytes)
        if type(source_fd) is not int or source_fd < 0:
            _fail('Artifact publication requires an explicit file capability.')
        def capture(output):
            _verified(_observe(source_fd, declaration, output=output))
        return self._publish(declaration, capture)

    def _snapshot(self, declaration):
        snapshot = None
        try:
            with self.store.root_directory() as root:
                local = staging = None
                try:
                    with self._source(root, declaration) as source:
                        local = _directory(root, '.tuldok-local', create=True)
                        staging = _directory(local, 'artifact-snapshots', create=True)
                        temporary = '.snapshot-' + uuid.uuid4().hex + '.tmp'
                        output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                         0o600, dir_fd=staging)
                        try:
                            _verified(_observe(source, declaration, output=output))
                            os.fchmod(output, 0o400)
                            os.fsync(output)
                        finally:
                            os.close(output)
                        snapshot = os.open(temporary, FILE_FLAGS, dir_fd=staging)
                        _info(snapshot, rooted=True)
                        os.unlink(temporary, dir_fd=staging)
                except _Missing as error:
                    raise ProjectArtifactError('Required artifact bytes are missing.', 'unavailable', 404) from error
                finally:
                    if staging is not None:
                        os.close(staging)
                    if local is not None:
                        os.close(local)
            return snapshot
        except BaseException:
            if snapshot is not None:
                os.close(snapshot)
            raise

    @contextmanager
    def open_verified(self, declaration, *, maximum_bytes=None):
        """Borrow a verified unlinked read-only snapshot, not a mutable source fd."""
        declaration = validate_declaration(declaration)
        _maximum(declaration, maximum_bytes)
        with self._mutex:
            self._ensure_open()
            try:
                snapshot = self._snapshot(declaration)
            except OSError as error:
                _io(error)
        # Release owner/project locks before consumer work. Source resolution
        # roots can close while this independent byte snapshot remains borrowed.
        try:
            yield snapshot
        finally:
            os.close(snapshot)

    def read_blob(self, descriptor, *, maximum_bytes=DEFAULT_READ_BYTES):
        if type(descriptor) is not dict or set(descriptor) != {'sha256', 'bytes'}:
            _fail('Blob references contain exactly SHA256 and byte count.')
        declaration = dict(format=FORMAT, **descriptor)
        with self.open_verified(declaration, maximum_bytes=maximum_bytes) as source:
            chunks = []
            while True:
                raw = os.read(source, CHUNK_BYTES)
                if not raw:
                    break
                chunks.append(raw)
            return b''.join(chunks)

    def close(self):
        with self._mutex:
            if not self._closed:
                for location in self._resolutions.values():
                    os.close(location['root_fd'])
                self._resolutions.clear()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()
