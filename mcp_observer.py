"""Operator-only opt-in MCP observations, separate from domain PostgreSQL.

Adapted from MrScripty/Coding-Standards (CC0-1.0), interaction_observer.py at
4887b7aff0ba84acd257da081135b7849cc9c79f. See docs/contracts/mcp-observer.md.
Only closed structural projections reach SQLite; no request/output scalar values.
"""
import argparse
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
import uuid

SCHEMA_VERSION = 1
APPLICATION_ID = 0x544F4253  # TOBS; never a domain store or the reference store.
DEFAULT_MAX_CALLS = 10_000
DEFAULT_MAX_AGE_SECONDS = 604800
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
BUSY_TIMEOUT_MS = 20
MAX_ACTIVE = 2  # One admitted SDK request plus one direct admission refusal.
MAX_FIELDS = 64
MAX_SHAPE_BYTES = 8192
METHODS = frozenset({'initialize', 'tools/list', 'tools/call', 'ping'})
PHASES = frozenset({'admitted', 'validated', 'dispatch', 'returned', 'terminal'})
OUTCOMES = frozenset({'pending', 'response', 'success', 'permission-refusal',
    'domain-error', 'transport-error', 'registry-refusal', 'call-error',
    'bridge-error', 'parse-error', 'invalid-request', 'unsupported-method',
    'invalid-parameters', 'busy-or-not-ready', 'protocol-error', 'response-too-large', 'unknown'})
SENSITIVE_FIELDS = frozenset({'annotation', 'document', 'files', 'inputs',
    'parameters', 'text', 'image', 'audio', 'data', 'content', 'body', 'prompt',
    'source', 'metadata', 'environment', 'token', 'password', 'secret', '_meta'})
SCHEMA_DDL = (
    'CREATE TABLE policy (id INTEGER PRIMARY KEY CHECK(id=1), max_calls INTEGER NOT NULL, max_age_seconds INTEGER NOT NULL, max_bytes INTEGER NOT NULL)',
    'CREATE TABLE sessions (id TEXT PRIMARY KEY, started REAL NOT NULL, registry_version INTEGER NOT NULL, registry_digest TEXT NOT NULL, implementation_digest TEXT NOT NULL, protocol TEXT NOT NULL)',
    'CREATE TABLE interactions (id TEXT PRIMARY KEY, session TEXT NOT NULL REFERENCES sessions(id), ordinal INTEGER NOT NULL, started REAL NOT NULL, method TEXT NOT NULL, operation TEXT NOT NULL, operation_id TEXT NOT NULL, input_schema TEXT NOT NULL, output_schema TEXT NOT NULL, request_bytes INTEGER NOT NULL, input_shape TEXT NOT NULL, UNIQUE(session,ordinal))',
    "CREATE TABLE events (interaction TEXT NOT NULL REFERENCES interactions(id) ON DELETE CASCADE, phase TEXT NOT NULL CHECK(phase IN ('admitted','validated','dispatch','returned','terminal')), recorded REAL NOT NULL, duration_ms REAL NOT NULL, outcome TEXT NOT NULL, envelope_status INTEGER, http_status INTEGER, rpc_code INTEGER, response_bytes INTEGER, delivery TEXT NOT NULL CHECK(delivery IN ('pending','written','incomplete')), PRIMARY KEY(interaction,phase))",
    'CREATE INDEX interaction_age ON interactions(started)',
)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def _kind(value):
    if value is None: return 'null'
    if type(value) is bool: return 'boolean'
    if isinstance(value, str): return 'string'
    if type(value) in (int, float): return 'number'
    if isinstance(value, dict): return 'object'
    if isinstance(value, list): return 'array'
    return 'unknown'


def input_shape(schema, value):
    """Exact top-level schema names only; no recursion or scalar retention."""
    if not isinstance(value, dict):
        return {'type': _kind(value)}
    fields, known = {}, 0
    properties = schema.get('properties', {})
    for name, definition in properties.items():
        if name in value:
            known += 1
            if len(fields) < MAX_FIELDS:
                item = value[name]
                fields[name] = ('redacted' if name in SENSITIVE_FIELDS else
                    {'type': _kind(item), **({'size': min(len(item), 1024 * 1024)}
                     if isinstance(item, (str, list, dict)) else {})})
    result = {'type': 'object', 'fields': fields, 'unknown_fields': len(value) - known,
              'truncated': known > len(fields)}
    return result if len(_json(result)) <= MAX_SHAPE_BYTES else {'type': 'object', 'truncated': True}


@dataclass(frozen=True)
class RecorderConfig:
    database: Path
    max_calls: int = DEFAULT_MAX_CALLS
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES

    def __post_init__(self):
        if not isinstance(self.database, Path) or not self.database.is_absolute():
            raise ValueError('invalid-observer-configuration')
        for value, low, high in ((self.max_calls, 16, 100000),
                                (self.max_age_seconds, 60, 31536000),
                                (self.max_bytes, 1048576, 1073741824)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('invalid-observer-configuration')


@dataclass(frozen=True)
class Observation:
    identity: str
    started: float


class StorageRejected(Exception):
    """Internal fixed reason, never a raw SQLite/OS exception."""


def _check_private(path, directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077
            or (not directory and info.st_nlink != 1)):
        raise StorageRejected('unsafe-storage')
    return info


def _connect(config, *, readonly=False, exclusive=False, create=False):
    """Own the process lock until connection closes; callers own trusted ancestors."""
    path = config.database
    if os.name != 'posix':
        raise StorageRejected('unsupported-filesystem')
    _check_private(path.parent, directory=True)
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = Path(str(path) + suffix)
        if os.path.lexists(sidecar):
            _check_private(sidecar)
            if suffix != '-journal':
                raise StorageRejected('unsupported-journal-mode')
    fd = os.open(path, (os.O_RDONLY if readonly else os.O_RDWR) | (os.O_CREAT if create else 0)
                 | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    db = None
    try:
        info = _check_private(path)
        opened = os.fstat(fd)
        if (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise StorageRejected('unsafe-storage')
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        db = sqlite3.connect(path.as_uri() + '?mode=' + ('ro' if readonly else 'rw'),
            uri=True, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute(f'PRAGMA busy_timeout={BUSY_TIMEOUT_MS}')
        if readonly:
            db.execute('PRAGMA query_only=ON')
        return db, fd, opened.st_size
    except BaseException:
        if db is not None: db.close()
        os.close(fd)
        raise


def _validate_schema(db):
    if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or
            db.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION):
        raise StorageRejected('unsupported-database-schema')
    actual = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
    if actual != {ddl.split()[2]: ddl for ddl in SCHEMA_DDL}:
        raise StorageRejected('invalid-database-schema')


def _read_policy(db, database):
    rows = db.execute('SELECT max_calls,max_age_seconds,max_bytes FROM policy').fetchall()
    if len(rows) != 1:
        raise StorageRejected('invalid-retention-policy')
    try:
        return RecorderConfig(database, *rows[0])
    except (TypeError, ValueError):
        raise StorageRejected('invalid-retention-policy') from None


def _validate_records(db):
    if db.execute('PRAGMA quick_check(1)').fetchone() != ('ok',) or db.execute('PRAGMA foreign_key_check').fetchone():
        raise StorageRejected('invalid-database-records')


class InteractionRecorder:
    def __init__(self, config, registry, *, diagnostics=None):
        self.config = config
        self._diagnostics = sys.stderr if diagnostics is None else diagnostics
        self._connection = self._fd = None
        self._active = {}
        self._sequence = 0
        self._closed = False
        self.session = uuid.uuid4().hex
        self.health = {'state': 'starting', 'reason': None, 'starts': 0,
                       'terminals': 0, 'dropped': 0, 'pruned': 0}
        self._operations = {op['mcp_name']: op for op in registry['operations']}
        try:
            # Installed source must be coherent and immutable during startup/run.
            source = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                      for name in ('mcp_stdio.py', 'agent_api.py', 'mcp_observer.py')}
            self._runtime = (self.session, time.time(), registry['version'], registry['digest'],
                             _digest(source), '2025-06-18')
            self._open()
            self.health['state'] = 'healthy'
            self._emit()
        except Exception as error:
            self._degrade(error)

    def _emit(self):
        try:
            print('tuldok observer ' + _json(self.health), file=self._diagnostics, flush=True)
        except Exception:
            pass

    def _release(self):
        if self._connection is not None:
            try: self._connection.close()
            except Exception: pass
            self._connection = None
        if self._fd is not None:
            try: os.close(self._fd)
            except OSError: pass
            self._fd = None

    def _degrade(self, error):
        reason = 'storage-unavailable'
        if isinstance(error, StorageRejected):
            reason = str(error)  # Only internal fixed literals construct this type.
        elif isinstance(error, sqlite3.Error):
            reason = {sqlite3.SQLITE_BUSY: 'storage-locked', sqlite3.SQLITE_LOCKED: 'storage-locked',
                      sqlite3.SQLITE_FULL: 'storage-full', sqlite3.SQLITE_CORRUPT: 'storage-corrupt',
                      sqlite3.SQLITE_NOTADB: 'storage-corrupt'}.get(
                          getattr(error, 'sqlite_errorcode', 0) & 255, 'storage-error')
        self.health.update(state='degraded', reason=reason)
        self.health['dropped'] += 1
        self._release()
        self._emit()

    def _open(self):
        db, self._fd, original_size = _connect(self.config, create=True)
        self._connection = db
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise StorageRejected('unsupported-journal-mode')
            pages = self.config.max_bytes // db.execute('PRAGMA page_size').fetchone()[0]
            if db.execute('PRAGMA page_count').fetchone()[0] > pages:
                raise StorageRejected('database-over-budget')
            db.execute(f'PRAGMA max_page_count={pages}')
            if (db.execute('PRAGMA user_version').fetchone()[0] == 0 and
                    db.execute('PRAGMA application_id').fetchone()[0] == 0 and
                    not db.execute('SELECT 1 FROM sqlite_master').fetchone()):
                if original_size or self.config.database.stat().st_size:
                    raise StorageRejected('nonpristine-database')
                for ddl in SCHEMA_DDL: db.execute(ddl)
                db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
                db.execute('INSERT INTO policy VALUES(1,?,?,?)',
                    (self.config.max_calls, self.config.max_age_seconds, self.config.max_bytes))
            _validate_schema(db)
            _validate_records(db)
            if _read_policy(db, self.config.database) != self.config:
                raise StorageRejected('retention-policy-mismatch')
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK')
            raise
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA secure_delete=ON')

    def _transaction(self, action):
        if self._connection is None:
            self.health['dropped'] += 1
            return False
        try:
            self._connection.execute('BEGIN IMMEDIATE')
            action(self._connection)
            self._connection.execute('COMMIT')
            return True
        except Exception as error:
            try: self._connection.execute('ROLLBACK')
            except sqlite3.Error: pass
            self._degrade(error)
            return False

    def _prune(self, db, now):
        pruned = db.execute('DELETE FROM interactions WHERE started < ?',
            (now - self.config.max_age_seconds,)).rowcount
        excess = db.execute('SELECT max(0,count(*)-?) FROM interactions',
            (self.config.max_calls - 1,)).fetchone()[0]
        if excess:
            pruned += db.execute('DELETE FROM interactions WHERE id IN '
                '(SELECT id FROM interactions ORDER BY started,id LIMIT ?)', (excess,)).rowcount
        db.execute('DELETE FROM sessions WHERE NOT EXISTS '
                   '(SELECT 1 FROM interactions WHERE session=sessions.id)')
        return pruned

    def begin(self, message, request_bytes, *, framing=False):
        if self._closed: return None
        if self._connection is None:
            self.health['dropped'] += 1
            return None
        try:
            if len(self._active) >= MAX_ACTIVE:
                raise StorageRejected('observation-capacity')
            method = message.get('method') if isinstance(message, dict) else None
            method = method if isinstance(method, str) and method in METHODS else 'framing' if framing else 'other'
            params = message.get('params') if isinstance(message, dict) else None
            params = params if isinstance(params, dict) else {}
            name = params.get('name')
            op = self._operations.get(name) if isinstance(name, str) and method == 'tools/call' else None
            observation = Observation(uuid.uuid4().hex, time.monotonic())
            self._sequence += 1
            now, pruned = time.time(), 0
            def write(db):
                nonlocal pruned
                pruned = self._prune(db, now)
                db.execute('INSERT OR IGNORE INTO sessions VALUES(?,?,?,?,?,?)', self._runtime)
                db.execute('INSERT INTO interactions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (observation.identity, self.session, self._sequence, now, method,
                     op['mcp_name'] if op else 'other', op['operation_id'] if op else 'other',
                     _digest(op['inputSchema']) if op else '', _digest(op['outputSchema']) if op else '',
                     request_bytes, _json(input_shape(op['inputSchema'], params.get('arguments', {}))) if op else '{}'))
            if not self._transaction(write): return None
            self.health['starts'] += 1
            self.health['pruned'] += pruned
            self._active[observation.identity] = observation
            return observation
        except Exception as error:
            self._degrade(error)
            return None

    def stage(self, observation, phase, *, outcome='pending', envelope_status=None, http_status=None,
              rpc_code=None, response_bytes=None, delivery='pending'):
        if observation is None or self._closed: return
        try:
            if phase not in PHASES or outcome not in OUTCOMES or delivery not in ('pending', 'written', 'incomplete'):
                raise StorageRejected('invalid-observation')
            if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
                http_status = None
            if envelope_status is not None and (type(envelope_status) is not int or not 100 <= envelope_status <= 599):
                envelope_status = None
            if rpc_code not in (-32700, -32600, -32601, -32602, -32000, -32603):
                rpc_code = None
            if response_bytes is not None and (type(response_bytes) is not int or not 0 <= response_bytes <= 32 * 1024 * 1024):
                response_bytes = None
            evicted = False
            def write(db):
                nonlocal evicted
                if not db.execute('SELECT 1 FROM interactions WHERE id=?', (observation.identity,)).fetchone():
                    evicted = True
                    return
                db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (observation.identity, phase, time.time(), max(0, (time.monotonic() - observation.started) * 1000),
                     outcome, envelope_status, http_status, rpc_code, response_bytes, delivery))
            if self._transaction(write):
                if evicted: self.health['dropped'] += 1
                elif phase == 'terminal': self.health['terminals'] += 1
            if phase == 'terminal': self._active.pop(observation.identity, None)
        except Exception as error:
            self._degrade(error)

    def close(self):
        if self._closed: return
        for observation in tuple(self._active.values()):
            self.stage(observation, 'terminal', outcome='unknown', delivery='incomplete')
        self._closed = True
        self._release()
        self._emit()


def check_store(database, *, retain=False):
    """Basic operator integrity/persistence check; never emits stored values."""
    config = RecorderConfig(database)
    db, fd, _ = _connect(config, readonly=not retain, exclusive=retain)
    try:
        db.execute('BEGIN IMMEDIATE' if retain else 'BEGIN')
        _validate_schema(db)
        policy = _read_policy(db, database)
        _validate_records(db)
        if retain:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM interactions WHERE started < ?', (time.time() - policy.max_age_seconds,))
            db.execute('DELETE FROM interactions WHERE id IN (SELECT id FROM interactions ORDER BY started DESC,id DESC LIMIT -1 OFFSET ?)', (policy.max_calls,))
            db.execute('DELETE FROM sessions WHERE NOT EXISTS (SELECT 1 FROM interactions WHERE session=sessions.id)')
        starts = db.execute('SELECT count(*) FROM interactions').fetchone()[0]
        terminals = db.execute("SELECT count(*) FROM events WHERE phase='terminal'").fetchone()[0]
        db.execute('COMMIT')
        return {'state': 'healthy', 'schema_version': SCHEMA_VERSION, 'retained_starts': starts,
                'retained_terminals': terminals, 'unfinished': starts - terminals}
    finally:
        db.close()
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--retain', action='store_true', help='Prune an offline store under its existing policy')
    args = parser.parse_args(argv)
    try:
        print(_json(check_store(Path(args.database), retain=args.retain)))
        return 0
    except Exception:
        print('tuldok observer storage-check-unavailable', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
