"""Five fixed owner extraction contracts and explicit authority handoff.

Controlled replies qualify client refusal/correlation. Actual source ownership,
stop and extraction are exercised by controller and public HTTP tests elsewhere.
"""
import copy
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

import agent_api as api
import project_cli
from tuldok_client import ProjectTransferClient

SOURCE,CONTROL,BINDING,NEXT_BINDING,PROJECT=(c*32 for c in 'abcdf')
SHA,OTHER='e'*64,'f'*64
TOKEN='fixture-only-transfer-owner-token'


def source():return dict(catalog_id=SOURCE,schema_version=10,catalog_signature=SHA,snapshot_sha256=SHA,
    backup_receipt_sha256=None,external_inventory_sha256=SHA)


def state(stopped=False):
    return dict(format='project_transfer_state_v1',binding=NEXT_BINDING if stopped else BINDING,
        phase='source_stopped' if stopped else 'source_live',source_catalog_id=SOURCE,control_catalog_id=CONTROL,
        roots=['output'],available_actions=['status','preview','report_page'],report=None,
        backup=dict(root='output',directory='backup',receipt_sha256=SHA) if stopped else None,
        destination=dict(root='output',directory='extracted') if stopped else None,failure=None,last_receipt=None)


def receipt():
    return dict(format='project_transfer_receipt_v1',committed=True,project_id=PROJECT,checkpoint=OTHER,request_key='k',
        input_sha256=SHA,report_sha256=SHA,source=dict(source(),backup_receipt_sha256=SHA),
        artifacts=dict(copied_count=1,missing_regenerable_count=0),verification=dict(checkpoint=OTHER,active_data_records=1),replayed=False)


def result():
    return dict(format='project_transfer_extraction_result_v1',binding=NEXT_BINDING,receipt=receipt(),
        selection=dict(selected=False,state=None,error=dict(code='project_selection_unavailable',detail='Published; explicit Open required.')))


def ready(value,catalog=CONTROL):
    client=api.ProjectTransferOwnerClient('http://127.0.0.1:12345',TOKEN,catalog)
    client._ready=True;client._selected={name:1 for name in api.PROJECT_TRANSFER_OPERATIONS}
    client._request=Mock(return_value={'status':200,'result':value})
    return client


class TransferClients(unittest.TestCase):
    def test_five_closed_operations_and_default_unavailable_profiles(self):
        self.assertEqual(api.PROJECT_TRANSFER_OPERATIONS,api.ProjectTransferOwnerClient.OPERATIONS)
        for profile in ('catalog','project'):
            manifest=api.capabilities(SOURCE,profile=profile)
            found=[op for op in manifest['operations'] if op['id'] in api.PROJECT_TRANSFER_OPERATIONS]
            self.assertEqual(len(found),5);self.assertTrue(all(op['availability']=='unavailable' for op in found))
            self.assertLessEqual(len(api.encoded(manifest)),api.CAPABILITIES_LIMIT)
        for name in api.PROJECT_TRANSFER_OPERATIONS:
            self.assertTrue(callable(getattr(ProjectTransferClient(Mock()),name.split('.')[1])))
            self.assertEqual(api.contract(name)['authority'],'owner')
            self.assertEqual(api.contract(name)['bounds']['response_bytes'],1048576)
        selection=dict(project_snapshot=dict(id=SOURCE,manifest_sha256=SHA),roots={'records':[PROJECT]},decisions=[])
        api.validate_arguments('project_transfer.preview',dict(binding=BINDING,selection=selection))
        for bad in (dict(selection,credential='forbidden'),dict(selection,stopped_source_lease={}),
                    dict(selection,roots={'arbitrary_files':['/etc/passwd']})):
            with self.assertRaises(api.AgentAPIError):api.validate_arguments('project_transfer.preview',dict(binding=BINDING,selection=bad))
        for directory in ('../escape','a/b','a\\b','.','..','bad\nname'):
            with self.assertRaises(api.AgentAPIError):api.validate_arguments('project_transfer.extract',dict(binding=NEXT_BINDING,report_sha256=SHA,
                destination_root='output',directory=directory,name='Extracted',request_key='k'))

    def test_owner_bootstrap_limits_tools_and_stop_requires_independent_new_client(self):
        client=api.ProjectTransferOwnerClient('http://127.0.0.1:12345',TOKEN,SOURCE)
        def request(method,path,body=None,**kwargs):
            if path=='/api/access/session':value=dict(kind='owner',catalog_id=SOURCE)
            elif path=='/api/workspace/context':value=dict(dataset_id=SOURCE)
            elif path=='/api/agent/capabilities':
                value=api.capabilities(SOURCE)
                for op in value['operations']:
                    if op['id'] in api.PROJECT_TRANSFER_OPERATIONS:op['availability']='available'
            else:value=state(True)
            return dict(status=200,result=value)
        client._request=Mock(side_effect=request)
        self.assertEqual(set(client.bootstrap()['operations']),api.PROJECT_TRANSFER_OPERATIONS)
        self.assertEqual({t['name'] for t in client.tool_definitions()},{name.replace('.','_') for name in api.PROJECT_TRANSFER_OPERATIONS})
        count=client._request.call_count
        with self.assertRaises(api.AgentAPIError):client.call('project_files.open',{})
        self.assertEqual(client._request.call_count,count)
        stopped=ProjectTransferClient(client).stop(binding=BINDING,report_sha256=SHA,backup_root='output',backup_directory='backup',destination_root='output',directory='extracted')
        self.assertEqual(stopped['phase'],'source_stopped');count=client._request.call_count
        with self.assertRaises(api.AgentAPIError) as failure:ProjectTransferClient(client).status()
        self.assertEqual(failure.exception.code,'authentication_handoff');self.assertEqual(client._request.call_count,count)
        control=ready(state(True));self.assertEqual(ProjectTransferClient(control).status(),stopped)
        wrong=ready(state(True),catalog=SOURCE)
        with self.assertRaises(api.AgentAPIError):ProjectTransferClient(wrong).status()

    def test_paged_report_and_published_unselected_receipt_correlate_without_retry(self):
        page=dict(format='project_transfer_report_page_v1',binding=NEXT_BINDING,report_sha256=SHA,section='included',
            items=[dict(family='workbench_record',id=PROJECT,revision=1)],offset=0,limit=40,total=1)
        client=ready(page);sdk=ProjectTransferClient(client)
        sdk.report_page(binding=NEXT_BINDING,report_sha256=SHA,section='included')
        for change in ({'binding':BINDING},{'report_sha256':OTHER},{'section':'unassigned'},{'offset':1},{'total':41}):
            client._request.return_value=dict(status=200,result=dict(page,**change))
            with self.assertRaises(api.AgentAPIError):sdk.report_page(binding=NEXT_BINDING,report_sha256=SHA,section='included')
        args=dict(binding=NEXT_BINDING,report_sha256=SHA,destination_root='output',directory='extracted',name='Extracted',request_key='k')
        client._request.return_value=dict(status=200,result=result());self.assertFalse(sdk.extract(**args)['selection']['selected'])
        bad=result();bad['receipt']['request_key']='other';client._request.return_value=dict(status=200,result=bad)
        with self.assertRaises(api.AgentAPIError):sdk.extract(**args)
        bad=result();bad['selection']['selected']=True;client._request.return_value=dict(status=200,result=bad)
        with self.assertRaises(api.AgentAPIError):sdk.extract(**args)
        client._request.return_value=dict(status=503,result={'code':'unknown','error':'Inspect explicit current status.'});before=client._request.call_count
        with self.assertRaises(api.AgentAPIError):sdk.extract(**args)
        self.assertEqual(client._request.call_count,before+1)

    def test_real_http_preserves_only_exact_partial_receipt_and_enforces_one_mib(self):
        partial=dict(committed=True,selected=False,project_id=PROJECT,checkpoint=OTHER,request_key='k',directory='extracted')
        value=dict(code='unknown',error='Published; inspect exact destination.',receipt=partial);oversized=False
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length','0')));raw=api.encoded(value)
                self.send_response(503);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(1048577 if oversized else len(raw)));self.end_headers()
                if not oversized:self.wfile.write(raw)
            def log_message(self,*_):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(thread.join,5);self.addCleanup(server.shutdown)
        client=api.ProjectTransferOwnerClient(f'http://127.0.0.1:{server.server_port}',TOKEN,CONTROL)
        client._ready=True;client._selected={'project_transfer.extract':1}
        args=dict(binding=NEXT_BINDING,report_sha256=SHA,destination_root='output',directory='extracted',name='Extracted',request_key='k')
        with self.assertRaises(api.AgentAPIError) as failure:ProjectTransferClient(client).extract(**args)
        self.assertEqual(failure.exception.receipt,partial)
        value['receipt']=dict(partial,credential=TOKEN)
        with self.assertRaises(api.AgentAPIError) as failure:ProjectTransferClient(client).extract(**args)
        self.assertEqual(failure.exception.code,'transport')
        oversized=True
        with self.assertRaises(api.AgentAPIError) as failure:ProjectTransferClient(client).extract(**args)
        self.assertEqual(failure.exception.code,'response_too_large')

    def test_named_cli_selects_separate_owner_and_preserves_selection_document(self):
        with tempfile.TemporaryDirectory(prefix='transfer-cli-fixture-') as directory:
            selection=dict(project_snapshot=dict(id=SOURCE,manifest_sha256=SHA),roots={'records':[PROJECT]},decisions=[])
            file=Path(directory)/'selection.json';file.write_text(json.dumps(selection))
            client=Mock();client.call.return_value=dict(status=200,result=state())
            output=io.StringIO()
            with (patch.object(project_cli.ProjectTransferOwnerClient,'from_config',return_value=client) as constructor,
                  patch('sys.stdout',output)):
                code=project_cli.main(['--config','/not-read','project-transfer','preview','--binding',BINDING,'--selection',str(file)])
            self.assertEqual(code,0);constructor.assert_called_once()
            self.assertEqual(client.call.call_args.args[:2],('project_transfer.preview',dict(binding=BINDING,selection=selection)))
            self.assertEqual(json.loads(output.getvalue()),state())


if __name__=='__main__':unittest.main()
