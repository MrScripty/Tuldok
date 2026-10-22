"""Private original-host physical custody facts, never portable authority."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from project_custody import ProjectCustody, validate
from project_store import ProjectStore
from workbench import WorkbenchError


class ProjectCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='tuldok-local-custody-');self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.control=self.root/'control';self.control.mkdir(mode=0o700)
        self.store=ProjectStore.create(self.root/'project','Neutral custody','new-custody','a'*64)
        self.addCleanup(self.store.close)
        self.host=uuid.uuid4().hex;self.projection=uuid.uuid4().hex
        self.manager=ProjectCustody(self.control,self.host)
        self.journal=self.manager.for_projection(self.store,self.projection)
        self.run=dict(id=uuid.uuid4().hex,admission_id=uuid.uuid4().hex,request_sha256='b'*64,
                      spec={'authored':'bounded specification'},custody_phase='prepared',custody_identity=None)
        self.helper=dict(pid=123456,start_ticks='987654',boot_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')

    def fresh(self):return ProjectCustody(self.control,self.host).for_projection(self.store,self.projection)

    def test_inert_index_then_exact_private_physical_binding_survives_reread(self):
        self.assertFalse((self.control/'.project-custody').exists())
        self.assertEqual(self.manager.pending(self.store),[])
        self.journal.observe_run(self.run)
        file=self.control/'.project-custody'/self.journal.name
        self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
        pending=self.manager.pending(self.store)
        self.assertEqual(pending,[self.journal.binding])
        self.assertEqual(self.fresh().snapshot(),self.journal.snapshot())
        self.assertNotIn('token',file.read_text())
        self.assertEqual(self.fresh().snapshot()['runs'][0]['phase'],'admitted')

    def test_exact_attempted_selection_is_correlated_and_other_checkout_refused(self):
        self.journal.observe_run(self.run);before=self.store.snapshot()
        record=dict(family='project_artifact',id='c'*64,document=dict(format='project_artifact_v1',sha256='c'*64,bytes=3))
        self.journal.expect_publication(before,[record],'local-publication','d'*64)
        selected=self.store.commit([record],before['checkpoint'],'local-publication','d'*64)
        self.fresh().validate_selection(selected)
        other=dict(family='project_artifact',id='e'*64,document=dict(format='project_artifact_v1',sha256='e'*64,bytes=4))
        foreign=self.store.commit([record,other],selected['checkpoint'],'unrelated-checkout','f'*64)
        with self.assertRaises(WorkbenchError):self.fresh().validate_selection(foreign)

    def test_portable_copy_and_other_host_cannot_inherit_original_custody(self):
        self.journal.observe_run(self.run)
        self.assertEqual(ProjectCustody(self.control,uuid.uuid4().hex).pending(self.store),[])
        clone=self.root/'copy';shutil.copytree(self.root/'project',clone)
        with ProjectStore.open(clone) as copied:
            self.assertEqual(copied.snapshot()['project_id'],self.store.snapshot()['project_id'])
            self.assertEqual(self.manager.pending(copied),[])
            with self.assertRaises(WorkbenchError):self.manager.for_projection(copied,self.projection)

    def test_replacing_canonical_identity_at_same_root_retains_original_custody(self):
        self.journal.observe_run(self.run);binding=self.journal.binding
        physical=(self.root/'project').stat().st_ino
        self.store.close()
        with ProjectStore.create(self.root/'replacement','Different valid project','replace-project','c'*64) as other:
            replacement=other.snapshot()['project_id']
        shutil.rmtree(self.root/'project'/'.tuldok')
        shutil.copytree(self.root/'replacement'/'.tuldok',self.root/'project'/'.tuldok')
        with ProjectStore.open(self.root/'project') as selected:
            self.assertEqual(selected.snapshot()['project_id'],replacement)
            self.assertEqual((self.root/'project').stat().st_ino,physical)
            self.assertNotEqual(replacement,binding['project_id'])
            self.assertEqual(self.manager.pending(selected),[binding])
            with self.assertRaises(WorkbenchError):self.journal.validate_selection(selected.snapshot())

    def test_explicit_refresh_preserves_exact_original_pending_marker(self):
        self.journal.observe_run(self.run);stale=self.fresh()
        self.journal.launch_intent(self.run['id'])
        self.assertEqual(stale.snapshot()['runs'][0]['phase'],'admitted')
        observed=stale.refresh()
        self.assertEqual(observed,self.journal.snapshot())
        self.assertEqual(observed['runs'][0]['phase'],'launch_intent')
        self.assertTrue(stale.has_pending)

    def test_launch_identity_and_unknown_provider_remain_explicit_fences(self):
        self.journal.observe_run(self.run);self.journal.launch_intent(self.run['id'])
        self.journal.launched(self.run['id'],self.helper)
        saved=self.fresh().snapshot()['runs'][0]
        self.assertEqual(saved['custody_identity']['helper'],self.helper)
        changed=copy.deepcopy(self.run);changed.update(custody_phase='barrier_ready',custody_identity=saved['custody_identity'])
        self.journal.observe_run(changed)
        changed['custody_phase']='go_intent';self.journal.observe_run(changed)
        self.assertEqual(self.fresh().snapshot()['runs'][0]['phase'],'go_intent')
        producer=uuid.uuid4().hex;admission=uuid.uuid4().hex
        self.journal.register_producer('generation_history',producer,admission,'e'*64)
        self.journal.producer_effect_intent('generation_history',producer)
        self.journal.producer_outcome('generation_history',producer,'unknown',True)
        value=self.fresh().snapshot()['producers'][0]
        self.assertTrue(value['worker_drained']);self.assertEqual(value['provider_outcome'],'unknown')
        self.assertTrue(self.fresh().has_pending)

    def test_only_two_file_writer_kinds_have_exact_retry_and_confirmation(self):
        self.journal.runtime_started('runtime-capture','a'*64,'b'*64)
        self.journal.package_started('package-prepare','c'*64,'d'*64)
        self.assertTrue(self.fresh().has_pending)
        with self.assertRaises(WorkbenchError):self.journal.runtime_started('runtime-capture','e'*64,'b'*64)
        self.journal.runtime_confirmed('runtime-capture')
        self.assertTrue(self.fresh().has_pending)
        self.journal.package_confirmed('package-prepare')
        self.assertEqual(self.manager.pending(self.store),[])

    def test_unsafe_or_unclassified_local_files_fail_closed(self):
        self.journal.observe_run(self.run);file=self.control/'.project-custody'/self.journal.name
        file.chmod(0o644)
        with self.assertRaises(WorkbenchError):self.manager.pending(self.store)
        file.chmod(0o600);raw=file.read_bytes();value=json.loads(raw);value['token']='unclassified'
        file.write_text(json.dumps(value))
        with self.assertRaises(WorkbenchError):self.manager.pending(self.store)
        file.write_bytes(raw);file.unlink();file.symlink_to(self.root/'untrusted')
        with self.assertRaises(WorkbenchError):self.manager.pending(self.store)
        value=self.journal.snapshot();value['runs'][0]['arbitrary_resume']=True
        with self.assertRaises(WorkbenchError):validate(value)

    def test_stale_local_reader_cannot_erase_another_current_admission(self):
        stale=self.fresh();self.journal.observe_run(self.run)
        other=copy.deepcopy(self.run);other['id']=uuid.uuid4().hex
        with self.assertRaises(WorkbenchError) as failure:stale.observe_run(other)
        self.assertEqual(failure.exception.code,'outcome_unknown')
        self.assertEqual([item['run_id'] for item in self.fresh().snapshot()['runs']],[self.run['id']])

    def test_directory_fsync_ack_loss_retains_pending_original_custody(self):
        self.journal.observe_run(self.run);original=os.fsync
        def fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):raise OSError('Injected directory fsync acknowledgement loss')
            return original(descriptor)
        with patch('os.fsync',side_effect=fsync),self.assertRaises(WorkbenchError) as failure:
            self.journal.launch_intent(self.run['id'])
        self.assertEqual(failure.exception.code,'outcome_unknown')
        self.assertEqual(self.fresh().snapshot()['runs'][0]['phase'],'launch_intent')
        self.assertTrue(self.manager.pending(self.store))
        with self.assertRaises(WorkbenchError):self.journal.launched(self.run['id'],self.helper)


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class OriginalHostIdentityFenceTests(unittest.TestCase):
    def test_cold_workspace_detects_different_uuid_at_original_physical_root(self):
        import psycopg
        from psycopg import sql
        from auth_helpers import ExplicitOwnerFixture
        from metadata import connection_info
        import project_workspace
        with tempfile.TemporaryDirectory(prefix='project-custody-identity-') as temporary:
            root=Path(temporary);external=root/'external';external.mkdir()
            workspace=project_workspace.ProjectWorkspace(root/'control',{'fixture':external})
            schemas=[workspace.db.schema]
            try:
                owner=ExplicitOwnerFixture.bootstrap(workspace)
                with ProjectStore.create(external/'project','Original identity','original-project','a'*64) as original:
                    binding=workspace.custody.for_projection(original,uuid.uuid4().hex)
                    binding.observe_run(dict(id=uuid.uuid4().hex,admission_id=uuid.uuid4().hex,
                        request_sha256='b'*64,spec={'authored':'unresolved physical custody index fixture'},
                        custody_phase='prepared',custody_identity=None))
                    original_id=original.snapshot()['project_id'];physical=(external/'project').stat().st_ino
                with ProjectStore.create(external/'replacement','Replacement identity','replacement-project','c'*64) as replacement:
                    replacement_id=replacement.snapshot()['project_id']
                shutil.rmtree(external/'project'/'.tuldok')
                shutil.copytree(external/'replacement'/'.tuldok',external/'project'/'.tuldok')
                with owner.bound(workspace),patch('runs.Runs',side_effect=AssertionError('Cold Open constructed Runs')), \
                     patch('subprocess.Popen',side_effect=AssertionError('Cold Open launched a process')):
                    state=workspace.status()
                    opened=workspace.dispatch('project_files.open',dict(binding=state['binding'],expected_checkpoint=None,
                        request_key='open-replaced-project',root='fixture',directory='project'))
                    self.assertEqual(opened['state'],'recovery_required')
                    self.assertEqual((external/'project').stat().st_ino,physical)
                    self.assertEqual(opened['project']['project_id'],replacement_id)
                    projection=workspace._projection;schemas.append(projection.db.schema)
                    self.assertFalse(projection.session.available);self.assertIsNone(projection.execution._runs)
                    self.assertEqual(projection.pending_original,[binding.binding])
                    self.assertEqual(projection.pending_original[0]['project_id'],original_id)
                    with self.assertRaises(WorkbenchError) as denied:
                        workspace.dispatch('project_files.data_import_text',dict(binding=opened['binding'],
                            expected_checkpoint=opened['project']['checkpoint'],request_key='deny-replaced-project-edit',
                            text='No new authority',name='Blocked edit',groups=['owned'],parents=[],rights='Authored fixture'))
                    self.assertEqual(denied.exception.code,'projection_unavailable')
            finally:
                workspace.close()
                with psycopg.connect(connection_info(),autocommit=True) as connection:
                    for schema in schemas:
                        connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))


CRASH_CHILD = r'''
import json,os,sys
from pathlib import Path
from project_workspace import ProjectWorkspace
import recipe_process
config=json.loads(Path(sys.argv[1]).read_text())
workspace=ProjectWorkspace(config['control'],{'fixture':config['source']})
with workspace.access.bind(Path(config['token_file']).read_text().strip()):
    state=workspace.status()
    workspace.dispatch('project_files.open',dict(binding=state['binding'],expected_checkpoint=None,
        request_key='child-cold-open',root='fixture',directory='alpha'))
    projection=workspace._projection;execution=projection.execution
    projection.source_adapter.register(dict(root='fixture',manifest_path='project.json'),
        projection.session.snapshot['checkpoint'],'child-current-source')
    preflight=execution.preflight_external(config['graph_id'],config['graph_revision'])
    body=dict(graph_id=config['graph_id'],graph_revision=config['graph_revision'],expected_digest=preflight['material_sha256'])
    def crash(identity,phase):
        print(json.dumps(dict(run_id=identity,projection_id=projection.db.projection_id,phase=phase,body=body)),flush=True)
        os._exit(74)
    if config['phase']=='started':
        original=recipe_process.Handle.poll
        def poll(handle):
            events=original(handle)
            if any(item['type']=='started' for item in events):crash(handle.spec['attempt_id'],'started')
            return events
        recipe_process.Handle.poll=poll
    else:
        original=projection.db._project_outcome
        def outcome(result):
            original(result)
            if result=='committed':
                for row in projection.db.execute('SELECT document FROM workspace_runs'):
                    run=json.loads(row['document'])
                    phase='admitted' if run['state']=='queued' else run['custody_phase']
                    if phase==config['phase']:crash(run['id'],phase)
        projection.db._project_outcome=outcome
    execution.submit_external(body,projection.session.snapshot['checkpoint'],'original-crash-submit')
    import time
    time.sleep(40)
    raise SystemExit('The requested real crash cut point was not reached')
'''


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class OriginalHostCrashTests(unittest.TestCase):
    def setUp(self):
        import test_project_files_m2_http as m2
        m2.ProjectFilesM2HTTP.setUp(self)

    def receipt(self):
        import test_project_files_m2_http as m2
        m2.ProjectFilesM2HTTP.receipt(self)

    def cleanup_owned(self):
        import test_project_files_http as m1
        m1.ProjectFilesHTTP.cleanup_owned(self)

    def select_host(self,*args,**kwargs):
        import test_project_files_http as m1
        return m1.ProjectFilesHTTP.select_host(self,*args,**kwargs)

    def request(self,*args,**kwargs):
        import test_project_files_m2_http as m2
        return m2.ProjectFilesM2HTTP.request(self,*args,**kwargs)

    def state(self):
        import test_project_files_http as m1
        return m1.ProjectFilesHTTP.state(self)

    def envelope(self,*args,**kwargs):
        import test_project_files_http as m1
        return m1.ProjectFilesHTTP.envelope(self,*args,**kwargs)

    def action(self,*args,**kwargs):
        import test_project_files_http as m1
        return m1.ProjectFilesHTTP.action(self,*args,**kwargs)

    def create(self):return self.action('new',root='fixture',directory='alpha',name='Original host neutral custody')

    def arguments(self,*args,**kwargs):
        import test_project_files_m2_http as m2
        return m2.ProjectFilesM2HTTP.arguments(self,*args,**kwargs)

    def transport(self,*args,**kwargs):
        import test_project_files_m2_http as m2
        return m2.ProjectFilesM2HTTP.transport(self,*args,**kwargs)

    def call(self,*args,**kwargs):
        import test_project_files_m2_http as m2
        return m2.ProjectFilesM2HTTP.call(self,*args,**kwargs)

    def crash_and_reconcile(self,phase):
        from test_project_files_material_http import neutral_source
        import recipe_process
        import project_workspace
        manifest,manifest_raw,definition_raw,source,exact_input=neutral_source(self.external)
        self.create()
        self.call('source_register',root='fixture',manifest_path='project.json')
        graph=self.call('graph_create_external',name='Original-host crash fixture',project_id=manifest['id'],
            recipe_id='neutral',expected_sha256=hashlib.sha256(definition_raw).hexdigest(),
            inputs={'sample':{'reference_id':'sample','expected_sha256':hashlib.sha256(exact_input).hexdigest()}},
            parameters={'mode':'sleep'})
        self.action('save');self.action('close')
        token_file=self.path/'child-owner.token';token_file.write_text(self.owner.token);token_file.chmod(0o600)
        config=self.path/'child-config.json'
        config.write_text(json.dumps(dict(control=str(self.workspace.path),source=str(self.external),
            token_file=str(token_file),graph_id=graph['id'],graph_revision=graph['revision'],phase=phase)))
        config.chmod(0o600)
        child=subprocess.run([sys.executable,'-c',CRASH_CHILD,str(config)],capture_output=True,text=True,timeout=50)
        self.assertEqual(child.returncode,74,child.stderr+child.stdout)
        observed=json.loads(child.stdout.strip().splitlines()[-1]);self.assertEqual(observed['phase'],phase)
        # A restarted original host reads the private binding. Open constructs
        # only inert owners and leaves all current execution unavailable.
        with patch('runs.Runs',side_effect=AssertionError('Open constructed a Run owner')), \
             patch('subprocess.Popen',side_effect=AssertionError('Open launched a process')):
            opened=self.action('open',root='fixture',directory='alpha')
        self.assertEqual(opened['state'],'recovery_required')
        self.assertIsNone(self.workspace._projection.execution._runs)
        pending=self.workspace.custody.pending(self.workspace._store)
        self.assertEqual(len(pending),1);self.assertEqual(pending[0]['projection_id'],observed['projection_id'])
        state=self.state()
        with patch.object(project_workspace,'M3_ENABLED',True), \
             patch('subprocess.Popen',side_effect=AssertionError('Reconciliation spawned a process')), \
             patch('recipe_process.Handle.go',side_effect=AssertionError('Reconciliation replayed GO')), \
             patch('runs.Runs._start',side_effect=AssertionError('Reconciliation started a queue')):
            arguments=dict(binding=state['binding'],expected_checkpoint=state['project']['checkpoint'])
            if phase=='admitted':
                # Explicit owner-only adapter uses AgentClient's actual HTTP,
                # negotiated pin and request/response identity correlation.
                from agent_api import AgentClient,ProjectFilesOwnerClient
                client=ProjectFilesOwnerClient(self.origin,self.owner.token,self.workspace.db.dataset_id,timeout=60)
                self.assertIsInstance(client,AgentClient)
                self.assertEqual(client.selected_contracts()['project_files.execution_reconcile_current'],1)
                result=client.call('project_files.execution_reconcile_current',arguments)
                status,response=result['status'],result['result']
            else:
                status,response=self.transport('execution_reconcile_current',arguments)
            self.assertEqual(status,200,response)
            self.assertEqual(response['binding'],state['binding'])
            value=response['value'];self.assertTrue(value['available'])
            self.assertEqual(value['run_ids'],[observed['run_id']])
            current=self.workspace._projection
            self.assertEqual(current.db.projection_id,observed['projection_id'])
            self.assertEqual(self.workspace.custody.pending(self.workspace._store),[])
            document=next(item['document'] for item in current.session.snapshot['records']
                if item['family']=='run_history' and item['document']['run']['id']==observed['run_id'])
            self.assertIn(document['run']['state'],('cancelled','interrupted'))
            if phase!='admitted':
                edge=next(item for item in document['payloads'] if item['name']=='custody-receipt.json')
                receipt=recipe_process.validate_receipt(current.artifacts.read_blob(edge['blob']),document['run']['custody_identity'])
                self.assertTrue(receipt['drained'])
                self.assertEqual(receipt['go_received'],phase=='started')
            before=current.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0]
            with self.owner.bound(self.workspace):
                replay=current.execution.submit_external(observed['body'],current.session.snapshot['checkpoint'],'original-crash-submit')
            self.assertEqual(replay['run_id'],observed['run_id'])
            self.assertEqual(current.db.execute('SELECT count(*) FROM workspace_runs').fetchone()[0],before)
        self.action('save');self.action('close')

    def test_original_host_crash_after_admission_ack_before_queue_wake(self):self.crash_and_reconcile('admitted')
    def test_original_host_crash_after_go_intent_before_go(self):self.crash_and_reconcile('go_intent')
    def test_original_host_crash_after_actual_recipe_started(self):self.crash_and_reconcile('started')


if __name__=='__main__':unittest.main()
