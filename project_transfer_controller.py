"""Explicit process-local legacy extraction and independent workspace selection.

The live Dataset is supplied by its existing controller. Stopping never imports
its credentials into the separate control host. Only that Dataset can issue a
StoppedSourceLease; requests carry a controller binding and report hashes, never
serialized cessation evidence or filesystem descriptors.
"""
import copy
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import re
import threading
import uuid

from project_store import _open_directory_path, _verify_origin, REQUEST_KEY
from project_transfer import ProjectTransfer, preview_source, normalize_selection, canonical, leaf, sha
from project_fork import _inside
from workbench import WorkbenchError

SECTIONS = frozenset(('included', 'required', 'unassigned', 'excluded', 'blockers', 'warnings', 'artifacts', 'working_files'))
OPERATIONS = frozenset('project_transfer.' + name for name in ('status', 'preview', 'report_page', 'stop', 'extract'))
MAX_RESPONSE = 1024 * 1024


def fail(message, code='invalid', status=400):
    raise WorkbenchError(message, code, status)


def _identity(descriptor):
    value = os.fstat(descriptor)
    return value.st_dev, value.st_ino


def _bounded(value):
    if len(canonical(value)) > MAX_RESPONSE:
        fail('Extraction controller response exceeds its bounded interface.', 'too_large', 413)
    return value


def _receipt_summary(value):
    if value.get('format') != 'project_extraction_receipt_v1':
        fields = ('committed', 'selected', 'project_id', 'checkpoint', 'request_key', 'directory')
        return {key: copy.deepcopy(value[key]) for key in fields if key in value}
    return dict(format='project_transfer_receipt_v1', committed=value['committed'],
        project_id=value['project_id'], checkpoint=value['checkpoint'], request_key=value['request_key'],
        input_sha256=value['input_sha256'], report_sha256=value['report_sha256'], source=copy.deepcopy(value['source']),
        artifacts=dict(copied_count=len(value['artifacts']['copied']), missing_regenerable_count=len(value['artifacts']['missing_regenerable'])),
        verification=copy.deepcopy(value['verification']), replayed=value['replayed'])


class ProjectTransferController:
    def __init__(self, dataset, control_workspace, roots=None):
        from app import Dataset
        from project_workspace import ProjectWorkspace
        if not isinstance(dataset, Dataset) or not isinstance(control_workspace, ProjectWorkspace):
            fail('Extraction requires an existing legacy controller and a separate control workspace.', 'forbidden', 403)
        if dataset.db.dataset_id == control_workspace.db.dataset_id or dataset.db is control_workspace.db:
            fail('The control host must have independent current local authority.', 'forbidden', 403)
        self.dataset, self.workspace = dataset, control_workspace
        self._lock = threading.RLock()
        self._binding = uuid.uuid4().hex
        self._phase = 'source_live'
        self._closed = False
        self._roots = {}
        self._source = self._transfer = self._report = self._selection = None
        self._backup = self._destination = self._last_receipt = self._failure = None
        configured = roots if roots is not None else {alias: value[0] for alias, value in control_workspace._roots.items()}
        try:
            if type(configured) is not dict or not 1 <= len(configured) <= 100:
                fail('Configure one to 100 extraction publication roots.')
            for alias, path in configured.items():
                if type(alias) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', alias):
                    fail('Invalid extraction publication root alias.')
                absolute, descriptor = _open_directory_path(path)
                self._roots[alias] = (Path(absolute), descriptor)
            # Publication parents may contain the source as a sibling, but may
            # never be inside it. Nonexistent leaf targets are checked at Stop.
            _, source_fd = _open_directory_path(dataset.path)
            try:
                if any(_inside(descriptor, source_fd) for _, descriptor in self._roots.values()):
                    fail('Extraction publication roots cannot be inside the source catalog.', 'conflict', 409)
            finally:
                os.close(source_fd)
        except BaseException:
            self.close()
            raise

    @property
    def control_workspace(self):
        return self.workspace

    @property
    def phase(self):
        """Trusted root dispatch uses this only to choose request authentication."""
        return self._phase

    @property
    def access(self):
        return self.dataset.access if self._phase == 'source_live' else self.workspace.access

    def _authorize(self, action):
        if self._closed:
            fail('Extraction controller is closed.', 'unavailable', 503)
        self.access.require('admin', 'project_transfer.' + action, owner_only=True)

    def _bound(self, binding):
        if type(binding) is not str or binding != self._binding:
            fail('Extraction controller changed. Refresh its process binding.', 'stale', 409)

    def _root(self, alias):
        if type(alias) is not str or alias not in self._roots:
            fail('Choose a configured extraction publication root.')
        path, descriptor = self._roots[alias]
        _verify_origin(descriptor, path)
        return descriptor

    def _target(self, root, directory, *, may_exist=False, selectable=False):
        leaf(directory)
        descriptor = self._root(root)
        if selectable:
            configured = self.workspace._roots.get(root)
            if configured is None or _identity(configured[1]) != _identity(descriptor):
                fail('The destination root must also be configured in the control workspace.', 'conflict', 409)
        try:
            os.stat(directory, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if not may_exist:
                fail('Extraction publication destination already exists.', 'conflict', 409)
        return descriptor

    def _summary(self):
        if self._report is None:
            return None
        return dict(report_sha256=self._report['report_sha256'],
            selection_sha256=hashlib.sha256(canonical(self._selection)).hexdigest(),
            source=copy.deepcopy(self._report['source']), can_extract=self._report['can_extract'],
            counts={section: len(self._report[section]) for section in sorted(SECTIONS)})

    def _state(self):
        actions = ['status']
        if self._phase in ('source_live', 'source_stopped'):
            actions += ['preview', 'report_page']
        if self._phase == 'source_live' and self._report is not None:
            actions.append('stop')
        if self._phase == 'source_stopped' and self._report is not None:
            actions.append('extract')
        return _bounded(dict(format='project_transfer_state_v1', binding=self._binding,
            phase=self._phase, source_catalog_id=self.dataset.db.dataset_id,
            control_catalog_id=self.workspace.db.dataset_id, roots=sorted(self._roots),
            available_actions=actions, report=self._summary(), backup=copy.deepcopy(self._backup),
            destination=copy.deepcopy(self._destination), failure=copy.deepcopy(self._failure),
            last_receipt=copy.deepcopy(self._last_receipt)))

    def status(self):
        with self._lock:
            self._authorize('status')
            return self._state()

    def preview(self, binding, selection):
        with self._lock:
            self._authorize('preview');self._bound(binding)
            if self._phase not in ('source_live', 'source_stopped'):
                fail('The original controller remains fenced after an unsuccessful stop.', 'source_fenced', 409)
            normalized = normalize_selection(selection)
            if len(canonical(normalized)) > MAX_RESPONSE:
                fail('Extraction selection exceeds the request bound.', 'too_large', 413)
            if self._phase == 'source_live':
                if self._source is not None:
                    self._source.close()
                self._source = self._transfer = self._report = self._selection = None
                self._source = preview_source(self.dataset)
            # Retain only the reviewed report, rather than accumulating a
            # stopped transfer's full report cache across selection changes.
            self._selection = self._report = None
            self._transfer = ProjectTransfer(self._source)
            report = self._transfer.preview(normalized)
            self._selection, self._report = normalized, report
            self._failure = None
            return self._state()

    def report_page(self, binding, report_sha256, section, offset=0, limit=40):
        with self._lock:
            self._authorize('report_page');self._bound(binding);sha(report_sha256)
            if self._report is None or report_sha256 != self._report['report_sha256']:
                fail('The extraction report changed. Review the current report.', 'stale', 409)
            if type(section) is not str or section not in SECTIONS or type(offset) is not int or not 0 <= offset <= 1000000 or type(limit) is not int or not 1 <= limit <= 40:
                fail('Choose a known report section and bounded page.')
            values = self._report[section]
            return _bounded(dict(format='project_transfer_report_page_v1', binding=self._binding,
                report_sha256=report_sha256, section=section, items=copy.deepcopy(values[offset:offset + limit]),
                offset=offset, limit=limit, total=len(values)))

    def stop(self, binding, report_sha256, backup_root, backup_directory, destination_root, directory):
        with self._lock:
            self._authorize('stop');self._bound(binding);sha(report_sha256)
            if self._phase != 'source_live' or self._report is None or self._report['report_sha256'] != report_sha256:
                fail('Review this live source before its explicit stop.', 'stale', 409)
            backup_fd = self._target(backup_root, backup_directory)
            destination_fd = self._target(destination_root, directory, selectable=True)
            if _identity(backup_fd) == _identity(destination_fd) and backup_directory == directory:
                fail('Stopped backup and extracted project require different destinations.', 'conflict', 409)
            if self._source is not None:
                self._source.close();self._source = self._transfer = None
            # After any stop attempt, source authentication may be closed and
            # ordinary legacy routes remain fenced. No DTO can mint a lease.
            self._phase = 'source_fenced';self._binding = uuid.uuid4().hex
            self._report = None
            try:
                source = self.dataset.stop_for_project_extraction(backup_fd, backup_directory)
            except BaseException as error:
                # Native authorization can fail before it installs the source
                # request fence. Do not claim a stopped/fenced source or switch
                # authentication in that no-effect case.
                if not self.dataset._extraction_stopping:
                    self._phase = 'source_live'
                self._failure = dict(action='stop', code=getattr(error, 'code', 'unknown'), detail=str(error)[:1000])
                raise
            self._source, self._transfer = source, ProjectTransfer(source)
            self._phase = 'source_stopped'
            self._backup = dict(root=backup_root, directory=backup_directory,
                receipt_sha256=hashlib.sha256(canonical(source.backup_receipt)).hexdigest())
            self._destination = dict(root=destination_root, directory=directory)
            self._failure = None
            return self._state()

    def extract(self, binding, report_sha256, destination_root, directory, name, request_key):
        with self._lock:
            self._authorize('extract');self._bound(binding);sha(report_sha256)
            if self._phase != 'source_stopped' or self._transfer is None:
                fail('A trusted stopped source is required before extraction.', 'source_fenced', 409)
            if self._report is None or report_sha256 != self._report['report_sha256']:
                fail('Review the exact stopped-source report before extraction.', 'stale', 409)
            if type(name) is not str or not name.strip() or len(name) > 200 or type(request_key) is not str or not REQUEST_KEY.fullmatch(request_key):
                fail('Choose an extraction name and exact request key.')
            destination_fd = self._target(destination_root, directory, may_exist=True, selectable=True)
            if self._backup is not None and _identity(destination_fd) == _identity(self._root(self._backup['root'])) and directory == self._backup['directory']:
                fail('Extraction cannot replace its stopped backup.', 'conflict', 409)
            # Pin selection before authority, matching Workspace's lock order.
            # An already selected destination owns its Store writer lock; only
            # its actual pinned Store can reconcile that exact destination.
            try:
                with self.workspace._mutex, self.workspace.access.lock, ExitStack() as guards:
                    self._authorize('extract')
                    opened = None
                    if self.workspace._selection == (destination_root, directory) and self.workspace._store is not None:
                        projection = self.workspace._projection
                        if projection is None or self.workspace._recovery is not None:
                            fail('Recover the selected workspace before reconciling extraction.', 'projection_unavailable', 503)
                        guards.enter_context(projection.session.lock)
                        guards.enter_context(projection.db.lock)
                        projection.session.check()
                        opened = self.workspace._store
                    receipt = self._transfer.extract(self._selection, report_sha256, destination_fd, directory, name, request_key, opened_store=opened)
            except BaseException as error:
                self._failure = dict(action='extract', code=getattr(error, 'code', 'unknown'), detail=str(error)[:1000])
                if getattr(error, 'receipt', None) is not None:
                    self._last_receipt = _receipt_summary(error.receipt)
                if getattr(error, 'staging_directory', None) is not None:
                    self._failure['staging_directory'] = error.staging_directory
                raise
            self._last_receipt = _receipt_summary(receipt)
            self._destination = dict(root=destination_root, directory=directory)
            self._failure = None
            selected, state, selection_error = False, None, None
            try:
                state = self.workspace.dispatch('project_files.status', {})
                arguments = dict(binding=state['binding'], expected_checkpoint=state['project']['checkpoint'] if state['project'] else None,
                    root=destination_root, directory=directory, request_key='extract-open.' + hashlib.sha256(request_key.encode()).hexdigest()[:32])
                state = self.workspace.dispatch('project_files.open', arguments)
                if state['project'] is None or state['project']['project_id'] != receipt['project_id']:
                    fail('Workspace selected a different project.', 'project_selection_unavailable', 503)
                selected = True
            except BaseException as error:
                selection_error = dict(code=getattr(error, 'code', 'unknown'), detail=str(error)[:1000])
            return _bounded(dict(format='project_transfer_extraction_result_v1', binding=self._binding,
                receipt=_receipt_summary(receipt), selection=dict(selected=selected, state=state, error=selection_error)))

    def dispatch(self, name, arguments):
        """The root transport admits only these five named, closed methods."""
        fields = {
            'project_transfer.status': set(),
            'project_transfer.preview': {'binding', 'selection'},
            'project_transfer.report_page': {'binding', 'report_sha256', 'section', 'offset', 'limit'},
            'project_transfer.stop': {'binding', 'report_sha256', 'backup_root', 'backup_directory', 'destination_root', 'directory'},
            'project_transfer.extract': {'binding', 'report_sha256', 'destination_root', 'directory', 'name', 'request_key'}}
        if type(name) is not str or name not in OPERATIONS or type(arguments) is not dict or set(arguments) - fields[name]:
            fail('Unsupported extraction controller action.', 'unsupported', 409)
        required = fields[name] - ({'offset', 'limit'} if name == 'project_transfer.report_page' else set())
        if not required <= set(arguments):
            fail('Missing extraction controller arguments.')
        if name == 'project_transfer.status':return self.status()
        if name == 'project_transfer.preview':return self.preview(arguments['binding'], arguments['selection'])
        if name == 'project_transfer.report_page':return self.report_page(arguments['binding'], arguments['report_sha256'], arguments['section'], arguments.get('offset', 0), arguments.get('limit', 40))
        if name == 'project_transfer.stop':return self.stop(arguments['binding'], arguments['report_sha256'], arguments['backup_root'], arguments['backup_directory'], arguments['destination_root'], arguments['directory'])
        return self.extract(arguments['binding'], arguments['report_sha256'], arguments['destination_root'], arguments['directory'], arguments['name'], arguments['request_key'])

    def close(self):
        with self._lock:
            if self._closed:return
            self._closed = True
            try:
                if self._source is not None:self._source.close()
            finally:
                for _, descriptor in self._roots.values():os.close(descriptor)
                self._roots.clear()
