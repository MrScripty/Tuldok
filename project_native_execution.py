"""Current native probe/train/verifier phases; retained phases are inert facts.

Only an explicitly authorized preparation or an actual local Run continuation
may call the phase owner. Reading a checkpoint validates these documents and
their immutable evidence without preparing files, importing workers, or GO.
"""
import copy
from datetime import datetime
import hashlib
import os
from pathlib import Path
import stat
import sys
import time
import uuid

import agent_api
import recipe_process
from pipeline import adapter_for_graph, adapter_identity_for_graph, decode_probe_observation, digest
from project_native_process import ENVIRONMENT, PHASES, WORKERS, prepare, validate_prepared_spec, validate_job_evidence
from project_session import REQUEST_KEY
from workbench import WorkbenchError, timestamp

FAMILY = 'native_execution_history'
FORMAT = 'native_execution_history_v1'
STATES = ('prepared', 'ready', 'go_intent', 'completed', 'failed', 'unknown')
FIELDS = {'format','origin_catalog_id','phase_id','phase','run_id','recipe',
          'request_key','request_sha256','actor_id','definition_identity','spec','events','payloads','observations','probe_result'}
OBSERVATIONS = {'job_template':('native-job-template.json',65536),
    'effective_job':('effective-job.json',65536),'parent_observation':('native-parent-observation.json',65536),
    'drain_receipt':('receipt.json',16384),'probe_stdout':('stdout.log',32768)}
PHASE_WALL_SECONDS = {'probe':45,'train':600,'verify':90}
PARENT_DRAIN_ALLOWANCE = 5


def native_admission_wall_seconds():
    """New material's finite probe/train/verifier and custody time allowance.

    This budgets child/custodian phases, not a storage availability guarantee.
    Cleanup already includes the custodian's TERM grace interval.
    """
    overhead=recipe_process.READY_SECONDS+recipe_process.GO_WAIT_SECONDS+recipe_process.CLEANUP_SECONDS+PARENT_DRAIN_ALLOWANCE
    return sum(PHASE_WALL_SECONDS.values())+len(PHASE_WALL_SECONDS)*overhead


def _fail(message, code='invalid'):
    raise WorkbenchError(message, code, 409 if code != 'invalid' else 400)


def _id(value):
    if type(value) is not str or recipe_process.ID.fullmatch(value) is None:
        _fail('Invalid native execution identity.')


def _sha(value):
    if type(value) is not str or recipe_process.HASH.fullmatch(value) is None:
        _fail('Invalid native execution digest.')


def phase_reference(value):
    event=value['events'][-1]
    return dict(format='project_native_phase_v1',origin_catalog_id=value['origin_catalog_id'],
        phase_id=value['phase_id'],phase=value['phase'],run_id=value['run_id'],state=event['state'],
        spec_sha256=hashlib.sha256(recipe_process.encoded(value['spec'])).hexdigest(),
        receipt_sha256=event['receipt_sha256'])


def classify_probe(recipe,raw):
    """Process drainage and a valid native runtime observation are distinct."""
    result=dict(stdout=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
    if len(raw)>32768:return dict(result,outcome='too_large')
    try:text=raw.decode('utf8')
    except UnicodeError:return dict(result,outcome='invalid_utf8')
    try:decode_probe_observation(recipe,recipe_process.decode(text))
    except (WorkbenchError,recipe_process.ProcessError):return dict(result,outcome='invalid_observation')
    return dict(result,outcome='valid')


def decode_records(records, *, artifacts=None):
    """Check exact finite phase/evidence closure, never local process state."""
    result={}
    availability={}
    declarations={r['id']:r['document'] for r in records if r['family']=='project_artifact'}
    try:
        for record in records:
            if record['family']!=FAMILY:continue
            value=record['document']
            if type(value) is not dict or set(value)!=FIELDS or value['format']!=FORMAT:
                _fail('Invalid native phase document.')
            for key in ('origin_catalog_id','phase_id','actor_id'):_id(value[key])
            if record['id']!=value['origin_catalog_id']+'.'+value['phase_id'] or record['id'] in result:
                _fail('Native phase envelope identity differs.')
            if value['phase'] not in PHASES or value['phase']!='probe' and value['run_id'] is None:
                _fail('Native phase does not match its Run association.')
            if value['run_id'] is not None:_id(value['run_id'])
            if type(value['request_key']) is not str or REQUEST_KEY.fullmatch(value['request_key']) is None:
                _fail('Invalid native phase request key.')
            _sha(value['request_sha256'])
            adapter_identity_for_graph(dict(recipe=value['recipe']))
            definition=value['definition_identity']
            if (type(definition) is not dict or set(definition)!={'definition_files','adapter_definition_sha256'}
                    or type(definition['definition_files']) is not dict or not definition['definition_files']
                    or len(definition['definition_files'])>120
                    or digest(definition['definition_files'])!=definition['adapter_definition_sha256']):
                _fail('Native definition identity differs.')
            for name,sha in definition['definition_files'].items():
                if (type(name) is not str or '/' in name or '\\' in name or not name.endswith('.py')):
                    _fail('Invalid native definition source name.')
                _sha(sha)
            worker=Path(adapter_for_graph(dict(recipe=value['recipe'])).__file__).name
            spec=validate_prepared_spec(value['spec'],phase=value['phase'],worker=worker)
            if (spec['attempt_id']!=value['phase_id'] or spec['request_sha256']!=value['request_sha256']
                    or spec['env']!=ENVIRONMENT or spec.get('native_loader_policy')!='glibc_x86_64_no_preload_v1'
                    or spec['wall_seconds']!=PHASE_WALL_SECONDS[value['phase']]
                    or spec['max_output_bytes']!=64*1024*1024 or not 1<=len(spec['runtime_files'])<=3):
                _fail('Native phase specification differs from its exact owner identity or environment.')
            events=value['events']
            if type(events) is not list or not 1<=len(events)<=4:
                _fail('Native phase has invalid bounded transitions.')
            previous=None;helper=None
            for index,event in enumerate(events):
                if type(event) is not dict or set(event)!={'state','at','actor_id','helper','receipt_sha256'}:
                    _fail('Unclassified native phase event.')
                _id(event['actor_id'])
                state=event['state']
                allowed={'prepared':{'ready','failed','unknown'},'ready':{'go_intent','failed','unknown'},
                         'go_intent':{'completed','failed','unknown'}}
                if (index==0 and state!='prepared' or index>0 and state not in allowed.get(previous,set())):
                    _fail('Invalid native phase transition.')
                if type(event['at']) is not str or len(event['at'])>80 or datetime.fromisoformat(event['at']).utcoffset() is None:
                    _fail('Native phase requires an offset timestamp.')
                if event['helper'] is not None:
                    if not recipe_process.valid_identity(event['helper']) or helper is not None and helper!=event['helper']:
                        _fail('Native phase helper identity changed.')
                    helper=event['helper']
                if state in ('ready','go_intent','completed') and event['helper'] is None:
                    _fail('Native phase lacks its actual READY helper observation.')
                if event['receipt_sha256'] is not None:
                    _sha(event['receipt_sha256'])
                    if state not in ('completed','failed'):_fail('Native drainage proof precedes terminal observation.')
                if state=='completed' and event['receipt_sha256'] is None:
                    _fail('Native completed phase requires its exact drainage proof.')
                previous=state
            payloads=value['payloads']
            if type(payloads) is not list or len(payloads)>180:_fail('Native payload inventory exceeds its bound.')
            runs=[];output_names=set()
            if value['run_id'] is not None:
                runs=[r['document']['run'] for r in records if r['family']=='run_history'
                      and r['id']==value['origin_catalog_id']+'.'+value['run_id']]
                if len(runs)!=1:_fail('Native phase lacks its exact retained Run.')
                from runs import native_payload_names
                output_names={'output/'+name for name in native_payload_names(runs[0])|{'artifact-manifest.json'}}
            names=set();byname={}
            for edge in payloads:
                if (type(edge) is not dict or set(edge)!={'name','blob','role','preservation','required_for'}
                        or edge['role'] not in ('execution_source','execution_spec','custody_proof','measured_job','measured_stream','measured_output')
                        or edge['preservation']!='unique' or edge['required_for']!=['execution_proof']
                        or type(edge['name']) is not str or edge['name'] in names):
                    _fail('Invalid native phase evidence edge.')
                name=edge['name'];names.add(name);blob=edge['blob']
                if (name not in ('spec.json','native-job-template.json','effective-job.json','native-parent-observation.json',
                                 'stdout.log','stderr.log','receipt.json') and
                        not (name.startswith('source/') and name[7:] in {*definition['definition_files'],'native_process_bootstrap.py'})
                        and name not in output_names):
                    _fail('Unsupported native phase evidence path.')
                role=('execution_source' if name.startswith('source/') else 'measured_output' if name.startswith('output/')
                      else 'execution_spec' if name in ('spec.json','native-job-template.json')
                      else 'measured_stream' if name in ('stdout.log','stderr.log')
                      else 'custody_proof' if name=='receipt.json' else 'measured_job')
                if edge['role']!=role:_fail('Native evidence edge has a different finite role.')
                if type(blob) is not dict or set(blob)!={'sha256','bytes'}:_fail('Invalid native evidence blob.')
                _sha(blob['sha256'])
                if type(blob['bytes']) is not int or not 0<=blob['bytes']<=64*1024*1024:
                    _fail('Native evidence exceeds its owner bound.')
                if declarations.get(blob['sha256'])!=dict(format='project_artifact_v1',**blob):
                    _fail('Native evidence declaration is missing or differs.')
                byname[name]=blob
                if artifacts is not None and blob['sha256'] not in availability:
                    observed=artifacts.status(dict(format='project_artifact_v1',**blob))
                    if observed['state']=='corrupt':_fail('Present native evidence differs from its declared bytes.')
                    availability[blob['sha256']]=observed['state']=='verified'
            observations=value['observations']
            if type(observations) is not dict or set(observations)!=set(OBSERVATIONS):
                _fail('Native phase has unclassified canonical observations.')
            proofs={}
            for key,(name,maximum) in OBSERVATIONS.items():
                text=observations[key]
                if text is not None:
                    if type(text) is not str:_fail('Native proof must retain its exact UTF8 observation.')
                    raw=text.encode('utf8')
                    if len(raw)>maximum or byname.get(name)!=dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)):
                        _fail('Canonical native observation differs from its exact evidence edge.')
                    proofs[key]=raw
            spec_raw=recipe_process.encoded(spec)
            if byname.get('spec.json')!=dict(sha256=hashlib.sha256(spec_raw).hexdigest(),bytes=len(spec_raw)):
                _fail('Native phase lacks its exact prepared specification.')
            for name,sha in definition['definition_files'].items():
                if byname.get('source/'+name,{}).get('sha256')!=sha:
                    _fail('Native phase lacks exact qualified source bytes.')
            captures={str(Path(item['path']).relative_to(spec['cwd'])):dict(sha256=item['sha256'],bytes=item['bytes'])
                      for item in spec['captured_files']}
            if set(captures)!={'source/'+name for name in definition['definition_files']}|(
                    {'source/native_process_bootstrap.py','native-job-template.json'} if value['phase']!='probe' else set()):
                _fail('Native phase capture inventory differs from its finite definition closure.')
            for name,blob in captures.items():
                if byname.get(name)!=blob:_fail('Native phase lacks exact immutable capture evidence.')
            if value['run_id'] is not None:
                if (len(runs)!=1 or runs[0]['graph']['recipe']!=value['recipe']
                        or runs[0]['runtime']['definition_files']!=definition['definition_files']):
                    _fail('Native phase differs from its retained Run and exact adapter.')
            if (value['phase']=='probe')!=(observations['job_template'] is None):
                _fail('Native job template observation differs from its phase.')
            if value['phase']!='probe' and observations['probe_stdout'] is not None:
                _fail('Training/verifier logs are not probe runtime observations.')
            if (observations['effective_job'] is None)!=(observations['parent_observation'] is None):
                _fail('Native measured parent/job observations must be retained together.')
            if value['phase']!='probe':
                template=recipe_process.decode(proofs['job_template'])
                if (type(template) is not dict or set(template)!={'format','phase','worker','attempt_id','request_sha256','job'}
                        or template['format']!='native_parent_binding_v1' or template['phase']!=value['phase']
                        or template['worker']!=worker or template['attempt_id']!=value['phase_id']
                        or template['request_sha256']!=value['request_sha256']):
                    _fail('Native job template differs from its exact phase.')
                job=adapter_for_graph(dict(recipe=value['recipe']))._checked_job(template['job'])
                run=runs[0]
                from pipeline import model_aware_graph
                import image_training
                expected_job=dict(schema_version=1,dataset_id=run['dataset_id'],run_id=run['id'],
                    graph_sha256=run['graph_sha256'],release_id=run['release_id'],release_sha256=run['release_sha256'],
                    release_path=job['release_path'],output_dir=spec['output_dir'],parameters=run['parameters'],parent_pid=1)
                if value['recipe']==image_training.MODEL_RECIPE:
                    expected_job.update(schema_version=2,evidence_context=run['evidence_context'])
                elif model_aware_graph(run['graph']):
                    from one_fit_evidence import job_for_run
                    expected_job=job_for_run(run,spec['output_dir'])
                    # Historical Run projection deliberately carries no live
                    # release path. Its absolute template observation is inert;
                    # scientific release identity and all evidence selections
                    # remain exact projections of the retained Run owner.
                    expected_job['release_path']=job['release_path']
                if (agent_api.encoded(job)!=agent_api.encoded(template['job'])
                        or agent_api.encoded(job)!=agent_api.encoded(expected_job)):
                    _fail('Native job template differs from its exact scientific Run inputs.')
            receipt_sha=events[-1]['receipt_sha256']
            if (receipt_sha is None)!=(observations['drain_receipt'] is None):
                _fail('Native terminal receipt observation differs from its acknowledged phase.')
            if receipt_sha is not None:
                if byname.get('receipt.json',{}).get('sha256')!=receipt_sha:
                    _fail('Native terminal observation differs from its retained receipt.')
                if observations['drain_receipt'] is not None:
                    raw=proofs['drain_receipt']
                    expected=dict(attempt_id=value['phase_id'],request_sha256=value['request_sha256'],
                                  spec_sha256=hashlib.sha256(spec_raw).hexdigest(),helper=helper)
                    receipt=recipe_process.validate_receipt(raw,expected)
                    validate_job_evidence(spec,phase=value['phase'],helper=helper,
                        template=proofs.get('job_template'),effective_job=proofs.get('effective_job'),
                        parent_observation=proofs.get('parent_observation'),receipt=receipt)
                    if not receipt['drained'] or (previous=='completed')!=(receipt['outcome']=='completed'):
                        _fail('Native terminal state differs from measured drainage.')
                    for stream in ('stdout','stderr'):
                        if byname.get(stream+'.log')!=receipt['streams'][stream]:
                            _fail('Native measured stream differs from its exact receipt.')
                    if value['phase']=='probe':
                        classified=value['probe_result']
                        if (type(classified) is not dict or set(classified)!={'outcome','stdout'}
                                or classified['outcome'] not in ('valid','invalid_utf8','invalid_observation','too_large')
                                or classified['stdout']!=byname.get('stdout.log')):
                            _fail('Native probe protocol observation differs from measured stdout.')
                        if observations['probe_stdout'] is not None:
                            if classify_probe(value['recipe'],proofs['probe_stdout'])!=classified:
                                _fail('Canonical native probe classification differs from exact stdout.')
                        elif classified['outcome'] not in ('invalid_utf8','too_large'):
                            _fail('A bounded UTF8 native probe requires its exact canonical stdout.')
                        if (classified['outcome']=='too_large')!=(classified['stdout']['bytes']>32768):
                            _fail('Native oversized probe observation has a different bound.')
                        if artifacts is not None and availability.get(classified['stdout']['sha256']):
                            actual=artifacts.read_blob(classified['stdout'],maximum_bytes=recipe_process.STREAM_LIMIT)
                            if classify_probe(value['recipe'],actual)!=classified:
                                _fail('Present native probe bytes differ from the classified observation.')
            elif value['probe_result'] is not None:
                _fail('Native probe protocol result precedes its measured terminal receipt.')
            if value['phase']!='probe' and value['probe_result'] is not None:
                _fail('Only a probe phase may classify a runtime response.')
            result[record['id']]=copy.deepcopy(value)
        return result
    except WorkbenchError:raise
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        _fail('Malformed retained native execution phase.')


class _RunAuthority:
    """One actual current SQL admission, never constructed from a checkpoint."""
    def __init__(self,native,run_id):
        self.native=native;self.run_id=run_id
        self.recipe=native.execution.runs._load(run_id)['graph']['recipe']

    def authorize_probe(self,recipe):
        execution=self.native.execution;owner=execution.runs
        with execution.db.lock:
            run=owner._load(self.run_id);execution._proof(run)
            context=execution.runtime_access.require_job('runs',run['id'],run['admission_id'],run['request_sha256'])
            execution.runtime_access.require('edit','runs.update',run['id'])
            execution.runtime_access.require('execute','pipeline.probe_native',recipe)
            if recipe!=self.recipe or run['state'] not in ('queued','running','cancelling'):
                _fail('Current native Run cannot observe this phase.','unavailable')
            inputs=self.native._run_inputs.get(run['id'])
            if inputs is None:_fail('A retained native Run has no current one-use qualification.','unavailable')
            if (os.environ.get('TULDOK_TRAINING_PYTHON') or sys.executable)!=inputs['runtime']['executable']:
                _fail('Configured native interpreter changed after admission.','stale')
            from project_native_process import current_runtime
            if current_runtime(inputs['runtime']['executable'])!=inputs['runtime']:
                _fail('Current native interpreter changed after admission.','stale')
            if owner.pipelines.definition_identity(recipe)!=inputs['definition_identity']:
                _fail('Native adapter changed after admission.','stale')
            return context

    def dispatch_allowed(self):
        owner=self.native.execution.runs;run=owner._load(self.run_id)
        if run['state'] not in ('queued','running') or owner._stop.is_set() or owner._blocked:
            _fail('Current native Run no longer permits dispatch.','unavailable')


class _ReconciliationAuthority:
    def __init__(self,native,recipe):self.native=native;self.recipe=recipe
    def authorize_probe(self,recipe):
        if recipe!=self.recipe:_fail('Native reconciliation phase changed.','conflict')
        return self.native.access.require('cancel','native_execution.reconcile',owner_only=True)


class ProjectNativeExecution:
    """The fixed current phase owner; construction is entirely inert."""
    def __init__(self, execution):
        self.execution=execution;self.projection=execution.projection
        self.session=execution.session;self.db=execution.db;self.access=execution.runtime_access
        self._dirty={};self._handles={};self._prepared={};self._contexts={};self._active=set();self._run_inputs={}
        self._never_launched=set()
        self._foreground_phase=None

    @property
    def has_dirty(self):return bool(self._dirty)

    @property
    def has_local_custody(self):
        return bool(self._active or self._handles)

    def capture_dirty(self, before_records):
        records=[]
        for phase_id,document in self._dirty.items():
            self._authorize(phase_id)
            records.append(dict(family=FAMILY,id=document['origin_catalog_id']+'.'+phase_id,document=copy.deepcopy(document)))
            records.extend(dict(family='project_artifact',id=edge['blob']['sha256'],
                document=dict(format='project_artifact_v1',**edge['blob'])) for edge in document['payloads'])
        return records

    def outcome(self, outcome):
        if outcome not in ('committed','rolled_back','unknown'):raise ValueError('Invalid native SQL outcome.')
        self._dirty.clear()
        if outcome=='unknown' or not self.session.available:
            for handle in self._handles.values():handle.close_control(wait=False)

    def abandon_pending(self):
        if not self.execution._reconstructing:raise RuntimeError('Native pending capture clears only during guarded reconstruction.')
        self._dirty.clear()

    def _authorize(self, phase_id):
        context=self._contexts.get(phase_id)
        if context is None:_fail('Native phase has no actual current preparation context.','unavailable')
        return context.authorize_probe(context.recipe)

    def authorize_dirty(self):
        for phase_id in self._dirty:self._authorize(phase_id)

    def _dispatch_authorized(self,phase_id):
        actor=self._authorize(phase_id)
        context=self._contexts[phase_id]
        if isinstance(context,_RunAuthority):context.dispatch_allowed()
        return actor

    def _retain(self, document, name, raw, role):
        declaration=dict(format='project_artifact_v1',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        self.session.artifacts.publish_bytes(raw,declaration,maximum_bytes=64*1024*1024)
        document['payloads'].append(dict(name=name,blob={k:declaration[k] for k in ('sha256','bytes')},
            role=role,preservation='unique',required_for=['execution_proof']))
        for key,(filename,maximum) in OBSERVATIONS.items():
            if name==filename and (key!='probe_stdout' or document['phase']=='probe'):
                if key=='probe_stdout':
                    document['probe_result']=classify_probe(document['recipe'],raw)
                    try:text=raw.decode('utf8') if len(raw)<=maximum else None
                    except UnicodeError:text=None
                    document['observations'][key]=text
                else:
                    if len(raw)>maximum:_fail('Native canonical observation exceeds its fixed bound.')
                    document['observations'][key]=raw.decode('utf8')

    def _retain_outputs(self,document,*,run=None,output=None):
        """Preserve measured native outputs without claiming their validity."""
        if document['phase']=='probe':return
        from runs import native_payload_names
        run=run if run is not None else self.execution.runs._load(document['run_id'])
        allowed=native_payload_names(run)|{'artifact-manifest.json'}
        # A saved pathname is an observation, never a directory capability.
        # Select only this physical projection's exact phase stage, including
        # the earlier training stage explicitly associated with a verifier.
        from project_store import DIR_FLAGS, FILE_FLAGS, ProjectStoreError, _open_directory_path, anchored_directory
        stage_id=document['phase_id']
        if document['phase']=='verify':
            matches=[row['document'] for row in self.session.snapshot['records']
                if row['family']==FAMILY and row['document']['phase']=='train'
                and row['document']['origin_catalog_id']==self.db.dataset_id
                and row['document']['run_id']==document['run_id']]
            if len(matches)!=1:_fail('Native verifier lacks its exact training stage.','unknown')
            stage_id=matches[0]['phase_id']
        _id(stage_id)
        relative='project-native-phases/'+stage_id+'/output'
        expected=self.db.path/relative
        if document['spec']['output_dir']!=str(expected) or output is not None and Path(output)!=expected:
            _fail('Native measured output is not its original local stage.','unknown')
        root=None;captured=[];total=0
        def identity(info):
            return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns
        try:
            root_path,root=_open_directory_path(self.db.path)
            with anchored_directory(root,relative,root_path=root_path) as directory:
                before=os.fstat(directory);names=sorted(os.listdir(directory))
                for name in names:
                    if name not in allowed:_fail('Native worker produced an unclassified output; retain local custody.','unknown')
                    descriptor=os.open(name,FILE_FLAGS,dir_fd=directory)
                    try:
                        info=os.fstat(descriptor)
                        if not stat.S_ISREG(info.st_mode) or info.st_size>document['spec']['max_output_bytes']:
                            _fail('Native output is not an admitted bounded regular file.','unknown')
                        chunks=[];remaining=document['spec']['max_output_bytes']-total+1
                        while remaining:
                            chunk=os.read(descriptor,min(remaining,65536))
                            if not chunk:break
                            chunks.append(chunk);remaining-=len(chunk)
                        raw=b''.join(chunks);total+=len(raw)
                        if (total>document['spec']['max_output_bytes'] or identity(info)!=identity(os.fstat(descriptor))
                                or identity(info)!=identity(os.stat(name,dir_fd=directory,follow_symlinks=False))):
                            _fail('Native output changed during its measured observation.','unknown')
                        captured.append((name,raw))
                    finally:os.close(descriptor)
                if identity(before)!=identity(os.fstat(directory)) or names!=sorted(os.listdir(directory)):
                    _fail('Native output directory changed during observation.','unknown')
            # The anchored context rechecks the complete directory binding
            # before any bytes receive canonical measured-output attribution.
            for name,raw in captured:self._retain(document,'output/'+name,raw,'measured_output')
        except (OSError,ProjectStoreError) as error:
            raise WorkbenchError('Native output stage is unavailable or changed; retain local custody.','unknown',409) from error
        finally:
            if root is not None:os.close(root)

    def _publish(self, document, state, *, helper=None, receipt_sha256=None):
        with self.db.lock,self.db.transaction():
            self.session.check();actor=self._authorize(document['phase_id'])
            document['events'].append(dict(state=state,at=timestamp(),actor_id=actor.actor_id,
                helper=copy.deepcopy(helper),receipt_sha256=receipt_sha256))
            self._dirty[document['phase_id']]=copy.deepcopy(document)
        if state!='prepared' and self.execution.custody is not None:
            with self.execution._journal_guard():self.execution.custody.native_observed(document)

    def assert_quiescent(self):
        if self.has_local_custody:_fail('Current native phase custody requires explicit drainage.','busy')

    def reconcile(self,phase_id,expected_checkpoint):
        """Observe exact original-host drainage; never prepare, import or GO."""
        import json
        from project_native_process import read_phase_evidence
        _id(phase_id);_sha(expected_checkpoint)
        self.access.require('cancel','native_execution.reconcile',phase_id,owner_only=True)
        if self.db.lock.owned_by_current_thread or self.db.in_transaction:
            _fail('Native custody reconciliation must drain outside command locks.','busy')
        execution=self.execution;journal=execution.custody
        if journal is None:_fail('There is no original local native custody.','unavailable')
        with self.db.lock:
            if self.session.snapshot['checkpoint']!=expected_checkpoint:_fail('Expected native recovery checkpoint changed.','stale_project')
            local=journal.refresh()
            selected=next((row for row in local.get('native_phases',[]) if row['phase_id']==phase_id),None)
            if selected is None:_fail('A retained phase alone cannot select current native custody.','unavailable')
            if (local['runs'] or local['producers'] or local['runtime_effects'] or local['package_effects']
                    or any(row['run_id']!=selected['run_id'] for row in local.get('native_admissions',[]))
                    or execution._runtime_active or execution._package_active):
                _fail('Other current effect owners must reconcile first.','busy')
            entries=[row for row in local['native_phases']
                     if row['phase_id']==phase_id or selected['run_id'] is not None and row['run_id']==selected['run_id']]
            if len(entries)!=len(local['native_phases']):_fail('Other native custody remains unresolved.','busy')
            if not self.db.claim_runtime('project_native_phases'):_fail('The original native application is still active.','busy')
            other=self.db.execute("SELECT id FROM workspace_runs WHERE document::jsonb->>'state' IN ('queued','running','cancelling','unknown') AND id<>%s",
                                  (selected['run_id'] or '',)).fetchall()
            if other:_fail('Another current Run must drain before native recovery.','busy')
        owner=execution._runs
        if owner is not None:owner._fence_coordinator()
        for entry in entries:
            handle=self._handles.get(entry['phase_id'])
            if handle is not None:
                receipt=handle.close_control()
                if not receipt or not receipt.get('drained'):_fail('Actual native helper has not drained.','unknown')
        if owner is not None and owner._thread is not None:
            owner._thread.join(60)
            if owner._thread.is_alive():_fail('Current native supervisor has not drained.','busy')
        if self._active:_fail('Current native owner has not finished its bounded observation.','busy')
        with execution.access.lock,self.session.lock,self.db.lock:
            self.access.require('cancel','native_execution.reconcile',phase_id,owner_only=True)
            if self.session.snapshot['checkpoint']!=expected_checkpoint:_fail('Native checkpoint changed while draining.','stale_project')
            if journal.refresh()!=local:_fail('Original native custody changed while draining.','stale_project')
            binding=journal.binding
            if (binding['project_id']!=self.db.dataset_id or binding['projection_id']!=self.db.projection_id
                    or binding['host_catalog_id']!=execution.access.catalog_id):
                _fail('Native custody belongs to another physical owner.','local_custody_unavailable')
            self.session.available=False
            snapshot=self.session.store.recover_checkpoint();journal.validate_selection(snapshot)
            with self.session.store.root_directory() as descriptor:
                info=os.fstat(descriptor)
                if [info.st_dev,info.st_ino]!=binding['root_identity']:
                    _fail('Native custody belongs to another physical project root.','local_custody_unavailable')
            documents=decode_records(snapshot['records'],artifacts=self.session.artifacts)
            phases=[];local_run=None;retained_run=None
            if selected['run_id'] is not None:
                if owner is None and not self.db.claim_runtime('workspace_runs'):
                    _fail('The original Run application still owns this projection.','busy')
                row=self.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(selected['run_id'],)).fetchone()
                if row is None:_fail('Native custody has no original local Run admission.','local_custody_unavailable')
                local_run=json.loads(row['document']);execution._proof(local_run)
                retained_run=next((row['document']['run'] for row in snapshot['records'] if row['family']=='run_history'
                    and row['id']==self.db.dataset_id+'.'+selected['run_id']),None)
                immutable=('id','dataset_id','request_key','request_sha256','admission_id','graph_sha256','release_sha256','runtime')
                if retained_run is None or any(local_run.get(key)!=retained_run.get(key) for key in immutable):
                    _fail('Original native Run admission differs from retained science.','local_custody_unavailable')
            for entry in entries:
                document=copy.deepcopy(documents.get(self.db.dataset_id+'.'+entry['phase_id']))
                stage=self.db.path/'project-native-phases'/entry['phase_id']
                if (document is None or document['run_id']!=entry['run_id'] or document['phase']!=entry['phase']
                        or document['request_sha256']!=entry['request_sha256'] or document['spec']['cwd']!=str(stage)
                        or hashlib.sha256(recipe_process.encoded(document['spec'])).hexdigest()!=entry['spec_sha256']):
                    _fail('Original native phase differs from its exact physical journal.','local_custody_unavailable')
                if entry['helper'] is None:
                    # A prepared journal has not acknowledged launch intent.
                    # After intent, only this process's retained call boundary
                    # proves Popen was never entered; a restarted owner cannot
                    # convert that ambiguous spawn window into cessation.
                    if entry['state']!='prepared' and not (entry['state']=='launch_intent' and entry['phase_id'] in self._never_launched):
                        _fail('Original native launch lacks an exact helper drainage identity.','unknown')
                    evidence=None
                else:evidence=read_phase_evidence(stage,document['spec'],phase=entry['phase'],helper=entry['helper'])
                phases.append((entry,document,evidence))
            # Fixed cache reconstruction happens only after every actual/local
            # effect has a complete drain receipt. It restores no Run or grant.
            self.projection.reconcile_inert(snapshot)
            try:
                for entry,document,evidence in phases:
                    identity=entry['phase_id'];self._contexts[identity]=_ReconciliationAuthority(self,document['recipe'])
                    if evidence is None:
                        if document['events'][-1]['state']!='failed':self._publish(document,'failed')
                        elif entry['state']!='failed':
                            with execution._journal_guard():journal.native_observed(document)
                        with execution._journal_guard():journal.native_not_launched(identity)
                        self._never_launched.discard(identity)
                        continue
                    names={edge['name'] for edge in document['payloads']}
                    for name,raw,role in (('stdout.log',evidence['stdout'],'measured_stream'),
                            ('stderr.log',evidence['stderr'],'measured_stream'),
                            ('receipt.json',recipe_process.encoded(evidence['receipt']),'custody_proof'),
                            ('effective-job.json',evidence['effective_job'],'measured_job'),
                            ('native-parent-observation.json',evidence['parent_observation'],'measured_job')):
                        if raw is not None and name not in names:self._retain(document,name,raw,role)
                    if document['phase']!='probe' and not any(name.startswith('output/') for name in names):
                        output=stage/'output'
                        if document['phase']=='verify':
                            train=next((value for value in documents.values() if value['run_id']==document['run_id']
                                        and value['phase']=='train'),None)
                            if train is None:_fail('Original verifier has no exact retained training phase.','unknown')
                            output=self.db.path/'project-native-phases'/train['phase_id']/'output'
                        if document['spec']['output_dir']!=str(output):_fail('Native output path differs from original local custody.','unknown')
                        if output.exists():self._retain_outputs(document,run=retained_run,output=output)
                    receipt_sha=hashlib.sha256(recipe_process.encoded(evidence['receipt'])).hexdigest()
                    if document['events'][-1]['state'] not in ('completed','failed'):
                        state='completed' if evidence['receipt']['outcome']=='completed' else 'failed'
                        self._publish(document,state,helper=entry['helper'],receipt_sha256=receipt_sha)
                    elif document['events'][-1]['receipt_sha256']!=receipt_sha:
                        _fail('Original native terminal receipt changed.','unknown')
                    elif entry['state'] not in ('completed','failed'):
                        with execution._journal_guard():journal.native_observed(document)
                    self._handles.pop(identity,None)
                if retained_run is not None:
                    current=copy.deepcopy(retained_run)
                    from runs import LOCAL_RUN_FIELDS
                    current.update({key:copy.deepcopy(value) for key,value in local_run.items() if key in LOCAL_RUN_FIELDS})
                    owner=execution._local_owner(recover=False) if owner is None else owner
                    owner._fence_coordinator()
                    with self.db.transaction():
                        execution._proof(current)
                        state='completed' if current['state']=='completed' else 'interrupted'
                        owner._event(current,state,'Original native custody drained; no phase was resumed or regenerated.')
                        owner._save(current)
                elif evidence is not None:
                    journal.native_confirmed(phase_id)
                journal.acknowledge(self.session.snapshot)
                return phase_reference(next(document for entry,document,evidence in phases if entry['phase_id']==phase_id))
            except BaseException:
                self.session.available=False
                if owner is not None:owner._fence_coordinator()
                raise

    def settle_run(self,run):
        if self.execution.custody is None or run['state'] not in ('completed','failed','cancelled','interrupted'):return
        for entry in self.execution.custody.snapshot().get('native_phases',[]):
            if entry['run_id']==run['id'] and entry['state'] in ('completed','failed') and entry['receipt_sha256'] is not None:
                self.execution.custody.native_confirmed(entry['phase_id'])

    def bind_run(self,run):
        """Retain a private measured qualification only during actual admission."""
        if not self.db.in_transaction:_fail('Native qualification binds only inside its admission transaction.')
        if self.execution.runs._validation_run(run):return
        context=self.projection.native_preparation.current(self.execution.runs.pipelines)
        _actor,inputs=self._inputs(run['graph']['recipe'],context)
        if (run['runtime']['definition_files']!=inputs['definition_identity']['definition_files']
                or run['runtime']['adapter_definition_sha256']!=inputs['definition_identity']['adapter_definition_sha256']):
            _fail('Native Run differs from its qualified adapter.','stale')
        if run['id'] in self._run_inputs:_fail('A native Run qualification cannot be replaced.','conflict')
        self._run_inputs[run['id']]=copy.deepcopy(inputs)
        self.db.on_rollback(lambda:self._run_inputs.pop(run['id'],None))

    def probe_current_run(self,owner,recipe):
        from access import current_context
        context=current_context()
        if (context is None or context.mode!='job' or context.kind!='runs'
                or context.catalog_id!=self.db.dataset_id or owner.db is not self.db):
            _fail('Native runtime probing requires its exact current local Run.','unavailable')
        authority=_RunAuthority(self,context.job_id);actor=authority.authorize_probe(recipe)
        inputs=self._run_inputs[context.job_id]
        result=self._run_phase('probe',recipe,'native-run-probe-'+context.job_id,actor,inputs,authority,run_id=context.job_id)
        return dict(runtime=self._probe_result(recipe,inputs,result['evidence']),phase=phase_reference(result['document']))

    def capture_run_payloads(self,run,artifacts):
        """Copy a newly admitted frozen native input, then reuse exact custody."""
        from projects import Projects
        prior=next((record['document'] for record in self.session.snapshot['records']
            if record['family']=='run_history' and record['id']==run['dataset_id']+'.'+run['id']),None)
        if prior is not None:
            retained=[copy.deepcopy(edge) for edge in prior['payloads']
                      if edge['name']=='release.zip' or edge['name'].startswith('source/')]
            expected={'release.zip':run['release_sha256'],
                      **{'source/'+name:sha for name,sha in run['runtime']['definition_files'].items()}}
            if {edge['name']:edge['blob']['sha256'] for edge in retained}!=expected:
                _fail('Native Run input/source custody is incomplete.','unavailable')
            for edge in retained:
                with artifacts.open_verified(dict(format='project_artifact_v1',**edge['blob'])):pass
            return retained
        if run['state']!='queued':_fail('Only an actual newly admitted native Run may capture inputs.','unavailable')
        edges=[]
        release=Path(run['release_path'])
        reader=Projects(self.execution.runs.dataset,{'native_release':release.parent})
        try:
            declaration=dict(format='project_artifact_v1',sha256=run['release_sha256'],bytes=run['release_bytes'])
            with reader._file('native_release',release.name) as (descriptor,_info):artifacts.publish_fd(descriptor,declaration)
            edges.append(dict(name='release.zip',blob={key:declaration[key] for key in ('sha256','bytes')},
                population='unknown',role='captured_input',preservation='unique',required_for=['scientific_inspection','execution_proof']))
        finally:reader.close()
        inputs=self._run_inputs.get(run['id'])
        if self.execution.runs._validation_run(run):
            sources={name:(self.execution.runs.pipelines.source_path/name).read_bytes()
                     for name in run['runtime']['definition_files']}
        elif inputs is None:_fail('Native input capture has no current qualification.','unavailable')
        else:sources=inputs['sources']
        for name,raw in sorted(sources.items()):
            if hashlib.sha256(raw).hexdigest()!=run['runtime']['definition_files'][name]:
                _fail('Native source changed before canonical admission.','stale')
            declaration=dict(format='project_artifact_v1',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
            artifacts.publish_bytes(raw,declaration)
            edges.append(dict(name='source/'+name,blob={key:declaration[key] for key in ('sha256','bytes')},
                population='unknown',role='execution_source',preservation='unique',required_for=['scientific_inspection','execution_proof']))
        return edges

    def execute_run(self,run_id):
        """Run the existing CPU owners through three fixed custody phases."""
        from pipeline import model_aware_graph
        from types import SimpleNamespace
        from runs import _sync
        owner=self.execution.runs
        with self.db.lock,self.db.transaction():
            run=owner._load(run_id)
            self.access.require_job('runs',run_id,run['admission_id'],run['request_sha256'])
            if run['state']!='queued' or owner._stop.is_set() or owner._blocked:return
            owner._event(run,'running','Verifying exact frozen native inputs before current CPU phases.')
            run['started_at']=timestamp();run['progress']['stage']='validate';owner._save(run)
        try:
            if owner._validation_run(run):return owner._execute_validation(run)
            runtime=owner.pipelines.probe(run['graph']['recipe'])
            if not runtime['available'] or runtime!=run['runtime']:_fail('Native runtime changed after admission.','stale')
            release=owner.pipelines.inspect_release(run['release_id'],private=True,recipe=run['graph']['recipe'])
            if release['sha256']!=run['release_sha256']:_fail('Native frozen release changed after admission.','stale')
            authority=_RunAuthority(self,run_id);actor=authority.authorize_probe(run['graph']['recipe'])
            phase_id=uuid.uuid4().hex;output=self.db.path/'project-native-phases'/phase_id/'output'
            job=dict(schema_version=1,dataset_id=run['dataset_id'],run_id=run_id,graph_sha256=run['graph_sha256'],
                release_id=run['release_id'],release_sha256=run['release_sha256'],release_path=release['path'],
                output_dir=str(output),parameters=run['parameters'],parent_pid=1)
            if run['graph']['recipe']=='image_classification_model_v2':
                job.update(schema_version=2,evidence_context=run['evidence_context'])
            elif model_aware_graph(run['graph']):
                from one_fit_evidence import job_for_run
                job.update(job_for_run(run,output),parent_pid=1,release_path=release['path'])
            with self.db.lock,self.db.transaction():
                current=owner._load(run_id);current['progress']['stage']='train'
                current['execution_test_exposure']=owner.pipelines.exposures(current['source_records'])
                for node in current['node_attempts']:
                    node['state']='completed' if node['type'] in ('release','validate') else 'running' if node['type']=='train' else 'pending'
                owner._save(current)
            trained=self._run_phase('train',run['graph']['recipe'],'native-train-'+run_id,actor,
                self._run_inputs[run_id],authority,run_id=run_id,job=job,phase_id=phase_id)
            if trained['evidence']['receipt']['outcome']!='completed':
                state='cancelled' if trained['evidence']['receipt']['outcome']=='cancelled' else 'failed'
                return owner._finish(run_id,state,'Native trainer drained without publishing results.')
            with (trained['prepared'].stage/'custody/stdout.log').open('rb') as stream:
                owner._read_progress(SimpleNamespace(stdout=stream),run,dict(buffer=b'',bytes=0,epoch=0))
            artifacts,metrics=owner._verify_directory(run,output)
            if model_aware_graph(run['graph']):
                verified=self._run_phase('verify',run['graph']['recipe'],'native-verify-'+run_id,actor,
                    self._run_inputs[run_id],authority,run_id=run_id,job=job)
                if verified['evidence']['receipt']['outcome']!='completed':
                    state='cancelled' if verified['evidence']['receipt']['outcome']=='cancelled' else 'failed'
                    return owner._finish(run_id,state,'Independent checkpoint verification drained without accepting outputs.')
            for path in output.iterdir():
                with path.open('rb') as source:os.fsync(source.fileno())
            _sync(output)
            with self.db.lock,self.db.transaction():
                current=owner._load(run_id)
                if current['state']=='cancelling' or owner._stop.is_set():
                    owner._event(current,'cancelled','Native workers drained before final publication.');owner._save(current);return
                os.rename(output,owner.path/run_id);_sync(owner.path)
                current['artifacts']=artifacts;current['metrics']=metrics
                for node in current['node_attempts']:node['state']='completed'
                owner._event(current,'completed','Measured native CPU outputs and independent evidence published after custody drainage.')
                owner._save(current)
        except (WorkbenchError,recipe_process.ProcessError) as error:
            state='unknown' if error.code in ('unknown','outcome_unknown') else 'failed'
            owner._finish(run_id,state,str(error),error.code)

    def _inputs(self, recipe, preparation):
        from project_native_preparation import NativePreparationContext
        if type(preparation) is not NativePreparationContext or preparation.recipe!=recipe:
            _fail('Native probing requires its actual current preparation context.','unavailable')
        actor=preparation.authorize_probe(recipe)
        inputs=preparation.native_inputs(recipe)
        if type(inputs) is not dict or set(inputs)!={'runtime','worker','sources','model_aware','definition_identity'}:
            _fail('Native preparation supplied unclassified phase inputs.')
        if inputs['worker'] not in WORKERS or type(inputs['model_aware']) is not bool:
            _fail('Native preparation supplied an unsupported adapter.')
        definition=inputs['definition_identity']
        if (type(definition) is not dict or set(definition)!={'definition_files','adapter_definition_sha256'}
                or type(inputs['sources']) is not dict or set(inputs['sources'])!=set(definition['definition_files'])
                or digest(definition['definition_files'])!=definition['adapter_definition_sha256']
                or any(type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=definition['definition_files'][name]
                       for name,raw in inputs['sources'].items())):
            _fail('Native measured sources differ from their exact definition.','stale')
        return actor,inputs

    def probe(self, recipe, *, expected_checkpoint, request_key, preparation):
        """Explicitly measure a native runtime behind canonical launch/GO ACKs."""
        if self.db.in_transaction:
            _fail('Native probing must precede the foreground admission transaction.','busy')
        if type(request_key) is not str or REQUEST_KEY.fullmatch(request_key) is None:
            _fail('Invalid native probe request key.')
        with self.db.lock:
            current=self.session.check()
            if current['checkpoint']!=expected_checkpoint:_fail('Native preparation checkpoint changed.','stale_project')
            actor,inputs=self._inputs(recipe,preparation)
            prior=[value for value in decode_records(current['records']).values()
                   if value['origin_catalog_id']==self.session.project_id and value['request_key']==request_key]
            if prior:
                _fail('A previous native probe is historical; start a fresh explicit preparation.','unavailable')
        result=self._run_phase('probe',recipe,request_key,actor,inputs,preparation)
        return dict(runtime=self._probe_result(recipe,inputs,result['evidence']),phase=phase_reference(result['document']))

    @staticmethod
    def _probe_result(recipe, inputs, evidence):
        receipt=evidence['receipt']
        if not receipt['go_received'] or receipt['outcome'] not in ('completed','failed'):
            _fail('The native runtime probe did not produce an acknowledged observation.','unavailable')
        if classify_probe(recipe,evidence['stdout'])['outcome']!='valid':
            _fail('The native runtime probe returned an invalid bounded observation.','unavailable')
        try:probe=decode_probe_observation(recipe,recipe_process.decode(evidence['stdout']))
        except (WorkbenchError,recipe_process.ProcessError):
            _fail('The native runtime probe did not return its bounded observation.','unavailable')
        if receipt['leader_returncode'] and probe['available']:
            _fail('Failed native runtime probe claimed availability.','invalid')
        return dict(probe,**inputs['definition_identity'])

    def _run_phase(self, phase, recipe, request_key, actor, inputs, authority, *, run_id=None, job=None, phase_id=None):
        if self.db.in_transaction:_fail('Native phase cannot launch inside a metadata transaction.','busy')
        with self.db.lock:
            self.session.check()
            if run_id is None and self._foreground_phase is not None:
                _fail('Another explicit native preparation phase is active.','busy')
            if not self.db.claim_runtime('project_native_phases'):_fail('Another current native phase owner is active.','busy')
            phase_id=phase_id or uuid.uuid4().hex
            if run_id is None:self._foreground_phase=phase_id
            self._active.add(phase_id);self._contexts[phase_id]=authority
        document=None;handle=None
        self._never_launched.add(phase_id)
        try:
            parent=self.db.path/'project-native-phases';parent.mkdir(mode=0o700,exist_ok=True)
            request_sha=hashlib.sha256(agent_api.encoded(dict(recipe=recipe,phase=phase,run_id=run_id,job=job,runtime=inputs['runtime'],
                definition_identity=inputs['definition_identity'],request_key=request_key))).hexdigest()
            prepared=prepare(parent/phase_id,phase=phase,attempt_id=phase_id,request_sha256=request_sha,
                runtime=inputs['runtime'],worker=inputs['worker'],sources=inputs['sources'],model_aware=inputs['model_aware'],job=job)
            self._prepared[phase_id]=prepared
            document=dict(format=FORMAT,origin_catalog_id=self.session.project_id,phase_id=phase_id,phase=phase,
                run_id=run_id,recipe=recipe,request_key=request_key,request_sha256=request_sha,actor_id=actor.actor_id,
                definition_identity=copy.deepcopy(inputs['definition_identity']),spec=prepared.spec,events=[],payloads=[],
                observations=dict.fromkeys(OBSERVATIONS),probe_result=None)
            self._retain(document,'spec.json',recipe_process.encoded(prepared.spec),'execution_spec')
            for item in prepared.spec['captured_files']:
                name=str(Path(item['path']).relative_to(prepared.stage))
                raw=recipe_process.read_regular(item['path'],64*1024*1024)
                if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                    _fail('Prepared native source or job changed before acknowledgement.','stale')
                self._retain(document,name,raw,'execution_spec' if name=='native-job-template.json' else 'execution_source')
            self._publish(document,'prepared')
            if self.execution.custody is None:_fail('Native launch requires its original physical custody journal.','unavailable')
            with self.db.lock,self.execution._journal_guard():
                self._dispatch_authorized(phase_id);self.session.check()
                if not self.execution.custody.has_pending:self.execution.custody.acknowledge(self.session.snapshot)
                self.execution.custody.native_prepared(document)
                self.execution.custody.native_launch_intent(phase_id)
            self._dispatch_authorized(phase_id)
            # Once the foundation launch call is entered, failure may mean a
            # spawned helper whose identity ACK was lost. Never infer no launch
            # from an exception, absent Handle, or a saved PID scan.
            handle=prepared.launch(prepared.stage/'custody',
                _before_spawn=lambda:self._never_launched.discard(phase_id))
            self._handles[phase_id]=handle
            with self.execution._journal_guard():
                helper=recipe_process.identity(handle.process.pid)
                self.execution.custody.native_launched(phase_id,helper)
            until=time.monotonic()+recipe_process.preparation_seconds(prepared.spec)+2
            terminal=False
            while not terminal:
                for event in handle.poll():
                    if event['type']=='ready':
                        self._publish(document,'ready',helper=handle.ready)
                        try:self._dispatch_authorized(phase_id)
                        except WorkbenchError:
                            handle.cancel('cancelled')
                            until=time.monotonic()+recipe_process.CLEANUP_SECONDS+PARENT_DRAIN_ALLOWANCE
                            continue
                        self._publish(document,'go_intent',helper=handle.ready)
                        # Recheck actual authority after both durable ACKs. A
                        # saved GO intent is never permission to retry this send.
                        with self.db.lock:
                            self.session.check();self._dispatch_authorized(phase_id)
                            if not self.execution.custody.has_pending:_fail('Native local custody disappeared.','unknown')
                            prepared.check_current_runtime()
                            handle.go(handle.ready)
                        until=(time.monotonic()+prepared.spec['wall_seconds']
                               +recipe_process.verification_seconds(prepared.spec)+recipe_process.CLEANUP_SECONDS+5)
                    elif event['type']=='terminal':terminal=True
                    elif event['type']=='lost':_fail('Native custodian control closed without its measured receipt.','unknown')
                if run_id is not None:
                    with self.db.lock:
                        current=self.execution.runs._load(run_id)
                        if current['state']=='cancelling' or self.execution.runs._stop.is_set():handle.cancel('cancelled')
                if time.monotonic()>until:_fail('Native phase exceeded its bounded custody deadline.','unknown')
                if not terminal:time.sleep(.02)
            evidence=prepared.evidence(handle)
            self._retain_outputs(document)
            for name,raw in (('stdout.log',evidence['stdout']),('stderr.log',evidence['stderr']),
                             ('receipt.json',recipe_process.encoded(evidence['receipt']))):
                self._retain(document,name,raw,'custody_proof' if name=='receipt.json' else 'measured_stream')
            for name,key in (('effective-job.json','effective_job'),('native-parent-observation.json','parent_observation')):
                if evidence[key] is not None:self._retain(document,name,evidence[key],'measured_job')
            receipt_sha=hashlib.sha256(recipe_process.encoded(evidence['receipt'])).hexdigest()
            state='completed' if evidence['receipt']['outcome']=='completed' else 'failed'
            self._publish(document,state,helper=handle.ready,receipt_sha256=receipt_sha)
            if run_id is None:
                with self.execution._journal_guard():self.execution.custody.native_confirmed(phase_id)
            return dict(document=document,evidence=evidence,prepared=prepared)
        except BaseException as error:
            # An unacknowledged phase cannot send GO or publish a successful
            # terminal fact. Close only this process's actual control channel.
            if handle is not None:
                try:handle.close_control()
                except (OSError,recipe_process.ProcessError):pass
            if phase_id not in self._never_launched:
                retained=next((record['document'] for record in self.session.snapshot['records']
                    if record['family']==FAMILY and record['id']==self.session.project_id+'.'+phase_id),None)
                acknowledged=(self.session.available and retained is not None
                    and retained['events'][-1]['state'] in ('completed','failed')
                    and retained['events'][-1]['receipt_sha256'] is not None)
                if not acknowledged:
                    already_fenced=not self.session.available
                    self.session.available=False
                    if self.execution._runs is not None:self.execution._runs._fence_coordinator()
                    if not already_fenced:
                        raise WorkbenchError('Native spawn outcome is uncertain; reconcile exact original custody before further dispatch.',
                                             'outcome_unknown',409) from error
            raise
        finally:
            self._active.discard(phase_id)
            if self._foreground_phase==phase_id:self._foreground_phase=None
            if handle is not None and handle.process.poll() is not None and handle.terminal:
                self._handles.pop(phase_id,None)
