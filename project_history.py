"""Inert project Study, lineage and Run facts, with owner-shared validation.

Historical identity is always (origin catalog, original ID). No imported fact is
inserted into a worker, admission, grant or request replay table. The optional
SQL connection is only a query engine for bounded supplied immutable JSON.
"""
import base64
import copy
import hashlib
import re
import uuid

import agent_api

from experiments import (DIMENSIONS, Experiments, budget, request_key,
    select_retained_checkpoint, reservation_totals, validate_candidate_evidence, new_study_document, edit_study_document, new_trial_document, new_candidate_document, validate_retained_candidate,
    validate_retained_policy, validate_retained_reservation,
    validate_retained_study, validate_retained_trial)
from experiment_lineage import (INTENT_LIMIT, validate_retained_ancestry,
    validate_retained_intent, validate_retained_lineage)
from model_definitions import checked_json, natural, reference, text
from pipeline import closed, digest, identifier, model_aware_graph, source_content_hash
from project_session import operation_records
from projects import relative_path
from runs import (ACTIVE, TERMINAL, TEST_FILES, MAX_ARTIFACT_BYTES, validate_retained_run,
                  project_run_projection, public_run_projection, artifact_capture_source, validate_external_artifact_inventory)
from workbench import WorkbenchError, timestamp

FAMILY_FORMATS = {
    'study_history': 'project_study_history_v1',
    'trial_history': 'project_trial_history_v1',
    'run_history': 'project_run_history_v1',
    'candidate_history': 'project_candidate_history_v1',
}
MAX_HISTORY_BYTES = 40 * 1024**2
MAX_HISTORY_RECORDS = 100_000
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$')
SHA = re.compile(r'^[a-f0-9]{64}$')

OPERATIONS = frozenset(('studies.create','studies.save','studies.prepare_trial','studies.record_lineage',
    'studies.branch_trial','studies.prepare_branch','studies.select_candidate','studies.prepare_package',
    'studies.prepare_verifier','studies.continue','studies.stop'))


def _invalid(message, code='invalid'):
    raise WorkbenchError(message, code, 409)


def _shape(value, fields, name):
    if type(value) is not dict or set(value) != set(fields):
        _invalid('Invalid '+name+' fields.')


def _items(value, name, maximum=10000):
    if type(value) is not list or len(value)>maximum:
        _invalid(name+' must be a bounded list.')
    return value


def _sha(value):
    if type(value) is not str or not SHA.fullmatch(value):
        _invalid('Historical digest must be an exact SHA256.')
    return value


def envelope(family, origin, identity, document):
    identifier(origin,'Origin catalog');identifier(identity,'Historical identity')
    return {'family':family,'id':origin+'.'+identity,'document':document}


def _audit(facts):
    """Retain classified scientific audit facts, never arbitrary access payloads."""
    for fact in _items(facts,'Scientific audit',100000):
        _shape(fact,('actor_id','action','target','details','result','occurred_at'),'scientific audit')
        if fact['actor_id'] is not None:identifier(fact['actor_id'],'Historical actor')
        action=fact['action'];details=fact['details']
        text(fact['occurred_at'],'Audit time',80);identifier(fact['target'],'Audit target')
        allowed=OPERATIONS|{'studies.admit','studies.approve','studies.reconcile','studies.candidate_selected','studies.lineage.record',
            'runs.admit','runs.admit_external','runs.update','runs.reconcile','runs.expose_test'}
        if action not in allowed:_invalid('Unclassified historical scientific audit action.','unsupported')
        if fact['result'] in ('denied','failed'):
            closed(details,('code',))
            if details['code'] not in ('invalid','unavailable','unsupported','stale','conflict','not_found','denied',
                    'forbidden','unknown','failed','cancelled','busy','interrupted'):_invalid('Unclassified historical failure code.')
            continue
        if fact['result'] not in ('success','interrupted'):_invalid('Unsupported historical audit result.')
        keys=set(details) if type(details) is dict else set()
        if action=='studies.create':
            closed(details,('policy_sha256','limits'));_sha(details['policy_sha256']);budget(details['limits'])
        elif action in ('studies.save','studies.continue','studies.stop'):
            if keys not in ({'revision'},{'revision','epoch'}):_invalid('Unclassified Study transition audit.')
        elif action=='studies.reconcile':
            if keys not in ({'revision','epoch'},{'state'}):_invalid('Unclassified Study recovery audit.')
        elif action=='studies.prepare_trial':
            if keys not in ({'trial_id'},{'trial_id','revision','epoch'}):_invalid('Unclassified Trial preparation audit.')
        elif action=='studies.admit':closed(details,('run_id','reservation_id','request_sha256','revision','epoch'))
        elif action=='studies.approve':closed(details,('trial_id','material_sha256','approval_id'))
        elif action=='studies.select_candidate':
            if keys not in ({'study_id','run_id','checkpoint_sha256'},{'study_id','run_id','checkpoint_sha256','decision'}):
                _invalid('Unclassified candidate selection audit.')
            if 'decision' in details and details['decision'] not in ('diagnostic','qualified'):_invalid('Invalid decision audit.')
        elif action=='studies.candidate_selected':closed(details,('candidate_id','revision','epoch'))
        elif action=='studies.lineage.record':
            if keys not in ({'intent_sha256'},{'material_sha256','intent_sha256'}):_invalid('Unclassified lineage audit.')
        elif action in ('studies.prepare_package','studies.prepare_verifier'):closed(details,('study_id','trial_id','material_sha256'))
        elif action=='runs.admit':closed(details,('request_sha256','graph_sha256','release_sha256'))
        elif action=='runs.admit_external':closed(details,('material_sha256','approved_material_sha256','approval_id','request_sha256'))
        elif action in ('runs.update','runs.reconcile'):
            if keys not in ({'state','request_sha256','graph_sha256','release_sha256'},
                    {'state','request_sha256','graph_sha256','material_sha256','approval_id','custody_phase','receipt_sha256'}):
                _invalid('Unclassified Run observation audit.')
        elif action=='runs.expose_test':closed(details,('event_id','release_sha256','reason'))
        else:_invalid('Unclassified historical scientific audit details.','unsupported')
        for key,value in details.items():
            if key.endswith('_sha256') and value is not None:_sha(value)
            elif key.endswith('_id') and value is not None:identifier(value,key)
            elif key in ('revision','epoch'):natural(value,key,1 if key=='revision' else 0)
            elif key=='state' and value not in set(ACTIVE)|set(TERMINAL)|{'open','stopping','stopped'}:_invalid('Invalid historical state audit.')
            elif key=='custody_phase' and value not in ('prepared','barrier_ready','go_intent','drained'):_invalid('Invalid custody audit.')
            elif key=='reason':text(value,'Disclosure reason',1000)


def _operations(facts, catalog_id):
    seen=set()
    for fact in _items(facts,'Historical operations',100000):
        _shape(fact,('actor_id','operation_id','request_key','request_sha256','result'),'historical operation')
        identifier(fact['actor_id'],'Historical actor');request_key(fact['request_key']);_sha(fact['request_sha256'])
        if fact['operation_id'] not in OPERATIONS:
            _invalid('Unsupported historical operation.','unsupported')
        key=(fact['actor_id'],fact['operation_id'],fact['request_key'])
        if key in seen:_invalid('Duplicate historical operation fact.')
        seen.add(key);checked_json(fact['result'])
        if not validate_operation_result(fact['operation_id'],fact['result']):
            _invalid('Unclassified historical operation result.','unsupported')


def _payloads(edges):
    result={}
    for edge in _items(edges,'Historical payloads',100000):
        _shape(edge,('name','blob','population','role','preservation','required_for'),'historical payload')
        name=edge['name']
        relative_path(name)
        if name in result:
            _invalid('Unsafe or duplicate historical payload name.')
        _shape(edge['blob'],('sha256','bytes'),'payload byte identity')
        _sha(edge['blob']['sha256']);natural(edge['blob']['bytes'],'Payload bytes')
        if edge['population'] not in ('train','validation','test','unknown'):
            _invalid('Unsupported historical payload population.')
        if edge['preservation'] not in ('unique','regenerable'):
            _invalid('Unsupported payload preservation meaning.')
        text(edge['role'],'Payload role',120)
        for use in _items(edge['required_for'],'Payload required uses',64):text(use,'Required use',120)
        result[name]=edge
    return result


def _approval(proof, run):
    """Validate exact old associations; return only the common proof projection."""
    if proof is None:return None
    _shape(proof,('grant','consumption','admission'),'historical admission proof')
    grant,consumption,admission=proof['grant'],proof['consumption'],proof['admission']
    if grant is not None:
        _shape(grant,('id','catalog_id','approver_actor_id','approver_credential_id','consumer_actor_id',
            'material_sha256','created_at','expires_at','revoked_at'),'historical approval')
        for key in ('id','catalog_id','approver_actor_id','approver_credential_id','consumer_actor_id'):
            identifier(grant[key],key)
        _sha(grant['material_sha256'])
        for key in ('created_at','expires_at'):natural(grant[key],key)
        if grant['expires_at']<=grant['created_at']:_invalid('Historical approval lifetime differs.')
        if grant['revoked_at'] is not None:natural(grant['revoked_at'],'Revocation time')
    if consumption is not None:
        _shape(consumption,('grant_id','run_id','admission_id','consumer_credential_id','request_sha256','consumed_at'),
               'historical approval consumption')
        for key in ('grant_id','run_id','admission_id','consumer_credential_id'):identifier(consumption[key],key)
        _sha(consumption['request_sha256']);natural(consumption['consumed_at'],'Consumption time')
    if admission is not None:
        _shape(admission,('id','catalog_id','actor_id','credential_id','kind','job_id','request_digest','effects','created_at'),
               'historical admission')
        for key in ('id','catalog_id','actor_id','credential_id','job_id'):identifier(admission[key],key)
        _sha(admission['request_digest']);natural(admission['created_at'],'Admission time')
        if (admission['kind']!='runs' or admission['id']!=run['admission_id'] or admission['catalog_id']!=run['dataset_id'] or
                admission['job_id']!=run['id'] or admission['request_digest']!=run['request_sha256']):
            _invalid('Historical admission differs from its Run.')
        # These are original closed owner-emitted effect observations, never
        # capabilities. Unknown action/target text cannot enter this proof.
        if run.get('execution_kind')=='external_recipe':
            expected={'runs.update':[run['id']]}
        else:
            recipe=run['graph'].get('recipe','image_classification')
            expected={'pipeline.inspect_release':[run['release_id']],
                'dataset_releases.locate':[run['release_id']],'pipeline.probe':[recipe],
                'pipeline.probe_native':[recipe],'pipeline.definition_identity':[recipe],
                'pipeline.exposures':[None],'runs.update':[run['id']]}
        if admission['effects']!=expected:_invalid('Unclassified historical admission effects.','unsupported')
    if grant is None and consumption is None:return None
    if grant is None or consumption is None or admission is None:
        _invalid('Historical approval proof is incomplete.')
    if (grant['id']!=run.get('approval_id') or consumption['grant_id']!=grant['id'] or
            consumption['run_id']!=run['id'] or consumption['admission_id']!=admission['id'] or
            consumption['request_sha256']!=run['request_sha256'] or
            consumption['consumer_credential_id']!=admission['credential_id'] or
            admission['actor_id']!=grant['consumer_actor_id']):
        _invalid('Historical approval consumption association differs.')
    return dict(material_sha256=grant['material_sha256'],consumer_actor_id=grant['consumer_actor_id'],
        catalog_id=grant['catalog_id'],run_id=consumption['run_id'],admission_id=consumption['admission_id'],
        request_sha256=consumption['request_sha256'])


def capture_run(run, *, admission_proof=None, payloads, publication=None):
    """Create an inert evidence projection; reject unknown source fields."""
    # Continuation state has its own closed evidence shape, never a replayable
    # field in the saved Run consumed by recovery.
    if publication is None and run.get('publication_continuation') is not None:
        publication={'continuation':copy.deepcopy(run['publication_continuation']),'source':None,'result':None}
    value=project_run_projection(run)
    payloads=copy.deepcopy(payloads)
    if run.get('execution_kind')!='external_recipe' and not any(item['name']=='release.zip' for item in payloads):
        payloads.append({'name':'release.zip','blob':{'sha256':run['release_sha256'],'bytes':run['release_bytes']},
            'population':'unknown','role':'frozen_input','preservation':'unique','required_for':['input_proof','scientific_inspection']})
    doc=dict(format=FAMILY_FORMATS['run_history'],origin_catalog_id=run['dataset_id'],run=value,
             admission_proof=copy.deepcopy(admission_proof),payloads=copy.deepcopy(payloads),publication=copy.deepcopy(publication))
    return envelope('run_history',run['dataset_id'],run['id'],doc)


def payload_set_sha256(origin_catalog_id,run_id,payloads):
    """New disclosure identity, separate from every historical proof namespace."""
    identifier(origin_catalog_id,'Origin catalog');identifier(run_id,'Run ID')
    edges=_payloads(payloads)
    value={'format':'project_disclosure_payload_set_v1','origin_catalog_id':origin_catalog_id,'run_id':run_id,
           'payloads':[{'name':name,**edge['blob']} for name,edge in sorted(edges.items())]}
    return hashlib.sha256(agent_api.encoded(value)).hexdigest()


def validate_disclosure_fact(value):
    _shape(value,('format','origin_catalog_id','run_id','payload_set_sha256','population','reason','actor_id','occurred_at'),
           'historical disclosure observation')
    if value['format']!='project_disclosure_v1' or value['population']!='all':
        _invalid('Unsupported historical disclosure observation.','unsupported')
    for key in ('origin_catalog_id','run_id','actor_id'):identifier(value[key],key)
    _sha(value['payload_set_sha256']);text(value['reason'],'Disclosure reason',1000)
    text(value['occurred_at'],'Disclosure observation time',80)
    return copy.deepcopy(value)


def declarations(record):
    if record['family']!='run_history':return []
    values={}
    edges=list(record['document']['payloads'])
    publication=record['document']['publication']
    blobs=[edge['blob'] for edge in edges]
    if publication is not None:blobs.extend(publication[key] for key in ('source','result') if publication[key] is not None)
    for blob in blobs:
        value={'format':'project_artifact_v1',**blob}
        if blob['sha256'] in values and values[blob['sha256']]['document']!=value:_invalid('Historical artifact declarations differ.')
        values[blob['sha256']]={'family':'project_artifact','id':blob['sha256'],'document':value}
    return list(values.values())


class HistoryFacts:
    def __init__(self):
        self.studies={};self.trials={};self.runs={};self.candidates={};self.policies={};self.reservations={}

    def trial_ref(self, value):
        _shape(value,('catalog_id','trial_id','material_sha256'),'historical Trial reference')
        key=(value['catalog_id'],value['trial_id'])
        if key not in self.trials:_invalid('Historical Trial dependency is missing.','unavailable')
        trial=self.trials[key]['trial']
        if value['material_sha256']!=trial['material']['sha256']:_invalid('Historical Trial material differs.')
        return trial


def _decode_records(records, *, materials=None, artifacts=None):
    """Validate finite owned families and complete metadata closure before effects.

    Declared but absent payload bytes are legitimate metadata. Semantic byte
    verification is explicit on use and cannot confer current permission.
    """
    if type(records) is not list:_invalid('Project records must be a list.')
    _items([record for record in records if type(record) is dict and record.get('family') in FAMILY_FORMATS],
           'Project history records',MAX_HISTORY_RECORDS)
    facts=HistoryFacts();declarations={}
    for record in records:
        if record.get('family')=='project_artifact':
            declarations[record['document']['sha256']]=record['document']
        family=record.get('family')
        if family not in FAMILY_FORMATS:continue
        _shape(record,('family','id','document'),'history envelope')
        doc=checked_json(record['document'],MAX_HISTORY_BYTES)
        if doc.get('format')!=FAMILY_FORMATS[family]:_invalid('Unsupported historical format.','unsupported')
        origin=doc.get('origin_catalog_id');identifier(origin,'Origin catalog')
        if family=='study_history':
            _shape(doc,('format','origin_catalog_id','study','memberships','policies','reservations','operations',
                        'revisions','audit','revision_history_complete'),'Study history')
            identity=doc['study'].get('id');target=facts.studies
        elif family=='trial_history':
            _shape(doc,('format','origin_catalog_id','trial','lineage'),'Trial history')
            identity=doc['trial'].get('id');target=facts.trials
        elif family=='run_history':
            _shape(doc,('format','origin_catalog_id','run','admission_proof','payloads','publication'),'Run history')
            identity=doc['run'].get('id');target=facts.runs
        else:
            _shape(doc,('format','origin_catalog_id','candidate'),'Candidate history')
            identity=doc['candidate'].get('id');target=facts.candidates
        identifier(identity,'Historical identity')
        if record['id']!=origin+'.'+identity or (origin,identity) in target:
            _invalid('Historical envelope identity differs or is duplicated.')
        target[(origin,identity)]=doc
    for (origin,identity),doc in facts.studies.items():
        policies={}
        for item in _items(doc['policies'],'Retained policies'):
            _shape(item,('ref','policy'),'historical policy')
            ref=reference(item['ref'],'selection_policy',origin);validate_retained_policy(item['policy'])
            if digest(item['policy'])!=ref['sha256']:_invalid('Historical selection policy digest differs.')
            key=(origin,ref['id'],ref['revision'],ref['sha256'])
            if key in policies or (key in facts.policies and facts.policies[key]!=item['policy']):
                _invalid('Historical selection policy is duplicated or contradictory.')
            policies[key]=item['policy'];facts.policies[key]=item['policy']
        memberships={}
        previous=[]
        for item in _items(doc['memberships'],'Study memberships'):
            _shape(item,('revision','trial_ids'),'historical membership')
            revision=natural(item['revision'],'Membership revision',1)
            if revision!=len(memberships)+1:_invalid('Historical membership revisions must be contiguous.')
            trials=_items(item['trial_ids'],'Historical trial members')
            if len(set(trials))!=len(trials) or trials[:len(previous)]!=previous:
                _invalid('Historical immutable membership changed or repeats a Trial.')
            for trial_id in trials:identifier(trial_id)
            memberships[revision]={'trial_ids':trials};previous=trials
        revisions=_items(doc['revisions'],'Study revisions')
        if not revisions or type(doc['revision_history_complete']) is not bool:_invalid('Study revision history is missing.')
        last_revision=0
        for study in revisions:
            if study.get('id')!=identity or study.get('revision',0)<=last_revision:_invalid('Study revision sequence differs.')
            ref=study['policy'];policy=policies.get((origin,ref['id'],ref['revision'],ref['sha256']))
            if policy is None:_invalid('Study policy closure is missing.','unavailable')
            validate_retained_study(study,catalog_id=origin,membership=memberships.get(study['membership_revision']),policy=policy)
            last_revision=study['revision']
        if revisions[-1]!=doc['study']:_invalid('Current Study differs from its revision stream.')
        if doc['revision_history_complete'] and [item['revision'] for item in revisions]!=list(range(1,last_revision+1)):
            _invalid('Complete Study history has a revision gap.')
        _audit(doc['audit']);_operations(doc['operations'],origin)
        for reservation in _items(doc['reservations'],'Study reservations'):
            if reservation.get('study_id')!=identity:_invalid('Historical reservation belongs to another Study.')
            key=(origin,reservation.get('run_id'))
            if key in facts.reservations:_invalid('Run has duplicate historical reservation associations.')
            facts.reservations[key]=reservation
    for (origin,identity),doc in facts.trials.items():
        trial=validate_retained_trial(doc['trial'],catalog_id=origin)
        study=facts.studies.get((origin,trial['study_id']))
        if study is None or identity not in study['study']['trial_ids']:_invalid('Historical Trial membership is missing.','unavailable')
        if materials is None:_invalid('Historical material decoder is unavailable.','unavailable')
        materials.recipe(trial['material'])
        if doc['lineage'] is not None:validate_retained_lineage(doc['lineage'],trial=trial,resolve=facts.trial_ref)
    for (origin,_identity),doc in facts.studies.items():
        for trial_id in doc['study']['trial_ids']:
            if (origin,trial_id) not in facts.trials:_invalid('Study contains a missing Trial.','unavailable')
    for (origin,identity),doc in facts.trials.items():
        parent=(doc['lineage']['intent']['parent'] or {}).get('trial_id') if doc['lineage'] else None
        def parent_of(trial_id):
            record=facts.trials.get((origin,trial_id))
            if record is None:_invalid('Historical ancestor is missing.','unavailable')
            return (record['lineage']['intent']['parent'] or {}).get('trial_id') if record['lineage'] else None
        validate_retained_ancestry(identity,parent,parent_of=parent_of)
    for (origin,identity),doc in facts.runs.items():
        run=project_run_projection(doc['run'],imported=True)
        if run.get('dataset_id')!=origin:_invalid('Historical Run origin differs.')
        edges=_payloads(doc['payloads'])
        for edge in edges.values():
            declaration=declarations.get(edge['blob']['sha256'])
            if declaration!={'format':'project_artifact_v1',**edge['blob']}:
                _invalid('Historical artifact declaration is missing or contradictory.','unavailable')
        for item in run.get('artifacts',[]):
            edge=edges.get(item.get('name'))
            if edge is None or edge['blob']!={key:item[key] for key in ('sha256','bytes')}:
                _invalid('Run artifact closure differs.','unavailable')
        if run.get('execution_kind')=='external_recipe':
            for name,item in run['material']['captures'].items():
                edge=edges.get(name)
                if edge is None or edge['blob']!={key:item[key] for key in ('sha256','bytes')}:
                    _invalid('Historical execution capture closure is missing or differs.','unavailable')
            descriptor=run['material'].get('torch_runtime',run['material'].get('cpu_snapshot'))
            if descriptor is not None:
                sha=digest(descriptor)
                if materials is None:_invalid('Historical runtime decoder is unavailable.','unavailable')
                materials.runtime({'kind':'runtime','catalog_id':origin,'id':sha,'sha256':sha})
            if run['state']=='completed':
                receipt=edges.get('custody-receipt.json')
                if receipt is None or receipt['blob']['sha256']!=run['custody_receipt_sha256']:
                    _invalid('Historical custody receipt declaration is missing or differs.','unavailable')
                if 'artifact-manifest.json' not in edges:
                    _invalid('Historical artifact manifest declaration is missing.','unavailable')
        else:
            release=edges.get('release.zip')
            if release is None or release['blob']!={'sha256':run['release_sha256'],'bytes':run['release_bytes']}:
                _invalid('Historical frozen input Release declaration is missing or differs.','unavailable')
        reservation=facts.reservations.get((origin,identity));association=None;composition=None
        if reservation is not None:
            trial=facts.trials.get((origin,reservation['trial_id']))
            if trial is None:_invalid('Reservation Trial is missing.','unavailable')
            association={key:reservation[key] for key in ('study_id','trial_id','actor_id','request_sha256','material_sha256')}
            composition=materials.recipe(trial['trial']['material'])
        elif run.get('approval_material_sha256') is not None:
            sha=run['approval_material_sha256']
            composition=materials.recipe({'kind':'recipe_material','catalog_id':origin,'id':sha,'sha256':sha})
        approval=_approval(doc['admission_proof'],run)
        # This validates the stored context/spec binding. Exact static context
        # is rederived from retained source bytes on explicit evidence use.
        validate_retained_run(run,catalog_id=origin,run_id=identity,request_key=run['request_key'],
            request_sha256=run['request_sha256'],association=association,approval=approval,composition=composition,
            extension_context=run.get('extension_context'))
        parent=run.get('parent_run_id')
        if parent is not None and (origin,parent) not in facts.runs:_invalid('Retry parent Run is missing.','unavailable')
        if run.get('execution_kind')=='external_recipe':
            for item in run['material']['inputs'].values():
                if item.get('kind')=='run_artifact':
                    source=item['source'];producer=facts.runs.get((source['catalog_id'],source['run_id']))
                    if producer is None:_invalid('Producer Run closure is missing.','unavailable')
                    match=[edge for edge in producer['payloads'] if edge['name']==source['artifact_name']]
                    if len(match)!=1 or match[0]['blob']!={'sha256':source['measured_sha256'],'bytes':source['artifact_bytes']}:
                        _invalid('Producer Run input byte identity differs.')
        publication=doc['publication']
        if publication is not None:
            _shape(publication,('continuation','source','result'),'publication history')
            from run_publication import validate_continuation
            historical=dict(run,publication_continuation=publication['continuation'])
            validate_continuation(historical)
            for key in ('source','result'):
                if publication[key] is not None:
                    _shape(publication[key],('sha256','bytes'),'publication byte reference')
                    if declarations.get(publication[key]['sha256'])!={'format':'project_artifact_v1',**publication[key]}:
                        _invalid('Historical publication byte declaration is missing.','unavailable')
    def visit_run(key,path):
        if key in path:_invalid('Cyclic historical Run ancestry or producer inputs.')
        if len(path)>=64:_invalid('Historical Run ancestry exceeds its bound.','unsupported')
        run=facts.runs[key]['run'];next_path=path|{key}
        if run.get('parent_run_id') is not None:visit_run((key[0],run['parent_run_id']),next_path)
        if run.get('execution_kind')=='external_recipe':
            for item in run['material']['inputs'].values():
                if item.get('kind')=='run_artifact':
                    source=item['source'];visit_run((source['catalog_id'],source['run_id']),next_path)
    for key in facts.runs:visit_run(key,set())
    for (origin,_identity),reservation in facts.reservations.items():
        trial=facts.trials[(origin,reservation['trial_id'])]['trial']
        run=facts.runs.get((origin,reservation['run_id']))
        if run is None:_invalid('Historical reservation Run is missing.','unavailable')
        validate_retained_reservation(reservation,trial=trial,composition=materials.recipe(trial['material']),run=run['run'])
    for (origin,_identity),doc in facts.candidates.items():
        value=doc['candidate'];trial=facts.trials.get((origin,value.get('trial_id')))
        reservation=facts.reservations.get((origin,value.get('run_id')))
        if trial is None or reservation is None:_invalid('Candidate dependency closure is missing.','unavailable')
        ref=value['policy'];policy=facts.policies.get((origin,ref['id'],ref['revision'],ref['sha256']))
        if policy is None:_invalid('Candidate policy closure is missing.','unavailable')
        validate_retained_candidate(value,catalog_id=origin,trial=trial['trial'],policy=policy,reservation=reservation)
    for (origin,_),doc in facts.studies.items():
        for operation in doc['operations']:
            validate_operation_result(operation['operation_id'],operation['result'],records)
    validate_data_exposures(records,facts)
    for record in records:
        if record.get('family')=='project_operation':
            value=record['document'];validate_operation_result(value['operation'],value['result'],records)
    return facts


def decode_records(records, *, materials=None, artifacts=None):
    try:
        return _decode_records(records,materials=materials,artifacts=artifacts)
    except WorkbenchError:
        raise
    except (KeyError,TypeError,ValueError,AttributeError,RecursionError):
        _invalid('Invalid or incomplete project history document.')


def _validate_operation_shape(operation,result):
    if operation=='history.disclose':
        validate_disclosure_fact(result);return True
    if operation in ('studies.create','studies.save'):
        closed(result,('format','id','revision','name','admission_epoch','open','state','limits','policy',
                       'membership_revision','trial_ids','stop_receipt_id'))
        if result['format']!='study_v1':_invalid('Historical Study operation result differs.')
        identifier(result['id']);natural(result['revision'],'Study revision',1);budget(result['limits'])
        reference(result['policy'],'selection_policy',result['policy']['catalog_id'])
        return True
    if operation in ('studies.prepare_trial','studies.prepare_branch'):
        validate_retained_trial(result,catalog_id=result['material']['catalog_id']);return True
    if operation=='studies.record_lineage':
        closed(result,('format','trial','intent','actor_id','recorded_at','timing'))
        if result['format']!='trial_lineage_v1':_invalid('Historical lineage operation result differs.')
        return True
    if operation=='studies.select_candidate':
        closed(result,('ref','candidate','run_id','checkpoint'))
        ref=reference(result['ref'],'candidate',result['ref']['catalog_id'])
        if (ref['sha256']!=digest(result['candidate']) or ref['id']!=result['candidate']['id'] or
                result['run_id']!=result['candidate']['run_id'] or result['checkpoint']['sha256']!=result['candidate']['checkpoint_sha256']):
            _invalid('Historical candidate operation identity differs.')
        return True
    if operation=='studies.continue':
        return _validate_operation_shape('studies.save',result)
    if operation=='studies.stop':
        closed(result,('study_id','stop_receipt_id','admission_epoch','run_ids'))
        identifier(result['study_id']);identifier(result['stop_receipt_id']);natural(result['admission_epoch'],'Admission epoch')
        for run_id in _items(result['run_ids'],'Stopped Run ids'):identifier(run_id)
        return True
    if operation in ('studies.prepare_package','studies.prepare_verifier'):
        from candidate_packages import decode_preparation_receipt
        origin=result['trial']['material']['catalog_id']
        decode_preparation_receipt(operation,result,catalog_id=origin,
            validate_trial=lambda value:validate_retained_trial(value,catalog_id=origin))
        return True
    if operation=='studies.branch_trial':
        from pipeline import decode_graph
        closed(result,('request_key','graph','model','parent','intent','study_id','source'))
        request_key(result['request_key']);decode_graph(result['graph']);identifier(result['study_id'])
        reference(result['model'],'model',result['model']['catalog_id'])
        closed(result['source'],('id','revision','material'));identifier(result['source']['id'])
        natural(result['source']['revision'],'Source graph revision',1)
        reference(result['source']['material'],'recipe_material',result['model']['catalog_id'])
        closed(result['parent'],('catalog_id','trial_id','material_sha256'))
        identifier(result['parent']['catalog_id']);identifier(result['parent']['trial_id']);_sha(result['parent']['material_sha256'])
        if result['intent']['parent']!=result['parent']:_invalid('Branch parent differs from retained intent.')
        # Exact lineage intent is checked with the complete Trial closure below.
        def ref(value):
            closed(value,('catalog_id','trial_id','material_sha256'))
            identifier(value['catalog_id']);identifier(value['trial_id']);_sha(value['material_sha256'])
        validate_retained_intent(result['intent'],resolve=ref)
        return True
    if operation=='studies.admit':
        # The legacy owner replays admission from reservations and never calls
        # _save_receipt for this operation. M3 must own any future publication
        # receipt; an invented public Run snapshot is not a portable v1 fact.
        _invalid('Portable admission operation receipts are unsupported; retain exact reservation and Run proof.','unsupported')
    return False


def _bind_operation_result(operation,result,records):
    def document(family,origin,identity):
        matches=[item['document'] for item in records if item.get('family')==family and item.get('id')==origin+'.'+identity]
        if len(matches)!=1:_invalid('Operation result has no unique canonical history fact.')
        return matches[0]
    if operation=='history.disclose':
        doc=document('run_history',result['origin_catalog_id'],result['run_id'])
        if result['payload_set_sha256']!=payload_set_sha256(doc['origin_catalog_id'],doc['run']['id'],doc['payloads']):
            _invalid('Disclosure observation does not identify the retained Run payload set.')
    elif operation in ('studies.create','studies.save'):
        doc=document('study_history',result['policy']['catalog_id'],result['id'])
        if result not in doc['revisions']:_invalid('Study operation result has no retained revision.')
    elif operation in ('studies.prepare_trial','studies.prepare_branch'):
        doc=document('trial_history',result['material']['catalog_id'],result['id'])
        if doc['trial']!=result:_invalid('Trial operation result has no retained Trial.')
    elif operation=='studies.record_lineage':
        ref=result['trial'];doc=document('trial_history',ref['catalog_id'],ref['trial_id'])
        if doc['lineage']!=result:_invalid('Lineage operation result has no retained sidecar.')
    elif operation=='studies.select_candidate':
        ref=result['ref'];doc=document('candidate_history',ref['catalog_id'],ref['id'])
        if doc['candidate']!=result['candidate']:_invalid('Candidate operation result has no retained decision.')
        run=document('run_history',ref['catalog_id'],result['run_id'])['run']
        checkpoint=result['checkpoint']
        if not any(all(item.get(key)==checkpoint.get(key) for key in ('name','sha256','bytes','media_type'))
                   for item in run['artifacts']):
            _invalid('Candidate operation checkpoint differs from its canonical Run artifact.')

    elif operation=='studies.continue':
        _bind_operation_result('studies.save',result,records)
    elif operation=='studies.stop':
        docs=[item['document'] for item in records if item.get('family')=='study_history'
              and item['document']['study']['id']==result['study_id']]
        matches=[doc for doc in docs if any(value['stop_receipt_id']==result['stop_receipt_id']
                  and value['admission_epoch']==result['admission_epoch'] for value in doc['revisions'])]
        if len(matches)!=1:_invalid('Stop receipt has no unique retained epoch fact.')
        members={value['run_id'] for value in matches[0]['reservations']}
        if not set(result['run_ids'])<=members:_invalid('Stop receipt references an unrelated Run.')
    elif operation in ('studies.prepare_package','studies.prepare_verifier'):
        origin=result['trial']['material']['catalog_id']
        _bind_operation_result('studies.prepare_trial',result['trial'],records)
        document('candidate_history',origin,result['candidate_id'])
        graph_docs=[item['document'] for item in records if item.get('family')=='pipeline_graph'
                    and item['document']['origin_catalog_id']==origin]
        if not any(result['graph'] in doc['revisions'] for doc in graph_docs):
            _invalid('Preparation graph has no retained revision.')
        if operation=='studies.prepare_verifier':document('run_history',origin,result['package_run_id'])
    elif operation=='studies.branch_trial':
        ref=result['parent'];origin=ref['catalog_id'];parent=document('trial_history',origin,ref['trial_id'])['trial']
        if parent['material']['sha256']!=ref['material_sha256']:_invalid('Branch parent material differs.')
        resolve=lambda value:document('trial_history',value['catalog_id'],value['trial_id'])['trial']
        validate_retained_intent(result['intent'],resolve=resolve)
        document('study_history',origin,result['study_id'])
        graph_docs=[item['document'] for item in records if item.get('family')=='pipeline_graph'
                    and item['document']['origin_catalog_id']==origin]
        if not any(result['graph'] in doc['revisions'] for doc in graph_docs):_invalid('Branch graph has no retained revision.')

def validate_operation_result(operation,result,records=None):
    """Validate exact returned meaning and, when supplied, its canonical fact."""
    try:
        claimed=_validate_operation_shape(operation,result)
        if claimed and records is not None:_bind_operation_result(operation,result,records)
        return claimed
    except WorkbenchError:
        raise
    except (KeyError,TypeError,ValueError,AttributeError):
        _invalid('Invalid historical operation result or fact binding.')


def validate_data_exposures(records,history):
    """Exposure is a historical Run/source fact, never present permission."""
    try:
        for item in records:
            if item.get('family')!='dataset_exposure':continue
            doc=item['document']
            _shape(doc,('format','id','record_id','source_hash','reason','run_id','release_id','created_at'),'dataset exposure')
            if doc['format']!='dataset_exposure_v1':_invalid('Unsupported dataset exposure.','unsupported')
            matches=[]
            for (origin,run_id),saved in history.runs.items():
                run=saved['run']
                if run_id!=doc['run_id'] or run.get('release_id')!=doc['release_id']:continue
                sources=[source for source in run.get('source_records',[]) if source.get('id')==doc['record_id']
                         and source.get('split')=='test' and source_content_hash(source)==doc['source_hash']]
                events=[event for event in run.get('exposure_events',[]) if event.get('created_at')==doc['created_at']
                        and event.get('reason')==doc['reason']]
                if len(sources)==1 and events:matches.append(origin)
            if len(matches)!=1:_invalid('Dataset exposure has no unique exact historical Run/source/release binding.')
        return True
    except WorkbenchError:
        raise
    except (KeyError,TypeError,ValueError,AttributeError):
        _invalid('Invalid historical dataset exposure binding.')


class ProjectHistory:
    """Read-only imported facts plus canonical, non-executing Study metadata edits."""
    def __init__(self,session,*,materials=None,authorize_disclosure=None):
        self.session=session;self.access=session.access;self.artifacts=session.artifacts
        if materials is None:
            from project_material import ProjectMaterial
            materials=ProjectMaterial(session)
        self.materials=materials;self.authorize_disclosure=authorize_disclosure

    def _facts(self):
        self.session.check()
        return decode_records(self.session.snapshot['records'],materials=self.materials,artifacts=self.artifacts)

    def _authorize(self,action,target=None):
        self.access.require('inspect',action,target)

    def _origin(self,origin):
        return self.session.snapshot['project_id'] if origin is None else origin

    def _record(self,collection,identity,origin=None):
        origin=self._origin(origin);identifier(origin,'Origin catalog');identifier(identity)
        result=collection.get((origin,identity))
        if result is None:_invalid('Historical record is unavailable.','not_found')
        return result

    def study(self,study_id,*,origin_catalog_id=None,offset=0,limit=100,revision=None):
        self._authorize('studies.get',study_id)
        natural(offset,'Reservation offset');natural(limit,'Reservation limit',1,100)
        facts=self._facts();doc=self._record(facts.studies,study_id,origin_catalog_id)
        if offset and revision is None:_invalid('Later reservation pages require a Study revision.')
        if revision is not None and revision!=doc['study']['revision']:_invalid('Study changed between pages.','stale')
        totals=reservation_totals(doc['reservations'])
        self._authorize('studies.get',study_id)
        end=min(offset+limit,len(doc['reservations']))
        return {'study':copy.deepcopy(doc['study']),'reservations':copy.deepcopy(doc['reservations'][offset:end]),
                'charged':totals,'revision_history_complete':doc['revision_history_complete'],
                'page':{'offset':offset,'limit':limit,'total':len(doc['reservations']),
                        'study_revision':doc['study']['revision'],'next_offset':end if end<len(doc['reservations']) else None}}

    def studies(self):
        self._authorize('studies.list')
        result=[{'origin_catalog_id':origin,'study':copy.deepcopy(doc['study'])}
                for (origin,_),doc in sorted(self._facts().studies.items())]
        return {'studies':result}

    def policies(self,*,origin_catalog_id=None):
        self._authorize('studies.policy')
        origin=self._origin(origin_catalog_id)
        return {'policies':[{'ref':{'kind':'selection_policy','catalog_id':namespace,'id':identity,'revision':revision,'sha256':sha},
                             'policy':copy.deepcopy(value)}
                for (namespace,identity,revision,sha),value in sorted(self._facts().policies.items()) if namespace==origin]}

    def policy(self,ref):
        self._authorize('studies.policy',ref.get('id'))
        reference(ref,'selection_policy',ref['catalog_id'])
        value=self._facts().policies.get((ref['catalog_id'],ref['id'],ref['revision'],ref['sha256']))
        if value is None:_invalid('Historical selection policy is unavailable.','not_found')
        return copy.deepcopy(value)

    def trial(self,trial_id,*,origin_catalog_id=None):
        self._authorize('studies.trial',trial_id)
        return copy.deepcopy(self._record(self._facts().trials,trial_id,origin_catalog_id)['trial'])

    def lineage(self,*,origin_catalog_id=None):
        self._authorize('studies.lineage')
        origin=self._origin(origin_catalog_id)
        return {'records':[copy.deepcopy(doc) for (namespace,_),doc in sorted(self._facts().trials.items()) if namespace==origin]}

    def run(self,run_id,*,origin_catalog_id=None,offset=None,limit=None):
        self._authorize('runs.get',run_id)
        facts=self._facts();doc=self._record(facts.runs,run_id,origin_catalog_id)
        self._transitive(facts,doc)
        public=public_run_projection(doc['run'])
        public.pop('exposure_events',None)
        disclosures=self.disclosure_facts(run_id,origin_catalog_id=doc['origin_catalog_id'])
        payloads=doc['payloads'];page=None
        if offset is not None or limit is not None:
            offset=0 if offset is None else offset;limit=40 if limit is None else limit
            natural(offset,'Run payload offset');natural(limit,'Run payload limit',1,100)
            end=min(offset+limit,len(payloads));disclosure_end=min(offset+limit,len(disclosures))
            page={'offset':offset,'limit':limit,'total':len(payloads),
                  'next_offset':end if end<len(payloads) else None,
                  'disclosures_total':len(disclosures),
                  'disclosures_next_offset':disclosure_end if disclosure_end<len(disclosures) else None}
            payloads=payloads[offset:end];disclosures=disclosures[offset:disclosure_end]
        result={'origin_catalog_id':doc['origin_catalog_id'],'run':public,
                'historical':True,'execution_available':False,'evidence':'unverified',
                'disclosures':disclosures,'document':self.run_document_descriptor(run_id,origin_catalog_id=doc['origin_catalog_id']),
                'payloads':[dict(copy.deepcopy(edge),availability=self.artifacts.inspect(
                    {'format':'project_artifact_v1',**edge['blob']})) for edge in payloads]}
        if page is not None:result['page']=page
        self._authorize('runs.get',run_id)
        return result

    def _run_document(self,run_id,origin_catalog_id):
        from project_store import _encode as canonical
        facts=self._facts();doc=self._record(facts.runs,run_id,origin_catalog_id)
        raw=canonical(doc)
        return facts,doc,raw,{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}

    def run_document_descriptor(self,run_id,*,origin_catalog_id=None):
        self._authorize('runs.get',run_id)
        _facts,_doc,_raw,descriptor=self._run_document(run_id,origin_catalog_id)
        self._authorize('runs.get',run_id)
        return descriptor

    def run_document_segment(self,run_id,expected_sha256,offset=0,limit=262144,*,origin_catalog_id=None):
        self._authorize('runs.get',run_id);_sha(expected_sha256)
        natural(offset,'Run document offset');natural(limit,'Run document segment limit',1,262144)
        facts,doc,raw,descriptor=self._run_document(run_id,origin_catalog_id)
        self._transitive(facts,doc);self._disclose(doc['run'],'unknown')
        if descriptor['sha256']!=expected_sha256:_invalid('Run document changed.','stale')
        if offset>len(raw):_invalid('Run document offset exceeds its size.')
        end=min(offset+limit,len(raw))
        result={'format':'project_run_document_segment_v1','origin_catalog_id':doc['origin_catalog_id'],
                'run_id':run_id,**descriptor,'offset':offset,'limit':limit,
                'base64':base64.b64encode(raw[offset:end]).decode('ascii'),
                'next_offset':end if end<len(raw) else None}
        self._authorize('runs.get',run_id);self._disclose(doc['run'],'unknown')
        return result

    def payload_set_sha256(self,run_id,*,origin_catalog_id=None):
        self._authorize('runs.get',run_id)
        doc=self._record(self._facts().runs,run_id,origin_catalog_id)
        return payload_set_sha256(doc['origin_catalog_id'],run_id,doc['payloads'])

    def disclosure_facts(self,run_id,*,origin_catalog_id=None):
        self._authorize('runs.get',run_id);origin=self._origin(origin_catalog_id)
        result=[]
        for operation in operation_records(self.session.snapshot['records']).values():
            if operation['operation']!='history.disclose':continue
            value=validate_disclosure_fact(operation['result'])
            if value['origin_catalog_id']==origin and value['run_id']==run_id:result.append(value)
        return sorted(result,key=lambda value:(value['occurred_at'],value['actor_id'],value['reason']))

    def record_disclosure(self,run_id,body,expected_checkpoint,key):
        closed(body,('origin_catalog_id','reason'));body=checked_json(body)
        identifier(run_id);identifier(body['origin_catalog_id'],'Origin catalog');text(body['reason'],'Disclosure reason',1000)
        authority=self.access.require('expose-holdout','history.disclose',run_id)
        actor_id=authority.actor_id
        effective=dict(body,actor_id=actor_id)
        def invoke():
            current=self.access.require('expose-holdout','history.disclose',run_id)
            if current.actor_id!=actor_id:_invalid('Disclosure caller changed.','conflict')
            doc=self._record(self._facts().runs,run_id,body['origin_catalog_id'])
            return validate_disclosure_fact({'format':'project_disclosure_v1','origin_catalog_id':body['origin_catalog_id'],
                'run_id':run_id,'payload_set_sha256':payload_set_sha256(doc['origin_catalog_id'],run_id,doc['payloads']),
                'population':'all','reason':body['reason'],'actor_id':actor_id,'occurred_at':timestamp()})
        def capture(result,before_records):return {'records':[],'result':result}
        return self.session.mutate('history.disclose',run_id,effective,expected_checkpoint,key,invoke,capture,scope='expose-holdout')

    def dependencies(self,run_id,*,origin_catalog_id=None,offset=0,limit=100):
        self._authorize('runs.get',run_id);natural(offset,'Dependency offset');natural(limit,'Dependency limit',1,100)
        doc=self._record(self._facts().runs,run_id,origin_catalog_id);run=doc['run']
        declarations_by_sha={item['document']['sha256']:item['document'] for item in self.session.snapshot['records']
                             if item['family']=='project_artifact'}
        required=[]
        for edge in doc['payloads']:
            required.append({'name':edge['name'],'sha256':edge['blob']['sha256'],'bytes':edge['blob']['bytes'],
                             'preservation':edge['preservation'],'required_for':edge['required_for']})
        if run.get('execution_kind')=='external_recipe':
            for path,item in sorted(run['material']['runtime']['files'].items()):
                required.append({'name':path,'sha256':item['sha256'],'bytes':item['bytes'],
                                 'preservation':'regenerable','required_for':['historical_runtime']})
            for name,sha in sorted(run['material']['host_files'].items()):
                declaration=declarations_by_sha.get(sha)
                required.append({'name':name,'sha256':sha,'bytes':declaration['bytes'] if declaration else None,
                                 'preservation':'unique','required_for':['historical_host_source']})
        end=min(offset+limit,len(required));items=[]
        for item in required[offset:end]:
            declaration=declarations_by_sha.get(item['sha256'])
            availability=self.artifacts.inspect(declaration) if declaration else {
                'state':'missing','expected_sha256':item['sha256'],'expected_bytes':item['bytes'],
                'observed_sha256':None,'observed_bytes':None}
            items.append(dict(copy.deepcopy(item),availability=availability))
        return {'items':items,'page':{'offset':offset,'limit':limit,'total':len(required),
                                     'next_offset':end if end<len(required) else None}}

    def publication_result(self,run_id,*,origin_catalog_id=None):
        """Inspect hash-bound publication proof without any continuation authority."""
        self._authorize('runs.publication_result',run_id)
        facts=self._facts();doc=self._record(facts.runs,run_id,origin_catalog_id);self._transitive(facts,doc)
        publication=doc['publication']
        if publication is None or publication['source'] is None:
            _invalid('Historical publication source is unavailable.','unavailable')
        from run_publication import validate_publication_source,validate_publication_result,MAX_DOCUMENT_BYTES
        run=doc['run'];self._disclose(run,'unknown');raw=self.artifacts.read_blob(publication['source'],maximum_bytes=MAX_DOCUMENT_BYTES)
        source=validate_publication_source(raw,run=run)
        result=None;continuation=publication['continuation']
        if publication['result'] is not None:
            if continuation is None or continuation['state']!='published':_invalid('Historical publication result is not attached.')
            raw=self.artifacts.read_blob(publication['result'],maximum_bytes=MAX_DOCUMENT_BYTES)
            result=validate_publication_result(raw,run=run,source=source,ref=continuation['result_ref'],continuation=continuation)
        self._authorize('runs.publication_result',run_id)
        return {'origin_catalog_id':doc['origin_catalog_id'],'source':source,'result':result,
                'evidence':'receipt_verified','execution_available':False}

    def _disclose(self,run,population,name=None):
        # Portable labels describe evidence; they cannot grant present access.
        if name=='release.zip':population='unknown'
        elif name in TEST_FILES or any(item['name']==name and item.get('split')=='test' for item in run['artifacts']):
            population='test'
        elif run.get('execution_kind')=='external_recipe' and (name is None or not name.startswith(('source/','runtime-bootstrap/','native-policy/'))):
            population='unknown'
        if population in ('test','unknown'):
            if self.authorize_disclosure is None:_invalid('Current explicit disclosure is required.','unavailable')
            self.authorize_disclosure(run,population)

    def _transitive(self,facts,doc,seen=None):
        run=doc['run'];key=(doc['origin_catalog_id'],run['id']);seen=set() if seen is None else seen
        if key in seen:_invalid('Cyclic historical Run input lineage.')
        if len(seen)>=64:_invalid('Historical Run input lineage exceeds its bound.','unsupported')
        seen=seen|{key}
        if run.get('execution_kind')!='external_recipe':return
        for item in run['material']['inputs'].values():
            if item.get('kind')!='run_artifact':continue
            source=item['source'];parent=facts.runs[(source['catalog_id'],source['run_id'])]
            self._authorize('runs.artifact',source['run_id'])
            edge=next(edge for edge in parent['payloads'] if edge['name']==source['artifact_name'])
            self._disclose(parent['run'],edge['population'],edge['name']);self._transitive(facts,parent,seen)

    def _read(self,doc,name,maximum):
        edges=_payloads(doc['payloads']);edge=edges.get(name)
        if edge is None:_invalid('Historical artifact is unavailable.','not_found')
        self._authorize('runs.artifact',doc['run']['id']);self._disclose(doc['run'],edge['population'],name)
        raw=self.artifacts.read_blob(edge['blob'],maximum_bytes=maximum)
        self._authorize('runs.artifact',doc['run']['id']);self._disclose(doc['run'],edge['population'],name)
        return raw

    def artifact(self,run_id,name,*,origin_catalog_id=None,maximum_bytes=40*1024**2):
        facts=self._facts();doc=self._record(facts.runs,run_id,origin_catalog_id)
        self._transitive(facts,doc)
        return self._read(doc,name,maximum_bytes)

    def capture_artifact(self,run_id,name,expected_sha256,*,max_bytes=MAX_ARTIFACT_BYTES,origin_catalog_id=None):
        """Capture an exact completed input without live recovery or admissions."""
        self._authorize('runs.capture_artifact',run_id);_sha(expected_sha256)
        natural(max_bytes,'Artifact input byte bound',1,MAX_ARTIFACT_BYTES)
        facts=self._facts();doc=self._record(facts.runs,run_id,origin_catalog_id);run=doc['run']
        self._transitive(facts,doc)
        if run['state']!='completed':_invalid('Only completed Runs provide artifact inputs.','unavailable')
        external=run.get('execution_kind')=='external_recipe'
        if not external and (run.get('graph',{}).get('recipe')!='image_classification_model_v2' or name=='release.zip'):
            _invalid('Capture requires qualified classifier evidence or an external Run.','unsupported')
        item=next((item for item in run['artifacts'] if item['name']==name),None)
        if item is None or item['bytes']>max_bytes:_invalid('Artifact input is unavailable or exceeds its bound.','unavailable')
        if item['sha256']!=expected_sha256:_invalid('Artifact differs from expected SHA256.','conflict')
        if external:
            self._disclose(run,'unknown')
            receipt=self._read(doc,'custody-receipt.json',16384)
            manifest=self._read(doc,'artifact-manifest.json',65536)
            try:validate_external_artifact_inventory(run,receipt,manifest)
            except (ValueError,TypeError,KeyError) as error:
                raise WorkbenchError('Retained external inventory differs.','unavailable',409) from error
            if run.get('extension_context') is not None:self.evidence(run_id,origin_catalog_id=doc['origin_catalog_id'])
            if not run['material']['recipe']['resources'].get('profile')=='captured_cpu_large_outputs_v1':
                for artifact in run['artifacts']:self._read(doc,artifact['name'],MAX_ARTIFACT_BYTES)
            proof=receipt
        else:
            # Shared model evidence verifies the full frozen prediction/checkpoint closure.
            self.evidence(run_id,origin_catalog_id=doc['origin_catalog_id'])
            proof=self._read(doc,'artifact-manifest.json',65536)
        raw=self._read(doc,name,max_bytes)
        source=artifact_capture_source(run,item,raw,proof)
        self._authorize('runs.capture_artifact',run_id)
        return raw,source

    def evidence(self,run_id,selectors=None,*,origin_catalog_id=None):
        self._authorize('runs.model_evidence',run_id)
        facts=self._facts();doc=self._record(facts.runs,run_id,origin_catalog_id)
        self._transitive(facts,doc)
        if doc['run'].get('execution_kind')=='external_recipe':self._disclose(doc['run'],'unknown')
        result=self.materials.evidence(doc['run'],selectors or {},
            read_blob=lambda name,maximum:self._read(doc,name,maximum))
        self._authorize('runs.model_evidence',run_id)
        return result

    def candidate(self,candidate_id,*,origin_catalog_id=None,verify=False):
        self._authorize('studies.candidate',candidate_id)
        facts=self._facts();doc=self._record(facts.candidates,candidate_id,origin_catalog_id);value=doc['candidate']
        result={'ref':{'kind':'candidate','catalog_id':doc['origin_catalog_id'],'id':candidate_id,'sha256':digest(value)},
                'candidate':copy.deepcopy(value),'run_id':value['run_id'],'evidence':'unverified'}
        if verify:
            evidence=self.evidence(value['run_id'],{'checkpoint_sha256':value['checkpoint_sha256']},
                                   origin_catalog_id=doc['origin_catalog_id'])
            trial=facts.trials[(doc['origin_catalog_id'],value['trial_id'])]['trial']
            validate_candidate_evidence(evidence,trial)
            ref=value['policy'];policy=facts.policies[(doc['origin_catalog_id'],ref['id'],ref['revision'],ref['sha256'])]
            checkpoint=select_retained_checkpoint(evidence,policy,value['checkpoint_sha256'])
            run=facts.runs[(doc['origin_catalog_id'],value['run_id'])]['run']
            evaluation='model-evidence.json' if run.get('extension_context') is not None else 'metrics.json'
            if not any(item['name']==evaluation and item['sha256']==value['evaluation_sha256'] for item in run['artifacts']):
                _invalid('Candidate evaluation identity differs.')
            result.update(checkpoint=checkpoint,evidence='verified')
        return result

    def package_state(self,candidate_id,*,origin_catalog_id=None):
        from candidate_packages import retained_package_state
        self._authorize('studies.package_state',candidate_id)
        facts=self._facts();origin=self._origin(origin_catalog_id)
        candidate=self.candidate(candidate_id,origin_catalog_id=origin,verify=True)
        preparations=[]
        for (namespace,_),doc in facts.studies.items():
            if namespace!=origin:continue
            for operation in doc['operations']:
                if operation['operation_id'] in ('studies.prepare_package','studies.prepare_verifier') and operation['result'].get('candidate_id')==candidate_id:
                    preparations.append({'operation_id':operation['operation_id'],'result':operation['result']})
        def runs_for_trial(trial_id):
            result=[]
            for (namespace,run_id),reservation in sorted(facts.reservations.items()):
                if namespace==origin and reservation['trial_id']==trial_id:
                    self._authorize('runs.get',run_id)
                    doc=facts.runs[(origin,run_id)];self._transitive(facts,doc);result.append(copy.deepcopy(doc['run']))
            return result
        result=retained_package_state(candidate,preparations,runs_for_trial=runs_for_trial,
            read_artifact=lambda run_id,name:self.artifact(run_id,name,origin_catalog_id=origin))
        self._authorize('studies.package_state',candidate_id)
        return result

    def retained_analysis(self,origin_catalog_id,body,*,export=False):
        from retained_analysis import query_history
        run_id=body['run_id'];doc=self._record(self._facts().runs,run_id,origin_catalog_id)
        evidence=self.evidence(run_id,{'checkpoint_sha256':body['checkpoint_sha256']},origin_catalog_id=origin_catalog_id)
        return query_history(self.session.db,doc['run'],evidence,body,authorize=self.access.require,export=export)

    def _mutate(self,operation,target,body,expected_checkpoint,key,build):
        prepared={}
        def invoke():
            self.access.require('edit',operation,target)
            facts=self._facts();records,result=build(facts)
            prepared['records']=records
            return result
        def capture(result,before_records):
            return {'records':prepared['records'],'result':result}
        self.access.require('edit',operation,target,owner_only=operation in ('studies.create','studies.save'))
        return self.session.mutate(operation,target,body,expected_checkpoint,key,invoke,capture)

    def _audit_fact(self,action,target,details):
        return {'actor_id':self.access._context().actor_id,'action':action,'target':target,'details':copy.deepcopy(details),
                'result':'success','occurred_at':timestamp()}

    def create_study(self,body,expected_checkpoint,request_key):
        closed(body,('name','limits','policy'));body=checked_json(body)
        text(body['name'],'Study name');limits=budget(body['limits']);policy=validate_retained_policy(body['policy'])
        def build(facts):
            origin=self.session.snapshot['project_id'];identity=uuid.uuid4().hex;sha=digest(policy)
            prior=next((key for key,value in facts.policies.items() if key[0]==origin and key[3]==sha),None)
            policy_id=prior[1] if prior else uuid.uuid4().hex
            ref={'kind':'selection_policy','catalog_id':origin,'id':policy_id,'revision':1,'sha256':sha}
            study=new_study_document(body,catalog_id=origin,study_id=identity,policy_id=policy_id)
            doc={'format':FAMILY_FORMATS['study_history'],'origin_catalog_id':origin,'study':study,
                 'memberships':[{'revision':1,'trial_ids':[]}],'policies':[{'ref':ref,'policy':policy}],
                 'reservations':[],'operations':[],'revisions':[copy.deepcopy(study)],
                 'audit':[self._audit_fact('studies.create',identity,{'policy_sha256':sha,'limits':limits})],
                 'revision_history_complete':True}
            return [envelope('study_history',origin,identity,doc)],study
        return self._mutate('studies.create',None,body,expected_checkpoint,request_key,build)

    def save_study(self,study_id,body,expected_checkpoint,request_key):
        closed(body,('revision','name','limits','policy'));body=checked_json(body)
        text(body['name'],'Study name');limits=budget(body['limits'])
        def build(facts):
            origin=self.session.snapshot['project_id'];doc=copy.deepcopy(self._record(facts.studies,study_id,origin));study=doc['study']
            if body['revision']!=study['revision']:_invalid('Study changed. Reload.','stale')
            ref=reference(body['policy'],'selection_policy',origin)
            policy=facts.policies.get((origin,ref['id'],ref['revision'],ref['sha256']))
            if policy is None:_invalid('Selection policy is unavailable.','unavailable')
            totals=reservation_totals(doc['reservations'])
            study=edit_study_document(study,body,policy=policy,charged=totals,catalog_id=origin)
            study['revision']=natural(study['revision']+1,'Study revision',1);doc['study']=study
            if not any(item['ref']==ref for item in doc['policies']):doc['policies'].append({'ref':ref,'policy':policy})
            doc['revisions'].append(copy.deepcopy(study));doc['audit'].append(self._audit_fact('studies.save',study_id,{'revision':study['revision']}))
            return [envelope('study_history',origin,study_id,doc)],study
        return self._mutate('studies.save',study_id,body,expected_checkpoint,request_key,build)

    def prepare_trial_from_material(self,study_id,body,expected_checkpoint,request_key):
        """Attach a fully retained composition without capture, approval or execution."""
        closed(body,('revision','material','replicate'));body=checked_json(body)
        natural(body['replicate'],'Replicate')
        self.access.require('edit','studies.prepare_trial',study_id)
        if request_key not in operation_records(self.session.snapshot['records']):
            self.materials.recipe(body['material'],verify=True)
        def build(facts):
            origin=self.session.snapshot['project_id'];doc=copy.deepcopy(self._record(facts.studies,study_id,origin))
            study=doc['study']
            if body['revision']!=study['revision']:_invalid('Study changed. Reload.','stale')
            ref=reference(body['material'],'recipe_material',origin);self.materials.recipe(ref)
            for (namespace,_),other in facts.trials.items():
                trial=other['trial']
                if namespace==origin and trial['study_id']==study_id and trial['material']==ref and trial['replicate']==body['replicate']:
                    _invalid('Material/replicate already belongs to this study.','conflict')
            trial=new_trial_document(study,ref,body['replicate'],trial_id=uuid.uuid4().hex)
            study['trial_ids'].append(trial['id']);study['membership_revision']+=1
            study['revision']=natural(study['revision']+1,'Study revision',1)
            doc['memberships'].append({'revision':study['membership_revision'],'trial_ids':copy.deepcopy(study['trial_ids'])})
            doc['revisions'].append(copy.deepcopy(study))
            doc['audit'].append(self._audit_fact('studies.prepare_trial',study_id,{'trial_id':trial['id']}))
            trial_doc={'format':FAMILY_FORMATS['trial_history'],'origin_catalog_id':origin,'trial':trial,'lineage':None}
            return [envelope('study_history',origin,study_id,doc),envelope('trial_history',origin,trial['id'],trial_doc)],trial
        return self._mutate('studies.prepare_trial',study_id,body,expected_checkpoint,request_key,build)

    def select_candidate(self,study_id,body,expected_checkpoint,request_key):
        closed(body,('revision','trial_id','run_id'),('checkpoint_sha256',));body=checked_json(body)
        identifier(body['trial_id']);identifier(body['run_id'])
        # Expensive semantic proof precedes the write transaction. All exact
        # associations and selected policy are checked again under publication.
        origin=self.session.snapshot['project_id']
        self.access.require('edit','studies.select_candidate',study_id)
        evidence=(self.evidence(body['run_id'],{},origin_catalog_id=origin)
                  if request_key not in operation_records(self.session.snapshot['records']) else None)
        def build(facts):
            doc=copy.deepcopy(self._record(facts.studies,study_id,origin));study=doc['study']
            if body['revision']!=study['revision']:_invalid('Study changed. Reload.','stale')
            trial=self._record(facts.trials,body['trial_id'],origin)['trial']
            reservation=facts.reservations.get((origin,body['run_id']))
            if reservation is None or reservation['trial_id']!=trial['id']:_invalid('Run does not belong to the selected trial.')
            validate_candidate_evidence(evidence,trial)
            ref=study['policy'];policy=facts.policies[(origin,ref['id'],ref['revision'],ref['sha256'])]
            checkpoint=select_retained_checkpoint(evidence,policy,body.get('checkpoint_sha256'))
            run=facts.runs[(origin,body['run_id'])]['run']
            name='model-evidence.json' if run.get('extension_context') is not None else 'metrics.json'
            evaluation=next((item for item in run['artifacts'] if item['name']==name),None)
            candidate=new_candidate_document(study,trial,run,checkpoint,evaluation,candidate_id=uuid.uuid4().hex)
            study['revision']=natural(study['revision']+1,'Study revision',1)
            doc['revisions'].append(copy.deepcopy(study));doc['audit'].append(self._audit_fact(
                'studies.select_candidate',candidate['id'],{'study_id':study_id,'run_id':run['id'],'checkpoint_sha256':checkpoint['sha256']}))
            candidate_doc={'format':FAMILY_FORMATS['candidate_history'],'origin_catalog_id':origin,'candidate':candidate}
            result={'ref':{'kind':'candidate','catalog_id':origin,'id':candidate['id'],'sha256':digest(candidate)},
                    'candidate':candidate,'run_id':run['id'],'checkpoint':checkpoint}
            return [envelope('study_history',origin,study_id,doc),
                    envelope('candidate_history',origin,candidate['id'],candidate_doc)],result
        return self._mutate('studies.select_candidate',study_id,body,expected_checkpoint,request_key,build)

    def record_lineage(self,body,expected_checkpoint,request_key):
        closed(body,('trial','intent'));body=checked_json(body,INTENT_LIMIT+4096)
        def build(facts):
            origin=self.session.snapshot['project_id'];trial=facts.trial_ref(body['trial'])
            if body['trial']['catalog_id']!=origin:_invalid('Inherited Trials remain immutable historical evidence.','conflict')
            doc=copy.deepcopy(facts.trials[(origin,trial['id'])])
            if doc['lineage'] is not None:_invalid('Trial lineage is already recorded and immutable.','conflict')
            intent=validate_retained_intent(body['intent'],resolve=facts.trial_ref)
            value={'format':'trial_lineage_v1','trial':copy.deepcopy(body['trial']),'intent':intent,
                   'actor_id':self.access._context().actor_id,'recorded_at':timestamp(),
                   'timing':'retrospective' if any(item['trial_id']==trial['id'] for item in facts.reservations.values()) else 'before_admission'}
            validate_retained_lineage(value,trial=trial,resolve=facts.trial_ref)
            parent=(intent['parent'] or {}).get('trial_id')
            validate_retained_ancestry(trial['id'],parent,parent_of=lambda identity:
                (facts.trials[(origin,identity)]['lineage']['intent']['parent'] or {}).get('trial_id')
                if facts.trials[(origin,identity)]['lineage'] else None)
            doc['lineage']=value
            study_doc=copy.deepcopy(facts.studies[(origin,trial['study_id'])])
            study_doc['audit'].append(self._audit_fact('studies.lineage.record',trial['id'],{'intent_sha256':digest(intent)}))
            return [envelope('trial_history',origin,trial['id'],doc),
                    envelope('study_history',origin,trial['study_id'],study_doc)],value
        return self._mutate('studies.record_lineage',body.get('trial',{}).get('trial_id'),body,expected_checkpoint,request_key,build)

    def unavailable_execution(self,*args,**kwargs):
        _invalid('Project execution and candidate preparation require the M3 custody boundary.','unavailable')

    approve=admit=continue_study=stop=prepare_package=prepare_verifier=unavailable_execution
