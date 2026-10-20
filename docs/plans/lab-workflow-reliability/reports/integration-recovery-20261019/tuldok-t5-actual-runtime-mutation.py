#!/usr/bin/env python3
"""Proposed finite T5 real-byte integrity observation; requires explicit execution.

No installation, training, Run admission, GO, cache or performance qualification.
Only a new owned capture is mutated; the nominated installation is read-only.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import time


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    raw = encoded(value)
    temporary = path.with_suffix('.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def require_conflict(call, expected_code):
    from workbench import WorkbenchError
    try:
        call()
    except WorkbenchError as error:
        require(error.status == 409 and error.code == expected_code,
                'Wrong domain refusal: ' + str((error.status, error.code)))
        return {'status': error.status, 'code': error.code}
    raise AssertionError('Changed real runtime bytes were accepted')


def owned_bytes(root):
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        require(not any((Path(directory) / name).is_symlink() for name in dirs),
                'Unexpected directory symlink in owned fixture')
        for name in files:
            info = (Path(directory) / name).lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
                    'Owned fixture must contain private regular files only')
            total += info.st_size
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    require(args.execute, 'Review driver and plan before explicit --execute')
    plan = json.loads(args.plan.read_bytes())
    require(sha(Path(__file__).read_bytes()) == plan['driver_sha256'], 'Driver changed after review')
    source = Path(plan['source_root'])
    for name, digest in plan['source_files_sha256'].items():
        require(sha((source / name).read_bytes()) == digest, 'Source changed: ' + name)
    sys.path[:0] = [str(source), str(source / 'tests')]
    import psycopg
    from psycopg import sql
    from metadata import Metadata
    from access import Access
    from runtime_snapshots import RuntimeSnapshots
    from torch_runtimes import TorchRuntimes
    import torch_runtime

    root, catalog = Path(plan['owned_root']), Path(plan['catalog_path'])
    receipt_path = Path(plan['receipt_path'])
    config_path = Path(plan['configuration_path'])
    config_raw = config_path.read_bytes()
    require(sha(config_raw) == plan['configuration_sha256'], 'Nominated configuration changed')
    config = json.loads(config_raw)
    require(root.parent == Path('/tmp') and root.name == 'tuldok-t5-real-runtime-' + plan['dataset_id'],
            'Owned root differs from exact preregistration')
    require(catalog == root / 'catalog' and plan['schema'] == 'catalog_' + plan['dataset_id'],
            'Catalog differs from exact preregistration')
    require(not root.exists() and not receipt_path.exists(), 'Refuse reuse of prior task artifacts')
    require(plan['owned_cap_bytes'] == 2 * 1024**3 and plan['reserve_bytes'] >= 512 * 1024**2,
            'Unsupported cap or reserve')
    root.mkdir(mode=0o700)
    marker = root / '.t5-owned.json'
    marker.write_bytes(encoded({'dataset_id': plan['dataset_id'], 'schema': plan['schema']}))
    os.chmod(marker, 0o600)
    receipt = {'format': 't5_actual_runtime_mutation_observation_v1', 'state': 'started',
               'source_head': plan['source_head'], 'driver_sha256': plan['driver_sha256'],
               'configuration_sha256': sha(config_raw), 'owned_root': str(root),
               'catalog_path': str(catalog), 'schema': plan['schema'],
               'dsn': plan['dsn'], 'checks': [], 'cleanup': {}, 'training_executed': False,
               'run_or_grant_or_go_calls': 0,
               'scope': 'Real CPU asset bytes copied by existing owners; no numerical or speed claim'}
    # Exact target recorded before Metadata construction for controlled-process cleanup.
    save(receipt_path, receipt)
    database = None
    original_copy_bytes = None
    mutated = None
    mutated_stat = None
    schema_was_absent = False
    constructor_entered = False
    started = time.monotonic()

    def deadline(_signal, _frame):
        raise TimeoutError('Finite 600 second qualification budget exhausted')

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(600)
    try:
        with psycopg.connect(plan['dsn'], autocommit=True, connect_timeout=5) as connection:
            connection.execute("SET statement_timeout = '10s'")
            require(connection.execute('SELECT to_regnamespace(%s)', (plan['schema'],)).fetchone()[0] is None,
                    'Preregistered schema already exists; no construction or cleanup authorized')
        schema_was_absent = True
        receipt['schema_absent_before_constructor'] = True
        save(receipt_path, receipt)
        constructor_entered = True
        database = Metadata(catalog, dsn=plan['dsn'], dataset_id=plan['dataset_id'])
        require(database.schema == plan['schema'], 'Unexpected catalog schema')
        access = Access(database, catalog)
        token = access.exchange(access._local_owner_token(initial=True))['token']
        with access.bind(token):
            tables = ('workspace_graphs', 'workspace_runs', 'access_execution_grants',
                      'access_execution_consumptions', 'model_attempt_reservations', 'access_admissions')
            def counts():
                return {name: database.execute(sql.SQL('SELECT count(*) FROM {}').format(
                    sql.Identifier(name))).fetchone()[0] for name in tables}
            receipt['counts_before'] = counts()
            require(all(value == 0 for value in receipt['counts_before'].values()), 'Fresh effects were not empty')
            snapshots = RuntimeSnapshots(database, access, catalog)
            measured = snapshots.inspect(config)
            require(measured['inventory_sha256'] == plan['expected_runtime_sha256'],
                    'Actual runtime differs from exact previous qualification; no fallback')
            # One copy plus its manifest, a bounded managed manifest and local metadata.
            cap_required = measured['total_bytes'] + measured['manifest_bytes'] + 48 * 1024**2
            required = measured['total_bytes'] + measured['manifest_bytes'] + plan['reserve_bytes']
            receipt['capacity'] = dict(payload_bytes=measured['total_bytes'],
                manifest_bytes=measured['manifest_bytes'], file_count=measured['file_count'],
                free_before_bytes=measured['free_bytes'], required_bytes=required,
                owned_bound_required_bytes=cap_required, owned_cap_bytes=plan['owned_cap_bytes'],
                reserve_bytes=plan['reserve_bytes'])
            save(receipt_path, receipt)
            require(cap_required <= plan['owned_cap_bytes'], 'Measured fixture exceeds owned cap')
            require(measured['free_bytes'] >= required, 'Insufficient space; no copy attempted')
            captured = snapshots.create(config, measured['inventory_sha256'], quiesced=True,
                                        reserve_bytes=plan['reserve_bytes'])
            receipt['baseline_captured_descriptor'] = captured
            copied_root = Path(captured['root'])
            require(copied_root.resolve().is_relative_to(root.resolve()), 'Copy escaped owned root')
            receipt['owned_bytes_after_capture'] = owned_bytes(root)
            require(receipt['owned_bytes_after_capture'] <= plan['owned_cap_bytes'], 'Owned cap exceeded')
            copied_config = copy.deepcopy(config)
            copied_config.update(python_root=str(copied_root / 'python'), site_packages=str(copied_root / 'packages'))
            copy_before = snapshots.inspect(copied_config)
            require(copy_before['inventory_sha256'] == measured['inventory_sha256'],
                    'Copied source inventory differs before mutation')
            managed = TorchRuntimes(database, access, catalog)
            installed_config = dict(python=str(copied_root / 'python/bin/python3.12'),
                python_root=str(copied_root / 'python'), site_packages=str(copied_root / 'packages'))
            installed = managed.inspect(installed_config)
            managed_identity = installed['manifest_sha256']
            managed.create(installed['manifest'], managed_identity)
            baseline_managed, _managed_raw = managed.get(managed_identity)
            receipt['baseline_managed_identity'] = managed_identity
            receipt['baseline_verified_managed_descriptor'] = baseline_managed
            mutated = copied_root / 'packages/torch/__init__.py'
            original_source = Path(config['site_packages']) / 'torch/__init__.py'
            mutated_stat = mutated.stat()
            require(mutated.resolve().is_relative_to(copied_root.resolve()) and mutated_stat.st_nlink == 1
                    and mutated_stat.st_uid == os.getuid() and not mutated.is_symlink(), 'Unsafe mutation target')
            source_stat = original_source.stat()
            require((source_stat.st_dev, source_stat.st_ino) != (mutated_stat.st_dev, mutated_stat.st_ino),
                    'Copy aliases original installation')
            original_copy_bytes = mutated.read_bytes()
            require(original_copy_bytes and sha(original_source.read_bytes()) == sha(original_copy_bytes),
                    'Selected real source differs from copied byte identity')
            receipt['baseline_torch_file'] = {
                'copied': dict(path=str(mutated), bytes=mutated_stat.st_size,
                    mode=stat.S_IMODE(mutated_stat.st_mode), mtime_ns=mutated_stat.st_mtime_ns,
                    sha256=sha(original_copy_bytes)),
                'original': dict(path=str(original_source), bytes=source_stat.st_size,
                    mode=stat.S_IMODE(source_stat.st_mode), mtime_ns=source_stat.st_mtime_ns,
                    sha256=sha(original_source.read_bytes()))}
            save(receipt_path, receipt)
            changed = bytes([original_copy_bytes[0] ^ 1]) + original_copy_bytes[1:]
            os.chmod(mutated, 0o600)
            with mutated.open('r+b') as handle:
                handle.write(changed); handle.flush(); os.fsync(handle.fileno())
            os.chmod(mutated, stat.S_IMODE(mutated_stat.st_mode))
            os.utime(mutated, ns=(mutated_stat.st_atime_ns, mutated_stat.st_mtime_ns))
            require(mutated.stat().st_size == mutated_stat.st_size and
                    mutated.stat().st_mtime_ns == mutated_stat.st_mtime_ns, 'Size/mtime negative not isolated')
            receipt['mutation'] = dict(relative_path='packages/torch/__init__.py',
                bytes=len(changed), original_sha256=sha(original_copy_bytes), changed_sha256=sha(changed),
                same_size=True, restored_mtime_ns=mutated_stat.st_mtime_ns)
            receipt['managed_old_verified_get'] = require_conflict(lambda: managed.get(managed_identity), 'unavailable')
            receipt['captured_old_verified_get'] = require_conflict(
                lambda: snapshots.get(captured['manifest_sha256']), 'stale')
            changed_managed = managed.inspect(installed_config)
            changed_copy = snapshots.inspect(copied_config)
            require(changed_managed['manifest_sha256'] != managed_identity and
                    changed_copy['inventory_sha256'] != measured['inventory_sha256'], 'Fresh inspection reused old identity')
            receipt['changed_managed_sha256'] = changed_managed['manifest_sha256']
            receipt['changed_copy_sha256'] = changed_copy['inventory_sha256']
            receipt['old_capture_request_from_changed_copy'] = require_conflict(lambda:
                snapshots.create(copied_config, measured['inventory_sha256'], quiesced=True,
                                 reserve_bytes=plan['reserve_bytes']), 'stale')
            require(len([path for path in snapshots.path.iterdir() if not path.name.startswith('.')]) == 1,
                    'Refusal created a second captured copy')
            os.chmod(mutated, 0o600)
            with mutated.open('r+b') as handle:
                handle.write(original_copy_bytes); handle.truncate(); handle.flush(); os.fsync(handle.fileno())
            os.chmod(mutated, stat.S_IMODE(mutated_stat.st_mode))
            os.utime(mutated, ns=(mutated_stat.st_atime_ns, mutated_stat.st_mtime_ns))
            restored_stat = mutated.stat()
            restored_file = dict(path=str(mutated), bytes=restored_stat.st_size,
                mode=stat.S_IMODE(restored_stat.st_mode), mtime_ns=restored_stat.st_mtime_ns,
                sha256=sha(mutated.read_bytes()))
            receipt['restored_torch_file'] = restored_file
            require(restored_file == receipt['baseline_torch_file']['copied'],
                    'Restored copy hash/size/mode/mtime differ from exact original copy')
            restored_managed, _restored_raw = managed.get(managed_identity)
            receipt['restored_verified_managed_descriptor'] = restored_managed
            require(restored_managed == baseline_managed, 'Restored managed descriptor differs')
            require(snapshots.get(captured['manifest_sha256']) == captured, 'Exact restoration changed captured descriptor')
            require(managed.inspect(installed_config)['manifest_sha256'] == managed_identity,
                    'Exact restoration changed managed identity')
            after_original = snapshots.inspect(config)
            require(after_original['inventory_sha256'] == measured['inventory_sha256'] and
                    sha(config_path.read_bytes()) == plan['configuration_sha256'], 'Original runtime/config changed')
            receipt['original_runtime_before_sha256'] = measured['inventory_sha256']
            receipt['original_runtime_after_sha256'] = after_original['inventory_sha256']
            receipt['counts_after'] = counts()
            require(receipt['counts_after'] == receipt['counts_before'], 'Run/grant/job accounting changed')
            receipt['audit_actions'] = [row[0] for row in database.execute('SELECT DISTINCT action FROM access_audit ORDER BY action')]
            require(not any(action.startswith(('runs.', 'access.grant_execution', 'access.consume_execution',
                                               'access.admit_job')) for action in receipt['audit_actions']),
                    'Unexpected execution authority action')
            receipt['owned_bytes_after'] = owned_bytes(root)
            require(receipt['owned_bytes_after'] <= plan['owned_cap_bytes'], 'Owned cap exceeded')
            require(shutil.disk_usage(root).free >= 512 * 1024**2, 'Current 512 MiB floor unavailable')
            receipt['checks'] = ['real_capture_equal_inventory', 'private_real_copy_no_inode_alias',
                'same_size_restored_mtime_byte_mutation', 'old_managed_verified_get_409',
                'old_captured_verified_get_409', 'fresh_inspections_new_identity',
                'old_expected_identity_capture_refused_without_second_copy', 'exact_restore_both_old_gets_pass',
                'original_full_inventory_and_config_unchanged', 'zero_run_grant_job_accounting']
            access.logout()
        for name, digest in plan['source_files_sha256'].items():
            require(sha((source / name).read_bytes()) == digest, 'Source changed during observation: ' + name)
        receipt['state'] = 'passed'
    except BaseException as error:
        receipt['state'] = 'failed'
        receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        signal.alarm(0)
        receipt['wall_seconds_before_cleanup'] = time.monotonic() - started
        # No schema inferred from a partial catalog: only the preregistered absent identity.
        cleanup_errors = []
        if database is not None:
            try:
                database.close()
            except BaseException as error:
                cleanup_errors.append('database.close:' + type(error).__name__)
        if schema_was_absent and constructor_entered:
            try:
                with psycopg.connect(plan['dsn'], autocommit=True, connect_timeout=5) as connection:
                    connection.execute("SET lock_timeout = '5s'")
                    connection.execute("SET statement_timeout = '10s'")
                    connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(plan['schema'])))
                    receipt['cleanup']['schema_absent'] = connection.execute(
                        'SELECT to_regnamespace(%s)', (plan['schema'],)).fetchone()[0] is None
            except BaseException as error:
                cleanup_errors.append('schema:' + type(error).__name__)
        try:
            require(json.loads(marker.read_bytes()) == {'dataset_id': plan['dataset_id'], 'schema': plan['schema']},
                    'Owned marker differs; refuse directory cleanup')
            shutil.rmtree(root)
            receipt['cleanup']['owned_directory_absent'] = not root.exists()
        except BaseException as error:
            cleanup_errors.append('directory:' + type(error).__name__)
        receipt['cleanup']['errors'] = cleanup_errors
        if cleanup_errors:
            receipt['state'] = 'failed_cleanup'
        receipt['wall_seconds_total'] = time.monotonic() - started
        save(receipt_path, receipt)
        print(json.dumps({'state': receipt['state'], 'receipt': str(receipt_path), 'cleanup': receipt['cleanup']}), flush=True)
        if cleanup_errors and sys.exc_info()[0] is None:
            raise RuntimeError('Owned cleanup incomplete; see retained receipt')


if __name__ == '__main__':
    main()
