"""Owner-authorized native composition, editable notes and selection recovery."""
import copy
import hashlib
import os
import unittest
from unittest.mock import patch

import agent_api
from access import AccessError
from project_artifacts import ProjectArtifacts
from project_composition import decode_records
from project_files import file_id
from project_store import ProjectStore
from workbench import WorkbenchError
from test_project_composition import approved_history
from test_project_workspace import ProjectWorkspaceTests


@unittest.skipUnless(os.environ.get('TULDOK_DATABASE_URL'),'Requires disposable PostgreSQL')
class CompositionWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=ProjectWorkspaceTests('test_lifecycle_replay_is_idempotent_only_while_resulting_state_is_current')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture;created,_=f.create();self.primary_id=created['project']['project_id']
        for revision,text in enumerate(('Original decision Ω\r\n','Updated decision Ω\r\n')):
            raw=text.encode();target=f.external/'alpha/notes/decision.md';target.parent.mkdir(exist_ok=True)
            target.write_bytes(raw)
            f.call('file_adopt',f.mutation(kind='note',path='notes/decision.md',expected_revision=revision,
                expected_sha256=hashlib.sha256(raw).hexdigest()))
        self.primary=f.workspace._store.snapshot()
        with ProjectStore.create(f.external/'retained','Retained source','create','a'*64) as store,ProjectArtifacts(store) as artifacts:
            records=approved_history();raw=b'reference input'
            artifacts.publish_bytes(raw,dict(format='project_artifact_v1',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
            self.secondary=store.commit(records,store.snapshot()['checkpoint'],'seed','b'*64)
        self.arguments=f.mutation(root='fixture',directory='combined',name='Combined scientific history',sources=[dict(
            root='fixture',directory='retained',project_id=self.secondary['project_id'],checkpoint=self.secondary['checkpoint'])])

    def compose(self):return self.fixture.call('compose',self.arguments)

    def test_native_owner_composition_preserves_note_history_and_selects_editable_primary_fork(self):
        f=self.fixture
        with patch('subprocess.Popen',side_effect=AssertionError('Imported projects never execute')):
            result=self.compose()
        state=result['state'];self.assertEqual(state['state'],'open')
        self.assertNotEqual(state['project']['project_id'],self.primary_id)
        self.assertEqual(result['sources'],[{key:s[key] for key in ('project_id','checkpoint')} for s in (self.primary,self.secondary)])
        snapshot=f.workspace._store.snapshot();identity=snapshot['project_id']
        decode_records(snapshot['records'],project_id=identity)
        old_note=next(r for r in self.primary['records'] if r['family']=='project_file')
        self.assertIn(old_note,snapshot['records']);self.assertEqual(len(old_note['document']['history']),2)
        adopted=file_id(identity,'note','notes/decision.md')
        value=f.call('file_get',dict(binding=state['binding'],checkpoint=state['project']['checkpoint'],file_id=adopted))['value']
        self.assertEqual(value['version']['text'],'Updated decision Ω\r\n')
        raw=b'Next independent decision\n';target=f.external/'combined/notes/decision.md';target.write_bytes(raw)
        updated=f.call('file_adopt',f.mutation(kind='note',path='notes/decision.md',expected_revision=value['version']['revision'],
            expected_sha256=hashlib.sha256(raw).hexdigest()))
        self.assertEqual(updated['value']['revision'],value['version']['revision']+1)
        agent_api.validate_output('project_files.compose',dict(status=200,result=result),version=1)

    def test_failed_selection_preserves_primary_and_exact_retry_reconciles_destination(self):
        f=self.fixture;project=f.workspace._projection_for
        def fail_new(store):
            if store.path.name=='combined':raise WorkbenchError('Bounded selection fixture failure.','unavailable',503)
            return project(store)
        with patch.object(f.workspace,'_projection_for',side_effect=fail_new),self.assertRaises(WorkbenchError) as caught:self.compose()
        self.assertEqual(caught.exception.code,'project_selection_unavailable')
        self.assertTrue(caught.exception.receipt['committed']);self.assertFalse(caught.exception.receipt['selected'])
        self.assertEqual(f.state()['project']['project_id'],self.primary_id)
        replay=self.compose();self.assertTrue(replay['fork']['reconciled'])
        self.assertEqual(replay['state']['project']['project_id'],caught.exception.receipt['project_id'])

    def test_wrong_secondary_checkpoint_is_rejected_before_destination_publication(self):
        self.arguments['sources'][0]['checkpoint']='0'*64
        with self.assertRaises(WorkbenchError) as caught:self.compose()
        self.assertEqual(caught.exception.code,'stale_project')
        self.assertFalse((self.fixture.external/'combined').exists())
        self.assertEqual(self.fixture.state()['project']['project_id'],self.primary_id)

    def test_anonymous_caller_is_denied_before_opening_retained_sources(self):
        with patch.object(ProjectStore,'open_at',side_effect=AssertionError('No unauthorized filesystem selection')):
            with self.assertRaises(AccessError) as caught:
                self.fixture.workspace.dispatch('project_files.compose',self.arguments)
        self.assertEqual(caught.exception.status,401)
        self.assertFalse((self.fixture.external/'combined').exists())


if __name__=='__main__':unittest.main()
