"""Current-host project execution, separate from inert imported Run history.

Construction installs transaction capture hooks but never constructs Runs,
claims runtime ownership, recovers a process or wakes a queue. Only an explicit
currently authorized action may create the local execution owner.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
import re
import threading
import time
import uuid

import agent_api
from access import Access, AccessError
from model_definitions import natural
from pipeline import closed, digest, identifier
from project_history import capture_run, declarations
from project_session import operation_records
from workbench import WorkbenchError


OPERATIONS = frozenset(('runs.submit_external', 'runs.cancel', 'runs.approve_external'))


class _FileEffect:
    """One of the two named nonexecuting filesystem publication guards."""
    def __init__(self, execution, kind, key, input_sha256, content_sha256):
        self.execution,self.kind,self.key=execution,kind,key
        self.input_sha256,self.content_sha256=input_sha256,content_sha256
        self.started=False;self.done=False

    def publication_started(self):
        execution=self.execution
        pending=execution._runtime_pending if self.kind=='runtime' else execution._package_pending
        identity_field='manifest_sha256' if self.kind=='runtime' else 'material_sha256'
        entry=dict(request_key=self.key,input_sha256=self.input_sha256,**{identity_field:self.content_sha256})
        previous=pending.get(self.key)
        if previous is not None and previous!=entry:
            raise WorkbenchError('File publication key has different current input.','conflict',409)
        # Retain a conservative local fence even if journal fsync acknowledgement
        # fails. No owner filesystem write follows an unacknowledged start.
        pending[self.key]=entry;self.started=True
        if execution.custody is not None:
            with execution._journal_guard():
                if not execution.custody.has_pending:execution.custody.acknowledge(execution.session.snapshot)
                if self.kind=='runtime':execution.custody.runtime_started(self.key,self.input_sha256,self.content_sha256)
                else:execution.custody.package_started(self.key,self.input_sha256,self.content_sha256)

    def confirmed(self):
        if not self.started:raise RuntimeError('File publication must have a durable start before confirmation.')
        execution=self.execution;execution.session.check()
        if execution.db.in_transaction:
            raise RuntimeError('File publication confirms only after its canonical and outer SQL acknowledgement.')
        if execution.custody is not None:
            with execution._journal_guard():
                if self.kind=='runtime':execution.custody.runtime_confirmed(self.key)
                else:execution.custody.package_confirmed(self.key)
        pending=execution._runtime_pending if self.kind=='runtime' else execution._package_pending
        pending.pop(self.key,None);self.done=True


def _admission_result(run):
    return dict(format='project_run_admission_v1', origin_catalog_id=run['dataset_id'],
                run_id=run['id'], request_sha256=run['request_sha256'])


def validate_operation_result(operation, result, records=None):
    """Validate inert operation facts, never a live grant or resume instruction."""
    if operation not in OPERATIONS:
        return False
    if operation == 'runs.approve_external':
        closed(result, ('format','origin_catalog_id','approval_id','material_sha256',
                        'consumer_actor_id','approver_actor_id','created_at','expires_at'))
        if result['format'] != 'project_execution_approval_v1':
            raise WorkbenchError('Invalid project approval observation.')
        for key in ('origin_catalog_id','approval_id','consumer_actor_id','approver_actor_id'):
            identifier(result[key], key)
        if type(result['material_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', result['material_sha256']):
            raise WorkbenchError('Invalid approved material identity.')
        natural(result['created_at'], 'Approval time');natural(result['expires_at'], 'Approval expiry')
        if not result['created_at'] < result['expires_at'] <= result['created_at'] + 3600:
            raise WorkbenchError('Invalid approval observation lifetime.')
        return True
    closed(result, ('format','origin_catalog_id','run_id','request_sha256'))
    if result['format'] != 'project_run_admission_v1':
        raise WorkbenchError('Invalid project Run observation.')
    identifier(result['origin_catalog_id'], 'Run origin');identifier(result['run_id'], 'Run ID')
    if type(result['request_sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', result['request_sha256']):
        raise WorkbenchError('Invalid Run request digest.')
    if records is not None:
        matches = [item['document']['run'] for item in records if item['family'] == 'run_history'
                   and item['id'] == result['origin_catalog_id']+'.'+result['run_id']]
        if len(matches) != 1 or _admission_result(matches[0]) != result:
            raise WorkbenchError('Run operation observation differs from its retained Run.')
    return True


class ProjectExecution:
    def __init__(self, projection):
        self.projection = projection
        self.session, self.db = projection.session, projection.db
        self.access = projection.access
        self.custody = getattr(projection, 'custody', None)
        local=self.custody.snapshot() if self.custody is not None else dict(runtime_effects=[],package_effects=[])
        self._runtime_pending={item['request_key']:item for item in local['runtime_effects']}
        self._package_pending={item['request_key']:item for item in local['package_effects']}
        self._runtime_active=self._package_active=None
        self._journal_publication_pending=False
        self.runtime_access = Access(self.db, self.db.path, authority=self.access)
        self.session.runtime_access = self.runtime_access
        self._runs = None
        self._constructing = False
        self._reconstructing = False
        self._dirty_runs = set()
        self._pending_studies = set()
        self._pending_producers = {kind:set() for kind in ('generation','grounded','caption','text_proposal')}
        self.study_execution = None
        self.producer_execution = None
        self._custody_lock = threading.RLock()
        self._handles = {}
        self._active_attempts = set()
        self.session.extra_capture = self.capture_dirty
        if self.custody is not None:self.session.publication_intent=self._publication_intent
        self.db.set_project_hooks(self.before_commit, self.outcome)

    def attach_runs(self, owner):
        if not self._constructing or owner.project_execution is not self or self._runs is not None:
            raise RuntimeError('Only explicit local construction can attach a Run owner.')
        self._runs = owner

    @contextmanager
    def _journal_guard(self):
        """A failed private custody acknowledgement fences every SQL outcome."""
        try:
            yield
        except BaseException:
            self.session.available = False
            if self._runs is not None:self._runs._fence_coordinator()
            raise

    def attempt_started(self, identity):
        with self._custody_lock:self._active_attempts.add(identity)

    def attempt_finished(self, identity):
        with self._custody_lock:self._active_attempts.discard(identity)

    def register_custody(self, identity, handle):
        if handle.spec['attempt_id'] != identity:
            raise RuntimeError('Current custodian differs from its Run.')
        with self._custody_lock:
            if identity in self._handles:
                raise RuntimeError('A current Run cannot replace its custodian.')
            self._handles[identity] = handle
        if self.custody is not None:
            from recipe_process import identity as process_identity
            with self._journal_guard():
                self.custody.launched(identity,process_identity(handle.process.pid))

    def before_launch(self, identity):
        with self.db.lock:
            self.session.check();run=self.runs._load(identity);self._proof(run)
            self.runtime_access.require_job('runs',identity,run['admission_id'],run['request_sha256'])
            if self.custody is not None:
                with self._journal_guard():self.custody.launch_intent(identity)

    def _publication_intent(self, before, records, key, sha):
        if self.custody is not None and self.custody.has_pending:
            with self._journal_guard():self.custody.expect_publication(before,records,key,sha)
            self._journal_publication_pending=True

    def _local_owner(self, *, recover=True):
        """Construct execution only after the caller checked exact authority."""
        self.session.check()
        if self._runs is None:
            from runs import Runs
            from pipeline import Pipelines
            context = copy.copy(self.projection.context)
            context.access, context.lock = self.runtime_access, self.db.lock
            context.project_execution = self
            pipelines = Pipelines(context)
            context.pipelines = pipelines
            self._constructing = True
            try:
                with self.runtime_access._reconcile():
                    owner = Runs(context, pipelines, recover=recover)
            finally:
                self._constructing = False
            self._runs = owner
            context.runs = owner
        return self._runs

    @property
    def runs(self):
        """An already activated owner, never an implicit constructor."""
        if self._runs is None:
            raise WorkbenchError('No current local execution owner is active.', 'unavailable', 409)
        return self._runs

    @property
    def has_local_custody(self):
        """Observe only current physical owners and their unresolved local index."""
        with self._custody_lock:
            return (self._runs is not None or bool(self._handles)
                    or self.producer_execution is not None and self.producer_execution.has_local_custody
                    or bool(self._runtime_pending or self._package_pending or self._runtime_active or self._package_active)
                    or self.custody is not None and self.custody.has_pending)

    @contextmanager
    def runtime_inspection(self):
        with self.access.lock,self.session.lock,self.db.lock:
            self.assert_quiescent()
            self._runtime_active='inspection'
            try:yield
            finally:self._runtime_active=None

    def runtime_effect(self, request_key, input_sha256=None, manifest_sha256=None):
        return self._file_effect('runtime',request_key,input_sha256,manifest_sha256)

    def package_effect(self, request_key, input_sha256=None, material_sha256=None):
        return self._file_effect('package',request_key,input_sha256,material_sha256)

    @contextmanager
    def package_reconciliation(self, request_key, input_sha256, material_sha256, expected_checkpoint):
        """Rebind one stopped original physical package writer; never rerun it.

        The caller publishes its fixed final/abandonment fact before confirming
        this guard. Imported intent alone cannot select or clear local custody.
        """
        with self._file_reconciliation('package',request_key,input_sha256,material_sha256,expected_checkpoint) as effect:
            yield effect

    @contextmanager
    def runtime_reconciliation(self, request_key, input_sha256, manifest_sha256, expected_checkpoint):
        """Hold one original stopped runtime capture for a canonical owner decision."""
        with self._file_reconciliation('runtime',request_key,input_sha256,manifest_sha256,expected_checkpoint) as effect:
            yield effect

    @contextmanager
    def _file_reconciliation(self, kind, request_key, input_sha256, content_sha256, expected_checkpoint):
        with self.access.lock,self.session.lock,self.db.lock:
            self._restore_file_writer(kind,request_key,input_sha256,content_sha256,expected_checkpoint)
            if kind=='runtime':self._runtime_active=request_key
            else:self._package_active=request_key
            effect=_FileEffect(self,kind,request_key,input_sha256,content_sha256)
            effect.started=True
            try:
                yield effect
            finally:
                if kind=='runtime':self._runtime_active=None
                else:self._package_active=None

    def runtime_pending(self, request_key):
        """Observe one current-host private runtime marker, never an imported intent."""
        self.access.require('admin','project_execution.runtime_pending',owner_only=True)
        if type(request_key) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',request_key):
            raise WorkbenchError('Invalid current runtime publication key.')
        with self.access.lock,self.session.lock,self.db.lock:
            self.access.require('admin','project_execution.runtime_pending',owner_only=True)
            if self.custody is None:return None
            with self._journal_guard():journal=self.custody.refresh()
            return next((copy.deepcopy(entry) for entry in journal['runtime_effects']
                         if entry['request_key']==request_key),None)

    def prepare_runtime_reconciliation(self, request_key, input_sha256, manifest_sha256, expected_checkpoint):
        """Restore one stopped capture before an explicit normal owner retry.

        No active file guard or marker is changed. The caller must still verify
        its actual target and acknowledge normal canonical completion.
        """
        return self._restore_file_writer('runtime',request_key,input_sha256,manifest_sha256,expected_checkpoint)

    def _restore_file_writer(self, kind, request_key, input_sha256, content_sha256, expected_checkpoint):
        # Exactly the two admitted synchronous filesystem owners share this
        # physical-custody proof. There is no extensible effect registry.
        if kind=='runtime':
            authority,scope,action=self.access,'admin','project_execution.runtime_reconciliation'
            field='manifest_sha256'
        elif kind=='package':
            authority,scope,action=self.runtime_access,'cancel','project_execution.package_reconciliation'
            field='material_sha256'
        else:raise RuntimeError('Unsupported file reconciliation owner.')
        authority.require(scope,action,owner_only=True)
        if type(request_key) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',request_key):
            raise WorkbenchError('Invalid current file publication key.')
        for value in (input_sha256,content_sha256,expected_checkpoint):
            if type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value):
                raise WorkbenchError('File reconciliation requires exact input and checkpoint digests.')
        with self.access.lock,self.session.lock,self.db.lock:
            authority.require(scope,action,owner_only=True)
            if self.db.in_transaction:
                raise RuntimeError('File reconciliation requires no outer SQL transaction.')
            if self.session.snapshot['checkpoint']!=expected_checkpoint:
                raise WorkbenchError('Expected current file checkpoint changed.','stale_project',409)
            if self.custody is None:
                raise WorkbenchError('No original physical file custody exists.','unavailable',409)
            if self._runtime_active or self._package_active:
                raise WorkbenchError('A current runtime or package writer is active.','busy',409)
            expected=dict(request_key=request_key,input_sha256=input_sha256,**{field:content_sha256})
            with self._journal_guard():journal=self.custody.refresh()
            own,other=(('runtime_effects','package_effects') if kind=='runtime' else ('package_effects','runtime_effects'))
            pending=self._runtime_pending if kind=='runtime' else self._package_pending
            other_pending=self._package_pending if kind=='runtime' else self._runtime_pending
            if expected not in journal[own]:
                raise WorkbenchError('No exact original file writer matches this request.','unavailable',409)
            if (journal['runs'] or journal['producers'] or journal[other]
                    or journal[own]!=[expected] or other_pending
                    or any(key!=request_key or value!=expected for key,value in pending.items())):
                raise WorkbenchError('Other original local custody remains unresolved.','outcome_unknown',409)
            self._assert_run_drained()
            if self.producer_execution is not None:self.producer_execution.assert_quiescent()
            binding=self.custody.binding
            if (binding['projection_id']!=self.db.projection_id or binding['project_id']!=self.db.dataset_id
                    or binding['host_catalog_id']!=self.access.catalog_id):
                raise WorkbenchError('File custody belongs to another physical owner.','local_custody_unavailable',409)
            # Recovery remains fenced until every fixed inert owner has been
            # reconstructed from this exact acknowledged/attempted selection.
            self.session.available=False
            snapshot=self.session.store.recover_checkpoint()
            with self.session.store.root_directory() as descriptor:
                info=os.fstat(descriptor)
                if [info.st_dev,info.st_ino]!=binding['root_identity']:
                    raise WorkbenchError('File custody belongs to another physical root.','local_custody_unavailable',409)
            self.custody.validate_selection(snapshot)
            self.projection.reconcile_inert(snapshot)
            pending[request_key]=expected
            self.assert_quiescent(_allow_file=(kind,request_key))
            return self.session.snapshot

    @contextmanager
    def _file_effect(self, kind, key, input_sha256, content_sha256):
        if type(key) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',key):
            raise WorkbenchError('Invalid current file publication key.')
        for value in (input_sha256,content_sha256):
            if value is not None and (type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value)):
                raise WorkbenchError('Invalid current file publication digest.')
        with self.access.lock,self.session.lock,self.db.lock:
            self.assert_quiescent(_allow_file=(kind,key))
            if kind=='runtime':self._runtime_active=key
            else:self._package_active=key
            effect=_FileEffect(self,kind,key,input_sha256,content_sha256)
            try:yield effect
            finally:
                if kind=='runtime':self._runtime_active=None
                else:self._package_active=None

    def mark_run(self, run_id):
        identifier(run_id, 'Dirty Run ID')
        if not self.db.in_transaction:
            raise RuntimeError('Run changes require their owned SQL transaction.')
        self._dirty_runs.add(run_id)

    def mark_study(self, study_id):
        identifier(study_id, 'Dirty Study ID')
        if not self.db.in_transaction:
            raise RuntimeError('Study changes require their owned SQL transaction.')
        if self.study_execution is None:
            self._pending_studies.add(study_id)
        else:
            self.study_execution.mark_study(study_id)

    def _mark_producer(self, kind, identity):
        identifier(identity, 'Dirty producer ID')
        if not self.db.in_transaction:
            raise RuntimeError('Producer changes require their owned SQL transaction.')
        if self.producer_execution is None:
            self._pending_producers[kind].add(identity)
        else:
            getattr(self.producer_execution, 'mark_'+kind)(identity)

    def mark_generation(self, identity):self._mark_producer('generation', identity)
    def mark_grounded(self, identity):self._mark_producer('grounded', identity)
    def mark_caption(self, identity):self._mark_producer('caption', identity)
    def mark_text_proposal(self, identity):self._mark_producer('text_proposal', identity)

    def _producer_authority(self, family, identity, admission_id, request_digest):
        from project_producer_execution import JOB_KINDS, FINISH
        from access import current_context
        if family not in JOB_KINDS:raise WorkbenchError('Unsupported producer custody family.')
        row=self.db.execute('SELECT * FROM access_admissions WHERE id=%s',(admission_id,)).fetchone()
        if (row is None or row['catalog_id']!=self.db.dataset_id or row['kind']!=JOB_KINDS[family]
                or row['job_id']!=identity or row['request_digest']!=request_digest):
            raise AccessError('Producer custody requires its exact current local admission.')
        context=current_context()
        if context is not None and context.mode=='job':
            self.runtime_access.require_job(JOB_KINDS[family],identity,admission_id,request_digest)
            self.runtime_access.require('edit',FINISH[family],identity)
        elif context is not None and context.mode=='system':
            self.runtime_access.require('cancel',JOB_KINDS[family]+'.reconcile',identity)
        else:self.runtime_access.require('inspect','producers.custody',identity)

    def register_producer(self, family, identity, admission_id, request_digest):
        with self.db.lock:
            self.session.check();self._producer_authority(family,identity,admission_id,request_digest)
            if self.custody is not None:
                with self._journal_guard():
                    if not self.custody.has_pending:self.custody.acknowledge(self.session.snapshot)
                    self.custody.register_producer(family,identity,admission_id,request_digest)

    def producer_effect_intent(self, family, identity):
        with self.db.lock:
            self.session.check()
            if self.custody is not None:
                value=next((item for item in self.custody.snapshot()['producers']
                    if (item['family'],item['producer_id'])==(family,identity)),None)
                if value is None:raise AccessError('Provider dispatch has no original-host custody admission.')
                self._producer_authority(family,identity,value['admission_id'],value['request_sha256'])
                with self._journal_guard():self.custody.producer_effect_intent(family,identity)

    def update_producer_outcome(self, family, identity, provider_outcome, worker_drained):
        with self.db.lock:
            self.session.check()
            if self.custody is not None:
                value=next((item for item in self.custody.snapshot()['producers']
                    if (item['family'],item['producer_id'])==(family,identity)),None)
                if value is None:return
                self._producer_authority(family,identity,value['admission_id'],value['request_sha256'])
                with self._journal_guard():self.custody.producer_outcome(family,identity,provider_outcome,worker_drained)

    def _proof(self, run):
        admission = self.db.execute('SELECT * FROM access_admissions WHERE id=%s', (run['admission_id'],)).fetchone()
        if admission is None:
            raise AccessError('Current local Run admission is unavailable.')
        admission = dict(admission)
        admission['effects'] = json.loads(admission.pop('effects_json'))
        if (admission['catalog_id'] != self.db.dataset_id or admission['kind'] != 'runs'
                or admission['job_id'] != run['id'] or admission['request_digest'] != run['request_sha256']):
            raise AccessError('Current local admission differs from its Run.')
        grant = consumption = None
        if run.get('execution_kind') == 'external_recipe':
            grant = self.db.execute('SELECT * FROM access_execution_grants WHERE id=%s', (run['approval_id'],)).fetchone()
            consumption = self.db.execute('SELECT * FROM access_execution_consumptions WHERE grant_id=%s', (run['approval_id'],)).fetchone()
            if grant is None or consumption is None:
                raise AccessError('Current local execution consumption is unavailable.')
        return dict(grant=dict(grant) if grant is not None else None,
                    consumption=dict(consumption) if consumption is not None else None, admission=admission)

    def _authorize_observation(self):
        context = self.runtime_access._context() if self._dirty_runs else None
        for identity in self._dirty_runs:
            row = self.db.execute('SELECT document FROM workspace_runs WHERE id=%s', (identity,)).fetchone()
            if row is None:
                raise AccessError('Current local Run is unavailable.')
            run = json.loads(row['document'])
            proof = self._proof(run)
            if context.mode == 'job':
                self.runtime_access.require_job('runs', identity, run['admission_id'], run['request_sha256'])
                self.runtime_access.require('edit', 'runs.update', identity)
            elif context.mode == 'system':
                if self._runs is None and not self._constructing:
                    raise AccessError('Reconciliation requires the current local execution owner.')
                if not self._runs.runtime_owner or not self.db.runtime_owned('workspace_runs'):
                    raise AccessError('Current local runtime custody ownership is unavailable.')
                self.runtime_access.require('cancel', 'runs.reconcile', identity)
            else:
                # The domain owner has already checked submit/cancel authority;
                # recheck live host credentials without inventing a worker owner.
                self.runtime_access.require('inspect', 'runs.observe', identity)
            if proof['admission']['catalog_id'] != self.session.snapshot['project_id']:
                raise AccessError('Local custody belongs to another project.')

    def _capture_run(self, identity):
        owner = self.runs
        run = owner._load(identity)
        proof = self._proof(run)
        payloads = owner._capture_project_payloads(run, self.session.artifacts)
        record = capture_run(run, admission_proof=proof, payloads=payloads)
        records = [record, *declarations(record)]
        if run.get('execution_kind') == 'external_recipe':
            environment = run['material'].get('torch_runtime', run['material'].get('cpu_snapshot', run['material']['runtime']))
            descriptor = environment if environment.get('profile') in ('captured_cpu_python_v1','managed_torch_python_v1') else None
            sha = digest(environment)
            ref = dict(kind='runtime', catalog_id=run['dataset_id'], id=sha, sha256=sha)
            from project_material import decode_records
            if ('runtime_material', ref['catalog_id']+'.'+sha) not in decode_records(self.session.snapshot['records']):
                raw = self.projection.runtime_manifest(descriptor) if descriptor is not None else None
                manifest = None
                if raw is not None:
                    from recipe_process import decode
                    manifest = decode(raw)
                runtime = self.projection.materials.capture_runtime(dict(ref=ref, descriptor=descriptor,
                    environment=None if descriptor is not None else environment, manifest=manifest), raw)
                records.extend([runtime, *self.projection.materials.declarations(runtime)])
        if self.custody is not None:
            with self._journal_guard():
                if not self.custody.has_pending:self.custody.acknowledge(self.session.snapshot)
                receipt=next((edge['blob']['sha256'] for edge in payloads if edge['name']=='custody-receipt.json'),None)
                self.custody.observe_run(run,receipt_sha256=receipt)
        return records

    def capture_dirty(self, before_records):
        """The finite owner capture seam used by foreground and background TXs."""
        if self._reconstructing:
            return []
        if self._pending_studies or any(self._pending_producers.values()):
            raise WorkbenchError('The changed execution family has no installed capture owner.', 'unavailable', 409)
        if self.study_execution is not None:
            self.study_execution.settle_runs(self._dirty_runs)
        self._authorize_observation()
        records = []
        for identity in sorted(self._dirty_runs):
            records.extend(self._capture_run(identity))
        if self.study_execution is not None:
            records.extend(self.study_execution.capture_dirty(before_records))
        if self.producer_execution is not None:
            records.extend(self.producer_execution.capture_dirty(before_records))
        # Shared immutable blobs can appear on several domain edges.
        merged = {}
        for record in records:
            identity = record['family'], record['id']
            if identity in merged and merged[identity] != record:
                raise WorkbenchError('Execution captures disagree on shared project facts.')
            merged[identity] = record
        return list(merged.values())

    def before_commit(self):
        if self._reconstructing or self.session.foreground_publication:
            return
        if not self._dirty_runs and not self._pending_studies and not any(self._pending_producers.values()) and self.study_execution is None and self.producer_execution is None:
            return
        snapshot = self.session.snapshot
        records = self.capture_dirty(snapshot['records'])
        if records:
            key = 'execution-observation-' + uuid.uuid4().hex
            sha = hashlib.sha256(agent_api.encoded(records)).hexdigest()
            self.session._publish_observation(records, key, sha, authorize=self._authorize_observation)

    def outcome(self, outcome):
        if outcome not in ('committed','rolled_back','unknown'):
            raise ValueError('Unsupported project SQL outcome.')
        if self._reconstructing:
            return
        self.session._observation_outcome(outcome)
        if self.custody is not None and outcome=='committed':
            try:
                if self._journal_publication_pending:self.custody.acknowledge(self.session.snapshot)
                for identity in sorted(self._dirty_runs):
                    run=self.runs._load(identity)
                    entry=next((item for item in self.custody.snapshot()['runs'] if item['run_id']==identity),None)
                    if entry is not None and run['state'] in ('completed','failed','cancelled','interrupted') and (
                            run['custody_phase']=='drained' and entry['receipt_sha256'] is not None
                            or entry['phase']=='admitted' and run.get('custody_identity') is None):
                        self.custody.settle_run(identity)
            except BaseException:
                self.session.available=False
                if self._runs is not None:self._runs._fence_coordinator()
                raise
        self._journal_publication_pending=False
        self._dirty_runs.clear();self._pending_studies.clear()
        for values in self._pending_producers.values():values.clear()
        for adapter in (self.study_execution, self.producer_execution):
            if adapter is not None:adapter.outcome(outcome)
        if outcome == 'unknown':self.session.available = False
        if not self.session.available:
            if self._runs is not None:self._runs._fence_coordinator()

    def abandon_pending(self):
        """Discard failed capture bookkeeping, never an admission or grant."""
        if not self._reconstructing:
            raise RuntimeError('Pending execution capture may clear only during guarded inert reconstruction.')
        self._dirty_runs.clear();self._pending_studies.clear()
        for values in self._pending_producers.values():values.clear()

    def mutate(self, operation, target, body, expected_checkpoint, key, invoke, capture, *, scope='edit'):
        try:
            return self.session.mutate(operation, target, body, expected_checkpoint, key, invoke, capture, scope=scope)
        except BaseException:
            if not self.session.available and self._runs is not None:self._runs._fence_coordinator()
            raise

    def preflight_external(self, graph_id, revision):
        self.runtime_access.require('inspect', 'pipeline.preflight_external', graph_id)
        with self.access.lock, self.session.lock, self.db.lock:
            self.session.check()
            return self.projection.pipelines.preflight_external(graph_id, revision)

    def submit_external(self, body, expected_checkpoint, key):
        authority = self.runtime_access.require_external_submission()
        with self.access.lock, self.session.lock, self.db.lock:
            self.session.check()
            prior = operation_records(self.session.snapshot['records']).get(key)
            if prior is None and expected_checkpoint != self.session.snapshot['checkpoint']:
                raise WorkbenchError('Expected project checkpoint changed.', 'stale_project', 409)
            if prior is not None:
                # A retained request never recreates a local Run/admission or wakes
                # imported queue state. A same-host local receipt can reconcile.
                result = prior['result']
                if (prior['operation'] != 'runs.submit_external' or
                        self.db.execute('SELECT id FROM workspace_runs WHERE id=%s', (result.get('run_id'),)).fetchone() is None):
                    raise WorkbenchError('This saved request has no current local Run admission.', 'unavailable', 409)
            request = dict(body, request_key=key)
            def invoke():
                owner = self._local_owner()
                public = owner.submit_external(request)
                return _admission_result(owner._load(public['id']))
            effective = dict(body, actor_id=authority.actor_id)
            return self.mutate('runs.submit_external', body.get('graph_id'), effective, expected_checkpoint, key,
                               invoke, lambda value,before:dict(records=[], result=value), scope='inspect')

    def approve_external(self, body, expected_checkpoint, key):
        authority = self.runtime_access.require('approve-execution', 'runs.approve_external', owner_only=True)
        with self.access.lock, self.session.lock, self.db.lock:
            self.session.check()
            prior = operation_records(self.session.snapshot['records']).get(key)
            if prior is None and expected_checkpoint != self.session.snapshot['checkpoint']:
                raise WorkbenchError('Expected project checkpoint changed.', 'stale_project', 409)
            if prior is not None:
                value = prior['result']
                if prior['operation'] != 'runs.approve_external' or self.db.execute(
                        'SELECT id FROM access_execution_grants WHERE id=%s', (value.get('approval_id'),)).fetchone() is None:
                    raise WorkbenchError('This approval is historical; approve explicitly under current authority.', 'unavailable', 409)
            def invoke():
                owner = self._local_owner()
                grant = owner.approve_external(body)
                return dict(format='project_execution_approval_v1', origin_catalog_id=grant['catalog_id'],
                    approval_id=grant['id'], **{key:grant[key] for key in ('material_sha256','consumer_actor_id',
                        'approver_actor_id','created_at','expires_at')})
            effective = dict(body, approver_actor_id=authority.actor_id)
            value = self.mutate('runs.approve_external', body.get('graph_id'), effective, expected_checkpoint, key,
                                invoke, lambda result,before:dict(records=[], result=result), scope='approve-execution')
            grant = self.db.execute('SELECT * FROM access_execution_grants WHERE id=%s', (value['approval_id'],)).fetchone()
            if grant is None:
                raise WorkbenchError('Current local execution approval is unavailable.', 'unavailable', 409)
            fields = ('material_sha256','consumer_actor_id','approver_actor_id','created_at','expires_at')
            if (grant['catalog_id'] != value['origin_catalog_id'] or grant['id'] != value['approval_id']
                    or any(grant[field] != value[field] for field in fields)
                    or grant['approver_actor_id'] != authority.actor_id or grant['revoked_at'] is not None
                    or grant['expires_at'] <= int(time.time())):
                raise WorkbenchError('This historical approval has no exact current live grant. Use a fresh key.', 'unavailable', 409)
            return dict(format='project_current_execution_approval_v1', current_local=True, grant=dict(grant))

    def cancel_run(self, run_id, expected_checkpoint, key):
        self.runtime_access.require('cancel', 'runs.cancel', run_id)
        with self.access.lock, self.session.lock, self.db.lock:
            if self._runs is None or self.db.execute('SELECT id FROM workspace_runs WHERE id=%s', (run_id,)).fetchone() is None:
                raise WorkbenchError('A historical Run has no current local process to cancel.', 'unavailable', 409)
            def invoke():
                self.runs.cancel(run_id)
                return _admission_result(self.runs._load(run_id))
            return self.mutate('runs.cancel', run_id, {}, expected_checkpoint, key, invoke,
                lambda result,before:dict(records=[], result=result), scope='cancel')

    def health(self, offset=0, limit=40):
        self.access.require('inspect', 'project_execution.health')
        natural(offset,'Execution offset',0,100000);natural(limit,'Execution limit',1,40)
        with self.db.lock:
            rows = [json.loads(row['document']) for row in self.db.execute('SELECT document FROM workspace_runs')]
            active = {row['id'] for row in rows if row['state'] in ('queued','running','cancelling','unknown')}
            with self._custody_lock:active.update(self._active_attempts)
            return dict(format='project_execution_health_v1', active_run_ids=sorted(active)[offset:offset+limit],
                        active_count=len(active), offset=offset, limit=limit,
                        local_owner_active=self._runs is not None,
                        available=self.session.available and self.db.dataset_id != self.access.catalog_id,
                        drain_required=bool(self.custody is not None and self.custody.has_pending
                            or self._runtime_active or self._package_active
                            or self._runs is not None and self._runs._thread is not None and self._runs._thread.is_alive()))

    def assert_quiescent(self, *, _allow_file=None):
        with self.db.lock:
            if not self.session.available:
                raise WorkbenchError('Current execution outcome requires explicit reconciliation.', 'projection_unavailable', 503)
            if self._runtime_active or self._package_active:
                raise WorkbenchError('A current runtime or package file writer is active.','busy',409)
            for kind,pending in (('runtime',self._runtime_pending),('package',self._package_pending)):
                if any(_allow_file!=(kind,key) for key in pending):
                    raise WorkbenchError('A current runtime or package publication requires exact reconciliation.','outcome_unknown',409)
            self._assert_run_drained()
            for adapter in (self.study_execution,self.producer_execution):
                if adapter is not None:adapter.assert_quiescent()
            if self.custody is not None:
                journal=self.custody.snapshot()
                if journal['runs'] or journal['producers']:
                    raise WorkbenchError('Original local custody remains unresolved.','outcome_unknown',409)

    def _assert_run_drained(self):
        """Check only actual current Run effects, including an idle supervisor."""
        rows = self.db.execute("SELECT id FROM workspace_runs WHERE document::jsonb->>'state' IN ('queued','running','cancelling','unknown')").fetchall()
        if rows:
            raise WorkbenchError('Drain or cancel current local Runs before closing or copying this project.', 'busy', 409)
        with self._custody_lock:
            if self._active_attempts or any(handle.process.poll() is None for handle in self._handles.values()):
                raise WorkbenchError('Current local custodians are still draining.', 'busy', 409)
        if self._runs is not None and self._runs._thread is not None and self._runs._thread.is_alive():
            raise WorkbenchError('Reconcile current local custody to stop its idle supervisor before closing.', 'busy', 409)
        if self._runs is not None and (self._runs._publication_active is not None or self._runs._publication_lock.locked()):
            raise WorkbenchError('Current Run publication has not drained.', 'busy', 409)

    def close(self):
        if not self.has_local_custody:
            return
        self.assert_quiescent()
        if self._runs is not None:
            with self.runtime_access._reconcile():self._runs.close()
        if self.producer_execution is not None:self.producer_execution.close()

    def shutdown(self):
        """Explicit application shutdown, outside project command locks.

        Existing local continuations own cancellation and final observations.
        This neither constructs an owner nor creates human execution authority.
        """
        if self.db.lock.owned_by_current_thread or self.db.in_transaction:
            raise WorkbenchError('Shutdown must drain outside the project command lock.', 'busy', 409)
        try:
            if self._runs is not None:
                with self.runtime_access._reconcile():self._runs.close()
        finally:
            if self.producer_execution is not None:self.producer_execution.shutdown()

    def reconcile_current(self):
        """Reconcile only retained current-local custody, never imported handles."""
        self.runtime_access.require('cancel', 'project_execution.reconcile', owner_only=True)
        if self._runs is None:
            raise WorkbenchError('No current local custody owner exists to reconcile.', 'unavailable', 409)
        if self.db.lock.owned_by_current_thread or self.db.in_transaction:
            raise WorkbenchError('Drain current custody outside the project command lock.', 'busy', 409)
        owner = self._runs
        owner._fence_coordinator()
        with self._custody_lock:handles = dict(self._handles)
        receipts = {}
        # Only actual Handle objects retained by this application's launch path
        # close control channels. Saved PID/spec/receipt text never selects one.
        for identity, handle in handles.items():
            receipt = handle.close_control()
            if not receipt or not receipt.get('drained'):
                raise WorkbenchError('Current custodian drainage is still unconfirmed.', 'unknown', 409)
            receipts[identity] = receipt
        deadline = time.monotonic() + 60
        thread = owner._thread
        if thread is not None:
            thread.join(max(0, deadline-time.monotonic()))
            if thread.is_alive():
                raise WorkbenchError('Current execution supervisor has not drained.', 'busy', 409)
        with self._custody_lock:
            if self._active_attempts:
                raise WorkbenchError('Current execution attempts have not drained.', 'busy', 409)
        if self.producer_execution is not None:self.producer_execution.assert_quiescent()
        with self.access.lock, self.session.lock, self.db.lock:
            self.runtime_access.require('cancel','project_execution.reconcile',owner_only=True)
            snapshot = self.session.store.recover_checkpoint()
            self.projection.reconcile_inert(snapshot)
            canonical = {item['document']['run']['id']:item['document']['run'] for item in snapshot['records']
                         if item['family']=='run_history' and item['document']['origin_catalog_id']==self.db.dataset_id}
            reconciled = []
            try:
                with self.runtime_access._reconcile(), self.db.transaction():
                    for row in self.db.execute('SELECT id FROM workspace_runs'):
                        local = owner._load(row['id'])
                        if local['state'] not in ('queued','running','cancelling','unknown'):
                            continue
                        self._proof(local)
                        retained = canonical.get(local['id'])
                        if retained is None or any(retained.get(key)!=local.get(key) for key in (
                                'dataset_id','id','request_sha256','admission_id','approval_id','material_sha256','spec')):
                            raise WorkbenchError('Current local admission differs from canonical custody.', 'unknown', 409)
                        run = copy.deepcopy(retained)
                        handle = handles.get(run['id'])
                        if handle is None:
                            if run['custody_phase']!='prepared' or run.get('custody_identity') is not None:
                                raise WorkbenchError('Canonical execution has no current local custody proof.', 'unknown', 409)
                            state = 'cancelled'
                        else:
                            receipt = receipts[run['id']]
                            if (handle.expected_identity['attempt_id']!=run['id'] or
                                    handle.expected_identity['request_sha256']!=run['request_sha256'] or
                                    run.get('custody_identity') not in (None,handle.expected_identity)):
                                raise WorkbenchError('Current custodian differs from its canonical admission.', 'unknown', 409)
                            run['custody_identity'] = copy.deepcopy(handle.expected_identity)
                            run['custody_phase'] = 'drained'
                            if run['state']=='completed':
                                owner._verify_external_artifacts(run)
                                state = 'completed'
                            else:
                                state = 'cancelled' if receipt['outcome']=='cancelled' else 'interrupted'
                        owner._event(run,state,'Explicit current-host reconciliation confirmed custody drainage; execution was not replayed.')
                        owner._save(run)
                        reconciled.append(run['id'])
                self.assert_quiescent()
            except BaseException:
                self.session.available = False
                owner._fence_coordinator()
                raise
            return dict(format='project_execution_reconciliation_v1', origin_catalog_id=self.db.dataset_id,
                        run_ids=sorted(reconciled), available=self.session.available)

    def reconcile_original(self, *, expected_checkpoint, timeout=15):
        """Explicit original-host receipt reconciliation, without PID control.

        The Workspace supplies only an indexed existing physical projection.
        Imported history never selects that projection or creates admissions.
        No Run owner exists until all journal/local-SQL/receipt proofs pass.
        """
        self.runtime_access.require('cancel','project_execution.reconcile_original',owner_only=True)
        if self.custody is None or self._runs is not None:
            raise WorkbenchError('Original custody requires its indexed inactive physical projection.','local_custody_unavailable',409)
        if self.db.lock.owned_by_current_thread or self.db.in_transaction:
            raise WorkbenchError('Original custody must drain outside command locks.','busy',409)
        if type(timeout) not in (int,float) or not 0<=timeout<=30:
            raise WorkbenchError('Original receipt wait must be zero through thirty seconds.')
        journal=self.custody.snapshot();snapshot=self.session.store.recover_checkpoint()
        if snapshot['checkpoint']!=expected_checkpoint:
            raise WorkbenchError('Expected original project checkpoint changed.','stale_project',409)
        self.custody.validate_selection(snapshot)
        canonical={item['document']['run']['id']:item['document']['run'] for item in snapshot['records']
                   if item['family']=='run_history' and item['document']['origin_catalog_id']==self.db.dataset_id}
        plans=[];unacknowledged=[];receipts={}
        with self.db.lock:
            if journal['runs'] and not self.db.claim_runtime('workspace_runs'):
                raise WorkbenchError('The original Run application still owns this physical projection.','busy',409)
            from project_producer_execution import TABLES as PRODUCER_TABLES
            for producer in journal['producers']:
                if not self.db.claim_runtime(PRODUCER_TABLES[producer['family']]):
                    raise WorkbenchError('An original producer application still owns this physical projection.','busy',409)
                if producer['phase']!='admitted' or producer['provider_outcome']!='not_admitted':
                    raise WorkbenchError('Original provider outcome remains unknown; a closed local worker is not cessation proof.','outcome_unknown',409)
            for entry in journal['runs']:
                row=self.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(entry['run_id'],)).fetchone()
                if row is None:
                    if entry['phase']!='admitted':
                        raise WorkbenchError('Launched custody has no original local admission.','local_custody_unavailable',409)
                    unacknowledged.append(entry['run_id']);continue
                local=json.loads(row['document']);retained=canonical.get(entry['run_id'])
                self._proof(local)
                from recipe_process import encoded
                if (retained is None or local['id']!=entry['run_id'] or local['admission_id']!=entry['admission_id']
                        or local['request_sha256']!=entry['request_sha256'] or local['dataset_id']!=self.db.dataset_id
                        or hashlib.sha256(encoded(local['spec'])).hexdigest()!=entry['spec_sha256']
                        or any(retained.get(key)!=local.get(key) for key in (
                            'id','dataset_id','admission_id','request_sha256','approval_id','material_sha256','spec'))
                        or local['spec']['cwd']!=str(self.db.path/'workspace-runs'/('.external-'+local['id']))):
                    raise WorkbenchError('Original local admission/specification differs from its indexed canonical observation.','local_custody_unavailable',409)
                if entry['phase']!='admitted' and entry['custody_identity'] is None:
                    raise WorkbenchError('Original spawn window lacks an observed helper identity; cessation remains unknown.','unknown',409)
                plans.append((entry,copy.deepcopy(retained)))
        # Poll only exact original local receipt files. Never signal a stored PID,
        # import a controller handle, replay GO or execute a project script.
        if any(entry['custody_identity'] is not None for entry,run in plans):
            from projects import Projects
            from recipe_process import validate_receipt
            reader=Projects(self.projection.context,{'original_runs':self.db.path/'workspace-runs'})
            deadline=time.monotonic()+timeout
            try:
                for entry,run in plans:
                    if entry['custody_identity'] is None:continue
                    while True:
                        try:
                            raw=reader._read('original_runs','.external-'+run['id']+'/custody/receipt.json',16384)
                            receipt=validate_receipt(raw,entry['custody_identity'])
                            if not receipt['drained']:
                                raise WorkbenchError('Original custodian has not established drainage.','unknown',409)
                            receipts[run['id']]=receipt;break
                        except FileNotFoundError:
                            if time.monotonic()>=deadline:
                                raise WorkbenchError('Original exact drain receipt is not available yet.','unknown',409) from None
                            time.sleep(min(.1,max(0,deadline-time.monotonic())))
            finally:reader.close()
        with self.access.lock,self.session.lock,self.db.lock:
            self.runtime_access.require('cancel','project_execution.reconcile_original',owner_only=True)
            self.custody.validate_selection(self.session.store.snapshot())
            self.projection.reconcile_inert(snapshot)
            owner=self._local_owner(recover=False) if plans else None
            if owner is not None:owner._fence_coordinator()
            try:
                if owner is not None:
                    # Verification uses the current human's existing disclosure
                    # policy. The following system scope owns only terminal SQL.
                    for entry,run in plans:
                        if run['state']=='completed':owner._verify_external_artifacts(run)
                    with self.runtime_access._reconcile(),self.db.transaction():
                        for entry,run in plans:
                            if entry['custody_identity'] is not None:
                                run['custody_identity']=copy.deepcopy(entry['custody_identity']);run['custody_phase']='drained'
                                state=run['state'] if run['state']=='completed' else (
                                    'cancelled' if receipts[run['id']]['outcome']=='cancelled' else 'interrupted')
                            else:state='cancelled'
                            owner._event(run,state,'Original-host exact local custody reconciled; execution was not resumed.')
                            owner._save(run)
                for identity in unacknowledged:self.custody.settle_run(identity)
                for producer in journal['producers']:
                    self.custody.producer_outcome(producer['family'],producer['producer_id'],'not_admitted',True)
                self.custody.acknowledge(self.session.snapshot)
            except BaseException:
                self.session.available=False
                if owner is not None:owner._fence_coordinator()
                raise
            return dict(format='project_execution_reconciliation_v1',origin_catalog_id=self.db.dataset_id,
                        run_ids=sorted([run['id'] for entry,run in plans]),available=self.session.available)
