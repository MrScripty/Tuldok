"""PostgreSQL catalog lifetime, schema and transaction ownership.

Domain owners use native PostgreSQL SQL. A session advisory lock serializes
catalog commands (including file publication) across independent connections;
transactions explicitly bound atomic changes and nested savepoints. Reads do
not leave implicit transactions open. This is not a second domain repository.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

SCHEMA_VERSION = 10
SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
MANIFEST = '.tuldok.json'
CATALOG_LOCAL_TIMEOUT = 60
_COMMAND_DEADLINE = ContextVar('tuldok_metadata_command_deadline', default=None)
CATALOG_VERSION_DDL = '''CREATE TABLE catalog_version (
    version INTEGER PRIMARY KEY, dataset_id TEXT NOT NULL,
    definition_sha256 TEXT NOT NULL, catalog_sha256 TEXT NOT NULL)'''


class StorageError(ValueError):
    """Unavailable, unsupported or inconsistent local catalog configuration."""


class CommitOutcomeUnknown(StorageError):
    """Commit response lost: retain files and resolve the saved receipt after reopen."""


class CatalogBusy(StorageError):
    """Local command ownership timed out; no catalog command was dispatched."""


class Row(tuple):
    def __new__(cls, values, columns):
        row = super().__new__(cls, values)
        row.columns = columns
        return row

    def keys(self):
        return self.columns

    def __getitem__(self, key):
        return super().__getitem__(self.columns.index(key) if isinstance(key, str) else key)


def row_factory(cursor):
    columns = tuple(column.name for column in cursor.description or ())
    return lambda values: Row(values, columns)


def connection_info(dsn=None):
    """Require explicit local configuration; never log passwords or conninfo."""
    dsn = dsn or os.environ.get('TULDOK_DATABASE_URL')
    if not dsn:
        raise StorageError('Set TULDOK_DATABASE_URL for your local PostgreSQL database; see docs/contracts/local-storage.md.')
    try:
        info = conninfo_to_dict(dsn)
    except psycopg.Error:
        raise StorageError('Invalid PostgreSQL connection configuration.') from None
    # Do not permit service files or ambient PGHOST to widen the local boundary.
    if info.get('service') or not info.get('dbname') or not info.get('host'):
        raise StorageError('PostgreSQL configuration must explicitly name a local host/socket and database.')
    for host in [*info['host'].split(','), *info.get('hostaddr', '').split(',')]:
        if not host:
            continue
        if host.startswith('/') or host == 'localhost':
            continue
        try:
            if ipaddress.ip_address(host).is_loopback:
                continue
        except ValueError:
            pass
        raise StorageError('Tuldok currently supports local PostgreSQL sockets or loopback addresses only.')
    if os.environ.get('PGHOSTADDR') or os.environ.get('PGSERVICE'):
        raise StorageError('Unset ambient PGHOSTADDR and PGSERVICE; use explicit local PostgreSQL configuration.')
    if info['host'] == 'localhost' and not info.get('hostaddr'):
        info['hostaddr'] = '127.0.0.1'
    info.setdefault('connect_timeout', '5')
    # A failed/lost server operation must return, not keep the UI blocked forever.
    info['options'] = '-c statement_timeout=60000 -c lock_timeout=15000'
    return psycopg.conninfo.make_conninfo(**info)


def _key(value):
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big', signed=True)


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _publish_manifest(path, value, *, initial_mode=None):
    temporary = path.with_suffix(path.suffix + '.tmp')
    if initial_mode is None:
        handle = temporary.open('w')
    else:
        if os.path.lexists(path):
            raise StorageError('New catalog manifest already exists.')
        handle = os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                   0o666), 'w')
    with handle:
        if initial_mode is not None:
            created = os.fstat(handle.fileno())
            if not stat.S_ISREG(created.st_mode) or created.st_uid != os.getuid() or created.st_nlink != 1:
                raise StorageError('New catalog manifest creation identity changed.')
            os.fchmod(handle.fileno(), initial_mode)
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _sync_directory(path.parent)


class CatalogLock:
    """Reentrant thread and cross-process command ownership, no implicit commit."""
    def __init__(self, metadata):
        self.metadata = metadata
        self.mutex = threading.RLock()
        self.depth = 0

    def __enter__(self):
        if not self.mutex.acquire(timeout=CATALOG_LOCAL_TIMEOUT):
            raise CatalogBusy('Catalog command ownership did not become available within its local wait bound.')
        try:
            if not self.depth:
                self.metadata.connection.execute('SELECT pg_advisory_lock(%s)', (self.metadata._lock_key,))
            self.depth += 1
            return self
        except BaseException:
            self.mutex.release()
            raise

    def __exit__(self, kind, error, tb):
        self.depth -= 1
        try:
            if not self.depth and not self.metadata.connection.closed:
                try:
                    self.metadata.connection.execute('SELECT pg_advisory_unlock(%s)', (self.metadata._lock_key,))
                except BaseException:
                    self.metadata._lock_release_unknown = True
                    if error is None:
                        raise
        finally:
            self.mutex.release()

    @contextmanager
    def bounded(self, deadline, cancelled=None):
        """Recovery acquires local ownership with a deadline and never waits for a peer backend."""
        while not self.mutex.acquire(timeout=min(.1, max(0, deadline-time.monotonic()))):
            if (cancelled and cancelled()) or time.monotonic() >= deadline:
                raise StorageError('Catalog command ownership did not become available within the recovery deadline.')
        entered = False
        primary = None
        try:
            if (cancelled and cancelled()) or time.monotonic() >= deadline:
                raise StorageError('Catalog command ownership was cancelled or reached its deadline.')
            if not self.depth and not self.metadata.connection.execute(
                    'SELECT pg_try_advisory_lock(%s)', (self.metadata._lock_key,)).fetchone()[0]:
                raise StorageError('A peer still owns the catalog command lock; recovery remains fenced.')
            self.depth += 1
            entered = True
            yield self
        except BaseException as error:
            primary = error
            raise
        finally:
            if entered:
                self.__exit__(type(primary), primary, primary.__traceback__ if primary else None)
            else:
                self.mutex.release()


class Metadata:
    def __init__(self, path, dsn=None, *, create=True, dataset_id=None,
                 schema_version=SCHEMA_VERSION, initial_file_modes=None, projection_id=None):
        # Version selection belongs to offline transfer/upgrade tools. Runtime
        # callers omit it and require the current schema, never auto-upgrade.
        if schema_version is not None and (type(schema_version) is not int or
                                           schema_version not in SUPPORTED_SCHEMA_VERSIONS):
            raise StorageError('Unsupported PostgreSQL catalog version.')
        if projection_id is not None and (type(projection_id) is not str or
                not re.fullmatch('[a-f0-9]{32}', projection_id)):
            raise StorageError('Invalid local project projection identity.')
        path = Path(path).resolve()
        if create:
            path.mkdir(parents=True, exist_ok=True)
        if initial_file_modes is not None:
            if (not create or type(initial_file_modes) is not dict or
                    set(initial_file_modes) not in ({MANIFEST}, {MANIFEST, '.metadata-init.lock'}) or
                    any(type(mode) is not int or not 0 <= mode <= 0o7777
                        for mode in initial_file_modes.values())):
                raise StorageError('Unsupported new catalog file permissions.')
            initial_file_modes = dict(initial_file_modes)
            if '.metadata-init.lock' in initial_file_modes:
                if any(os.path.lexists(path / name) for name in
                       (MANIFEST, '.metadata-init.lock', '.tuldok-initializing.json')):
                    raise StorageError('New catalog initialization files already exist.')
                guard = os.fdopen(os.open(path / '.metadata-init.lock',
                                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666), 'w')
            else:
                if os.path.lexists(path / MANIFEST) or not os.path.lexists(path / '.tuldok-initializing.json'):
                    raise StorageError('Missing supported pending catalog initialization.')
                guard = os.fdopen(os.open(path / '.metadata-init.lock',
                                         os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW), 'a')
        else:
            guard = (path / '.metadata-init.lock').open('a')
        with guard:
            if initial_file_modes is not None:
                created = os.fstat(guard.fileno())
                if not stat.S_ISREG(created.st_mode) or created.st_uid != os.getuid() or created.st_nlink != 1:
                    raise StorageError('New catalog lock creation identity changed.')
                if '.metadata-init.lock' in initial_file_modes:
                    os.fchmod(guard.fileno(), initial_file_modes['.metadata-init.lock'])
                    os.fsync(guard.fileno())
            fcntl.flock(guard, fcntl.LOCK_EX)
            self._initialize(path, dsn, create=create, dataset_id=dataset_id,
                             schema_version=schema_version, initial_file_modes=initial_file_modes,
                             projection_id=projection_id)

    def _initialize(self, path, dsn=None, *, create=True, dataset_id=None,
                    schema_version=SCHEMA_VERSION, initial_file_modes=None, projection_id=None):
        self.path = Path(path).resolve()
        self.schema_version = SCHEMA_VERSION if schema_version is None else schema_version
        self.dsn = connection_info(dsn)
        manifest = self.path / MANIFEST
        pending = self.path / '.tuldok-initializing.json'
        self._rollback = []
        self._commit = []
        self._project_before_commit = None
        self._project_outcome = None
        self._runtime_claims = {}
        if initial_file_modes is not None and (os.path.lexists(manifest) or
                ('.metadata-init.lock' in initial_file_modes and os.path.lexists(pending))):
            raise StorageError('New catalog initialization files already exist.')
        if manifest.exists():
            try:
                value = json.loads(manifest.read_text())
                identity = value['dataset_id']
                expected = {'version': 1, 'dataset_id': identity} if projection_id is None else {
                    'version': 2, 'dataset_id': identity, 'projection_id': projection_id}
                if value != expected or uuid.UUID(hex=identity).hex != identity:
                    raise ValueError()
                if dataset_id is not None and dataset_id != identity:
                    raise ValueError()
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                raise StorageError('Unsupported or malformed dataset identity manifest.') from None
        else:
            if not create:
                raise StorageError('Dataset identity manifest is missing.')
            if (self.path / 'dataset.sqlite3').exists():
                raise StorageError('Legacy SQLite dataset detected. Use migrate_sqlite.py with an untouched complete backup and a new destination.')
            if pending.exists():
                try:
                    reservation = json.loads(pending.read_text())
                    identity = reservation['dataset_id']
                    expected = {'version': 1, 'dataset_id': identity,
                                'definition_sha256': definition_hash(self.schema_version)}
                    if projection_id is not None:
                        expected.update(version=2, projection_id=projection_id)
                    if reservation != expected:
                        raise ValueError()
                    if dataset_id is not None and identity != dataset_id:
                        raise ValueError()
                except (OSError, ValueError, KeyError, TypeError):
                    raise StorageError('Unsupported interrupted catalog initialization.') from None
            else:
                identity = dataset_id or uuid.uuid4().hex
            if not isinstance(identity, str) or uuid.UUID(hex=identity).hex != identity:
                raise StorageError('Invalid dataset identity.')
        self.dataset_id = identity
        # Portable logical identity participates in domain hashes. A project
        # checkout's disposable physical projection must never alias another
        # checkout or machine merely because it has the same project UUID.
        self.projection_id = projection_id
        self.schema = ('catalog_' + identity if projection_id is None else
                       'projection_' + projection_id)
        self._lock_key = _key(self.schema)
        try:
            self.connection = psycopg.connect(self.dsn, autocommit=True, row_factory=row_factory)
        except psycopg.Error:
            raise StorageError('Local PostgreSQL is unavailable. Check its service, database and credentials.') from None
        self.lock = CatalogLock(self)
        try:
            if any(self.connection.info.parameter_status(name) != 'UTF8' for name in ('server_encoding', 'client_encoding')):
                raise StorageError('Tuldok requires UTF8 PostgreSQL server and client encoding to preserve exact text.')
            if not 160000 <= self.connection.info.server_version < 190000:
                raise StorageError('Supported PostgreSQL server versions are 16 through 18.')
            with self.lock:
                exists = self.connection.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s', (self.schema,)).fetchone()
                if exists and not manifest.exists() and not pending.exists():
                    raise StorageError('Destination catalog already exists; refuse adopting it without its dataset manifest.')
                if not manifest.exists() and not pending.exists():
                    with pending.open('x') as handle:
                        reservation = {'version': 1, 'dataset_id': identity,
                                       'definition_sha256': definition_hash(self.schema_version)}
                        if projection_id is not None:
                            reservation.update(version=2, projection_id=projection_id)
                        json.dump(reservation, handle)
                        handle.flush()
                        os.fsync(handle.fileno())
                    _sync_directory(self.path)
                if not exists:
                    if manifest.exists():
                        raise StorageError('Dataset manifest exists but its PostgreSQL catalog is missing; restore the complete backup.')
                    if not create:
                        raise StorageError('Dataset catalog is missing from the configured database.')
                    with self.connection.transaction():
                        self.connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
                        self._search_path()
                        for statement in self.tables.values():
                            self.connection.execute(statement)
                        for statement in INDEXES:
                            self.connection.execute(statement)
                        self.connection.execute(CATALOG_VERSION_DDL)
                        signature = self._signature()
                        self.connection.execute('INSERT INTO catalog_version VALUES (%s,%s,%s,%s)',
                                                (self.schema_version, identity, definition_hash(self.schema_version), signature))
                else:
                    self._search_path()
                    if schema_version is None:
                        try:
                            versions = self.execute('SELECT version FROM catalog_version').fetchall()
                            if len(versions) != 1 or versions[0][0] not in SUPPORTED_SCHEMA_VERSIONS:
                                raise StorageError('Unsupported PostgreSQL catalog version.')
                            self.schema_version = versions[0][0]
                        except psycopg.Error:
                            raise StorageError('Unsupported PostgreSQL catalog schema or version ledger.') from None
                self.validate_schema()
                if not manifest.exists():
                    if any(self.execute(sql.SQL('SELECT 1 FROM {} LIMIT 1').format(sql.Identifier(table))).fetchone()
                           for table in self.tables):
                        raise StorageError('Interrupted catalog initialization contains unexpected application rows.')
                    if initial_file_modes is None:
                        value = {'version': 1, 'dataset_id': identity} if projection_id is None else {
                            'version': 2, 'dataset_id': identity, 'projection_id': projection_id}
                        _publish_manifest(manifest, value)
                    else:
                        value = {'version': 1, 'dataset_id': identity} if projection_id is None else {
                            'version': 2, 'dataset_id': identity, 'projection_id': projection_id}
                        _publish_manifest(manifest, value,
                                          initial_mode=initial_file_modes[MANIFEST])
                if pending.exists():
                    pending.unlink()
                    _sync_directory(self.path)
        except BaseException:
            self.connection.close()
            raise

    def _search_path(self):
        self.connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(self.schema)))

    @property
    def tables(self):
        return tables_for_version(self.schema_version)

    def execute(self, statement, parameters=None):
        if parameters is not None and any(isinstance(value, str) and '\x00' in value for value in parameters):
            raise StorageError('PostgreSQL text cannot contain NUL. Input was not saved; no characters were stripped.')
        bounded = _COMMAND_DEADLINE.get()
        if bounded is not None and bounded[0] is self:
            remaining = bounded[1] - time.monotonic()
            if remaining <= 0:
                raise StorageError('Catalog command reached its recovery deadline.')
            self.connection.execute("SELECT set_config('statement_timeout',%s,false)",
                                    (str(max(1, int(remaining*1000))),))
        return self.connection.execute(statement, parameters)

    @contextmanager
    def commands_before(self, deadline):
        """Bound each recovery SQL command by the remaining shared wall budget.

        The caller retains CatalogLock throughout, so session settings cannot
        leak into another operation. Native transaction completion remains under
        the last remaining budget; the ordinary timeout is restored afterward.
        """
        if not self.lock.depth:
            raise RuntimeError('A command deadline requires exclusive catalog ownership.')
        old = self.connection.execute('SHOW statement_timeout').fetchone()[0]
        marker = _COMMAND_DEADLINE.set((self, deadline))
        primary = None
        try:
            yield
        except BaseException as error:
            primary = error
            raise
        finally:
            _COMMAND_DEADLINE.reset(marker)
            if not self.connection.closed:
                try:
                    self.connection.execute("SELECT set_config('statement_timeout',%s,false)", (old,))
                    self._command_cleanup_fault = False
                except BaseException:
                    self._command_cleanup_fault = True
                    if primary is None:
                        raise

    @contextmanager
    def transaction(self, *, force_rollback=False):
        """One outer commit; nested calls own savepoints and rollback cleanups."""
        with self.lock:
            callbacks = []
            self._rollback.append(callbacks)
            committed = []
            self._commit.append(committed)
            outermost = len(self._rollback) == 1
            body_failed = False
            try:
                try:
                    with self.connection.transaction(force_rollback=force_rollback):
                        try:
                            yield self
                            if outermost and not force_rollback and self._project_before_commit is not None:
                                self._project_before_commit()
                        except BaseException:
                            body_failed = True
                            raise
                finally:
                    # Outcome hooks and wakes observe the completed SQL scope.
                    # In particular an on_commit wake must not re-enroll itself
                    # into the callback list that is currently being drained.
                    self._rollback.pop()
                    self._commit.pop()
            except BaseException as error:
                confirmed_failure = getattr(error, 'sqlstate', '') or ''
                if body_failed or force_rollback or confirmed_failure[:2] in ('23', '40'):
                    if outermost and self._project_outcome is not None:
                        self._project_outcome('rolled_back')
                    for callback in reversed(callbacks):
                        callback()
                    raise
                # A lost COMMIT response never authorizes cleanup or a wake.
                if outermost and self._project_outcome is not None:
                    self._project_outcome('unknown')
                raise CommitOutcomeUnknown(
                    'PostgreSQL commit acknowledgement was lost. Files were retained; reopen and inspect the saved result before retrying.') from error
            else:
                if force_rollback:
                    if outermost and self._project_outcome is not None:
                        self._project_outcome('rolled_back')
                    for callback in reversed(callbacks):
                        callback()
                elif not outermost:
                    self._rollback[-1].extend(callbacks)
                    self._commit[-1].extend(committed)
                else:
                    if self._project_outcome is not None:
                        self._project_outcome('committed')
                    for callback in committed:
                        callback()

    def set_project_hooks(self, before_commit, outcome):
        """Install one fixed project durability owner, before any worker starts.

        Hooks belong to this physical projection, never to the process or an
        imported catalog. They run only at the outer transaction boundary.
        """
        with self.lock:
            if self.in_transaction:
                raise RuntimeError('Project hooks cannot change during a transaction.')
            if not callable(before_commit) or not callable(outcome):
                raise TypeError('Project transaction hooks must be callable.')
            if self._project_before_commit is not None:
                raise RuntimeError('Project transaction hooks already have an owner.')
            self._project_before_commit, self._project_outcome = before_commit, outcome

    @property
    def in_transaction(self):
        return bool(self._rollback)

    def on_rollback(self, callback):
        if not self._rollback:
            raise RuntimeError('Filesystem rollback must belong to a metadata transaction.')
        self._rollback[-1].append(callback)

    def on_commit(self, callback):
        if not self._commit:
            raise RuntimeError('Filesystem publication must belong to a metadata transaction.')
        self._commit[-1].append(callback)

    def claim_runtime(self, name):
        """Single worker supervisor per catalog; reopening never interrupts a peer."""
        with self.lock:
            if name not in self._runtime_claims:
                self._runtime_claims[name] = bool(self.execute('SELECT pg_try_advisory_lock(%s)',
                    (_key(self.schema + ':worker:' + name),)).fetchone()[0])
            return self._runtime_claims[name]

    def runtime_owned(self, name):
        """Observe this session's existing lock without stacking or claiming a peer's lock."""
        if self.connection.closed or getattr(self, '_lock_release_unknown', False) or not self._runtime_claims.get(name):
            return False
        key = _key(self.schema + ':worker:' + name) & ((1 << 64) - 1)
        return bool(self.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' "
            "AND pid=pg_backend_pid() AND granted AND objsubid=1 AND classid=%s::oid AND objid=%s::oid)",
            (key >> 32, key & 0xffffffff)).fetchone()[0])

    def _signature(self, schema=None):
        """Catalog structures, not formatted CREATE strings, detect unsupported drift."""
        schema = schema or self.schema
        values = []
        queries = [
            '''SELECT c.relname,a.attname,a.atttypid::regtype::text,a.attnotnull,
                      pg_get_expr(d.adbin,d.adrelid),a.attidentity
               FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               JOIN pg_attribute a ON a.attrelid=c.oid
               LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
               WHERE n.nspname=%s AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped
               ORDER BY c.relname,a.attnum''',
            '''SELECT c.relname,k.contype,pg_get_constraintdef(k.oid)
               FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
               JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s
               ORDER BY c.relname,k.conname''',
            '''SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname=%s ORDER BY tablename,indexname''',
            '''SELECT c.relname,t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
               JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND NOT t.tgisinternal ORDER BY c.relname,t.tgname''',
            '''SELECT c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=%s ORDER BY c.relname''',
        ]
        for query in queries:
            values.append([list(row) for row in self.execute(query, (schema,))])
        return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(',', ':')).replace(schema, '<catalog>').encode()).hexdigest()

    def expected_signature(self, version):
        """Derive the accepted structure independently of a possibly edited ledger.

        An always-rolled-back reference schema uses this server's formatting, so
        verification does not pin pg_get_constraintdef output across server majors.
        Call only from quiesced schema evolution under the catalog transaction.
        """
        if not self.in_transaction:
            raise RuntimeError('Schema proof must belong to a metadata transaction.')
        tables = tables_for_version(version)
        reference = 'tuldok_schema_proof_' + uuid.uuid4().hex
        with self.connection.transaction(force_rollback=True):
            self.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(reference)))
            self.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(reference)))
            for statement in tables.values():
                self.execute(statement)
            for statement in INDEXES:
                self.execute(statement)
            self.execute(CATALOG_VERSION_DDL)
            signature = self._signature(reference)
        return signature

    def validate_schema(self):
        try:
            rows = self.execute('SELECT version,dataset_id,definition_sha256,catalog_sha256 FROM catalog_version').fetchall()
            if (len(rows) == 1 and rows[0][0] in SUPPORTED_SCHEMA_VERSIONS
                    and rows[0][0] < self.schema_version):
                raise StorageError(f'PostgreSQL catalog schema {rows[0][0]} requires an explicit upgrade. Stop all writers, back up the catalog, then run upgrade_metadata.py CATALOG --quiesced; see docs/contracts/workspace-storage.md.')
            if len(rows) != 1 or tuple(rows[0][:3]) != (self.schema_version, self.dataset_id, definition_hash(self.schema_version)):
                raise StorageError('Unsupported PostgreSQL catalog version or definition.')
            if rows[0][3] != self._signature():
                raise StorageError('Unsupported PostgreSQL catalog schema, constraints, indexes or triggers.')
        except psycopg.Error:
            raise StorageError('Unsupported PostgreSQL catalog schema or version ledger.') from None

    def commit(self):
        if self._rollback:
            raise RuntimeError('Transaction commits belong to transaction() scopes.')
        self.connection.commit()

    def rollback(self):
        if self._rollback:
            raise RuntimeError('Transaction rollbacks belong to transaction() scopes.')
        self.connection.rollback()

    def close(self):
        self.connection.close()


INDEXES = (
    'CREATE INDEX workbench_content ON workbench_records(content_hash)',
    'CREATE INDEX workbench_response_prompt ON workbench_responses(prompt_id)',
    'CREATE INDEX workbench_preference_prompt ON workbench_preferences(prompt_id)',
)


def tables_for_version(version):
    if type(version) is not int or version not in SUPPORTED_SCHEMA_VERSIONS:
        raise StorageError('Unsupported PostgreSQL catalog version.')
    return {1: TABLES_V1, 2: TABLES_V2, 3: TABLES_V3, 4: TABLES_V4, 5: TABLES_V5, 6: TABLES_V6, 7: TABLES_V7, 8: TABLES_V8, 9: TABLES_V9, 10: TABLES}[version]


def definition_hash(version=SCHEMA_VERSION):
    return hashlib.sha256(json.dumps([version, tables_for_version(version), INDEXES], sort_keys=True).encode()).hexdigest()


# Schema 1 is the exact retained MB contract, including DDL whitespace because
# its definition hash is part of the persisted version ledger.
TABLES_V1 = {
    'samples': """CREATE TABLE samples (
            id TEXT PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, filename TEXT NOT NULL,
            width INTEGER NOT NULL, height INTEGER NOT NULL,
            book_id TEXT NOT NULL, session_id TEXT NOT NULL, split TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, annotation TEXT)""",
    'workbench_records': """CREATE TABLE workbench_records (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('image','text','sequence','mesh')),
                name TEXT, text TEXT, original_text TEXT,
                content_hash TEXT NOT NULL, pixel_hash TEXT,
                groups_json TEXT NOT NULL, parents_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL, task TEXT NOT NULL,
                annotation_json TEXT, review TEXT NOT NULL,
                revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    'workbench_history': """CREATE TABLE workbench_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id, revision))""",
    'workbench_rights_notes': """CREATE TABLE workbench_rights_notes (
                id TEXT PRIMARY KEY, note TEXT NOT NULL, revision INTEGER NOT NULL)""",
    'workbench_target_proposals': """CREATE TABLE workbench_target_proposals (id TEXT PRIMARY KEY, evidence TEXT NOT NULL)""",
    'workbench_responses': """CREATE TABLE workbench_responses (
                id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, revision INTEGER NOT NULL,
                completion TEXT NOT NULL, review TEXT NOT NULL, provenance_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    'workbench_response_history': """CREATE TABLE workbench_response_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id,revision))""",
    'workbench_deleted_sources': """CREATE TABLE workbench_deleted_sources (
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL, session_id TEXT NOT NULL,
                split TEXT NOT NULL)""",
    'workbench_preferences': """CREATE TABLE workbench_preferences (
                id TEXT PRIMARY KEY, prompt_id TEXT NOT NULL, revision INTEGER NOT NULL,
                data TEXT NOT NULL)""",
    'workbench_preference_history': """CREATE TABLE workbench_preference_history (
                id TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
                PRIMARY KEY(id,revision))""",
    'saved_selections': """CREATE TABLE saved_selections (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,
                members_json TEXT NOT NULL, member_count INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    'saved_searches': """CREATE TABLE saved_searches (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, revision INTEGER NOT NULL,
    criteria_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    'generation_jobs': """CREATE TABLE generation_jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, ordinal BIGINT GENERATED BY DEFAULT AS IDENTITY UNIQUE)""",
    'generation_entries': """CREATE TABLE generation_entries (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, data TEXT NOT NULL, UNIQUE(job_id, ordinal), storage_order BIGINT GENERATED BY DEFAULT AS IDENTITY UNIQUE)""",
    'grounded_jobs': """CREATE TABLE grounded_jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL, ordinal BIGINT GENERATED BY DEFAULT AS IDENTITY UNIQUE)""",
    'caption_proposals': """CREATE TABLE caption_proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL, ordinal BIGINT GENERATED BY DEFAULT AS IDENTITY UNIQUE)""",
    'text_classification_proposals': """CREATE TABLE text_classification_proposals (id TEXT PRIMARY KEY, data TEXT NOT NULL, ordinal BIGINT GENERATED BY DEFAULT AS IDENTITY UNIQUE)""",
    'workbench_sequence_assets': """CREATE TABLE workbench_sequence_assets (
    id TEXT PRIMARY KEY, bundle BYTEA NOT NULL, metadata_json TEXT NOT NULL,
    bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))""",
    'workbench_mesh_assets': """CREATE TABLE workbench_mesh_assets (
    id TEXT PRIMARY KEY, bundle BYTEA NOT NULL, metadata_json TEXT NOT NULL,
    bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))""",
}

WORKSPACE_TABLES = {
    'workspace_graphs': '''CREATE TABLE workspace_graphs (
        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL)''',
    'workspace_runs': '''CREATE TABLE workspace_runs (
        id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
        request_sha256 TEXT NOT NULL, document TEXT NOT NULL)''',
    'workspace_exposures': '''CREATE TABLE workspace_exposures (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL, source_hash TEXT NOT NULL,
        reason TEXT NOT NULL, run_id TEXT NOT NULL, release_id TEXT NOT NULL,
        created_at TEXT NOT NULL)''',
}
# Retained schema 2 is the exact M2 contract. Do not edit either old definition:
# their DDL hashes identify existing catalogs and retained backup receipts.
TABLES_V2 = {**TABLES_V1, **WORKSPACE_TABLES}
TABLES_V3 = {
    **TABLES_V2,
    'workbench_records': """CREATE TABLE workbench_records (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('image','text','sequence','mesh','audio')),
                name TEXT, text TEXT, original_text TEXT,
                content_hash TEXT NOT NULL, pixel_hash TEXT,
                groups_json TEXT NOT NULL, parents_json TEXT NOT NULL,
                provenance_json TEXT NOT NULL, task TEXT NOT NULL,
                annotation_json TEXT, review TEXT NOT NULL,
                revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
}

# Schema 3's exact DDL above remains an immutable backup/upgrade identity.
SPATIAL_TABLES = {
    'workbench_pointcloud_assets': """CREATE TABLE workbench_pointcloud_assets (
    id TEXT PRIMARY KEY, bundle BYTEA NOT NULL, metadata_json TEXT NOT NULL,
    bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))""",
    'workbench_volume_assets': """CREATE TABLE workbench_volume_assets (
    id TEXT PRIMARY KEY, bundle BYTEA NOT NULL, metadata_json TEXT NOT NULL,
    bundle_bytes INTEGER NOT NULL CHECK(bundle_bytes > 0))""",
}
TABLES_V4 = {
    **TABLES_V3, **SPATIAL_TABLES,
    'workbench_records': TABLES_V3['workbench_records'].replace(
        "'sequence','mesh','audio'", "'sequence','mesh','audio','pointcloud','volume'"),
}

# Retained schema 4 remains exact for old catalogs, receipts and explicit upgrades.
PROJECT_TABLES = {
    'workspace_projects': '''CREATE TABLE workspace_projects (
        id TEXT PRIMARY KEY, document TEXT NOT NULL)''',
}
TABLES_V5 = {**TABLES_V4, **PROJECT_TABLES}
# The scientific source lives in the existing local artifact tree, not a new table.
TABLES_V6 = {
    **TABLES_V5,
    'workbench_records': TABLES_V5['workbench_records'].replace(
        "'pointcloud','volume'", "'pointcloud','volume','field_sequence'"),
}

ACCESS_TABLES = {
    'access_actors': '''CREATE TABLE access_actors (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('owner','agent')),
        label TEXT NOT NULL, created_at BIGINT NOT NULL)''',
    'access_credentials': '''CREATE TABLE access_credentials (
        id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, token_sha256 TEXT UNIQUE NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('login','session','bearer')), scopes_json TEXT NOT NULL,
        expires_at BIGINT NOT NULL, revoked INTEGER NOT NULL CHECK(revoked IN (0,1)), consumed INTEGER NOT NULL CHECK(consumed IN (0,1)), created_at BIGINT NOT NULL)''',
    'access_audit': '''CREATE TABLE access_audit (
        id TEXT PRIMARY KEY, actor_id TEXT, credential_id TEXT, action TEXT NOT NULL,
        target_json TEXT NOT NULL, details_json TEXT NOT NULL, result TEXT NOT NULL, created_at BIGINT NOT NULL)''',
    'access_admissions': '''CREATE TABLE access_admissions (
        id TEXT PRIMARY KEY, catalog_id TEXT NOT NULL, actor_id TEXT NOT NULL, credential_id TEXT NOT NULL,
        kind TEXT NOT NULL, job_id TEXT NOT NULL, request_digest TEXT NOT NULL, effects_json TEXT NOT NULL, created_at BIGINT NOT NULL)''',
}
TABLES_V7 = {**TABLES_V6, **ACCESS_TABLES}
EXECUTION_APPROVAL_TABLES = {
    'access_execution_grants': '''CREATE TABLE access_execution_grants (
        id TEXT PRIMARY KEY, catalog_id TEXT NOT NULL, approver_actor_id TEXT NOT NULL,
        approver_credential_id TEXT NOT NULL, consumer_actor_id TEXT NOT NULL, material_sha256 TEXT NOT NULL,
        created_at BIGINT NOT NULL, expires_at BIGINT NOT NULL, revoked_at BIGINT)''',
    'access_execution_consumptions': '''CREATE TABLE access_execution_consumptions (
        grant_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL, admission_id TEXT UNIQUE NOT NULL,
        consumer_credential_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, consumed_at BIGINT NOT NULL)''',
}
TABLES_V8 = {**TABLES_V7, **EXECUTION_APPROVAL_TABLES}


# Additive schema9; every prior definition remains byte-exact.
MODEL_DEVELOPMENT_TABLES = {
    'workspace_recipe_drafts': """CREATE TABLE workspace_recipe_drafts (
        id TEXT PRIMARY KEY, revision BIGINT NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
        document TEXT NOT NULL)""",
    'model_definition_drafts': """CREATE TABLE model_definition_drafts (
        id TEXT PRIMARY KEY, revision BIGINT NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
        document TEXT NOT NULL)""",
    'model_materials': """CREATE TABLE model_materials (
        id TEXT NOT NULL, revision BIGINT NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
        sha256 TEXT UNIQUE NOT NULL, document TEXT NOT NULL, PRIMARY KEY(id,revision))""",
    'workspace_recipe_materials': """CREATE TABLE workspace_recipe_materials (
        sha256 TEXT PRIMARY KEY, recipe_id TEXT NOT NULL, recipe_revision BIGINT NOT NULL CHECK(recipe_revision BETWEEN 1 AND 9007199254740991),
        document TEXT NOT NULL)""",
    'model_selection_policies': """CREATE TABLE model_selection_policies (
        id TEXT NOT NULL, revision BIGINT NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
        sha256 TEXT UNIQUE NOT NULL, document TEXT NOT NULL, PRIMARY KEY(id,revision))""",
    'model_studies': """CREATE TABLE model_studies (
        id TEXT PRIMARY KEY, revision BIGINT NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
        admission_epoch BIGINT NOT NULL CHECK(admission_epoch BETWEEN 0 AND 9007199254740991), document TEXT NOT NULL)""",
    'model_trials': """CREATE TABLE model_trials (
        id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES model_studies(id),
        material_sha256 TEXT NOT NULL REFERENCES workspace_recipe_materials(sha256),
        replicate BIGINT NOT NULL CHECK(replicate BETWEEN 0 AND 9007199254740991), document TEXT NOT NULL,
        UNIQUE(study_id,material_sha256,replicate))""",
    'model_study_memberships': """CREATE TABLE model_study_memberships (
        study_id TEXT NOT NULL REFERENCES model_studies(id), revision BIGINT NOT NULL CHECK(revision BETWEEN 1 AND 9007199254740991),
        document TEXT NOT NULL, PRIMARY KEY(study_id,revision))""",
    'model_attempt_reservations': """CREATE TABLE model_attempt_reservations (
        id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES model_studies(id), actor_id TEXT NOT NULL,
        request_key TEXT NOT NULL, request_sha256 TEXT NOT NULL, trial_id TEXT NOT NULL REFERENCES model_trials(id),
        run_id TEXT UNIQUE NOT NULL REFERENCES workspace_runs(id), document TEXT NOT NULL, UNIQUE(study_id,request_key))""",
    'model_candidates': """CREATE TABLE model_candidates (
        id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES model_studies(id),
        trial_id TEXT NOT NULL REFERENCES model_trials(id), run_id TEXT NOT NULL REFERENCES workspace_runs(id), document TEXT NOT NULL)""",
    'model_operation_receipts': """CREATE TABLE model_operation_receipts (
        actor_id TEXT NOT NULL, operation_id TEXT NOT NULL, request_key TEXT NOT NULL, request_sha256 TEXT NOT NULL,
        document TEXT NOT NULL, PRIMARY KEY(actor_id,operation_id,request_key))""",
}
TABLES_V9 = {**TABLES_V8, **MODEL_DEVELOPMENT_TABLES}

# Lineage annotates immutable trials; historical trial/material bytes stay exact.
EXPERIMENT_LINEAGE_TABLES = {
    'model_trial_lineage': """CREATE TABLE model_trial_lineage (
        trial_id TEXT PRIMARY KEY REFERENCES model_trials(id),
        parent_trial_id TEXT REFERENCES model_trials(id),
        baseline_trial_id TEXT REFERENCES model_trials(id), document TEXT NOT NULL,
        CHECK(parent_trial_id IS NULL OR parent_trial_id <> trial_id),
        CHECK(baseline_trial_id IS NULL OR baseline_trial_id <> trial_id))""",
}
TABLES = {**TABLES_V9, **EXPERIMENT_LINEAGE_TABLES}
