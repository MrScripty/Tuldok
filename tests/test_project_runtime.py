"""Actual offline ELF inventory/copy and canonical two-phase runtime custody.

The selected python binary is /usr/bin/true: representative bytes, never a
runnable Python/model environment. No package install, probe or child is run.
"""
import copy
import errno
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from project_custody import ProjectCustody
from project_execution import ProjectExecution
from project_material import decode_records, validate_operation_result as material_result
from project_runtime import ProjectRuntime, validate_operation_result, _intent_key
from project_session import operation_documents, operation_records
from workbench import WorkbenchError
import test_project_material as material_fixture


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class RuntimeCaptureTests(unittest.TestCase):
    def setUp(self):
        f=self.fixture=material_fixture.CanonicalPublication('test_model_publication_is_canonical_before_ack_and_has_one_session_receipt')
        f.setUp();self.addCleanup(f.doCleanups)
        self.control=ProjectCustody(f.host.path,f.host.dataset_id)
        self.journal=self.control.for_projection(f.store,f.db.projection_id)
        projection=SimpleNamespace(session=f.session,db=f.db,access=f.access,materials=f.material,custody=self.journal)
        self.execution=projection.execution=ProjectExecution(projection)
        f.session._validate=self.validate
        self.runtime=ProjectRuntime(projection,resolve_configuration=self.resolve)
        python=f.path/'explicit-python';site=f.path/'explicit-packages'
        (python/'bin').mkdir(parents=True);(python/'lib/python3.12/lib-dynload').mkdir(parents=True)
        shutil.copyfile('/usr/bin/true',python/'bin/python3.12')
        (python/'lib/python3.12/lib-dynload/fixture.txt').write_text('fixture only')
        entries=[]
        for name in ('torch','numpy'):
            (site/name).mkdir(parents=True)
            (site/name/'__init__.py').write_text('raise AssertionError("Selected package must never be imported")\n')
            info=site/(name+'-0.0.dist-info');info.mkdir()
            (info/'METADATA').write_text('Name: '+name+'\nVersion: 0.0\n')
            (info/'LICENSE').write_text('Owned fixture')
            entries.extend([name,info.name])
        self.config=dict(schema_version=1,python_root=str(python),python_version='3.12',site_packages=str(site),packages=entries)
        self.request=dict(profile='owned-fixture');self.key='capture:fixture'
        self.cp=f.session.snapshot['checkpoint']

    def resolve(self,request):
        if request!=self.request:raise WorkbenchError('Choose a configured runtime source.','unavailable',409)
        return copy.deepcopy(self.config)

    def validate(self,records):
        decode_records(records)
        for receipt in operation_documents(records):
            if not (validate_operation_result(receipt['operation'],receipt['result'],records)
                    or material_result(receipt['operation'],receipt['result'],records)):
                raise WorkbenchError('Unowned fixture receipt.')

    def observed(self):
        with self.fixture.access.bind(self.fixture.owner.token):return self.runtime.inspect(self.request)

    def capture(self,observed=None,**kwargs):
        observed=observed or self.observed()
        with self.fixture.access.bind(self.fixture.owner.token):
            return self.runtime.capture(self.request,observed['inventory_sha256'],self.cp,self.key,reserve_bytes=0,**kwargs)

    def test_actual_capture_retains_intent_manifest_and_all_declarations_without_running_binaries(self):
        f=self.fixture
        with patch('subprocess.Popen',side_effect=AssertionError('No execution, probe or install')):
            observed=self.observed();result=self.capture(observed)
        records=f.session.snapshot['records'];receipts=operation_records(records)
        self.assertEqual(set(receipts),{_intent_key(self.key),self.key})
        self.assertEqual(receipts[_intent_key(self.key)]['operation'],'runtime.capture_intent')
        self.assertEqual(result['format'],'project_runtime_capture_v1')
        self.assertTrue(validate_operation_result('runtime.capture',result,records))
        self.assertEqual(result['actor_id'],f.owner.identity['actor_id'])
        material=next(r['document'] for r in records if r['family']=='runtime_material')
        declarations={r['id']:r['document'] for r in records if r['family']=='project_artifact'}
        self.assertEqual(len(material['artifacts']),observed['file_count']+1)
        self.assertEqual({e['preservation'] for e in material['artifacts'] if e['role']=='runtime_file'},{'regenerable'})
        for edge in material['artifacts']:
            self.assertEqual(declarations[edge['blob']['sha256']],dict(format='project_artifact_v1',**edge['blob']))
        raw=(Path(material['value']['descriptor']['root'])/'manifest.json').read_bytes()
        self.assertEqual(f.artifacts.read_blob(dict(sha256=result['manifest_sha256'],bytes=len(raw))),raw)
        unique=[edge for edge in material['artifacts'] if edge['preservation']=='unique']
        self.assertEqual([edge['name'] for edge in unique],['manifest.json'])
        file_edge=next(edge for edge in material['artifacts'] if edge['role']=='runtime_file')
        self.assertEqual(f.artifacts.inspect(dict(format='project_artifact_v1',**file_edge['blob']))['state'],'missing')
        self.assertFalse(self.execution.has_local_custody)
        self.assertFalse(self.journal.has_pending)
        self.assertEqual(self.control.pending(f.store),[])
        self.assertEqual(f.store.snapshot(),f.session.snapshot)

    def test_completed_replay_verifies_existing_target_without_source_reads_or_duplicate_owner_create(self):
        observed=self.observed();result=self.capture(observed)
        shutil.rmtree(self.config['python_root']);shutil.rmtree(self.config['site_packages'])
        before=self.fixture.store.snapshot()
        with (patch.object(self.runtime,'resolve_configuration',side_effect=AssertionError('No source replay')),
              patch.object(self.runtime.owner,'create',side_effect=AssertionError('No duplicate publication'))):
            replay=self.capture(observed)
        self.assertEqual(replay,result);self.assertEqual(self.fixture.store.snapshot(),before)
        self.assertFalse(self.journal.has_pending)
        with self.fixture.access.bind(self.fixture.owner.token):
            status=self.runtime.status(self.key)
        self.assertEqual(status['state'],'captured');self.assertEqual(status['result'],result)

    def test_copy_failure_keeps_durable_intent_and_pending_guard_until_explicit_same_key_retry(self):
        observed=self.observed();original=self.runtime.owner.create
        def stopped(*args,**kwargs):
            receipts=operation_records(self.fixture.store.snapshot()['records'])
            self.assertIn(_intent_key(self.key),receipts)
            self.assertEqual(self.journal.snapshot()['runtime_effects'][0]['request_key'],self.key)
            self.assertFalse(self.fixture.db.in_transaction)
            raise WorkbenchError('Injected copy failure.','stale',409)
        with patch.object(self.runtime.owner,'create',side_effect=stopped):
            with self.assertRaises(WorkbenchError) as caught:self.capture(observed)
        self.assertTrue(caught.exception.receipt['committed'])
        self.assertEqual(caught.exception.receipt['checkpoint'],self.fixture.store.snapshot()['checkpoint'])
        self.assertTrue(self.journal.has_pending)
        with self.assertRaises(WorkbenchError):self.execution.assert_quiescent()
        with self.fixture.access.bind(self.fixture.owner.token):self.assertEqual(self.runtime.status(self.key)['state'],'intent_recorded')
        completed=self.capture(observed)
        self.assertEqual(completed['manifest_sha256'],observed['inventory_sha256'])
        self.assertFalse(self.journal.has_pending);self.execution.assert_quiescent()

    def test_parent_fsync_unknown_does_not_ack_until_existing_target_verified_and_barrier_passes(self):
        import runtime_snapshots
        observed=self.observed();sync=runtime_snapshots.sync_directory
        def fault(directory):
            if Path(directory)==self.runtime.owner.path:raise OSError(errno.EIO,'Injected parent fsync failure')
            return sync(directory)
        with patch('runtime_snapshots.sync_directory',side_effect=fault):
            with self.assertRaises(WorkbenchError) as caught:self.capture(observed)
            self.assertEqual(caught.exception.code,'outcome_unknown')
            self.assertTrue((self.runtime.owner.path/observed['inventory_sha256']).exists())
            self.assertNotIn(self.key,operation_records(self.fixture.store.snapshot()['records']))
            with patch.object(self.runtime.owner,'create',side_effect=AssertionError('Never copy again')):
                with self.assertRaises(WorkbenchError):self.capture(observed)
        self.assertTrue(self.journal.has_pending)
        shutil.rmtree(self.config['python_root']);shutil.rmtree(self.config['site_packages'])
        with patch.object(self.runtime.owner,'create',side_effect=AssertionError('Verify published target')):
            result=self.capture(observed)
        self.assertEqual(result['manifest_sha256'],observed['inventory_sha256'])
        self.assertFalse(self.journal.has_pending)

    def test_intent_sql_commit_failure_never_invokes_filesystem_owner(self):
        observed=self.observed();db=self.fixture.db
        db.execute('CREATE TABLE deferred_runtime_parent(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE deferred_runtime_child(id INTEGER REFERENCES deferred_runtime_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        mutate=self.fixture.session.mutate
        def fault(operation,target,body,checkpoint,key,invoke,capture,**kwargs):
            def invoke_bad():
                value=invoke();db.execute('INSERT INTO deferred_runtime_child VALUES(73)');return value
            return mutate(operation,target,body,checkpoint,key,invoke_bad,capture,**kwargs)
        with patch.object(self.fixture.session,'mutate',side_effect=fault),patch.object(self.runtime.owner,'create',side_effect=AssertionError('No copy before intent ACK')):
            with self.assertRaises(Exception):self.capture(observed)
        self.assertFalse((self.runtime.owner.path/observed['inventory_sha256']).exists())
        self.assertFalse(self.journal.has_pending)
        self.assertIn(_intent_key(self.key),operation_records(self.fixture.store.snapshot()['records']))

    def test_changed_key_body_tampered_cache_and_active_work_are_refused_without_effects(self):
        observed=self.observed();result=self.capture(observed)
        before=self.fixture.store.snapshot()
        with self.fixture.access.bind(self.fixture.owner.token):
            with patch.object(self.runtime.owner,'create',side_effect=AssertionError('No changed-key effects')):
                with self.assertRaises(WorkbenchError) as caught:
                    self.runtime.capture(dict(profile='other'),observed['inventory_sha256'],self.cp,self.key,reserve_bytes=0)
                self.assertEqual(caught.exception.code,'conflict')
        self.assertEqual(self.fixture.store.snapshot(),before)
        target=self.runtime.owner.path/observed['inventory_sha256']/'packages/torch/__init__.py'
        target.chmod(0o600);target.write_bytes(b'changed cache');target.chmod(0o400)
        with patch.object(self.runtime.owner,'create',side_effect=AssertionError('Never overwrite corrupt target')):
            with self.assertRaises(WorkbenchError):self.capture(observed)
        self.assertEqual(self.fixture.store.snapshot(),before)
        self.execution._active_attempts.add('a'*32)
        with self.assertRaises(WorkbenchError):self.observed()
        self.execution._active_attempts.clear()

    def test_current_owner_authority_precedes_inspection_and_receipt_replay(self):
        from access import AccessError
        observed=self.observed();self.capture(observed)
        with patch.object(self.runtime.owner,'get',side_effect=AssertionError('No anonymous cache reads')):
            with self.assertRaises(AccessError):self.runtime.capture(self.request,observed['inventory_sha256'],self.cp,self.key,reserve_bytes=0)
        with self.assertRaises(AccessError):self.runtime.inspect(self.request)

    def test_final_sql_failure_retains_canonical_manifest_and_reconciles_without_recapture(self):
        observed=self.observed();f=self.fixture;db=f.db
        db.execute('CREATE TABLE final_runtime_parent(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE final_runtime_child(id INTEGER REFERENCES final_runtime_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        mutate=f.session.mutate
        def fault(operation,target,body,checkpoint,key,invoke,capture,**kwargs):
            if operation!='runtime.capture':return mutate(operation,target,body,checkpoint,key,invoke,capture,**kwargs)
            def invoke_bad():
                result=invoke();db.execute('INSERT INTO final_runtime_child VALUES(84)');return result
            return mutate(operation,target,body,checkpoint,key,invoke_bad,capture,**kwargs)
        with patch.object(f.session,'mutate',side_effect=fault):
            with self.assertRaises(Exception) as caught:self.capture(observed)
        self.assertTrue(caught.exception.receipt['committed'])
        self.assertFalse(f.session.available);self.assertTrue(self.journal.has_pending)
        snapshot=f.store.snapshot();self.journal.validate_selection(snapshot)
        result=operation_records(snapshot['records'])[self.key]['result']
        doc=next(r['document'] for r in snapshot['records'] if r['family']=='runtime_material')
        manifest_edge=next(edge for edge in doc['artifacts'] if edge['role']=='runtime_manifest')
        self.assertEqual(f.artifacts.status(dict(format='project_artifact_v1',**manifest_edge['blob']))['state'],'verified')
        # Explicit current-outcome reconstruction, not an automatic mutation retry.
        with f.access.lock,f.session.lock,db.lock:f.session.reconcile_selection(snapshot)
        with patch.object(self.runtime.owner,'create',side_effect=AssertionError('Never recapture committed bytes')):
            replay=self.capture(observed)
        self.assertEqual(replay,result);self.assertFalse(self.journal.has_pending)
        self.assertTrue(f.session.available)

    def test_receipt_requires_manifest_declarations_and_exact_durable_intent(self):
        result=self.capture(self.observed());records=self.fixture.session.snapshot['records']
        variants=[]
        variants.append([r for r in records if r['family']!='project_operation' or r['document']['operation']!='runtime.capture_intent'])
        variants.append([r for r in records if r['family']!='project_artifact' or r['id']!=result['manifest_sha256']])
        changed=copy.deepcopy(result);changed['total_bytes']+=1
        with self.assertRaises(WorkbenchError):validate_operation_result('runtime.capture',changed,records)
        for candidate in variants:
            with self.assertRaises(WorkbenchError):validate_operation_result('runtime.capture',result,candidate)

    def test_sigkill_after_native_publication_retains_exact_private_intent_without_final_ack(self):
        import json,subprocess,sys
        from project_store import ProjectStore
        report=self.fixture.path/'child-capture-report.json'
        script=r'''
import json,os,signal,sys
from pathlib import Path
from test_project_runtime import RuntimeCaptureTests
case=RuntimeCaptureTests('test_actual_capture_retains_intent_manifest_and_all_declarations_without_running_binaries')
case.setUp();f=case.fixture;observed=case.observed();create=case.runtime.owner.create
def stop(*args,**kwargs):
    value=create(*args,**kwargs)
    facts=dict(path=str(f.path),project=str(f.store.path),host_path=str(f.host.path),host_id=f.host.dataset_id,
        projection_id=f.db.projection_id,schemas=[f.host.schema,f.db.schema],manifest_sha256=value['manifest_sha256'],
        runtime_root=value['root'],checkpoint=f.store.snapshot()['checkpoint'],request_key=case.key)
    with open(sys.argv[1],'w') as handle:
        json.dump(facts,handle);handle.flush();os.fsync(handle.fileno())
    os.kill(os.getpid(),signal.SIGKILL)
case.runtime.owner.create=stop
case.capture(observed)
'''
        completed=subprocess.run([sys.executable,'-c',script,str(report)],cwd=Path(__file__).resolve().parents[1],timeout=20,capture_output=True,text=True)
        self.assertEqual(completed.returncode,-9,completed.stderr)
        facts=json.loads(report.read_text());self.fixture.schemas.extend(facts['schemas'])
        self.addCleanup(shutil.rmtree,facts['path'],True)
        with ProjectStore.open(facts['project']) as store:
            snapshot=store.snapshot();self.assertEqual(snapshot['checkpoint'],facts['checkpoint'])
            receipts=operation_records(snapshot['records'])
            self.assertIn(_intent_key(facts['request_key']),receipts);self.assertNotIn(facts['request_key'],receipts)
            private=ProjectCustody(facts['host_path'],facts['host_id'])
            self.assertEqual([r['projection_id'] for r in private.pending(store)],[facts['projection_id']])
            journal=private.for_projection(store,facts['projection_id']);journal.validate_selection(snapshot)
            self.assertEqual(journal.snapshot()['runtime_effects'][0]['manifest_sha256'],facts['manifest_sha256'])
            self.assertFalse(any(r['family']=='runtime_material' for r in snapshot['records']))
        raw=(Path(facts['runtime_root'])/'manifest.json').read_bytes()
        import hashlib
        self.assertEqual(hashlib.sha256(raw).hexdigest(),facts['manifest_sha256'])
