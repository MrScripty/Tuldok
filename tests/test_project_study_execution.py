"""Current Study epochs and retained accounting without imported runtime rows.

Control tests use real disposable PostgreSQL and the actual canonical owners.
Host execution cases, when added, run only under a coordinated source freeze.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from access import Access
from auth_helpers import ExplicitOwnerFixture
from experiments import Experiments, validate_retained_reservation
from metadata import Metadata, connection_info
from project_history import capture_run, declarations
from project_projection import ProjectProjection
from project_session import operation_records
from project_store import ProjectStore
from project_study_execution import ProjectStudyExecution, validate_operation_result
from test_project_history import legacy_run, policy, study, trial, Materials, ORIGIN
from workbench import WorkbenchError, encode


class CandidatePreparationContractTests(unittest.TestCase):
    def test_intent_binds_exact_candidate_and_study_revision_without_local_authority(self):
        from project_history import HistoryFacts
        from pipeline import digest
        candidate=dict(id='6'*32,study_id='3'*32,diagnostic='Exact authored selection')
        fact=dict(format='project_candidate_preparation_intent_v1',origin_catalog_id=ORIGIN,study_id='3'*32,
            study_revision=4,candidate=dict(kind='candidate',catalog_id=ORIGIN,id=candidate['id'],sha256=digest(candidate)),
            actor_id='5'*32,request_sha256='a'*64,root='explicit',directory='prepared',runtime_snapshot_sha256='b'*64)
        facts=HistoryFacts();facts.candidates[(ORIGIN,candidate['id'])]=dict(candidate=candidate)
        facts.studies[(ORIGIN,'3'*32)]=dict(revisions=[dict(revision=4)])
        operation='study_execution.prepare_package_intent'
        with patch('project_study_execution._facts',return_value=facts):
            self.assertTrue(validate_operation_result(operation,fact,[]))
            for change in (dict(fact,study_revision=5),dict(fact,candidate=dict(fact['candidate'],sha256='c'*64)),
                    dict(fact,current_local=True),dict(fact,grant={'token':'secret'})):
                with self.subTest(change=change),self.assertRaises(WorkbenchError):
                    validate_operation_result(operation,change,[])

    def test_archived_input_facade_requires_new_disclosure_and_never_constructs_runs(self):
        from project_history import ProjectHistory,HistoryFacts
        from project_study_execution import _PreparationRuns
        run=legacy_run();run['exposure_events']=[{'historical':'This fact grants nothing'}]
        facts=HistoryFacts();facts.runs[(ORIGIN,run['id'])]=dict(origin_catalog_id=ORIGIN,run=run,payloads=[])
        session=SimpleNamespace(access=SimpleNamespace(require=lambda *a,**k:None),artifacts=None,
            snapshot=dict(records=[],project_id=ORIGIN))
        history=ProjectHistory(session,materials=Materials());history._facts=lambda:facts
        adapter=SimpleNamespace(history=history,origin=ORIGIN,session=session)
        facade=_PreparationRuns(adapter)
        with patch('runs.Runs',side_effect=AssertionError('Archived package input allocated Runs')):
            with self.assertRaisesRegex(WorkbenchError,'Current explicit disclosure'):facade._load(run['id'])
            seen=[];history.authorize_disclosure=lambda selected,population:seen.append((selected['id'],population))
            self.assertEqual(facade._load(run['id']),run)
            self.assertEqual(seen,[(run['id'],'unknown')])
            self.assertFalse(hasattr(facade,'_admit'));self.assertFalse(hasattr(facade,'_start'))

    def test_native_directory_write_follows_ack_hook_and_project_failure_preserves_it(self):
        import candidate_packages as packages
        from test_candidate_packages import fixture
        manifest,blobs=fixture();package=packages.create_package(manifest,blobs)
        descriptor=packages.decode(blobs['runtime.json'])['snapshot']
        candidate=dict(ref=manifest['candidate'],candidate=packages.decode(blobs['candidate-decision.json']))
        with tempfile.TemporaryDirectory(prefix='tuldok-package-publication-') as directory:
            root=Path(directory);root_fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            self.addCleanup(os.close,root_fd);events=[]
            def opened(body):
                self.assertTrue((root/'prepared'/'project.json').is_file())
                events.append('source-read');raise RuntimeError('Controlled failure after directory publication')
            access=SimpleNamespace(require=lambda *a,**k:SimpleNamespace(actor_id='5'*32))
            dataset=SimpleNamespace(db=SimpleNamespace(in_transaction=False,dataset_id=descriptor['catalog_id']),
                path=root,projects=SimpleNamespace(roots={'explicit':(root_fd,[os.fstat(root_fd).st_dev,os.fstat(root_fd).st_ino])},open=opened),
                runs=SimpleNamespace(artifact=lambda *args:(package,'application/zip')))
            studies=SimpleNamespace(db=dataset.db,access=access,dataset=dataset,lock=threading.RLock(),
                _receipt=lambda *args:None,_study=lambda _:dict(revision=1),_expected=lambda *args:None,
                candidate=lambda _:candidate)
            def before_write():
                self.assertFalse((root/'prepared').exists());events.append('acknowledged-start')
            publication=SimpleNamespace(runtime_snapshot=descriptor,before_write=before_write)
            body=dict(request_key='controlled-prepare',revision=1,candidate_id=manifest['candidate']['id'],
                root='explicit',directory='prepared',runtime_snapshot_sha256=descriptor['manifest_sha256'],
                package_run_id='7'*32,package_sha256=packages.sha(package))
            with self.assertRaisesRegex(RuntimeError,'after directory publication'):
                packages._prepare_operation(studies,candidate['candidate']['study_id'],body,'verify',publication=publication)
            self.assertEqual(events,['acknowledged-start','source-read'])
            self.assertTrue((root/'prepared'/'project.json').is_file())


class StudyExecutionCodecTests(unittest.TestCase):
    def test_admission_has_only_exact_reservation_and_references(self):
        value=trial('9'*32,'3'*32)['document']['trial'];composition=Materials().recipe(value['material'])
        charge=composition['material']['resource_envelope']
        reservation=dict(id='e'*32,study_id='3'*32,admission_epoch=1,request_key='admission-0001',actor_id='5'*32,
            trial_id=value['id'],parent_run_id=None,run_id='7'*32,request_sha256='c'*64,
            material_sha256=value['material']['sha256'],envelope=charge,state='reserved',settled=None)
        run=dict(id='7'*32,actor_id='5'*32,request_sha256='c'*64,parent_run_id=None,
                 approval_material_sha256=value['material']['sha256'])
        validate_retained_reservation(reservation,trial=value,composition=composition,run=run)
        result=dict(format='project_study_admission_v1',origin_catalog_id=ORIGIN,
            study_id=reservation['study_id'],trial_id=value['id'],run_id=reservation['run_id'],reservation=reservation)
        self.assertTrue(validate_operation_result('study_execution.admit',result))
        for change in ({'run':{'token':'secret'}},{'run_id':'8'*32}):
            with self.subTest(change=change),self.assertRaises(WorkbenchError):
                validate_operation_result('study_execution.admit',dict(result,**change))
        changed=copy.deepcopy(result);changed['reservation']['envelope']['secret']='secret'
        with self.assertRaises(WorkbenchError):validate_operation_result('study_execution.admit',changed)

    def test_approval_canonical_fact_is_inert_and_never_contains_a_local_grant_wrapper(self):
        fact=dict(format='project_study_approval_v1',origin_catalog_id=ORIGIN,study_id='3'*32,
            trial_id='9'*32,approval_id='a'*32,material_sha256='b'*64,
            consumer_actor_id='c'*32,approver_actor_id='d'*32,created_at=1,expires_at=601)
        self.assertTrue(validate_operation_result('study_execution.approve',fact))
        for change in ({'current_local':True},{'grant':{'token':'secret'}},{'expires_at':4000}):
            with self.subTest(change=change),self.assertRaises(WorkbenchError):
                validate_operation_result('study_execution.approve',dict(fact,**change))

    def test_project_reservation_uses_retained_material_and_shared_proof_validation(self):
        value=trial('9'*32,'3'*32)['document']['trial'];composition=Materials().recipe(value['material'])
        reservation=dict(id='e'*32,study_id='3'*32,admission_epoch=1,request_key='admission-0001',actor_id='5'*32,
            trial_id=value['id'],parent_run_id=None,run_id='7'*32,request_sha256='c'*64,
            material_sha256=value['material']['sha256'],envelope=composition['material']['resource_envelope'],
            state='reserved',settled=None)
        run=dict(id='7'*32,actor_id='5'*32,request_sha256='c'*64,parent_run_id=None,
                 approval_material_sha256=value['material']['sha256'])
        row={key:reservation[key] for key in ('id','study_id','actor_id','request_key','request_sha256','trial_id','run_id')}
        row['document']=json.dumps(reservation)
        owner=Experiments.__new__(Experiments);owner.trial=lambda _:value;owner._run_fact=lambda _:run
        owner.dataset=SimpleNamespace(project_study_execution=SimpleNamespace(materials=Materials()),
            pipelines=SimpleNamespace(recipe_material=lambda _:(_ for _ in ()).throw(
                AssertionError('Project settlement crossed into host-authorized material owner'))))
        self.assertEqual(owner._reservation(row),reservation)
        changed=copy.deepcopy(reservation);changed['envelope']['retained_bytes']+=1
        row['document']=json.dumps(changed)
        with self.assertRaises(WorkbenchError):owner._reservation(row)

    def test_approval_binds_exact_owner_audit_and_abandon_cannot_activate_pending_epoch(self):
        from project_history import HistoryFacts, _audit
        value=trial('9'*32,'3'*32)['document']['trial']
        fact=dict(format='project_study_approval_v1',origin_catalog_id=ORIGIN,study_id='3'*32,
            trial_id=value['id'],approval_id='a'*32,material_sha256=value['material']['sha256'],
            consumer_actor_id='c'*32,approver_actor_id='d'*32,created_at=1,expires_at=601)
        details={key:fact[key] for key in ('trial_id','material_sha256','approval_id','consumer_actor_id','created_at','expires_at')}
        audit=dict(actor_id=fact['approver_actor_id'],action='studies.approve',target=fact['study_id'],
            details=details,result='success',occurred_at='1970-01-01T00:00:01+00:00')
        _audit([audit])
        facts=HistoryFacts();facts.studies[(ORIGIN,fact['study_id'])]=dict(audit=[audit])
        facts.trials[(ORIGIN,value['id'])]=dict(trial=value)
        # Supply only the already-decoded closure lookup; the actual binding
        # policy and the common execution approval validator remain real.
        with patch('project_study_execution._facts',return_value=facts):
            self.assertTrue(validate_operation_result('study_execution.approve',fact,[]))
            for field,changed in (('consumer_actor_id','e'*32),('approver_actor_id','e'*32),
                    ('expires_at',602),('material_sha256','f'*64)):
                with self.subTest(field=field),self.assertRaises(WorkbenchError):
                    validate_operation_result('study_execution.approve',dict(fact,**{field:changed}),[])
        adapter=ProjectStudyExecution.__new__(ProjectStudyExecution)
        adapter._dirty={'3'*32};adapter._revisions={'3'*32:{2:{'revision':2}}}
        adapter._pending_epochs={'3'*32:99};adapter._epochs={'4'*32:2}
        adapter._package_records=[]
        adapter.abandon_pending()
        self.assertEqual(adapter._epochs,{'4'*32:2})
        self.assertFalse(adapter._dirty);self.assertFalse(adapter._revisions);self.assertFalse(adapter._pending_epochs)

    def test_old_reservations_contribute_full_charges_but_are_not_local_children(self):
        historical=dict(id='e'*32,run_id='7'*32,state='unknown',settled=None,
            envelope=dict(attempt_slots=2,admitted_wall_seconds=70,retained_bytes=800,peak_staging_bytes=900))
        class ReadOnlyRows:
            def execute(self,query,args=()):
                if query.startswith('SELECT * FROM model_attempt_reservations'):return []
                raise AssertionError(query)
        adapter=SimpleNamespace(historical_reservations=lambda _: [copy.deepcopy(historical)],local_run_ids=lambda:set())
        owner=Experiments.__new__(Experiments)
        owner.db=ReadOnlyRows();owner.dataset=SimpleNamespace(project_study_execution=adapter,
            runs=SimpleNamespace(_load=lambda _:(_ for _ in ()).throw(AssertionError('Historical Run reached live resolver'))))
        values=owner._reservations('3'*32)
        self.assertEqual(owner._totals(values),historical['envelope'])
        self.assertEqual(owner._children_ceased(values),(True,False))
        self.assertEqual(values,[historical])


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ProjectStudyControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-study-execution-')
        self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.databases=[];self.projections=[];self.addCleanup(self.cleanup)
        host_db=self.metadata('host');self.host=SimpleNamespace(db=host_db,access=Access(host_db,host_db.path))
        self.owner=ExplicitOwnerFixture.bootstrap(self.host)
        self.store=ProjectStore.create(self.root/'project','Current Study intent','study-fixture','f'*64)
        self.addCleanup(self.store.close)
        self.open_projection()

    def metadata(self,name,*,project_id=None):
        kwargs={} if project_id is None else dict(dataset_id=project_id,projection_id=uuid.uuid4().hex)
        db=Metadata(self.root/name,**kwargs);self.databases.append(db);return db

    def open_projection(self):
        db=self.metadata('projection-'+uuid.uuid4().hex,project_id=self.store.snapshot()['project_id'])
        with self.owner.bound(self.host),patch('runs.Runs',side_effect=AssertionError('Inert Study Open constructed Runs')):
            projection=ProjectProjection(self.store,db,self.host.access,{})
            adapter=getattr(projection,'study_execution',None)
            if adapter is None:
                adapter=ProjectStudyExecution(projection,projection.execution);adapter.restore_authoring()
        self.projections.append(projection);self.projection=projection;self.adapter=adapter

    def cleanup(self):
        import psycopg
        from psycopg import sql
        for projection in reversed(self.projections):
            try:projection.close()
            except BaseException:
                # No test here admits a worker; cleanup only this fixture's DB
                # and artifact handles even after an asserted rollback failure.
                projection.artifacts.close();projection.db.close()
        for db in reversed(self.databases):db.close()
        with psycopg.connect(connection_info(),autocommit=True) as connection:
            for db in self.databases:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(db.schema)))

    def create_study(self):
        body=dict(name='Persistent scientific intent',limits=dict(attempt_slots=3,admitted_wall_seconds=100,
            retained_bytes=10000,peak_staging_bytes=10000),policy=policy())
        return self.projection.history.create_study(body,self.projection.session.snapshot['checkpoint'],'study-create-0001')

    def assert_no_runtime_authority(self):
        for table in ('workspace_runs','model_attempt_reservations','access_admissions','access_execution_grants',
                      'access_execution_consumptions','access_actors','access_credentials'):
            self.assertEqual(self.projection.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
        self.assertIsNone(self.projection.execution._runs)

    def test_canonical_metadata_projects_before_background_read_and_continue_never_constructs_runs(self):
        with self.owner.bound(self.host),patch('runs.Runs',side_effect=AssertionError('Continue constructed Runs')):
            value=self.create_study()
            self.assertEqual(self.adapter.studies._study(value['id']),value)
            opened=self.adapter.continue_study(value['id'],dict(revision=1,admission_epoch=0),
                self.projection.session.snapshot['checkpoint'],'study-continue-0001')
            self.assertTrue(self.adapter.epoch_current(opened));self.assertEqual(opened['admission_epoch'],1)
            saved=self.projection.history.save_study(value['id'],dict(revision=opened['revision'],name='New exact intent',
                limits=opened['limits'],policy=opened['policy']),self.projection.session.snapshot['checkpoint'],'study-save-0001')
            self.assertEqual(self.adapter.studies._study(value['id']),saved)
            self.assertTrue(self.adapter.epoch_current(saved))
            self.assert_no_runtime_authority()

    def test_cold_open_keeps_epoch_fact_inert_and_requires_fresh_explicit_continue(self):
        with self.owner.bound(self.host):
            value=self.create_study()
            opened=self.adapter.continue_study(value['id'],dict(revision=1,admission_epoch=0),
                self.projection.session.snapshot['checkpoint'],'study-continue-0001')
            checkpoint=self.projection.session.snapshot['checkpoint']
        self.projection.close();self.open_projection()
        with self.owner.bound(self.host),patch.object(self.projection.execution,'_local_owner',side_effect=AssertionError('Historical epoch activated owner')):
            self.assertEqual(self.adapter.studies._study(value['id']),opened)
            self.assertFalse(self.adapter.epoch_current(opened));self.assert_no_runtime_authority()
            before=self.projection.session.snapshot
            with self.assertRaisesRegex(WorkbenchError,'historical Continue'):
                self.adapter.continue_study(value['id'],dict(revision=1,admission_epoch=0),checkpoint,'study-continue-0001')
            with self.assertRaisesRegex(WorkbenchError,'Explicitly continue'):
                self.adapter.admit(value['id'],dict(revision=opened['revision'],admission_epoch=opened['admission_epoch'],trial_id='9'*32),
                    checkpoint,'new-attempt-0001')
            self.assertEqual(self.projection.session.snapshot,before)
            continued=self.adapter.continue_study(value['id'],dict(revision=opened['revision'],admission_epoch=opened['admission_epoch']),
                checkpoint,'study-continue-0002')
            self.assertEqual(continued['admission_epoch'],opened['admission_epoch']+1)
            self.assertEqual(continued['limits'],opened['limits']);self.assertTrue(self.adapter.epoch_current(continued))
            self.assert_no_runtime_authority()

    def test_multiple_source_revisions_in_one_transaction_survive_and_rollback_does_not_activate_epoch(self):
        with self.owner.bound(self.host):
            value=self.create_study();before=self.projection.session.snapshot
            with self.assertRaisesRegex(RuntimeError,'authored rollback'):
                with self.projection.db.transaction():
                    changed=copy.deepcopy(value);changed['name']='Must roll back'
                    self.adapter.studies._write(changed,'studies.save')
                    self.adapter._pending_epochs[value['id']]=99
                    raise RuntimeError('authored rollback')
            self.assertEqual(self.projection.session.snapshot,before)
            self.assertFalse(self.adapter._dirty);self.assertFalse(self.adapter._epochs)
            with self.projection.db.transaction():
                current=copy.deepcopy(value);current['name']='Observed revision two'
                current=self.adapter.studies._write(current,'studies.save')
                current['name']='Observed revision three'
                current=self.adapter.studies._write(current,'studies.save')
            doc=self.projection.history._facts().studies[(self.adapter.origin,value['id'])]
            self.assertEqual([item['revision'] for item in doc['revisions']],[1,2,3])
            self.assertEqual([item['name'] for item in doc['revisions']],
                ['Persistent scientific intent','Observed revision two','Observed revision three'])
            self.assertEqual(doc['study'],current);self.assert_no_runtime_authority()


if __name__=='__main__':unittest.main()


# Reuse only the authored neutral fixture helpers, never its test methods.
import test_project_execution as _run_fixtures


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL and coordinated host-source freeze')
class ProjectStudyCustodyTests(unittest.TestCase):
    setUp=_run_fixtures.ProjectRunCustodyTests.setUp
    metadata=_run_fixtures.ProjectRunCustodyTests.metadata
    cleanup=_run_fixtures.ProjectRunCustodyTests.cleanup
    checkpoint=_run_fixtures.ProjectRunCustodyTests.checkpoint
    record=_run_fixtures.ProjectRunCustodyTests.record
    await_drained=_run_fixtures.ProjectRunCustodyTests.await_drained

    def prepare_study(self):
        from pipeline import digest
        materials=self.projection.materials
        body=dict(name='Captured neutral Study model',kind='captured_source',
            task=dict(kind='task',catalog_id=self.db.dataset_id,id='neutral.bytes',revision=1,
                      sha256=digest({'format':'authored_neutral_task_v1'})),
            specification={'format':'authored_neutral_model_v1'},
            source_selector=dict(project_id=self.manifest['id'],recipe_id='neutral',
                expected_sha256=hashlib.sha256(self.definition_raw).hexdigest()),
            preprocessing_policy={'kind':'identity'},output_policy={'kind':'exact_bytes'})
        draft=materials.mutate_definition('model_definition','models.create',None,body,self.checkpoint(),
            'study-model-create',lambda:self.projection.models.create(body))
        model=materials.publish_model(self.projection.models,draft['id'],{'revision':1},self.checkpoint(),'study-model-publish')
        material=materials.prepare_recipe(self.projection.pipelines,self.graph['id'],self.graph['revision'],model['ref'],
            self.checkpoint(),'study-recipe-prepare')
        # The capture owner returns the immutable composition, never a plan.
        composition=self.projection.materials.recipe(material['ref'])
        envelope=composition['material']['resource_envelope']
        limits={key:value*3 for key,value in envelope.items()}
        study_value=self.projection.history.create_study(dict(name='Current neutral Study',limits=limits,policy=policy()),
            self.checkpoint(),'study-create')
        trial_value=self.projection.history.prepare_trial_from_material(study_value['id'],dict(revision=1,
            material=composition['ref'],replicate=0),self.checkpoint(),'study-trial-prepare')
        ref=dict(catalog_id=self.db.dataset_id,trial_id=trial_value['id'],material_sha256=composition['ref']['sha256'])
        intent=dict(ancestry='root',parent=None,baseline=None,cohort='authored neutral control',
            hypothesis='Exact original Study intent survives a cold runtime',change_summary='No change',
            target=dict(metric_id='diagnostic',metric_definition_sha256=None,direction='maximize',threshold=None,
                        acceptance='No scientific qualification claim'))
        lineage=self.projection.history.record_lineage(dict(trial=ref,intent=intent),self.checkpoint(),'study-lineage')
        return study_value['id'],trial_value,composition,envelope,lineage

    def test_cold_study_spent_budget_lineage_and_approval_remain_inert_while_fresh_attempt_is_current(self):
        from project_projection import ProjectProjection
        study_id,trial_value,composition,envelope,lineage=self.prepare_study()
        adapter=self.projection.study_execution
        value=adapter.studies._study(study_id)
        opened=adapter.continue_study(study_id,dict(revision=value['revision'],admission_epoch=value['admission_epoch']),
            self.checkpoint(),'study-current-continue')
        self.assertIsNone(self.execution._runs)
        approval_body=dict(trial_id=trial_value['id'],expected_material_sha256=composition['ref']['sha256'],
                           consumer_actor_id=self.access.identity()['actor_id'])
        approval=adapter.approve(study_id,approval_body,self.checkpoint(),'study-current-approve')
        fact=operation_records(self.session.snapshot['records'])['study-current-approve']['result']
        self.assertEqual(fact['format'],'project_study_approval_v1')
        self.assertNotIn('current_local',fact);self.assertNotIn('grant',fact)
        self.assertEqual(approval['grant']['id'],fact['approval_id'])
        self.assertIsNone(self.execution._runs)
        request=dict(revision=opened['revision'],admission_epoch=opened['admission_epoch'],trial_id=trial_value['id'],
                     approval_id=approval['grant']['id'])
        admitted=adapter.admit(study_id,request,self.checkpoint(),'study-current-attempt')
        first=self.await_drained(admitted['run_id'])
        self.assertEqual(first['state'],'completed')
        saved=self.projection.history.study(study_id)
        self.assertEqual(saved['charged'],envelope)
        self.assertEqual(saved['reservations'][0]['state'],'settled')
        self.assertEqual(saved['reservations'][0]['settled'],envelope)
        self.assertEqual(adapter.studies.lineage._record(trial_value['id']),lineage)
        old_grant=approval['grant']['id'];old_run=admitted['run_id'];logical=self.db.dataset_id
        self.execution.reconcile_current()
        self.projection.close()
        # Its worker has drained and closed; leave no duplicate cleanup owner.
        self.execution._runs=None
        self.db=self.metadata('cold-study-projection',logical)
        with patch('runs.Runs',side_effect=AssertionError('Cold Study Open constructed Runs')):
            self.projection=ProjectProjection(self.store,self.db,self.access,{'fixture':self.source_root})
        self.projections.append(self.projection);self.execution=self.projection.execution;self.session=self.projection.session
        adapter=self.projection.study_execution
        self.assertEqual(adapter.studies._totals(adapter.studies._reservations(study_id)),envelope)
        self.assertEqual(adapter.studies.lineage._record(trial_value['id']),lineage)
        for table in ('workspace_runs','model_attempt_reservations','access_admissions','access_execution_grants',
                      'access_execution_consumptions','model_operation_receipts'):
            self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
        with patch.object(self.execution,'_local_owner',side_effect=AssertionError('Historical request allocated a new owner')):
            with self.assertRaisesRegex(WorkbenchError,'historical'):
                adapter.approve(study_id,approval_body,self.checkpoint(),'study-current-approve')
            with self.assertRaisesRegex(WorkbenchError,'historical admission'):
                adapter.admit(study_id,request,self.checkpoint(),'study-current-attempt')
            value=adapter.studies._study(study_id)
            with self.assertRaisesRegex(WorkbenchError,'Explicitly continue'):
                adapter.admit(study_id,dict(revision=value['revision'],admission_epoch=value['admission_epoch'],
                    trial_id=trial_value['id'],approval_id=old_grant),self.checkpoint(),'study-before-new-epoch')
        lower=dict(value['limits']);lower['retained_bytes']=envelope['retained_bytes']-1
        before=self.session.snapshot
        with self.assertRaises(WorkbenchError):
            self.projection.history.save_study(study_id,dict(revision=value['revision'],name=value['name'],
                limits=lower,policy=value['policy']),self.checkpoint(),'study-lower-spent-budget')
        self.assertEqual(self.session.snapshot,before)
        continued=adapter.continue_study(study_id,dict(revision=value['revision'],admission_epoch=value['admission_epoch']),
            self.checkpoint(),'study-fresh-continue')
        self.assertGreater(continued['admission_epoch'],opened['admission_epoch'])
        self.projection.source_adapter.register(dict(root='fixture',manifest_path='project.json'),
            self.checkpoint(),'study-fresh-source-binding')
        recipe_cache=self.projection.pipelines.material_path/composition['ref']['sha256']
        model_cache=self.projection.models.path/composition['material']['model']['sha256']
        self.assertFalse(recipe_cache.exists());self.assertFalse(model_cache.exists())
        original_open=self.projection.artifacts.open_verified
        def missing_payload(declaration,**kwargs):
            if declaration['sha256']==composition['material']['recipe_document']['sha256']:
                raise WorkbenchError('Controlled missing canonical recipe bytes.','unavailable',409)
            return original_open(declaration,**kwargs)
        before=self.session.snapshot
        with patch.object(self.projection.artifacts,'open_verified',side_effect=missing_payload):
            with self.assertRaisesRegex(WorkbenchError,'missing canonical'):
                adapter.approve(study_id,approval_body,self.checkpoint(),'study-missing-payload')
        self.assertEqual(self.session.snapshot,before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM access_execution_grants').fetchone()[0],0)
        current=adapter.approve(study_id,approval_body,self.checkpoint(),'study-fresh-approve')
        self.assertTrue(recipe_cache.is_dir());self.assertTrue(model_cache.is_dir())
        self.assertNotEqual(current['grant']['id'],old_grant)
        self.assertIsNone(self.db.execute('SELECT id FROM access_execution_grants WHERE id=%s',(old_grant,)).fetchone())
        second=adapter.admit(study_id,dict(revision=continued['revision'],admission_epoch=continued['admission_epoch'],
            trial_id=trial_value['id'],approval_id=current['grant']['id']),self.checkpoint(),'study-fresh-attempt')
        result=self.await_drained(second['run_id']);self.assertEqual(result['state'],'completed')
        self.assertNotEqual(second['run_id'],old_run)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0],1)
        self.assertIsNone(self.db.execute('SELECT id FROM workspace_runs WHERE id=%s',(old_run,)).fetchone())
        self.assertEqual(self.projection.history.study(study_id)['charged'],{key:2*value for key,value in envelope.items()})
        self.assertEqual(adapter.studies.lineage._record(trial_value['id']),lineage)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class CandidateNativePublicationTests(unittest.TestCase):
    """Actual writers/codecs with authored observations; no fitted-model claim.

    Only verified candidate selection is substituted. The explicitly authored
    historical Run/receipt is test data, never an observed process completion.
    No runtime executable, project source, or model state may be launched.
    """
    setUp=ProjectStudyControlTests.setUp
    metadata=ProjectStudyControlTests.metadata
    cleanup=ProjectStudyControlTests.cleanup
    prepare_study=ProjectStudyCustodyTests.prepare_study

    def open_projection(self):
        from project_custody import ProjectCustody
        db=self.metadata('writer-projection-'+uuid.uuid4().hex,project_id=self.store.snapshot()['project_id'])
        journal=ProjectCustody(self.host.db.path,self.host.db.dataset_id).for_projection(self.store,db.projection_id)
        with self.owner.bound(self.host),patch('runs.Runs',side_effect=AssertionError('Inert writer Open constructed Runs')):
            projection=ProjectProjection(self.store,db,self.host.access,{},custody=journal)
        self.projections.append(projection);self.projection=projection;self.adapter=projection.study_execution

    def checkpoint(self):return self.projection.session.snapshot['checkpoint']

    def test_actual_verifier_owner_publication_is_canonical_and_cold_inert(self):
        self._native_publication()

    def test_native_completion_before_wrapper_ack_reconciles_without_repeating_writer(self):
        self._native_publication(wrapper_loss=True)

    def _native_publication(self,*,wrapper_loss=False):
        import shutil
        import candidate_packages as packages
        import recipe_contract,recipe_process
        from pipeline import digest,execution_digest
        from project_history import envelope,FAMILY_FORMATS
        from project_runtime import ProjectRuntime
        from test_candidate_packages import fixture
        from test_project_files_material_http import neutral_source
        self.db=self.projection.db;self.source_root=self.root/'source';self.source_root.mkdir()
        self.manifest,self.manifest_raw,self.definition_raw,self.source,self.input=neutral_source(self.source_root)
        definition=json.loads(self.definition_raw)
        definition['outputs']=[dict(path=name,role='result',max_bytes=2*1024**2,required=True)
            for name in ('package.zip','checkpoint-epoch-0001.json','metrics.json')]
        definition['resources']['max_output_bytes']=6*1024**2
        self.definition_raw=json.dumps(definition).encode();self.manifest['recipes'][0]['sha256']=packages.sha(self.definition_raw)
        (self.source_root/'recipe.json').write_bytes(self.definition_raw)
        (self.source_root/'project.json').write_bytes(json.dumps(self.manifest).encode())
        fd=os.open(self.source_root,os.O_RDONLY|os.O_DIRECTORY);info=os.fstat(fd)
        self.projection.sources.roots['fixture']=(fd,[info.st_dev,info.st_ino])
        with self.owner.bound(self.host),patch('subprocess.Popen',side_effect=AssertionError('No process in writer qualification')),patch('runs.Runs',side_effect=AssertionError('No Run owner in writer qualification')):
            self.projection.source_adapter.register(dict(root='fixture',manifest_path='project.json'),self.checkpoint(),'candidate-source')
            body=dict(name='Authored source graph',project_id=self.manifest['id'],recipe_id='neutral',expected_sha256=packages.sha(self.definition_raw),
                inputs={'sample':dict(reference_id='sample',expected_sha256=packages.sha(self.input))})
            self.graph=self.projection.materials.mutate_definition('pipeline_graph','graphs.create_external',None,body,
                self.checkpoint(),'candidate-source-graph',lambda:self.projection.pipelines.create_external(body))
            study_id,trial_value,composition,envelope_value,_lineage=self.prepare_study()
            python=self.root/'python';site=self.root/'packages'
            (python/'bin').mkdir(parents=True);(python/'lib/python3.12/lib-dynload').mkdir(parents=True)
            shutil.copyfile('/usr/bin/true',python/'bin/python3.12');(python/'lib/python3.12/lib-dynload/inert.txt').write_text('Not a Python environment')
            entries=[]
            for name in ('torch','numpy'):
                (site/name).mkdir(parents=True);(site/name/'__init__.py').write_text('raise AssertionError("Never import")\n')
                meta=site/(name+'-0.0.dist-info');meta.mkdir();(meta/'METADATA').write_text('Name: '+name+'\nVersion: 0.0\n');(meta/'LICENSE').write_text('Fixture')
                entries.extend([name,meta.name])
            config=dict(schema_version=1,python_root=str(python),python_version='3.12',site_packages=str(site),packages=entries)
            runtime=ProjectRuntime(self.projection,resolve_configuration=lambda request:copy.deepcopy(config))
            observed=runtime.inspect({'source':'authored'})
            captured=runtime.capture({'source':'authored'},observed['inventory_sha256'],self.checkpoint(),'candidate-runtime',reserve_bytes=0)
            descriptor=self.projection.materials.runtime(captured['runtime_ref'])['descriptor']
            old_manifest,old_blobs=fixture();published=packages.decode(old_blobs['published-model-material.json']);published['catalog_id']=self.db.dataset_id
            artifacts={name:old_blobs[name] for name in ('checkpoint-epoch-0001.json','weights-epoch-0001.pt','model-definition.json','fitted-transform.json','metrics.json','probe.json','probes-epoch-0001.json')}
            checkpoint=packages.decode(artifacts['checkpoint-epoch-0001.json']);checkpoint['model_sha256']=packages.sha(packages.encoded(published));artifacts['checkpoint-epoch-0001.json']=packages.encoded(checkpoint)
            probes=packages.decode(artifacts['probes-epoch-0001.json']);probes['checkpoint_sha256']=packages.sha(artifacts['checkpoint-epoch-0001.json']);artifacts['probes-epoch-0001.json']=packages.encoded(probes)
            study_doc=next(copy.deepcopy(r) for r in self.projection.session.snapshot['records'] if r['family']=='study_history' and r['document']['study']['id']==study_id)
            decision=dict(format='candidate_v1',id='f'*32,study_id=study_id,trial_id=trial_value['id'],run_id='a'*32,
                checkpoint_sha256=packages.sha(artifacts['checkpoint-epoch-0001.json']),evaluation_sha256=packages.sha(artifacts['metrics.json']),
                policy=study_doc['document']['study']['policy'],decision='diagnostic',limitations=['Authored structural writer fixture; not scientific qualification.'])
            candidate=dict(ref=dict(kind='candidate',catalog_id=self.db.dataset_id,id=decision['id'],sha256=digest(decision)),candidate=decision,
                run_id=decision['run_id'],checkpoint=packages.blob('checkpoint-epoch-0001.json',artifacts['checkpoint-epoch-0001.json']))
            manifest,blobs=packages.classifier_closure(candidate,artifacts,{'c'*32:b'authored fixture; not a PNG'},
                {'image_training.py':b'# inert authored source fixture\n'},packages.runtime_contract(descriptor),
                {'material':published,**{name:old_blobs['published-'+name+'.json'] for name in ('specification','preprocessing_policy','output_policy')}})
            package=packages.create_package(manifest,blobs);packages.inspect_package(package,packages.sha(package))
            recipe_snapshot=json.loads(self.projection.materials.blob(composition['ref'],composition['material']['recipe_document']))
            execution=recipe_snapshot['preflight']['material'];run_id='a'*32;request_sha='c'*64
            spec=dict(recipe_contract.spec_for_material(execution,Path('/authored/workspace-runs')/('.external-'+run_id)),attempt_id=run_id,request_sha256=request_sha)
            identity=dict(attempt_id=run_id,request_sha256=request_sha,spec_sha256=packages.sha(recipe_process.encoded(spec)),helper=dict(pid=123,start_ticks='1',boot_id='00000000-0000-0000-0000-000000000000'))
            receipt=dict(schema_version=1,**identity,go_received=True,spawn_closed=True,drained=True,echild=True,outcome='completed',reason='Authored fixture only',leader_returncode=0,
                streams={name:dict(bytes=0,sha256=packages.sha(b'')) for name in ('stdout','stderr')})
            receipt_raw=recipe_process.encoded(receipt)
            payload_bytes={'package.zip':package,'checkpoint-epoch-0001.json':artifacts['checkpoint-epoch-0001.json'],'metrics.json':artifacts['metrics.json']}
            inventory=[dict(name=name,role='result',bytes=len(raw),sha256=packages.sha(raw),media_type='application/octet-stream') for name,raw in payload_bytes.items()]
            actor=self.owner.identity['actor_id'];admission_id='8'*32;approval_id='9'*32
            run=dict(schema_version=1,mode='real',execution_kind='external_recipe',result_kind='external_recipe',id=run_id,dataset_id=self.db.dataset_id,
                request_key='authored-history',request_sha256=request_sha,actor_id=actor,admission_id=admission_id,approval_id=approval_id,
                state='completed',created_at='2026-10-22T00:00:00+00:00',started_at=None,finished_at='2026-10-22T00:00:01+00:00',graph=self.graph,
                graph_revision=self.graph['revision'],graph_sha256=execution_digest(self.graph),graph_document_sha256=digest(self.graph),material=execution,
                material_sha256=digest(execution),spec=spec,outputs=execution['recipe']['outputs'],parameters=execution['parameters'],attempt=1,parent_run_id=None,
                events=[],artifacts=inventory,metrics=None,error=None,custody_phase='drained',custody_identity=identity,custody_receipt_sha256=packages.sha(receipt_raw),
                quality_claim=False,progress=dict(stage='completed',completed=None,total=None),node_attempts=[],approval_material_sha256=composition['ref']['sha256'])
            proof=dict(grant=dict(id=approval_id,catalog_id=self.db.dataset_id,approver_actor_id=actor,approver_credential_id='4'*32,consumer_actor_id=actor,
                material_sha256=composition['ref']['sha256'],created_at=1,expires_at=601,revoked_at=None),
                consumption=dict(grant_id=approval_id,run_id=run_id,admission_id=admission_id,consumer_credential_id='5'*32,request_sha256=request_sha,consumed_at=2),
                admission=dict(id=admission_id,catalog_id=self.db.dataset_id,actor_id=actor,credential_id='5'*32,kind='runs',job_id=run_id,request_digest=request_sha,
                    effects={'runs.update':[run_id]},created_at=2))
            payload_bytes['custody-receipt.json']=receipt_raw
            payload_bytes['artifact-manifest.json']=encode(dict(schema_version=1,run_id=run_id,material_sha256=run['material_sha256'],request_sha256=request_sha,custody_receipt_sha256=run['custody_receipt_sha256'],artifacts=inventory)).encode()
            for path in recipe_snapshot['capture_paths']:payload_bytes[path['path']]=self.projection.materials.blob(composition['ref'],path['blob'])
            edges=[]
            for name,raw in payload_bytes.items():
                item=dict(sha256=packages.sha(raw),bytes=len(raw));self.projection.artifacts.publish_bytes(raw,dict(format='project_artifact_v1',**item))
                edges.append(dict(name=name,blob=item,population='unknown',role='authored_fixture',preservation='unique',required_for=['inspection']))
            archived=capture_run(run,admission_proof=proof,payloads=edges)
            reservation=dict(id='e'*32,study_id=study_id,admission_epoch=0,request_key='authored-history',actor_id=actor,trial_id=trial_value['id'],parent_run_id=None,
                run_id=run_id,request_sha256=request_sha,material_sha256=composition['ref']['sha256'],envelope=envelope_value,state='settled',settled=envelope_value)
            study_doc['document']['reservations']=[reservation]
            selected=envelope('candidate_history',self.db.dataset_id,decision['id'],dict(format=FAMILY_FORMATS['candidate_history'],origin_catalog_id=self.db.dataset_id,candidate=decision))
            before=self.projection.session.snapshot;records=[r for r in before['records'] if (r['family'],r['id'])!=(study_doc['family'],study_doc['id'])]
            merged={(r['family'],r['id']):r for r in [*records,study_doc,archived,*declarations(archived),selected]}
            self.projection.validate_records(list(merged.values()));self.store.commit(list(merged.values()),before['checkpoint'],'authored-history-fixture','a'*64)
            self.projection.session.adopt(self.store.snapshot());self.adapter.restore_authoring()
            # This is the sole scientific-selection substitution. Every package,
            # source, custody/input, current disclosure and canonical codec stays real.
            with patch.object(self.adapter,'candidate',return_value=candidate):
                request=dict(revision=study_doc['document']['study']['revision'],candidate_id=decision['id'],root='fixture',directory='verifier',
                    runtime_snapshot_sha256=descriptor['manifest_sha256'],package_run_id=run_id,package_sha256=packages.sha(package))
                with self.assertRaisesRegex(WorkbenchError,'disclose'):
                    self.adapter.prepare_verifier(study_id,request,self.checkpoint(),'verify-without-disclosure')
                self.assertFalse((self.source_root/'verifier').exists())
                self.projection.disclose(run_id,dict(origin_catalog_id=self.db.dataset_id,reason='Authored writer qualification'),self.checkpoint(),'disclose-writer-fixture')
                # The denied attempt retained an honest intent; use a new key.
                writes=[];original_writer=packages._write_project
                def write_after_intent(root,files):
                    receipts=operation_records(self.projection.session.snapshot['records'])
                    self.assertTrue(any(value['operation']=='study_execution.prepare_verifier_intent'
                        and value['result']['directory']=='verifier' for value in receipts.values()))
                    self.assertIn('verify-authored-fixture',self.projection.execution._package_pending)
                    self.assertFalse((self.source_root/'verifier').exists())
                    writes.append(self.checkpoint());return original_writer(root,files)
                with patch.object(packages,'_write_project',side_effect=write_after_intent):
                    if wrapper_loss:
                        original_mutate=self.adapter._mutate
                        def lose_wrapper(operation,*args,**kwargs):
                            if operation=='study_execution.prepare_verifier':
                                raise OSError('Controlled failure before public wrapper acknowledgement')
                            return original_mutate(operation,*args,**kwargs)
                        with patch.object(self.adapter,'_mutate',side_effect=lose_wrapper),self.assertRaisesRegex(OSError,'public wrapper'):
                            self.adapter.prepare_verifier(study_id,request,self.checkpoint(),'verify-authored-fixture')
                    else:result=self.adapter.prepare_verifier(study_id,request,self.checkpoint(),'verify-authored-fixture')
                self.assertEqual(len(writes),1)
                if wrapper_loss:
                    self.assertTrue(self.projection.custody.has_pending)
                    self.assertNotIn('verify-authored-fixture',operation_records(self.projection.session.snapshot['records']))
                    native=next(value for record in self.projection.session.snapshot['records'] if record['family']=='study_history'
                        and record['document']['study']['id']==study_id for value in record['document']['operations']
                        if value['operation_id']=='studies.prepare_verifier' and value['request_key']=='verify-authored-fixture')
                    self.assertEqual(native['result']['state'],'prepared')
                    before=copy.deepcopy(self.projection.session.snapshot)
                    with self.assertRaisesRegex(WorkbenchError,'complete'):
                        self.adapter.abandon_preparation(study_id,dict(preparation_key='verify-authored-fixture',reason='Must retain complete science'),
                            self.checkpoint(),'forbidden-complete-abandon')
                    self.assertEqual(self.projection.session.snapshot,before)
                    with patch.object(packages,'_write_project',side_effect=AssertionError('Recovery repeated native filesystem writes')):
                        result=self.adapter.reconcile_preparation(study_id,dict(preparation_key='verify-authored-fixture'),self.checkpoint())
                    self.assertEqual(result,native['result'])
                    receipt=operation_records(self.projection.session.snapshot['records'])['verify-authored-fixture']
                    self.assertEqual(receipt['operation'],'study_execution.prepare_verifier')
                    self.assertEqual(receipt['result'],native['result'])
                    self.assertFalse(self.projection.custody.has_pending)
                    self.assertEqual(self.adapter.prepare_verifier(study_id,request,self.checkpoint(),'verify-authored-fixture'),result)
                    for table in ('workspace_runs','access_execution_grants','access_admissions','model_attempt_reservations'):
                        self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
                    return
                self.assertEqual(result['state'],'prepared');self.assertTrue((self.source_root/'verifier/project.json').is_file())
                receipts=operation_records(self.projection.session.snapshot['records'])
                self.assertEqual(receipts['verify-authored-fixture']['operation'],'study_execution.prepare_verifier')
                self.assertTrue(validate_operation_result('study_execution.prepare_verifier',result,self.projection.session.snapshot['records']))
                saved=self.projection.session.snapshot
                self.assertEqual(self.adapter.prepare_verifier(study_id,request,self.checkpoint(),'verify-authored-fixture'),result)
                self.assertEqual(self.projection.session.snapshot,saved)
                consumer=self.projection.materials.recipe(result['trial']['material'])
                # The actual native reader must consume an archived producer
                # through current disclosure, with no live producer SQL row.
                self.assertEqual(self.projection.pipelines.recipe_material(result['trial']['material'],verify=True),consumer)
                self.projection._disclosures.clear()
                with self.assertRaisesRegex(WorkbenchError,'disclose'):
                    self.projection.pipelines.recipe_material(result['trial']['material'],verify=True)
                self.projection.disclose(run_id,dict(origin_catalog_id=self.db.dataset_id,reason='New consumer read permission'),
                    self.checkpoint(),'disclose-consumer-input')
                snapshot=json.loads(self.projection.materials.blob(consumer['ref'],consumer['material']['recipe_document']))
                tampered=copy.deepcopy(snapshot['preflight']['material'])
                import base64
                source=tampered['inputs']['package']['source']
                forged=recipe_process.decode(base64.b64decode(source['custody_receipt_base64']))
                forged['reason']='Different self-consistent authored receipt'
                forged_raw=recipe_process.encoded(forged)
                source['custody_receipt_base64']=base64.b64encode(forged_raw).decode('ascii')
                source['custody_receipt_sha256']=packages.sha(forged_raw)
                recipe_contract.validate_material(tampered)
                with self.assertRaisesRegex(WorkbenchError,'producer proof differs'):
                    packages.authorize_material_inputs(self.projection.history,tampered)
                # The named current execution composition selects the same
                # history proof seam; it cannot call a general live resolver.
                execution=self.projection.execution
                local_reader=SimpleNamespace(project_execution=execution,
                    _load=lambda _:(_ for _ in ()).throw(AssertionError('Imported producer reached live SQL resolver')))
                execution._runs=local_reader
                try:packages.authorize_material_inputs(local_reader,snapshot['preflight']['material'])
                finally:execution._runs=None
                # A synchronous failure after actual source/graph/model draft
                # publication preserves its directory and every canonical phase.
                partial=dict(request,revision=self.adapter.studies._study(study_id)['revision'],directory='partial')
                with patch.object(self.projection.models,'publish',side_effect=RuntimeError('Controlled partial owner failure')):
                    with self.assertRaisesRegex(RuntimeError,'partial owner failure'):
                        self.adapter.prepare_verifier(study_id,partial,self.checkpoint(),'verify-partial')
                phases=self.projection.session.snapshot['records']
                self.assertTrue((self.source_root/'partial/project.json').is_file())
                self.assertTrue(self.projection.custody.has_pending)
                aborted=self.adapter.abandon_preparation(study_id,dict(preparation_key='verify-partial',reason='Preserve and stop the authored partial writer'),
                    self.checkpoint(),'abandon-partial')
                self.assertEqual(aborted['state'],'abandoned')
                self.assertFalse(self.projection.custody.has_pending)
                current={(r['family'],r['id']):r for r in self.projection.session.snapshot['records']}
                self.assertTrue(all(current[(r['family'],r['id'])]==r for r in phases))
                self.assertTrue((self.source_root/'partial/project.json').is_file())
                # Lose only final journal acknowledgement, after all native and
                # canonical commits. Recovery must confirm the existing result.
                uncertain=dict(partial,directory='ack-lost')
                with patch.object(self.projection.custody,'package_confirmed',side_effect=OSError('Controlled final custody ACK loss')):
                    with self.assertRaisesRegex(OSError,'custody ACK loss'):
                        self.adapter.prepare_verifier(study_id,uncertain,self.checkpoint(),'verify-ack-lost')
                self.assertFalse(self.projection.session.available)
                completed=operation_records(self.projection.session.snapshot['records'])['verify-ack-lost']['result']
                with patch.object(packages,'_write_project',side_effect=AssertionError('Recovery repeated a native writer')):
                    recovered=self.adapter.reconcile_preparation(study_id,dict(preparation_key='verify-ack-lost'),self.checkpoint())
                self.assertEqual(recovered,completed);self.assertTrue(self.projection.session.available)
                self.assertFalse(self.projection.custody.has_pending)
            for table in ('workspace_runs','access_execution_grants','access_admissions','model_attempt_reservations'):
                self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
            self.assertFalse(self.projection.execution.has_local_custody)
            saved=self.projection.session.snapshot
            self.projection.close();self.open_projection()
            self.assertEqual(self.projection.session.snapshot,saved)
            self.assertFalse(self.projection.execution.has_local_custody)
            self.assertIn(result['trial']['id'],self.projection.history.study(study_id)['study']['trial_ids'])
            self.assertEqual(self.adapter.prepare_verifier(study_id,request,self.checkpoint(),'verify-authored-fixture'),result)
            with self.assertRaisesRegex(WorkbenchError,'exact original file writer') as refused:
                self.adapter.reconcile_preparation(study_id,dict(preparation_key='verify-ack-lost'),self.checkpoint())
            self.assertEqual(refused.exception.code,'unavailable')
            self.assertFalse(self.projection._disclosures)
            with self.assertRaisesRegex(WorkbenchError,'disclose'):
                self.projection.history.artifact(run_id,'package.zip')
            for table in ('workspace_runs','access_execution_grants','access_admissions','model_attempt_reservations','model_operation_receipts'):
                self.assertEqual(self.projection.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
