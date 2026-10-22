"""Finite runtime transport checks; inventory/copy custody is owned elsewhere."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import agent_api as api
import project_cli
import project_dispatch
from tuldok_client import ProjectFilesClient
from test_project_files_m4_clients import ready,bound,READ,WRITE,PROJECT,ACTOR,CP,NEXT,KEY,STAMP

ACTIONS=('runtime_sources','runtime_inspect','runtime_capture','runtime_status')


def inspection():
    return dict(format='project_runtime_inspection_v1',source='configured-cpu',inventory_sha256=CP,
        profile='captured_cpu_python_v1',python_version='3.12',file_count=1,total_bytes=1,manifest_bytes=400,free_bytes=1000,
        packages=[{'name':'numpy','version':'0.0'},{'name':'torch','version':'0.0'}],
        launch=dict(python='python/bin/python3.12',loader='system/lib/ld.so',home='python',stdlib='python/lib/python3.12',
            dynload='python/lib/python3.12/lib-dynload',packages='packages',library_dirs=['system/lib']),
        files=dict(items=[dict(path='python/bin/python3.12',bytes=1,sha256=CP,mode=0o500,kind='elf')],offset=0,limit=40,total=1))


def summary(complete=False):
    value=dict(format='project_runtime_capture_v1' if complete else 'project_runtime_capture_intent_v1',
        project_id=PROJECT,manifest_sha256=CP,file_count=1,total_bytes=1,actor_id=ACTOR,observed_at=STAMP,request_key=KEY)
    if complete:value['runtime_ref']=dict(kind='runtime',catalog_id=PROJECT,id=NEXT,sha256=NEXT)
    return value


def client(value):
    result=ready(dict(status=200,result=bound(value)),owner=True)
    result._selected={**result._selected,**{'project_files.'+action:1 for action in ACTIONS}}
    return result


class RuntimeClients(unittest.TestCase):
    def test_native_bounds_fixed_consumers_and_alias_only_current_configuration(self):
        import runtime_snapshots as native
        import recipe_process
        self.assertEqual((native.MAX_FILES,native.MAX_FILE_BYTES,native.MAX_BYTES,native.MAX_MANIFEST),
                         (40000,512*1024*1024,2*1024*1024*1024,16*1024*1024))
        op=api.operation('project_files.runtime_inspect')['outputSchema']['oneOf'][0]['properties']['result']['properties']['value']['properties']
        self.assertEqual(op['file_count']['maximum'],native.MAX_FILES)
        self.assertEqual(op['total_bytes']['maximum'],native.MAX_BYTES)
        self.assertEqual(op['manifest_bytes']['maximum'],native.MAX_MANIFEST)
        self.assertEqual(op['files']['properties']['items']['items']['properties']['bytes']['maximum'],native.MAX_FILE_BYTES)
        self.assertEqual(op['files']['properties']['items']['items']['properties']['path']['maxLength'],1024)
        self.assertTrue(recipe_process._cpu_relative('x'*1024));self.assertFalse(recipe_process._cpu_relative('x'*1025))
        for action in ACTIONS:
            self.assertIn('project_files.'+action,api.PROJECT_FILES_M3)
            self.assertTrue(callable(getattr(ProjectFilesClient(Mock()),action)))
            project_cli.parser().parse_args(['--config','/not-read','file-'+action.replace('_','-'),'--arguments','/not-read'])
        for change in ({'source':'/absolute/path'},{'source':'x'*65},{'configuration':{'python_root':'/tmp'}}):
            with self.assertRaises(api.AgentAPIError):
                api.validate_arguments('project_files.runtime_capture',{**WRITE,'source':'configured-cpu','expected_inventory_sha256':CP,**change})
        self.assertEqual(api.contract('project_files.runtime_capture')['authority'],'owner')
        self.assertEqual(api.contract('project_files.runtime_status')['authority'],'agent')

    def test_inventory_nested_page_and_capture_exact_receipt_are_correlated(self):
        value=inspection();raw=client(value);sdk=ProjectFilesClient(raw)
        sdk.runtime_inspect(**READ,source='configured-cpu')
        for change in ({'source':'another'},{'file_count':2}):
            raw._request.return_value=dict(status=200,result=bound(dict(value,**change)))
            with self.assertRaises(api.AgentAPIError):sdk.runtime_inspect(**READ,source='configured-cpu')
        corrupt=copy.deepcopy(value);corrupt['files']['offset']=1
        raw._request.return_value=dict(status=200,result=bound(corrupt))
        with self.assertRaises(api.AgentAPIError):sdk.runtime_inspect(**READ,source='configured-cpu')
        raw._request.return_value=dict(status=200,result=bound(summary(True),NEXT))
        sdk.runtime_capture(**WRITE,source='configured-cpu',expected_inventory_sha256=CP,reserve_bytes=0)
        for change in ({'request_key':'another-key'},{'manifest_sha256':NEXT},{'project_id':ACTOR}):
            raw._request.return_value=dict(status=200,result=bound(dict(summary(True),**change),NEXT))
            with self.assertRaises(api.AgentAPIError):sdk.runtime_capture(**WRITE,source='configured-cpu',expected_inventory_sha256=CP)

    def test_retained_status_never_conflates_capture_with_current_readiness(self):
        value=dict(state='captured',intent=summary(),result=summary(True));raw=client(value);sdk=ProjectFilesClient(raw)
        self.assertEqual(sdk.runtime_status(**READ,capture_key=KEY)['value'],value)
        for change in ({'state':'absent'},{'intent':None},{'result':dict(summary(True),request_key='other-key')},
                       {'result':dict(summary(True),file_count=2)},{'local_ready':True}):
            raw._request.return_value=dict(status=200,result=bound(dict(value,**change)))
            with self.assertRaises(api.AgentAPIError):sdk.runtime_status(**READ,capture_key=KEY)

    def test_dispatch_preserves_alias_only_owner_request_and_bounded_native_projection(self):
        runtime=Mock();current=inspection();runtime.inspect.return_value={
            **{field:current[field] for field in ('inventory_sha256','file_count','total_bytes','manifest_bytes','free_bytes')},
            'manifest':{'profile':current['profile'],'python_version':current['python_version'],'packages':{'numpy':'0.0','torch':'0.0'},
                        'launch':current['launch'],'files':current['files']['items']}}
        projection=SimpleNamespace(session=SimpleNamespace(access=SimpleNamespace(require=Mock())),runtime=runtime,
            runtime_sources=Mock(return_value={'sources':['configured-cpu']}))
        result=project_dispatch.dispatch(projection,'project_files.runtime_inspect',dict(READ,source='configured-cpu'))
        self.assertEqual(result,current);runtime.inspect.assert_called_once_with({'source':'configured-cpu'})
        project_dispatch.dispatch(projection,'project_files.runtime_capture',dict(WRITE,source='configured-cpu',expected_inventory_sha256=CP))
        runtime.capture.assert_called_once_with({'source':'configured-cpu'},CP,CP,KEY)
        project_dispatch.dispatch(projection,'project_files.runtime_status',dict(READ,capture_key=KEY))
        runtime.status.assert_called_once_with(KEY)


if __name__=='__main__':unittest.main()
