"""Real HTTP/PG recovery for stopped, nonexecuting runtime copy owners.

Reuse the authored /usr/bin/true ELF and inert package fixture. No runtime is
installed, imported, probed or executed. Abrupt fixture disposal closes only
known workerless handles; it does not claim successful public Close.
"""
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading
import unittest
from unittest.mock import patch

import psycopg
from psycopg import sql

from app import make_handler
from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
from project_runtime import _intent_key, validate_operation_result
from project_session import operation_documents, operation_records
from project_workspace import ProjectWorkspace
from workbench import WorkbenchError
import test_project_runtime_http as runtime_fixture


class RuntimeAbandonmentCodecTests(unittest.TestCase):
    def test_completed_capture_for_same_project_and_key_cannot_be_abandoned(self):
        project='1'*32;actor='2'*32;key='capture-codec-fixture';manifest='3'*64
        instant='2026-10-22T10:00:00+00:00';input_sha='4'*64
        intent=dict(format='project_runtime_capture_intent_v1',project_id=project,
            manifest_sha256=manifest,file_count=1,total_bytes=1,actor_id=actor,
            observed_at=instant,request_key=key)
        abandoned=dict(format='project_runtime_capture_abandon_v1',project_id=project,
            capture_key=key,input_sha256=input_sha,manifest_sha256=manifest,
            actor_id=actor,reason='Explicitly stopped copy',observed_checkpoint='5'*64,
            observed_at=instant)
        def receipt(operation,request_key,result):
            return dict(family='project_operation',
                id=project+'.'+hashlib.sha256(request_key.encode()).hexdigest(),
                document=dict(format='project_operation_v2',project_id=project,
                    operation=operation,target=manifest,request_key=request_key,
                    input_sha256=input_sha,result=result))
        records=[receipt('runtime.capture_intent',_intent_key(key),intent)]
        operation_documents(records)
        self.assertTrue(validate_operation_result('runtime.abandon',abandoned,records))
        complete=dict(intent,format='project_runtime_capture_v1',
            runtime_ref=dict(kind='runtime',catalog_id=project,id=manifest,sha256=manifest))
        self.assertTrue(validate_operation_result('runtime.capture',complete))
        records.append(receipt('runtime.capture',key,complete))
        operation_documents(records)
        with self.assertRaisesRegex(WorkbenchError,'Completed runtime capture cannot be abandoned'):
            validate_operation_result('runtime.abandon',abandoned,records)
        # Independent historical project keys cannot contradict this intent.
        other=copy.deepcopy(records[-1]);other['document']['project_id']='6'*32
        other['document']['result']['project_id']='6'*32
        other['document']['result']['runtime_ref']['catalog_id']='6'*32
        other['id']='6'*32+'.'+hashlib.sha256(key.encode()).hexdigest()
        records[-1]=other
        operation_documents(records)
        self.assertTrue(validate_operation_result('runtime.abandon',abandoned,records))


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ProjectRuntimeRecoveryHTTP(unittest.TestCase):
    select_host=runtime_fixture.ProjectRuntimeHTTP.select_host
    request=runtime_fixture.ProjectRuntimeHTTP.request
    state=runtime_fixture.ProjectRuntimeHTTP.state
    envelope=runtime_fixture.ProjectRuntimeHTTP.envelope
    action=runtime_fixture.ProjectRuntimeHTTP.action
    create=runtime_fixture.ProjectRuntimeHTTP.create
    arguments=runtime_fixture.ProjectRuntimeHTTP.arguments
    transport=runtime_fixture.ProjectRuntimeHTTP.transport
    call=runtime_fixture.ProjectRuntimeHTTP.call

    def setUp(self):
        runtime_fixture.ProjectRuntimeHTTP.setUp(self)
        self.enterContext(patch('runs.Runs',side_effect=AssertionError('Recovery constructed Runs')))
        self.enterContext(patch('subprocess.Popen',side_effect=AssertionError('Runtime recovery executed a child')))
        self.config=copy.deepcopy(self.workspace._runtime_sources['inert-fixture'])
        self.create()
        self.inventory=self.call('runtime_inspect',source='inert-fixture',limit=1)

    def cleanup_owned(self):
        schemas=set(self.schemas)
        for workspace,server,thread in reversed(self.hosts):
            server.shutdown();server.server_close();thread.join(3)
            if workspace._closed:continue
            self.dispose_handles(workspace)
        for dsn,control in self.controls:
            for manifest in control.rglob('.tuldok.json'):
                value=json.loads(manifest.read_bytes())
                schemas.add((dsn,'projection_'+value['projection_id'] if value['version']==2 else 'catalog_'+value['dataset_id']))
        for dsn,schema in schemas:
            with psycopg.connect(connection_info(dsn),autocommit=True) as connection:
                connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))

    @staticmethod
    def dispose_handles(workspace):
        # Every tested operation is synchronous and Popen is forbidden. Leave
        # journals/canonical files intact while disposing test-owned handles.
        for projection in (workspace._projection,workspace._retained_recovery):
            if projection is None:continue
            if projection.execution._runs is not None:raise AssertionError('Unexpected live Run owner')
            if projection.sources is not None:projection.sources.close()
            projection.artifacts.close();projection.db.close()
        if workspace._store is not None:workspace._store.close()
        for _path,descriptor in workspace._roots.values():os.close(descriptor)
        workspace._roots.clear();workspace.db.close();workspace._closed=True

    def stop_inert_application(self,workspace):
        for candidate,server,thread in self.hosts:
            if candidate is workspace:
                server.shutdown();server.server_close();thread.join(3)
                break
        self.dispose_handles(workspace)

    def start_application(self,control,*,sources=None):
        dsn=os.environ['TULDOK_DATABASE_URL']
        workspace=ProjectWorkspace(control,{'fixture':self.external},dsn=dsn,runtime_sources=sources)
        self.schemas.append((dsn,workspace.db.schema));self.controls.append((dsn,Path(control)))
        owner=ExplicitOwnerFixture.bootstrap(workspace)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(workspace))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.hosts.append((workspace,server,thread));self.workspace,self.owner=workspace,owner
        self.origin='http://127.0.0.1:'+str(server.server_port)

    def capture_arguments(self,key,*,reserve=0):
        return self.arguments('runtime_capture',source='inert-fixture',
            expected_inventory_sha256=self.inventory['inventory_sha256'],reserve_bytes=reserve,request_key=key)

    def partial(self,key):
        status,error=self.transport('runtime_capture',self.capture_arguments(key,reserve=2**53-1))
        self.assertEqual(status,409,error);self.assertEqual(error['code'],'unavailable')
        projection=self.workspace._projection
        records=projection.session.snapshot['records'];intent=operation_records(records)[_intent_key(key)]
        marker=projection.custody.snapshot()['runtime_effects'][0]
        self.assertEqual(marker['input_sha256'],intent['input_sha256'])
        self.assertNotIn(key,operation_records(records));self.assertTrue(projection.custody.has_pending)
        return projection

    def test_actual_partial_copy_abandon_needs_no_remaining_source_and_retains_binding(self):
        key='partial-source-lost';projection=self.partial(key);before=self.state();binding=before['binding']
        status,error=self.transport('close',self.envelope(request_key='close-pending-runtime'))
        self.assertEqual(status,409,error);self.assertTrue(projection.custody.has_pending)
        recovery=self.state();self.assertEqual(recovery['state'],'recovery_required')
        shutil.rmtree(self.config['python_root']);shutil.rmtree(self.config['site_packages'])
        with patch.object(projection.runtime,'resolve_configuration',side_effect=AssertionError('Abandon read missing source')):
            abandoned=self.call('runtime_abandon',capture_key=key,reason='Explicit owner retains partial copy as abandoned')
        self.assertEqual(abandoned['capture_key'],key)
        self.assertTrue(validate_operation_result('runtime.abandon',abandoned,projection.session.snapshot['records']))
        self.assertEqual(self.state()['binding'],binding);self.assertEqual(self.state()['state'],'open')
        self.assertFalse(projection.custody.has_pending)
        self.assertEqual(self.call('runtime_status',capture_key=key)['state'],'abandoned')
        self.action('save');self.action('close')

    def test_final_sql_failure_retry_requires_exact_public_view_and_never_recopies(self):
        projection=self.workspace._projection;db=projection.db;key='lost-final-sql'
        db.execute('CREATE TABLE runtime_ack_parent(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE runtime_ack_child(id INTEGER REFERENCES runtime_ack_parent(id) DEFERRABLE INITIALLY DEFERRED)')
        mutate=projection.session.mutate
        def fault(operation,target,body,checkpoint,request_key,invoke,capture,**kwargs):
            if operation!='runtime.capture':return mutate(operation,target,body,checkpoint,request_key,invoke,capture,**kwargs)
            def bad():
                result=invoke();db.execute('INSERT INTO runtime_ack_child VALUES(84)');return result
            return mutate(operation,target,body,checkpoint,request_key,bad,capture,**kwargs)
        with patch.object(projection.session,'mutate',side_effect=fault):
            status,error=self.transport('runtime_capture',self.capture_arguments(key))
        self.assertEqual(status,503,error);self.assertFalse(projection.session.available)
        state=self.state();self.assertEqual(state['state'],'recovery_required')
        arguments=self.capture_arguments(key);before=projection.session.snapshot
        for change in (dict(binding='f'*32),dict(expected_checkpoint='f'*64)):
            with patch.object(projection.runtime,'recover_capture',side_effect=AssertionError('Rejected public view reached recovery')):
                status,error=self.transport('runtime_capture',dict(arguments,**change))
            self.assertEqual(status,409,error);self.assertEqual(error['code'],'stale_project')
        self.assertEqual(projection.session.snapshot,before);self.assertTrue(projection.custody.has_pending)
        with patch.object(projection.runtime.owner,'create',side_effect=AssertionError('Do not recopy committed runtime')):
            status,recovered=self.transport('runtime_capture',arguments)
        self.assertEqual(status,200,recovered);self.assertEqual(recovered['binding'],state['binding'])
        self.assertEqual(self.state()['state'],'open');self.assertTrue(projection.session.available)
        self.assertFalse(projection.custody.has_pending)
        self.assertEqual(self.call('runtime_status',capture_key=key)['state'],'captured')
        self.action('close')

    def test_original_physical_cache_recovery_and_foreign_intent_cannot_regenerate(self):
        key='published-before-final';original=self.workspace;projection=original._projection;create=projection.runtime.owner.create
        def after_copy(*args,**kwargs):
            value=create(*args,**kwargs)
            raise WorkbenchError('Injected loss after actual native publication.','outcome_unknown',503)
        with patch.object(projection.runtime.owner,'create',side_effect=after_copy):
            status,error=self.transport('runtime_capture',self.capture_arguments(key))
        self.assertEqual(status,503,error);physical=projection.db.projection_id
        self.assertTrue((projection.runtime.owner.path/self.inventory['inventory_sha256']).is_dir())
        shutil.copytree(self.external/'alpha',self.external/'clone',ignore=shutil.ignore_patterns('.tuldok-local'))
        self.start_application(self.path/'foreign-control',sources={'inert-fixture':self.config})
        self.action('open',root='fixture',directory='clone')
        foreign=self.workspace._projection;before=foreign.session.snapshot
        with patch.object(foreign.runtime.owner,'create',side_effect=AssertionError('Imported intent regenerated a runtime')):
            status,error=self.transport('runtime_capture',self.capture_arguments(key))
        self.assertEqual(status,409,error);self.assertEqual(error['code'],'unavailable')
        self.assertEqual(foreign.session.snapshot,before);self.assertFalse(foreign.custody.has_pending)
        self.action('close')
        self.stop_inert_application(original)
        shutil.rmtree(self.config['python_root']);shutil.rmtree(self.config['site_packages'])
        self.start_application(original.path,sources={})
        opened=self.action('open',root='fixture',directory='alpha')
        self.assertEqual(opened['state'],'recovery_required');binding=opened['binding']
        self.assertNotEqual(self.workspace._projection.db.projection_id,physical)
        with patch('runtime_snapshots.RuntimeSnapshots.create',side_effect=AssertionError('Reopened recovery recopied runtime')):
            status,recovered=self.transport('runtime_capture',self.capture_arguments(key))
        self.assertEqual(status,200,recovered);self.assertEqual(recovered['binding'],binding)
        self.assertEqual(self.workspace._projection.db.projection_id,physical)
        self.assertEqual(self.workspace.custody.pending(self.workspace._store),[])
        self.assertEqual(self.state()['state'],'open');self.assertEqual(self.call('runtime_sources')['items'],[])
        self.action('close')

    def test_original_stopped_copy_can_be_abandoned_after_fresh_open_without_aliases(self):
        key='original-partial';projection=self.partial(key);original=self.workspace;physical=projection.db.projection_id
        self.stop_inert_application(original)
        shutil.rmtree(self.config['python_root']);shutil.rmtree(self.config['site_packages'])
        self.start_application(original.path,sources={})
        opened=self.action('open',root='fixture',directory='alpha')
        self.assertEqual(opened['state'],'recovery_required');binding=opened['binding']
        abandoned=self.call('runtime_abandon',capture_key=key,reason='Original owner acknowledges stopped partial copy')
        self.assertEqual(abandoned['capture_key'],key);self.assertEqual(self.state()['binding'],binding)
        self.assertEqual(self.workspace._projection.db.projection_id,physical)
        self.assertEqual(self.workspace.custody.pending(self.workspace._store),[])
        self.assertEqual(self.call('runtime_status',capture_key=key)['state'],'abandoned')
        self.action('save');self.action('close')


if __name__=='__main__':unittest.main()
