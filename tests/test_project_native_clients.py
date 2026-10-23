"""Finite native transport boundaries; no claim of native process execution."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import agent_api as api
import project_cli
import project_dispatch
from tuldok_client import ProjectFilesClient
from workbench import WorkbenchError
from test_project_files_m4_clients import ready,bound,READ,WRITE,PROJECT,ACTOR,CP,NEXT,KEY

GRAPH='1'*32;RUN='2'*32;PHASE='3'*32
ACTIONS=('native_preflight','native_submit','native_retry','native_reconcile')
def validation():
    return dict(status='valid',valid=True,errors=[],validation_token=CP,graph_revision=2,
                execution_sha256=NEXT,release={'id':CP},runtime={'available':True})
def phase():
    return dict(format='project_native_phase_v1',origin_catalog_id=PROJECT,phase_id=PHASE,
                phase='probe',run_id=None,state='failed',spec_sha256=CP,receipt_sha256=NEXT)
def admission():
    return dict(format='project_run_admission_v1',origin_catalog_id=PROJECT,run_id=RUN,request_sha256=NEXT)
def client(value,owner=True):
    raw=ready(dict(status=200,result=bound(value)),owner=owner)
    raw._selected.update({'project_files.'+name:1 for name in ACTIONS});return raw

class NativeClients(unittest.TestCase):
    def test_four_closed_operations_current_owner_and_named_consumers(self):
        for action in ACTIONS:
            name='project_files.'+action
            self.assertIn(name,api.PROJECT_FILES_M3);self.assertIn(name,project_dispatch.SUPPORTED_OPERATIONS)
            self.assertEqual(api.contract(name)['authority'],'owner')
            self.assertEqual(api.contract(name)['scopes'],['inspect','cancel' if action=='native_reconcile' else 'execute'])
            self.assertTrue(callable(getattr(ProjectFilesClient(Mock()),action)))
            project_cli.parser().parse_args(['--config','/not-read','file-'+action.replace('_','-'),'--arguments','/not-read'])
        args=dict(WRITE,graph_id=GRAPH,revision=2)
        api.validate_arguments('project_files.native_preflight',args)
        for change in ({'runtime_snapshot_sha256':CP},{'cache':{}},{'serialized_validation':validation()},{'command':['python']}):
            with self.assertRaises(api.AgentAPIError):api.validate_arguments('project_files.native_preflight',{**args,**change})
        args=dict(binding=READ['binding'],expected_checkpoint=CP,phase_id=PHASE)
        api.validate_arguments('project_files.native_reconcile',args)
        with self.assertRaises(api.AgentAPIError):api.validate_arguments('project_files.native_reconcile',dict(args,request_key=KEY))
        self.assertEqual(api.contract('project_files.native_reconcile')['retry'],'never')
        raw=client(validation(),owner=False);raw._selected.pop('project_files.native_preflight')
        with self.assertRaises(api.AgentAPIError):raw.call('project_files.native_preflight',dict(WRITE,graph_id=GRAPH,revision=2))
        raw._request.assert_not_called()

    def test_validation_admission_and_original_phase_identity_are_correlated(self):
        raw=client(validation());sdk=ProjectFilesClient(raw);args=dict(WRITE,graph_id=GRAPH,revision=2)
        sdk.native_preflight(**args)
        for change in ({'graph_revision':3},{'validation_token':None},{'valid':False},{'cache':{}},{'phase_ref':dict(phase(),origin_catalog_id=ACTOR)}):
            raw._request.return_value=dict(status=200,result=bound(dict(validation(),**change)))
            with self.assertRaises(api.AgentAPIError):sdk.native_preflight(**args)
        raw._request.return_value=dict(status=200,result=bound(admission()))
        sdk.native_submit(**WRITE,graph_id=GRAPH,graph_revision=2,validation_token=CP)
        raw._request.return_value=dict(status=200,result=bound(dict(admission(),origin_catalog_id=ACTOR)))
        with self.assertRaises(api.AgentAPIError):sdk.native_retry(**WRITE,run_id=RUN)
        raw._request.return_value=dict(status=200,result=bound(admission()))
        with self.assertRaises(api.AgentAPIError):sdk.native_retry(**WRITE,run_id=RUN)
        raw._request.return_value=dict(status=200,result=bound(phase()))
        sdk.native_reconcile(binding=READ['binding'],expected_checkpoint=CP,phase_id=PHASE)
        for change in ({'phase_id':GRAPH},{'origin_catalog_id':ACTOR},{'state':'running'},{'grant':{}}):
            raw._request.return_value=dict(status=200,result=bound(dict(phase(),**change)))
            with self.assertRaises(api.AgentAPIError):sdk.native_reconcile(binding=READ['binding'],expected_checkpoint=CP,phase_id=PHASE)

    def test_preflight_truth_fields_refuse_contradictions_and_nonstring_hashes(self):
        args=dict(WRITE,graph_id=GRAPH,revision=2);raw=client(validation());sdk=ProjectFilesClient(raw)
        failure=dict(status='unavailable',valid=False,errors=[dict(path='',message='Current CPU is unavailable',code='unavailable')],validation_token=None,release=None,runtime={'available':False})
        invalid=[
            dict(status='invalid',valid=True,errors=[7],release=None,runtime=None),
            dict(status='invalid'),dict(errors=[dict(path='runtime',message='Unavailable',code='unavailable')]),
            dict(release=None),dict(runtime=None),dict(runtime={'available':False}),dict(runtime={'available':1}),
            dict(valid=False,status='invalid',errors=[],validation_token=None),
            dict(failure,errors=[7]),dict(failure,status='other'),dict(failure,errors=[dict(path='',message='bad',code='unavailable',extra=True)]),
            dict(failure,errors=[dict(path=7,message='bad',code='unavailable')]),
            dict(failure,errors=[dict(path='',message='x'*2001,code='unavailable')]),
            dict(failure,errors=failure['errors']*101),
            dict(execution_sha256=int('7'*64)),dict(validation_token=int('7'*64)),
            dict(execution_sha256=True),dict(validation_token=True),
        ]
        for change in invalid:
            with self.subTest(change=change):
                raw._request.return_value=dict(status=200,result=bound(dict(validation(),**change)))
                with self.assertRaises(api.AgentAPIError) as caught:sdk.native_preflight(**args)
                self.assertEqual(caught.exception.code,'transport')
        for value in (validation(),dict(validation(),**failure)):
            raw._request.return_value=dict(status=200,result=bound(value));self.assertEqual(sdk.native_preflight(**args)['value'],value)

    def test_dispatch_uses_only_four_fixed_current_execution_seams(self):
        owner=Mock();projection=SimpleNamespace(session=SimpleNamespace(access=SimpleNamespace(require=Mock())),execution=owner)
        project_dispatch.dispatch(projection,'project_files.native_preflight',dict(WRITE,graph_id=GRAPH,revision=2))
        owner.native_preflight.assert_called_once_with(GRAPH,2,CP,KEY)
        project_dispatch.dispatch(projection,'project_files.native_submit',dict(WRITE,graph_id=GRAPH,graph_revision=2,validation_token=NEXT))
        owner.native_submit.assert_called_once_with(dict(graph_id=GRAPH,graph_revision=2,validation_token=NEXT),CP,KEY)
        project_dispatch.dispatch(projection,'project_files.native_retry',dict(WRITE,run_id=RUN));owner.native_retry.assert_called_once_with(RUN,CP,KEY)
        project_dispatch.dispatch(projection,'project_files.native_reconcile',dict(binding=READ['binding'],expected_checkpoint=CP,phase_id=PHASE));owner.native_reconcile.assert_called_once_with(PHASE,CP)

    def test_health_v2_adds_independent_bounded_current_phase_page_preserving_v1(self):
        self.assertEqual(api.contract('project_files.execution_health',1)['sha256'],'c3b1d0017f5a49cf69c3a4c5c33e1d3db9846404d12627563d97ef40de7404a5')
        legacy=dict(format='project_execution_health_v1',active_run_ids=[],active_count=0,offset=1,limit=1,local_owner_active=False,available=False,drain_required=True)
        value=dict(legacy,native_phases=dict(items=[phase()],total=2,offset=1,limit=1))
        raw=client(value);raw._selected['project_files.execution_health']=2;sdk=ProjectFilesClient(raw)
        sdk.execution_health(**READ,offset=1,limit=1)
        for change in ({'offset':0},{'total':1},{'items':[dict(phase(),origin_catalog_id=ACTOR)]}):
            raw._request.return_value=dict(status=200,result=bound(dict(value,native_phases={**value['native_phases'],**change})))
            with self.assertRaises(api.AgentAPIError):sdk.execution_health(**READ,offset=1,limit=1)
        raw._selected['project_files.execution_health']=1
        raw._request.return_value=dict(status=200,result=bound(legacy));sdk.execution_health(**READ,offset=1,limit=1)
        raw._request.return_value=dict(status=200,result=bound(value))
        with self.assertRaises(api.AgentAPIError):sdk.execution_health(**READ,offset=1,limit=1)

    def test_recipe_kind_is_inferred_and_contradictory_selector_refuses_before_effects(self):
        import pipeline
        pipelines=Mock();materials=Mock()
        projection=SimpleNamespace(session=SimpleNamespace(access=SimpleNamespace(require=Mock())),materials=materials,
            context=SimpleNamespace(models=Mock(),pipelines=pipelines),runtime_manifest=Mock())
        args=dict(WRITE,graph_id=GRAPH,revision=2,model={'kind':'model','catalog_id':PROJECT,'id':ACTOR,'revision':1,'sha256':CP})
        for recipe,builtin in (('external_recipe',False),(pipeline.MODEL_RECIPES[0] if isinstance(pipeline.MODEL_RECIPES,tuple) else next(iter(pipeline.MODEL_RECIPES)),True)):
            pipelines.get.return_value={'id':GRAPH,'recipe':recipe};materials.reset_mock()
            project_dispatch.dispatch(projection,'project_files.recipe_prepare',args)
            self.assertIs(materials.prepare_recipe.call_args.kwargs['builtin'],builtin)
            materials.reset_mock()
            with self.assertRaises(WorkbenchError) as failure:project_dispatch.dispatch(projection,'project_files.recipe_prepare',dict(args,builtin=not builtin))
            self.assertEqual(failure.exception.code,'conflict')
            materials.prepare_recipe.assert_not_called()
        pipelines.get.return_value={'id':GRAPH,'recipe':'release_validation'};materials.reset_mock()
        with self.assertRaises(WorkbenchError) as failure:project_dispatch.dispatch(projection,'project_files.recipe_prepare',args)
        self.assertEqual(failure.exception.code,'unsupported')
        materials.prepare_recipe.assert_not_called()

if __name__=='__main__':unittest.main()
