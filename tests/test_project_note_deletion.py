"""Explicit note absence is canonical history, never a filesystem delete command."""
import copy
import hashlib
import os
import shutil
import unittest
import uuid
from unittest.mock import patch

from access import AccessError
from project_artifacts import ProjectArtifacts
from project_files import ProjectFiles, decode_records, file_id, validate_operation_result
from project_fork import publish_fork
from project_fork_composition import build_candidate
from project_session import ProjectSession
from project_store import ProjectStore
from workbench import WorkbenchError, timestamp
import test_project_files as fixture


class NoteDeletionTests(unittest.TestCase):
    setUp=fixture.ProjectFilesTests.setUp
    adopt=fixture.ProjectFilesTests.adopt

    def deletion_body(self,result):
        return {key:result[key] for key in ('path',)} | dict(expected_revision=result['revision'],expected_sha256=result['sha256'])

    def remove_note(self,path='notes/decision.md',text='Exact original note\r\n'):
        result=self.adopt(path,text,kind='note')
        (self.root/path).unlink()
        body=self.deletion_body(result)
        deleted=self.files.adopt_deletion(body,self.session.snapshot['checkpoint'],'delete-note')
        return result,body,deleted

    def test_real_pg_deletion_cold_copy_fork_absence_and_explicit_restore_keep_exact_history(self):
        first=self.adopt('notes/decision.md','First cafe\u0301 😀\r\n',kind='note')
        second=self.adopt('notes/decision.md','Second exact note\n',1,'note')
        original=self.files.history(first['id'])
        before=copy.deepcopy(self.session.snapshot)
        (self.root/'notes/decision.md').unlink()
        deleted=self.files.adopt_deletion(self.deletion_body(second),before['checkpoint'],'delete-note')
        self.assertEqual(deleted['revision'],3);self.assertTrue(deleted['deleted'])
        self.assertIsNone(deleted['sha256']);self.assertEqual(deleted['bytes'],0)
        self.assertTrue(validate_operation_result('files.adopt_deletion',deleted,self.session.snapshot['records']))
        self.assertEqual(self.files.history(first['id'])[:2],original)
        self.assertEqual(self.files.read(first['id'],1)['version'],original[0])
        self.assertNotIn('deleted',original[0]);self.assertNotIn('deleted',original[1])
        report=self.files.require_clean()['items'][0]
        self.assertEqual(report['state'],'deleted');self.assertIsNone(report['expected_sha256']);self.assertEqual(report['expected_bytes'],0)
        source=self.session.snapshot
        copied=self.fixture.root/'cold-note-project';shutil.copytree(self.root,copied)
        store=ProjectStore.open(copied);self.addCleanup(store.close)
        artifacts=ProjectArtifacts(store);self.addCleanup(artifacts.close)
        cold_db=self.fixture.metadata('cold-note-projection')
        session=ProjectSession(store,cold_db,self.fixture.access,artifacts,validate_records=fixture.validate)
        cold=ProjectFiles(session)
        self.assertEqual(cold.history(first['id']),self.files.history(first['id']))
        self.assertEqual(cold.read(first['id'])['version']['deleted'],True)
        self.assertFalse((copied/'notes/decision.md').exists())
        self.assertEqual(cold.require_clean()['items'][0]['state'],'deleted')
        self.assertEqual(cold_db.execute('SELECT count(*) FROM workbench_records').fetchone()[0],0)
        root_fd=os.open(self.fixture.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.addCleanup(os.close,root_fd)
        result=publish_fork(store,artifacts,root_fd,'independent-note',root_path=self.fixture.root,
            name='Independent notes',expected_checkpoint=session.snapshot['checkpoint'],request_key='fork-note',quiescent=True,
            build_candidate=lambda snapshot,destination:build_candidate(snapshot,destination,
                created_at=timestamp(),id_factory=lambda *args:uuid.uuid4().hex),
            validate_candidate=lambda records,project_id:fixture.validate(records))
        destination=result['snapshot']['project_id']
        fresh_id=file_id(destination,'note','notes/decision.md')
        self.assertNotEqual(first['id'],fresh_id)
        self.assertFalse((self.fixture.root/'independent-note/notes/decision.md').exists())
        fork_store=ProjectStore.open(self.fixture.root/'independent-note');self.addCleanup(fork_store.close)
        fork_artifacts=ProjectArtifacts(fork_store);self.addCleanup(fork_artifacts.close)
        fork_db=self.fixture.metadata('fork-note-projection')
        fork_session=ProjectSession(fork_store,fork_db,self.fixture.access,fork_artifacts,validate_records=fixture.validate)
        fork=ProjectFiles(fork_session)
        self.assertEqual(fork.history(fresh_id),cold.history(first['id']))
        self.assertEqual(fork.require_clean()['items'][0]['state'],'deleted')
        # Existing adoption restores only explicitly supplied current bytes. The
        # independent source remains deleted and all old versions remain exact.
        restored=b'Explicit restored note\r\n';target=fork_store.path/'notes/decision.md'
        target.parent.mkdir(exist_ok=True);target.write_bytes(restored)
        self.assertEqual(fork.inspect()['items'][0]['state'],'changed')
        with self.assertRaises(WorkbenchError):fork.require_clean()
        response=fork.adopt(dict(kind='note',path='notes/decision.md',expected_revision=3,
            expected_sha256=hashlib.sha256(restored).hexdigest()),fork_session.snapshot['checkpoint'],'restore-note')
        self.assertNotIn('deleted',response);self.assertEqual(response['revision'],4)
        self.assertEqual(fork.history(fresh_id)[:3],cold.history(first['id']))
        self.assertEqual(fork.read(fresh_id)['version']['text'].encode(),restored)
        self.assertEqual(fork.require_clean()['items'][0]['state'],'unchanged')
        active=next(r['document'] for r in fork_session.snapshot['records'] if r['family']=='project_file' and r['id']==fresh_id)
        self.assertEqual(active['format'],'project_file_v2')
        self.assertEqual(self.session.snapshot,source);self.assertEqual(store.snapshot(),source)
        self.assertFalse((self.root/'notes/decision.md').exists());self.assertFalse((copied/'notes/decision.md').exists())

    def test_deletion_replay_requires_current_permission_and_exact_bound_input(self):
        first,body,deleted=self.remove_note()
        snapshot=self.session.snapshot
        (self.root/first['path']).write_text('External reappearance, not silently adopted')
        replay=self.files.adopt_deletion(body,'0'*64,'delete-note')
        self.assertEqual(replay,deleted);self.assertEqual(self.session.snapshot,snapshot)
        self.assertEqual(self.files.inspect()['items'][0]['state'],'changed')
        with self.assertRaises(WorkbenchError) as caught:
            self.files.adopt_deletion(dict(body,expected_sha256='a'*64),snapshot['checkpoint'],'delete-note')
        self.assertEqual(caught.exception.code,'conflict')
        token=self.fixture.access.issue(dict(label='Read notes',scopes=['inspect']))['token']
        with self.fixture.access.bind(token),self.assertRaises(AccessError):
            self.files.adopt_deletion(body,snapshot['checkpoint'],'delete-note')
        self.assertEqual(self.session.snapshot,snapshot)
        with self.assertRaises(WorkbenchError):
            self.files.adopt_deletion(body,snapshot['checkpoint'],'already-deleted')
        self.assertEqual((self.root/first['path']).read_text(),'External reappearance, not silently adopted')

    def test_unadopted_present_stale_mismatched_and_script_deletions_are_refused(self):
        note=self.adopt('notes/cas.md','Current reviewed note',kind='note');body=self.deletion_body(note)
        snapshot=self.session.snapshot
        for changed in (body,dict(body,path='notes/never-adopted.md'),dict(body,path='scripts/missing.py'),
                        dict(body,expected_revision=0),dict(body,expected_revision=True),dict(body,expected_sha256=None),
                        dict(body,expected_revision=2),dict(body,expected_sha256='a'*64),dict(body,extra=True)):
            with self.subTest(body=changed),self.assertRaises(WorkbenchError):
                self.files.adopt_deletion(changed,snapshot['checkpoint'],'reject-deletion')
            self.assertEqual(self.session.snapshot,snapshot)
        (self.root/'notes/cas.md').unlink()
        with self.assertRaises(WorkbenchError) as caught:self.files.adopt_deletion(body,'0'*64,'stale-deletion')
        self.assertEqual(caught.exception.code,'stale_project')
        script=self.adopt('scripts/protected.py','# retained script\n');(self.root/'scripts/protected.py').unlink()
        with self.assertRaises(WorkbenchError):
            self.files.adopt_deletion(self.deletion_body(script),self.session.snapshot['checkpoint'],'script-delete')
        self.assertEqual(next(row for row in self.files.inspect()['items'] if row['kind']=='script')['state'],'missing')
        with self.assertRaises(WorkbenchError):self.files.require_clean()
        self.assertEqual(self.files.read(script['id'])['version']['text'],'# retained script\n')

    def test_unsafe_alias_special_file_and_io_error_never_count_as_missing(self):
        note=self.adopt('notes/unsafe.md','Retained authored note',kind='note');target=self.root/note['path'];target.unlink()
        body=self.deletion_body(note);snapshot=self.session.snapshot
        outside=self.fixture.root/'outside-note';outside.write_text('Untouched outside source')
        for kind in ('dangling_symlink','symlink','fifo','hardlink'):
            if kind=='dangling_symlink':target.symlink_to(self.fixture.root/'not-present')
            elif kind=='symlink':target.symlink_to(outside)
            elif kind=='fifo':os.mkfifo(target)
            else:os.link(outside,target)
            try:
                with self.subTest(kind=kind),self.assertRaises(WorkbenchError):
                    self.files.adopt_deletion(body,snapshot['checkpoint'],'unsafe-'+kind)
                self.assertEqual(self.session.snapshot,snapshot)
            finally:target.unlink()
        notes=self.root/'notes';moved=self.root/'original-notes';notes.rename(moved);notes.symlink_to(self.fixture.root)
        try:
            with self.assertRaises(WorkbenchError):self.files.adopt_deletion(body,snapshot['checkpoint'],'unsafe-parent')
        finally:notes.unlink();moved.rename(notes)
        actual_open=os.open
        def unreadable(path,*args,**kwargs):
            if path=='notes' and kwargs.get('dir_fd') is not None:raise PermissionError(13,'Fixture read refusal')
            return actual_open(path,*args,**kwargs)
        with patch('project_files.os.open',side_effect=unreadable),self.assertRaises(WorkbenchError):
            self.files.adopt_deletion(body,snapshot['checkpoint'],'unreadable-parent')
        self.assertEqual(self.session.snapshot,snapshot);self.assertEqual(outside.read_text(),'Untouched outside source')

    def test_v2_closed_grammar_keeps_positive_versions_and_exact_deletion_receipts(self):
        first,body,deleted=self.remove_note();records=self.session.snapshot['records']
        original=next(r for r in records if r['family']=='project_file')
        self.assertEqual(original['document']['format'],'project_file_v2')
        for defect in ('future','v1_deletion','v2_without_deletion','first_deleted','deleted_false','extra','null_text',
                       'nonnull_hash','bool_bytes','script','consecutive'):
            malformed=copy.deepcopy(records);envelope=next(r for r in malformed if r['family']=='project_file');doc=envelope['document']
            value=doc['history'][-1]
            if defect=='future':doc['format']='project_file_v3'
            elif defect=='v1_deletion':doc['format']='project_file_v1'
            elif defect=='v2_without_deletion':doc['history'].pop()
            elif defect=='first_deleted':doc['history']=[dict(value,revision=1)]
            elif defect=='deleted_false':value['deleted']=False
            elif defect=='extra':value['reason']='not part of the grammar'
            elif defect=='null_text':doc['history'][0]['text']=None
            elif defect=='nonnull_hash':value['sha256']='a'*64
            elif defect=='bool_bytes':value['bytes']=False
            elif defect=='script':
                doc.update(kind='script',path='scripts/unsafe.py');envelope['id']=file_id(doc['project_id'],'script',doc['path'])
            else:doc['history'].append(dict(value,revision=3))
            doc['current']=copy.deepcopy(doc['history'][-1])
            with self.subTest(defect=defect),self.assertRaises(WorkbenchError):decode_records(malformed)
        for changes in (dict(deleted=False),dict(sha256='a'*64),dict(bytes=1),dict(changed=False),dict(revision=1)):
            with self.subTest(changes=changes),self.assertRaises(WorkbenchError):
                validate_operation_result('files.adopt_deletion',dict(deleted,**changes),records)
        with self.assertRaises(WorkbenchError):validate_operation_result('files.adopt',deleted,records)

    def test_rebound_parent_during_absence_observation_cannot_publish_a_deletion(self):
        note=self.adopt('notes/sub/raced.md','Exact authored note',kind='note')
        target=self.root/note['path'];target.unlink();body=self.deletion_body(note)
        snapshot=self.session.snapshot;parent=target.parent;parked=self.root/'parked-notes';actual_stat=os.stat
        changed=[]
        def rebind(path,*args,**kwargs):
            try:return actual_stat(path,*args,**kwargs)
            except FileNotFoundError:
                if path=='raced.md' and kwargs.get('dir_fd') is not None and not changed:
                    changed.append(True);parent.rename(parked);parent.mkdir()
                raise
        try:
            with patch('project_files.os.stat',side_effect=rebind),self.assertRaises(WorkbenchError):
                self.files.adopt_deletion(body,snapshot['checkpoint'],'raced-parent')
            self.assertEqual(changed,[True]);self.assertEqual(self.session.snapshot,snapshot)
        finally:
            if changed:parent.rmdir();parked.rename(parent)

    def test_deleted_note_with_missing_parent_stays_absent_and_reappearance_is_not_clean(self):
        first,body,deleted=self.remove_note('notes/sub/deleted.md')
        (self.root/'notes/sub').rmdir()
        self.assertEqual(self.files.require_clean()['items'][0]['state'],'deleted')
        target=self.root/first['path'];target.parent.mkdir()
        for raw in (b'new authored note',b'\xff'):
            target.write_bytes(raw)
            self.assertEqual(self.files.inspect()['items'][0]['state'],'changed')
            with self.assertRaises(WorkbenchError):self.files.require_clean()
        target.unlink();target.symlink_to(self.fixture.root/'missing-outside')
        self.assertEqual(self.files.inspect()['items'][0]['state'],'invalid')
        self.assertEqual(self.files.read(first['id'])['version']['deleted'],True)


if __name__=='__main__':unittest.main()
