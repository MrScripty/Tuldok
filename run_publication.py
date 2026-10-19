"""Runs-owned explicit publication continuation; never dispatch or change compute outcome."""
import copy
import base64
from functools import wraps
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import time
import phase_timings
import uuid

from metadata import CommitOutcomeUnknown
from pipeline import closed, digest, identifier
from workbench import WorkbenchError, encode, timestamp

WALL_SECONDS = 60
MAX_ATTEMPTS = 20
MAX_DOCUMENT_BYTES = 48 * 1024
_HASH = re.compile(r'^[a-f0-9]{64}$')


def _require(value, message, code='unavailable'):
    if not value:
        raise WorkbenchError(message, code, 409)


def _check(runs, deadline):
    _require(not runs._closed and not runs._stop.is_set() and not runs._publication_cancel.is_set(),
             'Publication continuation is paused.', 'cancelled')
    _require(time.monotonic() < deadline, 'Publication continuation reached its wall budget.')


def _read_check(runs, deadline):
    _require(not runs._closed and not runs._stop.is_set(), 'Recovered result reader is stopping.', 'cancelled')
    _require(time.monotonic() < deadline, 'Recovered result reader reached its wall budget.')


def _current_read(runs, run_id):
    runs.access.require('inspect', 'runs.publication_result', run_id)
    with runs.lock: run = runs._load(run_id)
    from candidate_packages import authorize_transitive_inputs
    authorize_transitive_inputs(runs, run)


def _reader_boundary(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except WorkbenchError:
            raise
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            raise WorkbenchError('Recovered publication bytes are unavailable or changed.', 'unavailable', 409) from error
    return checked


def _hash(value):
    return type(value) is str and _HASH.fullmatch(value) is not None


def validate_continuation(run):
    """Cold structural validation only; retained documents convey no new authority."""
    fault = run.get('publication_fault')
    if fault is not None:
        closed(fault, ('format', 'source_sha256', 'code', 'message', 'recorded_at'))
        _require(fault['format'] == 'external_publication_fault_v1'
                 and fault['source_sha256'] == run.get('publication_source', {}).get('sha256')
                 and type(fault['code']) is str and re.fullmatch('[a-z][a-z0-9_]{0,79}', fault['code'])
                 and type(fault['message']) is str and len(fault['message']) <= 240
                 and type(fault['recorded_at']) is str and len(fault['recorded_at']) <= 64,
                 'Retained publication fault differs.')
    value = run.get('publication_continuation')
    if value is None:
        return
    closed(value, ('format', 'schema_version', 'source_ref', 'actor_id', 'request_key', 'request_sha256',
                   'original_state', 'state', 'attempts', 'result_ref', 'cancel_requested', 'cancel_revision'))
    _require(len(encode(value).encode()) <= 16 * 1024 and value['format'] == 'same_run_publication_continuation_v1'
             and type(value['schema_version']) is int and value['schema_version'] == 1
             and value['source_ref'] == run.get('publication_source')
             and value['original_state'] == run['state'] and run['state'] in ('failed', 'interrupted')
             and type(value['actor_id']) is str and re.fullmatch('[a-f0-9]{32}', value['actor_id'])
             and type(value['request_key']) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}', value['request_key'])
             and type(value['cancel_requested']) is bool
             and type(value['cancel_revision']) is int and 0 <= value['cancel_revision'] <= 2**53 - 1
             and value['state'] in ('recovering', 'paused', 'blocked', 'published'),
             'Retained publication continuation differs.')
    body = {'run_id': run['id'], 'source_ref': value['source_ref'], 'request_key': value['request_key']}
    _require(value['request_sha256'] == digest({'actor_id': value['actor_id'],
        'operation': 'runs.recover_publication', 'body': body}), 'Retained publication request identity differs.')
    attempts = value['attempts']
    _require(type(attempts) is list and 1 <= len(attempts) <= MAX_ATTEMPTS, 'Publication attempt history exceeds its bound.')
    for number, attempt in enumerate(attempts, 1):
        closed(attempt, ('number', 'started_at', 'finished_at', 'state', 'error'))
        _require(type(attempt['number']) is int and attempt['number'] == number
                 and type(attempt['started_at']) is str and len(attempt['started_at']) <= 64
                 and (attempt['finished_at'] is None or type(attempt['finished_at']) is str and len(attempt['finished_at']) <= 64)
                 and attempt['state'] in ('recovering', 'paused', 'blocked', 'published'), 'Publication attempt differs.')
        if attempt['error'] is not None:
            closed(attempt['error'], ('code', 'message'))
            _require(type(attempt['error']['code']) is str and len(attempt['error']['code']) <= 80
                     and type(attempt['error']['message']) is str and len(attempt['error']['message']) <= 240,
                     'Publication attempt error exceeds its bound.')
    _require(attempts[-1]['state'] == value['state'], 'Publication attempt state differs.')
    if value['state'] == 'published':
        _result_ref(value['result_ref'], run)
    else:
        _require(value['result_ref'] is None, 'Unpublished continuation cannot expose a result.')


def _result_ref(ref, run):
    closed(ref, ('kind', 'schema_version', 'catalog_id', 'run_id', 'material_sha256',
                 'inventory_sha256', 'custody_receipt_sha256', 'sha256'))
    _require(ref['kind'] == 'recovered_publication_result' and type(ref['schema_version']) is int
             and ref['schema_version'] == 1 and ref['catalog_id'] == run['dataset_id'] and ref['run_id'] == run['id']
             and ref['material_sha256'] == run['material_sha256']
             and all(_hash(ref[key]) for key in ('material_sha256', 'inventory_sha256', 'custody_receipt_sha256', 'sha256')),
             'Recovered result reference differs.', 'stale')


def _source(runs, run, ref):
    _require(ref == run.get('publication_source'), 'Exact original publication source is required.', 'stale')
    directory = runs._diagnostic_directory(runs._external_directory(run))
    try:
        raw, _, _ = runs._diagnostic_read(directory, 'publication-source-v1.json', MAX_DOCUMENT_BYTES)
    finally:
        os.close(directory)
    _require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Retained publication source changed.')
    proof = runs._progress_json(raw)
    closed(proof, ('format', 'schema_version', 'catalog_id', 'run_id', 'request_sha256', 'material_sha256',
                   'graph_sha256', 'custody_receipt', 'inventory', 'inventory_sha256', 'evidence_semantics'))
    _require(proof['format'] == 'external_publication_source_v1' and type(proof['schema_version']) is int
             and proof['schema_version'] == 1 and proof['evidence_semantics'] == 'not_verified',
             'Unsupported original publication source.')
    _require(all(proof[key] == run[other] for key, other in (
        ('catalog_id', 'dataset_id'), ('run_id', 'id'), ('request_sha256', 'request_sha256'),
        ('material_sha256', 'material_sha256'), ('graph_sha256', 'graph_sha256'))),
        'Original publication identity differs.')
    import recipe_process
    receipt = recipe_process.validate_receipt(recipe_process.encoded(proof['custody_receipt']), run['custody_identity'])
    _require(receipt['drained'] and receipt['outcome'] == 'completed', 'Original compute did not complete and drain.')
    inventory = proof['inventory']; allowed = {item['path']: item for item in run['outputs']}
    _require(type(inventory) is list and len(inventory) <= len(allowed)
             and digest(inventory) == proof['inventory_sha256'], 'Original output inventory differs.')
    seen = set(); total = 0
    for item in inventory:
        closed(item, ('path', 'role', 'bytes', 'sha256'))
        name = item['path']; rule = allowed.get(name)
        _require(rule is not None and name not in seen and item['role'] == rule['role']
                 and type(item['bytes']) is int and 0 <= item['bytes'] <= rule['max_bytes']
                 and _hash(item['sha256']), 'Original output declaration differs.')
        seen.add(name); total += item['bytes']
    _require(total <= run['spec']['max_output_bytes']
             and all(not rule['required'] or name in seen for name, rule in allowed.items()),
             'Original output inventory is incomplete or exceeds its bound.')
    return proof


def _copy(runs, directory, name, item, deadline, output=None):
    _check(runs, deadline)
    runs._copy_verified(directory, name, item, output, deadline=deadline,
        cancelled=lambda: runs._closed or runs._stop.is_set() or runs._publication_cancel.is_set())


def _verify_source(runs, run, proof, deadline):
    stage = runs._external_directory(run)
    for relative, item in run['material']['captures'].items():
        path = Path(relative)
        directory = runs._diagnostic_directory(stage / path.parent)
        try:
            _copy(runs, directory, path.name, item, deadline)
        finally:
            os.close(directory)
    source = stage / 'output'; directory = runs._diagnostic_directory(source)
    try:
        _require(set(os.listdir(directory)) == {item['path'] for item in proof['inventory']},
                 'Original output membership changed.')
        for item in proof['inventory']:
            _copy(runs, directory, item['path'], item, deadline)
    finally:
        os.close(directory)
    artifacts = _artifacts(proof)
    if runs._extension(run):
        runs._verify_extension(source, dict(run, artifacts=artifacts), checkpoint=lambda: _check(runs, deadline))
    _check(runs, deadline)


def _artifacts(proof):
    return [{'name': item['path'], 'role': item['role'], 'bytes': item['bytes'], 'sha256': item['sha256'],
             'media_type': 'application/octet-stream'} for item in proof['inventory']]


def _manifest(run, proof):
    return {'schema_version': 1, 'run_id': run['id'], 'material_sha256': run['material_sha256'],
            'request_sha256': run['request_sha256'],
            'custody_receipt_sha256': hashlib.sha256(encode(proof['custody_receipt']).encode()).hexdigest(),
            'artifacts': _artifacts(proof)}


def _store(runs, run, name, raw):
    _require(len(raw) <= MAX_DOCUMENT_BYTES, 'Publication document exceeds its metadata bound.', 'unsupported')
    directory = runs._diagnostic_directory(runs._external_directory(run))
    temporary = '.publication-result-' + uuid.uuid4().hex
    created = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(descriptor, 'wb') as output:
            output.write(raw); output.flush(); os.fchmod(output.fileno(), 0o400); os.fsync(output.fileno())
        try:
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        except FileExistsError:
            existing, _, _ = runs._diagnostic_read(directory, name, MAX_DOCUMENT_BYTES)
            _require(existing == raw, 'A different immutable publication result already exists.', 'conflict')
        os.unlink(temporary, dir_fd=directory); created = False; os.fsync(directory)
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def _status(run):
    continuation = run['publication_continuation']
    return {'run_id': run['id'], 'state': continuation['state'],
            'original_run_state': continuation['original_state'], 'attempt_count': len(continuation['attempts']),
            'cancel_requested': continuation['cancel_requested'],
            'result_ref': copy.deepcopy(continuation['result_ref'])}


def status(runs, run_id, *, include_request=False):
    """Bounded saved metadata; current byte verification belongs to recovery/read."""
    identifier(run_id, 'Run ID')
    with runs.lock:
        run = runs._load(run_id)
    from candidate_packages import authorize_transitive_inputs
    authorize_transitive_inputs(runs, run)
    fault = run.get('publication_fault')
    eligible = (runs._external(run) and run['state'] in ('failed', 'interrupted') and not run['artifacts']
                and run.get('publication_source') is not None and type(fault) is dict
                and fault['code'] in ('unavailable', 'storage', 'commit_unknown'))
    value = {'run_id': run_id, 'original_run_state': run['state'], 'verification': 'saved_metadata_only',
            'eligibility': 'requires_verification' if eligible else 'unavailable',
            'source_ref': copy.deepcopy(run.get('publication_source')),
            'original_fault': copy.deepcopy(fault),
            'continuation': _status(run) if run.get('publication_continuation') is not None else None,
            'limits': {'wall_seconds': WALL_SECONDS, 'max_attempts': MAX_ATTEMPTS,
                       'copy_bytes': run['spec']['max_output_bytes'] if runs._external(run) else 0}}
    if include_request:
        continuation = run.get('publication_continuation')
        value['continuation_request'] = (None if continuation is None else
            {key: continuation[key] for key in ('actor_id', 'request_key', 'request_sha256')})
    return value


def _publish(runs, run, proof, deadline):
    """Reuse the owned unpublished destination; never create a third output copy."""
    source = destination = None
    destination_path = runs.path / run['id']
    try:
        source = runs._diagnostic_directory(runs._external_directory(run) / 'output')
        try:
            destination_path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        destination = runs._diagnostic_directory(destination_path)
        manifest = _manifest(run, proof)
        documents = {'custody-receipt.json': encode(proof['custody_receipt']).encode(),
                     'artifact-manifest.json': encode(manifest).encode()}
        allowed = {item['path'] for item in proof['inventory']} | set(documents)
        names = set(os.listdir(destination))
        _require(names <= allowed, 'Unowned publication directory entries cannot be removed.')
        sealed = bool(names & set(documents))
        missing = 0
        for item in proof['inventory']:
            if item['path'] not in names:
                missing += item['bytes']
                continue
            info = os.stat(item['path'], dir_fd=destination, follow_symlinks=False)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                     and info.st_nlink == 1 and info.st_size <= item['bytes'],
                     'Partial publication ownership cannot be established.')
            missing += item['bytes'] - info.st_size
        _require(shutil.disk_usage(runs.path).free >= missing + 512 * 1024**2,
                 'Insufficient storage for publication continuation.')
        for item in proof['inventory']:
            _check(runs, deadline); name = item['path']
            if name in names:
                try:
                    _copy(runs, destination, name, item, deadline)
                    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=destination)
                    try: os.fsync(descriptor)
                    finally: os.close(descriptor)
                    continue
                except WorkbenchError:
                    raise
                except ValueError:
                    _require(not sealed and not run['artifacts'] and
                             run['publication_continuation']['result_ref'] is None,
                             'Referenced or sealed publication bytes changed.')
                    info = os.stat(name, dir_fd=destination, follow_symlinks=False)
                    _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                             and info.st_nlink == 1 and info.st_size <= item['bytes'],
                             'Partial publication ownership cannot be established.')
                    os.unlink(name, dir_fd=destination)
            descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=destination)
            with os.fdopen(descriptor, 'wb') as output:
                _copy(runs, source, name, item, deadline, output)
                output.flush(); os.fsync(output.fileno())
        if runs._extension(run):
            runs._verify_extension(destination_path, dict(run, artifacts=manifest['artifacts']),
                                   checkpoint=lambda: _check(runs, deadline))
        for name, raw in documents.items():
            _check(runs, deadline)
            try:
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=destination)
            except FileExistsError:
                existing, _, _ = runs._diagnostic_read(destination, name, 65536)
                _require(existing == raw, 'Retained publication receipt or manifest changed.')
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=destination)
                try: os.fsync(descriptor)
                finally: os.close(descriptor)
            else:
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(raw); output.flush(); os.fsync(output.fileno())
        os.fsync(destination)
        descriptor = runs._diagnostic_directory(runs.path)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        return manifest
    finally:
        if source is not None: os.close(source)
        if destination is not None: os.close(destination)


def recover(runs, body):
    closed(body, ('run_id', 'source_ref', 'request_key'))
    body = copy.deepcopy(body)
    identifier(body['run_id'], 'Run ID')
    key, _ = runs._request(body, tuple(body))
    actor = runs.access.identity()['actor_id']
    request_sha = digest({'actor_id': actor, 'operation': 'runs.recover_publication', 'body': body})
    if not runs._publication_lock.acquire(blocking=False):
        with runs.lock:
            current = runs._load(body['run_id'])
        from candidate_packages import authorize_transitive_inputs
        authorize_transitive_inputs(runs, current)
        existing = current.get('publication_continuation')
        _require(type(existing) is dict and existing['request_sha256'] == request_sha,
                 'Another publication continuation is active.', 'conflict')
        if existing['state'] == 'published': result(runs, existing['result_ref'])
        return _status(current)
    runs._publication_active = (body['run_id'], key)
    runs._publication_cancel.clear()
    deadline = time.monotonic() + WALL_SECONDS
    try:
        runs._available(); _check(runs, deadline)
        with runs.lock:
            run = runs._load(body['run_id'])
        from candidate_packages import authorize_transitive_inputs
        authorize_transitive_inputs(runs, run)
        _require(runs._external(run) and run['state'] in ('failed', 'interrupted')
                 and not run['artifacts'], 'Only an unpublished failed/interrupted external attempt can continue.', 'unsupported')
        proof = _source(runs, run, body['source_ref'])
        fault = run.get('publication_fault')
        _require(type(fault) is dict and fault.get('source_sha256') == body['source_ref']['sha256']
                 and fault.get('code') in ('unavailable', 'storage', 'commit_unknown'),
                 'A recorded recoverable publication fault is required.')
        previous = run.get('publication_continuation')
        if previous is not None:
            _require(previous['request_sha256'] == request_sha, 'Publication request identity conflicts.', 'conflict')
            if previous['state'] == 'published':
                result(runs, previous['result_ref'], deadline=deadline, checkpoint=lambda: _check(runs, deadline))
                return _status(run)
            _require(len(previous['attempts']) < MAX_ATTEMPTS, 'Publication continuation history limit reached.', 'unsupported')
        else:
            previous = {'format': 'same_run_publication_continuation_v1', 'schema_version': 1, 'source_ref': body['source_ref'],
                'actor_id': actor, 'request_key': key, 'request_sha256': request_sha,
                'original_state': run['state'], 'state': 'recovering', 'attempts': [],
                'result_ref': None, 'cancel_requested': False, 'cancel_revision': 0}
        continuation = copy.deepcopy(previous)
        continuation['state'] = 'recovering'
        continuation['cancel_requested'] = False
        continuation['attempts'].append({'number': len(continuation['attempts']) + 1, 'started_at': timestamp(),
                                        'finished_at': None, 'state': 'recovering', 'error': None})
        with runs.lock, runs.db.transaction():
            run = runs._load(run['id'])
            current_continuation = run.get('publication_continuation')
            _require(current_continuation is None or current_continuation['cancel_revision'] == previous['cancel_revision'],
                     'Publication cancellation superseded this continuation request.', 'cancelled')
            run['publication_continuation'] = continuation; runs._save(run)
        clock = runs._phase_clock(run['id'])
        with phase_timings.observe(clock, 'recovery_verification', 'validating_outputs'):
            _verify_source(runs, run, proof, deadline)
        with phase_timings.observe(clock, 'recovery_publication', 'copying_outputs'):
            manifest = _publish(runs, run, proof, deadline)
        _check(runs, deadline)
        runs.access.require('approve-execution', 'runs.recover_publication', run['id'], owner_only=True)
        authorize_transitive_inputs(runs, run)
        document = {'format': 'recovered_publication_result_v1', 'schema_version': 1,
            'catalog_id': run['dataset_id'], 'run_id': run['id'], 'request_sha256': run['request_sha256'],
            'material_sha256': run['material_sha256'], 'source_ref': body['source_ref'],
            'continuation_request_sha256': request_sha,
            'inventory_sha256': proof['inventory_sha256'], 'custody_receipt_sha256': manifest['custody_receipt_sha256'],
            'artifacts': manifest['artifacts'], 'original_run_state': continuation['original_state'],
            'original_fault': fault}
        raw = encode(document).encode()
        ref = {'kind': 'recovered_publication_result', 'schema_version': 1,
            'catalog_id': run['dataset_id'], 'run_id': run['id'], 'material_sha256': run['material_sha256'],
            'inventory_sha256': proof['inventory_sha256'], 'custody_receipt_sha256': manifest['custody_receipt_sha256'],
            'sha256': hashlib.sha256(raw).hexdigest()}
        _store(runs, run, 'publication-result-v1.json', raw)
        with runs.lock, runs.db.transaction():
            current = runs._load(run['id'])
            _check(runs, deadline)
            _require(not current['publication_continuation']['cancel_requested'], 'Publication cancellation was acknowledged.', 'cancelled')
            _require(current['publication_continuation']['cancel_revision'] == continuation['cancel_revision'],
                     'Publication cancellation superseded result attachment.', 'cancelled')
            runs.access.require('approve-execution', 'runs.recover_publication', run['id'], owner_only=True)
            authorize_transitive_inputs(runs, current)
            _require(current['state'] == continuation['original_state'], 'Original Run outcome changed.', 'stale')
            continuation['state'] = 'published'; continuation['result_ref'] = ref
            continuation['attempts'][-1].update(state='published', finished_at=timestamp())
            current['publication_continuation'] = continuation; runs._save(current)
        return _status(current)
    except CommitOutcomeUnknown:
        raise
    except Exception as error:
        if 'continuation' in locals() and 'run' in locals():
            with runs.access._reconcile(), runs.lock, runs.db.transaction():
                current = runs._load(run['id'])
                saved = current.get('publication_continuation')
                if saved is not None and saved['request_sha256'] == request_sha and saved['state'] != 'published':
                    saved['state'] = 'paused' if isinstance(error, WorkbenchError) and error.code in ('cancelled', 'unavailable') else 'blocked'
                    saved['attempts'][-1].update(state=saved['state'], finished_at=timestamp(),
                        error={'code': error.code if isinstance(error, WorkbenchError) else 'unavailable',
                               'message': str(error)[:240] if isinstance(error, WorkbenchError) else 'Publication verification or storage failed.'})
                    if isinstance(error, WorkbenchError) and error.code == 'cancelled':
                        saved['cancel_requested'] = True
                    runs._save(current)
        if isinstance(error, (OSError, ValueError)) and not isinstance(error, WorkbenchError):
            raise WorkbenchError('Publication continuation could not verify retained bytes.', 'unavailable', 409) from error
        raise
    finally:
        runs._publication_active = None
        runs._publication_lock.release()


def cancel(runs, body):
    closed(body, ('run_id', 'request_key'))
    with runs.lock, runs.db.transaction():
        run = runs._load(body['run_id'])
        from candidate_packages import authorize_transitive_inputs
        authorize_transitive_inputs(runs, run)
        value = run.get('publication_continuation')
        _require(type(value) is dict and value['request_key'] == body['request_key'],
                 'Exact publication continuation request is required.', 'stale')
        if value['state'] == 'published':
            return _status(run)
        value['cancel_requested'] = True
        _require(value['cancel_revision'] < 2**53 - 1, 'Publication cancellation counter exhausted.', 'unsupported')
        value['cancel_revision'] += 1
        active = getattr(runs, '_publication_active', None) == (run['id'], body['request_key'])
        if active:
            runs.db.on_commit(runs._publication_cancel.set)
        else:
            value['state'] = 'paused'
            value['attempts'][-1].update(state='paused', finished_at=timestamp(),
                error={'code': 'cancelled', 'message': 'Publication continuation paused by its owner.'})
        runs._save(run)
        return _status(run)


@_reader_boundary
def result(runs, ref, *, deadline=None, checkpoint=None, _verify_payloads=True):
    deadline = time.monotonic() + WALL_SECONDS if deadline is None else deadline
    def guard():
        _read_check(runs, deadline)
        if checkpoint is not None: checkpoint()
    guard()
    closed(ref, ('kind', 'schema_version', 'catalog_id', 'run_id', 'material_sha256',
                 'inventory_sha256', 'custody_receipt_sha256', 'sha256'))
    _require(ref['kind'] == 'recovered_publication_result' and type(ref['schema_version']) is int
             and ref['schema_version'] == 1 and ref['catalog_id'] == runs.db.dataset_id,
             'Recovered result reference is unsupported or belongs to another catalog.', 'stale')
    identifier(ref['run_id'], 'Run ID')
    with runs.lock:
        run = runs._load(ref['run_id'])
    _result_ref(ref, run)
    from candidate_packages import authorize_transitive_inputs
    authorize_transitive_inputs(runs, run)
    continuation = run.get('publication_continuation')
    _require(type(continuation) is dict and continuation['state'] == 'published'
             and continuation['result_ref'] == ref, 'Recovered result is not attached to this original Run.', 'stale')
    source = _source(runs, run, run['publication_source'])
    guard()
    directory = runs._diagnostic_directory(runs._external_directory(run))
    try:
        raw, _, _ = runs._diagnostic_read(directory, 'publication-result-v1.json', MAX_DOCUMENT_BYTES)
    finally:
        os.close(directory)
    _require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'Recovered result content changed.')
    value = runs._progress_json(raw)
    closed(value, ('format', 'schema_version', 'catalog_id', 'run_id', 'request_sha256', 'material_sha256',
                   'source_ref', 'continuation_request_sha256', 'inventory_sha256', 'custody_receipt_sha256',
                   'artifacts', 'original_run_state', 'original_fault'))
    manifest = _manifest(run, source)
    _require(value.get('format') == 'recovered_publication_result_v1'
             and type(value.get('schema_version')) is int and value['schema_version'] == 1
             and value['request_sha256'] == run['request_sha256']
             and value['continuation_request_sha256'] == continuation['request_sha256']
             and value['original_fault'] == run['publication_fault']
             and value.get('artifacts') == manifest['artifacts'] and value.get('source_ref') == run['publication_source']
             and value.get('original_run_state') == run['state']
             and all(value.get(key) == ref[key] for key in ('catalog_id', 'run_id', 'material_sha256',
                 'inventory_sha256', 'custody_receipt_sha256')), 'Recovered result identity differs.')
    destination = runs._diagnostic_directory(runs.path / run['id'])
    try:
        _require(set(os.listdir(destination)) == {item['name'] for item in value['artifacts']} |
                 {'custody-receipt.json', 'artifact-manifest.json'}, 'Recovered result membership changed.')
        for name, expected in (('custody-receipt.json', encode(source['custody_receipt']).encode()),
                               ('artifact-manifest.json', encode(manifest).encode())):
            observed, _, _ = runs._diagnostic_read(destination, name, 65536)
            _require(observed == expected, 'Recovered publication receipt changed.')
        if _verify_payloads:
            for item in value['artifacts']:
                guard()
                runs._copy_verified(destination, item['name'], item, deadline=deadline,
                                    cancelled=lambda: runs._closed or runs._stop.is_set())
            if runs._extension(run):
                runs._verify_extension(runs.path / run['id'], dict(run, artifacts=value['artifacts']), checkpoint=guard)
    finally:
        os.close(destination)
    guard()
    _current_read(runs, ref['run_id'])
    return dict(value, result_ref=copy.deepcopy(ref))


@_reader_boundary
def artifact(runs, ref, name, expected_sha256):
    deadline = time.monotonic() + WALL_SECONDS
    value = result(runs, ref, deadline=deadline)
    item = next((item for item in value['artifacts'] if item['name'] == name), None)
    _require(item is not None and item['sha256'] == expected_sha256,
             'Exact recovered artifact identity is required.', 'stale')
    _require(item['bytes'] <= 8 * 1024**2, 'Recovered artifact exceeds the bounded reader size.', 'unsupported')
    _read_check(runs, deadline)
    directory = runs._diagnostic_directory(runs.path / ref['run_id'])
    try:
        raw, _, _ = runs._diagnostic_read(directory, name, 8 * 1024**2)
    finally:
        os.close(directory)
    _require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == expected_sha256,
             'Recovered artifact changed during capture.')
    _read_check(runs, deadline)
    _current_read(runs, ref['run_id'])
    return raw, item


@_reader_boundary
def artifact_segment(runs, ref, name, body):
    """Current exact-result authority, bounded bytes, provisional whole hash."""
    closed(body, ('expected_sha256', 'offset', 'max_bytes'))
    expected, offset, maximum = body['expected_sha256'], body['offset'], body['max_bytes']
    _require(_hash(expected) and type(offset) is int and 0 <= offset <= 512 * 1024**2
             and type(maximum) is int and 1 <= maximum <= 8 * 1024**2,
             'Publication segment needs exact hash, nonnegative offset and 1 through 8 MiB bound.', 'invalid')
    deadline = time.monotonic() + WALL_SECONDS
    # An attached immutable inventory permits provisional bounded reads. Full
    # result/semantic verification remains the explicit result reader's promise;
    # segmented clients must verify the reassembled whole digest themselves.
    value = result(runs, ref, deadline=deadline, _verify_payloads=False)
    item = next((item for item in value['artifacts'] if item['name'] == name), None)
    _require(item is not None and item['sha256'] == expected, 'Exact recovered artifact identity is required.', 'stale')
    _require(offset <= item['bytes'], 'Publication segment offset exceeds the artifact length.', 'invalid')
    directory = descriptor = None
    try:
        directory = runs._diagnostic_directory(runs.path / ref['run_id'])
        identity = os.fstat(directory)
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                 and before.st_nlink == 1 and before.st_size == item['bytes'], 'Recovered segment source changed.')
        _read_check(runs, deadline)
        raw = os.pread(descriptor, min(maximum, item['bytes'] - offset), offset)
        after = os.fstat(descriptor); current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')
        _require(len(raw) == min(maximum, item['bytes'] - offset)
                 and all(getattr(before, key) == getattr(after, key) == getattr(current, key) for key in keys),
                 'Recovered segment changed during capture.')
        current_directory = runs._diagnostic_directory(runs.path / ref['run_id'])
        try:
            current_identity = os.fstat(current_directory)
            _require((identity.st_dev, identity.st_ino) == (current_identity.st_dev, current_identity.st_ino),
                     'Recovered segment directory changed during capture.')
        finally: os.close(current_directory)
    finally:
        if descriptor is not None: os.close(descriptor)
        if directory is not None: os.close(directory)
    _read_check(runs, deadline)
    _current_read(runs, ref['run_id'])
    next_offset = offset + len(raw)
    return {'result_ref': copy.deepcopy(ref), 'run_id': ref['run_id'], 'name': name,
            'expected_sha256': expected, 'total_bytes': item['bytes'], 'media_type': item['media_type'],
            'offset': offset, 'bytes': len(raw), 'next_offset': next_offset,
            'eof': next_offset == item['bytes'], 'segment_sha256': hashlib.sha256(raw).hexdigest(),
            'data_base64': base64.b64encode(raw).decode('ascii'),
            'verification': 'segment_read_whole_hash_unverified'}


def _evidence(runs, ref, deadline):
    value = result(runs, ref, deadline=deadline, _verify_payloads=False)
    with runs.lock: run = runs._load(ref['run_id'])
    _require(runs._extension(run), 'Recovered result has no supported extension field evidence.', 'unsupported')
    verified = runs._verify_extension(runs.path / run['id'], dict(run, artifacts=value['artifacts']),
                                     checkpoint=lambda: _read_check(runs, deadline))
    return value, run, verified


@_reader_boundary
def model_evidence(runs, ref, body=None):
    import extension_evidence
    deadline = time.monotonic() + WALL_SECONDS
    _, _, verified = _evidence(runs, ref, deadline)
    projection = extension_evidence.query(verified, body)
    _read_check(runs, deadline)
    _current_read(runs, ref['run_id'])
    return {'result_ref': copy.deepcopy(ref), 'evidence': projection}


@_reader_boundary
def compare_evidence(runs, ref, other_ref, body):
    closed(body, ('checkpoint_sha256', 'other_checkpoint_sha256', 'evaluation_sha256', 'other_evaluation_sha256',
                  'metric_id', 'metric_definition_sha256', 'other_metric_definition_sha256', 'mode'))
    _require(body['mode'] in ('paired', 'side_by_side') and type(body['metric_id']) is str
             and 1 <= len(body['metric_id']) <= 64
             and all(_hash(value) for key, value in body.items() if key.endswith('sha256')),
             'Exact checkpoint, evaluation and metric identities are required.', 'invalid')
    deadline = time.monotonic() + WALL_SECONDS
    selected = [_evidence(runs, item, deadline) for item in (ref, other_ref)]
    contexts = []
    for index, (value, run, _) in enumerate(selected):
        item = next((item for item in value['artifacts'] if item['name'] == 'model-evidence.json'), None)
        _require(item is not None and item['sha256'] == body[('other_' if index else '') + 'evaluation_sha256'],
                 'Exact recovered evaluation identity differs.', 'stale')
        contexts.append(run['extension_context'])
    import extension_evidence
    comparison = extension_evidence.compare([item[2] for item in selected], contexts, body)
    _read_check(runs, deadline)
    for item in (ref, other_ref): _current_read(runs, item['run_id'])
    return {'result_refs': [copy.deepcopy(ref), copy.deepcopy(other_ref)], 'comparison': comparison}


@_reader_boundary
def compare_scientific(runs, body):
    """Read both supported custody forms through their existing authoritative owners."""
    closed(body, ('operands', 'selection', 'point'))
    _require(type(body['operands']) is list and len(body['operands']) == 2,
             'Select an exact baseline and candidate.', 'invalid')
    selection = body['selection']
    closed(selection, ('checkpoint_sha256', 'other_checkpoint_sha256', 'evaluation_sha256',
        'other_evaluation_sha256', 'metric_id', 'metric_definition_sha256', 'other_metric_definition_sha256', 'mode'))
    _require(selection['mode'] in ('paired', 'side_by_side') and type(selection['metric_id']) is str
             and 1 <= len(selection['metric_id']) <= 64
             and all(_hash(value) for key, value in selection.items() if key.endswith('sha256')),
             'Select exact checkpoint, evaluation and metric identities.', 'invalid')
    deadline = time.monotonic() + WALL_SECONDS
    selected = []; metadata = []
    for index, operand in enumerate(body['operands']):
        _require(type(operand) is dict, 'Invalid comparison operand.', 'invalid')
        if operand.get('kind') == 'publication_result':
            closed(operand, ('kind', 'ref'))
            value, run, verified = _evidence(runs, operand['ref'], deadline)
            artifacts = value['artifacts']
        elif operand.get('kind') == 'completed_run':
            closed(operand, ('kind', 'catalog_id', 'run_id'))
            _require(operand['catalog_id'] == runs.db.dataset_id, 'Comparison catalog differs.', 'stale')
            identifier(operand['run_id'], 'Comparison Run ID')
            runs.access.require('inspect', 'runs.compare_scientific_evidence', operand['run_id'])
            with runs.lock: run = runs._load(operand['run_id'])
            _require(run['state'] == 'completed' and runs._extension(run),
                     'Use an exact attached publication Ref for a recovered failed Run; legacy evidence is unsupported.', 'unsupported')
            runs._external_inventory(run)
            verified = runs._verify_extension(runs.path / run['id'], run,
                                             checkpoint=lambda: _read_check(runs, deadline))
            artifacts = run['artifacts']
        else:
            _require(False, 'Unsupported comparison operand kind.', 'unsupported')
        item = next((row for row in artifacts if row['name'] == 'model-evidence.json'), None)
        expected = selection[('other_' if index else '')+'evaluation_sha256']
        _require(item is not None and item['sha256'] == expected, 'Exact evaluation identity differs.', 'stale')
        selected.append((run, verified, copy.deepcopy(artifacts)))
        context = run['extension_context']
        association = runs.db.execute('SELECT study_id,trial_id FROM model_attempt_reservations WHERE run_id=%s',
                                      (run['id'],)).fetchone()
        membership = (dict(association, catalog_id=runs.db.dataset_id,
                           material_sha256=context['composition']['sha256']) if association is not None else None)
        metadata.append({'operand':copy.deepcopy(operand), 'original_run_state':run['state'],
            'model':copy.deepcopy(context['static']['model']), 'material':copy.deepcopy(context['composition']),
            'study_membership':membership,
            'configuration':copy.deepcopy(context['static']['policy']['model_specification']),
            'timings':runs.phase_timings(run['id']),
            'memory':{'state':'unknown','reason':'memory_measurement_not_retained_by_profile'},
            'artifacts':copy.deepcopy(artifacts), 'custody':'managed_run_artifacts'})
        _read_check(runs, deadline)
    import extension_evidence
    comparison = extension_evidence.compare_scientific([item[1] for item in selected],
        [item[0]['extension_context'] for item in selected], selection, body['point'])
    # Authority can change while bytes are read. Fence both operands after all
    # projection/timing work, through the same owners used for the initial read.
    for operand, (run, _, artifacts) in zip(body['operands'], selected, strict=True):
        if operand['kind'] == 'publication_result':
            current = result(runs, operand['ref'], deadline=deadline, _verify_payloads=False)
            _require(current['artifacts'] == artifacts, 'Publication inventory changed during comparison.', 'stale')
            _current_read(runs, run['id'])
        else:
            runs.access.require('inspect', 'runs.compare_scientific_evidence', run['id'])
            with runs.lock: current = runs._load(run['id'])
            _require(current['state'] == 'completed' and current['artifacts'] == artifacts,
                     'Completed Run inventory changed during comparison.', 'stale')
            runs._external_inventory(current)
        _read_check(runs, deadline)
    for run, _, _ in selected:
        _current_read(runs, run['id'])
    comparison['operands'] = metadata
    _require(len(encode(comparison).encode()) <= 2*1024**2, 'Comparison exceeds its response bound.')
    return comparison
