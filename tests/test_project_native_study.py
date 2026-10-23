"""Actual CPU native Study custody, accounting, and cold historical authority.

These gates require the integration lead's immutable source qualification window.
The six authored texts make no model quality or semantic independence claim.
"""
import copy
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

from access import Access
from auth_helpers import ExplicitOwnerFixture
from metadata import Metadata, connection_info, CATALOG_LOCAL_TIMEOUT
from project_custody import ProjectCustody
from project_projection import ProjectProjection
from project_session import operation_records
from project_session import ProjectSessionError
from project_store import ProjectStore
from project_store import _encode as canonical
from workbench import WorkbenchError
import recipe_process
import text_training
from pipeline import decode_exposures


def prepare_text_source(projection, *, key_prefix='native-text'):
    """Return (reviewed rows, actual canonical frozen text release); no child."""
    data=projection.data
    checkpoint=lambda:projection.session.snapshot['checkpoint']
    rows=[]
    for index in range(6):
        label='schedule' if index % 2 else 'cancel'
        text=(('Arrange meeting schedule tomorrow' if label=='schedule'
               else 'Cancel appointment reservation tomorrow')+' authoredmarker'+str(index))
        row=data.import_text(dict(text=text,groups=[key_prefix+'-source-'+str(index)],
            rights='Authored test text; no accuracy or semantic independence claim.'),
            checkpoint(),key_prefix+'-import-'+str(index))
        row=data.annotate(row['id'],dict(revision=row['revision'],source_revision=row['source_revision'],
            task='text_classification',annotation=dict(label=label),groups=row['groups'],review='human_reviewed'),
            checkpoint(),key_prefix+'-review-'+str(index))
        rows.append(row)
    request=dict(format='text_classification_v1',
        items=[{key:row[key] for key in ('id','revision','source_revision')} for row in rows],
        ratios=dict(train=34,validation=33,test=33),seed=0)
    for seed in range(100):
        request['seed']=seed
        preview=data.preview_release(request)
        if preview['eligible']:break
    if not preview['eligible']:
        raise AssertionError('Authored text release has no eligible deterministic split: '+repr(preview['blockers']))
    request['preview_token']=preview['preview_token']
    release=data.freeze_release(request,checkpoint(),key_prefix+'-freeze')
    return rows,release


def qa_retained_path(value):
    """Keep opt-in retained fixture evidence beneath its configured QA root."""
    output=Path(value).resolve()
    configured=os.environ.get('TULDOK_QA_OUTPUT_ROOT')
    if configured is not None and not configured.strip():
        raise AssertionError('Configured QA output root must not be empty')
    permitted=Path(configured if configured is not None else
        '/workspace/scratch/tuldok-save-load-qa/artifacts').resolve()
    if not output.is_relative_to(permitted):
        raise AssertionError('Native fixture evidence must remain below the disposable QA artifact root')
    return output


def retain_project_evidence(projection, label):
    """Opt-in disposable QA copy of exact records and verified proof bytes."""
    configured=os.environ.get('TULDOK_NATIVE_RETENTION_DIR')
    if not configured:return None
    output=qa_retained_path(configured)
    store=projection.session.store
    with projection.session.access.lock,projection.session.lock,projection.db.lock:
        snapshot=store.snapshot()
        manifest=(store.path/'.tuldok/project.json').read_bytes()
        if json.loads(manifest)['checkpoint']!=snapshot['checkpoint']:
            raise AssertionError('Native fixture snapshot and manifest checkpoints differ')
    output=output/(label+'-'+snapshot['project_id']+'-'+snapshot['checkpoint'])
    output.mkdir(parents=True,exist_ok=True)
    raw=canonical(snapshot);(output/'snapshot.json').write_bytes(raw)
    (output/'project.json').write_bytes(manifest)
    observed=[]
    blob_root=Path(configured).resolve()/'artifacts/sha256';blob_root.mkdir(parents=True,exist_ok=True)
    for record in snapshot['records']:
        if record['family']!='project_artifact':continue
        declaration=record['document'];status=projection.artifacts.status(declaration)
        observed.append(dict(declaration=declaration,availability=status))
        if status['state']!='verified':continue
        target=blob_root/declaration['sha256']
        with projection.artifacts.open_verified(declaration) as descriptor:
            digest=hashlib.sha256();size=0
            with target.open('wb') as captured:
                while True:
                    chunk=os.read(descriptor,1024**2)
                    if not chunk:break
                    digest.update(chunk);size+=len(chunk);captured.write(chunk)
            if size!=declaration['bytes'] or digest.hexdigest()!=declaration['sha256']:
                raise AssertionError('Native fixture retained proof differs from its declaration')
    receipt=dict(format='native_fixture_retention_v1',label=label,project_id=snapshot['project_id'],
        checkpoint=snapshot['checkpoint'],snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        manifest_sha256=hashlib.sha256(manifest).hexdigest(),artifacts=observed)
    (output/'receipt.json').write_bytes(canonical(receipt))
    return output


NATIVE_PYTHON=(Path(os.environ['TULDOK_TRAINING_PYTHON'])
    if os.environ.get('TULDOK_TRAINING_PYTHON') else None)

# Two bounded catalog waits cover terminal publication and its observation.
# Native helper drainage is already included in the admission wall budget.
NATIVE_PUBLICATION_OBSERVATION_ALLOWANCE_SECONDS=2*CATALOG_LOCAL_TIMEOUT


def native_drain_wait_seconds(timeout=None):
    if timeout is not None:return timeout
    from project_native_execution import native_admission_wall_seconds
    return native_admission_wall_seconds()+NATIVE_PUBLICATION_OBSERVATION_ALLOWANCE_SECONDS


class NativeDrainDeadlineTests(unittest.TestCase):
    def test_default_wait_covers_native_budget_and_catalog_observation_but_short_override_stays_bounded(self):
        import test_project_native_run as direct
        from project_native_execution import native_admission_wall_seconds
        self.assertEqual(native_drain_wait_seconds(),native_admission_wall_seconds()+2*CATALOG_LOCAL_TIMEOUT)
        self.assertEqual(native_drain_wait_seconds(.5),.5)
        def projection():
            active=iter((1,0))
            return SimpleNamespace(db=SimpleNamespace(lock=nullcontext(),execute=lambda *args:
                SimpleNamespace(fetchone=lambda:dict(document=json.dumps(dict(id='authored',state='completed'))))),
                execution=SimpleNamespace(health=lambda:dict(active_count=next(active))),fail=self.fail)
        for kind in ('study','direct'):
            def await_run(value,timeout=None):
                if kind=='study':return NativeStudyCustodyTests.await_drained(value,'authored',timeout)
                return direct.NativeRunSaveAsTests.await_drained(self,value,'authored',timeout)
            with self.subTest(kind=kind),patch.object(time,'monotonic',side_effect=(100,101,281)),patch.object(time,'sleep'):
                self.assertEqual(await_run(projection())['state'],'completed')
            with self.subTest(kind=kind,short=True),patch.object(time,'monotonic',side_effect=(100,100.1,100.7)),patch.object(time,'sleep'):
                with self.assertRaisesRegex(AssertionError,'did not drain'):await_run(projection(),.5)


class ExposureObservationTests(unittest.TestCase):
    def test_current_and_retained_observations_share_closed_non_authoritative_shape(self):
        event=dict(id='1'*32,record_id='2'*32,run_id='3'*32,source_hash='4'*64,
            release_id='5'*64,reason='Explicit authored observation',created_at='2026-10-22T12:00:00+00:00')
        value=dict(exposed=True,events=[event])
        self.assertEqual(decode_exposures(value),value)
        self.assertEqual(decode_exposures(dict(exposed=False,events=[])),dict(exposed=False,events=[]))
        for malformed in (dict(value,grant={'token':'secret'}),dict(value,exposed=False),
                dict(value,events=[dict(event,token='secret')]),dict(value,events=[event,event]),
                dict(value,events=[dict(event,created_at='2026-10-22T12:00:00')]),
                dict(value,events=[dict(event,run_id='not-a-run')])):
            with self.subTest(value=malformed),self.assertRaises(WorkbenchError):decode_exposures(malformed)


@unittest.skipUnless(os.environ.get('TULDOK_NATIVE_PROJECT_GO')=='1'
    and os.environ.get('TULDOK_DATABASE_URL') and NATIVE_PYTHON is not None and NATIVE_PYTHON.is_file(),
    'Requires disposable PostgreSQL, qualified CPU environment, and coordinated immutable source')
class NativeStudyCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-native-study-')
        self.root=Path(self.temporary.name)
        self.databases=[];self.projections=[];self.closed_projections=set();self.extra_stores=[]
        self.addCleanup(self.temporary.cleanup)
        host_db=self.metadata('host')
        self.host=SimpleNamespace(db=host_db,access=Access(host_db,host_db.path))
        self.owner=ExplicitOwnerFixture.bootstrap(self.host)
        self.enterContext(self.owner.bound(self.host))
        self.enterContext(patch.dict(os.environ,{'TULDOK_TRAINING_PYTHON':str(NATIVE_PYTHON)}))
        self.store=ProjectStore.create(self.root/'project','Actual CPU native Study','native-study-fixture','a'*64)
        self.addCleanup(self.store.close)
        self.custody=ProjectCustody(self.host.db.path,self.host.db.dataset_id)
        self.open_projection()
        self.addCleanup(self.cleanup)
        self.addCleanup(self.retain_before_cleanup)

    def metadata(self,name,*,project_id=None,dsn=None):
        kwargs={} if project_id is None else dict(dataset_id=project_id,projection_id=uuid.uuid4().hex)
        db=Metadata(self.root/(name+'-'+uuid.uuid4().hex),dsn=dsn,**kwargs)
        self.databases.append(db)
        return db

    def open_projection(self):
        db=self.metadata('projection',project_id=self.store.snapshot()['project_id'])
        journal=self.custody.for_projection(self.store,db.projection_id)
        with patch('runs.Runs',side_effect=AssertionError('Cold metadata Open constructed Runs')):
            projection=ProjectProjection(self.store,db,self.host.access,{},custody=journal)
        self.projections.append(projection)
        self.projection=projection;self.db=db;self.execution=projection.execution
        self.session=projection.session;self.adapter=projection.study_execution

    def checkpoint(self):return self.session.snapshot['checkpoint']

    def retain_before_cleanup(self):
        if getattr(self,'projection',None) is not None and id(self.projection) not in self.closed_projections:
            retain_project_evidence(self.projection,'study-before-cleanup')

    def cleanup(self):
        # Drain actual owners before releasing their file/SQL resources. Failed
        # ACK tests explicitly reconcile their phase before reaching teardown.
        for projection in reversed(self.projections):
            if id(projection) in self.closed_projections:continue
            execution=projection.execution
            if execution._runs is not None:
                with execution.runtime_access._reconcile():execution._runs.close()
            if projection.session.available and not projection.custody.has_pending:
                if execution._runs is not None:execution.reconcile_current()
                projection.close()
                self.closed_projections.add(id(projection))
            else:
                # Do not disguise an unresolved lifecycle failure as a close.
                self.fail('Native Study fixture left unresolved canonical/physical custody: '+repr(execution.health()))
        for store in self.extra_stores:store.close()
        for db in reversed(self.databases):db.close()
        for db in self.databases:
            with psycopg.connect(db.dsn,autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(db.schema)))

    def prepare_study(self):
        _,release=prepare_text_source(self.projection)
        pipelines=self.projection.pipelines;materials=self.projection.materials
        recipe=next(item for item in pipelines.definitions()['recipes'] if item['id']==text_training.MODEL_RECIPE)
        body=copy.deepcopy(recipe['model_template'])
        model=materials.mutate_definition('model_definition','models.create',None,body,self.checkpoint(),
            'native-study-model-create',lambda:self.projection.models.create(body))
        published=materials.publish_model(self.projection.models,model['id'],dict(revision=model['revision']),
            self.checkpoint(),'native-study-model-publish')
        graph_body=dict(name='Actual CPU native Study',recipe=recipe['id'],release_id=release['id'])
        graph=materials.mutate_definition('pipeline_graph','graphs.create',None,graph_body,self.checkpoint(),
            'native-study-graph-create',lambda:pipelines.create(graph_body))
        composition=materials.prepare_recipe(pipelines,graph['id'],graph['revision'],published['ref'],
            self.checkpoint(),'native-study-material-prepare',builtin=True)
        retained=materials.recipe(composition['ref'])
        envelope=retained['material']['resource_envelope']
        validation=self.projection.native_preparation.validate_graph(pipelines,graph['id'],graph['revision'],
            self.checkpoint(),'native-study-policy-validation')
        self.assertTrue(validation['valid'],validation)
        study=self.projection.history.create_study(dict(name='Finite CPU native Study',
            policy=validation['selection_policy'],limits={key:3*value for key,value in envelope.items()}),
            self.checkpoint(),'native-study-create')
        trial=self.projection.history.prepare_trial_from_material(study['id'],dict(revision=study['revision'],
            material=composition['ref'],replicate=0),self.checkpoint(),'native-study-trial')
        return study['id'],trial,composition,envelope

    def continue_study(self,study_id,key):
        value=self.adapter.studies._study(study_id)
        return self.adapter.continue_study(study_id,dict(revision=value['revision'],
            admission_epoch=value['admission_epoch']),self.checkpoint(),key)

    @staticmethod
    def admission_body(current,trial):
        return dict(revision=current['revision'],admission_epoch=current['admission_epoch'],trial_id=trial['id'])

    def await_drained(self,run_id,timeout=None):
        deadline=time.monotonic()+native_drain_wait_seconds(timeout)
        run=None
        while time.monotonic()<deadline:
            with self.db.lock:
                row=self.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(run_id,)).fetchone()
                run=json.loads(row['document']) if row else None
                health=self.execution.health()
            if run is not None and run['state'] in ('completed','failed','interrupted','cancelled','unknown') and health['active_count']==0:
                return run
            time.sleep(.05)
        self.fail('Actual native Study did not drain: '+repr(run)+' health='+repr(health))

    def assert_no_local_authority(self,*,cold=True):
        tables=['workspace_runs','model_attempt_reservations','access_admissions',
                'access_execution_grants','access_execution_consumptions','access_actors','access_credentials']
        if cold:tables.append('model_operation_receipts')
        for table in tables:
            self.assertEqual(self.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def assert_completed_science(self,run_id):
        run=self.await_drained(run_id)
        self.assertEqual(run['state'],'completed',dict(error=run.get('error'),events=run.get('events')))
        retain_project_evidence(self.projection,'study-completed-'+run_id)
        self.projection.disclose(run_id,dict(origin_catalog_id=run['dataset_id'],
            reason='Explicit current test inspection of the completed authored Study evidence'),
            self.checkpoint(),'native-study-disclose-'+run_id)
        evidence=self.projection.history.evidence(run_id)
        self.assertEqual(evidence['state'],'verified')
        self.assertEqual(len(evidence['checkpoint_index']['entries']),1)
        self.assertEqual(evidence['checkpoint_index']['entries'][0]['clocks']['fit_pass'],1)
        phases=[item['document'] for item in self.store.snapshot()['records']
                if item['family']=='native_execution_history' and item['document']['run_id']==run_id]
        for kind in ('train','verify'):
            selected=[item for item in phases if item['phase']==kind]
            self.assertEqual(len(selected),1,(kind,[(p['phase'],p['events']) for p in phases]))
            self.assertEqual(selected[0]['events'][-1]['state'],'completed')
            receipt=recipe_process.decode(selected[0]['observations']['drain_receipt'])
            self.assertTrue(receipt['go_received']);self.assertTrue(receipt['drained']);self.assertTrue(receipt['echild'])
        return run,evidence

    def test_text_source_fixture_freezes_actual_classification_without_native_children(self):
        with patch('subprocess.Popen',side_effect=AssertionError('Source freeze launched native child')), \
                patch('subprocess.run',side_effect=AssertionError('Source freeze probed runtime')):
            rows,release=prepare_text_source(self.projection,key_prefix='source-only')
            inspected=self.projection.pipelines.inspect_release(release['id'],recipe=text_training.MODEL_RECIPE)
        self.assertEqual(len(rows),6);self.assertEqual(inspected['records'],6)
        self.assertEqual(inspected['split_counts'],dict(train=2,validation=2,test=2))
        self.assertEqual({item['label'] for item in inspected['class_vocabulary']},{'schedule','cancel'})
        self.assertFalse(any(item['family']=='native_execution_history' for item in self.session.snapshot['records']))
        self.assert_no_local_authority()

    def test_actual_native_study_spent_budget_and_cold_history_require_fresh_admission(self):
        study_id,trial,composition,envelope=self.prepare_study()
        current=self.continue_study(study_id,'native-study-continue')
        body=self.admission_body(current,trial)
        observed=[];original_go=recipe_process.Handle.go
        def acknowledged_go(handle,expected):
            phase=next(item['document'] for item in self.store.snapshot()['records']
                if item['family']=='native_execution_history' and item['document']['phase_id']==handle.spec['attempt_id'])
            self.assertEqual(phase['events'][-1]['state'],'go_intent')
            self.assertFalse(self.db.in_transaction)
            observed.append((phase['phase'],phase['run_id']))
            return original_go(handle,expected)
        with patch.object(recipe_process.Handle,'go',acknowledged_go):
            admitted=self.adapter.admit(study_id,body,self.checkpoint(),'native-study-first-attempt')
            first,evidence=self.assert_completed_science(admitted['run_id'])
        self.assertIn(('train',first['id']),observed);self.assertIn(('verify',first['id']),observed)
        saved=self.projection.history.study(study_id)
        self.assertEqual(saved['charged'],envelope)
        self.assertEqual(saved['reservations'][0]['state'],'settled')
        self.assertEqual(saved['reservations'][0]['settled'],envelope)
        self.execution.reconcile_current()
        closed=self.projection;closed.close();self.closed_projections.add(id(closed))
        with patch('subprocess.Popen',side_effect=AssertionError('Cold native history launched')):
            self.open_projection()
            self.assert_no_local_authority();self.assertIsNone(self.execution._runs)
            self.assertEqual(self.projection.history.study(study_id)['charged'],envelope)
            with self.assertRaises(WorkbenchError) as protected:
                self.projection.history.evidence(first['id'])
            self.assertEqual(protected.exception.code,'forbidden')
            self.projection.disclose(first['id'],dict(origin_catalog_id=first['dataset_id'],
                reason='New current cold-host inspection; historical exposure grants nothing'),
                self.checkpoint(),'native-study-cold-disclose')
            self.assertEqual(self.projection.history.evidence(first['id']),evidence)
            self.assertFalse(self.adapter.epoch_current(self.adapter.studies._study(study_id)))
            with self.assertRaisesRegex(WorkbenchError,'historical admission'):
                self.adapter.admit(study_id,body,self.checkpoint(),'native-study-first-attempt')
            cold=self.adapter.studies._study(study_id)
            with self.assertRaisesRegex(WorkbenchError,'Explicitly continue'):
                self.adapter.admit(study_id,self.admission_body(cold,trial),self.checkpoint(),'native-study-uncontinued')
            lowered=dict(cold['limits']);lowered['retained_bytes']=envelope['retained_bytes']-1
            before=self.session.snapshot
            with self.assertRaises(WorkbenchError):
                self.projection.history.save_study(study_id,dict(revision=cold['revision'],name=cold['name'],
                    policy=cold['policy'],limits=lowered),self.checkpoint(),'native-study-lower-spent-budget')
            self.assertEqual(self.session.snapshot,before);self.assert_no_local_authority()
            continued=self.continue_study(study_id,'native-study-fresh-continue')
            self.assertGreater(continued['admission_epoch'],current['admission_epoch'])
            self.assert_no_local_authority(cold=False)
            receipts=list(self.db.execute('SELECT actor_id,operation_id,request_key,document FROM model_operation_receipts'))
            self.assertEqual(len(receipts),1)
            self.assertEqual((receipts[0]['operation_id'],receipts[0]['request_key']),
                ('studies.continue','native-study-fresh-continue'))
            self.assertEqual(receipts[0]['actor_id'],self.owner.identity['actor_id'])
            self.assertEqual(json.loads(receipts[0]['document']),continued)
        second=self.adapter.admit(study_id,self.admission_body(continued,trial),self.checkpoint(),'native-study-fresh-attempt')
        self.assertNotEqual(second['run_id'],first['id'])
        self.assert_completed_science(second['run_id'])
        self.assertEqual(self.projection.history.study(study_id)['charged'],
            {key:2*value for key,value in envelope.items()})
        self.assertEqual(self.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0],1)
        self.assertIsNone(self.db.execute('SELECT id FROM workspace_runs WHERE id=%s',(first['id'],)).fetchone())
        self.execution.reconcile_current()

    def test_native_study_admission_canonical_ack_then_sql_failure_never_starts_training(self):
        study_id,trial,composition,envelope=self.prepare_study()
        current=self.continue_study(study_id,'native-study-fault-continue')
        self.db.execute('CREATE TEMP TABLE study_ack_parent(id INT PRIMARY KEY)')
        self.db.execute('CREATE TEMP TABLE study_ack_child(id INT REFERENCES study_ack_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        original=self.db._project_before_commit;fired=[]
        def fail_admission_commit():
            identities=list(self.execution._dirty_runs)
            original()
            if identities and not fired:
                canonical=operation_records(self.store.snapshot()['records'])
                fact=canonical['native-study-failed-ack']['result']
                self.assertIn(fact['run_id'],identities)
                self.assertEqual(fact['trial_id'],trial['id'])
                fired.append(fact)
                self.db.execute('INSERT INTO study_ack_child VALUES(1)')
        original_go=recipe_process.Handle.go
        def probe_only_go(handle,expected):
            phase=next(item['document'] for item in self.store.snapshot()['records']
                if item['family']=='native_execution_history' and item['document']['phase_id']==handle.spec['attempt_id'])
            self.assertEqual(phase['phase'],'probe','A child beyond qualification started before admission ACK')
            return original_go(handle,expected)
        with patch.object(self.db,'_project_before_commit',new=fail_admission_commit), \
                patch.object(recipe_process.Handle,'go',probe_only_go):
            with self.assertRaises(ProjectSessionError) as failed:
                self.adapter.admit(study_id,self.admission_body(current,trial),self.checkpoint(),'native-study-failed-ack')
        self.assertEqual(failed.exception.code,'projection_unavailable')
        self.assertIsInstance(failed.exception.__cause__,psycopg.errors.ForeignKeyViolation)
        self.assertEqual(len(fired),1);self.assertFalse(self.session.available)
        self.assert_no_local_authority(cold=False)
        self.assertIsNone(self.execution._runs._thread)
        retained=self.store.snapshot()['records']
        fact=operation_records(retained)['native-study-failed-ack']['result']
        self.assertEqual(fact,fired[0])
        self.assertFalse(any(item['family']=='native_execution_history' and item['document']['phase'] in ('train','verify')
            for item in retained))
        with patch('subprocess.Popen',side_effect=AssertionError('ACK failure reconciliation launched')):
            self.execution.reconcile_current()
            self.assert_no_local_authority(cold=False);self.assertTrue(self.session.available)
            old=self.projection;old.close();self.closed_projections.add(id(old))
            self.open_projection();self.assert_no_local_authority();self.assertIsNone(self.execution._runs)
            self.assertEqual(operation_records(self.session.snapshot['records'])['native-study-failed-ack']['result'],fact)
            self.assertEqual(self.projection.history.study(study_id)['charged'],envelope)
            with self.assertRaisesRegex(WorkbenchError,'historical admission'):
                self.adapter.admit(study_id,self.admission_body(current,trial),self.checkpoint(),'native-study-failed-ack')


@unittest.skipUnless(os.environ.get('TULDOK_NATIVE_PROJECT_GO')=='1'
    and os.environ.get('TULDOK_NATIVE_RETAINED_SOURCE')
    and os.environ.get('TULDOK_PROJECT_FILES_COLD_DATABASE_URL') and NATIVE_PYTHON is not None and NATIVE_PYTHON.is_file(),
    'Explicit retained Study continuation qualification only; one fresh admission')
class NativeRetainedStudyTailTests(unittest.TestCase):
    """Reuse the measured first Study Run; only the fresh current Run fits."""
    setUp=NativeStudyCustodyTests.setUp
    cleanup=NativeStudyCustodyTests.cleanup
    open_projection=NativeStudyCustodyTests.open_projection
    checkpoint=NativeStudyCustodyTests.checkpoint
    retain_before_cleanup=NativeStudyCustodyTests.retain_before_cleanup
    assert_no_local_authority=NativeStudyCustodyTests.assert_no_local_authority
    continue_study=NativeStudyCustodyTests.continue_study
    admission_body=staticmethod(NativeStudyCustodyTests.admission_body)
    await_drained=NativeStudyCustodyTests.await_drained
    assert_completed_science=NativeStudyCustodyTests.assert_completed_science

    def metadata(self,name,*,project_id=None):
        return NativeStudyCustodyTests.metadata(self,name,project_id=project_id,
            dsn=os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL'])

    def test_retained_study_cold_budget_then_one_fresh_current_admission(self):
        retained=qa_retained_path(os.environ['TULDOK_NATIVE_RETAINED_SOURCE'])
        receipt=json.loads((retained/'receipt.json').read_bytes())
        raw=(retained/'snapshot.json').read_bytes();manifest_raw=(retained/'project.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),receipt['snapshot_sha256'])
        self.assertEqual(hashlib.sha256(manifest_raw).hexdigest(),receipt['manifest_sha256'])
        snapshot=json.loads(raw);manifest=json.loads(manifest_raw)
        self.assertEqual(snapshot['checkpoint'],manifest['checkpoint']);self.assertEqual(snapshot['checkpoint'],receipt['checkpoint'])
        self.assertEqual(snapshot['project_id'],manifest['project_id']);self.assertEqual(snapshot['project_id'],receipt['project_id'])
        source_database=psycopg.conninfo.conninfo_to_dict(connection_info(os.environ['TULDOK_DATABASE_URL']))['dbname']
        database,can_connect=self.host.db.execute(
            "SELECT current_database(),has_database_privilege(current_user,%s,'CONNECT')",(source_database,)).fetchone()
        self.assertNotEqual(database,source_database);self.assertFalse(can_connect)
        source=self.root/'exact-retained-study';source.mkdir();(source/'.tuldok').mkdir()
        indexed={(item['family'],item['id']):item for item in snapshot['records']}
        self.assertEqual(len(indexed),len(manifest['inventory']))
        for entry in manifest['inventory']:
            document=indexed[(entry['family'],entry['id'])]['document'];encoded=canonical(document)
            self.assertEqual(hashlib.sha256(encoded).hexdigest(),entry['sha256']);self.assertEqual(len(encoded),entry['bytes'])
            relative='records/'+entry['family']+'/'+entry['id']+'/'+entry['sha256']+'.json'
            self.assertEqual(entry['path'],relative)
            target=source/'.tuldok'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(encoded)
        (source/'.tuldok/project.json').write_bytes(manifest_raw)
        artifact_root=source/'artifacts/sha256';artifact_root.mkdir(parents=True)
        for item in snapshot['records']:
            if item['family']!='project_artifact':continue
            declaration=item['document'];contents=(retained.parent/'artifacts/sha256'/declaration['sha256']).read_bytes()
            self.assertEqual(hashlib.sha256(contents).hexdigest(),declaration['sha256'])
            self.assertEqual(len(contents),declaration['bytes']);(artifact_root/declaration['sha256']).write_bytes(contents)
        original_runs=[item for item in snapshot['records'] if item['family']=='run_history']
        self.assertEqual(len(original_runs),1);old=original_runs[0]['document']['run'];self.assertEqual(old['state'],'completed')
        study_docs=[item['document'] for item in snapshot['records'] if item['family']=='study_history']
        trial_docs=[item['document'] for item in snapshot['records'] if item['family']=='trial_history']
        self.assertEqual(len(study_docs),1);self.assertEqual(len(trial_docs),1)
        study_id=study_docs[0]['study']['id'];trial=trial_docs[0]['trial']
        with patch('subprocess.Popen',side_effect=AssertionError('Retained Study Open executed')):
            empty=self.projection;empty.close();self.closed_projections.add(id(empty))
            self.store=ProjectStore.open(source);self.extra_stores.append(self.store);self.open_projection()
            self.assertEqual(self.session.snapshot,snapshot);self.assert_no_local_authority()
            material=self.projection.materials.recipe(trial['material']);envelope=material['material']['resource_envelope']
            self.assertEqual(self.projection.history.study(study_id)['charged'],envelope)
            current=self.adapter.studies._study(study_id);self.assertFalse(self.adapter.epoch_current(current))
            with self.assertRaisesRegex(WorkbenchError,'Explicitly continue'):
                self.adapter.admit(study_id,self.admission_body(current,trial),self.checkpoint(),'retained-study-before-continue')
            with self.assertRaisesRegex(WorkbenchError,'historical admission'):
                self.adapter.admit(study_id,self.admission_body(current,trial),self.checkpoint(),'native-study-first-attempt')
            continued=self.continue_study(study_id,'retained-study-fresh-continue')
            self.assertGreater(continued['admission_epoch'],current['admission_epoch'])
            self.assert_no_local_authority(cold=False)
            receipts=list(self.db.execute('SELECT actor_id,operation_id,request_key,document FROM model_operation_receipts'))
            self.assertEqual(len(receipts),1)
            self.assertEqual((receipts[0]['actor_id'],receipts[0]['operation_id'],receipts[0]['request_key']),
                (self.owner.identity['actor_id'],'studies.continue','retained-study-fresh-continue'))
            self.assertEqual(json.loads(receipts[0]['document']),continued)
        admitted=self.adapter.admit(study_id,self.admission_body(continued,trial),self.checkpoint(),'retained-study-fresh-attempt')
        self.assertNotEqual(admitted['run_id'],old['id']);self.assert_completed_science(admitted['run_id'])
        self.assertEqual(self.projection.history.study(study_id)['charged'],{key:2*value for key,value in envelope.items()})
        self.assertEqual(self.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM model_attempt_reservations').fetchone()[0],1)
        self.assertIsNone(self.db.execute('SELECT id FROM workspace_runs WHERE id=%s',(old['id'],)).fetchone())
        self.assertIsNone(self.db.execute('SELECT run_id FROM model_attempt_reservations WHERE run_id=%s',(old['id'],)).fetchone())
        final={(item['family'],item['id']):item for item in self.session.snapshot['records']}
        for item in snapshot['records']:
            if item['family'] in ('run_history','native_execution_history'):
                self.assertEqual(final[(item['family'],item['id'])],item)
        self.execution.reconcile_current()
