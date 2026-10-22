"""Current Candidate preparation/recovery transport proof, without a writer."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import agent_api as api
import project_cli
import project_dispatch
from tuldok_client import ProjectFilesClient
from test_project_files_m4_clients import ready,bound,READ,WRITE,PROJECT,ACTOR,CP,NEXT,KEY,STAMP

STUDY='a'*32;CANDIDATE='e'*32
ACTIONS=('execution_study_prepare_package','execution_study_prepare_verifier','execution_study_abandon_preparation','execution_study_reconcile_preparation')
def prepared():
    return dict(state='prepared',candidate_id=CANDIDATE,trial=dict(format='trial_v1',id='b'*32,study_id=STUDY,
        material=dict(kind='recipe_material',catalog_id=PROJECT,id=CP,sha256=CP),replicate=0),
        graph=dict(id='f'*32,revision=1,nodes=[],edges=[]),model=dict(kind='model',catalog_id=PROJECT,id=ACTOR,revision=1,sha256=CP),runtime_snapshot_sha256=CP)
def abandonment():
    return dict(format='project_candidate_preparation_abandon_v1',origin_catalog_id=PROJECT,study_id=STUDY,
        preparation_key=KEY,preparation_operation='study_execution.prepare_package',input_sha256=CP,
        candidate=dict(kind='candidate',catalog_id=PROJECT,id=CANDIDATE,sha256=NEXT),actor_id=ACTOR,
        reason='Explicit retained scientific reason',observed_checkpoint=CP,occurred_at=STAMP,state='abandoned')
def client(value):
    raw=ready(dict(status=200,result=bound(value)),owner=True)
    raw._selected.update({'project_files.'+action:1 for action in ACTIONS});return raw
class CandidateClients(unittest.TestCase):
    def test_fixed_inputs_consumers_and_no_implicit_grant_or_admission(self):
        for action in ACTIONS:
            name='project_files.'+action;self.assertIn(name,api.PROJECT_FILES_M3)
            self.assertTrue(callable(getattr(ProjectFilesClient(Mock()),action)))
            project_cli.parser().parse_args(['--config','/not-read','file-'+action.replace('_','-'),'--arguments','/not-read'])
            self.assertEqual(api.contract(name)['authority'],'owner')
        common=dict(WRITE,study_id=STUDY,revision=1,candidate_id=CANDIDATE,root='fixture',directory='a'*120,runtime_snapshot_sha256=CP)
        api.validate_arguments('project_files.execution_study_prepare_package',common)
        for change in ({'directory':'a'*121},{'root':'a'*65},{'approval_id':ACTOR},{'launch':True}):
            with self.assertRaises(api.AgentAPIError):api.validate_arguments('project_files.execution_study_prepare_package',{**common,**change})
        args=dict(binding=READ['binding'],expected_checkpoint=CP,study_id=STUDY,preparation_key='k')
        api.validate_arguments('project_files.execution_study_reconcile_preparation',args)
        with self.assertRaises(api.AgentAPIError):api.validate_arguments('project_files.execution_study_reconcile_preparation',dict(args,request_key=KEY))
        self.assertEqual(api.contract('project_files.execution_study_reconcile_preparation')['retry'],'never')
    def test_exact_scientific_identity_and_recovery_reason_correlation(self):
        args=dict(WRITE,study_id=STUDY,revision=1,candidate_id=CANDIDATE,root='fixture',directory='package',runtime_snapshot_sha256=CP)
        raw=client(prepared());sdk=ProjectFilesClient(raw);sdk.execution_study_prepare_package(**args)
        for field,bad in (('candidate_id',ACTOR),('runtime_snapshot_sha256',NEXT)):
            raw._request.return_value=dict(status=200,result=bound(dict(prepared(),**{field:bad})))
            with self.assertRaises(api.AgentAPIError):sdk.execution_study_prepare_package(**args)
        raw._request.return_value=dict(status=200,result=bound(abandonment()))
        sdk.execution_study_abandon_preparation(**dict(WRITE,request_key='new-abandon-key'),study_id=STUDY,preparation_key=KEY,reason=abandonment()['reason'])
        raw._request.return_value=dict(status=200,result=bound(dict(abandonment(),reason='different')))
        with self.assertRaises(api.AgentAPIError):sdk.execution_study_abandon_preparation(**dict(WRITE,request_key='new-abandon-key'),study_id=STUDY,preparation_key=KEY,reason=abandonment()['reason'])
    def test_dispatch_exact_local_owner_and_reconciliation_has_no_second_key(self):
        owner=Mock();projection=SimpleNamespace(session=SimpleNamespace(access=SimpleNamespace(require=Mock())),execution=SimpleNamespace(study_execution=owner))
        args=dict(WRITE,study_id=STUDY,revision=1,candidate_id=CANDIDATE,root='fixture',directory='package',runtime_snapshot_sha256=CP)
        project_dispatch.dispatch(projection,'project_files.execution_study_prepare_package',args)
        owner.prepare_package.assert_called_once_with(STUDY,{k:v for k,v in args.items() if k not in ('binding','expected_checkpoint','request_key','study_id')},CP,KEY)
        args=dict(binding=READ['binding'],expected_checkpoint=CP,study_id=STUDY,preparation_key='k')
        project_dispatch.dispatch(projection,'project_files.execution_study_reconcile_preparation',args)
        owner.reconcile_preparation.assert_called_once_with(STUDY,{'preparation_key':'k'},CP)
if __name__=='__main__':unittest.main()
