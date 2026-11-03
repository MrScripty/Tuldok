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
# A retained scientific runtime can declare tens of thousands of small files.
# Their index is bounded separately from the actual record/payload byte budgets.
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
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
    'measurement_source': 'project_measurement_source_v1',
    'runtime_material': 'retained_runtime_material_v1',
    'study_history': 'project_study_history_v1',
    'trial_history': 'project_trial_history_v1',
    'run_history': 'project_run_history_v1',
    'run_observation': 'project_run_observation_v1',
    'native_execution_history': 'native_execution_history_v1',
    'candidate_history': 'project_candidate_history_v1',
    'project_artifact': 'project_artifact_v1',
    'project_operation': 'project_operation_v1',
    'project_fork': 'project_fork_v1',
    'project_composition': 'project_composition_v1',
    'project_file': 'project_file_v1',
    'project_extraction': 'project_extraction_v1',
    'generation_history': 'project_generation_history_v1',
    'grounded_history': 'project_grounded_history_v1',
    'caption_proposal_history': 'project_caption_proposal_history_v1',
    'text_proposal_history': 'project_text_proposal_history_v1',
    # Store-only: one shared retained runtime closure for compact Runs
    # (project_record_dedupe); never visible to domain owners.
    'run_runtime_closure': 'project_run_runtime_closure_v1',
}
MAX_RECORDS = 100_000
# Scientific history can retain original runtime/file observations in hundreds
# of Runs. Bound the whole local checkpoint separately from each document.
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
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
        if not value.isascii():
            try:
                value.encode('utf-8')
            except UnicodeEncodeError:
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


def copy_validated_json(value):
    """Own another tree of already validated JSON without Python graph copying.

    Canonical Store/Session values contain only JSON scalars, lists and string
    keyed dictionaries. This is a copy operation inside that proof boundary,
    never an input decoder or a substitute for freshness/codec validation.
    """
    return json.loads(json.dumps(value, ensure_ascii=True, allow_nan=False,
                                separators=(',', ':')))


def _manifest_raw(manifest):
    raw = _encode(manifest)
    if len(raw) > MAX_MANIFEST_BYTES:
        _fail('Project checkpoint exceeds its byte limit.')
    return raw


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
    if value != SUPPORTED_FORMATS[family] and not (
            family == 'project_operation' and value == 'project_operation_v2'
            or family == 'project_file' and value == 'project_file_v2'
            or family == 'run_history' and value == 'project_run_history_v2'):
        _fail('Unsupported domain document format.', 'unsupported', 422)


def _compact(value):
    # CPython's C encoder is used only without indent; it distinguishes 1, 1.0,
    # True and 0.0/-0.0, which Python == equality does not.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':'))


def _same_json(candidate, verified):
    """Exact JSON value equality: same types, float bits and key sets."""
    if candidate is verified:
        return True
    if candidate != verified:
        return False
    try:
        return _compact(candidate) == _compact(verified)
    except (TypeError, ValueError, RecursionError):
        return False


def _prepared_records(records, unchanged=None):
    """Validate and canonically encode a complete candidate record set.

    unchanged maps (family, id) -> (verified current document, inventory entry).
    A candidate document equal to its verified current revision reuses that
    revision's known canonical byte count and digest instead of re-encoding it;
    its raw slot is None and the caller must not rewrite it.
    """
    if type(records) is not list or len(records) > MAX_RECORDS:
        _fail('Project records must be a bounded list.')
    unchanged = unchanged or {}
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
        current = unchanged.get((family, identity))
        if current is not None and _same_json(document, current[0]) \
                and current[1]['format'] == document['format']:
            # Exactly equal JSON values have identical canonical bytes; share the
            # already verified current document (never handed out by alias).
            total += current[1]['bytes']
            if total > MAX_TOTAL_BYTES:
                _fail('Project records exceed the synchronous byte limit.')
            result.append((family, identity, current[0], None, current[1]))
            continue
        document = copy.deepcopy(document)
        raw = _encode(document)
        total += len(raw)
        if len(raw) > MAX_RECORD_BYTES or total > MAX_TOTAL_BYTES:
            _fail('Project records exceed the synchronous byte limit.')
        result.append((family, identity, document, raw, None))
    return sorted(result, key=lambda item: (item[0], item[1]))


_NESTED_DOCUMENT = b'\n' + b' ' * 4


class _RecordsDigest:
    """Incremental SHA256 of _encode([dict(family, id, document), ...]).

    add() takes each record's own canonical _encode(document) bytes, in record
    order. Canonical JSON never contains a literal newline inside a string, so
    a document nested two levels deep differs from its standalone encoding only
    by four extra spaces after each newline. The result is byte-identical to
    hashing the complete re-encoded list, without re-encoding any document.
    """
    def __init__(self):
        self._digest = hashlib.sha256()
        self._first = True

    def add(self, family, identity, raw):
        if not raw.endswith(b'\n'):
            _fail('Canonical record bytes must end with LF.')
        self._digest.update(b'[\n  {\n    "document": ' if self._first else b',\n  {\n    "document": ')
        self._first = False
        self._digest.update(raw[:-1].replace(b'\n', _NESTED_DOCUMENT))
        self._digest.update(b',\n    "family": ')
        self._digest.update(json.dumps(family, ensure_ascii=False).encode('utf-8'))
        self._digest.update(b',\n    "id": ')
        self._digest.update(json.dumps(identity, ensure_ascii=False).encode('utf-8'))
        self._digest.update(b'\n  }')

    def hexdigest(self):
        final = self._digest.copy()
        final.update(b'[]\n' if self._first else b'\n]\n')
        return final.hexdigest()


def envelope_digest(family, identity, raw):
    """SHA256 of _encode(dict(family, id, document)) from the document's canonical bytes.

    Canonical JSON has no literal newline inside strings, so the document nested
    one level deep differs from its standalone encoding only by two spaces after
    each newline.
    """
    if not raw.endswith(b'\n'):
        _fail('Canonical record bytes must end with LF.')
    digest = hashlib.sha256(b'{\n  "document": ')
    digest.update(raw[:-1].replace(b'\n', b'\n  '))
    digest.update(b',\n  "family": ' + json.dumps(family, ensure_ascii=False).encode('utf-8'))
    digest.update(b',\n  "id": ' + json.dumps(identity, ensure_ascii=False).encode('utf-8') + b'\n}\n')
    return digest.hexdigest()


def _records_digest(rows):
    """Digest of (family, id, canonical raw) rows; see _RecordsDigest."""
    digest = _RecordsDigest()
    for family, identity, raw in rows:
        digest.add(family, identity, raw)
    return digest.hexdigest()


def _records(records):
    """Complete canonical encoding as (family, id, document, raw) tuples."""
    return [(family, identity, document, raw)
            for family, identity, document, raw, _entry in _prepared_records(records)]


def _physical_candidates(records, logical, physical):
    """Physical envelopes for a logical candidate record set.

    A candidate equal to its current logical document reuses the current
    physical document (so its verified revision is kept). Changed Runs are
    compacted to a shared runtime closure when exactly reversible; every
    referenced closure is included once. Returns (physical candidates, logical
    result in record order) or (records, None) for malformed input, which
    _prepared_records then rejects with its usual errors.
    """
    from project_record_dedupe import CLOSURE_FAMILY, RUN_FAMILY, compact, is_compact
    if type(records) is not list or any(type(item) is not dict or set(item) != {'family', 'id', 'document'}
                                        or type(item['family']) is not str or type(item['id']) is not str
                                        for item in records):
        return records, None
    if any(item['family'] == CLOSURE_FAMILY for item in records):
        _fail('Runtime closures are store-owned records.', 'unsupported', 422)
    current_logical = {(item['family'], item['id']): item['document'] for item in logical}
    current_physical = {(item['family'], item['id']): item['document'] for item in physical}
    closures = {item['id']: item['document'] for item in physical if item['family'] == CLOSURE_FAMILY}
    candidates, logical_out, referenced = [], [], set()
    for item in records:
        key = (item['family'], item['id'])
        document = item['document']
        if key in current_logical and _same_json(document, current_logical[key]):
            stored = current_physical[key]
            candidates.append(dict(family=key[0], id=key[1], document=stored))
            logical_out.append(dict(family=key[0], id=key[1], document=current_logical[key]))
            if is_compact(key[0], stored):
                referenced.add(stored['runtime_closure']['id'])
            continue
        owned = copy.deepcopy(document)
        logical_out.append(dict(family=key[0], id=key[1], document=owned))
        compacted = compact(owned) if key[0] == RUN_FAMILY else None
        if compacted is not None:
            reduced, closure = compacted
            identity = reduced['runtime_closure']['id']
            closures.setdefault(identity, closure)
            referenced.add(identity)
            candidates.append(dict(family=key[0], id=key[1], document=reduced))
        else:
            candidates.append(dict(family=key[0], id=key[1], document=owned))
    candidates.extend(dict(family=CLOSURE_FAMILY, id=identity, document=closures[identity]) for identity in sorted(referenced))
    logical_out.sort(key=lambda item: (item['family'], item['id']))
    return candidates, logical_out


def _request(key, digest):
    if type(key) is not str or not REQUEST_KEY.fullmatch(key):
        _fail('Request key must contain 1–128 supported characters.')
    _digest(digest, 'Request body digest')


def checked_manifest(raw):
    """Decode and check a project checkpoint without reading any record file.

    Verifies format, identity, the checkpoint digest, every inventory entry's
    shape, ordering, rooted path and byte bounds, membership roots and receipt
    structure. Record bytes and the latest receipt's records digest are checked
    by whoever reads the records.
    """
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
    roots, total, previous = [], 0, None
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
    return manifest


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


def _directory_inside(candidate_fd, ancestor_fd):
    """Compare physical directory ancestry without following path aliases."""
    current = os.dup(candidate_fd)
    try:
        ancestor = _physical(ancestor_fd)
        while True:
            if _physical(current) == ancestor:
                return True
            parent = os.open('..', DIR_FLAGS, dir_fd=current)
            if _physical(parent) == _physical(current):
                os.close(parent)
                return False
            os.close(current)
            current = parent
    finally:
        os.close(current)


def assert_separate_project_control(trusted_root_fd, relative, *, root_path, control_path):
    """Reject portable project/control overlap before creating any destination.

    The caller retains its configured root handle. Existing targets must be
    physically disjoint from control in both directions; for an absent leaf,
    its existing anchored parent must be outside control. A broad root may
    still contain disjoint project and control siblings.
    """
    parts = _relative_parts(relative)
    control_fd = target_fd = None
    try:
        _, control_fd = _open_directory_path(control_path)
        with anchored_directory(trusted_root_fd, '/'.join(parts[:-1]), root_path=root_path) as parent_fd:
            try:
                target_fd = _directory(parent_fd, parts[-1])
            except FileNotFoundError:
                overlap = _directory_inside(parent_fd, control_fd)
            else:
                overlap = (_directory_inside(target_fd, control_fd) or
                           _directory_inside(control_fd, target_fd))
            if overlap:
                _fail('Keep the private workspace control directory separate from portable project directories.', 'conflict', 409)
            if target_fd is not None:
                current = _directory(parent_fd, parts[-1])
                try:
                    if _physical(current) != _physical(target_fd):
                        _fail('Project directory changed during control separation check.', 'stale', 409)
                finally:
                    os.close(current)
            _verify_origin(control_fd, control_path)
    except OSError as error:
        _io_error(error, 'verify project/control separation')
    finally:
        if target_fd is not None:
            os.close(target_fd)
        if control_fd is not None:
            os.close(control_fd)


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
    def __init__(self, path, root_fd, origin_fd, relative_parts, origin_path, canonical_digests=None):
        self.path = Path(path)
        # Optional private set of digests already proven canonical; see _load.
        self._canonical_digests = canonical_digests
        self._root_fd = root_fd
        self._origin_fd = origin_fd
        self._relative_parts = relative_parts
        self._origin_path = Path(origin_path)
        self._meta_fd = None
        self._manifest = None
        self._read_cache = None
        self._mutex = threading.RLock()
        self._unknown = False
        self._folder_mode = False
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
    def open(cls, path, *, canonical_digests=None):
        raw = _path_string(path)
        if type(raw) is not str or '\x00' in raw or '..' in raw.split('/'):
            _fail('Unsafe project root path.')
        absolute = os.path.abspath(raw)
        parent, leaf = os.path.split(absolute)
        _, parent_fd = _open_directory_path(parent)
        try:
            return cls.open_at(parent_fd, leaf, root_path=parent, canonical_digests=canonical_digests)
        finally:
            os.close(parent_fd)

    @classmethod
    def open_at(cls, trusted_root_fd, relative, *, root_path, canonical_digests=None):
        """Open a descendant without following any configured-root or child alias."""
        parts = _relative_parts(relative)
        absolute = _verify_origin(trusted_root_fd, root_path)
        origin_fd = os.dup(trusted_root_fd)
        store = None
        try:
            fd = _walk(origin_fd, parts)
            owned_origin, origin_fd = origin_fd, None
            store = cls(Path(absolute).joinpath(*parts), fd, owned_origin, parts, absolute,
                        canonical_digests=canonical_digests)
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

    # ---- Folder mode: the external project as an import source/export target.
    # A folder-mode Store holds the writer lock and root binding but never
    # loads the record set; the database working copy owns current records.

    @classmethod
    def open_folder_at(cls, trusted_root_fd, relative, *, root_path):
        """Bind an existing external project folder without reading its records."""
        parts = _relative_parts(relative)
        absolute = _verify_origin(trusted_root_fd, root_path)
        origin_fd = os.dup(trusted_root_fd)
        store = None
        try:
            fd = _walk(origin_fd, parts)
            owned_origin, origin_fd = origin_fd, None
            store = cls(Path(absolute).joinpath(*parts), fd, owned_origin, parts, absolute)
            store._meta_fd = _directory(fd, '.tuldok')
            store._folder_mode = True
            return store
        except OSError as exc:
            if store is not None:
                store.close()
            _io_error(exc, 'open project folder')
        except BaseException:
            if store is not None:
                store.close()
            raise
        finally:
            if origin_fd is not None:
                os.close(origin_fd)

    def folder_checkpoint(self):
        """(raw bytes, checked manifest) of the folder's current project.json."""
        with self._mutex:
            self._binding()
            try:
                raw = _read(self._meta_fd, 'project.json', MAX_MANIFEST_BYTES)
            except OSError as exc:
                _io_error(exc, 'read project checkpoint')
            return raw, checked_manifest(raw)

    def folder_record(self, entry):
        """One inventory entry's exact bytes after length/SHA256 verification."""
        with self._mutex:
            try:
                raw = self._record_file(entry['family'], entry['id'], entry['sha256'])
            except OSError as exc:
                _io_error(exc, 'read project record')
            if len(raw) != entry['bytes'] or _sha(raw) != entry['sha256']:
                _fail('Canonical record bytes changed or are corrupt.')
            return raw

    def folder_has_record(self, entry):
        """Whether the content-addressed revision file exists with its byte length."""
        with self._mutex:
            fds = []
            try:
                parent = self._meta_fd
                for part in ('records', entry['family'], entry['id']):
                    parent = _directory(parent, part)
                    fds.append(parent)
                info = os.stat(entry['sha256'] + '.json', dir_fd=parent, follow_symlinks=False)
                return stat.S_ISREG(info.st_mode) and info.st_size == entry['bytes']
            except FileNotFoundError:
                return False
            except OSError as exc:
                _io_error(exc, 'inspect project record')
            finally:
                for fd in reversed(fds):
                    os.close(fd)

    def folder_write_record(self, family, record_id, digest, raw):
        """Durably publish one immutable revision; existing bytes must be identical."""
        with self._mutex:
            try:
                written = self._record_file(family, record_id, digest, raw)
            except OSError as exc:
                _io_error(exc, 'write project record')
            if written != raw:
                _fail('Immutable project revision already has different bytes.')

    def folder_publish(self, raw, expected_raw):
        """Atomically replace project.json only if it still has expected_raw.

        expected_raw None means the folder has no checkpoint yet. Refuses to
        overwrite a checkpoint someone else published since import/export.
        """
        if len(raw) > MAX_MANIFEST_BYTES:
            _fail('Project checkpoint exceeds its byte limit.')
        with self._mutex:
            temporary = '.checkpoint-' + uuid.uuid4().hex + '.tmp'
            replaced = False
            try:
                _write_file(self._meta_fd, temporary, raw)
                self._binding()
                try:
                    current = _read(self._meta_fd, 'project.json', MAX_MANIFEST_BYTES)
                except FileNotFoundError:
                    current = None
                if current != expected_raw:
                    os.unlink(temporary, dir_fd=self._meta_fd)
                    _fail('The external project changed since Tuldok last imported or saved it.', 'conflict', 409)
                os.replace(temporary, 'project.json', src_dir_fd=self._meta_fd, dst_dir_fd=self._meta_fd)
                replaced = True
                os.fsync(self._meta_fd)
                os.fsync(self._root_fd)
            except OSError as exc:
                self._unknown = replaced
                _io_error(exc, 'publish checkpoint', unknown=replaced)

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
    def root_directory(self, *, verify_after=False):
        """Borrow this project's physical root while its writer binding is pinned."""
        if type(verify_after) is not bool:
            _fail('Root read verification must be an explicit boolean.')
        with self._mutex:
            before = self._current()[0]['checkpoint']
            descriptor = os.dup(self._root_fd)
            try:
                yield descriptor
                self._binding()
                if verify_after and self._current()[0]['checkpoint'] != before:
                    _fail('Project checkpoint changed during the bounded root read.', 'stale', 409)
            finally:
                os.close(descriptor)

    def _load(self):
        self._binding()
        raw = _read(self._meta_fd, 'project.json', MAX_MANIFEST_BYTES)
        cached = self._read_cache
        if cached is not None and raw == cached[0]:
            # Record files are content-addressed by their inventory digest and
            # are never rewritten, and every one was length/SHA256 verified when
            # this Store decoded it. Byte-identical checkpoint bytes therefore
            # name the same verified record set; re-hashing every record on each
            # freshness check is redundant. On-disk corruption after that point
            # is still refused by Save (verify_records) and by every reopen.
            self._binding()
            return cached[1], cached[2]
        manifest = checked_manifest(raw)
        loaded = []
        records_digest = _RecordsDigest()
        known = self._canonical_digests
        proven = []
        for entry in manifest['inventory']:
            family, record_id, digest = entry['family'], entry['id'], entry['sha256']
            record_raw = self._verified_record_bytes(entry)
            if known is not None and digest in known:
                # These exact bytes (named by their verified SHA256) were already
                # proven to be their value's canonical encoding, which excludes
                # duplicate keys and non-finite numbers; a plain parse is exact.
                document = json.loads(record_raw)
            else:
                document = _decode(record_raw)
                proven.append(digest)
            if type(document) is not dict or document.get('format') != entry['format']:
                _fail('Domain document format disagrees with its inventory.')
            records_digest.add(family, record_id, record_raw)
            loaded.append(dict(family=family, id=record_id, document=document))
        # _decode proved each raw revision is its document's canonical encoding.
        if manifest['receipts'][-1]['records_sha256'] != records_digest.hexdigest():
            _fail('Latest operation receipt disagrees with the current record set.')
        # A second pointer read detects checkout/replacement during closure validation.
        if _read(self._meta_fd, 'project.json', MAX_MANIFEST_BYTES) != raw:
            _fail('Project checkpoint changed while reading.', 'stale', 409)
        self._binding()
        if known is not None and proven:
            known.add_many(proven)
        # Domain owners see logical records: shared runtime closures hidden and
        # compact Runs expanded to their exact original documents.
        from project_record_dedupe import logical_records
        logical = logical_records(loaded)
        self._read_cache = (raw, manifest, logical, loaded)
        return manifest, logical

    def _verified_record_bytes(self, entry):
        raw = self._record_file(entry['family'], entry['id'], entry['sha256'])
        if len(raw) != entry['bytes'] or _sha(raw) != entry['sha256']:
            _fail('Canonical record bytes changed or are corrupt.',
                  'stale' if self._manifest else 'invalid', 409 if self._manifest else 400)
        return raw

    def _record_file(self, family, record_id, digest, raw=None, sync=False):
        fds = []
        try:
            parent = self._meta_fd
            for part in ('records', family, record_id):
                parent = _directory(parent, part, create=raw is not None)
                fds.append(parent)
            name = digest + '.json'
            if raw is not None:
                try:
                    existing = _read(parent, name, MAX_RECORD_BYTES)
                except FileNotFoundError:
                    temporary = '.record-' + uuid.uuid4().hex + '.tmp'
                    _write_file(parent, temporary, raw)
                    try:
                        _rename_noreplace(parent, temporary, name)
                    except FileExistsError:
                        if _read(parent, name, MAX_RECORD_BYTES) != raw:
                            _fail('Immutable project revision already has different bytes.')
                        os.unlink(temporary, dir_fd=parent)
                else:
                    if existing != raw:
                        _fail('Immutable project revision already has different bytes.')
                # Existing revisions can come from a copied project or an
                # interrupted earlier commit. Retain all ordinary sync checks;
                # only the disposable write/rename/unlink cycle is avoided.
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
        raw = _manifest_raw(manifest)
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
        return raw
        # Temporary/orphan files remain inert after failures and process interruption.

    def _snapshot(self, manifest, records):
        return dict(project_id=manifest['project_id'], name=manifest['name'],
                    checkpoint=manifest['checkpoint'], records=copy_validated_json(records))

    def _current(self):
        try:
            manifest, records = self._load()
            if manifest != self._manifest:
                _fail('Project checkpoint changed; close and reopen.', 'stale', 409)
            return manifest, records
        except OSError as exc:
            _io_error(exc, 'read project snapshot')

    def verify_records(self):
        """Re-read and SHA256-check every referenced canonical revision on disk.

        Ordinary freshness checks compare checkpoint bytes only; this explicit
        pass detects later same-length corruption of already-decoded revisions.
        """
        with self._mutex:
            manifest, _records = self._current()
            try:
                for entry in manifest['inventory']:
                    self._verified_record_bytes(entry)
            except OSError as exc:
                _io_error(exc, 'verify project records')
            if self._current()[0] != manifest:
                _fail('Project checkpoint changed during verification.', 'stale', 409)

    def summary(self):
        """Return scalar metadata after the checkpoint freshness check."""
        with self._mutex:
            manifest, _records = self._current()
            return {key: manifest[key] for key in ('project_id', 'name', 'checkpoint')}

    def snapshot(self):
        with self._mutex:
            manifest, records = self._current()
            return self._snapshot(manifest, records)

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
        with self._mutex:
            try:
                current, loaded = self._load()
                if current != self._manifest:
                    _fail('Project checkpoint changed; close and reopen.', 'stale', 409)
                physical = self._read_cache[3]
                # Unchanged records keep their verified canonical revision: no
                # re-encoding, rewrite or read-back of identical immutable bytes.
                entries = {(entry['family'], entry['id']): entry for entry in current['inventory']}
                unchanged = {(item['family'], item['id']): (item['document'], entries[(item['family'], item['id'])])
                             for item in physical}
                candidates, logical_out = _physical_candidates(records, loaded, physical)
                prepared = _prepared_records(candidates, unchanged)
                if logical_out is None:
                    logical_out = [dict(family=f, id=i, document=d) for f, i, d, _, _ in prepared]
                digest_rows = _RecordsDigest()
                for family, identity, _document, raw, entry in prepared:
                    if raw is None:
                        raw = self._verified_record_bytes(entry)
                    digest_rows.add(family, identity, raw)
                records_digest = digest_rows.hexdigest()
                for receipt in current['receipts']:
                    if receipt['request_key'] == request_key:
                        if receipt['request_sha256'] != request_sha256 or receipt['records_sha256'] != records_digest:
                            _fail('Request key was already used with different input.', 'conflict', 409)
                        return self._snapshot(current, loaded)
                if expected_checkpoint != current['checkpoint']:
                    _fail('Expected project checkpoint is stale.', 'stale', 409)
                manifest = copy.deepcopy(current)
                inventory = []
                for family, identity, document, raw, entry in prepared:
                    if raw is None:
                        inventory.append(copy.deepcopy(entry))
                        continue
                    digest = _sha(raw)
                    inventory.append(dict(family=family, id=identity, format=document['format'],
                        namespace=current['project_id'], path=f'records/{family}/{identity}/{digest}.json',
                        bytes=len(raw), sha256=digest))
                manifest['inventory'] = inventory
                manifest['roots'] = [dict(family=f, id=i) for f, i, _, _, _ in prepared]
                manifest['receipts'].append(dict(request_key=request_key,
                    request_sha256=request_sha256, records_sha256=records_digest))
                del manifest['checkpoint']
                manifest['checkpoint'] = _sha(_encode(manifest))
                # Refuse before record staging. The final publication also
                # rechecks this bound after the immutable files are durable.
                _manifest_raw(manifest)
                for family, identity, document, raw, _entry in prepared:
                    if raw is not None:
                        self._record_file(family, identity, _sha(raw), raw)
                published = self._publish(manifest)
                self._manifest = manifest
                if self._canonical_digests is not None:
                    # Freshly written revisions are canonical by construction.
                    self._canonical_digests.add_many(
                        [_sha(raw) for _f, _i, _d, raw, _e in prepared if raw is not None])
                # Every committed revision is either freshly written and read
                # back byte-for-byte or an unchanged verified revision.
                self._read_cache = (published, manifest, logical_out,
                                    [dict(family=f, id=i, document=d) for f, i, d, _, _ in prepared])
                return self._snapshot(manifest, logical_out)
            except OSError as exc:
                _io_error(exc, 'commit project records')

    def save(self, expected_checkpoint):
        _digest(expected_checkpoint, 'Expected checkpoint')
        with self._mutex:
            snapshot = self.snapshot()
            if expected_checkpoint != snapshot['checkpoint']:
                _fail('Expected project checkpoint is stale.', 'stale', 409)
            try:
                # Save is the explicit durability and integrity boundary: sync and
                # re-verify every referenced canonical revision's actual bytes.
                for entry in self._manifest['inventory']:
                    raw = self._record_file(entry['family'], entry['id'], entry['sha256'], sync=True)
                    if len(raw) != entry['bytes'] or _sha(raw) != entry['sha256']:
                        _fail('Canonical record bytes changed or are corrupt.', 'stale', 409)
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
            self._read_cache = None
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
