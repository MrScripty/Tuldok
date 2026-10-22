"""Current Study execution composed with exact inert project accounting.

Only authoring metadata is reconstructed. Historical reservations and Runs stay
in canonical history; they contribute charges but never become worker, grant,
admission, replay, or cancellation rows in this physical runtime.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import time
from types import SimpleNamespace

from experiments import (Experiments, budget, request_key, validate_retained_reservation)
from model_definitions import natural, text
from pipeline import closed, identifier, digest
from project_history import (FAMILY_FORMATS, _audit, _sha, envelope,
    decode_records as history_records)
from project_material import ProjectMaterial
from project_session import operation_records
from workbench import WorkbenchError, encode, timestamp

PREPARATIONS={'study_execution.prepare_package':'studies.prepare_package',
              'study_execution.prepare_verifier':'studies.prepare_verifier'}
INTENTS={operation+'_intent':native for operation,native in PREPARATIONS.items()}
ABANDON='study_execution.abandon_preparation'
OPERATIONS=frozenset(('study_execution.admit','study_execution.stop','study_execution.approve',ABANDON,*PREPARATIONS,*INTENTS))
GRANT_FIELDS=('id','catalog_id','approver_actor_id','approver_credential_id','consumer_actor_id',
              'material_sha256','created_at','expires_at','revoked_at')
RESERVATION_FIELDS=('id','study_id','admission_epoch','request_key','actor_id','trial_id','parent_run_id',
    'run_id','request_sha256','material_sha256','envelope','state','settled')


def _invalid(message,code='invalid'):
    raise WorkbenchError(message,code,409)


def _facts(records):
    view=SimpleNamespace(snapshot={'records':records},check=lambda:None)
    return history_records(records,materials=ProjectMaterial(view))


def _intent_key(operation,key):
    return 'candidate-'+digest(dict(key=key,operation=operation))+'-intent'


def _preparation_reference(records,study_id,key):
    receipts=operation_records(records)
    matches=[(operation,receipts[_intent_key(operation,key)]) for operation in PREPARATIONS
        if _intent_key(operation,key) in receipts]
    if len(matches)!=1:_invalid('Preparation requires one exact retained intent.','unavailable')
    operation,receipt=matches[0]
    if receipt['operation']!=operation+'_intent' or receipt['result']['study_id']!=study_id:
        _invalid('Preparation intent belongs to another operation or Study.','conflict')
    return operation,receipt['result'],receipts.get(key)


def _validate_abandon(result,records):
    closed(result,('format','origin_catalog_id','study_id','preparation_key','preparation_operation',
        'input_sha256','candidate','actor_id','reason','observed_checkpoint','occurred_at','state'))
    if result['format']!='project_candidate_preparation_abandon_v1' or result['state']!='abandoned':
        _invalid('Unsupported candidate preparation abandonment.','unsupported')
    for field in ('origin_catalog_id','study_id','actor_id'):identifier(result[field])
    request_key(result['preparation_key']);text(result['reason'],'Abandonment reason',1000)
    for field in ('input_sha256','observed_checkpoint'):_sha(result[field])
    if result['preparation_operation'] not in PREPARATIONS:_invalid('Unknown preparation operation.')
    from model_definitions import reference
    reference(result['candidate'],'candidate',result['origin_catalog_id'])
    if datetime.fromisoformat(result['occurred_at']).utcoffset() is None:_invalid('Abandonment time requires an offset.')
    if records is not None:
        operation,intent,complete=_preparation_reference(records,result['study_id'],result['preparation_key'])
        if (operation!=result['preparation_operation'] or intent['origin_catalog_id']!=result['origin_catalog_id']
                or intent['candidate']!=result['candidate'] or intent['request_sha256']!=result['input_sha256']):
            _invalid('Abandonment differs from its exact retained preparation intent.')
        if complete is not None:_invalid('Completed scientific preparation cannot be abandoned.')
    return True


def _validate_preparation(operation,result,records):
    from candidate_packages import NAME,decode_preparation_receipt
    from experiments import validate_retained_trial
    from model_definitions import reference
    intent=operation in INTENTS;native=INTENTS[operation] if intent else PREPARATIONS[operation]
    if intent:
        fields=('format','origin_catalog_id','study_id','study_revision','candidate','actor_id',
                'request_sha256','root','directory','runtime_snapshot_sha256')
        if native=='studies.prepare_verifier':fields+=('package_run_id','package_sha256')
        closed(result,fields)
        if result['format']!='project_candidate_preparation_intent_v1':_invalid('Unsupported candidate preparation intent.','unsupported')
        for field in ('origin_catalog_id','study_id','actor_id'):identifier(result[field])
        natural(result['study_revision'],'Study revision',1)
        for field in ('request_sha256','runtime_snapshot_sha256'):_sha(result[field])
        reference(result['candidate'],'candidate',result['origin_catalog_id'])
        for field in ('root','directory'):
            if type(result[field]) is not str or NAME.fullmatch(result[field]) is None:_invalid('Invalid preparation location.')
        if native=='studies.prepare_verifier':identifier(result['package_run_id']);_sha(result['package_sha256'])
    else:
        origin=result['trial']['material']['catalog_id']
        decode_preparation_receipt(native,result,catalog_id=origin,
            validate_trial=lambda value:validate_retained_trial(value,catalog_id=origin))
    if records is None:return True
    facts=_facts(records)
    if intent:
        origin=result['origin_catalog_id'];candidate=facts.candidates[(origin,result['candidate']['id'])]['candidate']
        if candidate['study_id']!=result['study_id'] or digest(candidate)!=result['candidate']['sha256']:
            _invalid('Preparation intent differs from its immutable candidate.')
        study=facts.studies[(origin,result['study_id'])]
        if not any(value['revision']==result['study_revision'] for value in study['revisions']):
            _invalid('Preparation intent lacks its exact Study revision.')
        if native=='studies.prepare_verifier':
            run=facts.runs[(origin,result['package_run_id'])]['run']
            if not any(item['name']=='package.zip' and item['sha256']==result['package_sha256'] for item in run['artifacts']):
                _invalid('Verifier intent differs from the retained package bytes.')
    else:
        from project_history import validate_operation_result as validate_history_result
        validate_history_result(native,result,records)
        trial=result['trial'];origin=trial['material']['catalog_id']
        candidate=facts.candidates[(origin,result['candidate_id'])]['candidate']
        if candidate['study_id']!=trial['study_id']:_invalid('Preparation candidate belongs to another Study.')
        materials=ProjectMaterial(SimpleNamespace(snapshot={'records':records},check=lambda:None))
        composition=materials.recipe(trial['material'])['material']
        if (composition['model']!=result['model'] or composition['recipe_id']!=result['graph']['id']
                or composition['recipe_revision']!=result['graph']['revision']):
            _invalid('Preparation model or graph differs from its retained composition.')
        descriptor=materials.runtime(composition['runtime'])['descriptor']
        if descriptor is None or descriptor['manifest_sha256']!=result['runtime_snapshot_sha256']:
            _invalid('Preparation runtime differs from its retained composition.')
    return True


def validate_operation_result(operation,result,records=None):
    """Closed scientific acknowledgements; none grants current authority."""
    if operation not in OPERATIONS:return False
    try:
        if operation==ABANDON:return _validate_abandon(result,records)
        if operation in PREPARATIONS or operation in INTENTS:
            return _validate_preparation(operation,result,records)
        if operation=='study_execution.admit':
            closed(result,('format','origin_catalog_id','study_id','trial_id','run_id','reservation'))
            if result['format']!='project_study_admission_v1':_invalid('Unsupported Study admission receipt.','unsupported')
            for key in ('origin_catalog_id','study_id','trial_id','run_id'):identifier(result[key])
            reservation=result['reservation'];closed(reservation,RESERVATION_FIELDS)
            for key in ('id','study_id','actor_id','trial_id','run_id'):identifier(reservation[key])
            if reservation['parent_run_id'] is not None:identifier(reservation['parent_run_id'])
            natural(reservation['admission_epoch'],'Admission epoch');request_key(reservation['request_key'])
            for key in ('request_sha256','material_sha256'):_sha(reservation[key])
            budget(reservation['envelope'])
            if reservation['state'] not in ('reserved','running','settled','unknown'):_invalid('Invalid reservation observation.')
            if reservation['settled'] is not None:budget(reservation['settled'])
            if any(result[key]!=reservation[key] for key in ('study_id','trial_id','run_id')):
                _invalid('Study admission references differ from their reservation.')
        elif operation=='study_execution.stop':
            closed(result,('format','origin_catalog_id','study_id','receipt','study_revision','state','open'))
            if result['format']!='project_study_stop_v1':_invalid('Unsupported Study stop receipt.','unsupported')
            identifier(result['origin_catalog_id']);identifier(result['study_id']);natural(result['study_revision'],'Study revision',1)
            receipt=result['receipt'];closed(receipt,('study_id','stop_receipt_id','admission_epoch','run_ids'))
            identifier(receipt['study_id']);identifier(receipt['stop_receipt_id']);natural(receipt['admission_epoch'],'Stop epoch')
            if (receipt['study_id']!=result['study_id'] or result['open'] is not False
                    or result['state'] not in ('stopping','stopped','unknown')
                    or type(receipt['run_ids']) is not list or len(receipt['run_ids'])>10000):_invalid('Invalid Study epoch closure.')
            for identity in receipt['run_ids']:identifier(identity)
            if len(set(receipt['run_ids']))!=len(receipt['run_ids']):_invalid('Duplicate stopped Run identity.')
        else:
            closed(result,('format','origin_catalog_id','study_id','trial_id','approval_id','material_sha256',
                'consumer_actor_id','approver_actor_id','created_at','expires_at'))
            if result['format']!='project_study_approval_v1':_invalid('Unsupported Study approval observation.','unsupported')
            identifier(result['study_id']);identifier(result['trial_id'])
            from project_execution import validate_operation_result as validate_execution_result
            base={key:result[key] for key in ('origin_catalog_id','approval_id','material_sha256',
                'consumer_actor_id','approver_actor_id','created_at','expires_at')}
            validate_execution_result('runs.approve_external',dict(format='project_execution_approval_v1',**base))
        if records is None:return True
        facts=_facts(records)
        if operation=='study_execution.admit':
            origin=result['origin_catalog_id'];reservation=result['reservation']
            saved=facts.reservations.get((origin,result['run_id']))
            if saved is None or any(saved[key]!=reservation[key] for key in RESERVATION_FIELDS if key not in ('state','settled')):
                _invalid('Admission receipt has no exact canonical reservation.')
            trial=facts.trials[(origin,result['trial_id'])]['trial'];run=facts.runs[(origin,result['run_id'])]['run']
            view=SimpleNamespace(snapshot={'records':records},check=lambda:None)
            validate_retained_reservation(reservation,trial=trial,
                composition=ProjectMaterial(view).recipe(trial['material']),run=run)
        elif operation=='study_execution.stop':
            doc=facts.studies[(result['origin_catalog_id'],result['study_id'])];receipt=result['receipt']
            matches=[value for value in doc['revisions'] if value['revision']==result['study_revision']]
            if (len(matches)!=1 or matches[0]['stop_receipt_id']!=receipt['stop_receipt_id']
                    or matches[0]['admission_epoch']!=receipt['admission_epoch']
                    or matches[0]['state']!=result['state'] or matches[0]['open']!=result['open']):
                _invalid('Stop receipt has no exact retained epoch closure.')
            if not set(receipt['run_ids'])<={value['run_id'] for value in doc['reservations']}:
                _invalid('Stop receipt targets an unrelated Run.')
        else:
            origin=result['origin_catalog_id'];doc=facts.studies[(origin,result['study_id'])]
            trial=facts.trials[(origin,result['trial_id'])]['trial']
            if trial['study_id']!=result['study_id'] or trial['material']['sha256']!=result['material_sha256']:
                _invalid('Approval observation differs from its exact retained Trial.')
            expected={key:result[key] for key in ('trial_id','material_sha256','approval_id','consumer_actor_id','created_at','expires_at')}
            matches=[fact for fact in doc['audit'] if fact['action']=='studies.approve'
                and fact['target']==result['study_id'] and fact['actor_id']==result['approver_actor_id']
                and fact['details']==expected]
            if len(matches)!=1:_invalid('Approval receipt has no exact historical Study approval observation.')
        return True
    except WorkbenchError:raise
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        _invalid('Malformed current Study operation receipt.')


class _LocalRunsReference:
    """Refer only to an explicitly activated local owner; never construct one."""
    def __init__(self,execution):self.execution=execution
    def __getattr__(self,name):return getattr(self.execution.runs,name)


class _PreparationRuns:
    """Scientific inputs only; this object cannot allocate or recover Runs."""
    def __init__(self,adapter):self.adapter=adapter;self.access=adapter.session.access
    def _load(self,run_id):
        history=self.adapter.history;history._authorize('runs.get',run_id)
        facts=history._facts();doc=history._record(facts.runs,run_id,self.adapter.origin)
        history._transitive(facts,doc);history._disclose(doc['run'],'unknown')
        return copy.deepcopy(doc['run'])
    @staticmethod
    def _external(run):return run.get('execution_kind')=='external_recipe'
    @staticmethod
    def _extension(run):
        from recipe_contract import is_evidence
        return run.get('execution_kind')=='external_recipe' and is_evidence(run['material']['recipe'])
    def artifact(self,run_id,name):
        raw=self.adapter.history.artifact(run_id,name,origin_catalog_id=self.adapter.origin,
            maximum_bytes=512*1024**2)
        return raw,'application/octet-stream'
    def model_evidence(self,run_id,selectors,*,contract_version=2):
        if contract_version!=2:_invalid('Candidate preparation requires model evidence version 2.','unsupported')
        return self.adapter.history.evidence(run_id,selectors,origin_catalog_id=self.adapter.origin)
    def capture_artifact(self,*args,**kwargs):return self.adapter.history.capture_artifact(*args,**kwargs)


class _PreparationProjects:
    def __init__(self,adapter,phase):
        self.adapter,self.phase=adapter,phase;self.source=adapter.projection.sources
        self.access=adapter.access
    def __getattr__(self,name):return getattr(self.source,name)
    def open(self,body):
        return self.adapter.projection.source_adapter.register(body,
            self.adapter.session.snapshot['checkpoint'],self.phase+'-source')


class _PreparationModels:
    def __init__(self,adapter,phase):self.adapter,self.phase=adapter,phase
    def material(self,ref,*,verify=False):return self.adapter.materials.model(ref,verify=verify)
    def read_blob(self,ref,item):return self.adapter.materials.blob(ref,item)
    def _read_blob(self,ref,item,maximum=40*1024**2):return self.adapter.materials.blob(ref,item,maximum)
    def create(self,body):
        adapter=self.adapter
        return adapter.materials.mutate_definition('model_definition','models.create',None,body,
            adapter.session.snapshot['checkpoint'],self.phase+'-model',lambda:adapter.projection.models.create(body))
    def publish(self,identity,body):
        adapter=self.adapter
        return adapter.materials.publish_model(adapter.projection.models,identity,body,
            adapter.session.snapshot['checkpoint'],self.phase+'-publish')


class _PreparationPipelines:
    def __init__(self,adapter,phase,context):
        from pipeline import Pipelines
        self.adapter,self.phase=adapter,phase;self.owner=Pipelines(context)
        self.material_path=self.owner.material_path
    def get(self,*args,**kwargs):return self.owner.get(*args,**kwargs)
    def recipe_material(self,ref,*,verify=False):return self.adapter.materials.recipe(ref,verify=verify)
    def create_external(self,body):
        adapter=self.adapter
        return adapter.materials.mutate_definition('pipeline_graph','graphs.create_external',None,body,
            adapter.session.snapshot['checkpoint'],self.phase+'-graph',lambda:self.owner.create_external(body))
    def prepare_external_material(self,*args,**kwargs):return self.owner.prepare_external_material(*args,**kwargs)
    def _retain_material(self,prepared):
        adapter=self.adapter;value=self.owner._retain_material(prepared)
        record=adapter.materials.capture_recipe_material(value,self.owner.material_path)
        adapter._package_records.extend([record,*adapter.materials.declarations(record),
            *adapter.materials.capture_recipe_dependencies(record,adapter.session.snapshot['records'])])
        return value


class ProjectStudyExecution:
    def __init__(self,projection,execution):
        self.projection,self.execution=projection,execution
        self.session,self.db,self.history=projection.session,projection.db,projection.history
        self.materials=projection.materials;self.access=execution.runtime_access
        self.origin=self.session.snapshot['project_id']
        self._dirty=set();self._revisions={};self._epochs={};self._pending_epochs={}
        self._package_records=[]
        self.context=copy.copy(projection.context)
        self.context.access,self.context.runs=self.access,_LocalRunsReference(execution)
        self.context.project_study_execution=self
        self.context.project_execution=execution
        self.studies=Experiments(self.context)
        execution.study_execution=self
        projection.study_execution=self
        self.history.study_execution=self

    def _canonical(self,records=None):
        records=self.session.snapshot['records'] if records is None else records
        return history_records(records,materials=self.materials)

    def restore_authoring(self,records=None):
        """Reconstruct intent only, under the current project guard."""
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.session.check();facts=self._canonical(records)
            with self.db.transaction():
                for (origin,identity),doc in sorted(facts.studies.items()):
                    if origin!=self.origin:continue
                    for item in doc['policies']:
                        ref=item['ref']
                        self.db.execute('INSERT INTO model_selection_policies VALUES(%s,%s,%s,%s) ON CONFLICT(id,revision) DO UPDATE SET sha256=EXCLUDED.sha256,document=EXCLUDED.document',
                            (ref['id'],ref['revision'],ref['sha256'],encode(item['policy'])))
                    value=doc['study']
                    self.db.execute('INSERT INTO model_studies VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET revision=EXCLUDED.revision,admission_epoch=EXCLUDED.admission_epoch,document=EXCLUDED.document',
                        (identity,value['revision'],value['admission_epoch'],encode(value)))
                    for member in doc['memberships']:
                        self.db.execute('INSERT INTO model_study_memberships VALUES(%s,%s,%s) ON CONFLICT(study_id,revision) DO UPDATE SET document=EXCLUDED.document',
                            (identity,member['revision'],encode({'trial_ids':member['trial_ids']})))
                for (origin,identity),doc in sorted(facts.trials.items()):
                    if origin!=self.origin:continue
                    value=doc['trial']
                    self.db.execute('INSERT INTO model_trials VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET document=EXCLUDED.document',
                        (identity,value['study_id'],value['material']['sha256'],value['replicate'],encode(value)))
                for (origin,identity),doc in sorted(facts.trials.items()):
                    if origin!=self.origin or doc['lineage'] is None:continue
                    value=doc['lineage'];intent=value['intent']
                    # Native current authoring only supports same-project SQL
                    # parent FKs; foreign history remains in the canonical view.
                    if any(ref is not None and ref['catalog_id']!=self.origin for ref in (intent['parent'],intent['baseline'])):continue
                    self.db.execute('INSERT INTO model_trial_lineage VALUES(%s,%s,%s,%s) ON CONFLICT(trial_id) DO UPDATE SET document=EXCLUDED.document',
                        (identity,(intent['parent'] or {}).get('trial_id'),(intent['baseline'] or {}).get('trial_id'),encode(value)))
        return None

    refresh_authoring=restore_authoring

    def local_run_ids(self):
        return {row[0] for row in self.db.execute('SELECT run_id FROM model_attempt_reservations')}

    def historical_reservations(self,study_id):
        doc=self._canonical().studies.get((self.origin,study_id))
        if doc is None:return []
        local=self.local_run_ids()
        return [copy.deepcopy(value) for value in doc['reservations'] if value['run_id'] not in local]

    def reject_historical_request(self,study_id,actor,key,sha):
        for value in self.historical_reservations(study_id):
            if value['request_key']==key:
                _invalid('This request identifies an inert historical attempt; use a fresh key for new execution.','conflict')

    def run_fact(self,run_id):
        identifier(run_id)
        if self.db.execute('SELECT id FROM workspace_runs WHERE id=%s',(run_id,)).fetchone() is not None:
            return copy.deepcopy(self.execution.runs._load(run_id))
        value=self._canonical().runs.get((self.origin,run_id))
        if value is None:_invalid('Retained Run observation is unavailable.','not_found')
        return copy.deepcopy(value['run'])

    def lineage_fact(self,trial_id):
        value=self._canonical().trials.get((self.origin,trial_id))
        return copy.deepcopy(value['lineage']) if value is not None else None

    def epoch_current(self,study):
        return study['open'] and self._epochs.get(study['id'])==study['admission_epoch']

    def require_current_epoch(self,study):
        if not self.epoch_current(study):
            _invalid('Explicitly continue this Study in the current runtime before admission.','unavailable')

    def external_blocked(self):
        owner=getattr(self.execution,'_runs',None)
        return bool(owner is not None and owner._external_blocked)

    def mark_study(self,study_id):
        identifier(study_id)
        if not self.db.in_transaction:raise RuntimeError('Study publication requires its owning SQL transaction.')
        value=self.studies._study(study_id)
        self._dirty.add(study_id)
        versions=self._revisions.setdefault(study_id,{})
        prior=versions.get(value['revision'])
        if prior is not None and prior!=value:_invalid('A Study revision changed inside its publication transaction.')
        versions[value['revision']]=copy.deepcopy(value)

    def _operation_study(self,operation,result):
        if operation in ('studies.create','studies.save','studies.continue'):return result['id']
        if operation in ('studies.prepare_trial','studies.prepare_branch'):return result['study_id']
        if operation in ('studies.branch_trial','studies.stop'):return result['study_id']
        if operation=='studies.select_candidate':return result['candidate']['study_id']
        if operation in ('studies.prepare_package','studies.prepare_verifier'):return result['trial']['study_id']
        if operation=='studies.record_lineage':return self.studies.trial(result['trial']['trial_id'])['study_id']
        _invalid('Unclassified native Study operation result.','unsupported')

    def mark_operation(self,operation,result):
        self.mark_study(self._operation_study(operation,result))

    def settle_runs(self,run_ids):
        if not run_ids:return
        if not self.db.in_transaction:raise RuntimeError('Reservation settlement must share Run publication.')
        studies={row['study_id'] for row in self.db.execute('SELECT study_id,run_id FROM model_attempt_reservations') if row['run_id'] in run_ids}
        if studies:
            with self.access._reconcile():
                for identity in sorted(studies):self.studies._reconcile_local(identity)

    @staticmethod
    def _audit_fact(row):
        return dict(actor_id=row['actor_id'],action=row['action'],target=json.loads(row['target_json']),
            details=json.loads(row['details_json']),result=row['result'],
            occurred_at=datetime.fromtimestamp(row['created_at'],timezone.utc).isoformat())

    def capture_dirty(self,before_records):
        # Execution has already qualified this observation against current
        # local custody. These finite metadata reads must not ask the child
        # continuation to acquire unrelated Study/policy capabilities.
        with self.access._reconcile():
            return self._capture_dirty(before_records)

    def _capture_dirty(self,before_records):
        if not self._dirty:return copy.deepcopy(self._package_records)
        facts=self._canonical(before_records);records=copy.deepcopy(self._package_records)
        audit_rows=list(self.db.execute('SELECT actor_id,action,target_json,details_json,result,created_at FROM access_audit ORDER BY created_at,id'))
        operation_rows=list(self.db.execute('SELECT actor_id,operation_id,request_key,request_sha256,document FROM model_operation_receipts ORDER BY actor_id,operation_id,request_key'))
        for study_id in sorted(self._dirty):
            old=facts.studies.get((self.origin,study_id));value=self.studies._study(study_id)
            doc=copy.deepcopy(old) if old is not None else dict(format=FAMILY_FORMATS['study_history'],origin_catalog_id=self.origin,
                study=value,memberships=[],policies=[],reservations=[],operations=[],revisions=[],audit=[],revision_history_complete=True)
            revisions={item['revision']:item for item in doc['revisions']}
            for revision,item in self._revisions.get(study_id,{}).items():
                if revision in revisions and revisions[revision]!=item:_invalid('Published Study revision cannot change.')
                revisions[revision]=copy.deepcopy(item)
            if value['revision'] in revisions and revisions[value['revision']]!=value:_invalid('Current Study differs from captured revision.')
            revisions[value['revision']]=copy.deepcopy(value)
            doc['study']=copy.deepcopy(value);doc['revisions']=[revisions[key] for key in sorted(revisions)]
            if old is None and min(revisions)!=1:doc['revision_history_complete']=False
            doc['memberships']=[dict(revision=row['revision'],trial_ids=json.loads(row['document'])['trial_ids'])
                for row in self.db.execute('SELECT revision,document FROM model_study_memberships WHERE study_id=%s ORDER BY revision',(study_id,))]
            policies={item['ref']['sha256']:item for item in doc['policies']}
            ref=value['policy'];policies[ref['sha256']]=dict(ref=copy.deepcopy(ref),policy=self.studies.policy(ref))
            doc['policies']=[policies[key] for key in sorted(policies)]
            reservations={item['run_id']:item for item in doc['reservations']}
            reservations.update((item['run_id'],item) for item in self.studies._local_reservations(study_id))
            doc['reservations']=sorted(reservations.values(),key=lambda item:item['id'])
            operations={(item['actor_id'],item['operation_id'],item['request_key']):item for item in doc['operations']}
            for row in operation_rows:
                result=json.loads(row['document'])
                if self._operation_study(row['operation_id'],result)!=study_id:continue
                item=dict(actor_id=row['actor_id'],operation_id=row['operation_id'],request_key=row['request_key'],
                    request_sha256=row['request_sha256'],result=result)
                key=item['actor_id'],item['operation_id'],item['request_key']
                if key in operations and operations[key]!=item:_invalid('A retained native operation fact changed.')
                operations[key]=item
            doc['operations']=[operations[key] for key in sorted(operations)]
            targets={study_id,*value['trial_ids'],*(item['run_id'] for item in doc['reservations'])}
            candidates=[]
            for row in self.db.execute('SELECT id,document FROM model_candidates WHERE study_id=%s',(study_id,)):
                candidate=json.loads(row['document']);targets.add(candidate['id'])
                candidates.append(envelope('candidate_history',self.origin,candidate['id'],dict(
                    format=FAMILY_FORMATS['candidate_history'],origin_catalog_id=self.origin,candidate=candidate)))
            for row in audit_rows:
                if not (row['action'].startswith('studies.') or row['action'].startswith('runs.')):continue
                fact=self._audit_fact(row)
                if fact['target'] not in targets:continue
                _audit([fact])
                if fact not in doc['audit']:doc['audit'].append(fact)
            records.append(envelope('study_history',self.origin,study_id,doc));records.extend(candidates)
            for trial_id in value['trial_ids']:
                trial=self.studies.trial(trial_id)
                row=self.db.execute('SELECT document FROM model_trial_lineage WHERE trial_id=%s',(trial_id,)).fetchone()
                prior=facts.trials.get((self.origin,trial_id));lineage=json.loads(row[0]) if row is not None else (prior['lineage'] if prior else None)
                records.append(envelope('trial_history',self.origin,trial_id,dict(format=FAMILY_FORMATS['trial_history'],
                    origin_catalog_id=self.origin,trial=trial,lineage=lineage)))
        return records

    def abandon_pending(self):
        """Discard only unpublished projection bookkeeping during guarded repair.

        This cannot activate an imported epoch or recreate any execution right.
        The root recovery owner separately qualifies custody and exact selection.
        """
        self._dirty.clear();self._revisions.clear();self._pending_epochs.clear()
        self._package_records.clear()

    def outcome(self,outcome):
        if outcome not in ('committed','rolled_back','unknown'):raise ValueError('Unsupported Study SQL outcome.')
        if outcome=='unknown':return
        if outcome=='committed':self._epochs.update(self._pending_epochs)
        self._dirty.clear();self._revisions.clear();self._pending_epochs.clear()
        self._package_records.clear()

    def _mutate(self,operation,study_id,body,expected_checkpoint,key,invoke,scope):
        return self.execution.mutate(operation,study_id,body,expected_checkpoint,key,invoke,
            lambda result,before:dict(records=[],result=result),scope=scope)

    def continue_study(self,study_id,body,expected_checkpoint,key):
        closed(body,('revision','admission_epoch'));request_key(key)
        self.access.require('execute','studies.continue',study_id,owner_only=True)
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.refresh_authoring()
            prior=operation_records(self.session.snapshot['records']).get(key)
            if prior is not None and not self.epoch_current(self.studies._study(study_id)):
                _invalid('A historical Continue receipt cannot activate this runtime; use a fresh key.','unavailable')
            def invoke():
                value=self.studies.continue_study(study_id,dict(body,request_key=key))
                self._pending_epochs[study_id]=value['admission_epoch']
                return value
            return self._mutate('studies.continue',study_id,body,expected_checkpoint,key,invoke,'execute')

    def _current_grant(self,value,approver):
        row=self.db.execute('SELECT * FROM access_execution_grants WHERE id=%s',(value['approval_id'],)).fetchone()
        if row is None:_invalid('This approval is historical; approve explicitly with a fresh key.','unavailable')
        grant=dict(row);closed(grant,GRANT_FIELDS)
        expected=dict(origin_catalog_id=grant['catalog_id'],approval_id=grant['id'],
            **{key:grant[key] for key in ('material_sha256','consumer_actor_id','approver_actor_id','created_at','expires_at')})
        if (any(value[key]!=item for key,item in expected.items()) or grant['approver_actor_id']!=approver
                or grant['revoked_at'] is not None or grant['expires_at']<=int(time.time())):
            _invalid('An exact current local execution approval is unavailable.','unavailable')
        return grant

    def _materialize_trial(self,study_id,trial_id,expected_sha256=None):
        """Explicit preparation reconstructs only the current private caches."""
        study=self.studies._study(study_id);trial=self.studies.trial(trial_id)
        if trial['study_id']!=study_id or trial_id not in study['trial_ids']:
            _invalid('Prepare an exact member Trial.')
        if expected_sha256 is not None and trial['material']['sha256']!=expected_sha256:
            _invalid('Composed material differs. Review the exact Trial.','stale')
        value=self.materials.recipe(trial['material']);material=value['material']
        snapshot=json.loads(self.materials.blob(trial['material'],material['recipe_document'],2*1024**2))
        if snapshot['format']!='builtin_recipe_snapshot_v1':
            # Current permission is independent from the original input proof.
            # Verify every protected producer before rebuilding captured bytes.
            for item in snapshot['preflight']['material']['inputs'].values():
                if item.get('kind')=='run_artifact':
                    source=item['source']
                    self.history.capture_artifact(source['run_id'],source['artifact_name'],source['measured_sha256'],
                        origin_catalog_id=source['catalog_id'])
        self.materials.materialize_projection(material['model'],self.projection.models.path)
        self.materials.materialize_projection(trial['material'],self.projection.pipelines.material_path)
        return trial

    def approve(self,study_id,body,expected_checkpoint,key):
        closed(body,('trial_id','expected_material_sha256','consumer_actor_id'),('ttl_seconds',));request_key(key)
        current=self.access.require('approve-execution','studies.approve',study_id,owner_only=True)
        effective=dict(body,approver_actor_id=current.actor_id)
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.refresh_authoring();prior=operation_records(self.session.snapshot['records']).get(key)
            if prior is not None:
                if prior['operation']!='study_execution.approve':_invalid('Request key has another operation.','conflict')
                validate_operation_result(prior['operation'],prior['result'],self.session.snapshot['records'])
                self._current_grant(prior['result'],current.actor_id)
            else:
                if expected_checkpoint!=self.session.snapshot['checkpoint']:_invalid('Expected project checkpoint changed.','stale_project')
                self._materialize_trial(study_id,body['trial_id'],body['expected_material_sha256'])
            def invoke():
                grant=self.studies.approve(study_id,body)
                return dict(format='project_study_approval_v1',origin_catalog_id=grant['catalog_id'],
                    study_id=study_id,trial_id=body['trial_id'],approval_id=grant['id'],
                    **{key:grant[key] for key in ('material_sha256','consumer_actor_id','approver_actor_id','created_at','expires_at')})
            value=self._mutate('study_execution.approve',study_id,effective,expected_checkpoint,key,invoke,'approve-execution')
            grant=self._current_grant(value,current.actor_id)
            return dict(format='project_current_execution_approval_v1',current_local=True,grant=grant)

    def admit(self,study_id,body,expected_checkpoint,key):
        closed(body,('revision','admission_epoch','trial_id'),('approval_id','parent_run_id'));request_key(key)
        authority=self.access.require_external_submission()
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.session.check();self.refresh_authoring()
            prior=operation_records(self.session.snapshot['records']).get(key)
            if prior is not None:
                result=prior['result']
                if (prior['operation']!='study_execution.admit' or self.db.execute(
                    'SELECT run_id FROM model_attempt_reservations WHERE run_id=%s',(result.get('run_id'),)).fetchone() is None):
                    _invalid('A historical admission receipt cannot create a current local attempt.','unavailable')
            else:
                if expected_checkpoint!=self.session.snapshot['checkpoint']:_invalid('Expected project checkpoint changed.','stale_project')
                self.require_current_epoch(self.studies._study(study_id))
                self.reject_historical_request(study_id,authority.actor_id,key,None)
                self._materialize_trial(study_id,body['trial_id'])
            def invoke():
                self.execution._local_owner()
                result=self.studies.admit(study_id,dict(body,request_key=key));reservation=result['reservation']
                return dict(format='project_study_admission_v1',origin_catalog_id=self.origin,
                    study_id=study_id,trial_id=reservation['trial_id'],run_id=reservation['run_id'],reservation=reservation)
            # The submission policy above permits an approved agent. The native
            # admission consumes its exact current grant atomically; execute
            # here would incorrectly impose the host's owner-only policy.
            return self._mutate('study_execution.admit',study_id,body,expected_checkpoint,key,invoke,'inspect')

    def stop(self,study_id,body,expected_checkpoint,key):
        closed(body,('revision',));request_key(key)
        self.access.require('cancel','studies.stop',study_id)
        invoked=[]
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.refresh_authoring()
            def invoke():
                receipt=self.studies._close_admission(study_id,dict(body,request_key=key));value=self.studies._study(study_id)
                invoked.extend(receipt['run_ids'])
                return dict(format='project_study_stop_v1',origin_catalog_id=self.origin,study_id=study_id,
                    receipt=receipt,study_revision=value['revision'],state=value['state'],open=value['open'])
            result=self._mutate('study_execution.stop',study_id,body,expected_checkpoint,key,invoke,'cancel')
            # Only acknowledged canonical closure permits this current-runtime
            # cancellation phase. Receipt replay does not repeat effects.
            for run_id in invoked:
                cancel_key='study-stop-'+hashlib.sha256((key+':'+run_id).encode()).hexdigest()
                try:self.execution.cancel_run(run_id,self.session.snapshot['checkpoint'],cancel_key)
                except BaseException as error:
                    error.study_stop_receipt=copy.deepcopy(result)
                    raise
            return result

    def candidate(self,candidate_id):
        value=self.history.candidate(candidate_id,origin_catalog_id=self.origin,verify=True)
        return {key:value[key] for key in ('ref','candidate','run_id','checkpoint')}

    def _pending_preparation(self,study_id,body,expected_checkpoint):
        identifier(study_id);request_key(body['preparation_key']);_sha(expected_checkpoint)
        self.access.require('cancel','studies.reconcile_preparation',study_id,owner_only=True)
        # The acknowledged intent is present even when a later Store/SQL ACK
        # is uncertain. Only the qualified execution guard may recover HEAD.
        snapshot=self.session.snapshot
        if snapshot['checkpoint']!=expected_checkpoint:_invalid('Expected project checkpoint changed.','stale_project')
        operation,intent,complete=_preparation_reference(snapshot['records'],study_id,body['preparation_key'])
        validate_operation_result(operation+'_intent',intent,snapshot['records'])
        if intent['origin_catalog_id']!=self.origin:_invalid('Historical origin cannot settle a current writer.','unavailable')
        if complete is not None and complete['operation']!=operation:_invalid('Preparation key has another operation.','conflict')
        return operation,intent,complete

    def reconcile_preparation(self,study_id,body,expected_checkpoint):
        """Acknowledge a completed publication without replaying its writer."""
        closed(body,('preparation_key',))
        with self.session.access.lock,self.session.lock,self.db.lock:
            operation,intent,complete=self._pending_preparation(study_id,body,expected_checkpoint)
            with self.execution.package_reconciliation(body['preparation_key'],intent['request_sha256'],
                    intent['candidate']['sha256'],expected_checkpoint) as guard:
                operation,current_intent,complete=_preparation_reference(self.session.snapshot['records'],study_id,body['preparation_key'])
                if current_intent!=intent:_invalid('Preparation intent changed during guarded reconciliation.','conflict')
                if complete is None:_invalid('No final preparation exists; explicitly abandon the stopped partial writer.','unavailable')
                if complete['operation']!=operation:_invalid('Preparation key has another operation.','conflict')
                validate_operation_result(operation,complete['result'],self.session.snapshot['records'])
                guard.confirmed()
                return copy.deepcopy(complete['result'])

    def abandon_preparation(self,study_id,body,expected_checkpoint,key):
        """Record a stopped writer decision; preserve every byte and phase fact."""
        closed(body,('preparation_key','reason'));request_key(key);text(body['reason'],'Abandonment reason',1000)
        if key==body['preparation_key']:_invalid('Abandonment requires a separate request key.')
        current=self.access.require('cancel','studies.abandon_preparation',study_id,owner_only=True)
        effective=dict(body,actor_id=current.actor_id)
        with self.session.access.lock,self.session.lock,self.db.lock:
            operation,intent,complete=self._pending_preparation(study_id,body,expected_checkpoint)
            if complete is not None:_invalid('Preparation is complete; reconcile its acknowledgement without abandoning science.','conflict')
            with self.execution.package_reconciliation(body['preparation_key'],intent['request_sha256'],
                    intent['candidate']['sha256'],expected_checkpoint) as guard:
                operation,current_intent,complete=_preparation_reference(self.session.snapshot['records'],study_id,body['preparation_key'])
                if current_intent!=intent:_invalid('Preparation intent changed during guarded reconciliation.','conflict')
                if complete is not None:_invalid('Preparation is complete; reconcile its acknowledgement without abandoning science.','conflict')
                observed_checkpoint=self.session.snapshot['checkpoint']
                def invoke():
                    actor=self.access.require('cancel','studies.abandon_preparation',study_id,owner_only=True)
                    if actor.actor_id!=current.actor_id:_invalid('Abandonment caller changed.','conflict')
                    return dict(format='project_candidate_preparation_abandon_v1',origin_catalog_id=self.origin,
                        study_id=study_id,preparation_key=body['preparation_key'],preparation_operation=operation,
                        input_sha256=intent['request_sha256'],candidate=copy.deepcopy(intent['candidate']),
                        actor_id=actor.actor_id,reason=body['reason'],observed_checkpoint=observed_checkpoint,
                        occurred_at=timestamp(),state='abandoned')
                value=self._mutate(ABANDON,study_id,effective,observed_checkpoint,key,invoke,'cancel')
                guard.confirmed()
                return value

    def _prepare_candidate(self,study_id,body,expected_checkpoint,key,kind):
        from candidate_packages import NAME,_prepare_operation
        from runtime_snapshots import RuntimeSnapshots
        from model_definitions import checked_json
        fields=('revision','candidate_id','root','directory','runtime_snapshot_sha256')
        if kind=='verify':fields+=('package_run_id','package_sha256')
        closed(body,fields);body=checked_json(body);request_key(key);identifier(study_id)
        natural(body['revision'],'Study revision',1);identifier(body['candidate_id']);_sha(body['runtime_snapshot_sha256'])
        for field in ('root','directory'):
            if type(body[field]) is not str or NAME.fullmatch(body[field]) is None:_invalid('Invalid candidate preparation location.')
        if kind=='verify':identifier(body['package_run_id']);_sha(body['package_sha256'])
        operation='study_execution.prepare_package' if kind=='package' else 'study_execution.prepare_verifier'
        native=PREPARATIONS[operation]
        actor=self.access.require('edit',native,study_id,owner_only=True)
        effective=dict(body,actor_id=actor.actor_id)
        input_sha=digest(dict(study_id=study_id,body=effective))
        intent_key=_intent_key(operation,key);phase=intent_key.removesuffix('-intent')
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.session.check()
            prior=operation_records(self.session.snapshot['records']).get(key)
            if prior is not None:
                # Current authority is checked above. Historical completion
                # acknowledges science and cannot repeat filesystem effects.
                return self._mutate(operation,study_id,effective,expected_checkpoint,key,
                    lambda:(_ for _ in ()).throw(RuntimeError('Completed preparation replay invoked effects.')),'edit')
            if expected_checkpoint!=self.session.snapshot['checkpoint']:_invalid('Expected project checkpoint changed.','stale_project')
            receipts=operation_records(self.session.snapshot['records'])
            if any(_intent_key(other,key) in receipts for other in PREPARATIONS if other!=operation):
                _invalid('Preparation key already identifies another preparation operation.','conflict')
            previous_intent=receipts.get(intent_key)
            if previous_intent is not None:
                if previous_intent['result'].get('request_sha256')!=input_sha:
                    _invalid('Candidate preparation key has different inputs or actor.','conflict')
                _invalid('Candidate preparation has an incomplete retained intent; reconcile it before a new explicit attempt.','unavailable')
            self.refresh_authoring();self.studies._expected(self.studies._study(study_id),body)
            candidate=self.candidate(body['candidate_id'])
            if candidate['candidate']['study_id']!=study_id:_invalid('Candidate belongs to another Study.')
            if body['root'] not in self.projection.sources.roots:_invalid('Choose a currently configured source root.','unavailable')
            with self.execution.runtime_inspection():
                snapshot=RuntimeSnapshots(self.db,self.access,self.db.path).get(body['runtime_snapshot_sha256'])
            if snapshot['catalog_id']!=self.origin:_invalid('Register this runtime under the current project.','unavailable')
            runtime_ref=dict(kind='runtime',catalog_id=self.origin,id=digest(snapshot),sha256=digest(snapshot))
            retained=self.materials.runtime(runtime_ref,verify=True)
            if retained['descriptor']!=snapshot:_invalid('Current runtime differs from retained preparation material.','stale')
            intent=dict(format='project_candidate_preparation_intent_v1',origin_catalog_id=self.origin,
                study_id=study_id,study_revision=body['revision'],candidate=copy.deepcopy(candidate['ref']),
                actor_id=actor.actor_id,request_sha256=input_sha,root=body['root'],directory=body['directory'],
                runtime_snapshot_sha256=body['runtime_snapshot_sha256'])
            if kind=='verify':intent.update({field:body[field] for field in ('package_run_id','package_sha256')})
            with self.execution.package_effect(key,input_sha,candidate['ref']['sha256']) as guard:
                self._mutate(operation+'_intent',study_id,effective,expected_checkpoint,intent_key,
                    lambda:copy.deepcopy(intent),'edit')
                projects=_PreparationProjects(self,phase);models=_PreparationModels(self,phase)
                context=copy.copy(self.projection.context)
                context.projects,context.models,context.runs=projects,models,_PreparationRuns(self)
                pipelines=_PreparationPipelines(self,phase,context);context.pipelines=pipelines
                execution_context=copy.copy(context);execution_context.access=self.access
                execution_context.project_study_execution=self;execution_context.project_execution=self.execution
                studies=Experiments(execution_context)
                publication=SimpleNamespace(runtime_snapshot=snapshot,before_write=guard.publication_started,
                    read_recipe_blob=self.materials.blob)
                result=_prepare_operation(studies,study_id,dict(body,request_key=key),kind,publication=publication)
                value=self._mutate(operation,study_id,effective,self.session.snapshot['checkpoint'],key,
                    lambda:copy.deepcopy(result),'edit')
                guard.confirmed()
                return value

    def prepare_package(self,study_id,body,expected_checkpoint,key):
        return self._prepare_candidate(study_id,body,expected_checkpoint,key,'package')

    def prepare_verifier(self,study_id,body,expected_checkpoint,key):
        return self._prepare_candidate(study_id,body,expected_checkpoint,key,'verify')

    def assert_quiescent(self):
        if self._dirty or self._pending_epochs or self._package_records:_invalid('Study publication is still pending.','busy')
