"""Quiesced, lossless PostgreSQL catalog plus ordinary-file backup and restore.

The JSON container encodes SQL values; stored evidence JSON remains opaque text.
A restore always targets a new directory and an absent catalog schema. It never
changes the original database, and restoring a backup is not a merge of writes.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid

from psycopg import sql

FORMAT_VERSION = 1
RECEIPT = 'backup-receipt.json'
ORDERS = {name: 'ordinal' for name in ('generation_jobs', 'grounded_jobs',
                                      'caption_proposals', 'text_classification_proposals')}
ORDERS['generation_entries'] = 'storage_order'


class StorageTransferError(ValueError):
    """An unsupported, unavailable or contradictory transfer is never success."""


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def write_json(path, value):
    """Replace a task-owned receipt only after the complete bytes reach disk."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('xb') as stream:
        stream.write(canonical(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def tree_manifest(path, exclude=()):
    """Hash all regular files and empty directories; never follow symlinks."""
    path = Path(path)
    if not path.is_dir() or path.is_symlink():
        raise StorageTransferError('Catalog must be an ordinary directory.')
    result = {}
    for item in sorted(path.rglob('*')):
        name = item.relative_to(path).as_posix()
        if name in exclude:
            continue
        mode = item.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise StorageTransferError('Unsupported symlink or special file: ' + name)
        if stat.S_ISDIR(mode):
            result[name] = {'kind': 'directory'}
        else:
            result[name] = {'kind': 'file', 'bytes': item.stat().st_size,
                            'sha256': file_hash(item)}
    return result


def separate_paths(*paths):
    paths = [Path(path).resolve() for path in paths]
    for i, left in enumerate(paths):
        for right in paths[i + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise StorageTransferError('Source, backup and destination must be separate, non-nested paths.')
    return paths


def copy_tree(source, target, expected):
    """Copy missing bytes into an owned staging directory; refuse changed bytes."""
    source, target = Path(source), Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name, entry in expected.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or name != relative.as_posix():
            raise StorageTransferError('Unsafe artifact path in receipt.')
        source_file, target_file = source / relative, target / relative
        if target_file.is_symlink():
            raise StorageTransferError('Destination contains a symlink.')
        if entry['kind'] == 'directory':
            target_file.mkdir(parents=True, exist_ok=True)
        else:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if target_file.exists():
                if not target_file.is_file() or file_hash(target_file) != entry['sha256']:
                    raise StorageTransferError('Staged artifact differs from backup: ' + name)
            else:
                # A partial copy is never given the final artifact name.
                temporary = target.parent / ('.tuldok-transfer-' + uuid.uuid4().hex)
                try:
                    with source_file.open('rb') as reader, temporary.open('xb') as writer:
                        shutil.copyfileobj(reader, writer)
                        writer.flush()
                        os.fsync(writer.fileno())
                    if temporary.stat().st_size != entry['bytes'] or file_hash(temporary) != entry['sha256']:
                        raise StorageTransferError('Artifact changed during copy: ' + name)
                    os.rename(temporary, target_file)
                finally:
                    temporary.unlink(missing_ok=True)
    for directory in sorted((p for p in target.rglob('*') if p.is_dir()), reverse=True):
        sync_directory(directory)
    sync_directory(target)


def pack(value):
    if value is None or type(value) in (int, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'bytea': base64.b64encode(value).decode('ascii')}
    raise StorageTransferError('Unsupported SQL value type: ' + type(value).__name__)


def unpack(value):
    if value is None or type(value) in (int, str):
        return value
    if isinstance(value, dict) and set(value) == {'bytea'} and isinstance(value['bytea'], str):
        try:
            return base64.b64decode(value['bytea'], validate=True)
        except ValueError:
            pass
    raise StorageTransferError('Unsupported encoded SQL value.')


def table_state(columns, rows):
    # Sort representations, not SQL collation, to compare identical bytes on both stores.
    packed = sorted(([pack(value) for value in row] for row in rows), key=canonical)
    hashes = [digest(row) for row in packed]
    return {'columns': list(columns), 'rows': packed, 'count': len(packed),
            'row_sha256': hashes, 'sha256': digest({'columns': list(columns), 'rows': hashes})}


def read_catalog(metadata):
    metadata.validate_schema()
    result = {}
    for table in sorted(metadata.tables):
        cursor = metadata.connection.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table)))
        result[table] = table_state([column.name for column in cursor.description], cursor.fetchall())
    return result



def read_sequences(metadata):
    """Retain identity high-water marks, including allocations whose rows were deleted."""
    result = {}
    for table, column in ORDERS.items():
        row = metadata.connection.execute(sql.SQL('SELECT last_value,is_called FROM {}').format(
            sql.Identifier(metadata.schema, table + '_' + column + '_seq'))).fetchone()
        result[table] = {'last_value': row[0], 'is_called': row[1]}
    return result


def restore_sequences(metadata, sequences):
    if set(sequences) != set(ORDERS):
        raise StorageTransferError('Unsupported backup identity sequences.')
    for table, value in sequences.items():
        if (set(value) != {'last_value', 'is_called'} or type(value['last_value']) is not int
                or not 1 <= value['last_value'] < 2 ** 63 or type(value['is_called']) is not bool):
            raise StorageTransferError('Unsupported identity sequence state.')
        maximum = metadata.connection.execute(sql.SQL('SELECT max({}) FROM {}').format(
            sql.Identifier(ORDERS[table]), sql.Identifier(table))).fetchone()[0]
        if maximum is not None and (value['last_value'] < maximum or
                                   (value['last_value'] == maximum and not value['is_called'])):
            raise StorageTransferError('Identity sequence would reuse an imported order value.')
        metadata.connection.execute('SELECT setval(pg_get_serial_sequence(%s,%s),%s,%s)',
                                    (table, ORDERS[table], value['last_value'], value['is_called']))


def summaries(tables):
    return {name: {key: state[key] for key in ('columns', 'count', 'row_sha256', 'sha256')}
            for name, state in tables.items()}


def populate_catalog(metadata, tables):
    """Caller owns one transaction; identity order is imported explicitly."""
    expected = read_catalog(metadata)
    if set(tables) != set(metadata.tables):
        raise StorageTransferError('Unsupported backup table set.')
    for table, state in tables.items():
        if state['columns'] != expected[table]['columns']:
            raise StorageTransferError('Unsupported backup columns: ' + table)
        if expected[table]['count']:
            raise StorageTransferError('Destination catalog is not empty.')
        rows = [[unpack(value) for value in row] for row in state['rows']]
        if table_state(state['columns'], rows) != state:
            raise StorageTransferError('Backup row/hash reconciliation failed: ' + table)
        statement = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
            sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, state['columns'])),
            sql.SQL(',').join(sql.Placeholder() for _ in state['columns']))
        for row in rows:
            metadata.connection.execute(statement, row)
        if table in ORDERS:
            column = ORDERS[table]
            metadata.connection.execute(sql.SQL('''SELECT setval(pg_get_serial_sequence(%s,%s),
                greatest(coalesce((SELECT max({}) FROM {}),0),0)+1,false)''').format(
                    sql.Identifier(column), sql.Identifier(table)), (table, column))
    if summaries(read_catalog(metadata)) != summaries(tables):
        raise StorageTransferError('Restored PostgreSQL row/hash reconciliation failed.')


def backup_catalog(path, backup, *, dsn=None, quiesced=False):
    """Create a complete immutable backup after the caller stops every writer."""
    from metadata import Metadata
    if not quiesced:
        raise StorageTransferError('Stop all app/artifact writers and explicitly pass quiesced=True / --quiesced.')
    path, backup = separate_paths(path, backup)
    if backup.exists():
        raise StorageTransferError('Backup destination already exists; never overwrite a backup.')
    backup.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=backup.name + '.partial-', dir=backup.parent))
    metadata = Metadata(path, dsn=dsn, create=False, schema_version=None)
    try:
        with metadata.lock, metadata.transaction():
            before = tree_manifest(path)
            tables = read_catalog(metadata)
            sequences = read_sequences(metadata)
            copy_tree(path, temporary / 'catalog', before)
            if before != tree_manifest(path) or before != tree_manifest(temporary / 'catalog'):
                raise StorageTransferError('Artifacts changed during backup. Keep all writers stopped.')
            write_json(temporary / 'metadata.json', {'format_version': FORMAT_VERSION,
                       'schema_version': metadata.schema_version, 'dataset_id': metadata.dataset_id, 'tables': tables,
                       'sequences': sequences})
            import psycopg
            receipt = {'format_version': FORMAT_VERSION, 'kind': 'postgresql',
                       'schema_version': metadata.schema_version, 'dataset_id': metadata.dataset_id,
                       'postgresql_server_version': metadata.connection.info.server_version,
                       'driver': 'psycopg ' + psycopg.__version__,
                       'restore_privileges': 'CONNECT and CREATE on a new PostgreSQL database; catalog schema must be absent',
                       'metadata_sha256': file_hash(temporary / 'metadata.json'),
                       'files': before, 'tables': summaries(tables), 'sequences': sequences}
            write_json(temporary / RECEIPT, receipt)
        os.rename(temporary, backup)
        sync_directory(backup.parent)
        return receipt
    finally:
        metadata.close()
        if temporary.exists():
            shutil.rmtree(temporary)


def restore_catalog(backup, destination, *, dsn=None):
    """Restore the same dataset identity into an absent schema and new directory."""
    from metadata import Metadata, SUPPORTED_SCHEMA_VERSIONS
    backup, destination = separate_paths(backup, destination)
    receipt = json.loads((backup / RECEIPT).read_bytes())
    version = receipt.get('schema_version')
    if (receipt.get('format_version') != FORMAT_VERSION or receipt.get('kind') != 'postgresql'
            or type(version) is not int or version not in SUPPORTED_SCHEMA_VERSIONS):
        raise StorageTransferError('Unsupported PostgreSQL backup version.')
    if tree_manifest(backup / 'catalog') != receipt['files'] or file_hash(backup / 'metadata.json') != receipt['metadata_sha256']:
        raise StorageTransferError('Backup file/hash reconciliation failed.')
    data = json.loads((backup / 'metadata.json').read_bytes())
    if (type(data.get('schema_version')) is not int or
            (data.get('format_version'), data.get('schema_version'), data.get('dataset_id')) != (FORMAT_VERSION, version, receipt['dataset_id']) or
            summaries(data['tables']) != receipt['tables'] or data.get('sequences') != receipt.get('sequences')):
        raise StorageTransferError('Backup metadata/receipt reconciliation failed.')
    identity = receipt['dataset_id']
    if not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
        raise StorageTransferError('Invalid backup dataset identity.')
    marker_name = '.restore-receipt-' + digest(receipt) + '.json'
    marker = {'kind': 'postgresql-restore', 'backup_sha256': digest(receipt), 'dataset_id': identity}
    staging = destination.with_name(destination.name + '.restore-' + identity)
    if destination.exists():
        if json.loads((destination / marker_name).read_bytes()) != marker:
            raise StorageTransferError('Destination already exists and belongs to another restore.')
        metadata = Metadata(destination, dsn=dsn, create=False, dataset_id=identity, schema_version=version)
        try:
            with metadata.lock, metadata.transaction():
                if summaries(read_catalog(metadata)) != receipt['tables'] or read_sequences(metadata) != receipt['sequences'] or tree_manifest(destination, (marker_name,)) != receipt['files']:
                    raise StorageTransferError('Restored catalog has changed; refusing to overwrite later writes.')
            return marker
        finally:
            metadata.close()
    if staging.exists():
        if json.loads((staging / marker_name).read_bytes()) != marker:
            raise StorageTransferError('Restore staging directory belongs to another transfer.')
    else:
        staging.mkdir(parents=True, mode=0o700)
        write_json(staging / marker_name, marker)
    # The source manifest names an already existing schema. Create this catalog
    # before copying that manifest, so an existing schema is never reused.
    existed = (staging / '.tuldok.json').exists()
    metadata = Metadata(staging, dsn=dsn, create=not existed, dataset_id=identity, schema_version=version)
    try:
        with metadata.lock, metadata.transaction():
            current = read_catalog(metadata)
            if any(state['count'] for state in current.values()):
                if summaries(current) != receipt['tables']:
                    raise StorageTransferError('Restore destination contains different metadata.')
            else:
                populate_catalog(metadata, data['tables'])
            restore_sequences(metadata, data['sequences'])
        copy_tree(backup / 'catalog', staging, receipt['files'])
        if tree_manifest(staging, (marker_name,)) != receipt['files']:
            raise StorageTransferError('Restored artifact/hash reconciliation failed.')
        os.rename(staging, destination)
        sync_directory(destination.parent)
        return marker
    finally:
        metadata.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('backup')
    create.add_argument('catalog'); create.add_argument('backup')
    create.add_argument('--quiesced', action='store_true')
    restore = commands.add_parser('restore')
    restore.add_argument('backup'); restore.add_argument('destination')
    args = parser.parse_args()
    try:
        result = (backup_catalog(args.catalog, args.backup, quiesced=args.quiesced)
                  if args.command == 'backup' else restore_catalog(args.backup, args.destination))
    except (StorageTransferError, OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
