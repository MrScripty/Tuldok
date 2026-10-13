"""Explicit catalog actors and bounded job continuations; no implicit domain transactions."""
import argparse
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
import uuid

SCOPES = frozenset(('inspect', 'edit', 'execute', 'cancel', 'freeze', 'approve-review',
                    'approve-execution', 'expose-holdout', 'admin'))
AGENT_SCOPES = SCOPES - {'approve-review', 'approve-execution', 'admin'}
SESSION_TTL = 8 * 3600
LOGIN_TTL = 600
MAX_TOKEN_TTL = 30 * 86400
_CURRENT = ContextVar('tuldok_actor', default=None)
HASH = re.compile(r'^[a-f0-9]{64}$')


class AccessError(Exception):
    def __init__(self, message, code='forbidden', status=403):
        super().__init__(message)
        self.code, self.status = code, status
        self.audited = False


@dataclass(frozen=True)
class ActorContext:
    catalog_id: str
    actor_id: str | None
    credential_id: str | None
    mode: str = 'credential'
    admission_id: str | None = None
    kind: str | None = None
    job_id: str | None = None
    request_digest: str | None = None


def _json(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(raw.encode('utf-8')) > 16384:
            raise ValueError()
        return raw
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise AccessError('Access evidence must be bounded finite JSON.', 'invalid', 400) from None


def _text(value, name, maximum=160):
    if type(value) is not str or not value.strip() or len(value) > maximum or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise AccessError(name + ' must be bounded nonempty text.', 'invalid', 400)
    return value


def authorized(scope, action, owner_only=False, target=None):
    """Authorize before entering the domain owner; never wrap its transaction."""
    def decorate(function):
        @wraps(function)
        def guarded(self, *args, **kwargs):
            access = self.access
            subject = target(*args, **kwargs) if callable(target) else target
            if target is None and args and isinstance(args[0], str):
                subject = args[0]
            try:
                access.require(scope, action, subject, owner_only=owner_only)
                return function(self, *args, **kwargs)
            except AccessError as error:
                access.denial(error, action, subject)
                raise
        return guarded
    return decorate


class Access:
    def __init__(self, db, catalog_path):
        self.db, self.catalog_path = db, Path(catalog_path)
        self.catalog_id, self.lock = db.dataset_id, db.lock

    def _credential(self, credential_id):
        row = self.db.execute('''SELECT c.id,c.actor_id,c.kind AS credential_kind,c.scopes_json,c.expires_at,
            c.revoked,c.consumed,a.kind,a.label FROM access_credentials c
            JOIN access_actors a ON a.id=c.actor_id WHERE c.id=%s''', (credential_id,)).fetchone()
        if row is None or row['revoked'] or row['consumed'] or row['expires_at'] <= int(time.time()) or row['credential_kind'] == 'login':
            raise AccessError('Credential is unavailable, expired or revoked.', 'unauthenticated', 401)
        return dict(row)

    def _resolve(self, token, *, login=False):
        if type(token) is not str or not 32 <= len(token) <= 256 or not token.isascii():
            raise AccessError('A valid credential is required.', 'unauthenticated', 401)
        row = self.db.execute('SELECT id,actor_id,kind,expires_at,revoked,consumed FROM access_credentials WHERE token_sha256=%s',
                              (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if row is None or row['revoked'] or row['consumed'] or row['expires_at'] <= int(time.time()):
            raise AccessError('A valid credential is required.', 'unauthenticated', 401)
        if login != (row['kind'] == 'login'):
            raise AccessError('Credential cannot be used for this authentication operation.', 'unauthenticated', 401)
        return row

    @contextmanager
    def bind(self, token):
        try:
            with self.lock:
                row = self._resolve(token)
                self._credential(row['id'])
        except AccessError as error:
            self.denial(error, 'access.authenticate', anonymous=True)
            raise
        marker = _CURRENT.set(ActorContext(self.catalog_id, row['actor_id'], row['id']))
        try:
            yield self.identity()
        finally:
            _CURRENT.reset(marker)

    def _context(self):
        context = _CURRENT.get()
        if context is None:
            raise AccessError('An explicit actor context is required.', 'unauthenticated', 401)
        if context.catalog_id != self.catalog_id:
            raise AccessError('Actor context belongs to another catalog.')
        return context

    def _admission(self, context):
        row = self.db.execute('SELECT * FROM access_admissions WHERE id=%s', (context.admission_id,)).fetchone()
        if (row is None or row['catalog_id'] != self.catalog_id or row['kind'] != context.kind
                or row['job_id'] != context.job_id or row['request_digest'] != context.request_digest
                or row['actor_id'] != context.actor_id or row['credential_id'] != context.credential_id):
            raise AccessError('Job continuation does not match its admitted request.')
        return row

    def require(self, scope, action, target=None, *, owner_only=False):
        if scope not in SCOPES:
            raise AccessError('Unsupported authorization scope.', 'invalid', 400)
        _text(action, 'Action')
        if target is not None:
            _text(target, 'Target', 512)
        try:
            with self.lock:
                context = self._context()
                if context.mode == 'job':
                    if owner_only or scope in ('approve-review', 'approve-execution', 'admin'):
                        raise AccessError('Job continuation cannot assume owner approval or administration.')
                    effects = json.loads(self._admission(context)['effects_json'])
                    if action not in effects or target not in effects[action]:
                        raise AccessError('Job continuation does not permit this action and target.')
                    return context
                if context.mode == 'system':
                    if owner_only or scope not in ('inspect', 'cancel'):
                        raise AccessError('System reconciliation cannot admit ordinary work.')
                    return context
                row = self._credential(context.credential_id)
                if row['actor_id'] != context.actor_id:
                    raise AccessError('Credential actor identity changed.')
                if scope not in json.loads(row['scopes_json']):
                    raise AccessError('Credential does not grant the required scope.')
                if row['kind'] != 'owner' and (owner_only or scope in ('execute', 'approve-review', 'approve-execution', 'admin')):
                    raise AccessError('This operation requires an authenticated owner; agent execution approval is not yet supported.')
                return context
        except AccessError as error:
            self.denial(error, action, target)
            raise

    def identity(self):
        with self.lock:
            context = self._context()
            if context.mode != 'credential':
                return {'catalog_id': self.catalog_id, 'actor_id': context.actor_id,
                        'credential_id': context.credential_id, 'kind': context.mode,
                        'label': 'Admitted job' if context.mode == 'job' else 'System reconciliation',
                        'scopes': [], 'expires_at': None, 'mode': context.mode,
                        'job_kind': context.kind, 'job_id': context.job_id,
                        'admission_id': context.admission_id, 'request_digest': context.request_digest}
            row = self._credential(context.credential_id)
            return {'catalog_id': self.catalog_id, 'actor_id': row['actor_id'], 'credential_id': row['id'],
                    'kind': row['kind'], 'label': row['label'], 'scopes': json.loads(row['scopes_json']),
                    'expires_at': row['expires_at']}

    def _insert_audit(self, action, target, details, result, context):
        _text(action, 'Action')
        if target is not None:
            _text(target, 'Target', 512)
        if result not in ('success', 'denied', 'failed', 'interrupted'):
            raise AccessError('Invalid audit outcome.', 'invalid', 400)
        self.db.execute('INSERT INTO access_audit VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
            (uuid.uuid4().hex, context.actor_id if context else None, context.credential_id if context else None,
             action, _json(target), _json(details or {}), result, int(time.time())))

    def audit(self, action, target=None, details=None, result='success'):
        if not self.db.in_transaction:
            raise RuntimeError('Success audit must share its domain mutation transaction.')
        context = self._context()
        if context.mode == 'job':
            effects = json.loads(self._admission(context)['effects_json'])
            if action not in effects or target not in effects[action]:
                raise AccessError('Job audit exceeds its admitted effect.')
        elif context.mode == 'system':
            if not action.endswith(('.reconcile', '.interrupt', '.drain', '.cancel')):
                raise AccessError('System audit must describe reconciliation or shutdown.')
        elif context.mode == 'credential':
            self._credential(context.credential_id)
        self._insert_audit(action, target, details, result, context)

    def denial(self, error, action, target=None, *, anonymous=False):
        # Nested domain guards defer denial evidence until their owner rolls back.
        if error.audited or self.db.in_transaction:
            return
        # Invalid caller targets must not break evidence of the original refusal.
        try:
            if target is not None:
                _text(target, 'Target', 512)
        except AccessError:
            target = None
        context = None if anonymous else _CURRENT.get()
        if context and context.catalog_id != self.catalog_id:
            context = None
        with self.lock, self.db.transaction():
            self._insert_audit(action, target, {'code': error.code}, 'denied', context)
        error.audited = True

    def _mint(self, actor_id, kind, scopes, ttl):
        token = secrets.token_urlsafe(32)
        credential_id = uuid.uuid4().hex
        self.db.execute('INSERT INTO access_credentials VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (credential_id, actor_id, hashlib.sha256(token.encode()).hexdigest(), kind,
             _json(sorted(scopes)), int(time.time()) + ttl, 0, 0, int(time.time())))
        return token, credential_id

    def _local_owner_token(self, *, initial=False):
        """Explicit local administration only; never exposed by a transport route."""
        with self.lock, self.db.transaction():
            owners = self.db.execute("SELECT id FROM access_actors WHERE kind='owner'").fetchall()
            if initial and owners:
                raise AccessError('Owner already exists; use local login renewal.', 'conflict', 409)
            if len(owners) > 1:
                raise AccessError('Owner identity is ambiguous.', 'unavailable', 409)
            actor_id = owners[0][0] if owners else uuid.uuid4().hex
            if not owners:
                self.db.execute('INSERT INTO access_actors VALUES (%s,%s,%s,%s)',
                                (actor_id, 'owner', 'Local owner', int(time.time())))
            token, credential_id = self._mint(actor_id, 'login', SCOPES, LOGIN_TTL)
            self._insert_audit('access.local_login', credential_id, {'initial': not bool(owners)}, 'success',
                               ActorContext(self.catalog_id, actor_id, credential_id))
            return token

    def exchange(self, token):
        try:
            with self.lock, self.db.transaction():
                row = self._resolve(token, login=True)
                changed = self.db.execute('UPDATE access_credentials SET consumed=1 WHERE id=%s AND consumed=0 AND revoked=0 RETURNING id', (row['id'],)).fetchone()
                if changed is None:
                    raise AccessError('Login credential was already consumed.', 'unauthenticated', 401)
                actor = self.db.execute('SELECT kind FROM access_actors WHERE id=%s', (row['actor_id'],)).fetchone()
                if actor is None or actor[0] != 'owner':
                    raise AccessError('Login requires an existing owner.', 'unauthenticated', 401)
                session, credential_id = self._mint(row['actor_id'], 'session', SCOPES, SESSION_TTL)
                self._insert_audit('access.exchange', credential_id, {}, 'success', ActorContext(self.catalog_id, row['actor_id'], credential_id))
            with self.bind(session):
                identity = self.identity()
            return {'token': session, 'identity': identity}
        except AccessError as error:
            self.denial(error, 'access.exchange', anonymous=True)
            raise

    @authorized('admin', 'access.issue', owner_only=True)
    def issue(self, body):
        if type(body) is not dict or set(body) - {'label', 'scopes', 'ttl_seconds'} or not {'label', 'scopes'} <= set(body):
            raise AccessError('Credential fields must be label, scopes and optional ttl_seconds.', 'invalid', 400)
        label = _text(body['label'], 'Label')
        scopes, ttl = body['scopes'], body.get('ttl_seconds', 3600)
        if type(scopes) is not list or any(type(s) is not str for s in scopes) or len(scopes) != len(set(scopes)) or not set(scopes) <= AGENT_SCOPES or 'inspect' not in scopes:
            raise AccessError('Agent scopes require inspect and cannot grant approval or admin.', 'invalid', 400)
        if type(ttl) is not int or not 60 <= ttl <= MAX_TOKEN_TTL:
            raise AccessError('Credential lifetime must be 60 seconds through 30 days.', 'invalid', 400)
        with self.lock, self.db.transaction():
            actor_id = uuid.uuid4().hex
            self.db.execute('INSERT INTO access_actors VALUES (%s,%s,%s,%s)', (actor_id, 'agent', label, int(time.time())))
            token, credential_id = self._mint(actor_id, 'bearer', scopes, ttl)
            self.audit('access.issue', credential_id, {'actor_id': actor_id, 'scopes': scopes, 'ttl_seconds': ttl})
        with self.bind(token):
            identity = self.identity()
        return {'token': token, 'identity': identity}

    @property
    def access(self):
        return self

    @authorized('admin', 'access.revoke', owner_only=True)
    def revoke(self, credential_id):
        with self.lock, self.db.transaction():
            changed = self.db.execute('UPDATE access_credentials SET revoked=1 WHERE id=%s RETURNING id', (credential_id,)).fetchone()
            if changed is None:
                raise AccessError('Credential not found.', 'unavailable', 404)
            # Self-revocation still records the actor verified at admission.
            self._insert_audit('access.revoke', credential_id, {}, 'success', self._context())
        return {'revoked': True, 'credential_id': credential_id}

    def logout(self):
        context = self.require('inspect', 'access.logout')
        if context.mode != 'credential':
            raise AccessError('Only a credential session can log out.')
        with self.lock, self.db.transaction():
            self.db.execute('UPDATE access_credentials SET revoked=1 WHERE id=%s', (context.credential_id,))
            self._insert_audit('access.logout', context.credential_id, {}, 'success', context)
        return {'revoked': True}

    def admit_job(self, kind, job_id, request_digest, effects):
        context = self.require('execute', 'access.admit_job', job_id, owner_only=True)
        if context.mode != 'credential' or not self.db.in_transaction:
            raise AccessError('Job admission requires an owner mutation transaction.')
        _text(kind, 'Job kind')
        _text(job_id, 'Job ID')
        if type(request_digest) is not str or not HASH.fullmatch(request_digest):
            raise AccessError('Job request digest must be SHA256.', 'invalid', 400)
        if type(effects) is not dict or not 1 <= len(effects) <= 16:
            raise AccessError('Job effects must be a finite action map.', 'invalid', 400)
        for action, targets in effects.items():
            _text(action, 'Effect action')
            if action.startswith('access.'):
                raise AccessError('Jobs cannot receive authentication or admission effects.', 'invalid', 400)
            if type(targets) is not list or not 1 <= len(targets) <= 256:
                raise AccessError('Job effects require bounded exact targets.', 'invalid', 400)
            for target in targets:
                if target is not None:
                    _text(target, 'Effect target', 512)
        admission_id = uuid.uuid4().hex
        self.db.execute('INSERT INTO access_admissions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (admission_id, self.catalog_id, context.actor_id, context.credential_id, kind, job_id,
             request_digest, _json(effects), int(time.time())))
        self.audit('access.admit_job', job_id, {'admission_id': admission_id, 'kind': kind, 'request_digest': request_digest, 'effects': effects})
        return admission_id

    def require_job(self, kind, job_id, admission_id, request_digest):
        context = self._context()
        if (context.mode != 'job' or context.kind != kind or context.job_id != job_id
                or context.admission_id != admission_id or context.request_digest != request_digest):
            raise AccessError('This operation requires its exact admitted job continuation.')
        with self.lock:
            self._admission(context)
        return context

    @contextmanager
    def _job(self, kind, job_id, admission_id, request_digest):
        with self.lock:
            row = self.db.execute('SELECT actor_id,credential_id FROM access_admissions WHERE id=%s', (admission_id,)).fetchone()
            if row is None:
                raise AccessError('Job admission is unavailable.')
            context = ActorContext(self.catalog_id, row['actor_id'], row['credential_id'], 'job', admission_id, kind, job_id, request_digest)
            self._admission(context)
        marker = _CURRENT.set(context)
        try:
            yield
        finally:
            _CURRENT.reset(marker)

    @contextmanager
    def _reconcile(self):
        marker = _CURRENT.set(ActorContext(self.catalog_id, None, None, 'system'))
        try:
            yield
        finally:
            _CURRENT.reset(marker)


def main():
    parser = argparse.ArgumentParser(description='Create a private one-time local owner login credential.')
    parser.add_argument('command', choices=('bootstrap', 'login'))
    parser.add_argument('--data', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    from metadata import Metadata
    descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as handle:
            os.fchmod(handle.fileno(), 0o600)
            db = Metadata(args.data, create=False)
            try:
                token = Access(db, args.data)._local_owner_token(initial=args.command == 'bootstrap')
            finally:
                db.close()
            handle.write(token + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        parent_fd = os.open(args.out.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        args.out.unlink(missing_ok=True)
        raise
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (AccessError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
