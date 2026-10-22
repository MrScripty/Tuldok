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
from project_custody import ProjectCustody
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
M3_ENABLED = True
M4_ENABLED = True
_RECOVERY_OPERATIONS = frozenset(('project_files.execution_reconcile_current',
    'project_files.native_reconcile',
    'project_files.runtime_capture', 'project_files.runtime_abandon',
    'project_files.execution_study_abandon_preparation', 'project_files.execution_study_reconcile_preparation'))
_DRAINING_OPERATIONS = _RECOVERY_OPERATIONS | frozenset(('project_files.execution_producer_cancel',
    'project_files.execution_study_stop'))
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def public_record(value):
    """Project owned values into the closed public contract; do not infer policy."""
    return {key: copy.deepcopy(value[key]) for key in PUBLIC_RECORD_FIELDS}


def _digest(value):
    return hashlib.sha256(agent_api.encoded(value)).hexdigest()


def http_arguments(method, target, body=None):
    """Use the fixed operation contracts for identical HTTP and SDK routing."""
    names = ['project_files.status', *('project_files.' + action for action in PROJECT_ACTIONS)]
    names.extend(sorted(agent_api.PROJECT_FILES_M2 | agent_api.PROJECT_FILES_M3 | agent_api.PROJECT_FILES_M4))
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

    def __init__(self, control_path, roots, *, dsn=None, runtime_sources=None):
        from runtime_snapshots import configuration
        configured = {}
        for alias, config in (runtime_sources or {}).items():
            if (type(alias) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', alias)
                    or len(configured) >= 100):
                raise WorkbenchError('Configure at most 100 named current runtime sources.')
            configured[alias] = copy.deepcopy(configuration(config))
        self.path = Path(control_path).resolve()
        self.db = Metadata(self.path, dsn=dsn)
        self.lock = self.db.lock
        self.access = Access(self.db, self.path)
        self.custody = ProjectCustody(self.path, self.db.dataset_id)
        self._retained_recovery = None
        self._dsn = dsn
        self._runtime_sources = configured
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
                if error.code not in ('unknown', 'outcome_unknown', 'stale', 'stale_project',
                                       'invalid', 'unsupported', 'unavailable'):
                    raise
                self._recovery_required('unknown_publication' if error.code in ('unknown', 'outcome_unknown')
                                        else 'projection_unavailable')
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
        value = agent_api.capabilities(self.db.dataset_id, profile='project')
        for operation in value['operations']:
            if operation['id'].startswith('project_transfer.'):
                operation['availability'] = ('available' if getattr(self, 'transfer_controller', None)
                                             is not None else 'unavailable')
                continue
            if operation['id'] in agent_api.PROJECT_FILES_M2 and not M2_ENABLED:
                operation['availability'] = 'unavailable'
            if operation['id'] in agent_api.PROJECT_FILES_M3 and not M3_ENABLED:
                operation['availability'] = 'unavailable'
            if operation['id'] in agent_api.PROJECT_FILES_M4 and not M4_ENABLED:
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
        root_path, root_fd = self._roots[alias]
        from project_store import assert_separate_project_control
        assert_separate_project_control(root_fd, relative, root_path=root_path, control_path=self.path)
        return self._roots[alias]

    def _projection_for(self, store):
        identity = uuid.uuid4().hex
        path = self.path / '.project-projections' / identity
        snapshot = store.snapshot()
        projection = Metadata(path, dsn=self._dsn, dataset_id=snapshot['project_id'], projection_id=identity)
        try:
            owner = ProjectProjection(store, projection, self.access,
                                      {alias: value[0] for alias, value in self._roots.items()},
                                      custody=self.custody.for_projection(store, identity),
                                      runtime_sources=self._runtime_sources)
            owner.pending_original = self.custody.pending(store)
            if owner.pending_original:
                owner.session.available = False
            return owner, owner.text
        except BaseException:
            projection.close()
            # Disposable failed projections remain identified for diagnosis;
            # no authoritative bytes or an uncertain outcome is deleted.
            raise

    def _retained_projection_for(self, store, projection_id):
        if type(projection_id) is not str or not re.fullmatch('[a-f0-9]{32}', projection_id):
            raise WorkbenchError('Invalid original local projection identity.', 'unavailable', 409)
        db = Metadata(self.path / '.project-projections' / projection_id, dsn=self._dsn,
                      create=False, dataset_id=store.snapshot()['project_id'], projection_id=projection_id)
        try:
            return ProjectProjection(store, db, self.access,
                {alias: value[0] for alias, value in self._roots.items()},
                custody=self.custody.for_projection(store, projection_id), restore=False,
                runtime_sources=self._runtime_sources)
        except BaseException:
            db.close()
            raise

    def _detach(self):
        """Release only a project whose current local effects have drained."""
        if self._projection is not None:
            self._projection.execution.assert_quiescent()
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
        if self._projection is not None and self._projection.pending_original:
            raise WorkbenchError('Explicitly reconcile original-host custody before reopening this project.',
                                 'projection_unavailable', 503)
        if self._projection is not None and self._projection.execution.has_local_custody:
            # Retain actual local custody until the explicit execution recovery
            # boundary proves cessation; imported history can never do so.
            self._projection.execution.assert_quiescent()
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
        if self._projection is not None:
            self._projection.execution.assert_quiescent()
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

    def _save_as(self, arguments):
        """Publish a new independent project, then select a fresh inert cache."""
        from functools import partial
        from project_fork import publish_fork
        from project_fork_composition import build_candidate
        from workbench import timestamp
        self._bound(arguments)
        root_path, root_fd = self._root(arguments['root'], arguments['directory'])
        source = self._projection
        source.execution.assert_quiescent()
        source.files.require_clean()
        self._store.save(arguments['expected_checkpoint'])
        published = None
        incoming = projection = None
        try:
            published = publish_fork(self._store, source.artifacts, root_fd, arguments['directory'],
                root_path=root_path, name=arguments['name'],
                expected_checkpoint=arguments['expected_checkpoint'], request_key=arguments['request_key'],
                quiescent=True, build_candidate=partial(build_candidate, created_at=timestamp(),
                    id_factory=lambda _family, _source_id, _revision: uuid.uuid4().hex),
                validate_candidate=lambda records, identity: source.validate_records(records, project_id=identity))
            # A filesystem editor can act outside the workspace lock. Leave the
            # complete fork unselected if its source working files changed.
            source.files.require_clean()
            incoming = ProjectStore.open_at(root_fd, arguments['directory'], root_path=root_path)
            projection, text = self._projection_for(incoming)
            snapshot, overlay = published['snapshot'], published['fork']
            self._detach()
            self._store, self._projection, self._text = incoming, projection, text
            self._selection = arguments['root'], arguments['directory']
            self._last_project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
            self._recovery = None
            self._binding = uuid.uuid4().hex
            summary = dict(source_project_id=overlay['source']['project_id'],
                source_checkpoint=overlay['source']['checkpoint'], project_id=snapshot['project_id'],
                checkpoint=snapshot['checkpoint'], root=arguments['root'], directory=arguments['directory'],
                request_key=arguments['request_key'], reconciled=published['reconciled'],
                mapping_count=len(overlay['mapping']), copied_count=len(overlay['artifacts']['copied']),
                missing_regenerable_count=len(overlay['artifacts']['missing_regenerable']))
            return dict(state=self._state(), fork=summary)
        except BaseException as error:
            if projection is not None and projection is not self._projection:
                projection.close()
            if incoming is not None and incoming is not self._store:
                incoming.close()
            receipt = getattr(error, 'receipt', None)
            if published is not None:
                snapshot = published['snapshot']
                receipt = dict(committed=True, selected=False, project_id=snapshot['project_id'],
                    checkpoint=snapshot['checkpoint'], request_key=arguments['request_key'],
                    root=arguments['root'], directory=arguments['directory'])
            elif receipt is not None:
                receipt = dict(receipt, root=arguments['root'])
            if receipt is not None:
                failure = WorkbenchError('Independent project was published but could not be selected; retry this exact Save As.',
                                         'project_selection_unavailable', 503)
                failure.receipt = receipt
                raise failure from error
            raise

    def dispatch(self, name, arguments, *, selected_version=None):
        """Pin workspace -> current host authority -> projection through return.

        An old request cannot observe a new Dataset alias. Revocation cannot
        complete before an already-authorized canonical publication finishes.
        """
        agent_api.validate_arguments(name, arguments)
        if not name.startswith('project_files.'):
            raise WorkbenchError('This domain is unavailable in external text-project mode.', 'unavailable', 409)
        if name == 'project_files.execution_health':
            return self._execution_health(arguments, selected_version=selected_version)
        if name in _DRAINING_OPERATIONS:
            return self._dispatch_draining(name, arguments)
        action = name.removeprefix('project_files.')
        with self._mutex, self.access.lock:
            self._ensure_open()
            operation = agent_api.operation(name)
            for scope in operation['scopes']:
                if scope == 'execute' and action in ('execution_submit_external', 'execution_study_admit'):
                    self.access.require_external_submission()
                else:
                    self.access.require(scope, name, owner_only=action in ('new', 'open', 'save', 'save_as', 'close'))
            if selected_version == 1 and action in ('get', 'annotate'):
                self._bound(arguments, check_checkpoint=action == 'get')
                record = self._projection.data._require_record(arguments['record_id'])
                if record['document']['current']['provenance'].get('method') != 'import':
                    raise WorkbenchError('This retained text provenance requires project text contract version 2.',
                                         'unsupported', 409)
            if name in agent_api.PROJECT_FILES_M4 and not M4_ENABLED:
                raise WorkbenchError('This project capability is not yet available.', 'unavailable', 409)
            if name in (agent_api.PROJECT_FILES_M2 | agent_api.PROJECT_FILES_M3 | agent_api.PROJECT_FILES_M4) - {'project_files.save_as'}:
                if ((name in agent_api.PROJECT_FILES_M2 and not M2_ENABLED)
                        or (name in agent_api.PROJECT_FILES_M3 and not M3_ENABLED)
                        or (name in agent_api.PROJECT_FILES_M4 and not M4_ENABLED)):
                    raise WorkbenchError('This project capability is not yet available.', 'unavailable', 409)
                self._bound(arguments, check_checkpoint=not operation['side_effects'])
                from project_dispatch import dispatch
                try:
                    value = dispatch(self._projection, name, arguments)
                    if name == 'project_files.execution_health' and selected_version == 1:
                        value = {key: item for key, item in value.items() if key != 'native_phases'}
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
                    prior_state = prior[1]['state'] if action == 'save_as' else prior[1]
                    if prior_state != self._state():
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
                        elif action == 'save_as':
                            result = self._save_as(arguments)
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
                        if action != 'save_as' and code in ('unknown', 'outcome_unknown', 'projection_unavailable'):
                            reason = 'unknown_publication' if code in ('unknown', 'outcome_unknown') else 'projection_unavailable'
                            self._recovery_required(reason, arguments.get('request_key'))
                        raise
                    if arguments.get('request_key') and action in ('new', 'open', 'save', 'save_as', 'close'):
                        self._receipts[key] = (signature, copy.deepcopy(result))
            if len(agent_api.encoded(result)) > agent_api.RESPONSE_LIMIT:
                raise WorkbenchError('This project result exceeds the synchronous response bound; canonical work is retained.',
                                     'too_large', 413)
            agent_api.validate_output(name, {'status': 200, 'result': result},version=selected_version)
            return result

    def _dispatch_draining(self, name, arguments):
        """Keep workspace selection pinned while descendants drain without SQL locks."""
        with self._mutex:
            with self.access.lock:
                self._ensure_open()
                if not M3_ENABLED:
                    raise WorkbenchError('This project capability is not yet available.', 'unavailable', 409)
                operation = agent_api.operation(name)
                for scope in operation['scopes']:
                    self.access.require(scope, name, owner_only=name in _RECOVERY_OPERATIONS)
                recovery_operation = name in _RECOVERY_OPERATIONS
                if recovery_operation and self._projection is not None and not self._projection.session.available:
                    self._recovery_required('projection_unavailable', arguments.get('request_key'))
                self._bound(arguments, check_checkpoint=recovery_operation and name != 'project_files.runtime_capture',
                            allow_recovery=recovery_operation)
                projection = self._projection
                recovering = self._recovery is not None or not projection.session.available
            from project_dispatch import dispatch
            try:
                incoming = projection
                if recovery_operation and projection.pending_original:
                    if len(projection.pending_original) != 1:
                        raise WorkbenchError('More than one original local custody binding needs explicit review.',
                                             'local_custody_unavailable', 409)
                    binding = projection.pending_original[0]
                    if binding['project_id'] != projection.session.project_id:
                        raise WorkbenchError('Restore the original project identity before reconciling this physical folder custody.',
                                             'local_custody_unavailable', 409)
                    if self._retained_recovery is None:
                        self._retained_recovery = self._retained_projection_for(self._store, binding['projection_id'])
                    incoming = self._retained_recovery
                    if incoming.db.projection_id != binding['projection_id']:
                        raise WorkbenchError('The retained physical recovery owner changed.', 'local_custody_unavailable', 409)
                    recovering = True
                if incoming is not projection and name == 'project_files.execution_reconcile_current':
                    value = incoming.execution.reconcile_original(expected_checkpoint=incoming.session.snapshot['checkpoint'])
                else:
                    internal = arguments
                    if recovery_operation and recovering and name != 'project_files.execution_reconcile_current':
                        # Public CAS above uses the last acknowledged workspace
                        # view. Only this qualified local owner sees its exact
                        # selected/attempted checkpoint for finite recovery.
                        internal = dict(arguments, expected_checkpoint=incoming.session.snapshot['checkpoint'])
                    if name == 'project_files.runtime_capture' and recovering:
                        options = {'reserve_bytes': internal['reserve_bytes']} if 'reserve_bytes' in internal else {}
                        value = incoming.runtime.recover_capture({'source': internal['source']},
                            internal['expected_inventory_sha256'], internal['expected_checkpoint'],
                            internal['request_key'], **options)
                    else:
                        value = dispatch(incoming, name, internal)
                if recovery_operation:
                    if not incoming.session.available or incoming.custody is not None and incoming.custody.has_pending:
                        raise WorkbenchError('Original writer custody remains unresolved.', 'outcome_unknown', 409)
                    if incoming is not projection:
                        incoming.execution.assert_quiescent()
                        projection.close()
                        projection = self._projection = incoming
                        self._text = incoming.text
                        self._retained_recovery = None
                        # Physical cache repair retains this same selected
                        # project and workspace generation; it is not Open.
            except BaseException as error:
                if getattr(error, 'code', None) in ('unknown', 'outcome_unknown', 'projection_unavailable'):
                    self._recovery_required('projection_unavailable', arguments.get('request_key'))
                raise
            with self.access.lock, projection.session.lock, projection.db.lock:
                snapshot = self._store.snapshot()
                self._last_project = {key: snapshot[key] for key in ('project_id', 'name', 'checkpoint')}
                if name in _RECOVERY_OPERATIONS:
                    self._recovery = None
                result = dict(binding=self._binding, project_id=snapshot['project_id'],
                              checkpoint=snapshot['checkpoint'], value=value)
                if len(agent_api.encoded(result)) > agent_api.RESPONSE_LIMIT:
                    raise WorkbenchError('Project drainage result exceeds its response bound.', 'too_large', 413)
                agent_api.validate_output(name, {'status': 200, 'result': result})
                return result

    def _execution_health(self, arguments, *, selected_version=None):
        """Read only indexed current-local custody, including a fenced owner."""
        name='project_files.execution_health'
        with self._mutex,self.access.lock:
            self._ensure_open()
            if not M3_ENABLED:raise WorkbenchError('This project capability is not yet available.','unavailable',409)
            self.access.require('inspect',name)
            if self._projection is not None and not self._projection.session.available:
                self._recovery_required('projection_unavailable')
            self._bound(dict(arguments,expected_checkpoint=arguments['checkpoint']),allow_recovery=True)
            incoming=self._projection
            if incoming.pending_original:
                if len(incoming.pending_original)!=1 or incoming.pending_original[0]['project_id']!=incoming.session.project_id:
                    raise WorkbenchError('Original local custody requires its exact project identity.','local_custody_unavailable',409)
                identity=incoming.pending_original[0]['projection_id']
                if self._retained_recovery is None:
                    self._retained_recovery=self._retained_projection_for(self._store,identity)
                incoming=self._retained_recovery
                if incoming.db.projection_id!=identity:
                    raise WorkbenchError('Original physical custody changed.','local_custody_unavailable',409)
            value=incoming.execution.health(arguments.get('offset',0),arguments.get('limit',40))
            if selected_version==1:value={key:item for key,item in value.items() if key!='native_phases'}
            result=dict(binding=self._binding,project_id=incoming.session.project_id,
                checkpoint=arguments['checkpoint'],value=value)
            if len(agent_api.encoded(result))>agent_api.RESPONSE_LIMIT:
                raise WorkbenchError('Current custody health exceeds its response bound.','too_large',413)
            agent_api.validate_output(name,dict(status=200,result=result),version=selected_version)
            return result

    def close(self):
        with self._mutex:
            if self._closed:
                return
            # Shutdown always releases handles, including a stale/unknown store;
            # actual local workers drain before any database handle is closed.
            if self._projection is not None:
                self._projection.execution.shutdown()
                self._projection.close()
            if self._store is not None:
                self._store.close()
            self._projection = self._text = self._store = None
            for _path, fd in self._roots.values():
                os.close(fd)
            self._roots.clear()
            self.db.close()
            self._closed = True
