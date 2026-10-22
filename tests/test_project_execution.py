"""Current host authority and real neutral project Run custody.

Only disposable PostgreSQL catalogs and the existing authored generic fixture
belong here. Actual host execution cases require a lead-coordinated source freeze.
"""
import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from access import Access, AccessError, ActorContext, _CURRENT, current_context
from metadata import Metadata, connection_info
from project_execution import ProjectExecution, validate_operation_result
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ProjectAccessBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='tuldok-project-execution-')
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.databases = []
        self.addCleanup(self.cleanup)
        self.host = self.metadata('host')
        self.host_access = Access(self.host, self.host.path)
        session = self.host_access.exchange(self.host_access._local_owner_token(initial=True))
        self.token, self.owner = session['token'], session['identity']
        self.local = self.metadata('projection', projection=True)
        self.bridge = Access(self.local, self.local.path, authority=self.host_access)

    def metadata(self, name, projection=False):
        kwargs = dict(dataset_id=uuid.uuid4().hex, projection_id=uuid.uuid4().hex) if projection else {}
        db = Metadata(self.root/name, **kwargs)
        self.databases.append(db)
        return db

    def cleanup(self):
        import psycopg
        from psycopg import sql
        for db in reversed(self.databases):db.close()
        with psycopg.connect(connection_info(), autocommit=True) as connection:
            for db in self.databases:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(db.schema)))

    def assert_no_credentials(self):
        for table in ('access_actors','access_credentials'):
            self.assertEqual(self.local.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)

    def test_current_host_identity_is_retagged_without_minting_or_copying(self):
        self.assertIsNone(current_context())
        with self.host_access.bind(self.token):
            original = current_context()
            context = self.bridge.require('execute', 'runs.submit', owner_only=True)
            self.assertEqual(context.catalog_id, self.local.dataset_id)
            self.assertEqual(context.actor_id, original.actor_id)
            self.assertEqual(current_context(), original)
            self.assertEqual(self.bridge.identity()['catalog_id'], self.local.dataset_id)
            calls = (lambda: self.bridge._local_owner_token(),
                     lambda: self.bridge.exchange(self.token),
                     lambda: self.bridge.issue({'label':'No copied identity','scopes':['inspect']}),
                     lambda: self.bridge.revoke(original.credential_id),
                     lambda: self.bridge.logout(), lambda: self.bridge._resolve(self.token),
                     lambda: self.bridge._mint(original.actor_id,'bearer',['inspect'],600))
            for call in calls:
                with self.assertRaises(AccessError):call()
            with self.assertRaises(AccessError):
                with self.bridge.bind(self.token):pass
        self.assert_no_credentials()

    def test_wrong_host_forged_logical_credential_and_host_system_refuse(self):
        other_db = self.metadata('other-host')
        other = Access(other_db, other_db.path)
        token = other.exchange(other._local_owner_token())['token']
        with other.bind(token), self.assertRaises(AccessError):
            self.bridge.require('inspect','runs.list')
        marker = _CURRENT.set(ActorContext(self.local.dataset_id,self.owner['actor_id'],self.owner['credential_id']))
        try:
            with self.assertRaises(AccessError):self.bridge.require('inspect','runs.list')
        finally:_CURRENT.reset(marker)
        with self.host_access._reconcile(), self.assertRaises(AccessError):
            self.bridge.require('inspect','runs.list')
        with self.bridge._reconcile():
            self.bridge.require('cancel','runs.reconcile')
            with self.assertRaises(AccessError):self.bridge.require('execute','runs.submit')
        self.assert_no_credentials()

    def test_live_scopes_revocation_and_expiry_are_checked_on_every_use(self):
        with self.host_access.bind(self.token):
            agent = self.host_access.issue({'label':'Current agent','scopes':['inspect','edit','execute']})
        with self.host_access.bind(agent['token']):
            self.bridge.require('edit','record.edit')
            self.bridge.require_external_submission()
            with self.assertRaises(AccessError):self.bridge.require('execute','runs.submit')
            with self.assertRaises(AccessError):self.bridge.grant_execution('a'*64,agent['identity']['actor_id'])
            with self.host_access.bind(self.token):self.host_access.revoke(agent['identity']['credential_id'])
            with self.assertRaises(AccessError):self.bridge.identity()
        with self.host_access.bind(self.token):
            expired = self.host_access.issue({'label':'Expires during request','scopes':['inspect']})
        with self.host_access.bind(expired['token']):
            self.host.execute('UPDATE access_credentials SET expires_at=0 WHERE id=%s',(expired['identity']['credential_id'],))
            with self.assertRaises(AccessError):self.bridge._context()
        self.assert_no_credentials()

    def test_current_grant_and_exact_local_job_survive_revocation_without_new_authority(self):
        request = hashlib.sha256(b'authored exact admission').hexdigest();run_id=uuid.uuid4().hex
        with self.host_access.bind(self.token):
            agent = self.host_access.issue({'label':'Bounded external submitter','scopes':['inspect','execute']})
            grant = self.bridge.grant_execution('b'*64,agent['identity']['actor_id'])
        self.assertEqual(grant['catalog_id'], self.local.dataset_id)
        with self.host_access.bind(agent['token']), self.local.transaction():
            admission = self.bridge._consume_external_run(grant['id'],'b'*64,run_id,request)
        with self.host_access.bind(self.token):self.host_access.revoke(agent['identity']['credential_id'])
        with self.bridge._job('runs',run_id,admission,request):
            self.bridge.require('edit','runs.update',run_id)
            self.bridge.require_job('runs',run_id,admission,request)
            for action,target in (('runs.update',uuid.uuid4().hex),('runs.cancel',run_id)):
                with self.assertRaises(AccessError):self.bridge.require('edit',action,target)
            with self.assertRaises(AccessError):self.bridge.require('execute','runs.submit')
        with self.assertRaises(AccessError):
            with self.bridge._job('runs',run_id,uuid.uuid4().hex,request):pass
        fresh = self.metadata('cold-projection',projection=True)
        cold = Access(fresh,fresh.path,authority=self.host_access)
        with self.assertRaises(AccessError):
            with cold._job('runs',run_id,admission,request):pass
        self.assert_no_credentials()

    def test_unbound_threads_get_no_owner_or_job_default(self):
        errors=[]
        def worker():
            try:self.bridge.require('inspect','runs.list')
            except AccessError as error:errors.append(error.code)
        with self.host_access.bind(self.token):
            thread=threading.Thread(target=worker);thread.start();thread.join(5)
        self.assertEqual(errors,['unauthenticated'])

    def test_logical_identity_collision_keeps_bridge_inert_and_execution_unavailable(self):
        db=Metadata(self.root/'same-logical-project',dataset_id=self.host.dataset_id,projection_id=uuid.uuid4().hex)
        self.databases.append(db)
        bridge=Access(db,db.path,authority=self.host_access)
        with self.host_access.bind(self.token):
            # Ordinary project metadata still uses the current host Access.
            self.host_access.require('edit','project_files.data_edit')
            with self.assertRaises(AccessError) as failure:bridge.require_external_submission()
            self.assertEqual(failure.exception.code,'unavailable')
            with self.assertRaises(AccessError):bridge.grant_execution('a'*64,self.owner['actor_id'])
        for table in ('access_actors','access_credentials','access_admissions','access_execution_grants'):
            self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)


class ExecutionObservationTests(unittest.TestCase):
    def test_run_receipt_binds_exact_retained_identity_and_rejects_live_fields(self):
        value=dict(format='project_run_admission_v1',origin_catalog_id='a'*32,run_id='b'*32,request_sha256='c'*64)
        record=dict(family='run_history',id='a'*32+'.'+'b'*32,document={'run':dict(dataset_id='a'*32,id='b'*32,request_sha256='c'*64)})
        self.assertTrue(validate_operation_result('runs.submit_external',value,[record]))
        for changed in (dict(value,request_sha256='d'*64),dict(value,approval_id='e'*32),dict(value,token='secret')):
            with self.assertRaises(WorkbenchError):validate_operation_result('runs.submit_external',changed,[record])
        self.assertFalse(validate_operation_result('other.operation',{}))

    def test_failed_custody_ack_fences_even_when_sql_rolls_back(self):
        execution=ProjectExecution.__new__(ProjectExecution)
        execution.session=SimpleNamespace(available=True)
        owner=SimpleNamespace(_fence_coordinator=lambda:None)
        execution._runs=owner
        with patch.object(owner,'_fence_coordinator') as fence:
            with self.assertRaises(WorkbenchError):
                with execution._journal_guard():
                    raise WorkbenchError('Filesystem acknowledgement was lost.','outcome_unknown',409)
            self.assertFalse(execution.session.available);fence.assert_called_once()


class RunHostSourceTests(unittest.TestCase):
    def setUp(self):
        from runs import Runs
        from project_artifacts import ProjectArtifacts
        from project_store import ProjectStore
        self.tmp=tempfile.TemporaryDirectory(prefix='project-run-host-source-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.host=self.root/'host';self.host.mkdir()
        self.source=self.host/'helper.py';self.raw=b'# exact authored host helper\n';self.source.write_bytes(self.raw)
        self.sha=hashlib.sha256(self.raw).hexdigest()
        self.store=ProjectStore.create(self.root/'project','Host bytes','new-host-source','a'*64)
        self.addCleanup(self.store.close)
        self.artifacts=ProjectArtifacts(self.store);self.addCleanup(self.artifacts.close)
        self.records=[]
        self.owner=Runs.__new__(Runs)
        self.owner.dataset=SimpleNamespace(access=None,db=None,lock=threading.RLock())
        self.owner.project_execution=SimpleNamespace(session=SimpleNamespace(snapshot={'records':self.records}))
        self.run=dict(id='a'*32,dataset_id='b'*32,state='queued',custody_phase='prepared',custody_identity=None,
                      material=dict(recipe={'authored':'qualified neutral helper'},host_files={'helper.py':self.sha}))
        self.file_patch=patch('recipe_contract.__file__',str(self.host/'recipe_contract.py'));self.file_patch.start()
        self.addCleanup(self.file_patch.stop)
        self.identity_patch=patch('recipe_contract.recipe_host_identity',return_value={'helper.py':self.sha})
        self.identity=self.identity_patch.start();self.addCleanup(self.identity_patch.stop)

    def capture(self):return self.owner._capture_project_host_sources(self.run,self.artifacts)

    def retain(self,edges):
        self.records.append(dict(family='run_history',id=self.run['dataset_id']+'.'+self.run['id'],
            document=dict(origin_catalog_id=self.run['dataset_id'],run=copy.deepcopy(self.run),payloads=edges)))

    def test_exact_source_is_durable_and_later_updates_use_retained_bytes(self):
        edges=self.capture();self.assertEqual(edges[0]['name'],'host/helper.py')
        self.assertEqual(self.artifacts.read_blob(edges[0]['blob']),self.raw)
        self.retain(edges);self.run.update(state='interrupted',custody_phase='drained')
        self.source.write_bytes(b'# newer unqualified helper\n')
        self.identity.side_effect=AssertionError('Later observation consulted the current host')
        self.assertEqual(self.capture(),edges)
        self.assertEqual(self.artifacts.read_blob(edges[0]['blob']),self.raw)

    def test_hash_race_cannot_publish_source_under_admitted_identity(self):
        from project_artifacts import ProjectArtifactError
        publish=self.artifacts.publish_fd
        def changed(fd,declaration,**kwargs):
            self.source.write_bytes(b'# source changed after identity measurement\n')
            return publish(fd,declaration,**kwargs)
        with patch.object(self.artifacts,'publish_fd',side_effect=changed),self.assertRaises(ProjectArtifactError):
            self.capture()
        self.assertEqual(self.store.snapshot()['records'],[])

    def test_historical_missing_or_contradictory_host_cannot_be_retrofitted(self):
        self.retain([])
        with self.assertRaises(WorkbenchError) as error:self.capture()
        self.assertEqual(error.exception.code,'unavailable');self.identity.assert_not_called()
        self.records.clear();edges=self.capture();self.retain(edges)
        self.records[0]['document']['payloads'][0]['blob']['sha256']='f'*64
        with self.assertRaises(WorkbenchError):self.capture()


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class FileWriterReconciliationTests(unittest.TestCase):
    def setUp(self):
        from auth_helpers import ExplicitOwnerFixture
        from project_custody import ProjectCustody
        from project_projection import ProjectProjection
        from project_store import ProjectStore
        self.tmp=tempfile.TemporaryDirectory(prefix='project-file-reconciliation-');self.root=Path(self.tmp.name)
        self.databases=[];self.projections=[];self.addCleanup(self.cleanup)
        host_db=self.metadata('host');self.host=SimpleNamespace(db=host_db,access=Access(host_db,host_db.path))
        self.owner=ExplicitOwnerFixture.bootstrap(self.host)
        self.store=ProjectStore.create(self.root/'project','Current file custody','file-fixture','a'*64)
        control=self.root/'control';control.mkdir()
        self.manager=ProjectCustody(control,host_db.dataset_id)
        db=self.metadata('projection',self.store.snapshot()['project_id'],uuid.uuid4().hex)
        self.journal=self.manager.for_projection(self.store,db.projection_id)
        self.projection=ProjectProjection(self.store,db,self.host.access,{},custody=self.journal)
        self.projections.append(self.projection);self.execution=self.projection.execution;self.session=self.projection.session
        self.enterContext(self.owner.bound(self.host))
        self.key='original-file-writer';self.input_sha='b'*64;self.content_sha='c'*64
        self.enterContext(patch('runs.Runs',side_effect=AssertionError('File recovery constructed Runs')))
        self.enterContext(patch('subprocess.Popen',side_effect=AssertionError('File recovery launched a process')))

    def metadata(self,name,logical=None,physical=None):
        kwargs={} if logical is None else dict(dataset_id=logical,projection_id=physical)
        db=Metadata(self.root/name,**kwargs);self.databases.append(db);return db

    def cleanup(self):
        import psycopg
        from psycopg import sql
        for projection in reversed(self.projections):
            if projection.sources is not None:projection.sources.close()
            projection.artifacts.close()
        for db in reversed(self.databases):db.close()
        if hasattr(self,'store'):self.store.close()
        with psycopg.connect(connection_info(),autocommit=True) as connection:
            for schema in {db.schema for db in self.databases}:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
        self.tmp.cleanup()

    def start(self,kind):
        context=(self.execution.runtime_effect if kind=='runtime' else self.execution.package_effect)
        with context(self.key,self.input_sha,self.content_sha) as effect:effect.publication_started()

    def decision(self,name):
        from test_project_history import policy
        return self.projection.history.create_study(dict(name=name,limits=dict(attempt_slots=1,
            admitted_wall_seconds=100,retained_bytes=10000,peak_staging_bytes=10000),policy=policy()),
            self.session.snapshot['checkpoint'],uuid.uuid4().hex)

    def test_package_guard_preserves_partial_bytes_until_acknowledged_owner_decision(self):
        self.start('package');partial=self.root/'partial-package';partial.write_bytes(b'Preserve exact partial bytes')
        with self.execution.package_reconciliation(self.key,self.input_sha,self.content_sha,self.session.snapshot['checkpoint']):
            self.assertTrue(self.journal.has_pending)
        self.assertTrue(self.journal.has_pending)
        with self.execution.package_reconciliation(self.key,self.input_sha,self.content_sha,self.session.snapshot['checkpoint']) as effect:
            self.decision('Acknowledged controlled owner decision')
            effect.confirmed()
        self.assertFalse(self.journal.has_pending);self.assertEqual(partial.read_bytes(),b'Preserve exact partial bytes')
        self.assertIsNone(self.execution._package_active);self.assertIsNone(self.execution._runs)

    def test_runtime_prepare_recovers_exact_unknown_canonical_and_reconstructs_before_retry(self):
        from project_store import ProjectStoreError
        self.start('runtime');before=self.session.snapshot;original=self.store.commit
        def lost(*args,**kwargs):
            original(*args,**kwargs)
            raise ProjectStoreError('Actual canonical selection lost its acknowledgement.','unknown',409)
        with patch.object(self.store,'commit',side_effect=lost),self.assertRaises(ProjectStoreError):
            self.decision('Canonical science selected before SQL rollback')
        self.assertFalse(self.session.available)
        observed=self.execution.runtime_pending(self.key)
        self.assertEqual(observed,dict(request_key=self.key,input_sha256=self.input_sha,manifest_sha256=self.content_sha))
        recovered=self.execution.prepare_runtime_reconciliation(self.key,self.input_sha,self.content_sha,before['checkpoint'])
        self.assertTrue(self.session.available);self.assertNotEqual(recovered['checkpoint'],before['checkpoint'])
        self.assertIsNone(self.execution._runtime_active);self.assertTrue(self.journal.has_pending)
        self.assertEqual(self.projection.db.execute('SELECT count(*) FROM model_studies').fetchone()[0],1)
        with self.execution.runtime_effect(self.key,self.input_sha,self.content_sha) as effect:
            effect.publication_started();self.decision('Explicit normal runtime retry acknowledged');effect.confirmed()
        self.assertFalse(self.journal.has_pending)

    def test_original_retained_projection_can_restore_but_foreign_physical_owner_cannot(self):
        from project_projection import ProjectProjection
        self.start('runtime');old=self.projection;identity=old.db.projection_id
        old.artifacts.close();old.db.close()
        db=Metadata(old.db.path,create=False,dataset_id=self.store.snapshot()['project_id'],projection_id=identity)
        self.databases.append(db)
        journal=self.manager.for_projection(self.store,identity)
        retained=ProjectProjection(self.store,db,self.host.access,{},custody=journal,restore=False)
        self.projections.append(retained);self.projection=retained;self.execution=retained.execution;self.session=retained.session
        self.assertFalse(self.session.available)
        restored=self.execution.prepare_runtime_reconciliation(self.key,self.input_sha,self.content_sha,self.session.snapshot['checkpoint'])
        self.assertEqual(restored,self.session.snapshot);self.assertTrue(self.session.available);self.assertTrue(journal.has_pending)
        foreign_db=self.metadata('foreign',db.dataset_id,uuid.uuid4().hex)
        foreign=ProjectProjection(self.store,foreign_db,self.host.access,{},
            custody=self.manager.for_projection(self.store,foreign_db.projection_id))
        self.projections.append(foreign)
        with self.assertRaises(WorkbenchError) as denied:
            foreign.execution.prepare_runtime_reconciliation(self.key,self.input_sha,self.content_sha,foreign.session.snapshot['checkpoint'])
        self.assertEqual(denied.exception.code,'unavailable');self.assertTrue(journal.has_pending)

    def test_wrong_tuple_active_writer_and_unrelated_checkout_never_clear_or_adopt(self):
        self.start('package');checkpoint=self.session.snapshot['checkpoint']
        with patch.object(self.store,'recover_checkpoint',side_effect=AssertionError('Rejected tuple touched selection')):
            for content in ('d'*64,):
                with self.assertRaises(WorkbenchError):
                    with self.execution.package_reconciliation(self.key,self.input_sha,content,checkpoint):pass
            self.execution._package_active=self.key
            try:
                with self.assertRaises(WorkbenchError):
                    with self.execution.package_reconciliation(self.key,self.input_sha,self.content_sha,checkpoint):pass
            finally:self.execution._package_active=None
        self.store.commit([],checkpoint,'unrelated-checkout','e'*64)
        with self.assertRaises(WorkbenchError) as rejected:
            with self.execution.package_reconciliation(self.key,self.input_sha,self.content_sha,checkpoint):pass
        self.assertEqual(rejected.exception.code,'stale_project');self.assertFalse(self.session.available)
        self.assertEqual(self.session.snapshot['checkpoint'],checkpoint);self.assertTrue(self.journal.has_pending)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable PostgreSQL')
class ProjectRunCustodyTests(unittest.TestCase):
    """Real generic external recipe, trusted custodian, no provider or model fit."""
    def setUp(self):
        from project_store import ProjectStore
        from project_projection import ProjectProjection
        from test_project_files_material_http import neutral_source
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-current-project-run-')
        self.root=Path(self.temporary.name);self.addCleanup(self.temporary.cleanup)
        self.databases=[];self.projections=[];self.stores=[];self.addCleanup(self.cleanup)
        self.source_root=self.root/'source';self.source_root.mkdir()
        self.manifest,self.manifest_raw,self.definition_raw,self.source,self.input=neutral_source(self.source_root)
        self.host=self.metadata('host');self.access=Access(self.host,self.host.path)
        self.token=self.access.exchange(self.access._local_owner_token())['token']
        self.enterContext(self.access.bind(self.token))
        self.store=ProjectStore.create(self.root/'project','Neutral current custody','new-custody','a'*64)
        self.stores.append(self.store)
        self.db=self.metadata('projection',self.store.snapshot()['project_id'])
        self.projection=ProjectProjection(self.store,self.db,self.access,{'fixture':self.source_root})
        self.projections.append(self.projection);self.execution=self.projection.execution
        self.session=self.projection.session
        registration=self.projection.source_adapter.register(dict(root='fixture',manifest_path='project.json'),self.checkpoint(),'source-register')
        self.assertEqual(registration['origin_catalog_id'],self.db.dataset_id)
        body=dict(name='Neutral custody',project_id=self.manifest['id'],recipe_id='neutral',
            expected_sha256=hashlib.sha256(self.definition_raw).hexdigest(),inputs={
                'sample':dict(reference_id='sample',expected_sha256=hashlib.sha256(self.input).hexdigest())})
        self.graph=self.projection.materials.mutate_definition('pipeline_graph','graphs.create_external',None,body,
            self.checkpoint(),'graph-create',lambda:self.projection.pipelines.create_external(body))
        self.preflight=self.execution.preflight_external(self.graph['id'],self.graph['revision'])

    def metadata(self,name,catalog_id=None):
        args=dict(dataset_id=catalog_id,projection_id=uuid.uuid4().hex) if catalog_id is not None else {}
        db=Metadata(self.root/(name+'-'+uuid.uuid4().hex),**args);self.databases.append(db)
        return db

    def cleanup(self):
        import psycopg
        from psycopg import sql
        for projection in reversed(self.projections):
            execution=getattr(projection,'execution',None)
            if execution is not None and execution._runs is not None:
                with execution.runtime_access._reconcile():execution._runs.close()
            # This explicit fixture teardown follows actual worker drain even
            # when a fault intentionally keeps the public lifecycle fenced.
            if projection.sources is not None:projection.sources.close()
            projection.artifacts.close()
        for db in reversed(self.databases):db.close()
        for store in reversed(self.stores):store.close()
        with psycopg.connect(connection_info(),autocommit=True) as connection:
            for db in self.databases:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(db.schema)))

    def checkpoint(self):return self.session.snapshot['checkpoint']
    def body(self):return dict(graph_id=self.graph['id'],graph_revision=self.graph['revision'],expected_digest=self.preflight['material_sha256'])
    def record(self,identity):
        return next(item['document'] for item in self.store.snapshot()['records']
                    if item['family']=='run_history' and item['document']['run']['id']==identity)
    def await_drained(self,identity,timeout=30):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            with self.db.lock:
                row=self.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(identity,)).fetchone()
                run=json.loads(row['document'])
                health=self.execution.health()
            if run['state'] in ('completed','failed','cancelled','interrupted','unknown') and health['active_count']==0:
                return run
            time.sleep(.03)
        self.fail('Current neutral Run did not drain: '+repr(run))

    def test_real_custodian_has_canonical_go_intent_and_terminal_payloads_before_ack(self):
        import recipe_process
        from project_projection import ProjectProjection
        self.assertIsNone(self.execution._runs)
        with self.assertRaises(WorkbenchError):self.execution.submit_external(self.body(),'0'*64,'stale-submit')
        self.assertIsNone(self.execution._runs)
        observed=[];original_go=recipe_process.Handle.go
        def go(handle,expected):
            retained=self.record(handle.spec['attempt_id'])
            self.assertEqual(retained['run']['custody_phase'],'go_intent')
            row=self.db.execute('SELECT document FROM workspace_runs WHERE id=%s',(handle.spec['attempt_id'],)).fetchone()
            self.assertEqual(json.loads(row['document'])['custody_phase'],'go_intent')
            observed.append('canonical-go-intent')
            return original_go(handle,expected)
        original_outcome=self.db._project_outcome
        def outcome(kind):
            if kind=='committed':
                for row in self.db.execute("SELECT id FROM workspace_runs WHERE document::jsonb->>'state'='completed'"):
                    document=self.record(row['id'])
                    self.assertEqual(document['run']['state'],'completed')
                    for edge in document['payloads']:
                        self.assertEqual(self.projection.artifacts.status(dict(format='project_artifact_v1',**edge['blob']))['state'],'verified')
                    observed.append('canonical-terminal-before-sql-outcome')
            original_outcome(kind)
        with patch.object(recipe_process.Handle,'go',go),patch.object(self.db,'_project_outcome',outcome):
            admitted=self.execution.submit_external(self.body(),self.checkpoint(),'real-neutral-submit')
            completed=self.await_drained(admitted['run_id'])
        self.assertEqual(completed['state'],'completed',completed.get('error'))
        self.assertEqual(observed,['canonical-go-intent','canonical-terminal-before-sql-outcome'])
        self.assertEqual(self.execution.submit_external(self.body(),'0'*64,'real-neutral-submit'),admitted)
        retained=self.record(admitted['run_id'])
        self.assertEqual(retained['run']['state'],'completed')
        self.assertEqual(retained['run']['request_sha256'],admitted['request_sha256'])
        edges={item['name']:item for item in retained['payloads']}
        self.assertEqual(self.projection.artifacts.read_blob(edges['input/sample']['blob']),self.input)
        self.assertEqual(self.projection.artifacts.read_blob(edges['source/recipe.py']['blob']),self.source)
        output=self.projection.artifacts.read_blob(edges['result.txt']['blob'])
        self.assertIn(self.input,output)
        receipt=recipe_process.validate_receipt(self.projection.artifacts.read_blob(edges['custody-receipt.json']['blob']),completed['custody_identity'])
        self.assertTrue(receipt['drained']);self.assertEqual(receipt['outcome'],'completed')
        self.execution.reconcile_current()
        self.execution.assert_quiescent()
        # Fresh projection consumes only portable facts, never source SQL
        # admissions/grants, saved PID handles, queues or operation replay.
        cold_db=self.metadata('cold-projection',self.db.dataset_id)
        with patch('runs.Runs',side_effect=AssertionError('Cold Open constructed Runs')), \
             patch('subprocess.Popen',side_effect=AssertionError('Cold Open launched a process')):
            cold=ProjectProjection(self.store,cold_db,self.access,{})
            self.projections.append(cold)
            for table in ('workspace_runs','access_admissions','access_execution_grants','access_execution_consumptions'):
                self.assertEqual(cold_db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            self.assertIsNone(cold.execution._runs)
            self.assertEqual(cold.execution.health()['active_count'],0)
            with self.assertRaises(WorkbenchError):cold.execution.submit_external(self.body(),cold.session.snapshot['checkpoint'],'real-neutral-submit')
            self.assertIsNone(cold.execution._runs)

    def test_current_approval_receipt_cannot_reissue_after_cold_projection(self):
        from project_projection import ProjectProjection
        actor=self.access.identity()['actor_id'];body=dict(self.body(),consumer_actor_id=actor)
        current=self.execution.approve_external(body,self.checkpoint(),'local-only-approval')
        self.assertTrue(current['current_local'])
        self.assertEqual(current,self.execution.approve_external(body,'0'*64,'local-only-approval'))
        canonical=next(item['document']['result'] for item in self.store.snapshot()['records']
            if item['family']=='project_operation' and item['document']['request_key']=='local-only-approval')
        self.assertEqual(canonical['format'],'project_execution_approval_v1')
        self.assertNotIn('grant',canonical);self.assertNotIn('approver_credential_id',canonical)
        cold_db=self.metadata('cold-approval',self.db.dataset_id)
        cold=ProjectProjection(self.store,cold_db,self.access,{})
        self.projections.append(cold)
        with patch('runs.Runs',side_effect=AssertionError('Historical approval constructed Runs')):
            with self.assertRaises(WorkbenchError):cold.execution.approve_external(body,cold.session.snapshot['checkpoint'],'local-only-approval')
        self.assertEqual(cold_db.execute('SELECT count(*) FROM access_execution_grants').fetchone()[0],0)

    def test_lost_go_commit_ack_never_sends_go_and_requires_exact_current_reconcile(self):
        import recipe_process
        import psycopg
        original_transaction=psycopg.Connection.transaction;injected=[];original_go=recipe_process.Handle.go
        go_calls=[]
        @contextmanager
        def transaction(connection,*args,**kwargs):
            with original_transaction(connection,*args,**kwargs):yield
            if connection is self.db.connection and not injected:
                rows=connection.execute("SELECT document FROM workspace_runs WHERE document::jsonb->>'custody_phase'='go_intent'").fetchall()
                if rows:
                    injected.append('lost-after-actual-go-intent-commit')
                    raise OSError('Injected lost SQL acknowledgement after canonical intent')
        def go(handle,expected):
            go_calls.append(True)
            return original_go(handle,expected)
        with patch.object(psycopg.Connection,'transaction',transaction),patch.object(recipe_process.Handle,'go',go):
            admitted=self.execution.submit_external(self.body(),self.checkpoint(),'go-ack-fault')
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                with self.execution._custody_lock:active=bool(self.execution._active_attempts)
                if injected and not active:break
                time.sleep(.03)
        self.assertEqual(len(injected),1);self.assertEqual(go_calls,[])
        self.assertFalse(self.session.available)
        self.assertEqual(self.record(admitted['run_id'])['run']['custody_phase'],'go_intent')
        with self.assertRaises(WorkbenchError):self.execution.assert_quiescent()
        recovered=self.execution.reconcile_current()
        self.assertTrue(recovered['available'])
        retained=self.record(admitted['run_id'])
        self.assertIn(retained['run']['state'],('interrupted','cancelled'))
        self.assertEqual(retained['run']['custody_phase'],'drained')
        edges={item['name']:item for item in retained['payloads']}
        receipt=recipe_process.validate_receipt(self.projection.artifacts.read_blob(edges['custody-receipt.json']['blob']),retained['run']['custody_identity'])
        self.assertTrue(receipt['drained']);self.assertEqual(go_calls,[])
        self.execution.assert_quiescent()

    def test_filesystem_publication_uncertainty_reconciles_exact_retained_writer_after_drain(self):
        from project_store import ProjectStoreError
        import recipe_process
        original_commit=self.store.commit;injected=[];go_calls=[]
        def commit(records,checkpoint,key,sha):
            result=original_commit(records,checkpoint,key,sha)
            if not injected and any(item['family']=='run_history' and
                    item['document']['run'].get('custody_phase')=='go_intent' for item in records):
                injected.append(True)
                self.store._unknown=True
                raise ProjectStoreError('Injected filesystem acknowledgement uncertainty after replacement','unknown',409)
            return result
        with patch.object(self.store,'commit',side_effect=commit), \
             patch.object(recipe_process.Handle,'go',side_effect=lambda *args:go_calls.append(True)):
            admitted=self.execution.submit_external(self.body(),self.checkpoint(),'go-filesystem-fault')
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                with self.execution._custody_lock:active=bool(self.execution._active_attempts)
                if injected and not active:break
                time.sleep(.03)
        self.assertEqual(len(injected),1);self.assertEqual(go_calls,[])
        self.assertFalse(self.session.available)
        with self.assertRaises(ProjectStoreError):self.store.snapshot()
        with self.assertRaises(WorkbenchError):self.execution.assert_quiescent()
        result=self.execution.reconcile_current()
        self.assertTrue(result['available']);self.assertEqual(result['run_ids'],[admitted['run_id']])
        retained=self.record(admitted['run_id'])
        self.assertIn(retained['run']['state'],('interrupted','cancelled'))
        self.assertEqual(retained['run']['custody_phase'],'drained')
        self.assertIn('custody-receipt.json',{item['name'] for item in retained['payloads']})
        self.assertEqual(go_calls,[])
        self.execution.assert_quiescent()


if __name__ == '__main__':unittest.main()
