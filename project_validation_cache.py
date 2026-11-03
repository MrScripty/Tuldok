"""Remember complete domain validation of exact project checkpoints.

A project checkpoint digest covers its manifest, which names every canonical
record revision by length and SHA256. Records are verified against those
digests before use, so (project ID, checkpoint) identifies the exact record set.
Complete cross-domain validation of that set is a pure function of those
records and the validating source code, so an earlier success can be reused
when both are identical.

Markers live only in the private local workspace control directory; a portable
project folder never carries validation authority. The validator fingerprint
covers every Tuldok Python module and extension schema plus the optional
validator package versions, so any code or dependency change revalidates.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import threading
import uuid

FORMAT = 'project_validation_marker_v1'
_HEX32 = re.compile(r'^[a-f0-9]{32}$')
_HEX64 = re.compile(r'^[a-f0-9]{64}$')
_SOURCE = Path(__file__).resolve().parent
_fingerprint = None
_fingerprint_lock = threading.Lock()


def _package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def validator_fingerprint():
    """SHA256 over validating source bytes, schemas and optional validators."""
    global _fingerprint
    with _fingerprint_lock:
        if _fingerprint is None:
            digest = hashlib.sha256(b'tuldok-validator-fingerprint-v1\0')
            paths = sorted(path for path in _SOURCE.glob('*.py'))
            schemas = _SOURCE / 'extension_schemas'
            if schemas.is_dir():
                paths += sorted(path for path in schemas.rglob('*') if path.is_file())
            for path in paths:
                digest.update(str(path.relative_to(_SOURCE)).encode('utf-8') + b'\0')
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            environment = dict(python=sys.version, jsonschema=_package_version('jsonschema'),
                               referencing=_package_version('referencing'))
            digest.update(json.dumps(environment, sort_keys=True).encode('utf-8'))
            _fingerprint = digest.hexdigest()
        return _fingerprint


class ProjectValidationCache:
    """Private per-workspace markers of fully validated project checkpoints."""
    def __init__(self, control_path, *, fingerprint=None):
        self.path = Path(control_path) / '.project-validation'
        self.fingerprint = fingerprint or validator_fingerprint()

    def _marker(self, project_id, checkpoint):
        if (type(project_id) is not str or not _HEX32.fullmatch(project_id)
                or type(checkpoint) is not str or not _HEX64.fullmatch(checkpoint)):
            raise ValueError('Invalid project validation identity.')
        name = hashlib.sha256(f'{project_id}:{checkpoint}:{self.fingerprint}'.encode()).hexdigest()
        return self.path / f'{name}.json', dict(format=FORMAT, project_id=project_id,
                                                  checkpoint=checkpoint, fingerprint=self.fingerprint)

    def known(self, project_id, checkpoint):
        path, expected = self._marker(project_id, checkpoint)
        try:
            with open(path, 'rb') as stream:
                return json.loads(stream.read(4096)) == expected
        except (OSError, ValueError):
            return False

    def remember(self, project_id, checkpoint):
        """Best effort: a missing marker only means the next Open revalidates."""
        path, marker = self._marker(project_id, checkpoint)
        try:
            self.path.mkdir(mode=0o700, exist_ok=True)
            temporary = self.path / f'.{uuid.uuid4().hex}.tmp'
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.write(descriptor, json.dumps(marker, sort_keys=True).encode('utf-8'))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, path)
        except OSError:
            pass


class CanonicalDigestCache:
    """Private set of record digests whose bytes were proven canonical JSON.

    Canonicality is a property of the bytes alone, and record files are named
    by their SHA256, so a proof for one digest holds for every project that
    contains those exact bytes. The set is versioned by the canonical codec's
    own source, so any change to the encoding rules starts a fresh set.
    """
    def __init__(self, control_path):
        import inspect
        import project_store
        codec = ''.join(inspect.getsource(function) for function in (
            project_store._json_value, project_store._encode, project_store._pairs, project_store._decode))
        version = hashlib.sha256((codec + json.__version__).encode('utf-8')).hexdigest()[:32]
        self.path = Path(control_path) / '.canonical-digests' / f'{version}.bin'
        self._known = None
        self._lock = threading.Lock()

    def _load(self):
        if self._known is None:
            known = set()
            try:
                with open(self.path, 'rb') as stream:
                    raw = stream.read()
                if len(raw) % 32 == 0:
                    known = {raw[index:index + 32] for index in range(0, len(raw), 32)}
            except OSError:
                pass
            self._known = known
        return self._known

    def __contains__(self, digest):
        with self._lock:
            return bytes.fromhex(digest) in self._load()

    def add_many(self, digests):
        """Best effort: a lost update only means those records are re-proven."""
        with self._lock:
            known = self._load()
            fresh = {bytes.fromhex(digest) for digest in digests} - known
            if not fresh:
                return
            known |= fresh
            try:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                temporary = self.path.parent / f'.{uuid.uuid4().hex}.tmp'
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                try:
                    remaining = memoryview(b''.join(sorted(known)))
                    while remaining:
                        remaining = remaining[os.write(descriptor, remaining):]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(temporary, self.path)
            except OSError:
                pass
