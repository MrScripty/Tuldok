"""Finite study intent and conservative admission accounting, never a runner.

Pipeline owns immutable composition. Runs/Access own process custody, execution
rights and worker continuations. All mutations use their existing catalog lock.
"""
import copy
import shutil
import uuid

from access import authorized
from metadata import CommitOutcomeUnknown
from model_definitions import checked_json, natural, reference, retained_json, text, SHA
from pipeline import closed, digest, identifier
from runs import ACTIVE, REQUEST_KEY
from workbench import WorkbenchError, encode

DIMENSIONS=('attempt_slots','admitted_wall_seconds','retained_bytes','peak_staging_bytes')
MAX_STUDY_DOCUMENT=1024*1024


def budget(value, minimum=1):
    closed(value,DIMENSIONS)
    for key in DIMENSIONS:natural(value[key],key,minimum)
    return copy.deepcopy(value)


def request_key(value):
    if type(value) is not str or not REQUEST_KEY.fullmatch(value):
        raise WorkbenchError('Request key requires8–128 supported characters.')
    return value


class Experiments:
    def __init__(self,dataset):
        self.dataset=dataset;self.db=dataset.db;self.lock=dataset.lock;self.access=dataset.access

    def _study(self,study_id):
        identifier(study_id)
        row=self.db.execute('SELECT revision,admission_epoch,document FROM model_studies WHERE id=%s',(study_id,)).fetchone()
        if row is None:raise WorkbenchError('Study not found.','not_found',404)
        value=retained_json(row['document'],MAX_STUDY_DOCUMENT)
        closed(value,('format','id','revision','name','admission_epoch','open','state','limits','policy',
                      'membership_revision','trial_ids','stop_receipt_id'))
        if (value['format']!='study_v1' or value['id']!=study_id or value['revision']!=row['revision'] or
                value['admission_epoch']!=row['admission_epoch'] or type(value['open']) is not bool or
                value['state'] not in ('draft','open','stopping','stopped','unknown') or
                value['open']!=(value['state']=='open')):
            raise WorkbenchError('Stored study identity/lifecycle differs.','unavailable',409)
        natural(value['revision'],'Study revision',1);natural(value['admission_epoch'],'Epoch')
        natural(value['membership_revision'],'Membership revision',1);text(value['name'],'Study name')
        budget(value['limits']);reference(value['policy'],'selection_policy',self.db.dataset_id)
        self.policy(value['policy'])
        if type(value['trial_ids']) is not list or len(value['trial_ids'])>10000:
            raise WorkbenchError('Stored study membership differs.','unavailable',409)
        for trial_id in value['trial_ids']:identifier(trial_id)
        if len(set(value['trial_ids']))!=len(value['trial_ids']):raise WorkbenchError('Duplicate trial membership.','unavailable',409)
        if value['stop_receipt_id'] is not None:identifier(value['stop_receipt_id'])
        membership=self.db.execute('SELECT document FROM model_study_memberships WHERE study_id=%s AND revision=%s',
                                  (study_id,value['membership_revision'])).fetchone()
        if membership is None or retained_json(membership[0],MAX_STUDY_DOCUMENT)!={'trial_ids':value['trial_ids']}:
            raise WorkbenchError('Stored immutable membership differs.','unavailable',409)
        return value

    def _write(self,value,action,details=None):
        value['revision']=natural(value['revision']+1,'Study revision',1)
        value=checked_json(value,MAX_STUDY_DOCUMENT)
        self.db.execute('UPDATE model_studies SET revision=%s,admission_epoch=%s,document=%s WHERE id=%s',
                        (value['revision'],value['admission_epoch'],encode(value),value['id']))
        self.access.audit(action,value['id'],dict(details or {},revision=value['revision'],epoch=value['admission_epoch']))
        return value

    def _expected(self,value,body):
        natural(body['revision'],'Study revision',1)
        if value['revision']!=body['revision']:raise WorkbenchError('Study changed. Reload.','stale',409)

    @authorized('inspect','studies.policy')
    def policy(self,ref):
        ref=reference(ref,'selection_policy',self.db.dataset_id)
        row=self.db.execute('SELECT document FROM model_selection_policies WHERE id=%s AND revision=%s AND sha256=%s',
                            (ref['id'],ref['revision'],ref['sha256'])).fetchone()
        if row is None:raise WorkbenchError('Selection policy not found.','not_found',404)
        value=retained_json(row[0]);self._policy(value)
        if digest(value)!=ref['sha256']:raise WorkbenchError('Selection policy identity differs.','unavailable',409)
        return value

    @staticmethod
    def _policy(value):
        closed(value,('format','metric_definition_sha256','checkpoint_rule','replicate_reduce',
                      'required_capabilities','numerical_acceptance','tie_break'))
        if (value['format']!='selection_policy_v1' or type(value['metric_definition_sha256']) is not str or
                not SHA.fullmatch(value['metric_definition_sha256']) or value['checkpoint_rule'] not in ('selected','last','explicit') or
                value['replicate_reduce'] not in ('individual','mean') or value['numerical_acceptance'] not in ('required','diagnostic') or
                value['tie_break']!='trial_id' or type(value['required_capabilities']) is not list or
                len(value['required_capabilities'])>64):
            raise WorkbenchError('Unsupported selection policy.')
        for item in value['required_capabilities']:text(item,'Required capability',64)
        if len(set(value['required_capabilities']))!=len(value['required_capabilities']):
            raise WorkbenchError('Duplicate required capability.')
        return value

    @authorized('edit','studies.create',owner_only=True)
    def create(self,body):
        closed(body,('name','limits','policy'));body=checked_json(body)
        policy=self._policy(body['policy']);limits=budget(body['limits']);text(body['name'],'Study name')
        study_id=uuid.uuid4().hex;policy_sha=digest(policy)
        with self.lock,self.db.transaction():
            self.access.require('edit','studies.create',owner_only=True)
            prior=self.db.execute('SELECT id,revision FROM model_selection_policies WHERE sha256=%s',(policy_sha,)).fetchone()
            policy_id=prior['id'] if prior else uuid.uuid4().hex
            if not prior:self.db.execute('INSERT INTO model_selection_policies VALUES(%s,%s,%s,%s)',(policy_id,1,policy_sha,encode(policy)))
            ref={'kind':'selection_policy','catalog_id':self.db.dataset_id,'id':policy_id,'revision':1,'sha256':policy_sha}
            value={'format':'study_v1','id':study_id,'revision':1,'name':body['name'],'admission_epoch':0,
                   'open':False,'state':'draft','limits':limits,'policy':ref,'membership_revision':1,'trial_ids':[],
                   'stop_receipt_id':None}
            self.db.execute('INSERT INTO model_studies VALUES(%s,%s,%s,%s)',(study_id,1,0,encode(value)))
            self.db.execute('INSERT INTO model_study_memberships VALUES(%s,%s,%s)',(study_id,1,encode({'trial_ids':[]})))
            self.access.audit('studies.create',study_id,{'policy_sha256':policy_sha,'limits':limits})
        return value

    @authorized('inspect','studies.trial')
    def trial(self,trial_id):
        identifier(trial_id)
        row=self.db.execute('SELECT study_id,material_sha256,replicate,document FROM model_trials WHERE id=%s',(trial_id,)).fetchone()
        if row is None:raise WorkbenchError('Trial not found.','not_found',404)
        value=retained_json(row['document']);closed(value,('format','id','study_id','material','replicate'))
        reference(value['material'],'recipe_material',self.db.dataset_id);natural(value['replicate'],'Replicate')
        if (value['format']!='trial_v1' or value['id']!=trial_id or value['study_id']!=row['study_id'] or
                value['replicate']!=row['replicate'] or value['material']['sha256']!=row['material_sha256']):
            raise WorkbenchError('Stored trial identity differs.','unavailable',409)
        return value

    @authorized('edit','studies.prepare_trial')
    def prepare_trial(self,study_id,body):
        closed(body,('request_key','revision','graph_id','graph_revision','model','replicate'),('reconcile_capture',));body=checked_json(body)
        request_key(body['request_key']);natural(body['replicate'],'Replicate')
        actor=self.access._context().actor_id;sha=digest({'study_id':study_id,'body':body})
        with self.lock:
            receipt=self._receipt(actor,'studies.prepare_trial',body['request_key'],sha)
            if receipt:return receipt
            study=self._study(study_id);self._expected(study,body)
        prepare=(self.dataset.pipelines.prepare_builtin_material if self.dataset.pipelines.get(body['graph_id']).get('recipe')=='image_classification_model_v2'
                 else self.dataset.pipelines.prepare_external_material)
        prepared=prepare(body['graph_id'],body['graph_revision'],body['model'],
                                            reconcile_capture=body.get('reconcile_capture',False))
        try:
            with self.lock,self.db.transaction():
                receipt=self._receipt(actor,'studies.prepare_trial',body['request_key'],sha)
                if receipt:
                    self.db.on_commit(lambda:shutil.rmtree(prepared['staging'],ignore_errors=True));return receipt
                self.access.require('edit','studies.prepare_trial',study_id)
                study=self._study(study_id);self._expected(study,body)
                if len(study['trial_ids'])>=10000:raise WorkbenchError('Study membership is full.','unavailable',409)
                material=self.dataset.pipelines._retain_material(prepared)
                prior=self.db.execute('SELECT id FROM model_trials WHERE study_id=%s AND material_sha256=%s AND replicate=%s',
                                      (study_id,material['ref']['sha256'],body['replicate'])).fetchone()
                if prior:raise WorkbenchError('Material/replicate already belongs to this study.','conflict',409)
                value={'format':'trial_v1','id':uuid.uuid4().hex,'study_id':study_id,'material':material['ref'],'replicate':body['replicate']}
                self.db.execute('INSERT INTO model_trials VALUES(%s,%s,%s,%s,%s)',
                                (value['id'],study_id,material['ref']['sha256'],value['replicate'],encode(value)))
                study['trial_ids'].append(value['id']);study['membership_revision']+=1
                self.db.execute('INSERT INTO model_study_memberships VALUES(%s,%s,%s)',
                                (study_id,study['membership_revision'],encode({'trial_ids':study['trial_ids']})))
                self._write(study,'studies.prepare_trial',{'trial_id':value['id']})
                self._save_receipt(actor,'studies.prepare_trial',body['request_key'],sha,value)
            return value
        except CommitOutcomeUnknown:raise
        except BaseException:
            shutil.rmtree(prepared['staging'],ignore_errors=True);raise

    def _receipt(self,actor,operation,key,sha):
        row=self.db.execute('SELECT request_sha256,document FROM model_operation_receipts WHERE actor_id=%s AND operation_id=%s AND request_key=%s',
                            (actor,operation,key)).fetchone()
        if row is None:return None
        if row['request_sha256']!=sha:raise WorkbenchError('Request key is bound to different inputs.','conflict',409)
        return retained_json(row['document'],MAX_STUDY_DOCUMENT)

    def _save_receipt(self,actor,operation,key,sha,value):
        value=checked_json(value,MAX_STUDY_DOCUMENT)
        self.db.execute('INSERT INTO model_operation_receipts VALUES(%s,%s,%s,%s,%s)',(actor,operation,key,sha,encode(value)))

    def _reservation(self,row):
        value=retained_json(row['document'])
        closed(value,('id','study_id','admission_epoch','request_key','actor_id','trial_id','parent_run_id','run_id',
                      'request_sha256','material_sha256','envelope','state','settled'))
        for key in ('id','study_id','actor_id','request_key','request_sha256','trial_id','run_id'):
            if value[key]!=row[key]:raise WorkbenchError('Reservation identity differs.','unavailable',409)
        budget(value['envelope']);natural(value['admission_epoch'],'Reservation epoch')
        if value['state'] not in ('reserved','running','settled','unknown'):
            raise WorkbenchError('Reservation state differs.','unavailable',409)
        if value['state']=='settled':
            if value['settled']!=value['envelope']:
                raise WorkbenchError('Conservative settled charge differs.','unavailable',409)
        elif value['settled'] is not None:
            raise WorkbenchError('Open reservation cannot contain a settled charge.','unavailable',409)
        trial=self.trial(value['trial_id'])
        material=self.dataset.pipelines.recipe_material(trial['material'])
        if (trial['study_id']!=value['study_id'] or value['material_sha256']!=trial['material']['sha256'] or
                value['envelope']!=material['material']['resource_envelope']):
            raise WorkbenchError('Reservation material/envelope differs.','unavailable',409)
        run=self.dataset.runs._load(value['run_id'])
        if (run['actor_id']!=value['actor_id'] or run['request_sha256']!=value['request_sha256'] or
                run['parent_run_id']!=value['parent_run_id'] or
                run.get('approval_material_sha256')!=value['material_sha256']):
            raise WorkbenchError('Reservation and Run receipt differ.','unavailable',409)
        return value

    def _reservations(self,study_id):
        return [self._reservation(row) for row in self.db.execute(
            'SELECT * FROM model_attempt_reservations WHERE study_id=%s ORDER BY id',(study_id,))]

    def _totals(self,reservations):
        totals={key:0 for key in DIMENSIONS}
        for value in reservations:
            charge=value['settled'] if value['state']=='settled' else value['envelope']
            if charge is None:raise WorkbenchError('Settled reservation lacks a charge.','unavailable',409)
            for key in DIMENSIONS:totals[key]=natural(totals[key]+charge[key],'Study total')
        return totals

    @authorized('inspect','studies.get')
    def get(self,study_id,*,offset=0,limit=100,revision=None):
        natural(offset,'Page offset');natural(limit,'Page limit',1,100)
        if revision is not None:natural(revision,'Study revision',1)
        if offset and revision is None:raise WorkbenchError('Later reservation pages require the study revision.')
        with self.lock:
            study=self._study(study_id);reservations=self._reservations(study_id)
            if revision is not None and revision!=study['revision']:raise WorkbenchError('Study changed between pages.','stale',409)
            end=min(offset+limit,len(reservations))
            return {'study':study,'reservations':reservations[offset:end],'charged':self._totals(reservations),
                    'page':{'offset':offset,'limit':limit,'total':len(reservations),'study_revision':study['revision'],
                            'next_offset':end if end<len(reservations) else None}}

    @authorized('inspect','studies.list')
    def list(self,*,cursor=None,limit=20):
        natural(limit,'Page limit',1,20)
        if cursor is not None:identifier(cursor)
        with self.lock:
            rows=self.db.execute('SELECT id FROM model_studies WHERE id>%s ORDER BY id LIMIT %s',(cursor or '',limit+1)).fetchall()
            summaries=[]
            for row in rows[:limit]:
                value=self._study(row[0]);summary={key:item for key,item in value.items() if key!='trial_ids'}
                summary['trial_count']=len(value['trial_ids']);summaries.append(summary)
            return {'studies':summaries,'limit':limit,'next_cursor':rows[limit-1][0] if len(rows)>limit else None}

    @authorized('edit','studies.save',owner_only=True)
    def save(self,study_id,body):
        closed(body,('revision','name','limits','policy'));body=checked_json(body)
        text(body['name'],'Study name');limits=budget(body['limits'])
        with self.lock,self.db.transaction():
            self.access.require('edit','studies.save',study_id,owner_only=True)
            study=self._study(study_id);self._expected(study,body);self.policy(body['policy'])
            totals=self._totals(self._reservations(study_id))
            if any(totals[key]>limits[key] for key in DIMENSIONS):
                raise WorkbenchError('Limits are below existing obligations.','conflict',409)
            study.update(name=body['name'],limits=limits,policy=body['policy'])
            return self._write(study,'studies.save')

    def _children_ceased(self,reservations):
        """Use owned Run custody; no PID signalling or optimistic terminal inference."""
        unknown=False;active=False
        for reservation in reservations:
            run=self.dataset.runs._load(reservation['run_id'])
            if run['state']=='unknown':unknown=True
            elif run['state'] in ACTIVE:active=True
            elif not self._ceased(run):unknown=True
        return not (unknown or active),unknown

    def _ceased(self,run):
        if run['state'] in ACTIVE or run['state']=='unknown':return False
        if run.get('custody_phase')=='drained':return True
        if not self.dataset.runs._external(run):
            from runs import process_status
            return run.get('worker') is None or process_status(run['worker'])=='ceased'
        return self.dataset.runs._external_recovery_state(run)=='interrupted'

    @authorized('execute','studies.continue',owner_only=True)
    def continue_study(self,study_id,body):
        closed(body,('request_key','revision','admission_epoch'));request_key(body['request_key'])
        natural(body['admission_epoch'],'Admission epoch');actor=self.access._context().actor_id
        sha=digest({'study_id':study_id,'body':body})
        with self.lock,self.db.transaction():
            self.access.require('execute','studies.continue',study_id,owner_only=True)
            receipt=self._receipt(actor,'studies.continue',body['request_key'],sha)
            if receipt:return receipt
            study=self._study(study_id);self._expected(study,body)
            reservations=self._reservations(study_id);ceased,unknown=self._children_ceased(reservations)
            if (study['open'] or study['admission_epoch']!=body['admission_epoch'] or not ceased or unknown or
                    any(item['state']=='unknown' for item in reservations)):
                raise WorkbenchError('Study cannot open before known child cessation and exact epoch.','unavailable',409)
            totals=self._totals(reservations)
            if any(totals[key]>=study['limits'][key] for key in DIMENSIONS):
                raise WorkbenchError('Study has no remaining budget.','unavailable',409)
            if self.dataset.runs._external_blocked:raise WorkbenchError('Run custody is unknown.','unavailable',409)
            study.update(open=True,state='open',admission_epoch=natural(study['admission_epoch']+1,'Admission epoch'))
            value=self._write(study,'studies.continue')
            self._save_receipt(actor,'studies.continue',body['request_key'],sha,value)
            return value

    @authorized('approve-execution','studies.approve',owner_only=True)
    def approve(self,study_id,body):
        closed(body,('trial_id','expected_material_sha256','consumer_actor_id'),('ttl_seconds',))
        identifier(body['trial_id']);identifier(body['consumer_actor_id'])
        with self.lock:
            study=self._study(study_id);trial=self.trial(body['trial_id'])
            if trial['study_id']!=study_id or trial['id'] not in study['trial_ids']:
                raise WorkbenchError('Approve an exact member trial.')
            if body['expected_material_sha256']!=trial['material']['sha256']:
                raise WorkbenchError('Composed material differs. Review the exact trial.','stale',409)
        # Full retained model/profile/input and current executable proof occurs
        # before the short grant transaction, without a process or private Run.
        prepared=self.dataset.pipelines.preflight_recipe_material(trial['material'])
        if prepared.get('kind')=='builtin':
            raise WorkbenchError('Built-in classifier execution remains owner-only; no delegated execution grant applies.','unsupported',409)
        with self.lock,self.db.transaction():
            self.access.require('approve-execution','studies.approve',study_id,owner_only=True)
            grant=self.access.grant_execution(trial['material']['sha256'],body['consumer_actor_id'],body.get('ttl_seconds',600))
            self.access.audit('studies.approve',study_id,{'trial_id':trial['id'],'material_sha256':trial['material']['sha256'],
                                                       'approval_id':grant['id']})
        return grant

    @authorized('inspect','studies.admit')
    def admit(self,study_id,body,*,selection=None):
        """One finite exact attempt; request identity includes operation semantics."""
        closed(body,('request_key','revision','admission_epoch','trial_id'),('approval_id','parent_run_id'))
        body=checked_json(body);request_key(body['request_key']);identifier(body['trial_id'])
        natural(body['revision'],'Study revision',1);natural(body['admission_epoch'],'Admission epoch')
        context=self.access.require_external_submission();actor=context.actor_id
        import agent_api
        if selection is not None:
            agent_api.require_selection(selection,'studies.admit')
            if selection[1]!=1:raise WorkbenchError('This admission meaning is not implemented.','unsupported',409)
        contract_sha=agent_api.contract('studies.admit',1)['sha256']
        sha=digest({'operation_id':'studies.admit','version':1,'contract_sha256':contract_sha,
                    'study_id':study_id,'body':body})
        with self.lock:
            receipt=self._admission_receipt(study_id,actor,body['request_key'],sha)
            if receipt:return receipt
            study=self._study(study_id);self._expected(study,body)
            trial=self.trial(body['trial_id'])
            if trial['study_id']!=study_id or trial['id'] not in study['trial_ids']:
                raise WorkbenchError('Trial is not a member of this study.')
        material=self.dataset.pipelines.recipe_material(trial['material'],verify=True)
        builtin=material['material']['trainer']['id']=='tinycnn_cpu_v2'
        if builtin:self.access.require('execute','studies.admit_builtin',study_id,owner_only=True)
        envelope=material['material']['resource_envelope']
        run_id=uuid.uuid4().hex;staging=self.dataset.runs.path/('.external-'+run_id)
        rollback_owned=False
        try:
            captured=self.dataset.pipelines.capture_recipe_material(trial['material'],staging)
            with self.lock,self.db.transaction():
                self.db.on_rollback(lambda:shutil.rmtree(staging,ignore_errors=True))
                rollback_owned=True
                self.access.require_external_submission()
                receipt=self._admission_receipt(study_id,actor,body['request_key'],sha)
                if receipt:
                    self.db.on_commit(lambda:shutil.rmtree(staging,ignore_errors=True));return receipt
                study=self._study(study_id);self._expected(study,body)
                if not study['open'] or study['admission_epoch']!=body['admission_epoch']:
                    raise WorkbenchError('Study admission epoch is closed.','stale',409)
                reservations=self._reservations(study_id);ceased,unknown=self._children_ceased(reservations)
                if not ceased or unknown or any(item['state']=='unknown' for item in reservations):
                    raise WorkbenchError('Study already has an active or unknown child.','unavailable',409)
                totals=self._totals(reservations)
                if any(natural(totals[key]+envelope[key],'Requested total')>study['limits'][key] for key in DIMENSIONS):
                    raise WorkbenchError('Finite study budget is exhausted.','unavailable',409)
                parent=None
                if body.get('parent_run_id') is not None:
                    identifier(body['parent_run_id']);parent=self.dataset.runs._load(body['parent_run_id'])
                    if not any(item['run_id']==parent['id'] and item['trial_id']==trial['id'] for item in reservations):
                        raise WorkbenchError('Retry parent does not belong to this trial.')
                    if parent['state'] not in ('failed','cancelled','interrupted'):
                        raise WorkbenchError('Retry requires a ceased failed/cancelled/interrupted parent.')
                run_key='study-'+digest({'study_id':study_id,'actor_id':actor,'request_key':body['request_key'],
                                         'operation_id':'studies.admit'})
                if builtin:
                    if body.get('approval_id') is not None:
                        raise WorkbenchError('Built-in owner admission does not consume delegated external grants.')
                    self.dataset.runs._available()
                    run=self.dataset.runs._admit(run_key,sha,captured['graph'],captured['validation'],captured['release'],
                                                parent,run_id=run_id,composition=captured['composition'])
                    self.db.on_commit(lambda:self.dataset.runs._start())
                else:
                    run_body={'request_key':run_key,'graph_id':captured['graph']['id'],
                              'graph_revision':captured['graph']['revision'],'expected_digest':captured['material_sha256']}
                    if body.get('approval_id') is not None:run_body['approval_id']=body['approval_id']
                    run=self.dataset.runs._admit_external_prepared(run_body,captured,run_id,staging,
                                check_current=False,request_hash=sha,parent=parent,
                                approval_material_sha256=trial['material']['sha256'])
                reservation={'id':uuid.uuid4().hex,'study_id':study_id,'admission_epoch':study['admission_epoch'],
                    'request_key':body['request_key'],'actor_id':actor,'trial_id':trial['id'],
                    'parent_run_id':parent['id'] if parent else None,'run_id':run_id,'request_sha256':sha,
                    'material_sha256':trial['material']['sha256'],'envelope':envelope,'state':'reserved','settled':None}
                self.db.execute('INSERT INTO model_attempt_reservations VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (reservation['id'],study_id,actor,body['request_key'],sha,trial['id'],run_id,encode(reservation)))
                self._write(study,'studies.admit',{'run_id':run_id,'reservation_id':reservation['id'],'request_sha256':sha})
            return {'reservation':reservation,'run':self.dataset.runs.get(run_id)}
        except CommitOutcomeUnknown:raise
        except BaseException:
            # Once the transaction owns capture, only its confirmed rollback
            # can delete it. Response reads/callbacks may fail after durable GO.
            if not rollback_owned:shutil.rmtree(staging,ignore_errors=True)
            raise

    def _admission_receipt(self,study_id,actor,key,sha):
        row=self.db.execute('SELECT * FROM model_attempt_reservations WHERE study_id=%s AND request_key=%s',
                            (study_id,key)).fetchone()
        if row is None:return None
        if row['actor_id']!=actor or row['request_sha256']!=sha:
            raise WorkbenchError('Admission key is bound to different actor/inputs.','conflict',409)
        reservation=self._reservation(row)
        return {'reservation':reservation,'run':self.dataset.runs.get(reservation['run_id'])}

    @authorized('inspect','studies.reconcile')
    def reconcile(self,study_id):
        """Explicit accounting reconciliation; never wake or replay a Run."""
        with self.lock,self.db.transaction():
            study=self._study(study_id);reservations=self._reservations(study_id);changed=False
            for value in reservations:
                run=self.dataset.runs._load(value['run_id'])
                state='unknown' if run['state']=='unknown' else 'running' if run['state'] in ACTIVE else 'settled'
                if state=='settled' and not self._ceased(run):state='unknown'
                if state!=value['state']:
                    value['state']=state
                    # Keep worst-case retained/staging charges until owned cleanup is proved.
                    value['settled']=copy.deepcopy(value['envelope']) if state=='settled' else None
                    self.db.execute('UPDATE model_attempt_reservations SET document=%s WHERE id=%s',(encode(value),value['id']))
                    changed=True
            ceased,unknown=self._children_ceased(reservations)
            if unknown and study['open']:
                study.update(open=False,state='unknown',admission_epoch=natural(study['admission_epoch']+1,'Admission epoch'))
                changed=True
            elif not study['open'] and study['state'] in ('stopping','unknown'):
                state='unknown' if unknown else 'stopped' if ceased else 'stopping'
                if study['state']!=state:study['state']=state;changed=True
            if changed:self._write(study,'studies.reconcile')
        return self.get(study_id)

    @authorized('cancel','studies.stop')
    def stop(self,study_id,body):
        closed(body,('request_key','revision'));request_key(body['request_key'])
        actor=self.access._context().actor_id;sha=digest({'study_id':study_id,'body':body})
        with self.lock,self.db.transaction():
            self.access.require('cancel','studies.stop',study_id)
            receipt=self._receipt(actor,'studies.stop',body['request_key'],sha)
            if receipt is None:
                study=self._study(study_id);self._expected(study,body)
                study.update(open=False,state='stopping',admission_epoch=natural(study['admission_epoch']+1,'Admission epoch'),
                             stop_receipt_id=uuid.uuid4().hex)
                self._write(study,'studies.stop')
                pending=[]
                for item in self._reservations(study_id):
                    if not self._ceased(self.dataset.runs._load(item['run_id'])):pending.append(item['run_id'])
                receipt={'study_id':study_id,'stop_receipt_id':study['stop_receipt_id'],'admission_epoch':study['admission_epoch'],
                         'run_ids':pending}
                self._save_receipt(actor,'studies.stop',body['request_key'],sha,receipt)
        # Epoch closure has acknowledged commit before any child cancellation.
        for run_id in receipt['run_ids']:self.dataset.runs.cancel(run_id)
        return {'receipt':receipt,'status':self.reconcile(study_id)}

    @authorized('edit','studies.select_candidate')
    def select_candidate(self,study_id,body):
        """Retain an exact diagnostic/qualified decision, separately from export."""
        closed(body,('request_key','revision','trial_id','run_id'),('checkpoint_sha256',))
        request_key(body['request_key']);identifier(body['trial_id']);identifier(body['run_id'])
        actor=self.access._context().actor_id;request_sha=digest({'study_id':study_id,'body':body})
        with self.lock:
            prior=self._receipt(actor,'studies.select_candidate',body['request_key'],request_sha)
            if prior:return prior
            study=self._study(study_id);self._expected(study,body)
            policy=self.policy(study['policy']);trial=self.trial(body['trial_id'])
            if trial['study_id']!=study_id:raise WorkbenchError('Trial belongs to another study.')
            reservation=self.db.execute('SELECT * FROM model_attempt_reservations WHERE run_id=%s',(body['run_id'],)).fetchone()
            if reservation is None or self._reservation(reservation)['trial_id']!=trial['id']:
                raise WorkbenchError('Run does not belong to the selected trial.')
        # Runs verifies retained bytes and task semantics outside a write transaction.
        evidence=self.dataset.runs.model_evidence(body['run_id'],{})
        if evidence['state']!='verified':raise WorkbenchError('Candidate requires verified model evidence.','unsupported',409)
        if evidence['manifest']['producer']['material_sha256']!=trial['material']['sha256']:
            raise WorkbenchError('Candidate evidence differs from its trial material.','unavailable',409)
        checkpoint=self._candidate_checkpoint(evidence,policy,body.get('checkpoint_sha256'))
        with self.lock,self.db.transaction():
            self.access.require('edit','studies.select_candidate',study_id)
            prior=self._receipt(actor,'studies.select_candidate',body['request_key'],request_sha)
            if prior:return prior
            study=self._study(study_id);self._expected(study,body)
            run=self.dataset.runs._load(body['run_id'])
            if run['state']!='completed':raise WorkbenchError('Candidate Run is not completed.','conflict',409)
            metrics=next((item for item in run['artifacts'] if item['name']=='metrics.json'),None)
            if metrics is None:raise WorkbenchError('Candidate evaluation artifact is unavailable.','unavailable',409)
            candidate={'format':'candidate_v1','id':uuid.uuid4().hex,'study_id':study_id,
                'trial_id':trial['id'],'run_id':run['id'],'checkpoint_sha256':checkpoint['sha256'],
                'evaluation_sha256':metrics['sha256'],'policy':study['policy'],'decision':'diagnostic',
                'limitations':['Validation diagnostics only; no quality threshold or physical acceptance is qualified.']}
            self.db.execute('INSERT INTO model_candidates VALUES(%s,%s,%s,%s,%s)',
                (candidate['id'],study_id,trial['id'],run['id'],encode(candidate)))
            self.access.audit('studies.select_candidate',candidate['id'],{'study_id':study_id,'run_id':run['id'],
                'checkpoint_sha256':checkpoint['sha256'],'decision':candidate['decision']})
            self._write(study,'studies.candidate_selected',{'candidate_id':candidate['id']})
            result=self._candidate_result(candidate,checkpoint)
            self._save_receipt(actor,'studies.select_candidate',body['request_key'],request_sha,result)
        return result

    def _candidate_checkpoint(self,evidence,policy,requested):
        if policy['replicate_reduce']!='individual':
            raise WorkbenchError('Mean-replicate candidate selection is not qualified.','unsupported',409)
        import model_evidence
        definitions=evidence['metric_definitions']
        matches=[item for item in definitions if model_evidence.digest(item)==policy['metric_definition_sha256']]
        if len(matches)!=1:raise WorkbenchError('Selection metric differs from the retained evaluator definition.','incompatible',409)
        coverage=evidence['manifest']['coverage']
        available=set(coverage['required']+coverage['optional'])-{item['capability'] for item in coverage['omitted']}
        if not set(policy['required_capabilities'])<=available:
            raise WorkbenchError('Candidate lacks required evidence capabilities.','unsupported',409)
        entries=evidence['checkpoint_index']['entries']
        rule=policy['checkpoint_rule']
        if rule=='explicit':
            chosen=[item for item in entries if item['checkpoint']['sha256']==requested]
        else:
            chosen=[item for item in entries if item['selected']] if rule=='selected' else entries[-1:]
            if requested is not None and (len(chosen)!=1 or chosen[0]['checkpoint']['sha256']!=requested):
                raise WorkbenchError('Explicit checkpoint contradicts the selection policy.')
        if len(chosen)!=1:raise WorkbenchError('Selection requires one retained checkpoint.')
        checkpoint=chosen[0]['checkpoint']
        observed=[item for item in evidence['observations'] if item['checkpoint_sha256']==checkpoint['sha256']
                  and item['metric_id']==matches[0]['id'] and item['state']=='observed']
        if len(observed)!=1:raise WorkbenchError('Selection requires a defined metric at this checkpoint.','unavailable',409)
        # A successful classifier fit supplies diagnostics, never an invented
        # model-quality threshold or physical acceptance result.
        if policy['numerical_acceptance']=='required':
            raise WorkbenchError('This evaluator has no qualified numerical acceptance criterion.','unsupported',409)
        return checkpoint

    def _candidate_result(self,value,checkpoint):
        return {'ref':{'kind':'candidate','catalog_id':self.db.dataset_id,'id':value['id'],'sha256':digest(value)},
                'candidate':value,'run_id':value['run_id'],'checkpoint':checkpoint}

    @authorized('inspect','studies.candidate')
    def candidate(self,candidate_id):
        identifier(candidate_id)
        with self.lock:
            row=self.db.execute('SELECT * FROM model_candidates WHERE id=%s',(candidate_id,)).fetchone()
            if row is None:raise WorkbenchError('Candidate not found.','not_found',404)
            value=retained_json(row['document'])
            closed(value,('format','id','study_id','trial_id','run_id','checkpoint_sha256','evaluation_sha256',
                          'policy','decision','limitations'))
            if (value['format']!='candidate_v1' or any(value[key]!=row[key] for key in ('id','study_id','trial_id','run_id'))
                    or value['decision']!='diagnostic'):
                raise WorkbenchError('Stored candidate identity differs.','unavailable',409)
            if (type(value['checkpoint_sha256']) is not str or not SHA.fullmatch(value['checkpoint_sha256'])
                    or type(value['evaluation_sha256']) is not str or not SHA.fullmatch(value['evaluation_sha256'])
                    or type(value['limitations']) is not list or len(value['limitations'])>64):
                raise WorkbenchError('Stored candidate evidence identity differs.','unavailable',409)
            for item in value['limitations']:text(item,'Candidate limitation',500)
            reference(value['policy'],'selection_policy',self.db.dataset_id);policy=self.policy(value['policy'])
            trial=self.trial(value['trial_id'])
            if trial['study_id']!=value['study_id']:raise WorkbenchError('Candidate trial differs.','unavailable',409)
            reservation=self.db.execute('SELECT * FROM model_attempt_reservations WHERE run_id=%s',(value['run_id'],)).fetchone()
            if reservation is None or self._reservation(reservation)['trial_id']!=trial['id']:
                raise WorkbenchError('Candidate Run association differs.','unavailable',409)
        evidence=self.dataset.runs.model_evidence(value['run_id'],{'checkpoint_sha256':value['checkpoint_sha256']})
        if evidence['state']!='verified':raise WorkbenchError('Candidate evidence is unavailable.','unavailable',409)
        if evidence['manifest']['producer']['material_sha256']!=trial['material']['sha256']:
            raise WorkbenchError('Candidate evidence material differs.','unavailable',409)
        checkpoint=self._candidate_checkpoint(evidence,policy,value['checkpoint_sha256'])
        run=self.dataset.runs.get(value['run_id'])
        if not any(item['name']=='metrics.json' and item['sha256']==value['evaluation_sha256'] for item in run['artifacts']):
            raise WorkbenchError('Candidate evaluation identity differs.','unavailable',409)
        return self._candidate_result(value,checkpoint)
