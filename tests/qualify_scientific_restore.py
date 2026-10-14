"""Opt-in staged scientific restore QA using existing metadata transfer owners.

No source deletion, model execution, historical replay or path rewriting. Each
phase is explicit. Keep all writers stopped; use a separate restore database.
Long baseline inventories are private; stdout contains only bounded summaries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backup_metadata as transfer
from metadata import Metadata

ACTIVE = {'queued', 'running', 'cancelling', 'unknown', 'pending', 'starting',
          'preparing', 'generating', 'stopping'}
JOB_TABLES = ('workspace_runs', 'generation_jobs', 'grounded_jobs', 'caption_proposals', 'text_classification_proposals')


def require(condition, message):
    if not condition:
        raise transfer.StorageTransferError(message)


def dsn(environment):
    value = os.environ.get(environment)
    require(bool(value), 'The selected private DSN environment variable is unset.')
    return value


def save_private(path, value):
    """Never overwrite earlier QA evidence or place it in the catalog tree."""
    path = Path(path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(transfer.canonical(value) + b'\n')
        stream.flush(); os.fsync(stream.fileno())
    transfer.sync_directory(path.parent)


def read_private(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
            'QA baseline must be an owned private regular file.')
    return json.loads(path.read_bytes())


def modes(path, files, exclude=()):
    """Independent QA mode oracle; intentionally not the transfer helper."""
    path = Path(path)
    result = {'': stat.S_IMODE(path.lstat().st_mode)}
    for name, item in files.items():
        if name in exclude:
            continue
        current = (path / name).lstat()
        require(not stat.S_ISLNK(current.st_mode), 'Unexpected source symlink.')
        require(stat.S_ISDIR(current.st_mode) if item['kind'] == 'directory' else
                stat.S_ISREG(current.st_mode) and current.st_nlink == 1, 'Unexpected source file kind/link count.')
        result[name] = stat.S_IMODE(current.st_mode)
    return result


def database_identity(metadata):
    # Hash a nonsecret connection identity; never serialize DSNs or passwords.
    info = metadata.connection.info
    return transfer.digest({'host': info.host, 'port': info.port, 'dbname': info.dbname})


def documents(tables, table):
    if table not in tables:
        return []
    state = tables[table]
    field = next((key for key in ('document', 'data') if key in state['columns']), None)
    if field is None:
        return []
    index = state['columns'].index(field)
    return [json.loads(transfer.unpack(row[index])) for row in state['rows']]


def check_quiescence(metadata, tables):
    for name in JOB_TABLES:
        require(metadata.claim_runtime(name), 'Stop every existing worker supervisor before this phase.')
    for table in JOB_TABLES:
        for value in documents(tables, table):
            require(value.get('state', value.get('status')) not in ACTIVE,
                    'Retained active or unknown work blocks a quiesced transfer.')


def check_custody(path, tables):
    """Use the existing receipt validator; refuse absent cessation evidence."""
    import recipe_process
    result = {}
    for run in documents(tables, 'workspace_runs'):
        if run.get('execution_kind') != 'external_recipe':
            continue
        if run['state'] != 'completed' and run.get('custody_phase') in ('prepared', 'barrier_ready'):
            continue  # Existing Runs recovery defines these as pre-GO.
        identity = run['id']
        require(len(identity) == 32 and all(c in '0123456789abcdef' for c in identity), 'Invalid retained Run identity.')
        try:
            raw = recipe_process.read_regular(Path(path)/'workspace-runs'/('.external-'+identity)/'custody'/'receipt.json', 16384)
            receipt = recipe_process.validate_receipt(raw, run.get('custody_identity'))
        except (OSError, ValueError, KeyError):
            require(False, 'Retained external attempt lacks verifiable cessation evidence; resolve through the Runs owner before transfer.')
        require(receipt['drained'], 'Retained external attempt has unconfirmed drainage.')
        if run['state'] == 'completed':
            published = recipe_process.read_regular(Path(path)/'workspace-runs'/identity/'custody-receipt.json', 16384)
            require(receipt['outcome'] == 'completed' and published == raw
                    and hashlib.sha256(raw).hexdigest() == run.get('custody_receipt_sha256'),
                    'Completed Run custody publication differs.')
        result[identity] = {'receipt_sha256':hashlib.sha256(raw).hexdigest(), 'drained':True, 'outcome':receipt['outcome']}
    return result


def snapshot(path, connection, *, exclude=(), quiesced=True):
    """Raw SQL/tree capture before any Dataset or authentication construction."""
    path = Path(path).resolve()
    metadata = Metadata(path, dsn=connection, create=False, schema_version=None)
    try:
        with metadata.lock, metadata.transaction():
            tables = transfer.read_catalog(metadata)
            if quiesced:
                check_quiescence(metadata, tables)
            files = transfer.tree_manifest(path, exclude)
            permissions = modes(path, files)
            sequences = transfer.read_sequences(metadata)
            require(files == transfer.tree_manifest(path, exclude) and permissions == modes(path, files),
                    'File bytes or modes changed during raw inventory.')
            result = {'dataset_id': metadata.dataset_id, 'schema_version': metadata.schema_version,
                'database_identity_sha256': database_identity(metadata),
                'schema_sha256': metadata._signature(), 'tables': transfer.summaries(tables),
                'sequences': sequences, 'files': files, 'modes': permissions,
                'custody': check_custody(path, tables),
                'packed_table_bytes': len(transfer.canonical(tables)),
                'run_states': {value['id']: value['state'] for value in documents(tables, 'workspace_runs')},
                'runtime_manifests': sorted(name.split('/')[1] for name in files
                    if name.startswith('runtime-snapshots/') and name.endswith('/manifest.json') and len(name.split('/')) == 3)}
            require(result['tables'] == transfer.summaries(transfer.read_catalog(metadata))
                    and sequences == transfer.read_sequences(metadata), 'SQL state changed during raw inventory.')
            return result
    finally:
        metadata.close()


def baseline(path):
    value = read_private(path)
    require(value.get('format') == 'tuldok-scientific-restore-baseline-v1', 'Unsupported QA baseline.')
    return value


def compare(actual, expected):
    for key in ('dataset_id', 'schema_version', 'schema_sha256', 'tables', 'sequences', 'files', 'modes', 'custody', 'run_states', 'runtime_manifests'):
        require(actual[key] == expected[key], 'Raw restored/source parity differs: ' + key)


def compact(state):
    return {'dataset_id': state['dataset_id'], 'schema_version': state['schema_version'],
        'schema_sha256': state['schema_sha256'], 'custody': state['custody'],
        'tables': {name: {'count': value['count'], 'sha256': value['sha256']} for name, value in state['tables'].items()},
        'sequences_sha256': transfer.digest(state['sequences']), 'files_sha256': transfer.digest(state['files']),
        'modes_sha256': transfer.digest(state['modes']), 'file_count': sum(value['kind'] == 'file' for value in state['files'].values()),
        'file_bytes': sum(value.get('bytes', 0) for value in state['files'].values()), 'run_states': state['run_states'],
        'runtime_manifests': state['runtime_manifests']}


def verify_backup(backup, base):
    """Independently read every packed SQL value and original file byte/mode."""
    backup = Path(backup).resolve()
    receipt = json.loads((backup / transfer.RECEIPT).read_bytes())
    metadata = json.loads((backup / 'metadata.json').read_bytes())
    require(transfer.file_hash(backup/'metadata.json') == receipt['metadata_sha256'], 'Backup metadata checksum differs.')
    require(receipt['dataset_id'] == metadata['dataset_id'] == base['dataset_id']
            and receipt['schema_version'] == metadata['schema_version'] == base['schema_version'], 'Backup catalog identity differs.')
    for state in metadata['tables'].values():
        require(transfer.table_state(state['columns'], [[transfer.unpack(value) for value in row] for row in state['rows']]) == state,
                'Packed SQL rows do not reconstruct their original hashes.')
    require(transfer.summaries(metadata['tables']) == receipt['tables'] == base['tables'], 'Backup SQL tables differ.')
    require(metadata['sequences'] == receipt['sequences'] == base['sequences'], 'Backup identity sequence high-water marks differ.')
    files = transfer.tree_manifest(backup/'catalog')
    require(files == receipt['files'] == base['files'], 'Backup file bytes differ.')
    require(modes(backup/'catalog', files) == base['modes'], 'Backup source modes differ.')
    return {'receipt_sha256': transfer.file_hash(backup/transfer.RECEIPT), 'receipt_digest': transfer.digest(receipt),
            'metadata_sha256': receipt['metadata_sha256'], 'files_sha256': transfer.digest(files)}


def sql_probe(backup, path, base, connection, restore_connection):
    """Explicit disposable DB only; retain its evidence, never drop any schema."""
    import psycopg
    require(not Path(path).exists(), 'SQL probe requires a new explicit task-owned directory.')
    identities = []
    for current in (connection, restore_connection):
        with psycopg.connect(current, autocommit=True) as probe:
            class ConnectionOnly: pass
            holder = ConnectionOnly(); holder.connection = probe
            identities.append(database_identity(holder))
    require(identities[0] != base['database_identity_sha256'] and identities[0] != identities[1],
            'SQL probe database must differ from both original and actual restore databases.')
    data = json.loads((Path(backup)/'metadata.json').read_bytes())
    metadata = Metadata(path, dsn=connection, create=True, dataset_id=base['dataset_id'], schema_version=base['schema_version'])
    try:
        with metadata.lock, metadata.transaction():
            transfer.populate_catalog(metadata, data['tables'])
            transfer.restore_sequences(metadata, data['sequences'])
            require(transfer.summaries(transfer.read_catalog(metadata)) == base['tables'], 'SQL probe row parity differs.')
            require(transfer.read_sequences(metadata) == base['sequences'], 'SQL probe sequence parity differs.')
            require(metadata._signature() == base['schema_sha256'], 'SQL probe schema differs.')
        require(transfer.summaries(transfer.read_catalog(metadata)) == base['tables']
                and transfer.read_sequences(metadata) == base['sequences'], 'Committed SQL probe parity differs.')
        return {'dataset_id':metadata.dataset_id, 'database_identity_sha256':identities[0],
                'tables_sha256':transfer.digest(base['tables']), 'sequences_sha256':transfer.digest(base['sequences']),
                'schema_sha256':metadata._signature(), 'path':str(Path(path).resolve()), 'committed':True}
    finally:
        metadata.close()


def raw_restored(backup, destination, base, connection):
    proof = verify_backup(backup, base)
    marker = '.restore-receipt-' + proof['receipt_digest'] + '.json'
    expected_marker = {'kind':'postgresql-restore', 'backup_sha256':proof['receipt_digest'], 'dataset_id':base['dataset_id']}
    require(json.loads((Path(destination)/marker).read_bytes()) == expected_marker, 'Restore marker differs.')
    actual = snapshot(destination, connection, exclude=(marker,))
    require(actual['database_identity_sha256'] != base['database_identity_sha256'], 'Restore must use a separate database.')
    compare(actual, base)
    return proof, actual


def qualified_reads(destination, connection, base, project_roots):
    # Imports with possible owner initialization occur only after raw parity.
    from app import Dataset
    from runtime_snapshots import RuntimeSnapshots
    dataset = Dataset(destination, dsn=connection, project_roots=project_roots)
    result = {'runtime_snapshots': [], 'runs': [], 'releases': [], 'scientific_views': []}
    try:
        login = dataset.access._local_owner_token(require_existing=True)
        credential = dataset.access.exchange(login)
        with dataset.access.bind(credential['token']):
            try:
                owner = RuntimeSnapshots(dataset.db, dataset.access, dataset.path)
                for identity in base['runtime_manifests']:
                    value = owner.get(identity, verify=True)
                    require(value['root'] == str(Path(destination).resolve()/'runtime-snapshots'/identity), 'Runtime inspection used a historical root.')
                    result['runtime_snapshots'].append({'manifest_sha256': identity, 'descriptor_sha256': transfer.digest(value), 'root': value['root']})
                for identity, state in sorted(base['run_states'].items()):
                    run = dataset.runs.get(identity)
                    require(run['state'] == state, 'Dataset opening replayed or changed a retained Run.')
                    if state != 'completed' or run.get('execution_kind') != 'external_recipe':
                        continue
                    artifacts = []
                    for item in run['artifacts']:
                        checksum, count = hashlib.sha256(), 0
                        with dataset.runs.open_artifact(identity, item['name']) as (stream, metadata):
                            while True:
                                chunk = stream.read(1024*1024)
                                if not chunk: break
                                checksum.update(chunk); count += len(chunk)
                            require(count == item['bytes'] == metadata['bytes'] and checksum.hexdigest() == item['sha256'], 'Completed payload parity differs.')
                        artifacts.append({'name':item['name'], 'role':item['role'], 'bytes':count, 'sha256':checksum.hexdigest()})
                    progress = dataset.runs.external_progress(identity)
                    require(progress['evidence'] == 'custody_verified', 'Restored completed progress lost retained custody.')
                    result['runs'].append({'id':identity, 'state':state, 'artifacts':artifacts, 'progress_sha256':transfer.digest(progress)})
                for name, entry in base['files'].items():
                    if name.startswith('releases/') and name.endswith('.zip') and len(name.split('/')) == 2:
                        identity = Path(name).stem
                        located = dataset.releases.locate(identity)
                        require(transfer.file_hash(located) == entry['sha256'] == identity, 'Restored immutable release differs.')
                        result['releases'].append({'id':identity,'bytes':entry['bytes']})
                # Exactly one actual retained field sequence is sufficient for a
                # typed slice/history owner checkpoint; all bytes were checked above.
                row = dataset.db.execute("SELECT id FROM workbench_records WHERE kind='field_sequence' ORDER BY id LIMIT 1").fetchone()
                if row:
                    record = dataset.workbench.get(row[0])
                    view = dataset.workbench.scientific.inspect(row[0])
                    history = dataset.workbench.history(row[0])
                    result['scientific_views'].append({'id':row[0], 'revision':record['revision'],
                        'source_revision':record['source_revision'], 'review':record['review'],
                        'view_sha256':transfer.digest(view), 'history_sha256':transfer.digest(history)})
                require(result['runtime_snapshots'] and result['runs'] and result['scientific_views'],
                        'Scientific qualification requires retained runtime, completed artifacts and a real field-sequence view.')
                require(dataset.runs._thread is None, 'Read qualification unexpectedly started the Runs scheduler.')
            finally:
                dataset.access.logout()
    finally:
        dataset.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('inventory', 'backup', 'verify-backup', 'probe-sql', 'restore-raw', 'qualify'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--probe-path', type=Path)
    parser.add_argument('--probe-dsn-env', default='TULDOK_PROBE_DATABASE_URL')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--source-dsn-env', default='TULDOK_DATABASE_URL')
    parser.add_argument('--restore-dsn-env', default='TULDOK_RESTORE_DATABASE_URL')
    parser.add_argument('--quiesced', action='store_true')
    parser.add_argument('--reserve-bytes', type=int, default=512*1024*1024)
    parser.add_argument('--allow-absent-source', action='store_true', help='Only after separately approved two-copy source disposition; never deletes anything.')
    parser.add_argument('--project-root', action='append', default=[], metavar='ALIAS=PATH')
    args = parser.parse_args()
    source = args.source.resolve()
    report = {'format':'tuldok-scientific-restore-qa-v1', 'phase':args.phase, 'source':str(source),
              'python':sys.version.split()[0], 'started_unix':time.time(), 'status':'failed'}
    report_authorized = False
    try:
        require(args.reserve_bytes >= 512*1024*1024, 'Keep at least 512 MiB operational reserve plus separately measured DB/WAL headroom.')
        require(args.quiesced, 'Every phase requires the explicit stopped-writers assertion --quiesced.')
        paths = [source, args.report.absolute(), args.baseline.absolute()]
        if args.backup: paths.append(args.backup.resolve())
        if args.destination: paths.append(args.destination.resolve())
        if args.probe_path: paths.append(args.probe_path.resolve())
        transfer.separate_paths(*paths)
        require(not args.report.exists(), 'Use a new report path for every attempt.')
        report_authorized = True
        report['free_before'] = shutil.disk_usage(source.parent).free
        if args.phase == 'inventory':
            state = snapshot(source, dsn(args.source_dsn_env))
            state.update(format='tuldok-scientific-restore-baseline-v1', source=str(source))
            save_private(args.baseline, state)
            report['raw'] = compact(state)
        else:
            state = baseline(args.baseline)
            require(state['source'] == str(source), 'Explicit source differs from baseline.')
            require(args.backup is not None, 'This phase requires --backup.')
            if args.phase == 'backup':
                compare(snapshot(source, dsn(args.source_dsn_env)), state)
                require(args.backup.parent.exists(), 'Create the approved backup parent before transfer.')
                required = sum(value.get('bytes',0) for value in state['files'].values()) + state['packed_table_bytes'] + args.reserve_bytes
                require(shutil.disk_usage(args.backup.parent).free >= required, 'Measured free space cannot hold backup plus reserve.')
                report['required_transfer_free_bytes'] = required
                transfer.backup_catalog(source, args.backup, dsn=dsn(args.source_dsn_env), quiesced=True)
                compare(snapshot(source, dsn(args.source_dsn_env)), state)
                report['backup'] = verify_backup(args.backup, state)
            elif args.phase == 'verify-backup':
                report['backup'] = verify_backup(args.backup, state)
            elif args.phase == 'probe-sql':
                require(args.probe_path is not None, 'SQL probe requires --probe-path.')
                report['backup'] = verify_backup(args.backup, state)
                report['sql_probe'] = sql_probe(args.backup, args.probe_path, state,
                    dsn(args.probe_dsn_env), dsn(args.restore_dsn_env))
            else:
                require(args.destination is not None, 'This phase requires --destination.')
                require(source.exists() or args.allow_absent_source, 'Source is absent; exact separately approved fallback must be explicit.')
                report['source_filesystem_present'] = source.exists()
                report['backup'] = verify_backup(args.backup, state)
                connection = dsn(args.restore_dsn_env)
                # Connection-only identity check before restore can create schema.
                import psycopg
                with psycopg.connect(connection, autocommit=True) as probe:
                    class ConnectionOnly: pass
                    holder = ConnectionOnly(); holder.connection = probe
                    require(database_identity(holder) != state['database_identity_sha256'], 'Restore database must be separate from the original.')
                if args.phase == 'restore-raw':
                    require(args.destination.parent.exists(), 'Create the approved restore parent before transfer.')
                    required = sum(value.get('bytes',0) for value in state['files'].values()) + args.reserve_bytes
                    require(shutil.disk_usage(args.destination.parent).free >= required, 'Measured free space cannot hold restore plus reserve.')
                    report['required_transfer_free_bytes'] = required
                    transfer.restore_catalog(args.backup, args.destination, dsn=connection)
                proof, restored = raw_restored(args.backup, args.destination, state, connection)
                report.update(backup=proof, destination=str(args.destination.resolve()), raw=compact(restored), raw_parity_before_dataset_and_auth=True)
                if args.phase == 'qualify':
                    roots = {}
                    for binding in args.project_root:
                        alias, separator, location = binding.partition('=')
                        require(separator and alias and location and alias not in roots, 'Supply unique explicit project root aliases.')
                        roots[alias] = location
                    report['reads'] = qualified_reads(args.destination, connection, state, roots)
                    marker = '.restore-receipt-' + proof['receipt_digest'] + '.json'
                    after = snapshot(args.destination, connection, exclude=(marker,))
                    changed = [name for name in state['tables'] if state['tables'][name] != after['tables'][name]]
                    require(set(changed) <= {'access_audit', 'access_credentials'}, 'Read qualification changed non-auth historical tables.')
                    require(after['run_states'] == state['run_states'] and after['sequences'] == state['sequences'], 'Qualification changed historical Runs or identity sequences.')
                    require(after['files'] == state['files'] and after['modes'] == state['modes'], 'Qualification changed retained artifact bytes/modes.')
                    report['post_auth_changed_tables'] = changed
                    report['backup_after'] = verify_backup(args.backup, state)
        report.update(status='passed', free_after=shutil.disk_usage(source.parent).free, completed_unix=time.time(),
                      baseline_sha256=transfer.file_hash(args.baseline))
    except Exception as error:
        # Metadata errors can include SQL values/connection details. Do not leak
        # them into stdout or a public report; preserve only a safe failure class.
        report['failure_type'] = type(error).__name__
        if isinstance(error, transfer.StorageTransferError): report['failure'] = str(error)
        if report_authorized:
            save_private(args.report, report)
        print(json.dumps({'status':'failed','phase':args.phase,'report':str(args.report),'failure_type':type(error).__name__}))
        return 1
    save_private(args.report, report)
    print(json.dumps({'status':'passed','phase':args.phase,'report':str(args.report),
                      'report_sha256':transfer.file_hash(args.report),'dataset_id':state['dataset_id']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
