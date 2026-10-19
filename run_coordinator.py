"""Runs-owned, bounded local coordinator journal; never process/custody authority."""
import json
import copy
import os
import stat
import threading
import time
import uuid
from contextlib import contextmanager

from workbench import WorkbenchError, encode, timestamp

LIMIT = 16 * 1024


class Coordinator:
    def __init__(self, runs):
        self.runs = runs
        self.lock = threading.RLock()
        self.recovery = threading.Lock()
        self.journal_ok = True
        self.value = {'format': 'run_coordinator_v1', 'catalog_id': runs.db.dataset_id,
                      'generation': 1, 'state': 'idle', 'updated_at': timestamp(),
                      'fault': None, 'request': None}
        if runs.runtime_owner:
            try:
                with self.directory() as descriptor:
                    try:
                        file = os.open('.coordinator-v1.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                       dir_fd=descriptor)
                    except FileNotFoundError:
                        file = None
                    if file is not None:
                        with os.fdopen(file, 'rb') as stream:
                            info = os.fstat(stream.fileno())
                            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > LIMIT:
                                raise ValueError('Invalid coordinator journal file.')
                            old = json.loads(stream.read(LIMIT + 1))
                            after = os.fstat(stream.fileno())
                            if (type(old) is not dict or old.get('format') != 'run_coordinator_v1' or
                                    set(old) != set(self.value) or
                                    old.get('catalog_id') != runs.db.dataset_id or
                                    type(old.get('generation')) is not int or not 1 <= old['generation'] < 2**31-1 or
                                    old.get('state') not in ('healthy', 'idle', 'blocked', 'recovering', 'stopped', 'faulted') or
                                    type(old.get('updated_at')) is not str or len(old['updated_at']) > 64 or
                                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) !=
                                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                                raise ValueError('Invalid coordinator journal identity.')
                            fault = old['fault']
                            if fault is not None and (type(fault) is not dict or set(fault) != {'category', 'at'} or
                                    any(type(fault[k]) is not str or not 1 <= len(fault[k]) <= 80 for k in fault)):
                                raise ValueError('Invalid retained coordinator fault.')
                            request = old['request']
                            if request is not None:
                                from runs import REQUEST_KEY
                                from pipeline import digest
                                if (type(request) is not dict or set(request) != {'actor_id', 'request_key', 'request_sha256',
                                        'expected_generation', 'completed_generation'} or
                                        type(request['actor_id']) is not str or len(request['actor_id']) != 32 or
                                        type(request['request_key']) is not str or not REQUEST_KEY.fullmatch(request['request_key']) or
                                        type(request['expected_generation']) is not int or not 1 <= request['expected_generation'] <= old['generation'] or
                                        request['completed_generation'] is not None and
                                        (type(request['completed_generation']) is not int or
                                         not request['expected_generation'] < request['completed_generation'] <= old['generation'])):
                                    raise ValueError('Invalid retained coordinator request.')
                                body = {'request_key': request['request_key'], 'expected_generation': request['expected_generation']}
                                if request['request_sha256'] != digest({'catalog_id': runs.db.dataset_id,
                                        'operation': 'runs.recover_coordinator', 'actor_id': request['actor_id'], 'body': body}):
                                    raise ValueError('Coordinator request digest differs.')
                            # Reopen still uses ordinary durable Run/custody reconciliation.
                            # Old readiness and request acknowledgements never revive a thread.
                            self.value['generation'] = old['generation'] + 1
                            self.value['fault'] = fault
                            self.value['request'] = request
                self.save()
            except (OSError, ValueError, TypeError):
                self.journal_ok = False
                self.fault('journal_unavailable')

    def directory(self):
        @contextmanager
        def opened():
            descriptor = os.open(self.runs.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(descriptor)
                if info.st_uid != os.getuid():
                    raise OSError('Coordinator directory owner differs.')
                yield descriptor
            finally:
                os.close(descriptor)
        return opened()

    def save(self):
        """Atomic private replacement and directory sync, bounded independently of history."""
        if not self.journal_ok:
            raise OSError('Original coordinator journal is unavailable; retain it for inspection.')
        raw = encode(self.value).encode('utf-8')
        if len(raw) > LIMIT:
            raise ValueError('Coordinator journal exceeds its bound.')
        with self.directory() as descriptor:
            temporary = '.coordinator-' + uuid.uuid4().hex
            try:
                file = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=descriptor)
                with os.fdopen(file, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, '.coordinator-v1.json', src_dir_fd=descriptor, dst_dir_fd=descriptor)
                os.fsync(descriptor)
            finally:
                try:
                    os.unlink(temporary, dir_fd=descriptor)
                except FileNotFoundError:
                    pass

    def transition(self, state):
        with self.lock:
            if self.runs._stop.is_set() and state != 'stopped':
                return
            if self.value['state'] == state:
                return
            self.value.update(state=state, updated_at=timestamp())
            try:
                self.save()
            except (OSError, ValueError):
                self.fault('journal_unavailable')

    def fault(self, code):
        with self.lock:
            self.runs._fence_coordinator()
            if self.value['fault'] is None:
                self.value['fault'] = {'category': code, 'at': timestamp()}
            self.value.update(state='faulted', updated_at=timestamp())
            try:
                self.save()
            except (OSError, ValueError):
                pass  # Memory fence survives an unacknowledged journal write.

    def projection(self):
        with self.lock:
            value = self.value
            thread = self.runs._thread
            dead = thread is not None and not thread.is_alive()
            ready = (not self.runs._closed and self.runs.runtime_owner and
                     not self.runs._stop.is_set() and not dead and
                     value['state'] not in ('faulted', 'recovering', 'stopped') and
                     not self.runs._blocked and not self.runs._external_blocked)
            state = ('stopped' if self.runs._closed else 'recovering' if value['state'] == 'recovering' else
                     'faulted' if dead and not ready else
                     'blocked' if value['state'] != 'faulted' and
                     (self.runs._blocked or self.runs._external_blocked or not self.runs.runtime_owner) else value['state'])
            return {'format': 'run_coordinator_health_v1', 'catalog_id': self.runs.db.dataset_id,
                    'generation': value['generation'],
                    'state': state, 'updated_at': value['updated_at'],
                    'fault': copy.deepcopy(value['fault']), 'admission_ready': bool(ready),
                    'recovery_request': copy.deepcopy(value['request'])}

    def require_ready(self):
        if not self.projection()['admission_ready']:
            raise WorkbenchError('Run coordinator is fenced; inspect its health and explicitly recover as owner.',
                                 'unavailable', 409)

    def recover(self, body):
        from pipeline import closed, digest
        from runs import REQUEST_KEY
        closed(body, ('expected_generation', 'request_key'))
        generation, key = body['expected_generation'], body['request_key']
        if type(generation) is not int or not 1 <= generation < 2**31 or type(key) is not str or not REQUEST_KEY.fullmatch(key):
            raise WorkbenchError('Recovery requires the exact generation and stable request key.', 'invalid', 400)
        deadline = time.monotonic() + 60
        with self.catalog(deadline):
            owner = self.runs.access.require('approve-execution', 'runs.recover_coordinator', owner_only=True)
        request = {'actor_id': owner.actor_id, 'request_key': key,
                   'request_sha256': digest({'catalog_id': self.runs.db.dataset_id,
                       'operation': 'runs.recover_coordinator', 'actor_id': owner.actor_id, 'body': body}),
                   'expected_generation': generation, 'completed_generation': None}
        while not self.recovery.acquire(timeout=.1):
            self.check_deadline(deadline)
        entered = False
        try:
            self.check_deadline(deadline)
            with self.bounded(self.lock, deadline):
                old = self.value['request']
                if old and old['request_key'] == key:
                    if any(old[field] != request[field] for field in ('actor_id', 'request_sha256', 'expected_generation')):
                        raise WorkbenchError('Recovery key belongs to another actor or request.', 'conflict', 409)
                    if old['completed_generation'] == self.value['generation'] and self.projection()['admission_ready']:
                        return self.projection()
                elif generation != self.value['generation']:
                    raise WorkbenchError('Coordinator generation changed; inspect current health.', 'stale', 409)
                if not self.journal_ok:
                    raise WorkbenchError('Original coordinator journal needs owner inspection before reopen.', 'unavailable', 409)
                if self.projection()['admission_ready']:
                    raise WorkbenchError('Coordinator is already ready.', 'conflict', 409)
                self.value['request'] = request
                entered = True
                self.runs._fence_coordinator()
                self.value.update(state='recovering', updated_at=timestamp())
                self.save()
            # No catalog or lifecycle lock is held while the old executor drains.
            thread = self.runs._thread
            while thread is not None and thread.is_alive():
                self.check_deadline(deadline)
                thread.join(timeout=.1)
            self.check_deadline(deadline)
            self.runs._reconcile_coordinator(deadline)
            with self.catalog(deadline), self.bounded(self.runs._thread_lock, deadline):
                self.check_deadline(deadline)
                self.runs.access.require('approve-execution', 'runs.recover_coordinator', owner_only=True)
                if not self.runs.runtime_owner or not self.runs.db.runtime_owned('workspace_runs'):
                    raise WorkbenchError('Current PostgreSQL session lost coordinator ownership.', 'unavailable', 409)
                if self.runs._blocked or self.runs._external_blocked:
                    raise WorkbenchError('Durable custody remains uncertain; execution stays fenced.', 'unavailable', 409)
                with self.bounded(self.lock, deadline):
                    self.value['generation'] += 1
                    self.value.update(state='idle', updated_at=timestamp())
                    self.save()
                # Only this serialized, reconciled recovery may replace a stopped
                # generation. Application close is checked under the same lock.
                self.runs._thread = None
                self.runs._stop.clear()
                self.runs._start()
                if not self.runs._thread or not self.runs._thread.is_alive():
                    raise WorkbenchError('Replacement coordinator did not establish ownership.', 'unavailable', 409)
                with self.bounded(self.lock, deadline):
                    request['completed_generation'] = self.value['generation']
                    self.save()
            return self.projection()
        except Exception:
            if entered:
                self.fault('recovery_failed')
            raise
        finally:
            self.recovery.release()

    def check_deadline(self, deadline):
        if self.runs._closed:
            raise WorkbenchError('Application shutdown has fenced coordinator recovery.', 'unavailable', 409)
        if time.monotonic() >= deadline:
            raise WorkbenchError('Coordinator recovery did not establish drainage within its wall bound.', 'unavailable', 409)

    @contextmanager
    def catalog(self, deadline):
        from metadata import StorageError, CommitOutcomeUnknown
        try:
            with self.runs.lock.bounded(deadline, cancelled=lambda: self.runs._closed), self.runs.db.commands_before(deadline):
                self.check_deadline(deadline)
                yield
        except CommitOutcomeUnknown as error:
            raise WorkbenchError(str(error), 'commit_unknown', 409) from error
        except StorageError as error:
            raise WorkbenchError(str(error), 'unavailable', 409) from error

    @contextmanager
    def bounded(self, lock, deadline):
        while not lock.acquire(timeout=min(.1, max(0, deadline-time.monotonic()))):
            self.check_deadline(deadline)
        try:
            self.check_deadline(deadline)
            yield
        finally:
            lock.release()
