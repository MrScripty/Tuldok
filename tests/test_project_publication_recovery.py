"""Real committed-stage recovery preserves bytes and never reconstructs sources."""
import errno
import os
import shutil
import unittest
from unittest.mock import patch

from project_composition import composition_input
from project_fork import recover_committed_publication
from project_store import ProjectStore, ProjectStoreError
from project_files import file_id, materialize_captured
from test_project_composition_publication import CompositionPublicationTests


class PublicationRecoveryTests(unittest.TestCase):
    setUp=CompositionPublicationTests.setUp
    publish=CompositionPublicationTests.publish
    assert_code=CompositionPublicationTests.assert_code

    def stage(self):
        with patch('project_fork._rename_noreplace',side_effect=OSError(errno.EIO,'interrupted before rename')):
            self.assert_code('unavailable',self.publish)
        self.staging=next(self.root.glob('.tuldok-fork-*'))
        with ProjectStore.open(self.staging) as store:
            self.committed=store.snapshot()
        self.request=composition_input(self.snapshots,'combined','Combined','compose-exact')

    def recover(self,**changes):
        args=dict(root_path=self.root,expected_project_id=self.committed['project_id'],
                  expected_checkpoint=self.committed['checkpoint'],expected_request=self.request,quiescent=True)
        args.update(changes)
        return recover_committed_publication(self.fd,self.staging.name,'combined',**args)

    def test_committed_stage_recovers_without_sources_payload_copies_or_new_identity(self):
        self.stage()
        before={p.name:(p.read_bytes(),p.stat().st_ino) for p in (self.staging/'artifacts/sha256').iterdir()}
        for store,artifacts in zip(self.stores,self.artifacts):
            artifacts.close();store.close();shutil.rmtree(store.path)
        with patch('project_artifacts.ProjectArtifacts.copy_many_to',side_effect=AssertionError('No recopy')), \
                patch('project_composition.build_candidate',side_effect=AssertionError('No rebuild')):
            result=self.recover()
        self.assertFalse(self.staging.exists())
        self.assertEqual(result['payloads_copied'],0)
        self.assertFalse(result['selected'])
        with ProjectStore.open(self.root/'combined') as store:
            self.assertEqual(store.snapshot(),self.committed)
        after={p.name:(p.read_bytes(),p.stat().st_ino) for p in (self.root/'combined/artifacts/sha256').iterdir()}
        self.assertEqual(before,after)
        self.assertTrue(self.recover()['reconciled'])

    def test_wrong_request_checkpoint_or_identity_never_publishes(self):
        self.stage()
        self.assert_code('stale',lambda:self.recover(expected_checkpoint='0'*64))
        self.assert_code('stale',lambda:self.recover(expected_project_id='0'*32))
        self.assert_code('conflict',lambda:self.recover(expected_request={**self.request,'name':'Changed'}))
        self.assert_code('busy',lambda:self.recover(quiescent=False))
        self.assertTrue(self.staging.exists());self.assertFalse((self.root/'combined').exists())

    def test_missing_copied_payload_preserves_stage_and_refuses_publication(self):
        self.stage();next((self.staging/'artifacts/sha256').iterdir()).unlink()
        with self.assertRaises(ProjectStoreError):self.recover()
        self.assertTrue(self.staging.exists());self.assertFalse((self.root/'combined').exists())

    def test_destination_appearance_never_overwrites_either_tree(self):
        self.stage();(self.root/'combined').mkdir();(self.root/'combined/unique').write_bytes(b'keep')
        self.assert_code('conflict',self.recover)
        self.assertTrue(self.staging.exists());self.assertEqual((self.root/'combined/unique').read_bytes(),b'keep')

    def test_lost_rename_ack_reconciles_exact_published_checkpoint(self):
        self.stage();fsync=os.fsync
        def fail_after_publish(fd):
            if (self.root/'combined').exists():raise OSError(errno.EIO,'lost publication acknowledgement')
            fsync(fd)
        with patch('project_fork.os.fsync',side_effect=fail_after_publish):
            self.assert_code('unknown',self.recover)
        self.assertFalse(self.staging.exists());self.assertTrue(self.recover()['reconciled'])

    def test_live_writer_and_non_stage_path_are_refused(self):
        self.stage()
        with ProjectStore.open(self.staging):
            self.assert_code('busy',self.recover)
        self.assert_code('invalid',lambda:recover_committed_publication(self.fd,'source0','combined',
            root_path=self.root,expected_project_id=self.committed['project_id'],expected_checkpoint=self.committed['checkpoint'],
            expected_request=self.request,quiescent=True))

    def test_initial_empty_stage_cannot_be_mistaken_for_committed_publication(self):
        self.stage();empty_name='.tuldok-fork-'+'9'*32
        with ProjectStore.create(self.root/empty_name,'Uncommitted','initial','a'*64) as store:
            initial=store.snapshot()
        self.assert_code('invalid',lambda:recover_committed_publication(self.fd,empty_name,'combined',
            root_path=self.root,expected_project_id=initial['project_id'],expected_checkpoint=initial['checkpoint'],
            expected_request=self.request,quiescent=True))
        self.assertTrue((self.root/empty_name).exists());self.assertFalse((self.root/'combined').exists())

    def test_missing_captured_working_file_refuses_without_changing_committed_history(self):
        # Seed a real current note before composing; its cloned editable record
        # and materialized bytes then pass through the normal publication path.
        from datetime import datetime, timezone
        import hashlib
        store=self.stores[0];snap=store.snapshot();raw=b'original note\n'
        version=dict(revision=1,text=raw.decode(),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                     actor_id='1'*32,adopted_at=datetime.now(timezone.utc).isoformat())
        doc=dict(format='project_file_v1',project_id=snap['project_id'],kind='note',path='notes/test.md',
                 current=version,history=[version],origin=None)
        record=dict(family='project_file',id=file_id(snap['project_id'],'note','notes/test.md'),document=doc)
        self.snapshots[0]=store.commit([*snap['records'],record],snap['checkpoint'],'note','c'*64)
        with store.root_directory() as root:
            materialize_captured(self.snapshots[0]['records'],snap['project_id'],root)
        self.stage();(self.staging/'notes/test.md').unlink()
        self.assert_code('working_files_changed',self.recover)
        self.assertFalse((self.root/'combined').exists())
        with ProjectStore.open(self.staging) as retained:
            self.assertEqual(retained.snapshot(),self.committed)


if __name__=='__main__':unittest.main()
