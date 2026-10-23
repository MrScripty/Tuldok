"""Inert history identity/closure and real PostgreSQL checkpoint boundaries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from access import Access
from experiments import new_study_document, validate_retained_reservation
from metadata import Metadata, connection_info
from pipeline import adapter_identity_for_graph, digest, execution_digest
from project_artifacts import ProjectArtifacts
from project_history import (FAMILY_FORMATS, HistoryFacts, ProjectHistory, capture_run, decode_records, declarations, envelope,
    validate_operation_result, validate_data_exposures)
from project_session import ProjectSession
from project_store import ProjectStore
from workbench import WorkbenchError
from auth_helpers import ExplicitOwnerFixture

ORIGIN='1'*32
OTHER='2'*32
MATERIAL='a'*64


def policy():
    return {'format':'selection_policy_v1','metric_definition_sha256':'b'*64,'checkpoint_rule':'explicit',
            'replicate_reduce':'individual','required_capabilities':[],'numerical_acceptance':'diagnostic','tie_break':'trial_id'}


def study(identity='3'*32,origin=ORIGIN,trials=()):
    value=new_study_document({'name':'Exact intent λ','limits':dict(attempt_slots=3,admitted_wall_seconds=100,
        retained_bytes=10000,peak_staging_bytes=10000),'policy':policy()},catalog_id=origin,study_id=identity,policy_id='4'*32)
    value['trial_ids']=list(trials)
    return envelope('study_history',origin,identity,dict(format=FAMILY_FORMATS['study_history'],origin_catalog_id=origin,
        study=value,memberships=[{'revision':1,'trial_ids':list(trials)}],policies=[{'ref':value['policy'],'policy':policy()}],
        reservations=[],operations=[],revisions=[copy.deepcopy(value)],audit=[],revision_history_complete=True))


def trial(identity,study_id,origin=ORIGIN,parent=None,baseline=None):
    ref={'kind':'recipe_material','catalog_id':origin,'id':MATERIAL,'sha256':MATERIAL}
    value={'format':'trial_v1','id':identity,'study_id':study_id,'material':ref,'replicate':0}
    lineage=None
    if parent is not None or baseline is not None:
        intent={'ancestry':'derived' if parent else 'root','parent':parent,'baseline':baseline,'cohort':'cross-study',
            'hypothesis':'Exact saved scientific intent','change_summary':'One factor',
            'target':{'metric_id':'accuracy','metric_definition_sha256':None,'direction':'maximize','threshold':None,
                      'acceptance':'Diagnostics only'}}
        lineage={'format':'trial_lineage_v1','trial':{'catalog_id':origin,'trial_id':identity,'material_sha256':MATERIAL},
            'intent':intent,'actor_id':'5'*32,'recorded_at':'2026-10-22T12:00:00+00:00','timing':'before_admission'}
    return envelope('trial_history',origin,identity,dict(format=FAMILY_FORMATS['trial_history'],origin_catalog_id=origin,
                    trial=value,lineage=lineage))


class Materials:
    """Only material lookup is substituted; history/lineage validators are real."""
    def recipe(self,ref,*,verify=False):
        if ref!={'kind':'recipe_material','catalog_id':ORIGIN,'id':MATERIAL,'sha256':MATERIAL}:
            raise WorkbenchError('Unknown exact fixture material.','unavailable',409)
        return {'ref':copy.deepcopy(ref),'material':{'resource_envelope':dict(attempt_slots=1,
            admitted_wall_seconds=10,retained_bytes=100,peak_staging_bytes=100)}}


def legacy_run(origin=ORIGIN):
    graph={'schema_version':1,'mode':'real','id':'6'*32,'revision':1,'name':'Saved graph',
           'recipe_version':1,'nodes':[{'id':'publish','type':'publish','definition_version':1,'parameters':{}}],'edges':[]}
    return {'schema_version':1,'mode':'real','id':'7'*32,'dataset_id':origin,'request_key':'old-request-0001',
        'request_sha256':'c'*64,'state':'completed','created_at':'2026-10-22T12:00:00+00:00',
        'started_at':None,'finished_at':'2026-10-22T12:01:00+00:00','graph':graph,'graph_revision':1,
        'graph_sha256':execution_digest(graph),'graph_document_sha256':digest(graph),'parameters':{},
        'adapter':adapter_identity_for_graph(graph),'artifacts':[],'metrics':None,'attempt':1,'parent_run_id':None,
        'events':[],'error':None,'quality_claim':False,'progress':{'stage':'completed','completed':None,'total':None},
        'node_attempts':[],'release_id':'d'*64,'release_sha256':'d'*64,'release_bytes':1,'source_records':[],
        'prior_test_exposure':{},'runtime':{},'exposure_events':[],'admission_id':'8'*32,
        'worker':{'pid':12345},'supervisor':{'pid':23456},'worker_command':['never','execute'],
        'python':'/historical/python','process_phase':'finished','release_path':'/historical/release.zip'}


class HistoryCodecTests(unittest.TestCase):
    def test_fork_preserves_archived_disclosure_observation_without_current_permission(self):
        from project_fork import _digest,_input
        from project_session import operation_records
        fact=dict(format='project_disclosure_v1',origin_catalog_id=ORIGIN,run_id='7'*32,payload_set_sha256='a'*64,population='all',
            reason='Original explicit disclosure observation',actor_id='8'*32,occurred_at='2026-10-22T00:00:00+00:00')
        key='original-disclosure'
        receipt=dict(format='project_operation_v2',project_id=ORIGIN,operation='history.disclose',
            target=fact['run_id'],request_key=key,input_sha256='b'*64,result=fact)
        original=dict(family='project_operation',id=ORIGIN+'.'+hashlib.sha256(key.encode()).hexdigest(),document=receipt)
        source=dict(project_id=ORIGIN,checkpoint='c'*64)
        fork=dict(format='project_fork_v1',source=source,destination_project_id=OTHER,
            request_key='fork-disclosure',request_sha256=_digest(_input(source,'copy','Copy','fork-disclosure')),
            directory='copy',name='Copy',mapping=[],archived=[dict(family=original['family'],id=original['id'])],
            artifacts=dict(copied=[],missing_regenerable=[]))
        records=[original,dict(family='project_fork',id=OTHER,document=fork)]
        calls=[]
        session=SimpleNamespace(snapshot=dict(records=records,project_id=OTHER),artifacts=None,
            access=SimpleNamespace(require=lambda *args,**kwargs:calls.append(args)))
        history=ProjectHistory(session,materials=Materials())
        self.assertEqual(operation_records(records),{})
        self.assertEqual(history.disclosure_facts(fact['run_id'],origin_catalog_id=ORIGIN),[fact])
        self.assertEqual(history.disclosure_facts(fact['run_id'],origin_catalog_id=OTHER),[])
        self.assertEqual(calls[0],('inspect','runs.get',fact['run_id']))
        with self.assertRaisesRegex(WorkbenchError,'Current explicit disclosure'):
            history._disclose(legacy_run(),'test')

    def test_cross_study_parent_baseline_and_origin_namespace_remain_exact(self):
        parent_id='9'*32;child_id='a'*32
        parent_ref={'catalog_id':ORIGIN,'trial_id':parent_id,'material_sha256':MATERIAL}
        records=[study('3'*32,trials=[parent_id]),study('b'*32,trials=[child_id]),
            trial(parent_id,'3'*32),trial(child_id,'b'*32,parent=parent_ref,baseline=parent_ref)]
        before=copy.deepcopy(records)
        with patch('app.Dataset',side_effect=AssertionError('Inert decode constructed Dataset')), \
             patch('runs.Runs',side_effect=AssertionError('Inert decode constructed Runs')), \
             patch('subprocess.Popen',side_effect=AssertionError('Inert decode launched process')):
            facts=decode_records(records,materials=Materials())
        self.assertEqual(facts.trials[(ORIGIN,child_id)]['lineage']['intent']['parent'],parent_ref)
        self.assertEqual(records,before)
        changed=copy.deepcopy(records);changed[-1]['document']['lineage']['intent']['baseline']['catalog_id']=OTHER
        with self.assertRaises(WorkbenchError):decode_records(changed,materials=Materials())

    def test_closure_omissions_cycles_and_history_completeness_are_rejected(self):
        parent_id='9'*32;child_id='a'*32
        ref=lambda identity:{'catalog_id':ORIGIN,'trial_id':identity,'material_sha256':MATERIAL}
        records=[study(trials=[parent_id,child_id]),trial(parent_id,'3'*32,parent=ref(child_id)),
                 trial(child_id,'3'*32,parent=ref(parent_id))]
        with self.assertRaisesRegex(WorkbenchError,'cycle'):decode_records(records,materials=Materials())
        with self.assertRaises(WorkbenchError):decode_records(records[:-1],materials=Materials())
        value=study();value['document']['study']['revision']=2;value['document']['revisions']=[copy.deepcopy(value['document']['study'])]
        with self.assertRaisesRegex(WorkbenchError,'revision gap'):decode_records([value])
        value['document']['revision_history_complete']=False
        value['document']['audit']=[{'actor_id':None,'action':'studies.reconcile','target':value['document']['study']['id'],
            'details':{'state':'unknown'},'result':'interrupted','occurred_at':'2026-10-22T12:00:00+00:00'}]
        self.assertFalse(decode_records([value]).studies[(ORIGIN,'3'*32)]['revision_history_complete'])

    def test_inert_run_excludes_controls_and_preserves_exact_historical_hashes(self):
        run=legacy_run();saved=capture_run(run,payloads=[])
        self.assertEqual(saved['document']['run']['graph_sha256'],run['graph_sha256'])
        self.assertNotIn('worker',saved['document']['run']);self.assertNotIn('worker_command',saved['document']['run'])
        with patch('runs.process_status',side_effect=AssertionError('No PID observation')):
            result=decode_records([saved,*declarations(saved)])
        self.assertEqual(result.runs[(ORIGIN,run['id'])]['run']['dataset_id'],ORIGIN)
        changed=copy.deepcopy(saved);changed['document']['run']['worker']={'pid':1}
        with self.assertRaises(WorkbenchError):decode_records([changed,*declarations(changed)])
        with self.assertRaises(WorkbenchError):capture_run(dict(run,new_unowned_field={}),payloads=[])

    def test_missing_payload_is_declared_and_malformed_or_control_records_refuse(self):
        raw=b'Unique observation\x00\xff';sha=hashlib.sha256(raw).hexdigest()
        run=legacy_run();run['artifacts']=[{'name':'test-metrics.json','sha256':sha,'bytes':len(raw),'media_type':'application/json','split':'test'}]
        edge={'name':'test-metrics.json','blob':{'sha256':sha,'bytes':len(raw)},'population':'test','role':'model_evidence',
              'preservation':'unique','required_for':['scientific_inspection']}
        record=capture_run(run,payloads=[edge])
        declaration={'family':'project_artifact','id':sha,'document':{'format':'project_artifact_v1','sha256':sha,'bytes':len(raw)}}
        self.assertEqual(len(decode_records([record,*declarations(record)]).runs),1)
        with self.assertRaisesRegex(WorkbenchError,'declaration'):decode_records([record])
        for change in ({'credential':{'token':'secret'}},{'worker':None}):
            changed=copy.deepcopy(record);changed['document'].update(change)
            with self.assertRaises(WorkbenchError):decode_records([changed,*declarations(record)])

    def test_operation_results_bind_historical_revision_and_reject_plausible_tamper(self):
        value=study();original=copy.deepcopy(value['document']['study'])
        changed=copy.deepcopy(original);changed.update(revision=2,name='Later authored name')
        value['document']['study']=changed;value['document']['revisions'].append(changed)
        self.assertTrue(validate_operation_result('studies.create',original,[value]))
        self.assertTrue(validate_operation_result('studies.save',changed,[value]))
        forged=copy.deepcopy(original);forged['name']='Plausible forged success'
        self.assertTrue(validate_operation_result('studies.create',forged))
        with self.assertRaisesRegex(WorkbenchError,'retained revision'):
            validate_operation_result('studies.create',forged,[value])
        parent=trial('9'*32,'3'*32);result=copy.deepcopy(parent['document']['trial'])
        self.assertTrue(validate_operation_result('studies.prepare_trial',result,[parent]))
        result['replicate']=1
        with self.assertRaisesRegex(WorkbenchError,'retained Trial'):
            validate_operation_result('studies.prepare_trial',result,[parent])

    def test_exposure_binds_exact_run_release_test_source_and_saved_observation(self):
        run=legacy_run();run['source_records']=[{'id':'source-1','kind':'text','split':'test','content_hash':'a'*64}]
        run['exposure_events']=[{'id':'e'*32,'reason':'Exact comparison','created_at':'2026-10-22T12:00:00+00:00'}]
        facts=HistoryFacts();facts.runs[(ORIGIN,run['id'])]={'run':run}
        exposure={'family':'dataset_exposure','id':'f'*32,'document':{'format':'dataset_exposure_v1','id':'f'*32,
            'record_id':'source-1','source_hash':'a'*64,'reason':'Exact comparison','run_id':run['id'],
            'release_id':run['release_id'],'created_at':'2026-10-22T12:00:00+00:00'}}
        self.assertTrue(validate_data_exposures([exposure],facts))
        for key,value in (('run_id','8'*32),('release_id','b'*64),('source_hash','c'*64),('reason','Different reason')):
            forged=copy.deepcopy(exposure);forged['document'][key]=value
            with self.subTest(key=key),self.assertRaises(WorkbenchError):validate_data_exposures([forged],facts)
        facts.runs[(OTHER,run['id'])]={'run':copy.deepcopy(run)}
        with self.assertRaisesRegex(WorkbenchError,'unique'):validate_data_exposures([exposure],facts)

    def test_unclassified_audit_and_admission_receipt_cannot_hide_credentials(self):
        value=study()
        value['document']['audit']=[{'actor_id':'5'*32,'action':'access.issue','target':'6'*32,
            'details':{'token':'secret','token_sha256':'a'*64},'result':'success','occurred_at':'2026-10-22T12:00:00+00:00'}]
        with self.assertRaisesRegex(WorkbenchError,'Unclassified'):decode_records([value])
        value=study();value['document']['operations']=[{'actor_id':'5'*32,'operation_id':'studies.admit',
            'request_key':'admission-0001','request_sha256':'a'*64,'result':{'token':'secret'}}]
        with self.assertRaises(WorkbenchError):decode_records([value])
        value=study();value['document']['audit']=[{'actor_id':None,'action':'studies.reconcile','target':'3'*32,
            'details':{'state':'unknown','token':'secret'},'result':'interrupted','occurred_at':'2026-10-22T12:00:00+00:00'}]
        with self.assertRaisesRegex(WorkbenchError,'Unclassified'):decode_records([value])

    def test_admission_receipt_with_valid_reservation_and_nested_token_is_explicitly_unsupported(self):
        from project_history import _approval
        trial_value=trial('9'*32,'3'*32)['document']['trial']
        charge=Materials().recipe(trial_value['material'])['material']['resource_envelope']
        reservation={'id':'e'*32,'study_id':'3'*32,'admission_epoch':1,'request_key':'admission-0001','actor_id':'5'*32,
            'trial_id':trial_value['id'],'parent_run_id':None,'run_id':'7'*32,'request_sha256':'c'*64,
            'material_sha256':MATERIAL,'envelope':charge,'state':'settled','settled':copy.deepcopy(charge)}
        run={'id':'7'*32,'actor_id':'5'*32,'request_sha256':'c'*64,'parent_run_id':None,'approval_material_sha256':MATERIAL}
        validate_retained_reservation(reservation,trial=trial_value,composition=Materials().recipe(trial_value['material']),run=run)
        fake={'reservation':reservation,'run':{'id':run['id'],'dataset_id':ORIGIN,'artifacts':[{'token':'secret'}]}}
        with self.assertRaisesRegex(WorkbenchError,'unsupported') as error:
            validate_operation_result('studies.admit',fake)
        self.assertEqual(error.exception.code,'unsupported')
        native=legacy_run();expected={'pipeline.inspect_release':[native['release_id']],
            'dataset_releases.locate':[native['release_id']],'pipeline.probe':['image_classification'],
            'pipeline.probe_native':['image_classification'],'pipeline.definition_identity':['image_classification'],
            'pipeline.exposures':[None],'runs.update':[native['id']]}
        admission={'id':native['admission_id'],'catalog_id':ORIGIN,'actor_id':'5'*32,'credential_id':'6'*32,
            'kind':'runs','job_id':native['id'],'request_digest':native['request_sha256'],'effects':expected,'created_at':1}
        proof={'grant':None,'consumption':None,'admission':admission}
        self.assertIsNone(_approval(proof,native))
        bad=copy.deepcopy(proof);bad['admission']['effects']['unknown.authority']=['secret']
        with self.assertRaisesRegex(WorkbenchError,'Unclassified historical admission effects'):_approval(bad,native)
        external=dict(native,execution_kind='external_recipe')
        proof['admission']['effects']={'runs.update':[native['id']]}
        self.assertIsNone(_approval(proof,external))
        proof['admission']['effects']['runs.update']=['9'*32]
        with self.assertRaises(WorkbenchError):_approval(proof,external)

    def test_retained_receipt_and_inventory_codec_never_uses_live_runs_class(self):
        import base64
        from test_builtin_artifact_sources import BuiltinArtifactSourceTests
        from runs import artifact_capture_source,decode_diagnostic_json
        raw,expected=BuiltinArtifactSourceTests().source()
        run={'id':expected['run_id'],'dataset_id':expected['catalog_id'],'state':'completed',
            'request_sha256':expected['request_sha256'],'graph':{'recipe':'image_classification_model_v2'},
            'graph_sha256':expected['graph_sha256'],'release_sha256':expected['release_sha256'],
            'evidence_context':{'material_sha256':expected['material_sha256'],'adapter_sha256':expected['adapter_sha256']}}
        item={'name':expected['artifact_name'],'sha256':expected['measured_sha256'],'bytes':len(raw),'split':None}
        proof=base64.b64decode(expected['artifact_manifest_base64'])
        with patch('runs.Runs',side_effect=AssertionError('No live Runs dependency')):
            self.assertEqual(artifact_capture_source(run,item,raw,proof),expected)
            self.assertEqual(decode_diagnostic_json(b'{"exact":1}'),{'exact':1})
            for malformed in (b'{"exact":1,"exact":2}',b'{"exact":NaN}'):
                with self.assertRaises(ValueError):decode_diagnostic_json(malformed)
        with self.assertRaises(WorkbenchError):artifact_capture_source(run,item,raw+b'x',proof)

    def test_settled_charge_cannot_be_lowered_or_disconnected_from_run(self):
        trial_value=trial('9'*32,'3'*32)['document']['trial'];material=Materials().recipe(trial_value['material'])
        charge=material['material']['resource_envelope']
        value={'id':'e'*32,'study_id':'3'*32,'admission_epoch':1,'request_key':'reservation-0001','actor_id':'5'*32,
            'trial_id':trial_value['id'],'parent_run_id':None,'run_id':'7'*32,'request_sha256':'c'*64,
            'material_sha256':MATERIAL,'envelope':charge,'state':'settled','settled':copy.deepcopy(charge)}
        run={'id':'7'*32,'actor_id':'5'*32,'request_sha256':'c'*64,'parent_run_id':None,'approval_material_sha256':MATERIAL}
        self.assertEqual(validate_retained_reservation(value,trial=trial_value,composition=material,run=run),value)
        changed=copy.deepcopy(value);changed['settled']['retained_bytes']=1
        with self.assertRaises(WorkbenchError):validate_retained_reservation(changed,trial=trial_value,composition=material,run=run)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ProjectHistoryPostgresTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='tuldok-history-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name);self.databases=[];self.stores=[];self.artifact_owners=[]
        self.addCleanup(self.cleanup)
        self.store=ProjectStore.create(self.path/'project','Scientific history','new','f'*64);self.stores.append(self.store)
        self.start()

    def cleanup(self):
        import psycopg
        from psycopg import sql
        for artifacts in self.artifact_owners:artifacts.close()
        for store in self.stores:store.close()
        schemas=[]
        for db in self.databases:
            manifest=json.loads((db.path/'.tuldok.json').read_bytes())
            schemas.append('projection_'+manifest['projection_id'] if manifest['version']==2 else 'catalog_'+db.dataset_id)
            db.close()
        with psycopg.connect(connection_info(),autocommit=True) as connection:
            for schema in schemas:connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def start(self):
        db=Metadata(self.path/('host-'+uuid.uuid4().hex),dsn=os.environ['TULDOK_DATABASE_URL']);self.databases.append(db)
        host=SimpleNamespace(db=db,access=Access(db,db.path));owner=ExplicitOwnerFixture.bootstrap(host)
        artifacts=ProjectArtifacts(self.store);self.artifact_owners.append(artifacts)
        session=ProjectSession(self.store,db,host.access,artifacts,validate_records=lambda records:decode_records(records,materials=Materials()))
        self.host,self.owner,self.session=host,owner,session
        self.history=ProjectHistory(session,materials=Materials())

    def test_metadata_edits_cold_reopen_keep_history_without_active_authority(self):
        with self.owner.bound(self.host):
            before=self.session.snapshot['checkpoint']
            body={'name':'Unique hypothesis λ','limits':dict(attempt_slots=3,admitted_wall_seconds=100,retained_bytes=10000,
                peak_staging_bytes=10000),'policy':policy()}
            created=self.history.create_study(body,before,'create-0001')
            updated=self.history.save_study(created['id'],dict(revision=1,name='Revised intent',limits=created['limits'],policy=created['policy']),
                self.session.snapshot['checkpoint'],'save-0001')
            self.assertEqual(updated['revision'],2)
            self.assertEqual(self.history.create_study(body,before,'create-0001'),created)
            snapshot=self.session.snapshot
        self.artifact_owners[-1].close();self.store.close()
        self.store=ProjectStore.open(self.path/'project');self.stores.append(self.store)
        with patch('app.Dataset',side_effect=AssertionError('No Dataset on cold history')), \
             patch('runs.Runs',side_effect=AssertionError('No recovery owner')):
            self.start()
            with self.owner.bound(self.host):
                self.assertEqual(self.session.snapshot,snapshot)
                state=self.history.study(created['id'])
                self.assertEqual(state['study'],updated)
                self.assertTrue(state['revision_history_complete'])
                self.assertEqual(self.store.save(snapshot['checkpoint']),snapshot)
        for table in ('workspace_runs','access_execution_grants','access_execution_consumptions','access_admissions','model_operation_receipts'):
            self.assertEqual(self.host.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_trial_and_cross_study_lineage_checkpoint_preserve_previous_revision(self):
        class OwnedMaterial:
            def __init__(self,origin):self.origin=origin
            def recipe(self,ref,*,verify=False):
                self.ref=ref
                if ref!={'kind':'recipe_material','catalog_id':self.origin,'id':MATERIAL,'sha256':MATERIAL}:
                    raise WorkbenchError('Material differs.')
                return {'ref':copy.deepcopy(ref),'material':{'resource_envelope':dict(attempt_slots=1,
                    admitted_wall_seconds=10,retained_bytes=100,peak_staging_bytes=100)}}
        origin=self.session.snapshot['project_id'];material=OwnedMaterial(origin)
        self.session._validate=lambda records:decode_records(records,materials=material)
        self.history=ProjectHistory(self.session,materials=material)
        body={'name':'Parent Study','limits':dict(attempt_slots=3,admitted_wall_seconds=100,retained_bytes=10000,
            peak_staging_bytes=10000),'policy':policy()}
        with self.owner.bound(self.host):
            parent_study=self.history.create_study(body,self.session.snapshot['checkpoint'],'parent-study')
            child_study=self.history.create_study(dict(body,name='Separate comparison Study'),self.session.snapshot['checkpoint'],'child-study')
            ref={'kind':'recipe_material','catalog_id':origin,'id':MATERIAL,'sha256':MATERIAL}
            parent=self.history.prepare_trial_from_material(parent_study['id'],{'revision':1,'material':ref,'replicate':0},
                self.session.snapshot['checkpoint'],'parent-trial')
            child=self.history.prepare_trial_from_material(child_study['id'],{'revision':1,'material':ref,'replicate':0},
                self.session.snapshot['checkpoint'],'child-trial')
            parent_ref={'catalog_id':origin,'trial_id':parent['id'],'material_sha256':MATERIAL}
            child_ref={'catalog_id':origin,'trial_id':child['id'],'material_sha256':MATERIAL}
            intended=trial('a'*32,'b'*32,parent=parent_ref,baseline=parent_ref)['document']['lineage']['intent']
            value=self.history.record_lineage({'trial':child_ref,'intent':intended},self.session.snapshot['checkpoint'],'lineage-child')
            self.assertEqual(value['intent']['parent'],parent_ref)
            self.assertEqual(value['intent']['baseline'],parent_ref)
            before=self.session.snapshot
            cyclic=dict(intended,parent=child_ref,baseline=None)
            with self.assertRaisesRegex(WorkbenchError,'cycle'):
                self.history.record_lineage({'trial':parent_ref,'intent':cyclic},before['checkpoint'],'lineage-cycle')
            self.assertEqual(self.session.snapshot,before)
            self.assertEqual(self.history.study(child_study['id'])['study']['revision'],2)
            self.assertEqual(self.history.trial(child['id']),child)
        for table in ('model_trials','model_studies','workspace_runs','access_admissions'):
            self.assertEqual(self.host.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_missing_unique_payload_and_fresh_protected_disclosure_are_separate(self):
        raw=b'Unique protected observation\x00\xff';sha=hashlib.sha256(raw).hexdigest()
        declaration={'format':'project_artifact_v1','sha256':sha,'bytes':len(raw)}
        run=legacy_run();run['artifacts']=[{'name':'test-metrics.json','sha256':sha,'bytes':len(raw),'media_type':'application/json','split':'test'}]
        edge={'name':'test-metrics.json','blob':{'sha256':sha,'bytes':len(raw)},'population':'test','role':'model_evidence',
              'preservation':'unique','required_for':['inspection']}
        record=capture_run(run,payloads=[edge]);records=[record,*declarations(record)]
        self.store.commit(records,self.store.snapshot()['checkpoint'],'fixture-history','e'*64)
        self.session.adopt(self.store.snapshot())
        with self.owner.bound(self.host):
            self.assertEqual(self.history.run(run['id'],origin_catalog_id=ORIGIN)['payloads'][0]['availability']['state'],'missing')
            with self.assertRaisesRegex(WorkbenchError,'disclosure'):self.history.artifact(run['id'],'test-metrics.json',origin_catalog_id=ORIGIN)
            self.session.artifacts.publish_bytes(raw,declaration)
            # A malicious portable label cannot turn a protected artifact into
            # present authority. Current test filename/owner split still wins.
            forged=copy.deepcopy(records);forged[0]['document']['payloads'][0]['population']='validation'
            self.store.commit(forged,self.store.snapshot()['checkpoint'],'forged-label','d'*64)
            self.session.adopt(self.store.snapshot())
            with self.assertRaisesRegex(WorkbenchError,'disclosure'):self.history.artifact(run['id'],'test-metrics.json',origin_catalog_id=ORIGIN)
            calls=[];self.history.authorize_disclosure=lambda origin_run,population:calls.append((origin_run['dataset_id'],population))
            self.assertEqual(self.history.artifact(run['id'],'test-metrics.json',origin_catalog_id=ORIGIN),raw)
            self.assertEqual(calls,[(ORIGIN,'test'),(ORIGIN,'test')])
        self.assertEqual(self.host.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

    def test_public_history_hides_frozen_holdout_and_document_segments_need_current_permission(self):
        import base64
        from project_store import _encode
        run=legacy_run();run['source_records']=[{'id':'frozen-example','kind':'text','split':'test',
            'text':'PRIVATE-HOLDOUT-SENTINEL','target':'PRIVATE-TARGET-SENTINEL'}]
        run['evidence_context']={'fixture':'PRIVATE-CONTEXT-SENTINEL'}
        record=capture_run(run,payloads=[]);records=[record,*declarations(record)]
        self.store.commit(records,self.store.snapshot()['checkpoint'],'private-run-fixture','e'*64)
        self.session.adopt(self.store.snapshot())
        with self.owner.bound(self.host):
            result=self.history.run(run['id'],origin_catalog_id=ORIGIN,offset=0,limit=1)
            self.assertNotIn('PRIVATE-',json.dumps(result))
            self.assertNotIn('source_records',result['run']);self.assertNotIn('evidence_context',result['run'])
            descriptor=self.history.run_document_descriptor(run['id'],origin_catalog_id=ORIGIN)
            self.assertEqual(descriptor,{'sha256':hashlib.sha256(_encode(record['document'])).hexdigest(),
                                         'bytes':len(_encode(record['document']))})
            with self.assertRaisesRegex(WorkbenchError,'disclosure'):
                self.history.run_document_segment(run['id'],descriptor['sha256'],origin_catalog_id=ORIGIN)
            self.history.authorize_disclosure=lambda *_:None
            parts=[];offset=0
            while True:
                segment=self.history.run_document_segment(run['id'],descriptor['sha256'],offset,limit=97,origin_catalog_id=ORIGIN)
                parts.append(base64.b64decode(segment['base64']))
                if segment['next_offset'] is None:break
                offset=segment['next_offset']
            self.assertEqual(b''.join(parts),_encode(record['document']))
            with self.assertRaisesRegex(WorkbenchError,'changed'):
                self.history.run_document_segment(run['id'],'0'*64,origin_catalog_id=ORIGIN)
        # Permission is process-local; a new owner over the same facts has none.
        cold=ProjectHistory(self.session,materials=Materials())
        with self.owner.bound(self.host),self.assertRaisesRegex(WorkbenchError,'disclosure'):
            cold.run_document_segment(run['id'],descriptor['sha256'],origin_catalog_id=ORIGIN)

    def test_disclosure_fact_is_actor_bound_and_never_restores_current_permission(self):
        from access import AccessError
        raw=b'Unique holdout observation';sha=hashlib.sha256(raw).hexdigest()
        run=legacy_run();run['artifacts']=[{'name':'test-metrics.json','sha256':sha,'bytes':len(raw),'media_type':'application/json','split':'test'}]
        edge={'name':'test-metrics.json','blob':{'sha256':sha,'bytes':len(raw)},'population':'test','role':'model_evidence',
              'preservation':'unique','required_for':['inspection']}
        archived=capture_run(run,payloads=[edge]);records=[archived,*declarations(archived)]
        self.store.commit(records,self.store.snapshot()['checkpoint'],'disclosure-fixture','d'*64)
        self.session.adopt(self.store.snapshot())
        with self.owner.bound(self.host):
            first=self.host.access.issue({'label':'Current disclosure authority','scopes':['inspect','expose-holdout']})
            second=self.host.access.issue({'label':'Different current actor','scopes':['inspect','expose-holdout']})
            inspect_only=self.host.access.issue({'label':'Inspect only','scopes':['inspect']})
        body={'origin_catalog_id':ORIGIN,'reason':'Compare this exact retained holdout population'}
        before=self.session.snapshot['checkpoint']
        with self.host.access.bind(inspect_only['token']),self.assertRaises(AccessError):
            self.history.record_disclosure(run['id'],body,before,'disclosure-0001')
        with self.host.access.bind(first['token']):
            fact=self.history.record_disclosure(run['id'],body,before,'disclosure-0001')
            self.assertEqual(fact['actor_id'],first['identity']['actor_id'])
            self.assertEqual(fact['payload_set_sha256'],self.history.payload_set_sha256(run['id'],origin_catalog_id=ORIGIN))
            self.assertEqual(self.history.record_disclosure(run['id'],body,before,'disclosure-0001'),fact)
            self.assertEqual(self.history.run(run['id'],origin_catalog_id=ORIGIN)['disclosures'],[fact])
            self.assertNotIn('exposure_events',self.history.run(run['id'],origin_catalog_id=ORIGIN)['run'])
        with self.host.access.bind(second['token']),self.assertRaises(WorkbenchError):
            self.history.record_disclosure(run['id'],body,before,'disclosure-0001')
        self.session.artifacts.publish_bytes(raw,{'format':'project_artifact_v1','sha256':sha,'bytes':len(raw)})
        with self.host.access.bind(first['token']),self.assertRaisesRegex(WorkbenchError,'disclosure'):
            self.history.artifact(run['id'],'test-metrics.json',origin_catalog_id=ORIGIN)
        snapshot=self.session.snapshot
        self.artifact_owners[-1].close();self.store.close()
        self.store=ProjectStore.open(self.path/'project');self.stores.append(self.store);self.start()
        with self.owner.bound(self.host):
            self.assertEqual(self.session.snapshot,snapshot)
            self.assertEqual(self.history.disclosure_facts(run['id'],origin_catalog_id=ORIGIN),[fact])
            with self.assertRaisesRegex(WorkbenchError,'disclosure'):
                self.history.artifact(run['id'],'test-metrics.json',origin_catalog_id=ORIGIN)

    def test_disclosure_snapshot_survives_payload_growth_and_replacement_without_new_permission(self):
        from project_fork_composition import artifact_plan
        run=legacy_run();run.update(state='running',finished_at=None)
        run['progress']['stage']='running'
        def artifact(raw,name='test-metrics.json'):
            item=dict(name=name,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),media_type='application/json',split='test')
            edge=dict(name=name,blob={k:item[k] for k in ('sha256','bytes')},population='test',role='model_evidence',
                preservation='unique',required_for=['inspection'])
            self.session.artifacts.publish_bytes(raw,dict(format='project_artifact_v1',**edge['blob']))
            return item,edge
        old_item,old_edge=artifact(b'{"partial":1}')
        run['artifacts']=[old_item]
        original=capture_run(run,payloads=[old_edge])
        self.store.commit([original,*declarations(original)],self.store.snapshot()['checkpoint'],'growing-run','d'*64)
        self.session.adopt(self.store.snapshot())
        body=dict(origin_catalog_id=ORIGIN,reason='Inspect the exact current observation')
        with self.owner.bound(self.host),patch('runs.Runs',side_effect=AssertionError('No Run recovery in disclosure')):
            first=self.history.record_disclosure(run['id'],body,self.session.snapshot['checkpoint'],'disclose-running')
            self.assertEqual(first['format'],'project_disclosure_v2')
            saved=copy.deepcopy(self.session.snapshot['records'])
            observation=next(r for r in saved if r['family']=='run_observation')
            self.assertEqual(observation['document']['observation'],original['document'])
            legacy={k:v for k,v in first.items() if k!='observation_sha256'}
            legacy['format']='project_disclosure_v1'
            self.assertTrue(validate_operation_result('history.disclose',legacy,saved))
            replacement,replacement_edge=artifact(b'{"complete":2}')
            added,added_edge=artifact(b'{"late":3}','late-output.json')
            run.update(state='completed',finished_at='2026-10-22T12:01:00+00:00',artifacts=[replacement,added])
            run['progress']['stage']='completed'
            grown=capture_run(run,payloads=[replacement_edge,added_edge])
            merged={(r['family'],r['id']):r for r in [*saved,grown,*declarations(grown)]}
            candidate=list(merged.values())
            decode_records(candidate,materials=Materials())
            self.assertTrue(validate_operation_result('history.disclose',first,candidate))
            with self.assertRaisesRegex(WorkbenchError,'payload set'):
                validate_operation_result('history.disclose',legacy,candidate)
            self.store.commit(candidate,self.session.snapshot['checkpoint'],'complete-growing-run','e'*64)
            self.session.adopt(self.store.snapshot())
            self.assertEqual(self.history.disclosure_facts(run['id'],origin_catalog_id=ORIGIN),[first])
            second=self.history.record_disclosure(run['id'],body,self.session.snapshot['checkpoint'],'disclose-completed')
            self.assertNotEqual(second['observation_sha256'],first['observation_sha256'])
            self.assertNotEqual(second['payload_set_sha256'],first['payload_set_sha256'])
            # A snapshot is science evidence, never a restored local capability.
            cold=ProjectHistory(self.session,materials=Materials())
            with self.assertRaisesRegex(WorkbenchError,'disclosure'):
                cold.artifact(run['id'],'test-metrics.json',origin_catalog_id=ORIGIN)
            current=self.session.snapshot['records']
            forged=copy.deepcopy(first);forged['payload_set_sha256']='0'*64
            with self.assertRaisesRegex(WorkbenchError,'payload set'):
                validate_operation_result('history.disclose',forged,current)
            foreign=copy.deepcopy(observation)
            foreign['document']['observation']['run']['request_sha256']='9'*64
            from project_store import _encode as canonical
            sha=hashlib.sha256(canonical(foreign['document']['observation'])).hexdigest()
            foreign['id']=foreign['document']['sha256']=sha
            forged=dict(first,observation_sha256=sha)
            with self.assertRaisesRegex(WorkbenchError,'immutable identity'):
                validate_operation_result('history.disclose',forged,[*current,foreign])
            foreign_payload=copy.deepcopy(observation)
            next(edge for edge in foreign_payload['document']['observation']['payloads']
                 if edge['name']=='test-metrics.json')['blob']=copy.deepcopy(added_edge['blob'])
            sha=hashlib.sha256(canonical(foreign_payload['document']['observation'])).hexdigest()
            foreign_payload['id']=foreign_payload['document']['sha256']=sha
            # These bytes have a real global declaration, but belong to a
            # different output than the observed Run inventory names here.
            with self.assertRaisesRegex(WorkbenchError,'Run artifact closure'):
                decode_records([*current,foreign_payload],materials=Materials())
            missing=[r for r in current if not (r['family']=='project_artifact' and r['id']==old_item['sha256'])]
            with self.assertRaisesRegex(WorkbenchError,'artifact declaration'):
                decode_records(missing,materials=Materials())
            # The exact old snapshot bytes stay unique even if its retained
            # edge is labelled regenerable; weak labels cannot discard science.
            weaker=copy.deepcopy(current)
            for record in weaker:
                if record['family']=='run_observation':
                    for edge in record['document']['observation']['payloads']:edge['preservation']='regenerable'
            plan=artifact_plan(weaker)
            self.assertEqual(next(v['preservation'] for v in plan if v['declaration']['sha256']==old_item['sha256']),'unique')
        self.assertEqual(self.host.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)

    def test_sql_analysis_uses_supplied_origin_json_and_no_active_run_row(self):
        from test_retained_analysis import fixture, EVALUATION, RUN
        from retained_analysis import query_history
        body,evidence=fixture()
        run={'id':RUN,'dataset_id':ORIGIN,'state':'completed','artifacts':[{'name':'model-evidence.json','sha256':EVALUATION}],
             'metrics':{'history':[{'epoch':1,'validation':{'accuracy':0.0,'examples':2}},
                                   {'epoch':2,'validation':{'accuracy':0.5,'examples':2}}]}}
        with self.owner.bound(self.host):
            result=query_history(self.host.db,run,evidence,body,authorize=self.host.access.require)
        self.assertEqual(result['provenance']['catalog_id'],ORIGIN)
        self.assertEqual([point['value'] for point in result['curve']],[0.0,0.5])
        self.assertEqual(self.host.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],0)


from test_model_definitions import CapturedModelCase


class ProjectHistoryActualOwnerTests(CapturedModelCase):
    """Actual captured composition/admission proof imported into a fresh inert DB."""
    def test_cold_actual_composed_proof_keeps_origin_without_live_authority(self):
        from experiments import Experiments
        from project_material import ProjectMaterial
        import psycopg
        from psycopg import sql
        self.dataset.models=self.models
        studies=Experiments(self.dataset)
        with self.owner.bound(self.dataset):
            model=self.models.publish(self.models.create(self.model_body)['id'],{'revision':1})
            value=studies.create({'name':'Retained exact source proof','limits':dict(attempt_slots=3,
                admitted_wall_seconds=1000,retained_bytes=10**8,peak_staging_bytes=10**8),'policy':policy()})
            prepared=studies.prepare_trial(value['id'],{'request_key':'actual-history-prepare','revision':1,
                'graph_id':self.graph['id'],'graph_revision':self.graph['revision'],'model':model['ref'],'replicate':0})
            value=studies._study(value['id'])
            studies.continue_study(value['id'],{'request_key':'actual-history-open','revision':value['revision'],'admission_epoch':0})
            grant=studies.approve(value['id'],{'trial_id':prepared['id'],'expected_material_sha256':prepared['material']['sha256'],
                'consumer_actor_id':self.agent['identity']['actor_id']})
            value=studies._study(value['id'])
        with self.dataset.access.bind(self.agent['token']),patch.object(self.dataset.runs,'_start'):
            admitted=studies.admit(value['id'],{'request_key':'actual-history-admit','revision':value['revision'],
                'admission_epoch':value['admission_epoch'],'trial_id':prepared['id'],'approval_id':grant['id']})
        with self.owner.bound(self.dataset):
            self.dataset.runs.cancel(admitted['run']['id'])
            run=copy.deepcopy(self.dataset.runs._load(admitted['run']['id']))
            value=studies._study(value['id']);reservation=studies._reservations(value['id'])[0]
            composition=self.dataset.pipelines.recipe_material(prepared['material'],verify=True)
            consumption=dict(self.dataset.db.execute('SELECT * FROM access_execution_consumptions WHERE run_id=%s',(run['id'],)).fetchone())
            admission=dict(self.dataset.db.execute('SELECT * FROM access_admissions WHERE id=%s',(run['admission_id'],)).fetchone())
            admission['effects']=json.loads(admission.pop('effects_json'))
            memberships=[{'revision':row['revision'],'trial_ids':json.loads(row['document'])['trial_ids']}
                for row in self.dataset.db.execute('SELECT revision,document FROM model_study_memberships WHERE study_id=%s ORDER BY revision',(value['id'],))]
        root=self.path/'portable-history';store=ProjectStore.create(root,'Actual cold history','new','f'*64)
        self.addCleanup(store.close)
        artifacts=ProjectArtifacts(store);self.addCleanup(artifacts.close)
        view=SimpleNamespace(snapshot={'project_id':store.snapshot()['project_id'],'records':[]},artifacts=artifacts,check=lambda:None)
        material=ProjectMaterial(view)
        model_record=material.capture_model_material(model,self.models.path)
        recipe_record=material.capture_recipe_material(composition,self.dataset.pipelines.material_path)
        runtime_ref=composition['material']['runtime']
        runtime_record=material.capture_runtime({'ref':runtime_ref,'descriptor':None,'environment':run['material']['runtime'],'manifest':None})
        records=[model_record,recipe_record,runtime_record,*material.declarations(model_record),*material.declarations(recipe_record)]
        snapshot=json.loads((self.dataset.pipelines.material_path/composition['ref']['sha256']/'recipe.json').read_bytes())
        capture_map={item['path']:item['blob'] for item in snapshot['capture_paths']}
        edges=[]
        for name,item in run['material']['captures'].items():
            blob=capture_map[name]
            raw=(self.dataset.pipelines.material_path/composition['ref']['sha256']/blob['name']).read_bytes()
            declaration={'format':'project_artifact_v1','sha256':item['sha256'],'bytes':item['bytes']}
            artifacts.publish_bytes(raw,declaration)
            edges.append({'name':name,'blob':dict(item),'population':'unknown','role':'execution_capture',
                'preservation':'unique','required_for':['execution_proof']})
        archived=capture_run(run,admission_proof={'grant':grant,'consumption':consumption,'admission':admission},payloads=edges)
        origin=self.dataset.db.dataset_id
        study_doc={'format':FAMILY_FORMATS['study_history'],'origin_catalog_id':origin,'study':value,'memberships':memberships,
            'policies':[{'ref':value['policy'],'policy':policy()}],'reservations':[reservation],'operations':[],
            'revisions':[copy.deepcopy(value)],'audit':[],'revision_history_complete':False}
        trial_doc={'format':FAMILY_FORMATS['trial_history'],'origin_catalog_id':origin,'trial':prepared,'lineage':None}
        records.extend([envelope('study_history',origin,value['id'],study_doc),
            envelope('trial_history',origin,prepared['id'],trial_doc),archived,*declarations(archived)])
        records=list({(item['family'],item['id']):item for item in records}.values())
        view.snapshot={'project_id':store.snapshot()['project_id'],'records':records}
        with patch('app.Dataset',side_effect=AssertionError('No Dataset on imported history')), \
             patch('runs.Runs',side_effect=AssertionError('No imported recovery owner')), \
             patch('subprocess.Popen',side_effect=AssertionError('No imported process')):
            decode_records(records,materials=material)
            store.commit(records,store.snapshot()['checkpoint'],'actual-history','e'*64)
            db=Metadata(self.path/'fresh-inert-db',dsn=os.environ['TULDOK_DATABASE_URL'])
            self.addCleanup(db.close)
            manifest=json.loads((db.path/'.tuldok.json').read_bytes())
            def remove_projection():
                db.close()
                with psycopg.connect(connection_info(),autocommit=True) as connection:
                    connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier('catalog_'+manifest['dataset_id'])))
            self.addCleanup(remove_projection)
            host=SimpleNamespace(db=db,access=Access(db,db.path));owner=ExplicitOwnerFixture.bootstrap(host)
            session=ProjectSession(store,db,host.access,artifacts,validate_records=lambda values:decode_records(values,materials=material))
            history=ProjectHistory(session,materials=material,authorize_disclosure=lambda *_:None)
            with owner.bound(host):
                result=history.run(run['id'],origin_catalog_id=origin)
                self.assertNotIn('spec',result['run'])
                descriptor=history.run_document_descriptor(run['id'],origin_catalog_id=origin)
                import base64
                parts=[];offset=0
                while True:
                    segment=history.run_document_segment(run['id'],descriptor['sha256'],offset,origin_catalog_id=origin)
                    self.assertEqual(segment['offset'],offset)
                    chunk=base64.b64decode(segment['base64'],validate=True);parts.append(chunk)
                    self.assertLessEqual(len(chunk),262144)
                    if segment['next_offset'] is None:break
                    self.assertEqual(segment['next_offset'],offset+len(chunk));offset=segment['next_offset']
                full=b''.join(parts)
                self.assertEqual(len(full),descriptor['bytes'])
                self.assertEqual(hashlib.sha256(full).hexdigest(),descriptor['sha256'])
                self.assertEqual(json.loads(full)['run']['spec'],run['spec'])
                self.assertFalse(result['execution_available'])
                self.assertEqual(history.study(value['id'],origin_catalog_id=origin)['charged'],reservation['envelope'])
                self.assertEqual(history.artifact(run['id'],'input/sample',origin_catalog_id=origin),self.input)
                self.assertEqual(material.composition_closure(prepared['material'])['execution_material'],run['material'])
                malformed=copy.deepcopy(records)
                next(item for item in malformed if item['family']=='run_history')['document']['admission_proof']['consumption']['request_sha256']='0'*64
                with self.assertRaises(WorkbenchError):decode_records(malformed,materials=material)
            for table in ('workspace_runs','access_admissions','access_execution_grants','access_execution_consumptions','model_operation_receipts'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)


if __name__=='__main__':unittest.main()
