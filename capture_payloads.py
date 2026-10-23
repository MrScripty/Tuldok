"""Bounded-memory, descriptor-backed payloads for explicitly streamed recipes.

These objects never serialize a live path into execution material. Publication
copies and hashes the selected bytes into the existing owned inventory.
"""
import hashlib
import os
import stat

from workbench import WorkbenchError

CHUNK_BYTES = 1024 * 1024
FORMAT = 'streamed_project_inputs_v1'


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid,
            info.st_gid, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class FilePayload:
    def __init__(self, descriptor, maximum, *, expected_sha256=None, guard=None):
        self.fd = os.dup(descriptor)
        self.guard = guard
        try:
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise WorkbenchError('Capture must be a bounded regular file.', 'too_large', 400)
            self.size = info.st_size
            self.original = identity(info)
            self.guard_identity = guard() if guard else None
            self.expected_sha256 = expected_sha256
            self.expected_sha256 = self._transfer()
        except BaseException:
            self.close()
            raise

    def __len__(self):
        return self.size

    def close(self):
        if getattr(self, 'fd', None) is not None:
            os.close(self.fd)
            self.fd = None

    def __del__(self):
        self.close()

    def _check(self):
        try:
            if (self.fd is None or identity(os.fstat(self.fd)) != self.original
                    or (self.guard and self.guard() != self.guard_identity)):
                raise WorkbenchError('Selected capture identity changed.', 'conflict', 409)
        except OSError as error:
            raise WorkbenchError('Selected capture path unavailable.', 'unavailable', 409) from error

    def _transfer(self, destination=None):
        self._check()
        digest = hashlib.sha256()
        offset = 0
        while offset < self.size:
            chunk = os.pread(self.fd, min(CHUNK_BYTES, self.size - offset), offset)
            if not chunk:
                raise WorkbenchError('Selected capture was truncated.', 'conflict', 409)
            digest.update(chunk)
            if destination is not None:
                destination.write(chunk)
            offset += len(chunk)
        self._check()
        measured = digest.hexdigest()
        if self.expected_sha256 is not None and measured != self.expected_sha256:
            raise WorkbenchError('Selected capture digest changed.', 'conflict', 409)
        return measured

    def digest(self):
        return self._transfer()

    def copy_to(self, handle):
        self._transfer(handle)

    def __eq__(self, other):
        if isinstance(other, FilePayload):
            return len(self) == len(other) and self.digest() == other.digest()
        if isinstance(other, bytes):
            return len(self) == len(other) and self.digest() == hashlib.sha256(other).hexdigest()
        return NotImplemented


def payload_digest(raw):
    return raw.digest() if isinstance(raw, FilePayload) else hashlib.sha256(raw).hexdigest()


def copy_payload(raw, destination):
    if isinstance(raw, FilePayload):
        raw.copy_to(destination)
    else:
        destination.write(raw)
