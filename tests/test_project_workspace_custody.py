"""Flag-gated real Workspace custody boundaries, PostgreSQL and loopback HTTP.

These tests do not qualify public M3 availability. A real local provider remains
active while an actual canonical commit loses its acknowledgement. Fault patches
inject only the acknowledgement failure; owners and dispatch remain production.
"""
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid

import psycopg
from psycopg import sql

import agent_api
from app import make_handler
from auth_helpers import ExplicitOwnerFixture
from metadata import connection_info
from project_store import ProjectStoreError
import project_workspace
from workbench import WorkbenchError, encode


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'), 'Requires disposable real PostgreSQL')
class ProjectWorkspaceCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='tuldok-workspace-custody-')
        self.root=Path(self.temp.name);self.external=self.root/'external';self.external.mkdir()
        self.provider_entered=threading.Event();self.provider_release=threading.Event()
        self.provider_disconnected=threading.Event();self.provider_requests=[];self.worker_errors=[]
        self.workspace=None;self.servers=[]
        self.previous_hook=threading.excepthook
        threading.excepthook=lambda event:self.worker_errors.append(event.exc_value)
        self.addCleanup(self.cleanup)
        self.flag=patch.object(project_workspace,'M3_ENABLED',True);self.flag.start()
        self.workspace=project_workspace.ProjectWorkspace(self.root/'control',{'fixture':self.external})
        self.owner=ExplicitOwnerFixture.bootstrap(self.workspace)
        fixture=self
        class Provider(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def send(self,value):
                raw=encode(value).encode();self.send_response(200)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):fixture.provider_disconnected.set()
            def do_GET(self):
                fixture.provider_requests.append(('GET',self.path))
                self.send({'data':[{'id':'fixture-model','owned_by':'fixture'}]})
            def do_POST(self):
                fixture.provider_requests.append(('POST',self.path))
                self.rfile.read(int(self.headers.get('Content-Length','0')))
                fixture.provider_entered.set();fixture.provider_release.wait(20)
                self.send({'model':'fixture-model','choices':[{'finish_reason':'stop','message':{'content':encode({'label':'positive'})}}]})
        self.provider=self.server(Provider)
        self.provider_url='http://127.0.0.1:'+str(self.provider.server_port)
        self.application=self.server(make_handler(self.workspace))
        self.origin='http://127.0.0.1:'+str(self.application.server_port)
        state=self.state()
        status,state=self.call('new',dict(binding=state['binding'],expected_checkpoint=None,request_key=uuid.uuid4().hex,
            root='fixture',directory='owned-project',name='Owned custody boundaries'))
        self.assertEqual(status,200,state)
        status,imported=self.call('data_import_text',self.envelope(text='Exact owned text café 山.',name='Owned source',groups=['owned'],parents=[],rights='Authored fixture'))
        self.assertEqual(status,200,imported)
        self.source=imported['value']

    def server(self,handler):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.servers.append((server,thread));return server

    def call(self,action,body=None,*,token=None):
        name='project_files.'+action;operation=agent_api.operation(name)
        headers={'Origin':self.origin,'Content-Type':'application/json',
                 'Authorization':'Bearer '+(token or self.owner.token),
                 'Tuldok-Operation-Contract':agent_api.selected_header(name)}
        request=Request(self.origin+operation['path'],data=None if body is None else encode(body).encode(),headers=headers,method=operation['method'])
        try:response=urlopen(request,timeout=15)
        except HTTPError as error:response=error
        with response:return response.status,json.loads(response.read())

    def state(self):
        status,value=self.call('status');self.assertEqual(status,200,value);return value

    def envelope(self,**values):
        state=self.state()
        return dict(binding=state['binding'],expected_checkpoint=state['project']['checkpoint'],request_key=uuid.uuid4().hex,**values)

    def start_provider(self):
        status,result=self.call('execution_producer_start',self.envelope(family='text_proposal_history',document=dict(
            request_id=uuid.uuid4().hex,source_id=self.source['id'],revision=self.source['revision'],source_revision=self.source['source_revision'],
            server_url=self.provider_url,model='fixture-model',instruction='Select only an exact offered label.',seed=7,labels=['positive','negative'])))
        self.assertEqual(status,200,result)
        self.assertTrue(self.provider_entered.wait(10),'Actual provider POST was not entered')
        projection=self.workspace._projection;adapter=projection.execution.producer_execution
        owner=adapter._owners['text_proposal_history']
        self.assertIsNone(projection.execution._runs)
        self.assertTrue(owner.worker.is_alive());self.assertFalse(owner.stop.is_set())
        self.assertTrue(projection.custody.has_pending)
        return projection,owner,result

    def assert_same_locked_selection(self,store,projection,root_fd,physical):
        self.assertIs(self.workspace._store,store);self.assertIs(self.workspace._projection,projection)
        self.assertEqual(store._root_fd,root_fd)
        observed=os.fstat(root_fd);self.assertEqual((observed.st_dev,observed.st_ino),physical)
        competing=os.open(self.external/'owned-project',os.O_RDONLY|os.O_DIRECTORY)
        try:
            with self.assertRaises(BlockingIOError):fcntl.flock(competing,fcntl.LOCK_EX|fcntl.LOCK_NB)
        finally:os.close(competing)
        self.assertFalse(projection.db.connection.closed)

    def stop_fixture_worker(self,owner):
        # Explicit disposable-fixture disposal, not a successful application
        # cancellation/recovery claim. Unknown provider cessation stays unknown.
        owner.stop.set();self.provider_release.set();owner.worker.join(10)
        self.assertFalse(owner.worker.is_alive())

    def test_recovery_open_keeps_producer_only_store_projection_and_real_root_flock(self):
        projection,owner,_=self.start_provider();state=self.state()
        store=self.workspace._store;root_fd=store._root_fd;st=os.fstat(root_fd);physical=(st.st_dev,st.st_ino)
        original=store.commit;injected=[]
        def lost_ack(*args,**kwargs):
            result=original(*args,**kwargs)
            injected.append(result['checkpoint'])
            raise ProjectStoreError('Authored canonical acknowledgement loss after actual commit','unknown',409)
        with patch.object(store,'commit',lost_ack):
            status,error=self.call('data_import_text',dict(binding=state['binding'],expected_checkpoint=state['project']['checkpoint'],
                request_key=uuid.uuid4().hex,text='Canonical result selected before lost acknowledgement.',name='Lost reply source',groups=['owned'],parents=[],rights='Authored fault fixture'))
        self.assertEqual(status,409,error);self.assertEqual(error['code'],'unknown');self.assertEqual(len(injected),1)
        self.assertFalse(projection.session.available)
        recovery=self.state();self.assertEqual(recovery['state'],'recovery_required')
        self.assertTrue(owner.worker.is_alive());self.assertFalse(owner.stop.is_set())
        self.assert_same_locked_selection(store,projection,root_fd,physical)
        arguments=dict(binding=recovery['binding'],expected_checkpoint=recovery['project']['checkpoint'],request_key=uuid.uuid4().hex,root='fixture',directory='owned-project')
        status,error=self.call('open',arguments)
        self.assertEqual(status,503,error);self.assertEqual(error['code'],'projection_unavailable')
        self.assertTrue(owner.worker.is_alive());self.assertFalse(owner.stop.is_set())
        self.assert_same_locked_selection(store,projection,root_fd,physical)
        # The old local provider thread can drain without any Run owner, yet no
        # generic provider cessation receipt exists. Recovery remains fenced.
        self.stop_fixture_worker(owner)
        status,error=self.call('open',dict(arguments,request_key=uuid.uuid4().hex))
        self.assertEqual(status,503,error);self.assertEqual(error['code'],'projection_unavailable')
        self.assertTrue(projection.custody.has_pending)
        self.assert_same_locked_selection(store,projection,root_fd,physical)
        self.assertIsNone(projection.execution._runs)

    def test_normal_stale_reconcile_checkpoint_refuses_before_any_provider_drain(self):
        projection,owner,_=self.start_provider();stale=self.state()
        store=self.workspace._store;root_fd=store._root_fd;st=os.fstat(root_fd);physical=(st.st_dev,st.st_ino)
        status,changed=self.call('data_import_text',dict(binding=stale['binding'],expected_checkpoint=stale['project']['checkpoint'],
            request_key=uuid.uuid4().hex,text='A later canonical edit.',name='Later source',groups=['owned'],parents=[],rights='Authored fixture'))
        self.assertEqual(status,200,changed);self.assertNotEqual(changed['checkpoint'],stale['project']['checkpoint'])
        before=store.snapshot();thread=owner.worker
        status,error=self.call('execution_reconcile_current',dict(binding=stale['binding'],expected_checkpoint=stale['project']['checkpoint']))
        self.assertEqual(status,409,error);self.assertEqual(error['code'],'stale_project')
        self.assertIs(owner.worker,thread);self.assertTrue(thread.is_alive());self.assertFalse(owner.stop.is_set())
        self.assertFalse(self.provider_release.is_set());self.assertFalse(self.provider_disconnected.is_set())
        self.assertEqual(store.snapshot(),before)
        self.assertEqual(self.state()['state'],'open')
        self.assert_same_locked_selection(store,projection,root_fd,physical)
        self.assertEqual(self.provider_requests,[('GET','/v1/models'),('POST','/v1/chat/completions')])

    def cleanup(self):
        try:
            if self.workspace is not None:
                projection=self.workspace._projection
                if projection is not None:
                    adapter=projection.execution.producer_execution
                    for owner in adapter._owners.values():
                        if owner.worker is not None and owner.worker.is_alive():self.stop_fixture_worker(owner)
            self.provider_release.set()
            for server,thread in reversed(self.servers):server.shutdown();server.server_close();thread.join(3)
            # Production correctly refuses Close for unresolved generic provider
            # effects. Dispose only the test-owned handles after actual joins.
            if self.workspace is not None:
                ws=self.workspace
                schemas=[ws.db.schema]
                if ws._projection is not None:
                    schemas.append(ws._projection.db.schema)
                    ws._projection.artifacts.close();ws._projection.db.close()
                if ws._store is not None:ws._store.close()
                for _path,descriptor in ws._roots.values():os.close(descriptor)
                ws._roots.clear();ws.db.close();ws._closed=True
                with psycopg.connect(connection_info(),autocommit=True) as connection:
                    for schema in schemas:connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            self.assertTrue(all(isinstance(error,(WorkbenchError,ValueError)) for error in self.worker_errors),self.worker_errors)
        finally:
            threading.excepthook=self.previous_hook
            self.flag.stop();self.temp.cleanup()
