"""M5 explicit cessation, readonly capture and atomic extraction on disposable PG."""
import copy
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
from app import Dataset, make_handler
from backup_metadata import tree_manifest
from project_store import ProjectStore, ProjectStoreError
from project_transfer import (ProjectTransfer, StoppedSourceLease, preview_source,
    stop_source, decode_records, _assert_unchanged)
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ProjectTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='tuldok-transfer-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.project_root=self.root/'registered';self.project_root.mkdir()
        self.dataset=Dataset(self.root/'legacy',project_roots={'fixture':self.project_root})
        self.addCleanup(self.cleanup)
        exchange=self.dataset.access.exchange(self.dataset.access._local_owner_token())
        self.token,self.actor=exchange['token'],exchange['identity']['actor_id']
        self.enterContext(self.dataset.access.bind(self.token))
        self.manifest=dict(schema_version=1,id=uuid.uuid4().hex,name='Exact chosen source λ',data=[],recipes=[],evidence=[],requirements=[])
        self.raw_manifest=(json.dumps(self.manifest,ensure_ascii=False,indent=3)+'\n\n').encode()
        (self.project_root/'source.json').write_bytes(self.raw_manifest)
        self.dataset.projects.register_snapshot(dict(root='fixture',manifest_path='source.json'))
        self.selection=dict(project_snapshot=dict(id=self.manifest['id'],manifest_sha256=hashlib.sha256(self.raw_manifest).hexdigest()),roots={},decisions=[])
        self.parent_fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY);self.addCleanup(os.close,self.parent_fd)
        self.leases=[]
    def cleanup(self):
        for source in self.leases:source.close()
        self.dataset.close()
        with psycopg.connect(self.dataset.db.dsn,autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.dataset.db.schema)))
    def text(self,value='Exact original e\u0301\r\nλ'):
        return self.dataset.workbench.import_asset(dict(kind='text',name='Authored unique source',text=value,groups=['shared-fixture'],parents=[],rights='Fixture permission'))
    def stop(self):
        source=self.dataset.stop_for_project_extraction(self.parent_fd,'verified-backup');self.leases.append(source);return source
    def test_preview_readonly_no_constructor_no_stop_and_explicit_unassigned(self):
        selected=self.text();other=self.text('Unassigned unique source')
        self.selection['roots']['records']=[selected['id']]
        before=tree_manifest(self.dataset.path)
        with preview_source(self.dataset) as source:
            with patch('metadata.Metadata.__init__',side_effect=AssertionError('preview initialized Metadata')), \
                 patch('synthetic.Jobs.__init__',side_effect=AssertionError('preview constructed Jobs')), \
                 patch('runs.Runs.__init__',side_effect=AssertionError('preview constructed Runs')):
                report=ProjectTransfer(source).preview(self.selection)
            self.assertFalse(report['can_extract'])
            self.assertEqual([b['code'] for b in report['blockers']],['cessation_proof_unavailable'])
            self.assertIn(dict(family='workbench_record',id=other['id'],revision=1),report['unassigned'])
            self.assertEqual(source.db.execute("SELECT current_setting('transaction_read_only')").fetchone()[0],'on')
            with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):source.db.execute('DELETE FROM workbench_records')
        self.assertEqual(before,tree_manifest(self.dataset.path))
        self.assertFalse(self.dataset._extraction_stopping)
    def test_actual_stop_backup_is_private_verified_and_source_unchanged(self):
        self.text();source=self.stop()
        self.assertIs(type(source),StoppedSourceLease)
        self.assertTrue(self.dataset._closed)
        self.assertEqual(tree_manifest(self.dataset.path),source.backup_receipt['files'])
        self.assertEqual(tree_manifest(self.root/'verified-backup'/'catalog'),source.backup_receipt['files'])
        self.assertTrue((self.root/'verified-backup'/'metadata.json').exists())
        _assert_unchanged(source)
        with self.assertRaises(WorkbenchError):
            with self.dataset._project_request():pass
        with self.assertRaises(WorkbenchError):self.dataset.stop_for_project_extraction(self.parent_fd,'retry-backup')
    def test_json_bool_and_fake_controller_guards_never_stop(self):
        for guard in (True,{},SimpleNamespace(require=lambda _:None)):
            with self.assertRaises(WorkbenchError) as caught:
                stop_source(self.dataset,backup_parent_fd=self.parent_fd,backup_directory='forged',controller_guard=guard)
            self.assertEqual(caught.exception.code,'forbidden')
        with self.assertRaises(WorkbenchError):StoppedSourceLease(None,None,None,None)
        with preview_source(self.dataset) as forged:
            forged.backup_receipt={}
            forged.__class__=StoppedSourceLease
            with self.assertRaises(WorkbenchError):forged.require()
            with self.assertRaises(WorkbenchError):ProjectTransfer(forged).extract(self.selection,'0'*64,self.parent_fd,'forged','No forged authority','forged-key')
        self.assertFalse(self.dataset._closed)
        self.assertFalse((self.root/'forged').exists())
    def test_unknown_custody_and_peer_ownership_cannot_mint_lease(self):
        self.dataset.runs._blocked=True
        with self.assertRaises(WorkbenchError) as caught:self.stop()
        self.assertEqual(caught.exception.code,'unknown')
        self.assertFalse((self.root/'verified-backup').exists())
        self.assertFalse(self.dataset._closed)
        self.dataset.runs._blocked=False
    def test_peer_lock_handoff_after_close_refuses_lease(self):
        from metadata import _key
        peer=psycopg.connect(self.dataset.db.dsn,autocommit=True);self.addCleanup(peer.close)
        original=self.dataset.close
        def close_and_claim():
            original()
            self.assertTrue(peer.execute('SELECT pg_try_advisory_lock(%s)',(_key(self.dataset.db.schema+':worker:generation_jobs'),)).fetchone()[0])
        with patch.object(self.dataset,'close',side_effect=close_and_claim),self.assertRaises(WorkbenchError) as caught:self.stop()
        self.assertEqual(caught.exception.code,'busy')
        self.assertFalse((self.root/'verified-backup').exists())
    def test_stopped_source_sql_and_external_byte_changes_are_detected(self):
        record=self.text();source=self.stop()
        source.read_root('fixture','source.json')
        with psycopg.connect(source.db.dsn,autocommit=True) as connection:
            connection.execute(sql.SQL('UPDATE {}.workbench_records SET name=%s WHERE id=%s').format(sql.Identifier(source.db.schema)),('bypass attempt',record['id']))
        with self.assertRaises(WorkbenchError) as caught:_assert_unchanged(source)
        self.assertEqual(caught.exception.code,'stale_source')
    def test_registered_source_change_blocks_before_publication(self):
        self.text();source=self.stop();source.read_root('fixture','source.json')
        (self.project_root/'source.json').write_bytes(self.raw_manifest+b' ')
        with self.assertRaises(WorkbenchError) as caught:_assert_unchanged(source)
        self.assertEqual(caught.exception.code,'stale_source')
        self.assertFalse((self.root/'extracted').exists())
    def test_handler_inflight_is_drained_then_new_requests_are_fenced(self):
        entered=threading.Event();release=threading.Event();errors=[]
        handler=make_handler(self.dataset)
        original=handler._handle_GET
        # The actual HTTP gate in _observe_request surrounds this handler body.
        def blocked_get(request):
            entered.set();release.wait(5);return original(request)
        handler._handle_GET=blocked_get
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request():
            try:
                connection=http.client.HTTPConnection(*server.server_address,timeout=10)
                connection.request('GET','/');response=connection.getresponse();response.read();connection.close()
            except BaseException as error:errors.append(error)
        client=threading.Thread(target=request);client.start();self.assertTrue(entered.wait(5))
        def stop():
            try:
                with self.dataset.access.bind(self.token):self.leases.append(self.dataset.stop_for_project_extraction(self.parent_fd,'verified-backup'))
            except BaseException as error:errors.append(error)
        stopper=threading.Thread(target=stop);stopper.start();time.sleep(.1)
        # If do_GET replacement was outside the gate this proves nothing; inspect
        # the real gate state before releasing the in-flight HTTP operation.
        self.assertTrue(self.dataset._extraction_stopping)
        self.assertTrue(stopper.is_alive())
        release.set();client.join(10);stopper.join(20)
        self.assertFalse(stopper.is_alive());self.assertEqual(errors,[])
        connection=http.client.HTTPConnection(*server.server_address,timeout=10)
        connection.request('GET','/');response=connection.getresponse();response.read();connection.close()
        self.assertEqual(response.status,409)
    def test_selected_text_working_file_material_extract_replay_and_cold_rebuild(self):
        row=self.text();unrelated=self.text('Keep unrelated global data unassigned')
        script=b'raise AssertionError("extraction must never run me")\n'
        (self.project_root/'scripts').mkdir();(self.project_root/'scripts'/'neutral.py').write_bytes(script)
        self.selection['roots'].update(records=[row['id']],working_files=[dict(kind='script',path='scripts/neutral.py')])
        source=self.stop();baseline=tree_manifest(self.dataset.path);transfer=ProjectTransfer(source)
        report=transfer.preview(self.selection)
        self.assertTrue(report['can_extract'],report['blockers'])
        self.assertTrue(any(item['id']==unrelated['id'] for item in report['unassigned']))
        receipt=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'extracted','New portable project','extract-once')
        self.assertTrue(receipt['committed']);self.assertFalse(receipt['selected'])
        self.assertEqual(receipt['verification']['active_data_records'],1)
        with ProjectStore.open(self.root/'extracted') as store:
            snapshot=store.snapshot();decode_records(snapshot['records'])
            self.assertNotEqual(snapshot['project_id'],source.db.dataset_id)
            active=[r for r in snapshot['records'] if r['family']=='workbench_record' and r['document']['current']['id']!=row['id']]
            self.assertEqual(len(active),1)
            self.assertEqual(active[0]['document']['source']['original_text'],'Exact original e\u0301\r\nλ')
            self.assertEqual((store.path/'scripts'/'neutral.py').read_bytes(),script)
            self.assertFalse(any(r['family'].startswith('access_') for r in snapshot['records']))
            # Actual ordinary Open under a different installation, with fresh
            # physical SQL and current host authority, remains inert.
            from access import Access
            from metadata import Metadata
            from project_projection import ProjectProjection
            host=Metadata(self.root/'new-installation')
            projected=Metadata(self.root/'cold-projection',dataset_id=snapshot['project_id'],projection_id=uuid.uuid4().hex)
            projection=None
            try:
                authority=Access(host,host.path);token=authority.exchange(authority._local_owner_token())['token']
                with authority.bind(token),patch('runs.Runs.__init__',side_effect=AssertionError('Open started Runs')),patch('synthetic.Jobs.__init__',side_effect=AssertionError('Open started Jobs')):
                    projection=ProjectProjection(store,projected,authority,{})
                    self.assertEqual(projection.data.get(active[0]['id']),active[0]['document']['current'])
                    for table in ('access_actors','access_credentials','access_admissions','access_execution_grants','workspace_runs'):
                        self.assertEqual(projected.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
                    self.assertEqual(store.snapshot(),snapshot)
            finally:
                if projection is not None:projection.close()
                else:projected.close()
                host.close()
                with psycopg.connect(source.db.dsn,autocommit=True) as cleanup:
                    for database in (projected,host):cleanup.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(database.schema)))
        replay=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'extracted','New portable project','extract-once')
        self.assertEqual({k:v for k,v in replay.items() if k!='replayed'},{k:v for k,v in receipt.items() if k!='replayed'})
        self.assertTrue(replay['replayed'])
        self.assertEqual(baseline,tree_manifest(self.dataset.path));_assert_unchanged(source)
        with self.assertRaises(ProjectStoreError):transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'extracted','Changed name','extract-once')

    def test_response_preference_model_study_shared_closure_is_exact(self):
        from test_project_history import policy
        parent=self.text();unrelated=self.text('Unassigned other project source')
        answers=[]
        for completion in ('Unique first answer\r\n','Unique second answer λ'):
            answers.append(self.dataset.workbench.save_response(dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,
                parent_revision=1,source_revision=1,completion=completion,review='draft'))['response'])
        judgment=self.dataset.workbench.preferences.save(dict(id=uuid.uuid4().hex,prompt_id=parent['id'],parent_revision=1,source_revision=1,
            left_id=answers[0]['id'],left_revision=1,right_id=answers[1]['id'],right_revision=1,revision=0,
            outcome='left',rationale='Exact authored distinction',review='human_reviewed'))['judgment']
        model=self.dataset.models.create(dict(name='Original model metadata',task=dict(kind='task',catalog_id=self.dataset.db.dataset_id,
            id='neutral',revision=1,sha256='b'*64),kind='template',specification={'unique':'λ'},source_selector=None,preprocessing_policy={},output_policy={}))
        changed=copy.deepcopy(model);changed['name']='Renamed observed metadata'
        model=self.dataset.models.save(model['id'],dict(revision=1,document=changed))
        study=self.dataset.studies.create(dict(name='Chosen actual scientific intent',limits=dict(attempt_slots=2,admitted_wall_seconds=100,
            retained_bytes=10000,peak_staging_bytes=10000),policy=policy()))
        self.selection['roots'].update(preferences=[judgment['id']],model_definitions=[model['id']],studies=[study['id']])
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        self.assertTrue(report['can_extract'],report['blockers'])
        required={(v['family'],v['id']) for v in report['required']}
        self.assertIn(('workbench_record',parent['id']),required)
        self.assertIn(('workbench_response',answers[0]['id']),required)
        self.assertTrue(any(v['id']==unrelated['id'] for v in report['unassigned']))
        self.assertTrue(any(v['code']=='observed_history_incomplete' for v in report['warnings']))
        baseline=tree_manifest(self.dataset.path)
        receipt=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'closure','Closure destination','closure-key')
        with ProjectStore.open(self.root/'closure') as store:
            records=store.snapshot()['records'];fork=next(r['document'] for r in records if r['family']=='project_fork')
            self.assertEqual(next(r['document']['current'] for r in records if r['family']=='workbench_preference' and r['id']==judgment['id']),judgment)
            fresh=next(r['document']['current'] for r in records if r['family']=='workbench_preference' and r['id']!=judgment['id'])
            self.assertEqual((fresh['review'],fresh['revision']),('draft',1))
            self.assertIn(dict(family='workbench_response',id=answers[0]['id']),fork['archived'])
            kept=next(r['document']['current'] for r in records if r['family']=='model_definition' and r['id'].startswith(source.db.dataset_id+'.'))
            self.assertEqual(kept,model)
            saved_study=next(r['document']['study'] for r in records if r['family']=='study_history')
            self.assertEqual(saved_study,study)
            self.assertFalse(any(r['family'].startswith('access_') for r in records))
            bad=copy.deepcopy(records);next(r['document'] for r in bad if r['family']=='project_extraction')['input_sha256']='0'*64
            with self.assertRaises(WorkbenchError):decode_records(bad)
        self.assertEqual(receipt['verification']['active_data_records'],1)
        self.assertEqual(baseline,tree_manifest(self.dataset.path))

    def test_required_exclusion_and_absent_history_block_publication(self):
        parent=self.text();answer=self.dataset.workbench.save_response(dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,
            parent_revision=1,source_revision=1,completion='Unique answer',review='draft'))['response']
        search=self.dataset.searches.create(dict(name='Original criteria',criteria={k:'' for k in ('q','kind','review','sort','task','label','group','rights')}))
        self.dataset.searches.mutate(search['id'],'rename',dict(revision=1,name='Saved later name'))
        self.selection['roots'].update(responses=[answer['id']],searches=[search['id']])
        self.selection['decisions']=[dict(family='workbench_record',id=parent['id'],include=False,reason='Deliberate ownership exclusion')]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        self.assertFalse(report['can_extract'])
        self.assertIn('required_dependency_excluded',{v['code'] for v in report['blockers']})
        self.assertIn('intent_history_unavailable',{v['code'] for v in report['blockers']})
        with self.assertRaises(WorkbenchError) as caught:transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'blocked','Blocked','block-key')
        self.assertEqual(caught.exception.code,'extraction_blocked')
        self.assertFalse((self.root/'blocked').exists())
        self.assertEqual(list(self.root.glob('.tuldok-extraction-*')),[])

    def test_failed_final_rename_preserves_stage_and_lost_rename_ack_reconciles(self):
        from project_transfer import _rename_noreplace as rename
        self.selection['roots']['records']=[self.text()['id']]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        def fail_before(parent,old,new):
            if new=='failed':raise OSError('Injected final publication failure')
            return rename(parent,old,new)
        with patch('project_transfer._rename_noreplace',side_effect=fail_before),self.assertRaises(OSError) as caught:
            transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'failed','Retained stage','before-key')
        stage=self.root/caught.exception.staging_directory
        self.assertTrue(stage.is_dir());self.assertFalse((self.root/'failed').exists())
        with ProjectStore.open(stage) as store:self.assertTrue(store.reconcile('before-key',next(r['document']['input_sha256'] for r in store.snapshot()['records'] if r['family']=='project_extraction')))
        def lose_ack(parent,old,new):
            rename(parent,old,new)
            if new=='published':raise OSError('Injected lost rename acknowledgement')
        with patch('project_transfer._rename_noreplace',side_effect=lose_ack),self.assertRaises(WorkbenchError) as lost:
            transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'published','Known committed identity','after-key')
        self.assertEqual(lost.exception.code,'unknown');self.assertTrue(lost.exception.receipt['committed'])
        self.assertFalse(lost.exception.receipt['selected']);self.assertTrue((self.root/'published').exists())
        receipt=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'published','Known committed identity','after-key')
        self.assertEqual(receipt['project_id'],lost.exception.receipt['project_id']);self.assertTrue(receipt['replayed'])
        _assert_unchanged(source)

    def test_current_inspect_agent_can_preview_but_cannot_stop_or_reuse_revoked_view(self):
        from access import AccessError
        agent=self.dataset.access.issue(dict(label='Finite extraction inspector',scopes=['inspect']))
        with self.dataset.access.bind(agent['token']):
            source=preview_source(self.dataset);self.addCleanup(source.close)
            self.assertFalse(ProjectTransfer(source).preview(self.selection)['can_extract'])
            with self.assertRaises(AccessError):self.dataset.stop_for_project_extraction(self.parent_fd,'agent-backup')
            with self.dataset.access.bind(self.token):self.dataset.access.revoke(agent['identity']['credential_id'])
            with self.assertRaises(AccessError):source.read_catalog('.tuldok.json')
        self.assertFalse(self.dataset._extraction_stopping)
        self.assertFalse((self.root/'agent-backup').exists())

    def test_standalone_owned_image_operation_is_cancelled_and_drained(self):
        from image_generation import Operation
        operation=Operation();identity=uuid.uuid4().hex
        with self.dataset.image_requests.lock:self.dataset.image_requests.active[identity]=operation
        def worker():
            operation.cancelled.wait(5)
            with self.dataset.image_requests.lock:self.dataset.image_requests.active.pop(identity,None)
            operation.done.set()
        thread=threading.Thread(target=worker);thread.start();self.addCleanup(thread.join,5)
        source=self.stop()
        self.assertTrue(operation.cancelled.is_set());self.assertTrue(operation.done.is_set())
        self.assertFalse(self.dataset.image_requests.active);source.require()

    def test_parent_revision_two_response_fork_keeps_original_binding_and_fresh_prompt(self):
        parent=self.text()
        parent=self.dataset.workbench.save(parent['id'],dict(revision=1,source_revision=1,task='text_classification',
            annotation={'label':'authored'},groups=parent['groups'],review='draft'))
        answer=self.dataset.workbench.save_response(dict(id=uuid.uuid4().hex,prompt_id=parent['id'],revision=0,parent_revision=2,
            source_revision=1,completion='Exact postannotation answer',review='draft'))['response']
        self.selection['roots']['responses']=[answer['id']]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        self.assertTrue(report['can_extract'],report['blockers'])
        transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'revision-two','Fresh prompt','revision-two-key')
        with ProjectStore.open(self.root/'revision-two') as store:
            records=store.snapshot()['records']
            original=next(r for r in records if r['family']=='workbench_response' and r['id']==answer['id'])
            fresh=next(r for r in records if r['family']=='workbench_response' and r['id']!=answer['id'])
            self.assertEqual(original['document']['history'][0]['parent']['revision'],2)
            self.assertEqual(fresh['document']['history'][0]['parent']['revision'],1)
            self.assertEqual(original['document']['current'],answer)

    def test_native_original_bytea_extracts_without_reexport_or_regeneration(self):
        import meshes
        from test_meshes import fixture
        prepared=meshes.prepare(*fixture())
        row=self.dataset.workbench.meshes.admit(prepared,dict(groups=['native-fixture'],rights='Unique native authored source'))
        original=bytes(self.dataset.db.execute('SELECT bundle FROM workbench_mesh_assets WHERE id=%s',(row['id'],)).fetchone()[0])
        self.selection['roots']['records']=[row['id']]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        self.assertTrue(report['can_extract'],report['blockers'])
        # Existing pure owner validation may reparse the bundle; custody must
        # publish the exact original bytes rather than a newly encoded archive.
        receipt=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'native','Native custody','native-key')
        from project_artifacts import ProjectArtifacts
        with ProjectStore.open(self.root/'native') as store,ProjectArtifacts(store) as artifacts:
            records=store.snapshot()['records'];source_record=next(r for r in records if r['family']=='workbench_record' and r['id']==row['id'])
            edge=source_record['document']['source']['asset']['artifact']
            self.assertEqual(artifacts.read_blob(dict(sha256=edge['sha256'],bytes=len(original))),original)
            self.assertEqual(source_record['document']['current'],row)
        self.assertEqual(receipt['verification']['active_data_records'],1)
        self.assertEqual(bytes(source.db.execute('SELECT bundle FROM workbench_mesh_assets WHERE id=%s',(row['id'],)).fetchone()[0]),original)

    def test_missing_unique_run_input_remains_explicitly_blocked(self):
        from test_project_history import legacy_run
        run=legacy_run(self.dataset.db.dataset_id)
        with self.dataset.db.lock,self.dataset.db.transaction():
            self.dataset.db.execute('INSERT INTO workspace_runs VALUES(%s,%s,%s,%s)',(run['id'],run['request_key'],run['request_sha256'],json.dumps(run)))
        self.selection['roots']['runs']=[run['id']]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        self.assertFalse(report['can_extract'])
        self.assertIn('missing_unique_payload',{v['code'] for v in report['blockers']})
        self.assertTrue(any(v['sha256']==run['release_sha256'] and v['preservation']=='unique' and v['state']=='missing' for v in report['artifacts']))
        with self.assertRaises(WorkbenchError):transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'missing','Missing unique source','missing-key')
        self.assertFalse((self.root/'missing').exists())

    def test_selected_working_symlink_and_hardlink_refuse_without_following(self):
        target=self.root/'outside.py';target.write_bytes(b'outside secret fixture never captured')
        (self.project_root/'scripts').mkdir();(self.project_root/'scripts'/'unsafe.py').symlink_to(target)
        self.selection['roots']['working_files']=[dict(kind='script',path='scripts/unsafe.py')]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        self.assertFalse(report['can_extract']);self.assertEqual(report['working_files'],[])
        self.assertFalse(any(v['sha256']==hashlib.sha256(target.read_bytes()).hexdigest() for v in report['artifacts']))
        (self.project_root/'scripts'/'unsafe.py').unlink();os.link(target,self.project_root/'scripts'/'unsafe.py')
        report=transfer.preview(self.selection)
        self.assertFalse(report['can_extract']);self.assertEqual(report['working_files'],[])

    def test_full_two_study_scientific_custody_extracts_and_cold_rebuilds(self):
        """Reuse strict historical source authorship, without an execution claim.

        The readonly fixture's capture boundary delegates to an actual opened
        Dataset's stop guard. Neither the proxy nor a fabricated JSON proof is
        ever supplied to ProjectTransfer as its source capability.
        """
        import test_project_extraction as legacy_fixtures
        from project_extraction import capture_legacy
        holder={};expected={}
        class SourceResult:
            def __getattr__(_,name):return getattr(holder['source'],name)
        def files():
            return dict(catalog=tree_manifest(self.dataset.path),registered=tree_manifest(self.project_root))
        def capture(_,roots):
            self.selection['roots']=roots
            before_stop=files()
            source=self.stop();holder['source']=source
            holder['baseline']=files()
            holder['stop_changes']=[group+'/'+path for group in before_stop for path in set(before_stop[group])|set(holder['baseline'][group]) if before_stop[group].get(path)!=holder['baseline'][group].get(path)]
            transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
            self.assertTrue(report['can_extract'],report['blockers'])
            required={(v['family'],v['id']) for v in report['required']}
            self.assertEqual(len([v for v in report['included'] if v['family']=='study_history']),2)
            self.assertEqual(len([v for v in report['included'] if v['family']=='trial_history']),2)
            self.assertEqual(len([v for v in report['included'] if v['family']=='candidate_history']),1)
            expected['captured']=capture_legacy(source,self.selection)
            receipt=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'science','Independent scientific custody','science-key')
            self.assertEqual(receipt['verification']['active_data_records'],1)
            from project_artifacts import ProjectArtifacts
            from project_history import decode_records as history
            from project_material import ProjectMaterial
            with ProjectStore.open(self.root/'science') as store,ProjectArtifacts(store) as artifacts:
                snapshot=store.snapshot();records=snapshot['records']
                view=SimpleNamespace(snapshot=snapshot,artifacts=artifacts,check=lambda:None)
                facts=history(records,materials=ProjectMaterial(view),artifacts=artifacts)
                self.assertEqual(len(facts.studies),2);self.assertEqual(len(facts.trials),2)
                self.assertEqual(len(facts.candidates),1);self.assertEqual(len(facts.reservations),1);self.assertEqual(len(facts.runs),1)
                for original in expected['captured']['records']:
                    self.assertIn(original,records)
                    if original['family']=='project_artifact' and source.artifacts.status(original['document'])['state']=='verified':
                        blob=dict(sha256=original['id'],bytes=original['document']['bytes'])
                        self.assertEqual(artifacts.read_blob(blob),source.artifacts.read_blob(blob))
                self.assertFalse(any(row['family'].startswith('access_') for row in records))
            _assert_unchanged(source)
            self.assertEqual(files(),holder['baseline'])
            return expected['captured']
        def fixture_assert_equal(actual,expected,*args):
            # The reused capture-only fixture compares all files around capture.
            # This adapter explicitly stops first; its source preservation
            # baseline therefore belongs after stop/backup, as the API promises.
            if type(actual) is dict and set(actual)=={'catalog','registered'} and 'baseline' in holder:
                return self.assertEqual(actual,holder['baseline'],*args)
            return self.assertEqual(actual,expected,*args)
        fixture=SimpleNamespace(dataset=self.dataset,db=self.dataset.db,access=self.dataset.access,
            actor=self.actor,workbench=self.dataset.workbench,text=self.text,files=files,
            view=lambda:SourceResult(),capture=capture,assertEqual=fixture_assert_equal,assertTrue=self.assertTrue)
        legacy_fixtures.LegacyCapture.test_two_study_lineage_reservation_candidate_and_run_science_are_captured(fixture)
        self.assertEqual(holder['stop_changes'],['catalog/workspace-runs/.coordinator-v1.json'])

    def test_noncooperating_owned_close_stays_bounded_fenced_and_has_no_lease(self):
        entered=threading.Event();release=threading.Event();original=self.dataset.generation_jobs.close
        def blocked_close():
            entered.set();release.wait(5);original()
        actual=self.dataset.close_for_project_extraction
        def bounded(**kwargs):return actual(deadline=time.monotonic()+.1)
        try:
            with patch.object(self.dataset.generation_jobs,'close',side_effect=blocked_close),patch.object(self.dataset,'close_for_project_extraction',side_effect=bounded):
                started=time.monotonic()
                with self.assertRaises(WorkbenchError) as caught:self.stop()
                self.assertEqual(caught.exception.code,'source_busy')
                self.assertLess(time.monotonic()-started,2)
                self.assertTrue(entered.is_set());self.assertTrue(self.dataset._extraction_closer.is_alive())
                self.assertTrue(self.dataset._extraction_stopping);self.assertEqual(self.leases,[])
                self.assertFalse((self.root/'verified-backup').exists())
                with self.assertRaises(WorkbenchError):
                    with self.dataset._project_request():pass
                with self.assertRaises(WorkbenchError):self.dataset.stop_for_project_extraction(self.parent_fd,'retry')
                release.set();self.dataset._extraction_closer.join(5)
                self.assertFalse(self.dataset._extraction_closer.is_alive());self.assertTrue(self.dataset._closed)
        finally:
            release.set()
            if self.dataset._extraction_closer is not None:self.dataset._extraction_closer.join(5)

    def test_retry_after_destination_image_edit_verifies_current_destination(self):
        import base64
        import io
        from PIL import Image
        from access import Access
        from metadata import Metadata
        from project_projection import ProjectProjection
        self.selection['roots']['records']=[self.text()['id']]
        source=self.stop();transfer=ProjectTransfer(source);report=transfer.preview(self.selection)
        birth=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'edited','Editable destination','edited-key')
        host=Metadata(self.root/'edit-host');projection=None;db=None
        try:
            authority=Access(host,host.path);token=authority.exchange(authority._local_owner_token())['token']
            with ProjectStore.open(self.root/'edited') as store,authority.bind(token):
                db=Metadata(self.root/'edit-projection',dataset_id=store.snapshot()['project_id'],projection_id=uuid.uuid4().hex)
                projection=ProjectProjection(store,db,authority,{})
                image=io.BytesIO();Image.new('RGB',(4,3),'purple').save(image,'PNG');raw=image.getvalue()
                current=projection.data.import_image(dict(image=base64.b64encode(raw).decode(),name='New destination-only image',
                    groups=['new-destination'],rights='New authored rights'),projection.session.snapshot['checkpoint'],'new-image')
                checkpoint=projection.session.snapshot['checkpoint']
                self.assertNotEqual(checkpoint,birth['checkpoint'])
                self.assertNotIn(hashlib.sha256(raw).hexdigest(),source.artifacts.declarations)
                # The trusted controller pins its selected Store; replay must
                # borrow that exact writer rather than opening a second one.
                with authority.lock,projection.session.lock,db.lock:
                    selected=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'edited','Editable destination','edited-key',opened_store=store)
                self.assertTrue(selected['replayed']);self.assertEqual(selected['checkpoint'],checkpoint)
                self.assertEqual(selected['verification']['active_data_records'],2)
                self.assertEqual(store.snapshot()['checkpoint'],checkpoint)
                with authority.lock,projection.session.lock,db.lock,self.assertRaises(WorkbenchError):
                    transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'different','Wrong destination','different-key',opened_store=store)
                projection.close();projection=None
            replay=transfer.extract(self.selection,report['report_sha256'],self.parent_fd,'edited','Editable destination','edited-key')
            self.assertTrue(replay['replayed']);self.assertEqual(replay['project_id'],birth['project_id'])
            self.assertEqual(replay['checkpoint'],checkpoint);self.assertEqual(replay['verification']['checkpoint'],checkpoint)
            self.assertEqual(replay['verification']['active_data_records'],2)
            self.assertEqual(replay['source'],birth['source']);self.assertEqual(replay['input_sha256'],birth['input_sha256'])
            self.assertEqual(replay['artifacts'],birth['artifacts']);self.assertFalse(replay['selected'])
        finally:
            if projection is not None:projection.close()
            elif db is not None:db.close()
            host.close()
            with psycopg.connect(source.db.dsn,autocommit=True) as cleanup:
                for database in (db,host):
                    if database is not None:cleanup.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(database.schema)))


if __name__=='__main__':unittest.main()
