"""Configured current-host runtime capture through real HTTP/PG, without execution."""
import hashlib
from http.server import ThreadingHTTPServer
import os
import shutil
import threading
import unittest
from unittest.mock import patch

from app import make_handler
from auth_helpers import ExplicitOwnerFixture
from project_workspace import ProjectWorkspace
import project_workspace
import test_project_files_http as m1
import test_project_files_m2_http as m2


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class ProjectRuntimeHTTP(unittest.TestCase):
    cleanup_owned=m1.ProjectFilesHTTP.cleanup_owned
    select_host=m1.ProjectFilesHTTP.select_host
    request=m1.ProjectFilesHTTP.request
    state=m1.ProjectFilesHTTP.state
    envelope=m1.ProjectFilesHTTP.envelope
    action=m1.ProjectFilesHTTP.action
    create=m1.ProjectFilesHTTP.create
    arguments=m2.ProjectFilesM2HTTP.arguments
    transport=m2.ProjectFilesM2HTTP.transport
    call=m2.ProjectFilesM2HTTP.call

    def setUp(self):
        self.operations=[];m1.ProjectFilesHTTP.setUp(self)
        self.enterContext(patch.object(project_workspace,'M3_ENABLED',True))
        python=self.path/'explicit-python';site=self.path/'explicit-packages'
        (python/'bin').mkdir(parents=True);(python/'lib/python3.12/lib-dynload').mkdir(parents=True)
        shutil.copyfile('/usr/bin/true',python/'bin/python3.12')
        (python/'lib/python3.12/lib-dynload/fixture.txt').write_text('Owned inert bytes')
        packages=[]
        for name in ('torch','numpy'):
            (site/name).mkdir(parents=True);(site/name/'__init__.py').write_text('raise AssertionError("Never import this fixture")\n')
            info=site/(name+'-0.0.dist-info');info.mkdir();(info/'METADATA').write_text('Name: '+name+'\nVersion: 0.0\n')
            (info/'LICENSE').write_text('Owned fixture');packages.extend([name,info.name])
        config=dict(schema_version=1,python_root=str(python),python_version='3.12',site_packages=str(site),packages=packages)
        dsn=os.environ['TULDOK_DATABASE_URL'];control=self.path/'configured-control'
        workspace=ProjectWorkspace(control,{'fixture':self.external},dsn=dsn,runtime_sources={'inert-fixture':config})
        self.schemas.append((dsn,workspace.db.schema));self.controls.append((dsn,control))
        owner=ExplicitOwnerFixture.bootstrap(workspace)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(workspace));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.hosts.append((workspace,server,thread));self.workspace,self.owner=workspace,owner
        self.origin='http://127.0.0.1:'+str(server.server_port)

    def test_configured_alias_actual_capture_and_cold_historical_status_never_execute(self):
        self.create()
        with patch('subprocess.Popen',side_effect=AssertionError('Runtime capture executed a child')):
            sources=self.call('runtime_sources');self.assertEqual(sources['items'],[{'source':'inert-fixture'}])
            inventory=self.call('runtime_inspect',source='inert-fixture',limit=1)
            self.assertEqual(len(inventory['files']['items']),1)
            arguments=self.arguments('runtime_capture',source='inert-fixture',
                expected_inventory_sha256=inventory['inventory_sha256'],reserve_bytes=0,request_key='actual-runtime-capture')
            status,response=self.transport('runtime_capture',arguments);self.assertEqual(status,200,response)
            captured=response['value'];self.assertEqual(captured['format'],'project_runtime_capture_v1')
            projection=self.workspace._projection
            receipts=[r['document'] for r in projection.session.snapshot['records'] if r['family']=='project_operation']
            self.assertTrue(any(r['operation']=='runtime.capture_intent' for r in receipts))
            self.assertTrue(any(r['operation']=='runtime.capture' for r in receipts))
            status,replay=self.transport('runtime_capture',arguments);self.assertEqual(status,200,replay)
            self.assertEqual(replay['value'],captured)
            self.action('close')
            self.select_host(self.path/'cold-control',{'fixture':self.external})
            self.action('open',root='fixture',directory='alpha')
            historical=self.call('runtime_status',capture_key='actual-runtime-capture')
            self.assertEqual(historical['state'],'captured');self.assertEqual(historical['result'],captured)
            self.assertEqual(self.call('runtime_sources')['items'],[])
            self.assertIsNone(self.workspace._projection.execution._runs)
            self.assertFalse((self.workspace._projection.db.path/'runtime-snapshots'/inventory['inventory_sha256']).exists())
            before=self.workspace._projection.session.snapshot
            status,error=self.transport('runtime_inspect',self.arguments('runtime_inspect',source='inert-fixture'))
            self.assertEqual(status,409,error);self.assertEqual(self.workspace._projection.session.snapshot,before)


if __name__=='__main__':unittest.main()
