"""Explicit current-host producers over inert canonical producer history.

No owner is constructed by this adapter's constructor. Preparation is part of
Session's canonical foreground transaction; worker launch requires its confirmed
acknowledgement and is never inferred from a saved receipt or imported history.
"""
import copy
import json
import threading
import uuid

from access import AccessError, current_context
from image_sources import ImageSources
from project_producers import (FAMILIES, TABLES, ProjectProducers, _capture_job,
    _CapturedEvidence, _composed, _declarations, _referenced_artifacts, decode_records,
    identity, shape)
from workbench import WorkbenchError

KINDS = {'generation_history':'generation', 'grounded_history':'grounded',
         'caption_proposal_history':'caption', 'text_proposal_history':'text_proposal'}
JOB_KINDS = {'generation_history':'synthetic', 'grounded_history':'grounded',
             'caption_proposal_history':'caption', 'text_proposal_history':'text_classification'}
FINISH = {'generation_history':'synthetic.finish', 'grounded_history':'grounded.finish',
          'caption_proposal_history':'caption.finish', 'text_proposal_history':'text_classification.finish'}
ACTIONS = frozenset(('start','resume','review','decide','cancel'))
OPERATIONS = frozenset('producers.'+value for value in ACTIONS)


def validate_operation_result(operation, target, result, records):
    if operation not in OPERATIONS:
        return False
    shape(result, {'format','family','origin_catalog_id','producer_id','action'})
    if (result['format'] != 'project_producer_action_v1' or result['family'] not in FAMILIES
            or result['action'] not in ACTIONS or operation != 'producers.'+result['action']):
        raise WorkbenchError('Invalid retained producer action.')
    if ((result['action']=='resume' and result['family']!='generation_history')
            or (result['action']=='review' and result['family']!='grounded_history')
            or (result['action']=='decide' and result['family'] not in ('caption_proposal_history','text_proposal_history'))):
        raise WorkbenchError('Producer action does not belong to this finite family.')
    identity(result['origin_catalog_id']);identity(result['producer_id'])
    if target != result['producer_id'] and not (result['action']=='start' and target is None):
        raise WorkbenchError('Producer action target differs.')
    if not any(r['family']==result['family'] and r['id']==result['origin_catalog_id']+'.'+result['producer_id'] for r in records):
        raise WorkbenchError('Producer action has no retained scientific history.')
    return True


class _LiveContext:
    def __init__(self, adapter):
        self.adapter = adapter
        self.access = adapter.runtime_access
        self.project_execution = adapter.execution
    def __getattr__(self, name):
        return getattr(self.adapter.data.context, name)


class ProjectProducerExecution:
    def __init__(self, session, data, archive, runtime_access=None, *, execution=None):
        self.session, self.db, self.data, self.archive = session, session.db, data, archive
        self.runtime_access = runtime_access or session.runtime_access
        self.execution = execution or self
        self._owners = {}
        self._custody_lock = threading.RLock()
        self._journaled = set()
        self._journal_observations = {}
        self._dirty = {family:set() for family in FAMILIES}
        self._runtime_data = None
        self._fenced = False

    def _family(self, family):
        if family not in FAMILIES:
            raise WorkbenchError('Unsupported project producer family.')
        return family

    def _owner(self, family):
        self._family(family);self.session.check()
        if self._fenced:
            raise WorkbenchError('Current producer custody is uncertain. Reopen for inert inspection.', 'outcome_unknown', 409)
        self._refuse_unknown_provider()
        if family not in self._owners:
            # Imported science retains its physical ordering. A fresh local
            # authority table must allocate beyond those observed ordinals.
            table=TABLES[family]
            observed=max((r['document']['ordinal'] for r in self.session.snapshot['records']
                          if r['family']==family and r['document']['origin_catalog_id']==self.db.dataset_id),default=0)
            current=self.db.execute('SELECT COALESCE(max(ordinal),0) FROM '+table).fetchone()[0]
            maximum=max(observed,current)
            self.db.execute('SELECT setval(pg_get_serial_sequence(%s,%s),%s,%s)',(table,'ordinal',max(1,maximum),maximum>0))
            # The calling action has checked current host authority. Never restore
            # archived jobs into these local authority tables.
            context = _LiveContext(self)
            workbench = copy.copy(self.data.workbench)
            workbench.dataset = context
            if family == 'generation_history':
                from synthetic import Jobs
                from image_generation import ImageRequests
                context.image_requests = ImageRequests(self.runtime_access)
                context.workbench = workbench
                image_context = _LiveContext(self)
                image_context.access = self.data._authority
                image_context.workbench = workbench
                images = ImageSources(image_context)
                def add(body, generation=None):
                    if generation is None:
                        raise WorkbenchError('Current producer context only accepts admitted output.')
                    with self.db.lock, self.db.transaction():
                        key = 'generated-image-'+uuid.uuid4().hex
                        with self.data.runtime_mutation('data.runtime_generated_image', key):
                            self._runtime_data = ('data.runtime_generated_image', key)
                            return images.add(body, generation=generation)
                context.add = add
                owner = Jobs(context)
                context.generation_jobs = owner
                image_context.generation_jobs = owner
            else:
                if family == 'grounded_history':
                    from grounded_candidates import Proposals as Owner
                elif family == 'caption_proposal_history':
                    from caption_proposals import CaptionProposals as Owner
                else:
                    from text_classification_proposals import TextClassificationProposals as Owner
                owner = Owner(workbench)
            self._owners[family] = owner
        return self._owners[family]

    def _mark(self, family, producer_id):
        identity(producer_id)
        if not self.db.in_transaction:
            raise RuntimeError('Producer writes require their owned SQL transaction.')
        self._dirty[family].add(producer_id)

    def mark_generation(self, producer_id):self._mark('generation_history', producer_id)
    def mark_grounded(self, producer_id):self._mark('grounded_history', producer_id)
    def mark_caption(self, producer_id):self._mark('caption_proposal_history', producer_id)
    def mark_text_proposal(self, producer_id):self._mark('text_proposal_history', producer_id)

    def _proof(self, family, job):
        row = self.db.execute('SELECT * FROM access_admissions WHERE id=%s', (job.get('admission_id'),)).fetchone()
        if row is None:
            raise AccessError('Current local producer admission is unavailable.')
        row = dict(row)
        if (row['catalog_id'] != self.db.dataset_id or row['kind'] != JOB_KINDS[family]
                or row['job_id'] != job['id'] or row['request_digest'] != job.get('request_digest')):
            raise AccessError('Current producer admission differs from its retained request.')
        context = current_context()
        if context is None:
            raise AccessError('Producer observation requires current authority.')
        if context.mode == 'job':
            self.runtime_access.require_job(JOB_KINDS[family], job['id'], job['admission_id'], job['request_digest'])
            self.runtime_access.require('edit', FINISH[family], job['id'])
        elif context.mode == 'system':
            # Only a constructed local owner can reconcile its own table.
            self.runtime_access.require('cancel', JOB_KINDS[family]+'.reconcile', job['id'])
        else:
            self.runtime_access.require('inspect', 'producers.observe', job['id'])

    def capture_dirty(self, before_records):
        result = []
        if self._runtime_data is not None:
            operation, key = self._runtime_data
            result.extend(self.data.capture_runtime_changes(before_records, operation=operation, key=key))
        if not any(self._dirty.values()):
            return result
        capture = copy.copy(self.archive)
        capture._origin = self.db.dataset_id
        capture._artifacts = {}
        capture._pending_payloads = {}
        for family, ids in self._dirty.items():
            for producer_id in sorted(ids):
                row = self.db.execute('SELECT data,ordinal FROM '+TABLES[family]+' WHERE id=%s', (producer_id,)).fetchone()
                if row is None:
                    raise WorkbenchError('Current producer row disappeared.')
                job = json.loads(row[0]);self._proof(family, job)
                entries = []
                if family == 'generation_history':
                    entries = [(json.loads(raw),order) for raw,order in self.db.execute(
                        'SELECT data,storage_order FROM generation_entries WHERE job_id=%s ORDER BY ordinal',(producer_id,))]
                record = _capture_job(capture, family, job, row[1], entries)
                # Keep all observed entry facts across explicit continuation and
                # deletion; the current view remains the final observation.
                previous = next((r for r in before_records if r['family']==family and r['id']==record['id']),None)
                if previous is not None and family == 'generation_history':
                    old = {v['entry']['id']:v for v in previous['document']['entries']}
                    for value in record['document']['entries']:
                        if value['entry']['id'] in old:
                            history = copy.deepcopy(old[value['entry']['id']]['history'])
                            payload_history=copy.deepcopy(old[value['entry']['id']].get('history_payloads',
                                [old[value['entry']['id']]['payloads'] for _ in history]))
                            if history[-1] != value['entry']:
                                history.append(copy.deepcopy(value['entry']))
                                payload_history.append(copy.deepcopy(value['payloads']))
                            value['history'] = history
                            value['history_payloads'] = payload_history
                result.append(record)
        result.extend(dict(family='project_artifact',id=sha,document=decl) for sha,decl in capture._artifacts.items())
        decode_records(_composed(before_records,result), artifacts=_CapturedEvidence(capture))
        for sha,raw in capture._pending_payloads.items():
            self.session.artifacts.publish_bytes(raw,capture._artifacts[sha],maximum_bytes=32*1024*1024)
        return result

    def outcome(self, outcome):
        if outcome not in ('committed','rolled_back','unknown'):
            raise ValueError('Invalid producer transaction outcome.')
        for values in self._dirty.values():values.clear()
        if self._runtime_data is not None:
            self.data.finish_runtime_mutation()
        self._runtime_data = None
        if outcome == 'unknown' or not self.session.available:
            self._fenced = True
            # Unknown acknowledgement fences authority. It never authorizes an
            # unacknowledged cancellation signal to a current worker.
        if outcome == 'committed':
            records = self.session.snapshot['records']
            self.archive._records = copy.deepcopy([r for r in records if r['family'] in FAMILIES])
            declarations = _declarations(records)
            self.archive._artifacts = {sha:declarations[sha] for sha in _referenced_artifacts(self.archive._records)}

    def _ack(self, family, producer_id, action):
        return dict(format='project_producer_action_v1',family=family,
                    origin_catalog_id=self.db.dataset_id,producer_id=producer_id,action=action)

    def _mutate(self, action, family, producer_id, body, checkpoint, key, invoke, *, scope='edit'):
        return self.session.mutate('producers.'+action,producer_id,dict(family=family,document=body),checkpoint,key,
            invoke,lambda result,before:dict(records=[],result=result),scope=scope)

    def _dispatch_prepared(self, family, owner, job):
        try:
            # Host-local custody must be durable before any worker can perform
            # capability discovery or inference. Saved project receipts cannot
            # recreate this registration or launch a worker.
            self.execution.register_producer(family,job['id'],job['admission_id'],job['request_digest'])
            self._journaled.add((family,job['id']))
            self.execution.producer_effect_intent(family,job['id'])
            with self._custody_lock:
                owner._project_worker_id=job['id']
                owner._launch(job)
        except BaseException:
            self._fenced=True
            self.session.available=False
            raise

    def _settle_drained(self):
        if not self.session.available:
            return
        records=self.session.snapshot['records']
        for family,owner in self._owners.items():
            producer_id=getattr(owner,'_project_worker_id',None)
            identity_key=(family,producer_id)
            if identity_key not in self._journaled or owner.worker is not None and owner.worker.is_alive():
                continue
            doc=next((r['document'] for r in records if r['family']==family and r['id']==self.db.dataset_id+'.'+producer_id),None)
            if doc is None or doc['job']['status'] in ('preparing','generating','stopping'):
                continue
            job=doc['job'];outcome=job.get('provider_outcome')
            entries=[v['entry'] for v in doc.get('entries',[])]
            batches=[v['batch'] for v in doc.get('prompt_batches',[])]
            if (outcome=='unknown' or any(e.get('provider_outcome')=='unknown' for e in entries)
                    or any(b['status']=='requesting' for b in batches)):
                outcome='unknown'
            elif (outcome=='result_received' or any(e.get('provider_outcome')=='result_received' for e in entries)
                    or any(b['response_sha256'] is not None for b in batches)):
                outcome='result_received'
            else:
                # Every effectful request is preceded by canonical uncertainty;
                # a terminal job with no such request is known not admitted.
                outcome='not_admitted'
            observation=(outcome,True,self.session.snapshot['checkpoint'])
            if self._journal_observations.get(identity_key)!=observation:
                self.execution.update_producer_outcome(family,producer_id,outcome,True)
                self._journal_observations[identity_key]=observation
            if outcome!='unknown':self._journaled.discard(identity_key)

    def start(self, family, body, expected_checkpoint, key):
        self._family(family)
        if family == 'generation_history':
            shape(body, {'server_url','model','prompt','count','strategy','session_id'},
                  {'width','height','seed','protocol','profile','prompt_url','prompt_model','book_id','split'})
        self.runtime_access.require('execute','producers.start',owner_only=True)
        prepared = []
        def invoke():
            requested = body.get('request_id') if type(body) is dict else None
            if requested is not None and any(r['family']==family and r['id']==self.db.dataset_id+'.'+requested for r in self.session.snapshot['records']):
                if self.db.execute('SELECT id FROM '+TABLES[family]+' WHERE id=%s',(requested,)).fetchone() is None:
                    raise WorkbenchError('A retained producer identity cannot acquire current admission. Start with a new identity.','unavailable',409)
            owner = self._owner(family)
            job, launch = owner._prepare_start(body)
            if launch:prepared.append((owner,copy.deepcopy(job)))
            return self._ack(family,job['id'],'start')
        with self.session.access.lock, self.session.lock, self.db.lock:
            self._settle_drained()
            result = self._mutate('start',family,None,body,expected_checkpoint,key,invoke,scope='execute')
            # Replays never invoke preparation. Unknown/failed commits never reach
            # this line. Hold custody locks until the local worker is installed.
            for owner,job in prepared:
                self._dispatch_prepared(family,owner,job)
            return result

    def resume_generation(self, producer_id, expected_checkpoint, key):
        identity(producer_id)
        self.runtime_access.require('execute','producers.resume',owner_only=True)
        prepared=[]
        def invoke():
            self._refuse_unknown_provider()
            owner=self._owners.get('generation_history')
            if owner is None:
                raise WorkbenchError('Only a current local generation queue can continue. Imported history is inert.','unavailable',409)
            job,launch=owner._prepare_resume(producer_id)
            if launch:prepared.append((owner,copy.deepcopy(job)))
            return self._ack('generation_history',producer_id,'resume')
        with self.session.access.lock,self.session.lock,self.db.lock:
            self._settle_drained()
            result=self._mutate('resume','generation_history',producer_id,{},expected_checkpoint,key,invoke,scope='execute')
            for owner,job in prepared:
                self._dispatch_prepared('generation_history',owner,job)
            return result

    def _decision(self, action, family, producer_id, body, checkpoint, key):
        self._family(family);identity(producer_id)
        self.runtime_access.require('edit','producers.'+action,producer_id)
        def invoke():
            owner=self._owners.get(family)
            if owner is None:
                raise WorkbenchError('Imported producer history cannot be applied as current authority.','unavailable',409)
            operation={'grounded_history':'data.runtime_grounded_text','caption_proposal_history':'data.runtime_caption',
                       'text_proposal_history':'data.runtime_text_classification'}[family]
            with self.data.runtime_mutation(operation,key):
                self._runtime_data=(operation,key)
                if action=='review':owner.review(producer_id,body)
                else:owner.decide(producer_id,body)
            return self._ack(family,producer_id,action)
        return self._mutate(action,family,producer_id,body,checkpoint,key,invoke)

    def review_grounded(self, producer_id, body, expected_checkpoint, key):
        return self._decision('review','grounded_history',producer_id,body,expected_checkpoint,key)

    def decide(self, family, producer_id, body, expected_checkpoint, key):
        if family not in ('caption_proposal_history','text_proposal_history'):
            raise WorkbenchError('Only caption/classification proposals accept a decision.')
        return self._decision('decide',family,producer_id,body,expected_checkpoint,key)

    def cancel(self, family, producer_id, expected_checkpoint, key, *, drain_timeout=10):
        self._family(family);identity(producer_id)
        self.runtime_access.require('cancel','producers.cancel',producer_id)
        if getattr(self.db.lock,'owned_by_current_thread',False):
            raise WorkbenchError('Cancellation must signal and drain outside project command locks.','producer_active',409)
        prepared=[]
        def invoke():
            owner=self._owners.get(family)
            if owner is None:
                raise WorkbenchError('No current local producer custody exists for this history.','unavailable',409)
            _result,pending=owner._prepare_cancel(producer_id)
            if pending is not None:prepared.append((owner,pending))
            return self._ack(family,producer_id,'cancel')
        result=self._mutate('cancel',family,producer_id,{},expected_checkpoint,key,invoke,scope='cancel')
        # A replay never invokes preparation. Failure or uncertain COMMIT never
        # reaches this point, and therefore never stops transport or a worker.
        for owner,pending in prepared:
            with self._custody_lock:
                signalled=owner._signal_cancel(pending)
            # The image transport owner audits through host/SQL locks. Never
            # hold the custody mutex while entering those ordered guards.
            if signalled and family=='generation_history':owner._cancel_transport(pending)
            worker=pending[0]
            if worker is not None:
                worker.join(drain_timeout)
                if worker.is_alive():
                    raise WorkbenchError('Cancellation intent is saved; current worker has not drained.','producer_draining',409)
        return result

    def _refuse_unknown_provider(self):
        for family in self._owners:
            for raw, in self.db.execute('SELECT data FROM '+TABLES[family]):
                job=json.loads(raw)
                if (job.get('provider_outcome')=='unknown'
                        or any(v['status']=='requesting' for v in job.get('prompt_batches',[]))):
                    raise WorkbenchError('Downstream producer outcome is unknown; local drainage is not provider cessation.','outcome_unknown',409)
                if family=='generation_history':
                    if any(json.loads(row[0]).get('provider_outcome')=='unknown' for row in self.db.execute('SELECT data FROM generation_entries WHERE job_id=%s',(job['id'],))):
                        raise WorkbenchError('Image provider outcome is unknown.','outcome_unknown',409)

    def abandon_pending(self):
        if not getattr(self.execution,'_reconstructing',False):
            raise RuntimeError('Pending producer facts can be abandoned only by explicit current reconstruction.')
        for owner in self._owners.values():
            if owner.worker is not None and owner.worker.is_alive():
                raise WorkbenchError('Actual local producer custody has not drained.','producer_active',409)
        self._refuse_unknown_provider()
        for values in self._dirty.values():values.clear()
        self.data.finish_runtime_mutation()
        self._runtime_data=None
        self._fenced=False

    def assert_quiescent(self):
        if not self.has_local_custody:
            return
        self._settle_drained()
        for family,owner in self._owners.items():
            if owner.worker is not None and owner.worker.is_alive():
                raise WorkbenchError('Stop and drain the current producer before changing project.','producer_active',409)
            self._refuse_unknown_provider()
            for raw, in self.db.execute('SELECT data FROM '+TABLES[family]):
                job=json.loads(raw)
                if job['status'] in ('preparing','generating','stopping') or job.get('provider_outcome')=='unknown':
                    raise WorkbenchError('Current producer is active or its provider outcome is unknown.','producer_active',409)

    def close(self):
        # Project lifecycle refuses active/unknown custody; it never turns Close
        # into an implicit cancellation or recovery instruction.
        self.assert_quiescent()

    @property
    def has_local_custody(self):
        return bool(self._owners)

    def shutdown(self):
        """Explicit application shutdown drains only actual constructed owners.

        Historical rows, process IDs and endpoints never select a custodian.
        Shutdown is separate from ordinary project Close, which refuses work.
        """
        if getattr(self.db.lock,'owned_by_current_thread',self.db.lock.depth) or self.db.in_transaction:
            raise WorkbenchError('Producer shutdown must drain outside project command locks.','producer_active',409)
        for owner in self._owners.values():
            with self.runtime_access._reconcile():owner.close()
        with self.runtime_access._reconcile():self._settle_drained()

    def status(self, *, offset=0, limit=40):
        if type(offset) is not int or not 0<=offset<=1_000_000 or type(limit) is not int or not 1<=limit<=40:
            raise WorkbenchError('Invalid current producer health page.')
        with self.session.access.lock,self.session.lock,self.db.lock:
            self.session.access.require('inspect','producers.health')
            self.session.check()
            self._settle_drained()
            items=[]
            for family,owner in self._owners.items():
                for raw, in self.db.execute('SELECT data FROM '+TABLES[family]+' ORDER BY ordinal'):
                    job=json.loads(raw)
                    observed=job.get('provider_outcome')
                    if any(v['status']=='requesting' for v in job.get('prompt_batches',[])):observed='unknown'
                    if family=='generation_history' and any(json.loads(row[0]).get('provider_outcome')=='unknown' for row in self.db.execute('SELECT data FROM generation_entries WHERE job_id=%s',(job['id'],))):observed='unknown'
                    items.append(dict(family=family,producer_id=job['id'],status=job['status'],
                                      provider_outcome=observed,worker_alive=bool(owner.worker
                                      and owner.worker.is_alive() and getattr(owner,'_project_worker_id',None)==job['id'])))
            return dict(format='project_producer_health_v1',items=items[offset:offset+limit],total=len(items),
                        offset=offset,limit=limit,fenced=bool(self._fenced or self.runtime_access.catalog_id==self.session.access.catalog_id or any(v['provider_outcome']=='unknown' for v in items)))
