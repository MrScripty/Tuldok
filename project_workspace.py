"""One inert external-project workspace and its installation-local authority.

Only explicit project-files operations enter this owner. Legacy domain routes
are unavailable in this mode until their canonical publication is implemented.
The installation catalog holds local credentials; it is never portable content.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid

from access import Access
import agent_api
from metadata import Metadata
from project_store import ProjectStore, ProjectStoreError
from project_projection import ProjectProjection
from workbench import WorkbenchError


PUBLIC_RECORD_FIELDS = ('id', 'kind', 'name', 'text', 'groups', 'parents', 'provenance',
                        'task', 'annotation', 'review', 'revision', 'source_revision',
                        'created_at', 'updated_at')
SUMMARY_FIELDS = ('id', 'kind', 'name', 'task', 'review', 'revision', 'source_revision',
                  'created_at', 'updated_at')
PROJECT_ACTIONS = ('new', 'open', 'save', 'close', 'query', 'get', 'import_text', 'annotate')
# Set only after the complete finite dispatcher is integrated. A capability is
# a promise that the route reaches canonical publication, not an API wishlist.
M2_ENABLED = True
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def public_record(value):
    """Project owned values into the closed public contract; do not infer policy."""
    return {key: copy.deepcopy(value[key]) for key in PUBLIC_RECORD_FIELDS}


def _digest(value):
    return hashlib.sha256(agent_api.encoded(value)).hexdigest()


def http_arguments(method, target, body=None):
    """Use the fixed operation contracts for identical HTTP and SDK routing."""
    names = ['project_files.status', *('project_files.' + action for action in PROJECT_ACTIONS)]
    names.extend(sorted(agent_api.PROJECT_FILES_M2))
    operations = {name: agent_api.operation(name) for name in names}
    # A literal import route wins over a record-id placeholder. Contract
    # validation still rejects an unexpected path/body/query representation.
    ordered = sorted(operations.items(), key=lambda item: (item[1]['path'].count('{'), item[0]))
    for name, operation in ordered:
        if agent_api._route_matches(operation, method, target):
            selected = (name, 1, agent_api.contract(name, 1)['sha256'])
            return name, agent_api.validate_selected(selected, method, target, body)
    raise WorkbenchError('Unknown project-file operation.', 'unsupported', 404)


class ProjectWorkspace:
    project_files_mode = True

    def __init__(self, control_path, roots, *, dsn=None):
        self.path = Path(control_path).resolve()
        self.db = Metadata(self.path, dsn=dsn)
        self.lock = self.db.lock
        self.access = Access(self.db, self.path)
        self._dsn = dsn
        self._mutex = threading.RLock()
        self._roots = {}
        self._store = self._text = self._projection = None
        self._selection = None
        self._last_project = None
        self._recovery = None
        self._binding = uuid.uuid4().hex
        self._closed = False
        self._receipts = {}
        try:
            if not roots or len(roots) > 100:
                raise WorkbenchError('Configure between one and 100 local project-file roots.')
            for alias, path in roots.items():
                if type(alias) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', alias):
                    raise WorkbenchError('Invalid local project-file root alias.')
                location = Path(path).expanduser().resolve(strict=True)
                descriptor = os.open(location, DIR_FLAGS)
                self._roots[alias] = (location, descriptor)
        except BaseException:
            self.close()
            raise

    def _ensure_open(self):
        if self._closed:
            raise WorkbenchError('Project workspace is closed.', 'unavailable', 503)

    def _recovery_required(self, reason, request_key=None):
        if self._recovery is None and self._selection is not None and self._last_project is not None:
            self._recovery = dict(action='open', root=self._selection[0], directory=self._selection[1],
                                  reason=reason, request_key=request_key)

    def _state(self):
        self._ensure_open()
        project = None
        if self._recovery is None and self._store is not None:
            try:
                snapshot = self._store.snapshot()
            except ProjectStoreError as error:
                if error.code not in ('unknown', 'outcome_unknown'):
                    raise
                self._recovery_required('unknown_publication')
            else:
                if self._text is not None and not self._text.available:
                    self._recovery_required('projection_unavailable')
                else:
                    project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
                    self._last_project = copy.deepcopy(project)
        if self._recovery is not None:
            return dict(format='project_files_state_v1', binding=self._binding, state='recovery_required',
                        roots=sorted(self._roots), project=copy.deepcopy(self._last_project),
                        available_actions=['open'], recovery=copy.deepcopy(self._recovery))
        return dict(format='project_files_state_v1', binding=self._binding,
                    state='open' if project is not None else 'no_project_open',
                    roots=sorted(self._roots), project=project,
                    available_actions=list(PROJECT_ACTIONS if project is not None else ('new', 'open')))

    def status(self):
        with self._mutex, self.access.lock:
            self.access.require('inspect', 'project_files.status')
            return self._state()

    def capabilities(self):
        value = agent_api.capabilities(self.db.dataset_id)
        for operation in value['operations']:
            if operation['id'] in agent_api.PROJECT_FILES_M2 and not M2_ENABLED:
                operation['availability'] = 'unavailable'
            if not operation['id'].startswith('project_files.') and operation['id'] not in ('context.get', 'identity.get'):
                operation['availability'] = 'unavailable'
        return value

    def _bound(self, arguments, *, may_be_empty=False, check_checkpoint=True, allow_recovery=False):
        self._ensure_open()
        if arguments['binding'] != self._binding:
            raise WorkbenchError('The project workspace changed. Refresh its binding before acting.',
                                 'stale_project', 409)
        if self._recovery is not None:
            if not allow_recovery:
                raise WorkbenchError('Explicitly reopen the current project to reconcile its canonical outcome.',
                                     'projection_unavailable', 503)
            if arguments.get('expected_checkpoint') != self._last_project['checkpoint']:
                raise WorkbenchError('Recovery requires the last acknowledged checkpoint.', 'stale_project', 409)
            return
        if self._store is None:
            if not may_be_empty:
                raise WorkbenchError('Open an external project first.', 'unavailable', 409)
            if arguments.get('expected_checkpoint') is not None:
                raise WorkbenchError('The empty workspace has no checkpoint.', 'stale_project', 409)
            return
        snapshot = self._store.snapshot()
        expected = arguments.get('expected_checkpoint', arguments.get('checkpoint'))
        if check_checkpoint and expected != snapshot['checkpoint']:
            raise WorkbenchError('The project checkpoint changed. Refresh before acting.', 'stale_project', 409)

    def _root(self, alias, relative):
        if alias not in self._roots:
            raise WorkbenchError('Choose a configured local project-file root.', 'unavailable', 409)
        # Store create_at/open_at retains this handle through all actual use.
        if (type(relative) is not str or not relative or len(relative) > 512 or
                relative.startswith('/') or '\\' in relative or '\x00' in relative or
                any(part in ('', '.', '..') for part in relative.split('/')) or
                len(relative.split('/')) > 16):
            raise WorkbenchError('Use a project directory relative to its configured root, without traversal.')
        return self._roots[alias]

    def _projection_for(self, store):
        identity = uuid.uuid4().hex
        path = self.path / '.project-projections' / identity
        snapshot = store.snapshot()
        projection = Metadata(path, dsn=self._dsn, dataset_id=snapshot['project_id'], projection_id=identity)
        try:
            owner = ProjectProjection(store, projection, self.access,
                                      {alias: value[0] for alias, value in self._roots.items()})
            return owner, owner.text
        except BaseException:
            projection.close()
            # Disposable failed projections remain identified for diagnosis;
            # no authoritative bytes or an uncertain outcome is deleted.
            raise

    def _detach(self):
        """M1 owns no worker-capable domains; all requests drain under _mutex."""
        if self._store is not None:
            # Prove pending project publications and their full closure first.
            self._store.save(self._store.snapshot()['checkpoint'])
        if self._projection is not None:
            self._projection.close()
        if self._store is not None:
            self._store.close()
        self._store = self._text = self._projection = None
        self._selection = None
        self._last_project = self._recovery = None

    def _recover_current(self, arguments):
        self._bound(arguments, allow_recovery=True)
        if (arguments['root'], arguments['directory']) != self._selection:
            raise WorkbenchError('Recover the current project before switching destinations.', 'projection_unavailable', 503)
        root_path, root_fd = self._root(*self._selection)
        # Keep the old projection and generation until a fresh inert projection
        # is ready. Releasing the uncertain writer lock is necessary to reread it.
        if self._store is not None:
            self._store.close()
            self._store = None
        store = projection = None
        try:
            store = ProjectStore.open_at(root_fd, arguments['directory'], root_path=root_path)
            snapshot = store.snapshot()
            if snapshot['project_id'] != self._last_project['project_id']:
                raise WorkbenchError('Recovery destination has a different project identity.', 'stale_project', 409)
            # A reread reconciles identity; only a successful durability barrier
            # resolves a prior checkpoint/directory fsync failure.
            store.save(snapshot['checkpoint'])
            projection, text = self._projection_for(store)
            snapshot = store.snapshot()
            if self._projection is not None:
                self._projection.close()
            self._store, self._projection, self._text = store, projection, text
            self._last_project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
            self._recovery = None
            self._binding = uuid.uuid4().hex
            return self._state()
        except BaseException:
            if projection is not None and projection is not self._projection:
                projection.close()
            if store is not None and store is not self._store:
                store.close()
            raise

    def _select(self, action, arguments):
        if self._recovery is not None:
            if action != 'open':
                raise WorkbenchError('Reopen the current project before creating another.', 'projection_unavailable', 503)
            return self._recover_current(arguments)
        self._bound(arguments, may_be_empty=True)
        root_path, root_fd = self._root(arguments['root'], arguments['directory'])
        selection = (arguments['root'], arguments['directory'])
        if action == 'open' and selection == self._selection:
            return self._state()
        # Validate and construct the incoming inert projection before releasing
        # the existing binding. An invalid Open cannot strand current custody.
        store = None
        projection = None
        created = None
        try:
            if action == 'new':
                request = {key: arguments[key] for key in ('root', 'directory', 'name', 'request_key')}
                digest = _digest(request)
                reconciled = False
                try:
                    store = ProjectStore.create_at(root_fd, arguments['directory'], arguments['name'],
                                                   arguments['request_key'], digest, root_path=root_path)
                except ProjectStoreError as error:
                    if error.code not in ('conflict', 'unknown', 'outcome_unknown'):
                        raise
                    # A lost creation reply or restart may leave a complete,
                    # unselected destination. Only its exact receipt authorizes
                    # treating it as this New; unrelated folders remain conflicts.
                    try:
                        store = ProjectStore.open_at(root_fd, arguments['directory'], root_path=root_path)
                    except ProjectStoreError:
                        raise error
                    if store.reconcile(arguments['request_key'], digest) is None:
                        raise error
                    reconciled = True
                snapshot = store.snapshot()
                if reconciled:
                    store.save(snapshot['checkpoint'])
                created = snapshot
            else:
                store = ProjectStore.open_at(root_fd, arguments['directory'], root_path=root_path)
            projection, text = self._projection_for(store)
            self._detach()
            self._store, self._projection, self._text = store, projection, text
            self._selection = selection
            snapshot = store.snapshot()
            self._last_project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
            self._recovery = None
            self._binding = uuid.uuid4().hex
            return self._state()
        except BaseException as error:
            if projection is not None and projection is not self._projection:
                projection.close()
            if store is not None and store is not self._store:
                store.close()
            if created is not None and self._store is not store:
                failure = WorkbenchError('Project was created but could not be selected; retry this exact New to reconcile its destination.',
                                         'project_selection_unavailable', 503)
                failure.committed, failure.selected = True, False
                failure.project_id, failure.checkpoint = created['project_id'], created['checkpoint']
                failure.request_key = arguments['request_key']
                failure.root, failure.directory = arguments['root'], arguments['directory']
                failure.receipt = dict(committed=True, selected=False, project_id=created['project_id'],
                    checkpoint=created['checkpoint'], request_key=arguments['request_key'],
                    root=arguments['root'], directory=arguments['directory'])
                raise failure from error
            raise

    def _record_result(self, record, *, before_revision=None, history_limit=1):
        snapshot = self._store.snapshot()
        history = [item for item in self._text.history(record['id'])
                   if item['revision'] <= record['revision'] and
                   (before_revision is None or item['revision'] < before_revision)]
        history.sort(key=lambda item: item['revision'], reverse=True)
        page = history[:history_limit]
        self._last_project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
        return dict(binding=self._binding, project_id=snapshot['project_id'], checkpoint=snapshot['checkpoint'],
                    record=public_record(record), history=[public_record(item) for item in page],
                    next_history_before_revision=page[-1]['revision'] if len(history) > len(page) else None)

    def dispatch(self, name, arguments):
        """Pin workspace -> current host authority -> projection through return.

        An old request cannot observe a new Dataset alias. Revocation cannot
        complete before an already-authorized canonical publication finishes.
        """
        agent_api.validate_arguments(name, arguments)
        if not name.startswith('project_files.'):
            raise WorkbenchError('This domain is unavailable in external text-project mode.', 'unavailable', 409)
        action = name.removeprefix('project_files.')
        with self._mutex, self.access.lock:
            self._ensure_open()
            operation = agent_api.operation(name)
            for scope in operation['scopes']:
                self.access.require(scope, name, owner_only=action in ('new', 'open', 'save', 'close'))
            if name in agent_api.PROJECT_FILES_M2:
                if not M2_ENABLED:
                    raise WorkbenchError('This project capability is not yet available.', 'unavailable', 409)
                self._bound(arguments, check_checkpoint=not operation['side_effects'])
                from project_dispatch import dispatch
                try:
                    value = dispatch(self._projection, name, arguments)
                except BaseException as error:
                    if getattr(error, 'code', None) in ('unknown', 'outcome_unknown', 'projection_unavailable'):
                        self._recovery_required('projection_unavailable', arguments.get('request_key'))
                    raise
                snapshot = self._store.snapshot()
                self._last_project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
                result = dict(binding=self._binding, project_id=snapshot['project_id'],
                              checkpoint=snapshot['checkpoint'], value=value)
            elif action == 'status':
                result = self._state()
            else:
                # Lifecycle receipts are process-binding scoped. Domain edit
                # receipts are canonical and survive any originating DB loss.
                key = (name, arguments.get('binding'), arguments.get('request_key'))
                signature = _digest(arguments)
                prior = self._receipts.get(key) if arguments.get('request_key') else None
                if prior is not None:
                    if prior[0] != signature:
                        raise WorkbenchError('Request key already has different input.', 'conflict', 409)
                    if prior[1] != self._state():
                        raise WorkbenchError('This lifecycle receipt belongs to an obsolete workspace state.', 'stale_project', 409)
                    result = copy.deepcopy(prior[1])
                else:
                    try:
                        if action in ('new', 'open'):
                            result = self._select(action, arguments)
                        elif action == 'save':
                            self._bound(arguments)
                            self._store.save(arguments['expected_checkpoint'])
                            result = self._state()
                        elif action == 'close':
                            self._bound(arguments)
                            self._detach()
                            self._binding = uuid.uuid4().hex
                            result = self._state()
                        elif action == 'query':
                            self._bound(arguments)
                            value = self._text.records()
                            items = sorted(value['items'], key=lambda item: item['id'])
                            if arguments.get('after_id') is not None:
                                items = [item for item in items if item['id'] > arguments['after_id']]
                            page = items[:arguments.get('limit', 40)]
                            result = dict(binding=self._binding, project_id=value['project_id'], checkpoint=value['checkpoint'],
                                          items=[{key: copy.deepcopy(item[key]) for key in SUMMARY_FIELDS} for item in page],
                                          next_after_id=page[-1]['id'] if len(items) > len(page) else None)
                        elif action == 'get':
                            self._bound(arguments)
                            result = self._record_result(self._text.get(arguments['record_id']),
                                before_revision=arguments.get('before_revision'), history_limit=arguments.get('history_limit', 1))
                        elif action in ('import_text', 'annotate'):
                            # Canonical domain receipts reconcile before CAS.
                            self._bound(arguments, check_checkpoint=False)
                            if action == 'import_text':
                                record = self._text.import_text(arguments['asset'], arguments['expected_checkpoint'], arguments['request_key'])
                            else:
                                record = self._text.annotate(arguments['record_id'], arguments['annotation'],
                                                             arguments['expected_checkpoint'], arguments['request_key'])
                            result = self._record_result(record)
                        else:
                            raise WorkbenchError('Unsupported project-file operation.', 'unsupported', 400)
                    except BaseException as error:
                        code = getattr(error, 'code', None)
                        if code in ('unknown', 'outcome_unknown', 'projection_unavailable'):
                            reason = 'unknown_publication' if code in ('unknown', 'outcome_unknown') else 'projection_unavailable'
                            self._recovery_required(reason, arguments.get('request_key'))
                        raise
                    if arguments.get('request_key') and action in ('new', 'open', 'save', 'close'):
                        self._receipts[key] = (signature, copy.deepcopy(result))
            if len(agent_api.encoded(result)) > agent_api.RESPONSE_LIMIT:
                raise WorkbenchError('This project result exceeds the synchronous response bound; canonical work is retained.',
                                     'too_large', 413)
            agent_api.validate_output(name, {'status': 200, 'result': result})
            return result

    def close(self):
        with self._mutex:
            if self._closed:
                return
            # Shutdown always releases handles, including a stale/unknown store;
            # no worker domains exist and no canonical recovery is attempted.
            if self._projection is not None:
                self._projection.close()
            if self._store is not None:
                self._store.close()
            self._projection = self._text = self._store = None
            for _path, fd in self._roots.values():
                os.close(fd)
            self._roots.clear()
            self.db.close()
            self._closed = True
