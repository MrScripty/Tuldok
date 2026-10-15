"""Local authoring I/O; the canonical extension owner supplies all declaration policy."""
import os
from pathlib import Path
import stat

from extension_contract import (ExtensionError, ReadLimitError, MANIFEST_LIMIT,
                                catalog, declaration, digest, relative_path, schemas)


class RootReader:
    """Own one explicitly selected directory handle for the duration of validation."""
    def __init__(self, root):
        self.root = Path(root)
        self.fd = None

    def __enter__(self):
        try:
            self.fd = os.open(self.root.resolve(strict=True), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except (OSError, AttributeError, ValueError, RuntimeError):
            raise ExtensionError('Cannot open the selected authoring root on this platform.', 'unavailable') from None
        return self

    def __exit__(self, *_error):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read(self, path, limit):
        if self.fd is None:
            raise ExtensionError('Selected authoring root is not open.', 'unavailable')
        parts = relative_path(path).split('/')
        descriptors = []
        directory = self.fd
        try:
            for part in parts[:-1]:
                directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                descriptors.append(directory)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            descriptors.append(fd)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ExtensionError('Authoring references must be regular files.', 'unavailable')
            if before.st_size > limit:
                raise ReadLimitError('Authoring file exceeds the selected byte limit.', 'unavailable')
            chunks, remaining = [], limit + 1
            while remaining:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            after = os.fstat(fd)
            content = b''.join(chunks)
            if len(content) > limit:
                raise ReadLimitError('Authoring file exceeds the selected byte limit.', 'unavailable')
            if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(content) != after.st_size):
                raise ExtensionError('Authoring file changed during validation.', 'unavailable')
            return content
        finally:
            for fd in reversed(descriptors):
                os.close(fd)


def verify_schema_copies():
    """Included authoring copies may never become independent validation authority."""
    directory = Path(__file__).with_name('contracts')
    try:
        canonical = schemas()
        for name, content in canonical.items():
            if (directory / (name + '-v1.json')).read_bytes() != content:
                raise ExtensionError('Authoring schemas differ from the canonical contract.')
    except OSError:
        raise ExtensionError('Canonical or included authoring schemas are unavailable.', 'unavailable') from None
    return {name:digest(content) for name, content in canonical.items()}


def validate(root, manifest_path='extension.json'):
    """Inspect one package. Dependencies outside that package remain unavailable."""
    verify_schema_copies()
    relative_path(manifest_path)
    try:
        with RootReader(root) as reader:
            try:
                content = reader.read(manifest_path, MANIFEST_LIMIT)
            except ReadLimitError:
                raise ExtensionError('Selected manifest exceeds the canonical 64 KiB bound.') from None
            references = [{'id':'selected', 'label':'Selected authoring manifest',
                           'path':manifest_path, 'sha256':digest(content)}]
            return catalog(references, reader.read)
    except OSError:
        raise ExtensionError('Authoring manifest is missing or cannot be safely read.', 'unavailable') from None
