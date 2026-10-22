"""Small consumer workflows over the negotiated local AgentClient.

Import is standard-library-only. Each WorkflowClient exclusively owns its
AgentClient while a workflow runs; callers must not share it concurrently.
Execution, disclosure, comparison and grants remain server-owned.
"""
import copy
from contextlib import contextmanager, nullcontext
import hashlib
import math
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time

from agent_api import (ProjectTransferOwnerClient, AgentAPIError, AgentClient, contract, encoded, validate_arguments,
                       verify_artifact, verify_publication_artifact, validate_artifact_segments,
                       validate_segment, validate_publication_segment)

MAX_ITEMS = 20
MAX_COLLECTION_BYTES = 512 * 1024 * 1024
MAX_BATCH_BYTES = 8 * 1024 * 1024
TERMINAL = frozenset(('completed', 'failed', 'cancelled', 'interrupted', 'unknown'))
SUBMISSIONS = frozenset(('runs.submit_external', 'studies.admit'))
COMPARISONS = frozenset(('runs.compare_model_evidence', 'runs.compare_publication_evidence'))


def _closed(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise AgentAPIError('Invalid workflow document fields.')


def _digest(value):
    try:
        return hashlib.sha256(encoded(value)).hexdigest()
    except (TypeError, ValueError, RecursionError):
        raise AgentAPIError('Invalid bounded workflow JSON.') from None


def _domain_digest(value):
    # workbench.encode / pipeline.digest: domain content uses canonical UTF-8.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _error(error):
    return {'code': error.code, 'error': str(error), 'status': error.status}


def _invoke(client, operation, arguments):
    envelope = client.call(operation, arguments)
    if envelope['status'] >= 400:
        error = envelope['result']
        raise AgentAPIError(error['error'], error.get('code', 'http_error'), envelope['status'],
                            preflight_report=error.get('preflight_report'), receipt=error.get('receipt'))
    return envelope['result']


def _manifest(catalog_id, operation, arguments, kind):
    result = {'format': kind, 'catalog_id': catalog_id, 'operation': operation,
              'arguments': copy.deepcopy(arguments)}
    return dict(result, sha256=_digest(result))


def _check_manifest(value, catalog_id, kind, operations):
    _closed(value, ('format', 'catalog_id', 'operation', 'arguments', 'sha256'))
    body = {key: child for key, child in value.items() if key != 'sha256'}
    if (value['format'] != kind or value['catalog_id'] != catalog_id
            or type(value['operation']) is not str or value['operation'] not in operations or _digest(body) != value['sha256']):
        raise AgentAPIError('Workflow manifest identity differs.', 'conflict', 409)
    version = 2 if value['operation'] == 'runs.compare_model_evidence' else None
    if version is None:
        validate_arguments(value['operation'], value['arguments'])
    else:
        validate_arguments(value['operation'], value['arguments'], version)
    if value['operation'] in SUBMISSIONS and 'approval_id' not in value['arguments']:
        raise AgentAPIError('Select an existing owner approval_id for the reviewed material.')
    return copy.deepcopy(value)


@contextmanager
def _private_output(destination, *, before_publish=None):
    """One private provisional file, file fsync and atomic no-clobber publication."""
    destination = Path(destination)
    if os.path.lexists(destination):
        raise AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409)
    fd, provisional = tempfile.mkstemp(prefix='.tuldok-download-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        if before_publish is not None:
            before_publish()
        os.link(provisional, destination, follow_symlinks=False)
    except FileExistsError:
        raise AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409) from None
    finally:
        os.unlink(provisional)


def download(client, run_id, name, expected_sha256, destination, *, result_ref=None,
             chunk_bytes=8*1024*1024, cancelled=None, expected_bytes=None):
    """Verify whole bytes, fsync and atomically link a new private file.

    Incomplete segments are disposable, including cancellation. A future explicit
    collection resumes this item at zero rather than trusting a partial prefix.
    """
    destination = Path(destination)
    with _private_output(destination) as handle:
        def consume(raw):
            if cancelled is not None and cancelled.is_set():
                raise AgentAPIError('Collection stopped; compute cancellation was not requested.', 'stopped', 409)
            handle.write(raw)
            if expected_bytes is not None and handle.tell() > expected_bytes:
                raise AgentAPIError('Artifact exceeds selected inventory bytes.', 'artifact_mismatch', 409)
        receipt = (verify_artifact(client, run_id, name, expected_sha256, consume=consume, chunk_bytes=chunk_bytes)
                   if result_ref is None else verify_publication_artifact(client, result_ref, name,
                       expected_sha256, consume=consume, chunk_bytes=chunk_bytes))
        if expected_bytes is not None and receipt['bytes'] != expected_bytes:
            raise AgentAPIError('Artifact size differs from selected inventory.', 'artifact_mismatch', 409)
        if cancelled is not None and cancelled.is_set():
            raise AgentAPIError('Collection stopped; compute cancellation was not requested.', 'stopped', 409)
    return dict(receipt, run_id=run_id, name=name, output=str(destination))


def _verified_local(path, item):
    """Reopen resumed success without following links; never trust a receipt alone."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size != item['bytes']
                or before.st_uid != os.getuid() or before.st_mode & 0o077):
            raise AgentAPIError('Resumed artifact is not a private exact regular file.', 'artifact_mismatch', 409)
        checksum = hashlib.sha256()
        remaining = item['bytes']
        while remaining:
            raw = os.read(fd, min(65536, remaining))
            if not raw:
                break
            checksum.update(raw)
            remaining -= len(raw)
        after = os.fstat(fd)
        current = os.stat(path, follow_symlinks=False)
        if ((current.st_dev, current.st_ino) != (after.st_dev, after.st_ino)
                or remaining or checksum.hexdigest() != item['sha256']
                or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                   (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise AgentAPIError('Resumed artifact differs from its exact whole hash.', 'artifact_mismatch', 409)
    finally:
        os.close(fd)


class ProjectTransferClient:
    """Five explicit extraction actions with independently configured owner access.

    Stop ends the source client's authority. Obtain current-control credentials
    separately and construct a new client before stopped preview or extraction.
    """
    def __init__(self,client):self.client=client

    @classmethod
    def from_config(cls,path):return cls(ProjectTransferOwnerClient.from_config(path))

    def _call(self,action,arguments):
        name='project_transfer.'+action
        validate_arguments(name,arguments)
        return _invoke(self.client,name,arguments)

    def status(self):return self._call('status',{})

    def preview(self,selection,*,binding):return self._call('preview',dict(binding=binding,selection=selection))

    def report_page(self,*,binding,report_sha256,section,offset=0,limit=40):
        return self._call('report_page',dict(binding=binding,report_sha256=report_sha256,section=section,offset=offset,limit=limit))

    def stop(self,*,binding,report_sha256,backup_root,backup_directory,destination_root,directory):
        return self._call('stop',dict(binding=binding,report_sha256=report_sha256,backup_root=backup_root,
            backup_directory=backup_directory,destination_root=destination_root,directory=directory))

    def extract(self,*,binding,report_sha256,destination_root,directory,name,request_key):
        return self._call('extract',dict(binding=binding,report_sha256=report_sha256,destination_root=destination_root,
            directory=directory,name=name,request_key=request_key))


class ProjectFilesClient:
    """Thin, explicit checkpoint-bound file-project calls; never retries a mutation.

    Retain each request_key until its outcome is known. Binding and checkpoint
    come from status or the last acknowledged project response, never a local
    project path or a logical project UUID.
    """
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_config(cls, path):
        return cls(AgentClient.from_config(path))

    def _call(self, action, arguments):
        operation = 'project_files.' + action
        validate_arguments(operation, arguments)
        return _invoke(self.client, operation, arguments)

    def status(self):
        return self._call('status', {})

    def new(self, *, root, directory, name, binding, expected_checkpoint, request_key):
        return self._call('new', dict(root=root, directory=directory, name=name,
            binding=binding, expected_checkpoint=expected_checkpoint, request_key=request_key))

    def open(self, *, root, directory, binding, expected_checkpoint, request_key):
        return self._call('open', dict(root=root, directory=directory,
            binding=binding, expected_checkpoint=expected_checkpoint, request_key=request_key))

    def save(self, *, binding, expected_checkpoint, request_key):
        return self._call('save', dict(binding=binding,
            expected_checkpoint=expected_checkpoint, request_key=request_key))

    def close(self, *, binding, expected_checkpoint, request_key):
        return self._call('close', dict(binding=binding,
            expected_checkpoint=expected_checkpoint, request_key=request_key))

    def query(self, *, binding, checkpoint, after_id=None, limit=None):
        arguments = dict(binding=binding, checkpoint=checkpoint)
        if after_id is not None:
            arguments['after_id'] = after_id
        if limit is not None:
            arguments['limit'] = limit
        return self._call('query', arguments)

    def get(self, record_id, *, binding, checkpoint, before_revision=None, history_limit=None):
        arguments = dict(record_id=record_id, binding=binding, checkpoint=checkpoint)
        if before_revision is not None:
            arguments['before_revision'] = before_revision
        if history_limit is not None:
            arguments['history_limit'] = history_limit
        return self._call('get', arguments)

    def import_text(self, asset, *, binding, expected_checkpoint, request_key):
        return self._call('import_text', dict(asset=copy.deepcopy(asset), binding=binding,
            expected_checkpoint=expected_checkpoint, request_key=request_key))

    def annotate(self, record_id, annotation, *, binding, expected_checkpoint, request_key):
        return self._call('annotate', dict(record_id=record_id,
            annotation=copy.deepcopy(annotation), binding=binding,
            expected_checkpoint=expected_checkpoint, request_key=request_key))

    def artifact_status(self, **arguments):
        """artifact status; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('artifact_status', arguments)

    def artifacts(self, **arguments):
        """artifacts; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('artifacts', arguments)

    def candidate(self, **arguments):
        """candidate; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('candidate', arguments)

    def candidate_select(self, **arguments):
        """candidate select; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('candidate_select', arguments)

    def data_annotate(self, **arguments):
        """data annotate; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_annotate', arguments)

    def data_availability(self, **arguments):
        """data availability; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_availability', arguments)

    def data_get(self, **arguments):
        """data get; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_get', arguments)

    def data_history(self, **arguments):
        """data history; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_history', arguments)

    def data_import_audio(self, **arguments):
        """data import audio; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_audio', arguments)

    def data_import_image(self, **arguments):
        """data import image; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_image', arguments)

    def data_import_mesh(self, **arguments):
        """data import mesh; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_mesh', arguments)

    def data_import_pointcloud(self, **arguments):
        """data import pointcloud; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_pointcloud', arguments)

    def data_import_sequence(self, **arguments):
        """data import sequence; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_sequence', arguments)

    def data_import_text(self, **arguments):
        """data import text; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_text', arguments)

    def data_import_volume(self, **arguments):
        """data import volume; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_import_volume', arguments)

    def data_preference_delete(self, **arguments):
        """data preference delete; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_preference_delete', arguments)

    def data_preference_history(self, **arguments):
        """data preference history; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_preference_history', arguments)

    def data_preference_save(self, **arguments):
        """data preference save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_preference_save', arguments)

    def data_preferences(self, **arguments):
        """data preferences; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_preferences', arguments)

    def data_query(self, **arguments):
        """data query; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_query', arguments)

    def data_response_history(self, **arguments):
        """data response history; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_response_history', arguments)

    def data_response_save(self, **arguments):
        """data response save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_response_save', arguments)

    def data_responses(self, **arguments):
        """data responses; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_responses', arguments)

    def data_rights(self, **arguments):
        """data rights; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_rights', arguments)

    def data_source_delete(self, **arguments):
        """data source delete; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_source_delete', arguments)

    def data_source_save(self, **arguments):
        """data source save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('data_source_save', arguments)

    def evidence(self, **arguments):
        """evidence; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('evidence', arguments)

    def expose_holdout(self, **arguments):
        """expose holdout; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('expose_holdout', arguments)

    def graph_clone(self, **arguments):
        """graph clone; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('graph_clone', arguments)

    def graph_create(self, **arguments):
        """graph create; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('graph_create', arguments)

    def graph_get(self, **arguments):
        """graph get; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('graph_get', arguments)

    def graph_save(self, **arguments):
        """graph save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('graph_save', arguments)

    def graphs(self, **arguments):
        """graphs; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('graphs', arguments)

    def lineage(self, **arguments):
        """lineage; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('lineage', arguments)

    def lineage_record(self, **arguments):
        """lineage record; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('lineage_record', arguments)

    def model_create(self, **arguments):
        """model create; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('model_create', arguments)

    def model_get(self, **arguments):
        """model get; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('model_get', arguments)

    def model_material(self, **arguments):
        """model material; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('model_material', arguments)

    def model_publish(self, **arguments):
        """model publish; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('model_publish', arguments)

    def model_save(self, **arguments):
        """model save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('model_save', arguments)

    def models(self, **arguments):
        """models; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('models', arguments)

    def policies(self, **arguments):
        """policies; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('policies', arguments)

    def policy(self, **arguments):
        """policy; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('policy', arguments)

    def producer(self, **arguments):
        """producer; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('producer', arguments)

    def producers(self, **arguments):
        """producers; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('producers', arguments)

    def recipe_create(self, **arguments):
        """recipe create; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('recipe_create', arguments)

    def recipe_get(self, **arguments):
        """recipe get; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('recipe_get', arguments)

    def recipe_material(self, **arguments):
        """recipe material; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('recipe_material', arguments)

    def recipe_prepare(self, **arguments):
        """recipe prepare; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('recipe_prepare', arguments)

    def recipe_save(self, **arguments):
        """recipe save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('recipe_save', arguments)

    def recipes(self, **arguments):
        """recipes; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('recipes', arguments)

    def release_freeze(self, **arguments):
        """release freeze; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('release_freeze', arguments)

    def release_preview(self, **arguments):
        """release preview; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('release_preview', arguments)

    def retained_analysis(self, **arguments):
        """retained analysis; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('retained_analysis', arguments)

    def retained_analysis_export(self, **arguments):
        """retained analysis export; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('retained_analysis_export', arguments)

    def run(self, **arguments):
        """run; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('run', arguments)

    def runtime_material(self, **arguments):
        """runtime material; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('runtime_material', arguments)

    def search_create(self, **arguments):
        """search create; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('search_create', arguments)

    def search_delete(self, **arguments):
        """search delete; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('search_delete', arguments)

    def search_rename(self, **arguments):
        """search rename; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('search_rename', arguments)

    def searches(self, **arguments):
        """searches; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('searches', arguments)

    def selection_create(self, **arguments):
        """selection create; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('selection_create', arguments)

    def selection_delete(self, **arguments):
        """selection delete; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('selection_delete', arguments)

    def selection_get(self, **arguments):
        """selection get; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('selection_get', arguments)

    def selection_rename(self, **arguments):
        """selection rename; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('selection_rename', arguments)

    def selections(self, **arguments):
        """selections; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('selections', arguments)

    def snapshot(self, **arguments):
        """snapshot; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('snapshot', arguments)

    def studies(self, **arguments):
        """studies; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('studies', arguments)

    def study(self, **arguments):
        """study; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('study', arguments)

    def study_create(self, **arguments):
        """study create; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('study_create', arguments)

    def study_save(self, **arguments):
        """study save; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('study_save', arguments)

    def trial(self, **arguments):
        """trial; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('trial', arguments)

    def trial_prepare(self, **arguments):
        """trial prepare; exact selected project checkpoint, existing domain validation, no execution."""
        return self._call('trial_prepare', arguments)


    def source_register(self, **arguments):
        return self._call('source_register', arguments)

    def data_import_scientific(self, **arguments):
        return self._call('data_import_scientific', arguments)

    def runs(self, **arguments):
        return self._call('runs', arguments)

    def materials(self, **arguments):
        return self._call('materials', arguments)

    def publication_result(self, **arguments):
        return self._call('publication_result', arguments)

    def package_state(self, **arguments):
        return self._call('package_state', arguments)

    def dependencies(self, **arguments):
        return self._call('dependencies', arguments)

    def definitions(self, **arguments):
        return self._call('definitions', arguments)

    def run_document_segment(self, **arguments):
        return self._call('run_document_segment', arguments)

    def source_references(self, **arguments):
        return self._call('source_references', arguments)

    def artifact_resolve(self, **arguments):
        return self._call('artifact_resolve', arguments)

    def graph_create_external(self, **arguments):
        return self._call('graph_create_external', arguments)

    def execution_health(self, **arguments):
        return self._call('execution_health', arguments)

    def execution_preflight_external(self, **arguments):
        return self._call('execution_preflight_external', arguments)

    def execution_approve_external(self, **arguments):
        return self._call('execution_approve_external', arguments)

    def execution_submit_external(self, **arguments):
        return self._call('execution_submit_external', arguments)

    def execution_cancel(self, **arguments):
        return self._call('execution_cancel', arguments)

    def execution_study_continue(self, **arguments):
        return self._call('execution_study_continue', arguments)

    def execution_study_approve(self, **arguments):
        return self._call('execution_study_approve', arguments)

    def execution_study_admit(self, **arguments):
        return self._call('execution_study_admit', arguments)

    def execution_study_stop(self, **arguments):
        return self._call('execution_study_stop', arguments)

    def execution_reconcile_current(self, **arguments):
        return self._call('execution_reconcile_current', arguments)

    def execution_producer_start(self, **arguments):
        return self._call('execution_producer_start', arguments)

    def execution_generation_resume(self, **arguments):
        return self._call('execution_generation_resume', arguments)

    def execution_grounded_review(self, **arguments):
        return self._call('execution_grounded_review', arguments)

    def execution_producer_decide(self, **arguments):
        return self._call('execution_producer_decide', arguments)

    def execution_producer_cancel(self, **arguments):
        return self._call('execution_producer_cancel', arguments)


    def execution_producer_health(self, **arguments):
        return self._call('execution_producer_health', arguments)

    def execution_study_prepare_package(self, **arguments):
        return self._call('execution_study_prepare_package',arguments)

    def execution_study_prepare_verifier(self, **arguments):
        return self._call('execution_study_prepare_verifier',arguments)

    def execution_study_abandon_preparation(self, **arguments):
        return self._call('execution_study_abandon_preparation',arguments)

    def execution_study_reconcile_preparation(self, **arguments):
        return self._call('execution_study_reconcile_preparation',arguments)

    def runtime_abandon(self, **arguments):
        return self._call('runtime_abandon',arguments)

    def runtime_sources(self, **arguments):
        return self._call('runtime_sources',arguments)

    def runtime_inspect(self, **arguments):
        return self._call('runtime_inspect',arguments)

    def runtime_capture(self, **arguments):
        return self._call('runtime_capture',arguments)

    def runtime_status(self, **arguments):
        return self._call('runtime_status',arguments)

    def save_as(self, *, root, directory, name, binding, expected_checkpoint, request_key):
        """Create and select an independent fork; never retry a mutation implicitly."""
        return self._call('save_as',dict(root=root,directory=directory,name=name,binding=binding,
            expected_checkpoint=expected_checkpoint,request_key=request_key))

    def files_inspect(self, **arguments):
        return self._call('files_inspect',arguments)

    def file_get(self, **arguments):
        return self._call('file_get',arguments)

    def file_history(self, **arguments):
        return self._call('file_history',arguments)

    def file_adopt(self, **arguments):
        return self._call('file_adopt',arguments)

    def material_intents(self, **arguments):
        return self._call('material_intents',arguments)

    def material_intent(self, **arguments):
        return self._call('material_intent',arguments)

    def material_intent_capabilities(self, **arguments):
        return self._call('material_intent_capabilities',arguments)

    def fork_info(self, **arguments):
        return self._call('fork_info',arguments)


class WorkflowClient:
    """Explicit, serial consumer of one privately configured AgentClient."""
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_config(cls, path):
        return cls(AgentClient.from_config(path))

    def submission_manifest(self, graph_id, revision, *, approval_id, request_key):
        """Read selected preflight; export existing grant + exact reviewed material."""
        prepared = _invoke(self.client, 'graphs.preflight_external', {'graph_id': graph_id, 'revision': revision})
        if (prepared['material']['catalog_id'] != self.client.catalog_id
                or prepared['graph_revision'] != revision
                or _domain_digest(prepared['material']) != prepared['material_sha256']):
            raise AgentAPIError('Selected preflight material differs.', 'conflict', 409)
        args = {'graph_id': graph_id, 'graph_revision': revision,
                'expected_digest': prepared['material_sha256'], 'approval_id': approval_id, 'request_key': request_key}
        validate_arguments('runs.submit_external', args)
        return _manifest(self.client.catalog_id, 'runs.submit_external', args, 'workflow_submission_manifest_v1')

    def trial_submission_manifest(self, trial_id, *, approval_id, request_key, parent_run_id=None):
        trial = _invoke(self.client, 'studies.trial', {'trial_id': trial_id})
        study = _invoke(self.client, 'studies.get', {'study_id': trial['study_id']})['study']
        if (trial['id'] != trial_id or trial['material']['catalog_id'] != self.client.catalog_id
                or study['id'] != trial['study_id']):
            raise AgentAPIError('Selected Trial belongs to another identity.', 'conflict', 409)
        args = {'study_id': trial['study_id'], 'revision': study['revision'],
                'admission_epoch': study['admission_epoch'], 'trial_id': trial_id,
                'approval_id': approval_id, 'request_key': request_key}
        if parent_run_id is not None:
            args['parent_run_id'] = parent_run_id
        validate_arguments('studies.admit', args)
        return _manifest(self.client.catalog_id, 'studies.admit', args, 'workflow_submission_manifest_v1')

    def submit(self, manifest):
        """One dispatch. Unknown delivery returns the same manifest for explicit reconciliation."""
        manifest = _check_manifest(manifest, self.client.catalog_id, 'workflow_submission_manifest_v1', SUBMISSIONS)
        operation, arguments = manifest['operation'], manifest['arguments']
        selected = self.client.selected_contracts()
        if operation not in selected:
            raise AgentAPIError('Submission has no compatible available contract.', 'operation_unsupported', 409)
        validate_arguments(operation, arguments, selected[operation])
        receipt = {'format': 'workflow_submission_receipt_v1', 'manifest': manifest}
        try:
            envelope = self.client.call(operation, arguments)
        except AgentAPIError as error:
            return dict(receipt, state='unknown', error=_error(error))
        if envelope['status'] >= 500 or envelope['result'].get('code') == 'commit_unknown':
            error = envelope['result']
            return dict(receipt, state='unknown', error={'code': error.get('code', 'http_error'),
                'error': error['error'], 'status': envelope['status']})
        if envelope['status'] >= 400:
            return dict(receipt, state='refused', envelope=envelope)
        try:
            if operation == 'runs.submit_external':
                run = envelope['result']
                if (run['request_key'] != arguments['request_key'] or run['dataset_id'] != self.client.catalog_id
                        or run['graph']['id'] != arguments['graph_id']
                        or run['graph_revision'] != arguments['graph_revision']
                        or run['material_sha256'] != arguments['expected_digest']
                        or run['approval_id'] != arguments['approval_id']):
                    raise ValueError()
            else:
                reservation = envelope['result']['reservation']
                run = envelope['result']['run']
                # experiments.Experiments.admit/1 owns this receipt identity.
                # Correlate its canonical request; do not reproduce budget policy.
                request_sha = _domain_digest({'operation_id': 'studies.admit', 'version': 1,
                    'contract_sha256': contract('studies.admit', 1)['sha256'],
                    'study_id': arguments['study_id'],
                    'body': {key: value for key, value in arguments.items() if key != 'study_id'}})
                if (any(reservation[key] != arguments[key] for key in
                        ('study_id', 'trial_id', 'request_key', 'admission_epoch'))
                        or reservation['run_id'] != run['id']
                        or reservation['request_sha256'] != request_sha
                        or reservation['parent_run_id'] != arguments.get('parent_run_id')
                        or run['parent_run_id'] != arguments.get('parent_run_id')
                        or run['dataset_id'] != self.client.catalog_id
                        or run['approval_id'] != arguments['approval_id']
                        or run['actor_id'] != reservation['actor_id']
                        or run['approval_material_sha256'] != reservation['material_sha256']
                        or any(run['study_membership'][key] != arguments[key] for key in ('study_id', 'trial_id'))):
                    raise ValueError()
        except (KeyError, TypeError, ValueError):
            return dict(receipt, state='unknown', error={'code': 'transport', 'status': 502,
                'error': 'Submission acknowledgement differs from its exact requested identity.'})
        return dict(receipt, state='acknowledged', envelope=envelope)

    def reconcile(self, unknown):
        if type(unknown) is not dict or set(unknown) not in (
                {'format', 'manifest', 'state', 'error'}, {'format', 'manifest', 'state', 'error', 'reconciliation'}):
            raise AgentAPIError('Reconcile requires the exact unknown submission receipt.')
        if unknown['format'] != 'workflow_submission_receipt_v1' or unknown['state'] != 'unknown':
            raise AgentAPIError('Reconcile requires the exact unknown submission receipt.')
        # Validate before the try: a changed manifest is an invalid local request,
        # not another observation of the original uncertain admission.
        _check_manifest(unknown['manifest'], self.client.catalog_id, 'workflow_submission_manifest_v1', SUBMISSIONS)
        try:
            current = self.submit(unknown['manifest'])
        except AgentAPIError as error:
            current = {'state': 'unknown', 'error': _error(error)}
        if current['state'] == 'acknowledged':
            return current
        # Later revocation/refusal cannot establish that an earlier unknown
        # mutation had no effect. Preserve its original uncertainty and identity.
        observation = {key: value for key, value in current.items() if key in ('state', 'error', 'envelope')}
        return dict(copy.deepcopy(unknown), reconciliation=observation)

    def monitor(self, run_id, *, timeout=60, cancelled=None, interval=.25, max_interval=5):
        """Bound read-only polling, bootstrap and blocking reads with one deadline."""
        for value in (timeout, interval, max_interval):
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise AgentAPIError('Monitoring requires finite positive budgets.')
        if interval > max_interval or timeout > 86400 or max_interval > 60:
            raise AgentAPIError('Monitoring budgets exceed the supported bounds.')
        stop = cancelled if cancelled is not None else threading.Event()
        deadline, delay, reads, latest = time.monotonic() + timeout, interval, 0, None
        def outcome(state):
            return {'state': state, 'run': latest, 'reads': reads, 'compute_cancel_requested': False}
        try:
            with self.client.read_budget(deadline, stop):
                validate_arguments('runs.get', {'run_id': run_id})
                while True:
                    if stop.is_set():
                        return outcome('stopped')
                    if time.monotonic() >= deadline:
                        return outcome('deadline')
                    latest = _invoke(self.client, 'runs.get', {'run_id': run_id})
                    reads += 1
                    if latest['id'] != run_id:
                        raise AgentAPIError('Monitor returned a different Run.', 'transport', 502)
                    if latest['state'] in TERMINAL:
                        return outcome('terminal')
                    # The selected Run contract has no Retry-After field. Server
                    # errors remain typed; capped delay is only for valid reads.
                    stop.wait(min(delay, max(0, deadline-time.monotonic())))
                    delay = min(max_interval, delay * 2)
        except AgentAPIError as error:
            if error.code in ('deadline', 'stopped'):
                return outcome(error.code)
            raise

    def cancel(self, run_id):
        run = _invoke(self.client, 'runs.cancel', {'run_id': run_id})
        if run['id'] != run_id:
            raise AgentAPIError('Cancellation returned a different Run.', 'transport', 502)
        drained = run.get('custody_phase') == 'drained'
        before_start = run['state'] == 'cancelled' and run.get('custody_phase') == 'prepared'
        return {'state': 'drained' if drained else 'cancelled_before_start' if before_start else 'requested',
                'drained': drained, 'run': run}

    def _result(self, source):
        if set(source) == {'run_id'}:
            value = _invoke(self.client, 'runs.get', source)
            if value['id'] != source['run_id'] or value.get('dataset_id') != self.client.catalog_id:
                raise AgentAPIError('Collection Run identity differs.', 'conflict', 409)
        elif set(source) == {'ref'}:
            value = _invoke(self.client, 'runs.publication_result', source)
            if value['result_ref'] != source['ref'] or value['catalog_id'] != self.client.catalog_id:
                raise AgentAPIError('Collection publication identity differs.', 'conflict', 409)
        else:
            raise AgentAPIError('Select one exact Run or publication Ref.')
        return value

    def _inventory(self, source):
        return self._artifact_inventory(self._result(source), source)

    @staticmethod
    def _artifact_inventory(value, source):
        try:
            artifacts = value['artifacts']
            if type(artifacts) is not list or len(artifacts) > 96:
                raise ValueError()
            inventory = []
            for item in artifacts:
                validate_arguments('runs.artifact_chunk', {
                    'run_id': source.get('run_id', source.get('ref', {}).get('run_id')),
                    'name': 'inventory-entry', 'expected_sha256': item['sha256'], 'offset': 0, 'max_bytes': 1})
                # Public inventory metadata can include artifact-manifest.json,
                # which the segment operation deliberately cannot select.
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', item['name']):
                    raise ValueError()
                if type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_COLLECTION_BYTES:
                    raise ValueError()
                inventory.append({key: item[key] for key in ('name', 'sha256', 'bytes')})
            if len({item['name'] for item in inventory}) != len(inventory):
                raise ValueError()
        except (KeyError, TypeError, ValueError, AgentAPIError):
            raise AgentAPIError('Selected artifact inventory is malformed or exceeds its bounds.', 'transport', 502) from None
        return sorted(inventory, key=lambda item: item['name'])

    def collection_manifest(self, *, names, run_id=None, result_ref=None):
        if (run_id is None) == (result_ref is None):
            raise AgentAPIError('Select one exact Run or publication Ref.')
        if (type(names) is not list or not 1 <= len(names) <= MAX_ITEMS
                or any(type(name) is not str for name in names) or len(set(names)) != len(names)):
            raise AgentAPIError('Select between 1 and 20 unique artifact names.')
        source = {'run_id': run_id} if result_ref is None else {'ref': copy.deepcopy(result_ref)}
        inventory = self._inventory(source)
        items = [item for item in inventory if item['name'] in names]
        if len(items) != len(names) or sum(item['bytes'] for item in items) > MAX_COLLECTION_BYTES:
            raise AgentAPIError('Selected artifacts are missing or exceed the aggregate collection bound.')
        body = {'format': 'workflow_collection_manifest_v1', 'catalog_id': self.client.catalog_id,
                'source': source, 'inventory_sha256': _digest(inventory), 'items': items}
        return self._validate_collection(dict(body, sha256=_digest(body)))

    def _validate_collection(self, manifest):
        _closed(manifest, ('format', 'catalog_id', 'source', 'inventory_sha256', 'items', 'sha256'))
        if (manifest['format'] != 'workflow_collection_manifest_v1' or manifest['catalog_id'] != self.client.catalog_id
                or manifest['sha256'] != _digest({k: v for k, v in manifest.items() if k != 'sha256'})
                or type(manifest['source']) is not dict or type(manifest['items']) is not list
                or not 1 <= len(manifest['items']) <= MAX_ITEMS):
            raise AgentAPIError('Invalid collection manifest.')
        source = manifest['source']
        if set(source) == {'run_id'}:
            operation = 'runs.artifact_chunk'
        elif set(source) == {'ref'}:
            operation = 'runs.publication_artifact_chunk'
        else:
            raise AgentAPIError('Select one exact Run or publication Ref.')
        inventory_hash = manifest['inventory_sha256']
        if (type(inventory_hash) is not str or len(inventory_hash) != 64
                or any(char not in '0123456789abcdef' for char in inventory_hash)):
            raise AgentAPIError('Invalid collection inventory identity.')
        names = []
        for item in manifest['items']:
            _closed(item, ('name', 'sha256', 'bytes'))
            if type(item['bytes']) is not int or not 0 <= item['bytes'] <= MAX_COLLECTION_BYTES:
                raise AgentAPIError('Invalid collection item byte bound.')
            validate_arguments(operation, dict(source, name=item['name'], expected_sha256=item['sha256'],
                offset=0, max_bytes=1))
            if 'ref' in source and source['ref']['catalog_id'] != self.client.catalog_id:
                raise AgentAPIError('Collection publication belongs to another catalog.', 'conflict', 409)
            names.append(item['name'])
        if len(set(names)) != len(names) or sum(item['bytes'] for item in manifest['items']) > MAX_COLLECTION_BYTES:
            raise AgentAPIError('Collection exceeds unique item or aggregate bounds.')
        return copy.deepcopy(manifest)

    def _check_collection(self, manifest):
        # Fresh transitive disclosure and exact inventory, including on resume.
        inventory = self._inventory(manifest['source'])
        if (_digest(inventory) != manifest['inventory_sha256']
                or any(item not in inventory for item in manifest['items'])):
            raise AgentAPIError('Selected inventory changed; explicit new selection required.', 'stale', 409)
        return copy.deepcopy(manifest)

    def collect(self, manifest, directory, *, resume=None, cancelled=None, chunk_bytes=8*1024*1024):
        """Sequential exact collection. Failure stops dispatch; explicit resume is required."""
        if cancelled is not None and not isinstance(cancelled, threading.Event):
            raise AgentAPIError('Collection cancellation must be a threading.Event.')
        if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 8*1024*1024:
            raise AgentAPIError('Invalid bounded collection segment size.')
        manifest = self._validate_collection(manifest)
        # Ordinary collection retains individual segmented reads. Explicit
        # collect_batch selects the separate negotiated batch operation.
        previous = {}
        if resume is not None:
            _closed(resume, ('format', 'manifest', 'state', 'items'))
            if (resume['format'] != 'workflow_collection_receipt_v1' or resume['manifest'] != manifest
                    or type(resume['items']) is not list or len(resume['items']) != len(manifest['items'])):
                raise AgentAPIError('Resume receipt differs from the exact collection manifest.', 'conflict', 409)
            for selected, result in zip(manifest['items'], resume['items']):
                if (type(result) is not dict or result.get('name') != selected['name']
                        or result.get('state') not in ('verified', 'refused', 'outstanding')):
                    raise AgentAPIError('Invalid resume item.')
                previous[result['name']] = result
        def stopped():
            return {'format': 'workflow_collection_receipt_v1', 'manifest': manifest, 'state': 'stopped',
                    'items': [copy.deepcopy(previous.get(item['name'], {'name': item['name'], 'state': 'outstanding'}))
                              for item in manifest['items']]}
        if cancelled is not None and cancelled.is_set():
            return stopped()
        try:
            budget = self.client.read_budget(None, cancelled) if cancelled is not None else nullcontext()
            with budget:
                self._check_collection(manifest)
                directory = Path(directory)
                if not directory.is_dir() or directory.is_symlink():
                    raise AgentAPIError('Collection destination must be an existing regular directory.')
                results, halted, freshly_verified = [], False, 0
                for item in manifest['items']:
                    name = item['name']
                    destination = directory / name
                    if halted or (cancelled is not None and cancelled.is_set()):
                        results.append(copy.deepcopy(previous.get(name, {'name': name, 'state': 'outstanding'})))
                        halted = True
                        continue
                    try:
                        if previous.get(name, {}).get('state') == 'verified':
                            # Reauthorize this artifact even when no local write is needed.
                            source = manifest['source']
                            operation = 'runs.publication_artifact_chunk' if 'ref' in source else 'runs.artifact_chunk'
                            _invoke(self.client, operation, dict(source, name=name, expected_sha256=item['sha256'], offset=0, max_bytes=1))
                            _verified_local(destination, item)
                            receipt = {'run_id': source.get('run_id', source.get('ref', {}).get('run_id')),
                                       'name': name, 'output': str(destination), 'sha256': item['sha256'],
                                       'bytes': item['bytes'], 'verification': 'whole_sha256_verified'}
                            if 'ref' in source:
                                receipt['result_ref'] = copy.deepcopy(source['ref'])
                        else:
                            source = manifest['source']
                            receipt = download(self.client, source.get('run_id', source.get('ref', {}).get('run_id')),
                                name, item['sha256'], destination, result_ref=source.get('ref'), chunk_bytes=chunk_bytes,
                                cancelled=cancelled, expected_bytes=item['bytes'])
                        results.append({'name': name, 'state': 'verified', 'receipt': receipt})
                        freshly_verified += 1
                    except (AgentAPIError, OSError) as error:
                        if isinstance(error, OSError):
                            error = AgentAPIError('Local collection file operation failed.', 'unavailable', 503)
                        results.append({'name': name, 'state': 'outstanding' if error.code == 'stopped' else 'refused', 'error': _error(error)})
                        halted = True
                state = ('stopped' if cancelled is not None and cancelled.is_set() else
                         'complete' if freshly_verified == len(manifest['items']) else 'partial')
                return {'format': 'workflow_collection_receipt_v1', 'manifest': manifest, 'state': state, 'items': results}

        except AgentAPIError as error:
            if error.code == 'stopped':
                return stopped()
            raise

    def collect_batch(self, manifest, directory, *, cancelled=None):
        """Explicit one-request whole-artifact collection; never fall back or retry.

        Use ordinary collect for larger selections or explicit receipt resume.
        Successful outputs preceding an item/local failure remain verified;
        later buffered items stay outstanding and are never silently retried.
        """
        if cancelled is not None and not isinstance(cancelled, threading.Event):
            raise AgentAPIError('Collection cancellation must be a threading.Event.')
        manifest = self._validate_collection(manifest)
        source = manifest['source']
        batch_source = ({'kind': 'run', 'run_id': source['run_id']} if 'run_id' in source else
                        {'kind': 'publication', 'ref': copy.deepcopy(source['ref'])})
        request = {'items': [dict(key='item-'+str(index), source=copy.deepcopy(batch_source),
                    name=item['name'], expected_sha256=item['sha256'], offset=0,
                    max_bytes=max(1, item['bytes'])) for index, item in enumerate(manifest['items'])]}
        if sum(item['max_bytes'] for item in request['items']) > MAX_BATCH_BYTES:
            raise AgentAPIError('Batch collection exceeds 8 MiB requested whole bytes; use explicit ordinary collect.', 'too_large', 413)
        validate_arguments('runs.artifact_segments', request, 1)
        results = [{'name': item['name'], 'state': 'outstanding'} for item in manifest['items']]

        def stopped():
            if cancelled is not None and cancelled.is_set():
                raise AgentAPIError('Collection stopped; compute cancellation was not requested.', 'stopped', 409)

        def receipt():
            state = ('stopped' if cancelled is not None and cancelled.is_set() else
                     'complete' if all(item['state'] == 'verified' for item in results) else 'partial')
            return {'format': 'workflow_collection_receipt_v1', 'manifest': manifest, 'state': state, 'items': results}

        try:
            stopped()
            directory = Path(directory)
            if not directory.is_dir() or directory.is_symlink():
                raise AgentAPIError('Collection destination must be an existing regular directory.')
            for index, item in enumerate(manifest['items']):
                if os.path.lexists(directory / item['name']):
                    error = AgentAPIError('Destination already exists; choose a new file.', 'conflict', 409)
                    results[index] = {'name': item['name'], 'state': 'refused', 'error': _error(error)}
                    return receipt()
            budget = self.client.read_budget(None, cancelled) if cancelled is not None else nullcontext()
            with budget:
                if self.client.selected_contracts().get('runs.artifact_segments') != 1:
                    raise AgentAPIError('Explicit batch collection has no supported negotiated contract.', 'operation_unsupported', 409)
                self._check_collection(manifest)
                stopped()
                value = _invoke(self.client, 'runs.artifact_segments', request)
                validate_artifact_segments(value, request)
                for index, (item, outcome, selected) in enumerate(zip(manifest['items'], value['items'], request['items'], strict=True)):
                    try:
                        stopped()
                        if outcome['status'] != 200:
                            raise AgentAPIError(outcome['error']['message'], outcome['error']['code'], outcome['status'])
                        segment = outcome['result']
                        raw = (validate_segment(segment, dict(selected, run_id=source['run_id'])) if 'run_id' in source else
                               validate_publication_segment(segment, dict(selected, ref=source['ref'])))
                        if (segment['total_bytes'] != item['bytes'] or len(raw) != item['bytes']
                                or segment['offset'] != 0 or segment['next_offset'] != item['bytes'] or not segment['eof']
                                or hashlib.sha256(raw).hexdigest() != item['sha256']):
                            raise AgentAPIError('Batch item does not match the selected whole length and SHA256.', 'artifact_mismatch', 409)
                        destination = directory / item['name']
                        with _private_output(destination, before_publish=stopped) as handle:
                            handle.write(raw)
                        proof = {'run_id': source.get('run_id', source.get('ref', {}).get('run_id')),
                                 'name': item['name'], 'output': str(destination), 'sha256': item['sha256'],
                                 'bytes': item['bytes'], 'verification': 'whole_sha256_verified'}
                        if 'ref' in source:
                            proof['result_ref'] = copy.deepcopy(source['ref'])
                        results[index] = {'name': item['name'], 'state': 'verified', 'receipt': proof}
                    except (AgentAPIError, OSError) as error:
                        if isinstance(error, OSError):
                            error = AgentAPIError('Local collection file operation failed.', 'unavailable', 503)
                        results[index] = {'name': item['name'], 'state': 'outstanding' if error.code == 'stopped' else 'refused',
                                          'error': _error(error)}
                        break
                return receipt()
        except AgentAPIError as error:
            if error.code == 'stopped':
                return receipt()
            raise

    def comparison_manifest(self, run_id, other_run_id, *, checkpoint_sha256, other_checkpoint_sha256,
                            metric_id, mode='paired', result_ref=None, other_result_ref=None):
        """Read exact evidence selectors; delegate all compatibility and numerical work."""
        if (result_ref is None) != (other_result_ref is None):
            raise AgentAPIError('Mixed ordinary/recovered comparison is unsupported.', 'unsupported', 409)
        selections = []
        for selected_run, checkpoint, ref in ((run_id, checkpoint_sha256, result_ref),
                                             (other_run_id, other_checkpoint_sha256, other_result_ref)):
            source = {'run_id': selected_run} if ref is None else {'ref': ref}
            value = self._result(source)
            self._artifact_inventory(value, source)
            args = {'run_id': selected_run, 'checkpoint_sha256': checkpoint} if ref is None else {
                'ref': ref, 'selectors': {'checkpoint_sha256': checkpoint}}
            evidence = _invoke(self.client, 'runs.model_evidence' if ref is None else 'runs.publication_model_evidence', args)
            if ref is not None:
                if ref['run_id'] != selected_run:
                    raise AgentAPIError('Comparison Run differs from publication Ref.', 'conflict', 409)
                evidence = evidence['evidence']
            if evidence.get('state') != 'verified':
                raise AgentAPIError(evidence.get('reason', 'Selected evidence is unavailable.'), 'unsupported', 409)
            try:
                evaluation = next(item['sha256'] for item in value['artifacts'] if item['name'] == 'model-evidence.json')
                definition = evidence['metric_definition_hashes'][metric_id]
            except (KeyError, StopIteration):
                raise AgentAPIError('Selected evaluation or metric definition is unavailable.', 'unsupported', 409) from None
            selections.append((checkpoint, evaluation, definition))
        args = {'run_id': run_id, 'other_run_id': other_run_id, 'metric_id': metric_id, 'mode': mode}
        for prefix, values in zip(('', 'other_'), selections):
            args.update({prefix + key: value for key, value in zip(
                ('checkpoint_sha256', 'evaluation_sha256', 'metric_definition_sha256'), values)})
        operation = 'runs.compare_model_evidence'
        if result_ref is not None:
            args = {'ref': result_ref, 'other_ref': other_result_ref,
                    'selection': {k: v for k, v in args.items() if k not in ('run_id', 'other_run_id')}}
            operation = 'runs.compare_publication_evidence'
        result = _manifest(self.client.catalog_id, operation, args, 'workflow_comparison_manifest_v1')
        return _check_manifest(result, self.client.catalog_id, 'workflow_comparison_manifest_v1', COMPARISONS)

    def compare(self, manifest):
        manifest = _check_manifest(manifest, self.client.catalog_id, 'workflow_comparison_manifest_v1', COMPARISONS)
        operation = manifest['operation']
        selected = self.client.selected_contracts()
        if operation not in selected or (operation == 'runs.compare_model_evidence' and selected[operation] < 2):
            raise AgentAPIError('Exact comparison has no compatible available contract.', 'operation_unsupported', 409)
        return self.client.call(operation, manifest['arguments'])
