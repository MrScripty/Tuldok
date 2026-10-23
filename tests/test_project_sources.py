"""Explicit rooted source registration/import using disposable PostgreSQL.

Fixtures are authored native scientific bytes. No source script, worker,
training runtime, dependency installer, network fetch or laboratory is used.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import uuid

from access import Access, AccessError
from metadata import Metadata
from project_artifacts import ProjectArtifacts, validate_declaration
from project_data import ProjectData, decode_data_records, validate_operation_result as data_result
from project_material import ProjectMaterial, decode_records as material_records
from project_material import validate_operation_result as material_result
from project_session import ProjectSession, operation_records
from project_sources import SourceAdapter, validate_operation_result
from project_store import ProjectStore
from projects import Projects
from qualify_scientific_fields import neutral_bundle
from workbench import WorkbenchError


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class SourceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='tuldok-project-source-');self.root=Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup);self.resources=[];self.schemas=[];self.addCleanup(self.cleanup)
        self.source_root=self.root/'source';self.source_root.mkdir()
        self.raw=neutral_bundle();self.digest=hashlib.sha256(self.raw).hexdigest()
        (self.source_root/'field.zip').write_bytes(self.raw)
        (self.source_root/'never-run.py').write_text('raise AssertionError("Source registration executed a script")\n')
        self.manifest=dict(schema_version=1,id='a'*32,name='Authored source λ',
            data=[dict(id='fields',label='Authored native fields',path='field.zip',sha256=self.digest)],
            recipes=[],evidence=[],requirements=[])
        self.manifest_raw=(json.dumps(self.manifest,ensure_ascii=False,indent=3)+'\n\n').encode()
        (self.source_root/'source.json').write_bytes(self.manifest_raw)
        self.host=self.metadata('host')
        self.access=Access(self.host,self.host.path)
        self.token=self.access.exchange(self.access._local_owner_token())['token']
        self.enterContext(self.access.bind(self.token))
        self.store=ProjectStore.create(self.root/'project','Source fixture','new-source','a'*64)
        self.resources.append(self.store)
        self.artifacts=ProjectArtifacts(self.store);self.resources.append(self.artifacts)
        self.projection,self.adapter=self.project('projection',{'fixture':self.source_root})
        self.session=self.projection.session;self.db=self.session.db

    def metadata(self,name,*,projection=False):
        kwargs=dict(dataset_id=self.store.snapshot()['project_id'],projection_id=uuid.uuid4().hex) if projection else {}
        db=Metadata(self.root/name,**kwargs);self.resources.append(db);self.schemas.append(db.schema)
        return db

    def project(self,name,roots):
        db=self.metadata(name,projection=True)
        session=ProjectSession(self.store,db,self.access,self.artifacts,validate_records=self.validate)
        data=ProjectData(session);data.restore();materials=ProjectMaterial(session);materials.restore()
        context=SimpleNamespace(db=db,lock=db.lock,path=db.path,access=materials.owner_access)
        sources=Projects(context,roots);self.resources.append(sources)
        projection=SimpleNamespace(session=session,db=db,access=self.access,data=data,materials=materials,sources=sources)
        return projection,SourceAdapter(projection)

    def cleanup(self):
        import psycopg
        from psycopg import sql
        from metadata import connection_info
        for resource in reversed(self.resources):resource.close()
        with psycopg.connect(connection_info(),autocommit=True) as db:
            for schema in self.schemas:db.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    def validate(self,records):
        decode_data_records(records);material_records(records)
        for envelope in records:
            if envelope['family']=='project_artifact':validate_declaration(envelope['document'])
        for receipt in operation_records(records).values():
            operation,result=receipt['operation'],receipt['result']
            if not (validate_operation_result(operation,result,records) or data_result(operation,result,records) or material_result(operation,result,records)):
                raise AssertionError('Unexpected fixture operation')

    def register(self,adapter=None,key='register-source',body=None,checkpoint=None):
        adapter=adapter or self.adapter
        return adapter.register(body or dict(root='fixture',manifest_path='source.json'),
            checkpoint or adapter.session.snapshot['checkpoint'],key)

    def import_body(self,registration):
        return dict(snapshot={key:registration[key] for key in ('origin_catalog_id','project_id','manifest_sha256')},
            reference_id='fields',expected_sha256=self.digest,
            document=dict(name='Authored scientific source',groups=['source-fixture'],rights='Authored fixture; no scientific qualification claim.'))

    def test_registration_retains_original_bytes_attribution_and_one_canonical_operation(self):
        with patch('subprocess.Popen',side_effect=AssertionError('No script process')):
            result=self.register()
        self.assertEqual(result['actor_id'],self.access._context().actor_id)
        self.assertTrue(validate_operation_result('source.register',result,self.store.snapshot()['records']))
        snapshot=self.store.snapshot();records=snapshot['records']
        self.assertEqual({r['family'] for r in records},{'project_snapshot','project_artifact','project_operation'})
        retained=next(r for r in records if r['family']=='project_snapshot')
        self.assertEqual(retained['document']['value']['manifest_sha256'],hashlib.sha256(self.manifest_raw).hexdigest())
        self.assertEqual(self.artifacts.read_blob(retained['document']['artifacts'][0]['blob']),self.manifest_raw)
        self.assertEqual(self.db.execute('SELECT count(*) FROM workspace_projects').fetchone()[0],1)
        again=self.register(key='register-again')
        self.assertEqual(again['manifest_sha256'],result['manifest_sha256'])
        self.assertEqual(next(r for r in self.store.snapshot()['records'] if r['family']=='project_snapshot'),retained)
        for forged in (dict(result,name='Well-formed forged snapshot'),dict(result,root='fixture'),dict(result,registered_at='2026-10-22T12:00:00')):
            with self.assertRaises(WorkbenchError):validate_operation_result('source.register',forged,records)
        self.assertFalse(validate_operation_result('data.import_scientific',{},records))

    def test_cold_open_has_no_bindings_and_explicit_replay_can_rebind_relocated_root(self):
        first=self.register();canonical=self.store.snapshot()
        original=next(r for r in canonical['records'] if r['family']=='project_snapshot')
        moved=self.root/'relocated';shutil.copytree(self.source_root,moved)
        projection,adapter=self.project('cold',{'fixture':moved})
        self.assertEqual(projection.db.execute('SELECT count(*) FROM workspace_projects').fetchone()[0],0)
        with self.assertRaises(WorkbenchError):projection.sources.read_snapshot_manifest(first['project_id'],first['manifest_sha256'])
        self.assertEqual(self.register(adapter,checkpoint='0'*64),first)
        self.assertEqual(self.store.snapshot(),canonical)
        current=json.loads(projection.db.execute('SELECT document FROM workspace_projects').fetchone()[0])
        self.assertNotEqual(current['root_identity'],original['document']['value']['root_identity'])
        self.assertEqual(next(r for r in self.store.snapshot()['records'] if r['family']=='project_snapshot'),original)
        self.assertEqual(projection.sources.read_snapshot_manifest(first['project_id'],first['manifest_sha256'])[1],self.manifest_raw)

    def test_receipt_cannot_bind_absent_current_root_and_agent_is_denied_before_read(self):
        first=self.register();canonical=self.store.snapshot()
        projection,adapter=self.project('without-roots',{})
        with self.assertRaises(WorkbenchError):self.register(adapter,checkpoint='0'*64)
        self.assertEqual(projection.db.execute('SELECT count(*) FROM workspace_projects').fetchone()[0],0)
        agent=self.access.issue(dict(label='Source editor',scopes=['inspect','edit']))
        with self.access.bind(agent['token']),patch.object(self.projection.sources,'_read_snapshot_file',side_effect=AssertionError('Owner check must precede I/O')):
            with self.assertRaises(AccessError):self.register(checkpoint='0'*64)
        self.assertEqual(self.store.snapshot(),canonical)

    def test_changed_manifest_stale_cas_and_key_conflict_never_renew_binding(self):
        first=self.register();canonical=self.store.snapshot()
        current=self.db.execute('SELECT document FROM workspace_projects').fetchone()[0]
        (self.source_root/'other.json').write_bytes(self.manifest_raw)
        with self.assertRaises(WorkbenchError) as error:self.register(body=dict(root='fixture',manifest_path='other.json'))
        self.assertEqual(error.exception.code,'conflict')
        with self.assertRaises(WorkbenchError) as error:self.register(key='stale-source',checkpoint='0'*64)
        self.assertEqual(error.exception.code,'stale_project')
        changed=dict(self.manifest,name='Changed source');(self.source_root/'source.json').write_text(json.dumps(changed))
        with self.assertRaises(WorkbenchError) as error:self.register(checkpoint='0'*64)
        self.assertEqual(error.exception.code,'stale')
        self.assertEqual(self.db.execute('SELECT document FROM workspace_projects').fetchone()[0],current)
        self.assertEqual(self.store.snapshot(),canonical)

    def test_symlink_and_special_source_reads_refuse_before_any_canonical_import(self):
        outside=self.root/'outside.json';outside.write_bytes(self.manifest_raw)
        (self.source_root/'linked.json').symlink_to(outside)
        with self.assertRaises(WorkbenchError):self.register(body=dict(root='fixture',manifest_path='linked.json'))
        first=self.register();canonical=self.store.snapshot();body=self.import_body(first)
        (self.source_root/'field.zip').unlink();(self.source_root/'field.zip').symlink_to(outside)
        with self.assertRaises(WorkbenchError):self.adapter.import_scientific(body,self.session.snapshot['checkpoint'],'symlink-import')
        (self.source_root/'field.zip').unlink();os.mkfifo(self.source_root/'field.zip')
        with self.assertRaises(WorkbenchError):self.adapter.import_scientific(body,self.session.snapshot['checkpoint'],'fifo-import')
        self.assertEqual(self.store.snapshot(),canonical)

    def test_real_scientific_import_uses_one_data_session_and_cold_source_access_stays_unbound(self):
        registration=self.register();body=self.import_body(registration)
        with patch.object(self.session,'mutate',wraps=self.session.mutate) as observed:
            row=self.adapter.import_scientific(body,self.session.snapshot['checkpoint'],'import-science')
        self.assertEqual(observed.call_count,1)
        self.assertEqual(observed.call_args.args[0],'data.import_scientific')
        self.assertEqual(self.projection.data.workbench.asset(row['id'])[0],self.raw)
        canonical=self.store.snapshot()
        projection,adapter=self.project('cold-import',{'fixture':self.source_root})
        self.assertEqual(projection.data.get(row['id']),row)
        self.assertEqual(projection.data.workbench.asset(row['id'])[0],self.raw)
        with self.assertRaises(WorkbenchError):adapter.import_scientific(body,'0'*64,'import-science')
        self.assertEqual(self.register(adapter,checkpoint='0'*64),registration)
        self.assertEqual(adapter.import_scientific(body,'0'*64,'import-science'),row)
        forged=copy.deepcopy(body);forged['snapshot']['origin_catalog_id']='f'*32
        with self.assertRaises(WorkbenchError):adapter.import_scientific(forged,projection.session.snapshot['checkpoint'],'foreign-unbound')
        self.assertEqual(self.store.snapshot(),canonical)

    def test_deferred_sql_failure_retains_snapshot_receipt_and_explicit_cold_replay_rebinds(self):
        self.db.execute("CREATE FUNCTION fixture_refuse_source() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled source SQL failure' USING ERRCODE='23514'; END; $$")
        self.db.execute('CREATE CONSTRAINT TRIGGER fixture_source_failure AFTER INSERT ON workspace_projects DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fixture_refuse_source()')
        with self.assertRaises(WorkbenchError) as error:self.register()
        self.assertEqual(error.exception.code,'projection_unavailable')
        self.assertTrue(error.exception.receipt['committed'])
        canonical=self.store.snapshot();original=operation_records(canonical['records'])['register-source']['result']
        self.assertEqual(self.db.execute('SELECT count(*) FROM workspace_projects').fetchone()[0],0)
        projection,adapter=self.project('cold-after-sql-failure',{'fixture':self.source_root})
        self.assertEqual(self.register(adapter,checkpoint='0'*64),original)
        self.assertEqual(self.store.snapshot(),canonical)
        self.assertEqual(projection.sources.read_snapshot_manifest(original['project_id'],original['manifest_sha256'])[1],self.manifest_raw)

    def test_reference_page_measures_only_selected_current_data_without_changing_registration(self):
        self.manifest['data'].extend([dict(id='missing',label='Missing source',path='missing.zip',sha256='0'*64),
            dict(id='later',label='Unselected source',path='never-read.bin',sha256='1'*64)])
        self.manifest['recipes']=[dict(id='script',label='Never inspect or run',path='never-run.py')]
        self.manifest_raw=json.dumps(self.manifest,ensure_ascii=False).encode()
        (self.source_root/'source.json').write_bytes(self.manifest_raw)
        registration=self.register();snapshot={key:registration[key] for key in ('origin_catalog_id','project_id','manifest_sha256')}
        canonical=self.store.snapshot()
        with patch.object(self.projection.sources,'_inspect',wraps=self.projection.sources._inspect) as inspected, \
             patch.object(self.projection.sources,'_get',side_effect=AssertionError('No whole-project inspection')), \
             patch('extension_contract.catalog',side_effect=AssertionError('No extension callbacks')), \
             patch('project_activity.activity',side_effect=AssertionError('No activity callbacks')):
            page=self.adapter.references(snapshot,offset=0,limit=1)
            self.assertEqual((page['total'],page['offset'],page['limit']),(3,0,1))
            self.assertEqual(len(page['items']),1)
            self.assertEqual(page['items'][0]['observed_sha256'],self.digest)
            self.assertEqual(page['items'][0]['integrity'],'verified')
            self.assertEqual(page['items'][0]['label'],'Authored native fields')
            missing=self.adapter.references(snapshot,offset=1,limit=1)
            self.assertEqual(missing['items'][0]['status'],'missing')
            self.assertEqual([call.args[1]['id'] for call in inspected.call_args_list],['fields','missing'])
        projection,adapter=self.project('cold-references',{'fixture':self.source_root})
        with patch.object(projection.sources,'_read',side_effect=AssertionError('No I/O before explicit binding')):
            with self.assertRaises(WorkbenchError) as error:adapter.references(snapshot,limit=1)
        self.assertEqual(error.exception.code,'unavailable')
        self.assertEqual(self.store.snapshot(),canonical)
