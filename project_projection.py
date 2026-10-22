"""Concrete inert composition of external-project projection owners.

No registry, worker constructor, process recovery, dependency installation or
project-script import belongs here. The fixed codecs validate the same candidate
checkpoint before reconstruction and before each canonical publication.
"""
import copy
from datetime import datetime
import re
from types import SimpleNamespace

from project_artifacts import ProjectArtifacts, validate_declaration
from project_data import ProjectData, FAMILIES as DATA_FAMILIES, decode_data_records
from project_data import validate_operation_result as validate_data_result
from project_history import ProjectHistory, FAMILY_FORMATS as HISTORY_FAMILIES
from project_history import decode_records as decode_history_records
from project_history import validate_operation_result as validate_history_result
from project_material import ProjectMaterial, FAMILIES as MATERIAL_FAMILIES
from project_material import decode_records as decode_material_records
from project_material import validate_operation_result as validate_material_result
from project_producers import ProjectProducers, FAMILIES as PRODUCER_FAMILIES
from project_producers import decode_records as decode_producer_records
from project_session import ProjectSession, operation_documents, operation_records
from project_locks import ProjectLock
from project_execution import ProjectExecution, validate_operation_result as validate_execution_result
from project_producer_execution import ProjectProducerExecution, validate_operation_result as validate_producer_result
from project_files import ProjectFiles, decode_records as decode_file_records
from project_files import validate_operation_result as validate_file_result
from project_study_execution import ProjectStudyExecution, validate_operation_result as validate_study_execution_result
from project_runtime import ProjectRuntime, validate_operation_result as validate_runtime_result
from project_native_execution import FAMILY as NATIVE_FAMILY, decode_records as decode_native_records
from project_native_preparation import ProjectNativePreparation, validate_operation_result as validate_preparation_result
from project_sources import SourceAdapter, validate_operation_result as validate_source_result
from workbench import WorkbenchError
from workbench import timestamp


def validate_artifact_resolution(operation, result, records):
    if operation != 'artifacts.resolve':
        return False
    if (type(result) is not dict or set(result) != {
            'format', 'sha256', 'bytes', 'actor_id', 'observed_at'}
            or result['format'] != 'project_artifact_resolution_v1'
            or type(result['actor_id']) is not str or not re.fullmatch('[a-f0-9]{32}', result['actor_id'])
            or type(result['observed_at']) is not str):
        raise WorkbenchError('Invalid artifact resolution observation.')
    try:
        if datetime.fromisoformat(result['observed_at']).utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise WorkbenchError('Artifact observation timestamp requires an offset.') from None
    declaration = validate_declaration(dict(format='project_artifact_v1', sha256=result['sha256'], bytes=result['bytes']))
    if not any(item['family'] == 'project_artifact' and item['id'] == declaration['sha256']
               and item['document'] == declaration for item in records):
        raise WorkbenchError('Artifact resolution observation has no exact declaration.')
    return True


class ProjectProjection:
    def __init__(self, store, db, access, roots, *, custody=None, restore=True, runtime_sources=None):
        self.store, self.db, self.access = store, db, access
        self.custody = custody
        self.pending_original = []
        self.project_id = store.snapshot()['project_id']
        self.artifacts = ProjectArtifacts(store)
        self.sources = None
        self._disclosures = set()
        # Only installation configuration supplies these aliases. Neither a
        # project descriptor nor an HTTP request supplies filesystem roots.
        self._runtime_sources = copy.deepcopy(runtime_sources or {})
        try:
            self.session = ProjectSession(store, db, access, self.artifacts,
                                          validate_records=self.validate_records)
            # Install before domain constructors retain their lock references.
            db.lock = ProjectLock(access.lock, self.session.lock, db.lock)
            self.producers = ProjectProducers(self.session)
            self.data = ProjectData(self.session, generation_entries=self.producers.generation_jobs)
            self.materials = ProjectMaterial(self.session)
            self.history = ProjectHistory(self.session, materials=self.materials,
                                          authorize_disclosure=self.authorize_disclosure)
            if restore:
                self.producers.restore(self.session.snapshot)
                self.data.restore()
                self.materials.restore()
            # These owners create only disposable local directories. Their
            # semantic capture/preparation methods run solely on explicit calls.
            from projects import Projects
            from model_definitions import ModelDefinitions
            from pipeline import Pipelines
            self.context = SimpleNamespace(path=db.path, db=db, lock=db.lock,
                                           access=self.materials.owner_access,
                                           workbench=self.data.workbench,
                                           releases=self.data.releases, runs=self.history)
            self.sources = Projects(self.context, roots)
            self.context.projects = self.sources
            self.context.pipelines = self.pipelines = Pipelines(self.context)
            self.context.models = self.models = ModelDefinitions(self.context)
            self.source_adapter = SourceAdapter(self)
            self.text = _TextView(self)
            self.execution = ProjectExecution(self)
            self.native_preparation=ProjectNativePreparation(self)
            self.context.project_native_preparation=self.native_preparation
            self.runtime = ProjectRuntime(self, resolve_configuration=self.runtime_configuration)
            self.execution.producer_execution = ProjectProducerExecution(
                self.session, self.data, self.producers,
                runtime_access=self.execution.runtime_access, execution=self.execution)
            self.files = ProjectFiles(self.session)
            self.study_execution = ProjectStudyExecution(self, self.execution)
            if restore:
                self.study_execution.restore_authoring()
            else:
                # Explicit original-host recovery validates custody before any
                # science cache reconstruction or local execution constructor.
                self.session.available = False
        except BaseException:
            self.close()
            raise

    @property
    def schema(self):
        return self.db.schema

    def execute(self, *args, **kwargs):
        return self.db.execute(*args, **kwargs)

    def validate_records(self, records, *, project_id=None):
        project_id = self.project_id if project_id is None else project_id
        claimed = {'workbench_text', 'project_artifact', 'project_operation', 'project_file', 'project_fork', 'project_extraction', NATIVE_FAMILY} | set(DATA_FAMILIES) | set(
            MATERIAL_FAMILIES) | set(HISTORY_FAMILIES) | set(PRODUCER_FAMILIES)
        identities = set()
        declarations = {}
        for item in records:
            identity = (item['family'], item['id'])
            if item['family'] not in claimed or identity in identities:
                raise WorkbenchError('Unknown or duplicate owned project family.', 'unsupported', 409)
            identities.add(identity)
            if item['family'] == 'project_artifact':
                declaration = validate_declaration(item['document'])
                if declaration['sha256'] != item['id']:
                    raise WorkbenchError('Artifact inventory identity differs.')
                declarations[item['id']] = declaration
        decode_data_records(records)
        from project_fork import decode_fork
        decode_fork(records, project_id=project_id)
        from project_transfer import decode_records as decode_extraction_records
        decode_extraction_records(records)
        operation_records(records, project_id=project_id)
        decode_file_records(records)
        decode_native_records(records,artifacts=self.artifacts)
        materials = decode_material_records(records)
        for document in materials.values():
            for edge in document.get('artifacts', []):
                blob = edge['blob']
                if declarations.get(blob['sha256']) != dict(format='project_artifact_v1', **blob):
                    raise WorkbenchError('Material artifact declaration is missing or inconsistent.')
        # Resolve every cross-owner reference against THIS candidate, rather
        # than a resolver that still sees the preceding committed checkpoint.
        candidate = SimpleNamespace(snapshot=dict(project_id=project_id, records=records),
                                    artifacts=self.artifacts, check=lambda: None)
        decode_producer_records(records, artifacts=self.artifacts)
        decode_history_records(records, materials=ProjectMaterial(candidate), artifacts=self.artifacts)
        for receipt in operation_documents(records):
            operation, result = receipt['operation'], receipt['result']
            if (validate_data_result(operation, result, records)
                    or validate_material_result(operation, result, records)
                    or validate_history_result(operation, result, records)
                    or validate_source_result(operation, result, records)
                    or validate_execution_result(operation, result, records)
                    or validate_producer_result(operation, receipt['target'], result, records)
                    or validate_file_result(operation, result, records)
                    or validate_study_execution_result(operation, result, records)
                    or validate_runtime_result(operation, result, records)
                    or validate_preparation_result(operation, result, records)
                    or validate_artifact_resolution(operation, result, records)):
                continue
            raise WorkbenchError('No project owner accepts this operation receipt.', 'unsupported', 409)

    def resolve_artifact(self, body, expected_checkpoint, key):
        """Explicitly supply exact bytes from a configured current local root."""
        if type(body) is not dict or set(body) != {'sha256', 'root', 'path'}:
            raise WorkbenchError('Choose one declared artifact and a current rooted file.')
        with self.access.lock, self.session.lock, self.db.lock:
            actor = self.access.require('edit', 'artifacts.resolve', body['sha256'], owner_only=True)
            self.session.check()
            declaration = next((item['document'] for item in self.session.snapshot['records']
                                if item['family'] == 'project_artifact' and item['id'] == body['sha256']), None)
            if declaration is None:
                raise WorkbenchError('Artifact is not declared by this project.', 'not_found', 404)
            def invoke():
                with self.sources._file(body['root'], body['path']) as (descriptor, info):
                    if info.st_size != declaration['bytes']:
                        raise WorkbenchError('Supplied file length differs from the declared artifact.', 'conflict', 409)
                    self.artifacts.publish_fd(descriptor, declaration)
                return dict(format='project_artifact_resolution_v1', sha256=declaration['sha256'],
                            bytes=declaration['bytes'], actor_id=actor.actor_id, observed_at=timestamp())
            return self.session.mutate('artifacts.resolve', body['sha256'], body, expected_checkpoint, key,
                                       invoke, lambda result, before: dict(records=[], result=result))

    def runtime_manifest(self, descriptor):
        """Read only a current local registration during explicit preparation.

        An imported descriptor's root is never a filesystem capability. Captured
        manifests already in canonical artifacts need no current registration.
        """
        from pathlib import Path
        import hashlib
        if descriptor.get('catalog_id') != self.project_id:
            raise WorkbenchError('Register this runtime under the current project before preparation.',
                                 'unavailable', 409)
        if descriptor.get('profile') == 'captured_cpu_python_v1':
            from runtime_snapshots import RuntimeSnapshots
            from recipe_process import read_regular, CPU_MANIFEST_LIMIT
            with self.execution.runtime_inspection():
                current = RuntimeSnapshots(self.db, self.execution.runtime_access, self.db.path).get(
                    descriptor['manifest_sha256'], verify=False)
            if current != descriptor:
                raise WorkbenchError('Current runtime registration differs from the selected descriptor.', 'stale', 409)
            raw = read_regular(Path(current['root']) / 'manifest.json', CPU_MANIFEST_LIMIT)
        elif descriptor.get('profile') == 'managed_torch_python_v1':
            from torch_runtimes import TorchRuntimes
            current, raw = TorchRuntimes(self.db, self.access, self.db.path).get(
                descriptor['manifest_sha256'], verify=False)
            if current != descriptor:
                raise WorkbenchError('Current runtime registration differs from the selected descriptor.', 'stale', 409)
        else:
            raise WorkbenchError('Unsupported current runtime registration.', 'unsupported', 409)
        if len(raw) != descriptor['manifest_bytes'] or hashlib.sha256(raw).hexdigest() != descriptor['manifest_sha256']:
            raise WorkbenchError('Current runtime manifest changed during capture.', 'stale', 409)
        return raw

    def runtime_configuration(self, request):
        if (type(request) is not dict or set(request) != {'source'}
                or type(request['source']) is not str or request['source'] not in self._runtime_sources):
            raise WorkbenchError('Choose an explicitly configured current runtime source.', 'unavailable', 409)
        return copy.deepcopy(self._runtime_sources[request['source']])

    def runtime_sources(self):
        with self.access.lock, self.session.lock, self.db.lock:
            self.access.require('admin', 'runtime.sources', owner_only=True)
            self.session.check()
            return dict(sources=sorted(self._runtime_sources))

    def authorize_disclosure(self, run, population):
        self.access.require('inspect', 'project_history.artifact', run['id'])
        self.access.require('expose-holdout', 'project_history.disclosure', run['id'])
        origin = run['dataset_id']
        digest = self.history.payload_set_sha256(run['id'], origin_catalog_id=origin)
        actor = self.access._context().actor_id
        if (actor, origin, run['id'], digest) not in self._disclosures:
            raise WorkbenchError('Explicitly disclose this retained Run under current local authority first.',
                                 'forbidden', 403)

    def disclose(self, run_id, body, expected_checkpoint, key):
        with self.access.lock, self.session.lock, self.db.lock:
            result = self.history.record_disclosure(run_id, body, expected_checkpoint, key)
            actor = self.access._context().actor_id
            self._disclosures.add((actor, result['origin_catalog_id'], run_id, result['payload_set_sha256']))
            return result

    def reconcile_inert(self, snapshot):
        """Rebuild selected science after actual local custody has drained.

        This preserves existing local Run/admission rows solely for the current
        reconciler's terminal proof. No imported authority table is populated.
        """
        execution = self.execution
        with self.access.lock, self.session.lock, self.db.lock:
            if execution._reconstructing:
                raise RuntimeError('Project reconstruction already has an owner.')
            execution._reconstructing = True
            try:
                self.session.reconcile_selection(snapshot)
                execution.abandon_pending()
                self.study_execution.abandon_pending()
                execution.producer_execution.abandon_pending()
                self.producers.refresh(snapshot)
                self.data.restore(snapshot)
                self.materials.reconcile_projection()
                self.study_execution.restore_authoring(snapshot['records'])
            except BaseException:
                self.session.available = False
                raise
            finally:
                execution._reconstructing = False

    def close(self):
        execution = getattr(self, 'execution', None)
        if execution is not None:
            execution.close()
        if self.sources is not None:
            self.sources.close()
        self.artifacts.close()
        self._disclosures.clear()
        self.db.close()


class _TextView:
    """Preserve the M1 text wire projection over the complete data owner."""
    def __init__(self, projection):
        self.projection = projection

    @property
    def available(self):
        return self.projection.session.available

    def _tag(self, value):
        snapshot = self.projection.session.snapshot
        return dict(value, project_id=snapshot['project_id'], checkpoint=snapshot['checkpoint'])

    def records(self):
        self.projection.session.check()
        from project_fork import active_records
        snapshot = self.projection.session.snapshot
        records = active_records(snapshot['records'], project_id=snapshot['project_id'])
        return self._tag(dict(items=[copy.deepcopy(item['document']['current']) for item in records
                                    if item['family'] in ('workbench_record', 'workbench_text')
                                    and item['document']['current']['kind'] == 'text']))

    def get(self, identity):
        result = self.projection.data.get(identity)
        if result['kind'] != 'text':
            raise WorkbenchError('Use the modality-aware data operation for this record.', 'unsupported', 409)
        return self._tag(result)

    def history(self, identity):
        self.get(identity)
        return self.projection.data.history(identity)

    def import_text(self, body, expected_checkpoint, key):
        return self._tag(self.projection.data.import_text(body, expected_checkpoint, key))

    def annotate(self, identity, body, expected_checkpoint, key):
        self.get(identity)
        return self._tag(self.projection.data.annotate(identity, body, expected_checkpoint, key))
